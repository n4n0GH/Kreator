"""Live previews for QML documents and Qt Designer forms."""

from __future__ import annotations

import copy
import glob
import os
import re

from PySide6.QtCore import (Q_ARG, QBuffer, QByteArray, QIODevice, QMetaObject, QObject, QPluginLoader, QPoint, QPointF,
                            QRect, QSize, Qt, QTimer, QUrl, Slot)
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlComponent, QQmlContext, QQmlEngine
from PySide6.QtQuick import QQuickImageProvider, QQuickItem
from PySide6.QtWidgets import QLayout, QWidget

import shiboken6

from . import qmldoc

MARKER = "__qv_"

# --------------------------------------------------------------------------- plugin preloading
#
# PySide6 + Qt 6.12 deadlock when a QML plugin is instantiated on the QML type
# loader thread and connects to a signal of the (Python wrapped) application
# object: the loader thread waits for the GIL that the main thread holds while
# it waits for the loader.  Instantiating the plugins on the main thread first
# avoids that, so every module a document may import is preloaded.

_IMPORT_RE = re.compile(r"^\s*import\s+([A-Za-z_][\w.]*)", re.M)


_QT_PREFIXES = ("QtQuick", "QtQml", "Qt", "QtCore", "QtQuick3D", "QtMultimedia", "QtWebEngine", "QtWebView",
                "QtPositioning", "QtLocation", "QtCharts", "QtGraphs", "QtTest", "QtWayland", "Qt5Compat",
                "QtSensors", "QtTextToSpeech", "QtWebSockets", "QtWebChannel", "QtRemoteObjects", "QtScxml",
                "QtNetwork", "QtDataVisualization", "QtSvg")


class PluginPreloader:
    def __init__(self, engine: QQmlEngine):
        self.engine = engine
        self.done_modules: set[str] = set()
        self.loaders: list[QPluginLoader] = []
        self.loaded_files: set[str] = set()

    def module_dirs(self, uri: str):
        rel = uri.replace(".", "/")
        for base in self.engine.importPathList():
            d = os.path.join(base, rel)
            if os.path.isfile(os.path.join(d, "qmldir")):
                yield d

    def preload_text(self, text: str):
        for uri in _IMPORT_RE.findall(text):
            self.preload_module(uri)

    def preload_directory(self, path: str, limit: int = 300):
        files = glob.glob(os.path.join(path, "*.qml")) + glob.glob(os.path.join(path, "*", "*.qml"))
        for f in files[:limit]:
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    self.preload_text(fh.read())
            except OSError:
                pass

    def preload_module(self, uri: str):
        # Qt's own modules are safe (and must not be loaded twice by hand)
        if uri in self.done_modules or uri.split(".", 1)[0] in _QT_PREFIXES:
            return
        self.done_modules.add(uri)
        for d in self.module_dirs(uri):
            try:
                with open(os.path.join(d, "qmldir"), encoding="utf-8") as fh:
                    qmldir = fh.read()
            except OSError:
                continue
            for line in qmldir.splitlines():
                parts = line.split()
                if not parts:
                    continue
                if parts[0] in ("plugin", "optional") and len(parts) >= 2:
                    if parts[0] == "optional":
                        parts = parts[1:]
                    if parts[0] != "plugin" or len(parts) < 2:
                        continue
                    self._load_plugin(d, parts[1], parts[2] if len(parts) > 2 else "")
                elif parts[0] in ("depends", "import") and len(parts) >= 2:
                    self.preload_module(parts[1])
            # modules' own QML files may import further modules
            for f in glob.glob(os.path.join(d, "**", "*.qml"), recursive=True)[:400]:
                try:
                    with open(f, encoding="utf-8", errors="replace") as fh:
                        for sub in _IMPORT_RE.findall(fh.read(4096)):
                            self.preload_module(sub)
                except OSError:
                    pass
            # nested plugins (e.g. org/kde/kirigami/*/)
            for so in glob.glob(os.path.join(d, "**", "*.so"), recursive=True):
                self._load_file(so)

    def _load_plugin(self, d: str, name: str, path: str):
        base = os.path.join(d, path) if path else d
        for cand in (f"lib{name}.so", f"{name}.so", f"lib{name}_debug.so"):
            p = os.path.join(base, cand)
            if os.path.isfile(p):
                self._load_file(p)
                return

    def _load_file(self, path: str):
        if path in self.loaded_files:
            return
        self.loaded_files.add(path)
        loader = QPluginLoader(path)
        loader.instance()  # may fail for non-plugins; that's fine
        self.loaders.append(loader)


