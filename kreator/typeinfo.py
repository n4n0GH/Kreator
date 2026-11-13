"""Descriptions of QML types implemented in C++, from their .qmltypes files.

Go to definition has nothing to open for such types (Rectangle, Item,
Kirigami.Icon…): qmlls only knows a source file for types written in QML.
Kreator shows a short description instead: the type's module, its
properties, signals and methods, and those it inherits.

The index of all .qmltypes files below the QML import paths is built once
(parsing the ~250 files of a full Qt + KDE installation takes well under a
second); a project's own modules (e.g. a cxx-qt app's) are found in its build
output like the preview's stand-ins (mocks.py).
"""

from __future__ import annotations

import os
import re

from PySide6.QtCore import QLibraryInfo

from .mocks import _find_qmldirs, _parse_qmltypes

_EXPORT = re.compile(r"([\w.]+)/(\w+) (\d+)(?:\.(\d+))?")


# C++ value types as written in QML
_QML_TYPES = {
    "QString": "string", "QColor": "color", "double": "real", "float": "real", "qreal": "real",
    "QUrl": "url", "QVariant": "var", "QJSValue": "var", "QVariantMap": "var", "QVariantList": "list<var>",
    "QStringList": "list<string>", "QFont": "font", "QPointF": "point", "QPoint": "point", "QSizeF": "size",
    "QSize": "size", "QRectF": "rect", "QRect": "rect", "QDateTime": "date", "QDate": "date", "QTime": "date",
    "QMatrix4x4": "matrix4x4", "QQuaternion": "quaternion", "QVector2D": "vector2d", "QVector3D": "vector3d",
    "QVector4D": "vector4d", "QObject": "QtObject", "qlonglong": "int", "qulonglong": "int", "uint": "int",
    "short": "int", "ushort": "int", "qsizetype": "int", "QByteArray": "var",
}


def _list(value) -> list:
    return value if isinstance(value, list) else ([] if value in (None, "") else [value])


class _Module:
    def __init__(self, uri: str):
        self.uri = uri
        self.imports: list[str] = []     # re-exported modules (qmldir "import X")
        self.types: dict[str, tuple] = {}  # QML name -> ((major, minor), component)