# --------------------------------------------------------------------------- i18n

def _fmt(text, *args):
    text = str(text)
    for i, a in enumerate(args, 1):
        if a is not None:
            text = text.replace(f"%{i}", str(a))
    return text


class I18nShim(QObject):
    """Stand-in for KLocalizedContext so i18n() works in previews."""

    @Slot(str, result=str)
    @Slot(str, "QVariant", result=str)
    @Slot(str, "QVariant", "QVariant", result=str)
    @Slot(str, "QVariant", "QVariant", "QVariant", result=str)
    @Slot(str, "QVariant", "QVariant", "QVariant", "QVariant", result=str)
    def i18n(self, text, a1=None, a2=None, a3=None, a4=None):
        return _fmt(text, a1, a2, a3, a4)

    @Slot(str, str, result=str)
    @Slot(str, str, "QVariant", result=str)
    @Slot(str, str, "QVariant", "QVariant", result=str)
    @Slot(str, str, "QVariant", "QVariant", "QVariant", result=str)
    def i18nc(self, _ctx, text, a1=None, a2=None, a3=None):
        return _fmt(text, a1, a2, a3)

    @Slot(str, str, "QVariant", result=str)
    @Slot(str, str, "QVariant", "QVariant", result=str)
    @Slot(str, str, "QVariant", "QVariant", "QVariant", result=str)
    def i18np(self, singular, plural, n=None, a2=None, a3=None):
        try:
            text = singular if int(n) == 1 else plural
        except (TypeError, ValueError):
            text = plural
        return _fmt(text, n, a2, a3)

    @Slot(str, str, str, "QVariant", result=str)
    @Slot(str, str, str, "QVariant", "QVariant", result=str)
    def i18ncp(self, _ctx, singular, plural, n=None, a2=None):
        return self.i18np(singular, plural, n, a2)

    @Slot(str, str, result=str)
    @Slot(str, str, "QVariant", result=str)
    @Slot(str, str, "QVariant", "QVariant", result=str)
    def i18nd(self, _domain, text, a1=None, a2=None):
        return _fmt(text, a1, a2)

    @Slot(str, str, str, result=str)
    @Slot(str, str, str, "QVariant", result=str)
    def i18ndc(self, _domain, _ctx, text, a1=None):
        return _fmt(text, a1)

    @Slot(str, result=str)
    @Slot(str, "QVariant", result=str)
    @Slot(str, "QVariant", "QVariant", result=str)
    def xi18n(self, text, a1=None, a2=None):
        return re.sub(r"</?[a-zA-Z][^>]*>", "", _fmt(text, a1, a2))

    @Slot(str, str, result=str)
    @Slot(str, str, "QVariant", result=str)
    def xi18nc(self, _ctx, text, a1=None):
        return self.xi18n(text, a1)


# --------------------------------------------------------------------------- QML preview

WINDOW_PROPS = {
    "visible", "title", "flags", "modality", "minimumWidth", "minimumHeight", "maximumWidth",
    "maximumHeight", "visibility", "screen", "transientParent", "x", "y", "width", "height",
    "onClosing", "onActiveChanged", "onVisibilityChanged", "onWindowStateChanged", "onFrameSwapped",
    "onActiveFocusItemChanged", "onClosed", "onScreenChanged", "minimumSize", "maximumSize",
}
NO_MARKER_TYPES = {"Component", "ListElement", "ListModel", "Binding", "Connections", "Behavior",
                   "NumberAnimation", "PropertyAnimation", "ColorAnimation", "SequentialAnimation",
                   "ParallelAnimation", "Transition", "State", "PropertyChanges", "Translate", "Scale",
                   "Rotation", "Shortcut", "FontMetrics", "TextMetrics", "Instantiator", "DelegateModel",
                   "SortFilterProxyModel", "KSortFilterProxyModel"}


# Bindings that crash Qt when they evaluate to null, as they do outside the app
# (e.g. a profile normally handed in by the application).
UNSAFE_BINDINGS = {
    "WebEngineView": {"profile"},
    "WebView": {"profile"},
}


def _stripped(name: str, names: set[str]) -> bool:
    """`quitAction.enabled` is stripped together with `quitAction`."""
    return name in names or name.split(".", 1)[0] in names


def build_preview_document(doc: qmldoc.QmlDocument, strip: set[str]):
    """Return (preview document, root mode, uid->objectName map)."""
    pdoc = copy.deepcopy(doc)
    names: dict[int, str] = {}
    mode = "item"
    root = pdoc.root
    if root is None:
        return pdoc, "none", names

    kir = pdoc.import_alias("org.kde.kirigami")
    t = root.short_type
    if t == "ApplicationWindow" and kir is not None and root.type_name == (f"{kir}.ApplicationWindow" if kir else "ApplicationWindow"):
        root.type_name = (f"{kir}." if kir else "") + "ApplicationItem"
        mode = "window"
    elif t == "ApplicationWindow":
        root.type_name = root.type_name[: -len("ApplicationWindow")] + "Page"
        mode = "window"
        mb = root.binding("menuBar")
        if mb is not None and root.binding("header") is None:
            mb.name = "header"
    elif t in ("Window", "ApplicationWindow"):
        root.type_name = "Rectangle"
        mode = "window"
    if mode == "window":
        # keep the window's declared size as the preview's natural size
        for dim in ("width", "height"):
            b = root.binding(dim)
            implicit = "implicit" + dim.capitalize()
            if b is not None and isinstance(b.value, str) and root.binding(implicit) is None:
                b.name = implicit
        if root.short_type == "ApplicationItem" and root.binding("pageStack.globalToolBar.style") is None:
            k = f"{kir}." if kir else ""
            root.members.append(qmldoc.Binding(name="pageStack.globalToolBar.style",
                                               value=f"{k}ApplicationHeaderStyle.ToolBar"))
        strip = strip | WINDOW_PROPS
        for d in root.declarations():
            if "required" in d.modifiers:
                d.modifiers.remove("required")

    for d in root.declarations():
        if "required" in d.modifiers and d.value is None:
            d.modifiers.remove("required")

    # strip unsupported properties (keep line count by leaving a comment)
    def strip_members(node):
        for i, m in enumerate(list(node.members)):
            if isinstance(m, qmldoc.Binding) and _stripped(m.name, strip):
                node.members[i] = qmldoc.RawMember(text=f"// {m.name}: (hidden in preview)")
    strip_members(root)
    for node in qmldoc.iter_subtree(root):
        local_strip = {s.split("@", 1)[1] for s in strip if s.startswith(f"{node.uid}@")}
        if local_strip:
            for i, m in enumerate(list(node.members)):
                if isinstance(m, qmldoc.Binding) and _stripped(m.name, local_strip):
                    node.members[i] = qmldoc.RawMember(text=f"// {m.name}: (hidden in preview)")

    for node in qmldoc.iter_subtree(root):
        unsafe = UNSAFE_BINDINGS.get(node.short_type)
        if unsafe:
            for i, m in enumerate(list(node.members)):
                if isinstance(m, qmldoc.Binding) and m.name in unsafe:
                    node.members[i] = qmldoc.RawMember(text=f"// {m.name}: (not set in the preview)")

    # tag every object so it can be found again
    in_skip = set()
    for node in qmldoc.iter_subtree(root):
        if node.uid in in_skip:
            continue
        if node.short_type in NO_MARKER_TYPES or node.component_name or node.on_target:
            for sub in qmldoc.iter_subtree(node):
                in_skip.add(sub.uid)
            continue
        on = node.binding("objectName")
        if on is not None:
            kind, val = qmldoc.classify(on.value)
            if kind == "string" and val:
                names[node.uid] = val
            continue
        name = f"{MARKER}{node.uid}"
        names[node.uid] = name
        node.members.insert(0, qmldoc.Binding(name="objectName", value=qmldoc.quote(name)))
    return pdoc, mode, names


def preview_text(pdoc: qmldoc.QmlDocument) -> str:
    """Serialise, putting injected objectName bindings on the line of the `{` so
    that line numbers in error messages match the editor."""
    text = pdoc.to_text()
    return re.sub(r"\{\n[ \t]*(objectName: \"" + MARKER + r"\d+\")\n", r"{ \1\n", text)


_FIRST_IMPORT_RE = re.compile(r"^[ \t]*import\b", re.M)