class TypeIndex:
    def __init__(self, paths_getter=None):
        self._paths_getter = paths_getter or (lambda: [])
        self._modules: dict[str, _Module] | None = None
        self._by_cpp: dict[str, dict] = {}
        self._exported: dict[str, tuple[str, str]] = {}   # C++ name -> (module, QML name)
        self._project_dirs: set[str] = set()

    # ----------------------------------------------------------------- loading
    def _base_paths(self) -> list[str]:
        paths = list(self._paths_getter())
        sys_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.QmlImportsPath)
        if sys_path:
            paths.append(sys_path)
        return [p for p in dict.fromkeys(paths) if os.path.isdir(p)]

    def _ensure(self):
        if self._modules is not None:
            return
        self._modules = {}
        for base in self._base_paths():
            for root, dirs, files in os.walk(base):
                dirs.sort()
                if "qmldir" in files:
                    self._load_qmldir(os.path.join(root, "qmldir"))

    def _load_qmldir(self, path: str, uri: str = "") -> _Module | None:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = [ln.split("#", 1)[0].split() for ln in fh]
        except OSError:
            return None
        lines = [ln for ln in lines if ln]
        uri = next((ln[1] for ln in lines if ln[0] == "module" and len(ln) > 1), uri)
        if not uri:
            return None
        mod = self._modules.get(uri) or _Module(uri)
        self._modules[uri] = mod
        mdir = os.path.dirname(path)
        for ln in lines:
            if ln[0] == "import" and len(ln) > 1 and ln[1] not in mod.imports:
                mod.imports.append(ln[1])
            elif ln[0] == "typeinfo" and len(ln) > 1:
                self._load_qmltypes(os.path.join(mdir, ln[1]))
        return mod

    def _load_qmltypes(self, path: str):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                comps = _parse_qmltypes(fh.read())
        except (OSError, IndexError):
            return
        for comp in comps:
            cpp = comp.get("name", "")
            if cpp:
                self._by_cpp[cpp] = comp
            for exp in _list(comp.get("exports")):
                m = _EXPORT.fullmatch(exp)
                if not m:
                    continue
                uri, name = m.group(1), m.group(2)
                version = (int(m.group(3)), int(m.group(4) or 0))
                mod = self._modules.get(uri) or _Module(uri)
                self._modules[uri] = mod
                old = mod.types.get(name)
                if old is None or old[0] <= version:
                    mod.types[name] = (version, comp)
                if cpp:
                    self._exported.setdefault(cpp, (uri, name))

    def _project_module(self, uri: str, near: str):
        """A module of the project (e.g. built by cxx-qt), from its build output."""
        key = f"{uri}@{near}"
        if key in self._project_dirs or not near:
            return
        self._project_dirs.add(key)
        for path in _find_qmldirs(near, uri):
            self._load_qmldir(path, uri)

    # ----------------------------------------------------------------- lookup
    def _find(self, uri: str, name: str, seen=None):
        seen = seen if seen is not None else set()
        if uri in seen:
            return None
        seen.add(uri)
        mod = self._modules.get(uri)
        if mod is None:
            return None
        if name in mod.types:
            return uri, mod.types[name][1]
        for sub in mod.imports:
            hit = self._find(sub, name, seen)
            if hit:
                return hit
        return None

    def resolve(self, word: str, imports: list[tuple[str, str]], near: str = ""):
        """(module, component) for a type name as written in a document with
        these imports ([(module, alias)]); "Kirigami.Icon" uses an alias."""
        self._ensure()
        qualifier, _, name = word.rpartition(".")
        # later imports win, as in QML
        candidates = [m for m, alias in reversed(imports) if (alias or "") == qualifier]
        for uri in candidates:
            if uri not in self._modules:
                self._project_module(uri, near)
            hit = self._find(uri, name)
            if hit:
                return hit
        return None

    def qml_type(self, t: str) -> str:
        """A C++ type name as QML code names it (QColor -> color, QQuickItem -> Item)."""
        t = (t or "var").replace("const ", "").rstrip("*&").strip()
        if t in _QML_TYPES:
            return _QML_TYPES[t]
        if t in self._exported:
            return self._exported[t][1]
        for prefix in ("QQuick", "QQml", "QQuick3D"):
            if t.startswith(prefix) and len(t) > len(prefix):
                return t[len(prefix):]
        return t

    def _members(self, comp: dict) -> dict:
        props, signals, methods = [], [], []
        for ch in comp.get("_children", []):
            kind, name = ch.get("_kind"), ch.get("name", "")
            if not name or name.startswith("_"):
                continue
            if kind == "Property":
                t = self.qml_type(ch.get("type", "var"))
                if ch.get("isList") == "true":
                    t = f"list<{t}>"
                props.append({"name": name, "type": t, "readonly": ch.get("isReadonly") == "true"})
            elif kind in ("Signal", "Method"):
                params = [f"{p.get('name', '')}: {self.qml_type(p.get('type'))}" if p.get("name") else self.qml_type(p.get("type"))
                          for p in ch.get("_children", []) if p.get("_kind") == "Parameter"]
                ret = ch.get("type", "")
                entry = {"name": name, "params": ", ".join(params), "returns": self.qml_type(ret) if ret else ""}
                (signals if kind == "Signal" else methods).append(entry)
        # property change signals are implied: leave them out
        names = {p["name"] for p in props}
        signals = [s for s in signals if not (s["name"].endswith("Changed") and s["name"][:-7] in names)]
        key = lambda e: e["name"].lower()  # noqa: E731
        return {"properties": sorted(props, key=key), "signals": sorted(signals, key=key),
                "methods": sorted(methods, key=key)}

    def _label(self, comp: dict) -> str:
        cpp = comp.get("name", "")
        exp = self._exported.get(cpp)
        return exp[1] if exp else cpp

    def describe(self, word: str, imports: list[tuple[str, str]], near: str = "") -> dict:
        """{name, module, cppName, ..members, bases: [{name, module, ..members}]}
        or {} if the type isn't known (or is written in QML)."""
        hit = self.resolve(word, imports, near)
        if not hit:
            return {}
        uri, comp = hit
        out = {"name": word.rpartition(".")[2], "module": uri, "cppName": comp.get("name", ""),
               "singleton": comp.get("isSingleton") == "true", **self._members(comp), "bases": []}
        seen = {comp.get("name")}
        proto = comp.get("prototype", "")
        while proto and proto not in seen:
            seen.add(proto)
            base = self._by_cpp.get(proto)
            if base is None:
                out["bases"].append({"name": proto, "module": "", "properties": [], "signals": [], "methods": []})
                break
            exp = self._exported.get(proto)
            out["bases"].append({"name": self._label(base), "module": exp[0] if exp else "", **self._members(base)})
            proto = base.get("prototype", "")
        return out