def _with_import(text: str, uri: str) -> str:
    """`text` importing the module `uri` too, on the line of its first import
    (line numbers in error messages stay those of the editor)."""
    if not uri:
        return text
    m = _FIRST_IMPORT_RE.search(text)
    at = m.start() if m else 0
    return f"{text[:at]}import {uri}; {text[at:]}"


class QmlPreview:
    def __init__(self, engine: QQmlEngine, preloader: PluginPreloader):
        self.engine = engine
        self.preloader = preloader
        self.counter = 0
        self.shim = I18nShim()
        self.mocks = None  # MockModules, created on first need
        self.context: QQmlContext | None = None
        self.component: QQmlComponent | None = None

    def component_size(self, snippet: str, imports: str, width: float, height: float) -> tuple[float, float]:
        """The size a palette snippet gets in a parent of the given size (for
        the design view's drop preview); (0, 0) for non-visual objects."""
        body = "\n".join("        " + line for line in snippet.splitlines())
        text = f"{imports}\nItem {{\n    width: {width:g}\n    height: {height:g}\n    Item {{\n        anchors.fill: parent\n{body}\n    }}\n}}\n"
        self.preloader.preload_text(text)
        comp = QQmlComponent(self.engine)
        comp.setData(QByteArray(text.encode("utf-8")), QUrl.fromLocalFile(os.path.join(os.getcwd(), ".kreator-measure.qml")))
        if comp.isError():
            return 0.0, 0.0
        ctx = QQmlContext(self.engine.rootContext())
        ctx.setContextObject(self.shim)
        obj = comp.create(ctx)
        if obj is None:
            return 0.0, 0.0
        QQmlEngine.setObjectOwnership(obj, QQmlEngine.ObjectOwnership.CppOwnership)
        ctx.setParent(obj)
        comp.setParent(obj)
        size = (0.0, 0.0)
        try:
            holder = obj.childItems()[0] if isinstance(obj, QQuickItem) and obj.childItems() else None
            items = holder.childItems() if holder is not None else []
            if items:
                it = items[0]
                stack = [it]
                while stack:  # layouts compute their sizes when polished
                    c = stack.pop()
                    c.ensurePolished()
                    stack.extend(c.childItems())
                w = it.width() or it.implicitWidth()
                h = it.height() or it.implicitHeight()
                size = (float(w), float(h))
        finally:
            obj.deleteLater()
        return size

    def create(self, doc: qmldoc.QmlDocument, base_path: str):
        """Return (object or None, mode, names, error text)."""
        if doc.import_alias("org.kde.plasma.plasmoid") is not None or (
                doc.root is not None and doc.root.short_type in ("PlasmoidItem", "ContainmentItem", "WallpaperItem")):
            return None, "none", {}, ("Plasma applets need a running Plasma shell and cannot be previewed here; "
                                      "use plasmoidviewer to test them. You can still edit the file.")
        strip: set[str] = set()
        last_errors = ""
        mocked: list[str] = []
        self._premock(doc, base_path, mocked)
        own = self._mock_own_module(doc, base_path, mocked)
        for _attempt in range(16):
            pdoc, mode, names = build_preview_document(doc, strip)
            text = _with_import(preview_text(pdoc), own)
            self.preloader.preload_text(text)
            self.counter += 1
            directory = os.path.dirname(base_path) if base_path else os.getcwd()
            url = QUrl.fromLocalFile(os.path.join(directory, f".kreator-preview-{self.counter}.qml"))
            self.engine.trimComponentCache()
            comp = QQmlComponent(self.engine)
            comp.setData(QByteArray(text.encode("utf-8")), url)
            if comp.isError():
                errs = comp.errors()
                last_errors = format_errors(errs)
                if self._mock_missing_modules(errs, base_path, mocked):
                    continue
                new = _strippable(errs, pdoc, doc)
                if new and not new <= strip:
                    strip |= new
                    continue
                return None, mode, names, last_errors
            ctx = QQmlContext(self.engine.rootContext())
            ctx.setContextObject(self.shim)
            obj = comp.beginCreate(ctx)
            if obj is None:
                errs = comp.errors()
                last_errors = format_errors(errs)
                new = _strippable(errs, pdoc, doc)
                if new and not new <= strip:
                    strip |= new
                    continue
                return None, mode, names, last_errors
            comp.completeCreate()
            # never let the QML garbage collector take objects we hand to QML
            QQmlEngine.setObjectOwnership(obj, QQmlEngine.ObjectOwnership.CppOwnership)
            # keep references alive as long as the object lives: the component
            # and context belong to the object (PySide ties the object's wrapper
            # to the component's: dropping that one invalidated it, so the
            # previous preview was never hidden nor deleted when a new one
            # replaced it)
            ctx.setParent(obj)
            comp.setParent(obj)
            self.component, self.context = comp, ctx
            if mode != "window":
                mo = obj.metaObject()
                if mo.indexOfProperty("globalToolBarStyle") >= 0 and mo.indexOfProperty("actions") >= 0:
                    mode = "page"
                elif not isinstance(obj, QQuickItem):
                    mode = "popup" if obj.metaObject().indexOfMethod("open()") >= 0 and obj.property("contentItem") is not None else "nonvisual"
            hidden = sorted({s.split("@", 1)[1] for s in strip if "@" in s})
            notes = []
            if mocked:
                notes.append("Modules only available inside the application are simulated: " + "; ".join(mocked) + ".")
            if hidden:
                notes.append("Left out of the preview because the type has no such property: " + ", ".join(hidden))
            note = "\n".join(notes)
            return obj, mode, names, note
        return None, "item", {}, last_errors

    def _module_loadable(self, uri: str) -> bool:
        """Does an import path contain `uri` with its plugin library (if any)?"""
        rel = uri.replace(".", os.sep)
        for base in self.engine.importPathList():
            if self.mocks is not None and base == self.mocks.root:
                continue
            d = os.path.join(base, rel)
            qmldir = os.path.join(d, "qmldir")
            if base.startswith(":") or not os.path.isfile(qmldir):
                continue
            try:
                with open(qmldir, encoding="utf-8", errors="replace") as fh:
                    plugins = [ln.split()[-1] for ln in fh if re.match(r"\s*(optional\s+)?plugin\s", ln)]
            except OSError:
                continue
            if not plugins or any(glob.glob(os.path.join(d, f"*{p}*.so")) for p in plugins):
                return True
        return False

    def _premock(self, doc, base_path, mocked):
        """Stand in for imported modules that can't be loaded outside their app.

        Done before compiling because the engine caches failed imports."""
        from .mocks import MockModules

        for uri, _alias in doc.imports():
            if uri.startswith('"') or uri.split(".", 1)[0] in _QT_PREFIXES or self._module_loadable(uri):
                continue
            if self.mocks is None:
                self.mocks = MockModules()
            desc = self.mocks.build(uri, base_path)
            if desc is None:
                continue
            if self.mocks.root not in self.engine.importPathList():
                self.engine.addImportPath(self.mocks.root)
            mocked.append(desc)

    def _mock_own_module(self, doc, base_path, mocked) -> str:
        """Stand in for the module the document is a part of (see
        mocks.own_module()); its URI, for the preview to import, or ""."""
        from .mocks import MockModules, own_module

        uri = own_module(base_path)
        if not uri or self._module_loadable(uri):
            return ""
        if any(u == uri for u, _alias in doc.imports()):
            return ""   # (imported by the document: done by _premock())
        if self.mocks is None:
            self.mocks = MockModules()
        desc = self.mocks.build(uri, base_path, own=True)
        if desc is None:
            return ""
        if self.mocks.root not in self.engine.importPathList():
            self.engine.addImportPath(self.mocks.root)
        mocked.append(desc)
        return uri

    def _mock_missing_modules(self, errors, base_path, mocked) -> bool:
        """Build stand-ins for modules that cannot be imported; True to retry."""
        from .mocks import MockModules

        retry = False
        for uri in _missing_modules(errors):
            if any(m.startswith(uri + " ") for m in mocked):
                continue
            if self.mocks is None:
                self.mocks = MockModules()
            desc = self.mocks.build(uri, base_path)
            if desc is None:
                continue
            if self.mocks.root not in self.engine.importPathList():
                self.engine.addImportPath(self.mocks.root)
            mocked.append(desc)
            retry = True
        return retry


_MISSING_MODULE_RE = re.compile(r'module "([\w.]+)" (?:is not installed|plugin "[^"]*" not found)')


def _missing_modules(errors) -> list[str]:
    return list(dict.fromkeys(m.group(1) for e in errors
                              for m in [_MISSING_MODULE_RE.search(e.description())] if m))


_NONEXIST_RE = re.compile(r'(?:Cannot assign to non-existent property|non-existent property|Invalid property assignment: "?)\s*"?([\w.]+)"?')


def _strippable(errors, pdoc, doc) -> set[str]:
    """Properties named in 'non-existent property' errors on the root, as uid@name."""
    out = set()
    lines = preview_text(pdoc).split("\n")
    for e in errors:
        m = _NONEXIST_RE.search(e.description())
        if not m:
            continue
        name = m.group(1)
        line = e.line()
        # find which node declares that binding at this line: walk up to the nearest object start
        uid = _uid_at_line(lines, line)
        if uid is not None:
            out.add(f"{uid}@{name}")
    return out


def _uid_at_line(lines, line):
    """uid of the innermost tagged object enclosing 1-based `line`."""
    if not 0 < line <= len(lines):
        return None
    marker = re.compile(r'objectName: "' + MARKER + r'(\d+)"')
    m = marker.search(lines[line - 1])
    if m:
        return int(m.group(1))
    balance = 0
    for i in range(line - 2, -1, -1):
        ln = lines[i]
        balance += ln.count("}") - ln.count("{")
        if balance < 0:
            m = marker.search(ln)
            if m:
                return int(m.group(1))
            balance = 0  # a group or untagged object: keep looking outwards
    return None


def format_errors(errors) -> str:
    out = []
    for e in errors:
        msg = e.description()
        line = e.line()
        url = e.url().toString()
        where = "" if (not url or ".kreator-preview-" in url) else os.path.basename(url) + ", "
        out.append(f"{where}Line {line}: {msg}" if line > 0 else f"{where.rstrip(', ')}: {msg}" if where else msg)
    return "\n".join(dict.fromkeys(out))


def find_named(root: QObject, names: dict[int, str]) -> dict[int, QObject]:
    """Map uid -> live object by objectName, searching QObject and item trees."""
    wanted = {v: k for k, v in names.items()}
    found: dict[int, QObject] = {}
    seen = set()
    stack = [root]
    keep = []  # keep wrappers alive so their ids stay unique
    while stack:
        o = stack.pop()
        if o is None:
            continue
        try:
            key = shiboken6.getCppPointer(o)[0]
        except Exception:  # noqa: BLE001
            continue
        if key in seen:
            continue
        seen.add(key)
        keep.append(o)
        try:
            n = o.objectName()
        except RuntimeError:
            continue
        uid = wanted.get(n)
        if uid is not None and uid not in found:
            found[uid] = o
            QQmlEngine.setObjectOwnership(o, QQmlEngine.ObjectOwnership.CppOwnership)
        stack.extend(o.children())
        if isinstance(o, QQuickItem):
            stack.extend(o.childItems())
        for prop in ("contentItem", "background", "header", "footer"):
            try:
                v = o.property(prop) if o.metaObject().indexOfProperty(prop) >= 0 else None
            except Exception:  # noqa: BLE001
                v = None
            if isinstance(v, QObject):
                stack.append(v)
    return found


def pick_item(host: QQuickItem, root_items: list[QQuickItem], x: float, y: float, name_to_uid: dict[str, int]):
    """Deepest visible item under (x, y) in host coordinates that maps to a document node."""
    stack = pick_stack(host, root_items, x, y, name_to_uid)
    return stack[0] if stack else None


def pick_stack(host: QQuickItem, root_items: list[QQuickItem], x: float, y: float, name_to_uid: dict[str, int]):
    """Every visible item under (x, y) in host coordinates that maps to a
    document node, as uids, topmost first."""
    hits = []

    def rec(item: QQuickItem):
        if not item.isVisible() or item.opacity() <= 0:
            return
        local = item.mapFromItem(host, QPointF(x, y))
        inside = 0 <= local.x() <= item.width() and 0 <= local.y() <= item.height()
        if inside:
            uid = name_to_uid.get(item.objectName())
            if uid is not None:
                if uid in hits:
                    hits.remove(uid)
                hits.append(uid)
        # children may overflow, so always recurse (but only if clipping allows)
        if item.clip() and not inside:
            return
        for c in sorted(item.childItems(), key=lambda c: c.z()):
            rec(c)

    for r in root_items:
        rec(r)
    return hits[::-1]


# --------------------------------------------------------------------------- popups

def _pointer(obj) -> int:
    try:
        return shiboken6.getCppPointer(obj)[0] if obj is not None and shiboken6.isValid(obj) else 0
    except Exception:  # noqa: BLE001
        return 0


class PopupConfiner(QObject):
    """Keeps what a preview shows over itself inside the preview.

    Qt doesn't draw popups (dialogs, menus, drawers) where they are declared:
    when one opens, its visual item is moved into the overlay of its window.
    A preview lives in Kreator's own window, so a previewed application's
    sidebar would cover Kreator's sidebar, and its dialogs would dim and block
    all of Kreator. Kirigami puts more there, such as passive notifications.

    The confiner watches the window's overlay and hands everything in it that
    belongs to a preview to the design view's popup layer (PreviewPane.qml's
    `popupLayer`, which does the rest). What belongs to a preview is told by
    its QObject and item parents leading to one of the preview's objects; QML
    can't see those, which is why this part is done here.
    """

    def __init__(self, roots, parent=None):
        super().__init__(parent)
        self._roots = roots             # callable: the previews' root objects (current and replaced ones)
        self._layer: QQuickItem | None = None
        self._watched: set[int] = set()  # the items whose children are watched
        self._adopted: list[tuple[QQuickItem, int]] = []  # (item, its preview's root)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.sweep)

    def set_layer(self, layer):
        self._layer = layer if isinstance(layer, QQuickItem) else None
        self.schedule()

    @Slot()
    def schedule(self):
        """Look at the overlay once Qt is done with what it is doing there
        (it may be in the middle of opening the popup)."""
        if not self._timer.isActive():
            self._timer.start()

    def _watch(self, item):
        key = _pointer(item)
        if key and key not in self._watched:
            self._watched.add(key)
            item.childrenChanged.connect(self.schedule)
            item.destroyed.connect(lambda *_a, k=key: self._watched.discard(k))

    def _root_of(self, obj, roots: set[int]) -> int:
        """The preview root that `obj` belongs to (0: none), following QObject
        parents, item parents and the items popups are attached to."""
        seen: set[int] = set()
        stack = [obj]
        while stack and len(seen) < 500:
            o = stack.pop()
            key = _pointer(o)
            if not key or key in seen:
                continue
            seen.add(key)
            if key in roots:
                return key
            try:
                stack.append(o.parent())
                if isinstance(o, QQuickItem):
                    stack.append(o.parentItem())
                elif o.inherits("QQuickPopup"):
                    stack.append(o.property("parent"))
            except RuntimeError:
                continue
        return 0

    @Slot()
    def sweep(self):
        layer = self._layer
        if not _pointer(layer) or layer.window() is None:
            return
        content = layer.window().contentItem()
        self._watch(content)
        roots = {_pointer(r) for r in self._roots()} - {0}
        if not roots:
            return
        overlay = next((c for c in content.childItems() if c.inherits("QQuickOverlay")), None)
        if overlay is not None:
            self._watch(overlay)
        # (non-modal Kirigami drawers put themselves below the overlay, among
        # the window's own items)
        candidates = [c for c in content.childItems() if c.inherits("QQuickPopupItem")]
        candidates += overlay.childItems() if overlay is not None else []
        for item in candidates:
            popup = item.parent() if item.inherits("QQuickPopupItem") else None
            if popup is not None and not popup.inherits("QQuickPopup"):
                popup = None
            root = self._root_of(popup or item, roots)
            if not root:
                continue
            self._adopted = [(i, r) for i, r in self._adopted if _pointer(i) and _pointer(i) != _pointer(item)]
            self._adopted.append((item, root))
            if popup is not None:
                QMetaObject.invokeMethod(layer, "adoptPopup", Qt.ConnectionType.DirectConnection,
                                         Q_ARG("QVariant", item), Q_ARG("QVariant", popup))
            else:
                QMetaObject.invokeMethod(layer, "adoptItem", Qt.ConnectionType.DirectConnection,
                                         Q_ARG("QVariant", item))

    def retire(self, root):
        """A preview was replaced (it is deleted a little later): what it
        still shows goes away now."""
        key = _pointer(root)
        keep = []
        for item, r in self._adopted:
            if not _pointer(item):
                continue
            if r == key:
                item.setVisible(False)
            else:
                keep.append((item, r))
        self._adopted = keep


# --------------------------------------------------------------------------- .ui preview

class UiImageProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.image = QImage(1, 1, QImage.Format.Format_ARGB32)
        self.image.fill(Qt.GlobalColor.transparent)

    def requestImage(self, _id, size, _requested):  # noqa: N802
        if size is not None:
            try:
                size.setWidth(self.image.width())
                size.setHeight(self.image.height())
            except AttributeError:
                pass
        return self.image


class UiPreview:
    def __init__(self, provider: UiImageProvider):
        self.provider = provider
        self.widget: QWidget | None = None
        self.dpr = 1.0

    def render(self, xml_text: str, base_path: str):
        from PySide6.QtUiTools import QUiLoader

        if self.widget is not None:
            self.widget.hide()
            self.widget.deleteLater()
            self.widget = None
        loader = QUiLoader()
        if base_path:
            from PySide6.QtCore import QDir
            loader.setWorkingDirectory(QDir(os.path.dirname(base_path)))
        buf = QBuffer()
        buf.setData(QByteArray(xml_text.encode("utf-8")))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        w = loader.load(buf, None)
        err = loader.errorString()
        if w is None:
            return False, err or "Could not create the form"
        w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        if w.width() < 50 or w.height() < 30:
            w.resize(w.sizeHint().expandedTo(QSize(320, 200)))
        w.show()
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        pm = w.grab()
        self.dpr = pm.devicePixelRatio()
        self.provider.image = pm.toImage()
        self.widget = w
        return True, err if err and "unknown" in err.lower() else ""

    def size(self) -> QSize:
        return self.widget.size() if self.widget else QSize(0, 0)

    @staticmethod
    def size_hint(spec: dict) -> tuple[int, int]:
        """The size a new widget of a palette entry would like."""
        from PySide6.QtUiTools import QUiLoader

        w = QUiLoader().createWidget(spec.get("type", "QWidget"), None)
        if w is None:
            return 120, 80
        for name, (_kind, value) in spec.get("props", {}).items():
            if name == "text":
                w.setProperty("text", value)
        hint = w.sizeHint()
        w.deleteLater()
        if not hint.isValid() or hint.width() <= 0 or hint.height() <= 0:
            return 120, 80
        return max(hint.width(), 20), max(hint.height(), 20)

    def find(self, name: str):
        if self.widget is None or not name:
            return None
        if self.widget.objectName() == name:
            return self.widget
        return self.widget.findChild(QObject, name)

    def rect_of(self, name: str) -> QRect:
        o = self.find(name)
        if o is None:
            return QRect()
        if isinstance(o, QWidget):
            if o is self.widget:
                return QRect(QPoint(0, 0), o.size())
            if not o.isVisibleTo(self.widget):
                return QRect()
            return QRect(o.mapTo(self.widget, QPoint(0, 0)), o.size())
        if isinstance(o, QLayout):
            pw = o.parentWidget()
            g = o.geometry()
            if pw is None:
                return QRect()
            return QRect(pw.mapTo(self.widget, g.topLeft()), g.size()) if pw is not self.widget else g
        return QRect()

    def pick_stack(self, x: int, y: int, names: set[str]) -> list[str]:
        """The named widgets under (x, y), topmost first (later siblings are
        drawn over earlier ones, children over their parent)."""
        if self.widget is None:
            return []
        hits = []

        def rec(w: QWidget):
            if not w.isVisibleTo(self.widget):
                return
            local = w.mapFrom(self.widget, QPoint(x, y)) if w is not self.widget else QPoint(x, y)
            if not w.rect().contains(local):
                return
            if w.objectName() in names:
                hits.append(w.objectName())
            for c in w.children():
                if isinstance(c, QWidget) and not c.isWindow():
                    rec(c)

        rec(self.widget)
        return hits[::-1]

    def pick(self, x: int, y: int, names: set[str]) -> str:
        if self.widget is None:
            return ""
        w = self.widget.childAt(QPoint(x, y))
        while w is not None:
            if w.objectName() in names:
                return w.objectName()
            # layouts: is the point inside a named layout of the parent?
            w = w.parentWidget()
        return self.widget.objectName()
