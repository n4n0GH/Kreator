"""The QObject exposed to the QML user interface as the `Backend` singleton."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
import re

import shiboken6
from PySide6.QtCore import (
    QFileSystemWatcher, QProcess,
    Property, QLockFile, QObject, QPoint, QPointF, QSettings, QStandardPaths, QTimer, QUrl, Signal, Slot,
)
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine
from PySide6.QtQuick import QQuickItem

from . import documents, editors, katestyle, palette, preview, project, qmldoc, session, signalflow, typeinfo, uidoc
from .runner import Runner
from .models import RowsModel

PARSE_ERRORS = (qmldoc.QmlSyntaxError, uidoc.UiError)


def _clean_positions(positions) -> dict:
    """{str: [x, y]} with finite, non-negative numbers; anything else dropped."""
    out = {}
    if not isinstance(positions, dict):
        return out
    for k, v in positions.items():
        try:
            x, y = float(v[0]), float(v[1])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if isinstance(k, str) and 0 <= x < 1e6 and 0 <= y < 1e6:
            out[k] = [round(x, 1), round(y, 1)]
    return out


@dataclass
class DocState:
    """A document that is open but not shown, with everything to restore it."""
    key: str
    adapter: object
    path: str
    saved_text: str
    undo: list = field(default_factory=list)
    redo: list = field(default_factory=list)
    selected: int = 0
    collapsed: set = field(default_factory=set)
    disk_text: str = ""
    template_name: str = ""

    # (adapter, saved text) -> modified: a background tab's document only
    # changes by being replaced, so its text needn't be made again for every
    # look at the tabs
    _modified: tuple | None = field(default=None, repr=False, compare=False)

    @property
    def modified(self) -> bool:
        m = self._modified
        if m is None or m[0] is not self.adapter or m[1] is not self.saved_text:
            m = self._modified = (self.adapter, self.saved_text, self.adapter.text() != self.saved_text)
        return m[2]

    @property
    def name(self) -> str:
        return os.path.basename(self.path) if self.path else (self.template_name or "Untitled")


class Backend(QObject):
    documentChanged = Signal()       # a different document was loaded / closed
    contentChanged = Signal()        # text / structure changed
    selectionChanged = Signal()
    stateChanged = Signal()          # modified / undo / redo
    previewChanged = Signal()
    noteChanged = Signal()
    editorsChanged = Signal()
    kateStyleChanged = Signal()
    diskChanged = Signal()           # the file was changed by another program
    documentsChanged = Signal()      # the set of open documents or their modified state
    projectChanged = Signal()
    recentChanged = Signal()
    insertSlotsChanged = Signal()    # where the Add tab's components can go, or go
    runChanged = Signal()            # what Run would start, or whether it is running
    runOutputChanged = Signal()
    runProblem = Signal(str)         # the running application reported a problem (once per run)
    runFinished = Signal(str, int, bool)   # file name, exit code, failed
    notify = Signal(str)             # transient message for the user
    errorOccurred = Signal(str)

    def __init__(self, engine: QQmlEngine, preloader: preview.PluginPreloader, ui_provider, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.preloader = preloader
        self.qml_preview = preview.QmlPreview(engine, preloader)
        self.popup_confiner = preview.PopupConfiner(lambda: [self._preview_obj, *self._graveyard], self)
        self.ui_preview = preview.UiPreview(ui_provider)
        # what the Add tab shows of a component before it is added
        self._palette_images = preview.PaletteImageProvider()
        engine.addImageProvider("kreatorpalette", self._palette_images)
        self._palette_item = None
        self._palette_serial = 0
        self.settings = QSettings("kreator", "kreator")

        self.adapter = None
        self.path = ""
        self.current_key = ""
        self.docs: dict[str, DocState] = {}
        # the signal flow view's objects moved by hand: doc key -> {stable key: [x, y]}
        self._flow_positions: dict[str, dict] = {}
        self.tab_order: list[str] = []       # keys of open documents, as tabs
        self._tabs_model = RowsModel(["key", "path", "name", "modified", "current", "untitled", "recency"], "key", self)
        self.documentsChanged.connect(self._refresh_tabs)
        self._untitled = 0
        # Kate's editor in the source view (see native.py); set by the app at start
        self._kate_editor = False
        self._kate_problem = ""
        # session (see saveSession): only one running instance owns it
        self._session_lock: QLockFile | None = None
        self._session_written = None      # last JSON written, to skip unchanged saves
        self._pending_source = ""         # unapplied source view text of the current doc
        self._restored_pending: dict[str, str] = {}
        self.project_root = ""
        # descriptions of C++ QML types (Ctrl+click on one in Kate's editor)
        self._types = typeinfo.TypeIndex(lambda: [p for p in self.engine.importPathList() if os.path.isdir(p)])
        self._project_files: list[str] = []
        self._project_dirs: list[str] = []
        self._project_collapsed: set[str] = set()
        self._project_filter = ""
        self._project_model = RowsModel(["key", "relPath", "name", "depth", "isDir", "expanded", "kind",
                                         "modified", "current", "open", "detail"], "key", self)
        self._project_watcher = QFileSystemWatcher(self)
        self._project_scan_timer = QTimer(self, singleShot=True, interval=500)
        self._project_scan_timer.timeout.connect(self._rescan_project)
        self._project_watcher.directoryChanged.connect(lambda _p: self._project_scan_timer.start())
        self.saved_text = ""
        self.undo_stack: list[tuple[str, int]] = []
        self.redo_stack: list[tuple[str, int]] = []
        self.selected = 0
        self.collapsed: set[int] = set()
        self.issues: list[dict] = []
        self.palette_filter = ""
        self._insert_slot = ""       # the property the Add tab's components go into ("": the contents)
        self.prop_filter = ""
        self.show_all_props = False

        self._preview_obj = None
        self._preview_mode = "none"
        self._preview_error = ""
        self._preview_note = ""
        self._preview_names: dict[int, str] = {}
        self._live: dict[int, QObject] = {}
        self._live_missing: dict[int, float] = {}    # uid -> when it was last looked for in vain
        self._ui_counter = 0
        self._ui_size = (0, 0)
        self._source_error = ""
        self._graveyard: list[QObject] = []
        self._alive_keys: set[int] = set()

        self._outline = RowsModel(["uid", "depth", "typeName", "fullType", "objectId", "label",
                                   "hasChildren", "expanded", "issueCount"], "uid", self)
        self._props = RowsModel(["name", "kind", "value", "isSet", "section", "liveValue", "enumKeys",
                                 "typeName", "raw"], "name", self)
        self._palette = RowsModel(["name", "category", "iconName", "description", "index", "module"],
                                  "index", self)
        self._issues = RowsModel(["index", "uid", "severity", "title", "detail", "property", "fixable",
                                  "nodeLabel"], "index", self)

        self._runtime_warnings: list[str] = []
        self._note_pending = False

        # external editors / watching the file on disk
        self.disk_text = ""          # file contents as last read or written by us
        self._external_change = False
        self._external_error = ""
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(lambda _p: self._disk_timer.start())
        self._disk_timer = QTimer(self, singleShot=True, interval=300)
        self._disk_timer.timeout.connect(self._check_disk)
        self._disk_retries = 0

        # Kate's editor settings for the source view; follow changes made in Kate
        self._kate_style = None
        self._katerc_watcher = QFileSystemWatcher(self)
        self._katerc_watcher.addPath(os.path.dirname(katestyle.katerc_path()))
        self._katerc_watcher.directoryChanged.connect(lambda _p: self._kate_timer.start())
        self._katerc_watcher.fileChanged.connect(lambda _p: self._kate_timer.start())
        if os.path.exists(katestyle.katerc_path()):
            self._katerc_watcher.addPath(katestyle.katerc_path())
        self._kate_timer = QTimer(self, singleShot=True, interval=500)
        self._kate_timer.timeout.connect(self._reload_kate_style)
        self.editorsChanged.connect(self.kateStyleChanged)
        self.previewChanged.connect(self.noteChanged)
        engine.warnings.connect(self._on_qml_warnings)

        # Run (see runner.py): the application as it is on disk, outside Kreator
        self.import_paths: list[str] = []     # extra QML import paths (-I), set by the app
        self._runner = Runner(self)
        self._runner.changed.connect(self.runChanged)
        self._runner.outputChanged.connect(self.runOutputChanged)
        self._runner.problemReported.connect(self.runProblem)
        self._runner.finished.connect(self.runFinished)
        self.documentChanged.connect(self.runChanged)
        self.projectChanged.connect(self.runChanged)

        # the Add tab's target: back to the object's contents with every selection
        self.selectionChanged.connect(self._reset_insert_slot)
        for sig in (self.selectionChanged, self.contentChanged, self.previewChanged):
            sig.connect(self.insertSlotsChanged)

        self._preview_shown = True
        self._preview_timer = QTimer(self, singleShot=True, interval=250)
        self._preview_timer.timeout.connect(self.refresh_preview)

    # ======================================================================= properties
    def _get_has_doc(self):
        return self.adapter is not None

    hasDocument = Property(bool, _get_has_doc, notify=documentChanged)

    previewShownChanged = Signal()

    def _set_preview_shown(self, shown):
        if bool(shown) == self._preview_shown:
            return
        self._preview_shown = bool(shown)
        if shown and self._preview_timer.isActive():  # due: now, not after it shows empty
            self._preview_timer.stop()
            self.refresh_preview()
        self.previewShownChanged.emit()
    # whether the design view's preview is on screen (set by the page)
    previewShown = Property(bool, lambda self: self._preview_shown, _set_preview_shown, notify=previewShownChanged)
    docKind = Property(str, lambda self: self.adapter.kind if self.adapter else "", notify=documentChanged)
    filePath = Property(str, lambda self: self.path, notify=documentChanged)
    fileName = Property(str, lambda self: os.path.basename(self.path) if self.path else "Untitled",
                        notify=documentChanged)
    modified = Property(bool, lambda self: self.adapter is not None and self.adapter.text() != self.saved_text,
                        notify=stateChanged)
    canUndo = Property(bool, lambda self: bool(self.undo_stack), notify=stateChanged)
    canRedo = Property(bool, lambda self: bool(self.redo_stack), notify=stateChanged)
    sourceText = Property(str, lambda self: self.adapter.text() if self.adapter else "", notify=contentChanged)
    sourceError = Property(str, lambda self: self._source_error, notify=contentChanged)

    outline = Property(QObject, lambda self: self._outline, constant=True)
    properties = Property(QObject, lambda self: self._props, constant=True)
    palette = Property(QObject, lambda self: self._palette, constant=True)
    issueModel = Property(QObject, lambda self: self._issues, constant=True)
    issueCount = Property(int, lambda self: len(self.issues), notify=contentChanged)
    warningCount = Property(int, lambda self: sum(1 for i in self.issues if i["severity"] == "warning"),
                            notify=contentChanged)

    selectedUid = Property(int, lambda self: self.selected, notify=selectionChanged)

    def _info(self):
        if self.adapter is None or not self.selected:
            return None
        return self.adapter.node_info(self.selected)

    selectedType = Property(str, lambda self: (self._info() or {}).get("type", ""), notify=selectionChanged)
    selectedId = Property(str, lambda self: (self._info() or {}).get("id", ""), notify=selectionChanged)
    idLabel = Property(str, lambda self: (self._info() or {}).get("idLabel", "id"), notify=selectionChanged)
    isRootSelected = Property(bool, lambda self: self._is_root(), notify=selectionChanged)

    previewObject = Property(QObject, lambda self: self._preview_obj, notify=previewChanged)
    previewMode = Property(str, lambda self: self._preview_mode, notify=previewChanged)
    previewError = Property(str, lambda self: self._preview_error, notify=previewChanged)
    previewNote = Property(str, lambda self: "\n".join(([self._preview_note] if self._preview_note else [])
                                                       + self._runtime_warnings), notify=noteChanged)
    uiImage = Property(str, lambda self: f"image://kreatorui/{self._ui_counter}" if self._ui_counter else "",
                       notify=previewChanged)
    uiWidth = Property(int, lambda self: self._ui_size[0], notify=previewChanged)
    uiHeight = Property(int, lambda self: self._ui_size[1], notify=previewChanged)

    def _recent(self):
        v = self.settings.value("recentFiles", [])
        if isinstance(v, str):
            v = [v]
        return [p for p in (v or []) if os.path.exists(p)]

    recentFiles = Property("QVariantList", _recent, notify=recentChanged)

    # ----------------------------------------------------------- external editors
    def _editor_settings(self) -> dict:
        return editors.assign_ids(editors.load_settings(self.settings.value("externalEditors", "")))

    def _default_editor(self) -> dict:
        s = self._editor_settings()
        return next((e for e in editors.editors(s) if e["id"] == s["default"]), editors.editors(s)[0])

    editorList = Property("QVariantList", lambda self: editors.editors(self._editor_settings()),
                          notify=editorsChanged)
    defaultEditorName = Property(str, lambda self: self._default_editor()["name"], notify=editorsChanged)
    defaultEditorIcon = Property(str, lambda self: self._default_editor()["icon"], notify=editorsChanged)
    defaultEditorAvailable = Property(bool, lambda self: self._default_editor()["available"],
                                      notify=editorsChanged)
    def _get_kate_style(self):
        if self._kate_style is None:
            self._kate_style = katestyle.kate_style()
        style = dict(self._kate_style)
        style["enabled"] = bool(self._editor_settings().get("useKateStyle", True))
        return style

    def _reload_kate_style(self):
        new = katestyle.kate_style()
        path = katestyle.katerc_path()
        if os.path.exists(path) and path not in self._katerc_watcher.files():
            self._katerc_watcher.addPath(path)
        if new != self._kate_style:
            self._kate_style = new
            self.kateStyleChanged.emit()

    kateStyle = Property("QVariantMap", _get_kate_style, notify=kateStyleChanged)

    externalChange = Property(bool, lambda self: self._external_change, notify=diskChanged)
    externalError = Property(str, lambda self: self._external_error, notify=diskChanged)

    def _is_root(self):
        if self.adapter is None:
            return False
        root = self.adapter.doc.root
        return root is not None and root.uid == self.selected

    # ======================================================================= files
    # ======================================================================= documents
    # Several documents can be "open": the current one, and others kept in
    # memory with their unsaved edits, undo history and selection, so users can
    # switch between project files without saving or being asked.
    def _current_state(self) -> DocState | None:
        if self.adapter is None:
            return None
        return DocState(key=self.current_key, adapter=self.adapter, path=self.path, saved_text=self.saved_text,
                        undo=list(self.undo_stack), redo=list(self.redo_stack), selected=self.selected,
                        collapsed=set(self.collapsed), disk_text=self.disk_text,
                        template_name=getattr(self, "_template_name", ""))

    def _stash(self):
        st = self._current_state()
        if st is None:
            return
        self.docs[st.key] = st  # stays open (as a tab) until closed

    def _activate(self, st: DocState):
        self.current_key = st.key
        self.path = st.path
        self.adapter = st.adapter
        self.saved_text = st.saved_text
        self.undo_stack[:] = st.undo
        self.redo_stack[:] = st.redo
        self.collapsed = set(st.collapsed)
        self._template_name = st.template_name
        self._source_error = ""
        self._set_preview(None, "none", {}, "", "")
        self._ui_counter = 0
        root = self.adapter.doc.root
        self.selected = st.selected if self.adapter.doc.find(st.selected) is not None else (root.uid if root else 0)
        self._set_disk(st.disk_text)
        self.documentChanged.emit()
        self._after_change(preview_now=True)
        self.selectionChanged.emit()
        self.documentsChanged.emit()
        # changed on disk while it was in the background?
        if self.path and os.path.exists(self.path):
            self._disk_timer.start()

    @Slot(str, result=bool)
    def openFile(self, url_or_path):  # noqa: N802
        path = QUrl(url_or_path).toLocalFile() if url_or_path.startswith("file:") else url_or_path
        path = os.path.abspath(path)
        if self.adapter is not None and path == self.path:
            return True
        cached = self.docs.pop(path, None)
        if cached is not None:
            self._stash()
            self._activate(cached)
            self._add_recent(path)
            return True
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as e:
            self.errorOccurred.emit(f"Could not open {path}: {e.strerror}")
            return False
        try:
            adapter = documents.open_document(text, path)
        except PARSE_ERRORS as e:
            self.errorOccurred.emit(f"Could not read {os.path.basename(path)}: {e}")
            return False
        self._stash()
        self.path = path
        self.current_key = path
        self._add_tab(path)
        self.preloader.preload_directory(os.path.dirname(self.path))
        self._load(adapter, saved_text=adapter.text())
        self._set_disk(text)
        self._add_recent(self.path)
        return True

    @Slot(str)
    def newDocument(self, template):  # noqa: N802
        name, text = documents.TEMPLATES.get(template, documents.TEMPLATES["kirigami-page"])
        self._stash()
        self._untitled += 1
        self.current_key = f"untitled:{self._untitled}"
        self._add_tab(self.current_key)
        self.path = ""
        adapter = documents.open_document(text, name)
        self._template_name = name
        self._load(adapter, saved_text="")
        self._set_disk("")

    def _load(self, adapter, saved_text):
        self._set_preview(None, "none", {}, "", "")
        self._ui_counter = 0
        self.adapter = adapter
        self.saved_text = saved_text
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.collapsed.clear()
        self._source_error = ""
        root = adapter.doc.root
        self.selected = root.uid if root is not None else 0
        self.documentChanged.emit()
        self._after_change(preview_now=True)
        self.selectionChanged.emit()
        self.documentsChanged.emit()

    def _add_tab(self, key):
        if key not in self.tab_order:
            cur = self.tab_order.index(self.current_key) if self.current_key in self.tab_order else len(self.tab_order) - 1
            self.tab_order.insert(cur + 1, key)

    @Slot()
    def closeDocument(self):  # noqa: N802
        """Close the current document (its unsaved changes are dropped) and
        show the neighbouring tab, like Kate."""
        key = self.current_key
        neighbour = ""
        if key in self.tab_order:
            i = self.tab_order.index(key)
            self.tab_order.remove(key)
            if self.tab_order:
                neighbour = self.tab_order[min(i, len(self.tab_order) - 1)]
        st = self.docs.pop(neighbour, None) if neighbour else None
        if st is not None:
            self._activate(st)
            return
        self.adapter = None
        self.path = ""
        self.current_key = ""
        self._set_disk("")
        self._set_preview(None, "none", {}, "", "")
        self._outline.set_rows([])
        self._props.set_rows([])
        self._issues.set_rows([])
        self.issues = []
        self.selected = 0
        self.documentChanged.emit()
        self.contentChanged.emit()
        self.stateChanged.emit()
        self.selectionChanged.emit()
        self.documentsChanged.emit()

    def _all_states(self):
        cur = self._current_state()
        states = ([cur] if cur else []) + list(self.docs.values())
        order = {k: i for i, k in enumerate(self.tab_order)}
        return sorted(states, key=lambda st: order.get(st.key, len(order)))

    def _doc_rows(self):
        # recency: background documents are kept most-recently-used last
        recency = {k: i for i, k in enumerate(reversed(list(self.docs)), start=1)}
        rows = []
        for st in self._all_states():
            rows.append({"key": st.key, "path": st.path, "name": st.name, "modified": st.modified,
                         "current": st.key == self.current_key, "untitled": not st.path,
                         "recency": 0 if st.key == self.current_key else recency.get(st.key, 999)})
        return rows

    openDocuments = Property("QVariantList", _doc_rows, notify=documentsChanged)
    # just their keys (cheap: no texts compared)
    openDocumentKeys = Property("QVariantList", lambda self: ([self.current_key] if self.adapter is not None else [])
                                + list(self.docs), notify=documentsChanged)
    # the same as a model, updated incrementally, so tab items persist
    documentTabs = Property(QObject, lambda self: self._tabs_model, constant=True)

    def _refresh_tabs(self):
        self._tabs_model.set_rows(self._doc_rows())
    currentKey = Property(str, lambda self: self.current_key, notify=documentsChanged)
    unsavedCount = Property(int, lambda self: sum(1 for st in self._all_states() if st.modified),
                            notify=documentsChanged)
    unsavedNames = Property("QVariantList", lambda self: [st.name for st in self._all_states() if st.modified],
                            notify=documentsChanged)

    @Slot(str, result=bool)
    def switchTo(self, key):  # noqa: N802
        """Switch to an open document by key (path or untitled:N)."""
        if key == self.current_key:
            return True
        st = self.docs.pop(key, None)
        if st is None:
            return self.openFile(key) if not key.startswith("untitled:") else False
        self._stash()
        self._activate(st)
        return True

    @Slot(str)
    def closeBackgroundDocument(self, key):  # noqa: N802
        """Close a tab that is not the current document (dropping its changes)."""
        if key == self.current_key:
            self.closeDocument()
            return
        self.docs.pop(key, None)
        if key in self.tab_order:
            self.tab_order.remove(key)
        self.documentsChanged.emit()
        self._project_state_changed()

    @Slot(int)
    def nextTab(self, delta):  # noqa: N802
        if len(self.tab_order) < 2 or self.current_key not in self.tab_order:
            return
        i = (self.tab_order.index(self.current_key) + delta) % len(self.tab_order)
        self.switchTo(self.tab_order[i])

    @Slot(int, int)
    def moveTab(self, from_index, to_index):  # noqa: N802
        if 0 <= from_index < len(self.tab_order) and 0 <= to_index < len(self.tab_order):
            self.tab_order.insert(to_index, self.tab_order.pop(from_index))
            self.documentsChanged.emit()

    @Slot(result=int)
    def saveAll(self):  # noqa: N802
        """Save every modified document that has a file; returns how many untitled ones remain."""
        return self._save_documents()[0]

    def _save_documents(self, wanted=lambda st: True) -> tuple[int, bool]:
        """Save the modified documents for which wanted(state) holds. Returns
        (how many remain unsaved: untitled ones, and background documents
        that couldn't be written; whether writing one failed)."""
        remaining = 0
        failed = False
        cur = self._current_state()
        if cur and cur.modified and wanted(cur):
            if cur.path:
                failed = not self._write(cur.path)
            else:
                remaining += 1
        for st in self.docs.values():
            if not st.modified or not wanted(st):
                continue
            if not st.path:
                remaining += 1
                continue
            text = st.adapter.text()
            try:
                with open(st.path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            except OSError as e:
                self.errorOccurred.emit(f"Could not save {st.path}: {e.strerror}")
                remaining += 1
                failed = True
                continue
            st.saved_text = text
            st.disk_text = text
        self.documentsChanged.emit()
        self.stateChanged.emit()
        self._project_state_changed()
        return remaining, failed

    @Slot(result=str)
    def firstUntitledModified(self):  # noqa: N802
        for st in self._all_states():
            if st.modified and not st.path:
                return st.key
        return ""

    @Slot()
    def discardAll(self):  # noqa: N802
        """Forget all unsaved changes (when quitting without saving)."""
        for key in [k for k, st in self.docs.items() if st.modified]:
            self.docs.pop(key)
            if key in self.tab_order:
                self.tab_order.remove(key)
        if self.adapter is not None:
            self.saved_text = self.adapter.text()
        self.documentsChanged.emit()
        self.stateChanged.emit()
        self._project_state_changed()

    # ======================================================================= projects
    def _get_project_name(self):
        return os.path.basename(self.project_root.rstrip(os.sep)) if self.project_root else ""

    projectPath = Property(str, lambda self: self.project_root, notify=projectChanged)
    projectName = Property(str, _get_project_name, notify=projectChanged)
    projectFiles = Property(QObject, lambda self: self._project_model, constant=True)
    projectFileList = Property("QVariantList", lambda self: [
        {"key": os.path.join(self.project_root, f), "relPath": f, "name": os.path.basename(f)}
        for f in self._project_files], notify=projectChanged)

    def _recent_folders(self):
        v = self.settings.value("recentFolders", [])
        if isinstance(v, str):
            v = [v]
        return [p for p in (v or []) if os.path.isdir(p)]

    recentFolders = Property("QVariantList", _recent_folders, notify=recentChanged)

    @Slot(str, result=bool)
    def openFolder(self, url_or_path):  # noqa: N802
        path = QUrl(url_or_path).toLocalFile() if url_or_path.startswith("file:") else url_or_path
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            self.errorOccurred.emit(f"{path} is not a folder")
            return False
        self.project_root = path
        self._project_collapsed = set()
        self._project_filter = ""
        self._rescan_project()
        self.preloader.preload_directory(path)
        rec = [p for p in self._recent_folders() if p != path]
        rec.insert(0, path)
        self.settings.setValue("recentFolders", rec[:8])
        self.recentChanged.emit()
        self.projectChanged.emit()
        return True

    # -- new projects (see project.py): a folder with a first file, opened at once
    @Slot(result=str)
    def defaultProjectLocation(self):  # noqa: N802
        """The folder a new project is created in unless another is chosen:
        the one used last, else where the last opened folder is, else Documents."""
        last = self.settings.value("projectLocation", "")
        if isinstance(last, str) and last and os.path.isdir(last):
            return last
        for folder in self._recent_folders():
            parent = os.path.dirname(folder.rstrip(os.sep))
            if parent and os.path.isdir(parent) and os.access(parent, os.W_OK):
                return parent
        docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        return docs or os.path.expanduser("~")

    @Slot(result="QVariantList")
    def projectTemplates(self):  # noqa: N802
        titles = {"kirigami-app": ("Kirigami Application", "A window with a page: the start of a KDE application"),
                  "qtquick": ("Qt Quick Application", "A window with plain Qt Quick Controls"),
                  "widgets-form": ("Qt Widgets Form", "A Qt Designer form (.ui)")}
        return [{"key": key, "title": titles.get(key, (key, ""))[0], "description": titles.get(key, ("", ""))[1],
                 "fileName": file_name}
                for key, (file_name, _text) in project.PROJECT_TEMPLATES.items()]

    @Slot(str, str, result=str)
    def projectProblem(self, name, location):  # noqa: N802
        """Why this project can't be created ("" if it can)."""
        return project.project_problem(name, self._local_path(location))

    @Slot(str, str, str, result=str)
    def projectFilePath(self, name, location, template):  # noqa: N802
        """The file a project with these settings starts with."""
        if not name.strip() or not location.strip():
            return ""
        return project.project_file(name, self._local_path(location), template)

    @staticmethod
    def _local_path(url_or_path: str) -> str:
        return QUrl(url_or_path).toLocalFile() if url_or_path.startswith("file:") else url_or_path

    @Slot(str, str, str, result=bool)
    def createProject(self, name, location, template):  # noqa: N802
        """Create a folder called `name` in `location` with a first user
        interface file, and open both."""
        location = self._local_path(location)
        try:
            folder, path = project.create_project(name, location, template)
        except ValueError as e:
            self.errorOccurred.emit(str(e))
            return False
        self.settings.setValue("projectLocation", os.path.abspath(os.path.expanduser(location.strip())))
        if not self.openFolder(folder):
            return False
        return self.openFile(path)

    # -- Run: the application outside Kreator, as `qml6 Main.qml` starts it
    def _run_target(self) -> str:
        """The file Run starts: the project's Main.qml (or main.qml) while a
        document of the project is shown (or none), else the shown QML
        document; "" if there is none, or it has no file yet."""
        if self.project_root and (self.adapter is None or self.path.startswith(self.project_root + os.sep)):
            for name in ("Main.qml", "main.qml"):
                if name in self._project_files:
                    return os.path.join(self.project_root, name)
        if self.adapter is not None and self.adapter.kind == "qml" and self.path:
            return self.path
        return ""

    # (an untitled QML document can be run once it has a file: the window asks for one)
    canRun = Property(bool, lambda self: bool(self._run_target())
                      or (self.adapter is not None and self.adapter.kind == "qml" and not self.path),
                      notify=runChanged)
    running = Property(bool, lambda self: self._runner.running, notify=runChanged)
    # the name of what runs, or would be run
    runName = Property(str, lambda self: os.path.basename(self._runner.path if self._runner.running
                                                          else self._run_target()), notify=runChanged)
    runOutput = Property(str, lambda self: self._runner.output, notify=runOutputChanged)

    @Slot(result=bool)
    def run(self):
        """Save the application's files and start it (again, if it runs)."""
        target = self._run_target()
        if not target:
            self.errorOccurred.emit("There is no QML file to run. Open one, or a project with a Main.qml.")
            return False
        # what runs is what is on disk: unsaved changes to the application's files are saved
        folder = os.path.dirname(target) + os.sep
        _remaining, failed = self._save_documents(lambda st: bool(st.path) and st.path.startswith(folder))
        if failed:
            return False
        problem = self._runner.start(target, self.import_paths)
        if problem:
            self.errorOccurred.emit(problem)
            return False
        return True

    @Slot()
    def stopRun(self):  # noqa: N802
        self._runner.stop()

    @Slot()
    def closeFolder(self):  # noqa: N802
        self.project_root = ""
        self._project_files, self._project_dirs = [], []
        dirs = self._project_watcher.directories()
        if dirs:
            self._project_watcher.removePaths(dirs)
        self._refresh_project()
        self.projectChanged.emit()

    # ======================================================================= session
    @staticmethod
    def session_file() -> str:
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
        return os.path.join(base, "kreator", "session.json")

    def _session_flags(self) -> tuple[bool, bool]:
        s = self._editor_settings()
        restore = bool(s.get("restoreSession", True))
        return restore, restore and bool(s.get("keepUnsaved", True))

    # without the session (another instance has it) quitting asks as usual
    def set_kate_editor(self, available: bool, problem: str = ""):
        self._kate_editor, self._kate_problem = available, problem

    kateEditorAvailable = Property(bool, lambda self: self._kate_editor, constant=True)
    kateEditorProblem = Property(str, lambda self: self._kate_problem, constant=True)

    keepsUnsaved = Property(bool, lambda self: self._session_flags()[1] and self._session_lock is not None,
                            notify=editorsChanged)
    sessionInterval = Property(int, lambda self: max(0, int(self._editor_settings().get("sessionInterval", 15) or 0))
                               if self._session_flags()[0] and self.ownsSession else 0, notify=editorsChanged)

    @Slot(result=bool)
    def claimSession(self):  # noqa: N802
        """Take the session for this instance. A second Kreator running at the
        same time neither restores nor overwrites it."""
        if self._session_lock is None:
            path = self.session_file()
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
            except OSError:
                return False
            lock = QLockFile(path + ".lock")
            lock.setStaleLockTime(0)  # stale only when its process is gone (e.g. after a crash)
            if not lock.tryLock(0):
                return False
            self._session_lock = lock
            self.editorsChanged.emit()
        return True

    ownsSession = Property(bool, lambda self: self._session_lock is not None, notify=editorsChanged)

    @Slot(str)
    def setPendingSource(self, text):  # noqa: N802
        """Source view edits not applied yet (they may not even parse)."""
        self._pending_source = text or ""

    @Slot(result=str)
    def takePendingSource(self):  # noqa: N802
        return self._restored_pending.pop(self.current_key, "")

    hasPendingSource = Property(bool, lambda self: self.current_key in self._restored_pending, notify=documentChanged)

    @Slot()
    def saveSession(self):  # noqa: N802
        """Remember the open folder and documents for the next start. With
        keepUnsaved, unsaved changes and untitled documents are stored too."""
        if self._session_lock is None:
            return
        keep = self._session_flags()[1]
        states = {st.key: st for st in self._all_states()}
        docs = []
        for key in self.tab_order:
            st = states.get(key)
            if st is None:
                continue
            untitled = key.startswith("untitled:")
            if untitled and not keep:
                continue
            entry = {"key": key, "path": st.path}
            if untitled:
                entry.update(text=st.adapter.text(), template=st.template_name)
            elif keep and st.modified:
                entry.update(text=st.adapter.text(), saved=st.saved_text, disk=st.disk_text)
            if keep and key == self.current_key and self._pending_source \
                    and self._pending_source != st.adapter.text():
                entry["pending"] = self._pending_source
            if self._flow_positions.get(key):
                entry["flowPositions"] = self._flow_positions[key]
            if keep and (st.undo or st.redo):
                cur = st.adapter.text()
                entry["history"] = {"base": session.text_hash(cur), "undo": session.encode_chain(cur, st.undo),
                                    "redo": session.encode_chain(cur, st.redo)}
            docs.append(entry)
        data = {"version": 1, "folder": self.project_root,
                "current": self.current_key if any(d["key"] == self.current_key for d in docs) else "",
                "docs": docs}
        text = json.dumps(data)
        if text == self._session_written:
            return
        path = self.session_file()
        try:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
            self._session_written = text
        except OSError as e:
            self.errorOccurred.emit(f"Could not save the session: {e.strerror}")

    def _session_state(self, d: dict) -> DocState | None:
        key, path, text = str(d.get("key", "")), str(d.get("path", "")), d.get("text")
        try:
            if key.startswith("untitled:"):
                template = str(d.get("template") or "Untitled.qml")
                self._untitled += 1
                return DocState(key=f"untitled:{self._untitled}", adapter=documents.open_document(str(text or ""), template),
                                path="", saved_text="", template_name=template)
            if not path:
                return None
            if isinstance(text, str):
                # unsaved changes; a file changed on disk meanwhile is noticed
                # (and offered for reload) when its tab is shown
                return DocState(key=path, adapter=documents.open_document(text, path), path=path,
                                saved_text=str(d.get("saved", "")), disk_text=str(d.get("disk", "")))
            if not os.path.isfile(path):
                return None
            with open(path, encoding="utf-8") as fh:
                disk = fh.read()
            adapter = documents.open_document(disk, path)
            return DocState(key=path, adapter=adapter, path=path, saved_text=adapter.text(), disk_text=disk)
        except (OSError, UnicodeDecodeError, *PARSE_ERRORS):
            return None  # unreadable now; drop it

    @Slot(result=bool)
    def restoreSession(self):  # noqa: N802
        """Reopen what saveSession() remembered, if enabled. Only the current
        document is loaded into the preview; the others wait as tabs."""
        restore, keep = self._session_flags()
        if not restore or not self.claimSession():
            return False
        try:
            with open(self.session_file(), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return False
        if not isinstance(data, dict):
            return False
        folder = str(data.get("folder") or "")
        if folder and os.path.isdir(folder):
            self.openFolder(folder)
        current_old, current = str(data.get("current") or ""), ""
        order = []
        for d in data.get("docs") or []:
            if not isinstance(d, dict):
                continue
            if not keep:  # stored edits are ignored: files come back as saved
                if str(d.get("key", "")).startswith("untitled:"):
                    continue
                d = {k: v for k, v in d.items() if k not in ("text", "saved", "disk", "pending", "history")}
            st = self._session_state(d)
            if st is None or st.key in self.docs:
                continue
            self.docs[st.key] = st
            order.append(st.key)
            if d.get("key") == current_old:
                current = st.key
            if keep and isinstance(d.get("pending"), str):
                self._restored_pending[st.key] = d["pending"]
            # layout, not an edit: always restored
            pos = _clean_positions(d.get("flowPositions"))
            if pos:
                self._flow_positions[st.key] = pos
            hist = d.get("history")
            if keep and isinstance(hist, dict):
                cur = st.adapter.text()
                # only onto the exact text it was recorded against
                if hist.get("base") == session.text_hash(cur):
                    st.undo = session.decode_chain(cur, hist.get("undo") or [])
                    st.redo = session.decode_chain(cur, hist.get("redo") or [])
        for dname in dict.fromkeys(os.path.dirname(k) for k in order if not k.startswith("untitled:")):
            self.preloader.preload_directory(dname)
        self.tab_order = order
        if order:
            self.switchTo(current or order[0])
        self.documentsChanged.emit()
        self._project_state_changed()
        return bool(folder or order)

    def _rescan_project(self):
        if not self.project_root:
            return
        self._project_files, self._project_dirs = project.scan(self.project_root)
        watched = self._project_watcher.directories()
        if watched:
            self._project_watcher.removePaths(watched)
        dirs = [self.project_root] + [os.path.join(self.project_root, d) for d in self._project_dirs]
        self._project_watcher.addPaths(dirs[:300])
        self._refresh_project()
        self.projectChanged.emit()

    def _refresh_project(self):
        if not self.project_root:
            self._project_model.set_rows([])
            return
        states = {st.key: st for st in self._all_states()}
        if self._project_filter:
            scored = []
            for f in self._project_files:
                sc = project.fuzzy_score(self._project_filter, f)
                if sc:
                    scored.append((-sc, f))
            rows = [{"key": os.path.join(self.project_root, f), "relPath": f, "name": os.path.basename(f), "depth": 0,
                     "isDir": False, "expanded": False, "kind": "ui" if f.lower().endswith(".ui") else "qml"}
                    for _sc, f in sorted(scored)]
        else:
            rows = project.tree_rows(self.project_root, self._project_files, self._project_dirs,
                                     self._project_collapsed)
        for r in rows:
            st = states.get(r["key"])
            r["modified"] = bool(st and st.modified)
            r["current"] = r["key"] == self.current_key
            r["open"] = st is not None
            r["detail"] = os.path.dirname(r["relPath"]) if self._project_filter else ""
        self._project_model.set_rows(rows)

    @Slot(str)
    def toggleProjectDir(self, key):  # noqa: N802
        rel = os.path.relpath(key, self.project_root)
        if rel in self._project_collapsed:
            self._project_collapsed.discard(rel)
        else:
            self._project_collapsed.add(rel)
        self._refresh_project()

    @Slot(str)
    def setProjectFilter(self, text):  # noqa: N802
        self._project_filter = text.strip()
        self._refresh_project()

    @Slot(result=bool)
    def save(self):
        if not self.path:
            return False
        return self._write(self.path)

    @Slot(str, result=bool)
    def saveAs(self, url):  # noqa: N802
        path = QUrl(url).toLocalFile() if url.startswith("file:") else url
        if self.adapter is not None and not os.path.splitext(path)[1]:
            path += ".ui" if self.adapter.kind == "ui" else ".qml"
        if self._write(path):
            old_key = self.current_key
            self.path = os.path.abspath(path)
            self.current_key = self.path
            if old_key in self._flow_positions:
                self._flow_positions[self.path] = self._flow_positions.pop(old_key)
            if old_key in self.tab_order and self.path not in self.tab_order:
                self.tab_order[self.tab_order.index(old_key)] = self.path
            elif old_key in self.tab_order:
                self.tab_order.remove(old_key)
            self.docs.pop(self.path, None)  # an older copy of that file
            self._add_recent(self.path)
            self.documentChanged.emit()
            self.documentsChanged.emit()
            if self.project_root and self.path.startswith(self.project_root + os.sep):
                self._rescan_project()
            return True
        return False

    def _write(self, path):
        if self.adapter is None:
            return False
        text = self.adapter.text()
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as e:
            self.errorOccurred.emit(f"Could not save {path}: {e.strerror}")
            return False
        self.saved_text = text
        self._set_disk(text, path)
        self.stateChanged.emit()
        self.documentsChanged.emit()
        self._project_state_changed()
        self.notify.emit(f"Saved {os.path.basename(path)}")
        return True

    @Slot()
    def reload(self):
        """Read the file again, in place (the tab stays; undo brings back the edits)."""
        if self.path:
            self.reloadFromDisk()

    def _add_recent(self, path):
        rec = [p for p in self._recent() if p != path]
        rec.insert(0, path)
        self.settings.setValue("recentFiles", rec[:10])
        self.recentChanged.emit()

    @Slot()
    def clearRecent(self):  # noqa: N802
        self.settings.setValue("recentFiles", [])
        self.recentChanged.emit()

    @Slot(str, result=str)
    def suggestedFileName(self, _dummy=""):  # noqa: N802
        if self.path:
            return QUrl.fromLocalFile(self.path).toString()
        name = getattr(self, "_template_name", "untitled.qml")
        return QUrl.fromLocalFile(os.path.join(os.getcwd(), name)).toString()

    # ======================================================================= disk & editors
    def _set_disk(self, text, path=None):
        """Remember what is on disk and (re)start watching the current file."""
        self.disk_text = text
        path = path or self.path
        files = self._watcher.files()
        if files:
            self._watcher.removePaths(files)
        if path and os.path.exists(path):
            self._watcher.addPath(path)
        if self._external_change or self._external_error:
            self._external_change = False
            self._external_error = ""
            self.diskChanged.emit()

    def _check_disk(self):
        if not self.path or self.adapter is None:
            return
        if not os.path.exists(self.path):
            # editors often save by writing a new file and renaming it
            if self._disk_retries < 10:
                self._disk_retries += 1
                self._disk_timer.start()
            return
        self._disk_retries = 0

        # Kate's editor settings for the source view; follow changes made in Kate
        self._kate_style = None
        self._katerc_watcher = QFileSystemWatcher(self)
        self._katerc_watcher.addPath(os.path.dirname(katestyle.katerc_path()))
        self._katerc_watcher.directoryChanged.connect(lambda _p: self._kate_timer.start())
        self._katerc_watcher.fileChanged.connect(lambda _p: self._kate_timer.start())
        if os.path.exists(katestyle.katerc_path()):
            self._katerc_watcher.addPath(katestyle.katerc_path())
        self._kate_timer = QTimer(self, singleShot=True, interval=500)
        self._kate_timer.timeout.connect(self._reload_kate_style)
        self.editorsChanged.connect(self.kateStyleChanged)
        if self.path not in self._watcher.files():
            self._watcher.addPath(self.path)
        try:
            with open(self.path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            return
        if text == self.disk_text:
            return
        modified = self.adapter.text() != self.saved_text
        if not modified and self._editor_settings()["autoReload"]:
            self._reload_from_disk(text, quiet=False)
        else:
            self._external_change = True
            self._external_error = ""
            self.diskChanged.emit()

    def _reload_from_disk(self, text, quiet=True):
        try:
            adapter = documents.open_document(text, self.path)
        except PARSE_ERRORS as e:
            # probably saved half-way through an edit; wait for the next save
            self._external_error = f"{os.path.basename(self.path)} was changed on disk but cannot be read: {e}"
            self._external_change = False
            self.disk_text = text
            self.diskChanged.emit()
            return False
        before = self.adapter.text()
        sel = self._preorder_index(self.selected)
        self.undo_stack.append((before, sel))
        self.redo_stack.clear()
        self.adapter = adapter
        self.saved_text = adapter.text()
        self.disk_text = text
        self._external_change = False
        self._external_error = ""
        self.collapsed.clear()
        self.selected = self._uid_at_preorder(sel)
        self._after_change()
        self.selectionChanged.emit()
        self.diskChanged.emit()
        if not quiet:
            self.notify.emit(f"Reloaded {os.path.basename(self.path)}, it was changed in another program")
        return True

    @Slot()
    def reloadFromDisk(self):  # noqa: N802
        """Take the version on disk, dropping unsaved changes (undoable)."""
        try:
            with open(self.path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as e:
            self.errorOccurred.emit(f"Could not read {self.path}: {e.strerror}")
            return
        self._reload_from_disk(text)

    @Slot()
    def keepMyVersion(self):  # noqa: N802
        try:
            with open(self.path, encoding="utf-8") as fh:
                self.disk_text = fh.read()
        except OSError:
            pass
        self._external_change = False
        self._external_error = ""
        self.diskChanged.emit()

    def _disk_position(self):
        """(line, column) of the selected object in the file as it is on disk."""
        if self.adapter is None or not self.selected:
            return 0, 0
        if self.adapter.kind == "qml":
            idx = self._preorder_index(self.selected)
            try:
                disk = qmldoc.parse(self.disk_text)
            except qmldoc.QmlSyntaxError:
                return 0, 0
            for i, (n, *_r) in enumerate(disk.walk()):
                if i == idx:
                    return n.line, n.column
            return 0, 0
        node = self.adapter.doc.find(self.selected)
        if node is None or not node.id:
            return 0, 0
        needle = f'name="{node.id}"'
        for i, ln in enumerate(self.disk_text.split("\n")):
            if needle in ln and re.search(r"<(widget|layout|spacer|action)\b", ln):
                return i + 1, ln.index("<") + 1
        return 0, 0

    @Slot(str, result=bool)
    def openInEditor(self, editor_id):  # noqa: N802
        """Open the (saved) file in an external editor at the selected object."""
        if not self.path:
            self.errorOccurred.emit("Save the document before opening it in another editor.")
            return False
        settings = self._editor_settings()
        editor_id = editor_id or settings["default"]
        line, column = self._disk_position()
        try:
            argv = editors.argv_for(settings, editor_id, self.path, line, column)
        except editors.EditorError as e:
            self.errorOccurred.emit(str(e))
            return False
        result = QProcess.startDetached(argv[0], argv[1:], os.path.dirname(self.path))
        ok = result[0] if isinstance(result, tuple) else bool(result)
        name = next((e["name"] for e in editors.editors(settings) if e["id"] == editor_id), "the editor")
        if not ok:
            self.errorOccurred.emit(f"Could not start {name} ({argv[0]}).")
            return False
        self.notify.emit(f"Opened in {name}" + (f" at line {line}" if line and (
            editor_id != editors.KATE_ID or settings["kate"].get("gotoObject", True)) else ""))
        return True

    @Slot(result=str)
    def editorSettingsJson(self):  # noqa: N802
        return json.dumps(self._editor_settings())

    @Slot(str)
    def setEditorSettingsJson(self, text):  # noqa: N802
        s = editors.assign_ids(editors.load_settings(text))
        self.settings.setValue("externalEditors", json.dumps(s))
        self.settings.sync()
        self.editorsChanged.emit()

    @Slot(result="QVariantList")
    def editorPresets(self):  # noqa: N802
        return editors.PRESETS

    @Slot(result="QVariantList")
    def kateSessions(self):  # noqa: N802
        return editors.kate_sessions()

    @Slot(result=str)
    def kateCommand(self):  # noqa: N802
        k = editors.find_kate()
        return " ".join(k) if k else ""

    @Slot(str, result=str)
    def resolveCommand(self, command):  # noqa: N802
        prog = editors.resolve_program(command)
        return prog[0] if prog else ""

    # ======================================================================= editing core
    def _preorder_index(self, uid):
        if self.adapter is None:
            return 0
        for i, (n, *_r) in enumerate(self.adapter.doc.walk()):
            if n.uid == uid:
                return i
        return 0

    def _uid_at_preorder(self, idx):
        last = 0
        for i, (n, *_r) in enumerate(self.adapter.doc.walk()):
            last = n.uid
            if i == idx:
                return n.uid
        return last

    def _edit(self, fn, *args, select_result=False):
        """Run a mutating adapter call with undo support."""
        if self.adapter is None:
            return None
        before = self.adapter.text()
        sel = self._preorder_index(self.selected)
        try:
            result = fn(*args)
        except (documents.EditError, *PARSE_ERRORS) as e:
            # restore the document in case the call partially mutated it
            if self.adapter.text() != before:
                self.adapter = documents.open_document(before, self.path or "x." + self.adapter.kind)
            self.errorOccurred.emit(str(e))
            return None
        if self.adapter.text() == before:
            return result
        self.undo_stack.append((before, sel))
        if len(self.undo_stack) > 200:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        if select_result and isinstance(result, int):
            self.selected = result
            self._expand_to(result)
        self._after_change()
        self.selectionChanged.emit()
        return result

    def _project_state_changed(self):
        if self.project_root:
            self._refresh_project()

    def _after_change(self, preview_now=False):
        if self.adapter is not None and self.adapter.doc.find(self.selected) is None:
            root = self.adapter.doc.root
            self.selected = root.uid if root is not None else 0
            self.selectionChanged.emit()
        self.issues = self.adapter.lint() if self.adapter else []
        self._refresh_outline()
        self._refresh_palette()
        self._refresh_issues()
        self._refresh_properties()
        self.contentChanged.emit()
        self.stateChanged.emit()
        self._project_state_changed()
        self.documentsChanged.emit()
        if preview_now and self._preview_shown:
            self.refresh_preview()
        else:
            # (hidden behind the source or flow view: made a moment later, so
            # switching tabs isn't held up; it still gives live values)
            self._preview_timer.start()

    def _expand_to(self, uid):
        # make sure all ancestors of uid are expanded
        if self.adapter is None:
            return
        chain = {}
        for n, _d, parent, _l in self.adapter.doc.walk():
            chain[n.uid] = parent.uid if parent is not None else None
        p = chain.get(uid)
        while p:
            self.collapsed.discard(p)
            p = chain.get(p)

    # ======================================================================= models
    def _refresh_outline(self):
        if self.adapter is None:
            self._outline.set_rows([])
            return
        counts = {}
        for i in self.issues:
            counts[i["uid"]] = counts.get(i["uid"], 0) + 1
        rows = []
        hide_depth = None
        for r in self.adapter.outline():
            if hide_depth is not None:
                if r["depth"] > hide_depth:
                    continue
                hide_depth = None
            r = dict(r)
            r["expanded"] = r["uid"] not in self.collapsed
            r["issueCount"] = counts.get(r["uid"], 0)
            if r["hasChildren"] and not r["expanded"]:
                hide_depth = r["depth"]
            rows.append(r)
        self._outline.set_rows(rows)

    def _refresh_properties(self):
        if self.adapter is None or not self.selected:
            self._props.set_rows([])
            return
        live = self._live_object(self.selected)
        try:
            rows = self.adapter.properties(self.selected, live, self.adapter.parent_type(self.selected))
        except RuntimeError:  # live object already deleted
            rows = self.adapter.properties(self.selected, None, self.adapter.parent_type(self.selected))
        if self._preview_mode == "window" and self._is_root():
            for r in rows:
                if r["name"] in preview.WINDOW_PROPS:
                    r["liveValue"] = ""
        f = self.prop_filter.lower()
        rows = [r for r in rows
                if (not f or f in r["name"].lower())
                and (r["section"] != "All properties" or self.show_all_props or f)]
        self._props.set_rows(rows)

    def _refresh_palette(self):
        if self.adapter is None:
            self._palette.set_rows([])
            return
        f = self.palette_filter.lower()
        rows = []
        for i, e in enumerate(self.adapter.palette()):
            if f and f not in e["name"].lower() and f not in e["desc"].lower() and f not in e["cat"].lower():
                continue
            rows.append({"name": e["name"], "category": e["cat"], "iconName": e["icon"],
                         "description": e["desc"], "index": i,
                         "module": e["module"][0] if "module" in e else "Qt Widgets"})
        self._palette.set_rows(rows)

    def _refresh_issues(self):
        labels = {}
        if self.adapter is not None:
            for r in self.adapter.outline():
                labels[r["uid"]] = r["typeName"] + (f" ({r['objectId']})" if r["objectId"] else "")
        rows = []
        for i, iss in enumerate(self.issues):
            rows.append({"index": i, "uid": iss["uid"], "severity": iss["severity"], "title": iss["title"],
                         "detail": iss["detail"], "property": iss.get("property", ""),
                         "fixable": bool(iss.get("fix")), "nodeLabel": labels.get(iss["uid"], "")})
        self._issues.set_rows(rows)

    # ======================================================================= preview
    def _on_qml_warnings(self, warnings):
        added = False
        for w in warnings:
            url = w.url().toString()
            mock_root = self.qml_preview.mocks.root if self.qml_preview.mocks else None
            if ".kreator-preview-" not in url and not (mock_root and mock_root in url):
                continue
            line = w.line()
            where = "" if ".kreator-preview-" in url else os.path.basename(url) + ", "
            msg = where + (f"Line {line}: " if line > 0 else "") + w.description()
            if msg not in self._runtime_warnings and len(self._runtime_warnings) < 6:
                self._runtime_warnings.append(msg)
                added = True
        if added and not self._note_pending:
            # warnings arrive while bindings are being evaluated (often because
            # the warning bar itself changed the layout); report them later
            self._note_pending = True
            QTimer.singleShot(0, self._emit_note)

    def _emit_note(self):
        self._note_pending = False
        self.noteChanged.emit()

    def _set_preview(self, obj, mode, names, error, note):
        old = self._preview_obj
        self._preview_obj = obj
        self._preview_mode = mode
        self._preview_names = names
        self._preview_error = error
        self._preview_note = note
        self._set_live(preview.find_named(obj, names) if obj is not None else {})
        self.previewChanged.emit()
        if old is not None and old is not obj and self._alive(old):
            # QML may still reference the old tree (toolbars, bindings) until the
            # next event loop passes, so hide it now and delete it later.
            if isinstance(old, QQuickItem):
                old.setVisible(False)
            self._graveyard.append(old)
            self.popup_confiner.retire(old)
            QTimer.singleShot(3000, self._bury)

    # Objects can be destroyed by QML or Kirigami behind our back (and PySide
    # does not always notice), so every object we keep is tracked through its
    # destroyed() signal.
    def _track(self, obj):
        key = shiboken6.getCppPointer(obj)[0]
        if key not in self._alive_keys:
            self._alive_keys.add(key)
            obj.destroyed.connect(lambda *_a, k=key: self._alive_keys.discard(k))
        return obj

    def _alive(self, obj) -> bool:
        try:
            return shiboken6.isValid(obj) and shiboken6.getCppPointer(obj)[0] in self._alive_keys
        except Exception:  # noqa: BLE001
            return False

    def _set_live(self, live: dict):
        self._live = {uid: self._track(o) for uid, o in live.items()}
        self._live_missing = {}
        if self._preview_obj is not None:
            self._track(self._preview_obj)

    def _live_object(self, uid):
        """The live object of a document's object in the preview, or None.

        Objects the preview makes after it was created, such as a view's
        delegates (made once the view is laid out), are looked for when asked
        for; the first one found stands for the object."""
        live = self._live.get(uid)
        if live is not None and self._alive(live):
            return live
        name = self._preview_names.get(uid) if self.adapter is not None and self.adapter.kind == "qml" else None
        root = self._preview_obj
        if not name or root is None or not self._alive(root):
            return None
        # (not on every look: it walks the whole preview)
        now = time.monotonic()
        if now - self._live_missing.get(uid, -10.0) < 1.0:
            return None
        found = preview.find_named(root, {uid: name}).get(uid)
        if found is None:
            self._live_missing[uid] = now
            return None
        self._live[uid] = self._track(found)
        return found

    def shutdown(self):
        """Tear down previews before the QML engine goes away."""
        self._runner.stop(wait=True)    # what Kreator started ends with it
        if self._session_lock is not None:
            self._session_lock.unlock()
        self._preview_timer.stop()
        try:
            self.engine.warnings.disconnect(self._on_qml_warnings)
        except (RuntimeError, TypeError):
            pass
        self.clearComponentPreview()
        objs = [self._preview_obj, *self._graveyard]
        self._preview_obj = None
        self._graveyard = []
        self._live = {}
        for o in objs:
            if o is not None and self._alive(o):
                if isinstance(o, QQuickItem):
                    o.setParentItem(None)
                shiboken6.delete(o)
        if self.ui_preview.widget is not None:
            shiboken6.delete(self.ui_preview.widget)
            self.ui_preview.widget = None
        if self.qml_preview.mocks is not None:
            self.qml_preview.mocks.cleanup()

    def _bury(self):
        if not self._graveyard:
            return
        old = self._graveyard.pop(0)
        if not self._alive(old):
            return
        if isinstance(old, QQuickItem):
            old.setParentItem(None)
        old.deleteLater()

    @Slot()
    def refresh_preview(self):
        if self.adapter is None:
            return
        self._runtime_warnings = []
        if self.adapter.kind == "qml":
            obj, mode, names, msg = self.qml_preview.create(self.adapter.doc, self.path)
            if obj is None:
                # keep the last good preview visible, but report the error
                self._preview_error = msg
                self._preview_note = ""
                self.previewChanged.emit()
            else:
                self._set_preview(obj, mode, names, "", msg)
        else:
            ok, msg = self.ui_preview.render(self.adapter.text(), self.path)
            names = {n.uid: n.id for n, *_ in self.adapter.doc.walk() if n.id}
            if ok:
                self._ui_counter += 1
                s = self.ui_preview.size()
                self._ui_size = (s.width(), s.height())
                self._preview_names = names
                live = {}
                for uid, name in names.items():
                    o = self.ui_preview.find(name)
                    if o is not None:
                        live[uid] = o
                self._set_live(live)
                self._preview_mode = "ui"
                self._preview_error = ""
                self._preview_note = msg
            else:
                self._preview_error = msg
            self.previewChanged.emit()
        self._refresh_properties()

    @Slot(QObject)
    def confinePopups(self, layer):  # noqa: N802
        """Popups of the preview are shown in `layer` (see PopupConfiner)."""
        self.popup_confiner.set_layer(layer)

    @Slot(int, result="QVariantList")
    def previewItemFor(self, uid):  # noqa: N802
        """[item] or [] — PySide 6.12 crashes when a QObject* slot returns None."""
        it = self._preview_item(uid)
        return [it] if it is not None else []

    def _preview_item(self, uid):
        o = self._live.get(uid)
        if o is not None and not self._alive(o):
            return None
        try:
            if isinstance(o, QQuickItem):
                return o
            if o is not None and o.metaObject().indexOfProperty("contentItem") >= 0:
                ci = o.property("contentItem")
                if isinstance(ci, QQuickItem):
                    return ci.parentItem() or ci
        except RuntimeError:
            return None
        return None

    @Slot(QObject, float, float)
    def pickAt(self, host, x, y):  # noqa: N802
        uid = self._pick_uid(host, x, y)
        if uid:
            self.select(uid)

    def _pick_uid(self, host, x, y):
        if self._preview_obj is None or not self._alive(self._preview_obj) or not isinstance(host, QQuickItem):
            return 0
        roots = []
        o = self._preview_obj
        if isinstance(o, QQuickItem):
            roots.append(o)
        else:
            it = self._preview_item(next((u for u, v in self._live.items() if v is o), -1))
            if it is not None:
                roots.append(it)
        name_to_uid = {v: k for k, v in self._preview_names.items()}
        return preview.pick_item(host, roots, x, y, name_to_uid)

    def _pick_stack(self, host, x, y):
        """The document objects under (x, y), topmost first."""
        if self.adapter is None:
            return []
        if self.adapter.kind != "qml":
            names = {v: k for k, v in self._preview_names.items()}
            return [names[n] for n in self.ui_preview.pick_stack(int(x), int(y), set(names))]
        if self._preview_obj is None or not self._alive(self._preview_obj) or not isinstance(host, QQuickItem):
            return []
        o = self._preview_obj
        roots = [o] if isinstance(o, QQuickItem) else []
        if not roots:
            it = self._preview_item(next((u for u, v in self._live.items() if v is o), -1))
            if it is not None:
                roots.append(it)
        name_to_uid = {v: k for k, v in self._preview_names.items()}
        return preview.pick_stack(host, roots, x, y, name_to_uid)

    def _inside(self, uid, ancestor):
        """Whether `uid` is `ancestor` or one of its descendants."""
        chain = {n.uid: (p.uid if p is not None else None) for n, _d, p, _l in self.adapter.doc.walk()}
        while uid:
            if uid == ancestor:
                return True
            uid = chain.get(uid)
        return False

    @Slot(QObject, float, float, bool, result=bool)
    def pressAt(self, host, x, y, below):  # noqa: N802
        """A press on the design view at (x, y). Selects the topmost object
        there, except: with `below` (Alt), the next object under the selected
        one (going round); and when the selected object is there but covered by
        an unrelated one, it stays selected so it can be dragged — returns true
        then, and a click without dragging selects the topmost (pickAt)."""
        self._fresh_preview()
        stack = self._pick_stack(host, x, y)
        if not stack:
            return False
        if below:
            i = stack.index(self.selected) + 1 if self.selected in stack else 0
            self.select(stack[i % len(stack)])
            return False
        if self.selected in stack and not self._inside(stack[0], self.selected):
            return True
        self.select(stack[0])
        return False

    @Slot(float, float)
    def pickUi(self, x, y):  # noqa: N802
        uid = self._pick_ui(x, y)
        if uid:
            self.select(uid)

    def _pick_ui(self, x, y):
        names = {v: k for k, v in self._preview_names.items()}
        name = self.ui_preview.pick(int(x), int(y), set(names))
        return names.get(name, 0)

    @Slot(int, result="QVariantList")
    def uiRect(self, uid):  # noqa: N802
        name = self._preview_names.get(uid, "")
        r = self.ui_preview.rect_of(name)
        if r.isNull() or r.isEmpty():
            return []
        return [r.x(), r.y(), r.width(), r.height()]

    # ======================================================================= selection & outline
    @Slot(int)
    def select(self, uid):
        if uid == self.selected:
            return
        self.selected = uid
        self._expand_to(uid)
        self._refresh_outline()
        self._refresh_properties()
        self.selectionChanged.emit()

    @Slot(int)
    def toggleExpanded(self, uid):  # noqa: N802
        if uid in self.collapsed:
            self.collapsed.discard(uid)
        else:
            self.collapsed.add(uid)
        self._refresh_outline()

    @Slot(result=int)
    def selectedRow(self):  # noqa: N802
        for i, r in enumerate(self._outline.rows()):
            if r["uid"] == self.selected:
                return i
        return -1

    @Slot(int)
    def selectRow(self, row):  # noqa: N802
        r = self._outline.row(row)
        if r:
            self.select(r["uid"])

    # ======================================================================= property editing
    @Slot(str, str, str)
    def setProperty(self, name, kind, value):  # noqa: N802
        if self.adapter is None or not self.selected:
            return
        self._edit(self.adapter.set_property, self.selected, name, kind, value)

    @Slot(str)
    def removeProperty(self, name):  # noqa: N802
        if self.adapter is None or not self.selected:
            return
        self._edit(self.adapter.remove_property, self.selected, name)

    @Slot(str)
    def setSelectedId(self, value):  # noqa: N802
        if self.adapter is None or not self.selected:
            return
        if value.strip() == self.selectedId:
            return
        self._edit(self.adapter.set_id, self.selected, value)

    @Slot(str)
    def setSelectedType(self, value):  # noqa: N802
        if self.adapter is None or not self.selected or value.strip() == self.selectedType:
            return
        self._edit(self.adapter.set_type, self.selected, value)

    @Slot(str)
    def setPropertyFilter(self, text):  # noqa: N802
        self.prop_filter = text
        self._refresh_properties()

    @Slot(bool)
    def setShowAllProperties(self, show):  # noqa: N802
        self.show_all_props = show
        self._refresh_properties()

    # ======================================================================= structure editing
    @Slot(str)
    def setPaletteFilter(self, text):  # noqa: N802
        self.palette_filter = text
        self._refresh_palette()

    @Slot(int, QQuickItem, result="QVariantMap")
    def componentPreview(self, index, stage):  # noqa: N802
        """What palette entry `index` looks like, for the Add tab to show
        before the component is added:
          {kind: "item", item}    the live component, made as a child of `stage`
          {kind: "image", source, width, height}    a picture of the widget
          {kind: "none"}          it draws nothing
        each with a `note` to show below ("" for none). The item lives until
        the next call, or clearComponentPreview()."""
        self.clearComponentPreview()
        if self.adapter is None or not 0 <= index < len(self.adapter.palette()):
            return {"kind": "none", "note": ""}
        entry = self.adapter.palette()[index]
        out = {"kind": "none", "note": palette.preview_note(entry)}
        if self.adapter.kind != "qml":
            try:
                drawn = self.ui_preview.demo_image(entry)
            except Exception:  # noqa: BLE001 - only a preview
                drawn = None
            if drawn is None:
                out["note"] = out["note"] or "Draws nothing itself: it holds other widgets"
                return out
            self._palette_images.image, width, height = drawn
            self._palette_serial += 1
            out.update(kind="image", source=f"image://kreatorpalette/{self._palette_serial}",
                       width=width, height=height)
            return out
        text = palette.preview_qml(entry)
        if not text or stage is None:
            return out
        try:
            item = self.qml_preview.demo_item(entry["name"], text, stage)
        except Exception:  # noqa: BLE001 - only a preview
            item = None
        if item is None:
            out["note"] = "No preview: the component could not be created here"
            return out
        self._palette_item = self._track(item)
        out.update(kind="item", item=item)
        return out

    @Slot()
    def clearComponentPreview(self):  # noqa: N802
        item, self._palette_item = self._palette_item, None
        if item is not None and self._alive(item):
            item.setVisible(False)
            item.setParentItem(None)
            item.deleteLater()

    @Slot(int)
    def insertComponent(self, index):  # noqa: N802
        """Add a palette component to the selected object: to its contents,
        or into the property chosen as `insertSlot`."""
        if self.adapter is None:
            return
        entry = self.adapter.palette()[index]
        slot = self._insert_slot if self.adapter.kind == "qml" else ""
        if slot:
            is_list = any(s["name"] == slot and s["isList"] for s in self._slots())
            self._edit(self.adapter.insert, self.selected, entry, slot, is_list, select_result=True)
            return
        self._edit(self.adapter.insert, self.selected, entry, select_result=True)

    # -- the properties of the selected object that hold objects (a page's
    # header, a control's contentItem, a view's delegate…): the Add tab can put
    # a component into one of them instead of among the object's children
    def _slots(self) -> list[dict]:
        if self.adapter is None or self.adapter.kind != "qml" or not self.selected:
            return []
        live = self._live_object(self.selected)
        try:
            return self.adapter.slots(self.selected, live)
        except RuntimeError:  # live object already deleted
            return self.adapter.slots(self.selected, None)

    def _set_insert_slot(self, name):
        name = name or ""
        if name and not any(s["name"] == name for s in self._slots()):
            name = ""
        if name != self._insert_slot:
            self._insert_slot = name
            self.insertSlotsChanged.emit()

    def _reset_insert_slot(self):
        self._insert_slot = ""

    insertSlots = Property("QVariantList", _slots, notify=insertSlotsChanged)
    insertSlot = Property(str, lambda self: self._insert_slot, _set_insert_slot, notify=insertSlotsChanged)

    # -- placing objects on the design grid ---------------------------------------
    # Positions come from the design view in its own coordinates (those of the
    # preview's top-left corner, already snapped to the grid there); they are
    # written relative to the object's parent. `step` and `unit` name the grid
    # (a Kirigami unit and its size in pixels): QML positions on the grid are
    # written in that unit, e.g. "Kirigami.Units.largeSpacing * 3".
    _POSITIONING_ITEMS = ("QQuickLayout", "QQuickBasePositioner")

    def _content_item(self, uid):
        """The item a QML object's declared children are parented to."""
        it = self._preview_item(uid)
        if it is None:
            return None
        for node, _d, parent, _l in self.adapter.doc.walk():
            if parent is not None and parent.uid == uid:
                child = self._preview_item(node.uid)
                if child is not None and child is not it and child.parentItem() is not None:
                    return child.parentItem()
        mo = it.metaObject()
        i = mo.indexOfClassInfo("DefaultProperty")
        default = mo.classInfo(i).value() if i >= 0 else "data"
        if default != "data" and mo.indexOfProperty("contentItem") >= 0:
            ci = it.property("contentItem")
            if isinstance(ci, QQuickItem):
                return ci
        return it

    def _positions_children(self, item) -> bool:
        """Whether an item places its children itself (layouts, Row, Column…)."""
        mo = item.metaObject() if item is not None else None
        while mo is not None:
            if mo.className() in self._POSITIONING_ITEMS:
                return True
            mo = mo.superClass()
        return False

    def _placement_problem(self, uid) -> str:
        if self.adapter is None or not uid:
            return "nothing is selected"
        try:
            problem = self.adapter.placement_problem(uid)
        except documents.EditError as e:
            return str(e)
        if problem or self.adapter.kind != "qml":
            return problem
        it = self._preview_item(uid)
        if it is None:
            return "it isn't shown in the preview"
        if self._positions_children(it.parentItem()):
            return "its parent places it (a layout)"
        return ""

    def _size_problem(self, uid) -> str:
        if self.adapter is None or not uid:
            return "nothing is selected"
        try:
            problem = self.adapter.size_problem(uid)
        except documents.EditError as e:
            return str(e)
        if problem or self.adapter.kind != "qml":
            return problem
        it = self._preview_item(uid)
        if it is None:
            return "it isn't shown in the preview"
        mo = it.parentItem().metaObject() if it.parentItem() is not None else None
        while mo is not None:
            if mo.className() == "QQuickLayout":
                return "its layout sizes it (use its Layout properties)"
            mo = mo.superClass()
        return ""

    @Slot(QObject, int, result="QVariantList")
    def guideRects(self, host, uid):  # noqa: N802
        """Rectangles ([x, y, w, h] in the design view) an object being moved or
        resized can be aligned with: its parent and its parent's other
        visible children."""
        if self.adapter is None or not uid:
            return []
        if self.adapter.kind == "qml":
            it = self._preview_item(uid)
            parent = it.parentItem() if it is not None else None
            return self._rects_of(host, parent, [parent], skip=it)
        w = self.ui_preview.find(self._preview_names.get(uid, ""))
        parent = w.parentWidget() if w is not None else None
        return self._rects_of(host, parent, [parent], skip=w)

    @Slot(QObject, int, result="QVariantList")
    def containerRects(self, host, uid):  # noqa: N802
        """Rectangles a component dropped into the container `uid` (as
        dropTarget() names it) can be aligned with: the container and its
        visible children."""
        if self.adapter is None or not uid:
            return []
        if self.adapter.kind == "qml":
            content = self._content_item(uid)
            own = self._preview_item(uid)
            return self._rects_of(host, content, [own, content])
        w = self.ui_preview.find(self._preview_names.get(uid, ""))
        return self._rects_of(host, w, [w])

    def _rects_of(self, host, parent, own, skip=None):
        """[x, y, w, h] in the design view of the objects in `own` and of the
        document's visible objects among `parent`'s children (but `skip`)."""
        out, seen = [], set()
        if parent is None:
            return out
        names = set(self._preview_names.values())
        if self.adapter.kind == "qml":
            if not isinstance(host, QQuickItem):
                return out
            for o in [*own, *parent.childItems()]:
                if o is None or o is skip or not o.isVisible() or o.width() <= 0 or o.height() <= 0:
                    continue
                if o not in own and o.objectName() not in names:
                    continue
                p = o.mapToItem(host, QPointF(0, 0))
                r = (p.x(), p.y(), o.width(), o.height())
                if r not in seen:
                    seen.add(r)
                    out.append(list(r))
            return out
        for o in [*own, *parent.children()]:
            if o is None or o is skip or not hasattr(o, "isVisibleTo") or o.objectName() not in names:
                continue
            r = self.ui_preview.rect_of(o.objectName())
            if not r.isNull() and not r.isEmpty() and (r.x(), r.y(), r.width(), r.height()) not in seen:
                seen.add((r.x(), r.y(), r.width(), r.height()))
                out.append([r.x(), r.y(), r.width(), r.height()])
        return out

    @Slot(int, result=str)
    def resizeProblem(self, uid):  # noqa: N802
        """Why the object can't be resized in the design view ("" if it can)."""
        return self._size_problem(uid)

    @Slot(QObject, int, float, float, float, float, float, str, bool, result=bool)
    def resizeTo(self, host, uid, x, y, w, h, step, unit, move):  # noqa: N802
        """Give an object the rectangle (x, y, w, h) of the design view; with
        `move` false only its size changes (its right or bottom edge moved)."""
        self._fresh_preview()
        problem = self._size_problem(uid) or (self._placement_problem(uid) if move else "")
        if problem:
            self.errorOccurred.emit(f"This object can't be resized: {problem}.")
            return False
        if self.adapter.kind == "qml":
            rel = self._relative(host, self._preview_item(uid).parentItem(), x, y) if move else (0, 0)
            if rel is None:
                return False
            return self._placed(self._edit(self.adapter.set_geometry, uid, rel[0], rel[1], w, h, step, unit, move))
        wdg = self.ui_preview.find(self._preview_names.get(uid, ""))
        if wdg is None or wdg.parentWidget() is None:
            return False
        parent_uid = next((u for u, n in self._preview_names.items() if n == wdg.parentWidget().objectName()), None)
        rel = self._relative(host, parent_uid, x, y) if parent_uid else None
        if rel is None:
            return False
        return self._placed(self._edit(self.adapter.set_geometry, uid, rel[0], rel[1], w, h))

    @Slot(int, result=str)
    def placementProblem(self, uid):  # noqa: N802
        """Why the object can't be moved in the design view ("" if it can)."""
        return self._placement_problem(uid)

    def _relative(self, host, uid_or_item, x, y):
        """(x, y) of the design view relative to an object's parent."""
        if self.adapter.kind == "qml":
            parent = uid_or_item
            if not isinstance(parent, QQuickItem) or not isinstance(host, QQuickItem):
                return None
            p = parent.mapFromItem(host, QPointF(x, y))
            return p.x(), p.y()
        w = self.ui_preview.find(self._preview_names.get(uid_or_item, ""))
        root = self.ui_preview.widget
        if w is None or root is None:
            return None
        p = w.mapFrom(root, QPoint(round(x), round(y))) if w is not root else QPoint(round(x), round(y))
        return float(p.x()), float(p.y())

    @Slot(QObject, int, float, float, float, str, result=bool)
    def placeAt(self, host, uid, x, y, step, unit):  # noqa: N802
        """Move an object so that its top-left corner is at (x, y)."""
        self._fresh_preview()
        problem = self._placement_problem(uid)
        if problem:
            self.errorOccurred.emit(f"This object can't be moved: {problem}.")
            return False
        if self.adapter.kind == "qml":
            rel = self._relative(host, self._preview_item(uid).parentItem(), x, y)
            if rel is None:
                return False
            return self._placed(self._edit(self.adapter.set_position, uid, rel[0], rel[1], step, unit))
        w = self.ui_preview.find(self._preview_names.get(uid, ""))
        if w is None or w.parentWidget() is None:
            return False
        parent_uid = next((u for u, n in self._preview_names.items() if n == w.parentWidget().objectName()), None)
        rel = self._relative(host, parent_uid, x, y) if parent_uid else None
        if rel is None:
            return False
        return self._placed(self._edit(self.adapter.set_geometry, uid, rel[0], rel[1], w.width(), w.height()))

    def _fresh_preview(self):
        """Before hit-testing or measuring the preview: rebuild it if it is
        due (after undo or a source edit the document's objects were made
        anew, and the shown preview still maps the old ones)."""
        if self._preview_shown and self._preview_timer.isActive():
            self._preview_timer.stop()
            self.refresh_preview()

    def _placed(self, result) -> bool:
        """After moving or adding an object in the design view: show it there
        now (the next move starts from where the preview shows it)."""
        if result and self._preview_shown and self._preview_timer.isActive():
            self._preview_timer.stop()
            self.refresh_preview()
        return bool(result)

    def _drop_container(self, host, x, y, container=0):
        """(container uid, its content item or None, free placement?) for a
        component dropped at (x, y), or into `container` (a uid that
        dropTarget() returned)."""
        if container and self.adapter.doc.find(container) is not None:
            if self.adapter.kind == "qml":
                item = self._content_item(container)
                return container, item, item is not None and not self._positions_children(item)
            return container, None, self.adapter.free_container(container) == container
        if self.adapter.kind == "qml":
            picked = self._pick_uid(host, x, y) or (self.adapter.doc.root.uid if self.adapter.doc.root else 0)
            uid = self.adapter.container_for(picked)
            item = self._content_item(uid)
            return uid, item, item is not None and not self._positions_children(item)
        picked = self._pick_ui(x, y)
        free = self.adapter.free_container(picked)
        if free is not None:
            return free, None, True
        return picked or (self.adapter.doc.root.uid if self.adapter.doc.root else 0), None, False

    @Slot(QObject, float, float, result="QVariantMap")
    def dropTarget(self, host, x, y):  # noqa: N802
        """Where a component dropped at (x, y) goes: {label, free, rect: [x, y, w, h]}."""
        self._fresh_preview()
        if self.adapter is None:
            return {}
        uid, _item, free = self._drop_container(host, x, y)
        node = self.adapter.doc.find(uid)
        if node is None:
            return {}
        label = node.id or (node.type_name.split(".")[-1] if self.adapter.kind == "qml" else node.el.get("class", ""))
        rect = []
        if self.adapter.kind == "qml":
            it = self._preview_item(uid)
            if it is not None and isinstance(host, QQuickItem):
                p = it.mapToItem(host, QPointF(0, 0))
                rect = [p.x(), p.y(), it.width(), it.height()]
        else:
            r = self.ui_preview.rect_of(self._preview_names.get(uid, ""))
            if not r.isNull():
                rect = [r.x(), r.y(), r.width(), r.height()]
        return {"uid": uid, "label": label, "free": free, "rect": rect}

    @Slot(int, int, result="QVariantList")
    def componentSize(self, index, container):  # noqa: N802
        """[w, h]: the size palette entry `index` will likely get when placed
        freely in the container `container` (as dropTarget() names it); [0, 0]
        if unknown or not visual."""
        if self.adapter is None or not 0 <= index < len(self.adapter.palette()):
            return [0, 0]
        entry = self.adapter.palette()[index]
        if entry.get("slot") or not entry.get("visual", True):
            return [0, 0]
        if self.adapter.kind != "qml":
            if entry.get("type") == "Spacer" or entry.get("type") in uidoc.LAYOUT_CLASSES:
                return [0, 0]
            return list(self.ui_preview.size_hint(entry))
        item = self._content_item(container) if container else None
        cw = round(item.width()) if item is not None and item.width() > 0 else 400
        ch = round(item.height()) if item is not None and item.height() > 0 else 300
        key = (index, cw, ch)
        cache = self.__dict__.setdefault("_component_sizes", {})
        if key not in cache:
            try:
                cache[key] = list(self.qml_preview.component_size(palette.standalone(entry["qml"]),
                                                                  palette.STANDALONE_IMPORTS, cw, ch))
            except Exception:  # noqa: BLE001 - only a preview of the size
                cache[key] = [0, 0]
            # anchored to its parent (its position isn't the drop point), or
            # sized by a layout: no size to show
            if "anchors." in entry["qml"] or min(cache[key]) <= 0:
                cache[key] = [0, 0]
        return cache[key]

    @Slot(QObject, int, float, float, float, str)
    def insertComponentAt(self, host, index, x, y, step, unit):  # noqa: N802
        """Add a palette component where it was dropped: at (x, y) when its
        parent lets objects be placed freely, else as with insertComponent."""
        self.insertComponentInto(host, index, 0, x, y, step, unit)

    @Slot(QObject, int, int, float, float, float, str)
    def insertComponentInto(self, host, index, container, x, y, step, unit):  # noqa: N802
        """insertComponentAt() into the container dropTarget() named (0: the
        one at (x, y)): a point aligned with an edge may lie on a neighbour."""
        self.insertComponentSized(host, index, container, x, y, 0, 0, step, unit)

    @Slot(QObject, int, int, float, float, float, float, float, str)
    def insertComponentSized(self, host, index, container, x, y, w, h, step, unit):  # noqa: N802
        """insertComponentInto(), giving it a width and / or height (> 0), as
        when the design view fitted it between its neighbours."""
        if self.adapter is None:
            return
        if not container:
            self._fresh_preview()
        entry = self.adapter.palette()[index]
        uid, item, free = self._drop_container(host, x, y, container)
        widget = self.adapter.kind == "qml" or (entry.get("type") != "Spacer"
                                                 and entry.get("type") not in uidoc.LAYOUT_CLASSES)
        if not free or entry.get("slot") or not widget or not entry.get("visual", True):
            self._edit(self.adapter.insert, uid, entry, select_result=True)
            return
        if self.adapter.kind == "qml":
            rel = self._relative(host, item, x, y)

            def run():
                new = self.adapter.insert(uid, entry)
                if rel is not None and not self.adapter.placement_problem(new):
                    self.adapter.set_position(new, rel[0], rel[1], step, unit)
                    if (w > 0 or h > 0) and not self.adapter.size_problem(new):
                        node = self.adapter.node(new)
                        if w > 0:
                            node.set_binding("width", self.adapter.position_value(w, step, unit))
                        if h > 0:
                            node.set_binding("height", self.adapter.position_value(h, step, unit))
                return new
            self._placed(self._edit(run, select_result=True))
            return
        rel = self._relative(host, uid, x, y)
        hint_w, hint_h = self.ui_preview.size_hint(entry)
        self._placed(self._edit(self.adapter.insert_free, uid, entry, rel[0] if rel else x, rel[1] if rel else y,
                                w if w > 0 else hint_w, h if h > 0 else hint_h, select_result=True))

    @Slot()
    def deleteSelected(self):  # noqa: N802
        if self.adapter is None or not self.selected:
            return
        if self._is_root():
            self.errorOccurred.emit("The root object cannot be deleted.")
            return
        self._edit(self.adapter.delete, self.selected, select_result=True)

    @Slot(int)
    def moveSelected(self, delta):  # noqa: N802
        if self.adapter is None or not self.selected:
            return
        self._edit(self.adapter.move, self.selected, delta)

    @Slot()
    def duplicateSelected(self):  # noqa: N802
        if self.adapter is None or not self.selected:
            return
        self._edit(self.adapter.duplicate, self.selected, select_result=True)

    @Slot()
    def copySelected(self):  # noqa: N802
        if self.adapter is None or not self.selected:
            return
        QGuiApplication.clipboard().setText(self.adapter.copy_text(self.selected))
        self.notify.emit("Copied to clipboard")

    @Slot()
    def cutSelected(self):  # noqa: N802
        if self.adapter is None or not self.selected or self._is_root():
            return
        QGuiApplication.clipboard().setText(self.adapter.copy_text(self.selected))
        self.deleteSelected()

    @Slot()
    def paste(self):
        if self.adapter is None:
            return
        text = QGuiApplication.clipboard().text()
        if not text.strip():
            self.errorOccurred.emit("The clipboard is empty.")
            return
        self._edit(self.adapter.paste, self.selected, text, select_result=True)

    # ======================================================================= guidelines
    @Slot(int)
    def applyFix(self, index):  # noqa: N802
        if self.adapter is None or not 0 <= index < len(self.issues):
            return
        issue = self.issues[index]

        def run():
            if not self.adapter.apply_fix(issue):
                raise documents.EditError("this issue cannot be fixed automatically")

        self._edit(run)

    @Slot()
    def applyAllFixes(self):  # noqa: N802
        if self.adapter is None:
            return

        def run():
            for _ in range(5):  # fixes may reveal / invalidate others
                fixable = [i for i in self.adapter.lint() if i.get("fix")]
                if not fixable:
                    break
                changed = False
                for iss in fixable:
                    changed |= bool(self.adapter.apply_fix(iss))
                if not changed:
                    break

        self._edit(run)

    # ======================================================================= undo / source
    def _restore(self, text, sel_index):
        self.adapter = documents.open_document(text, self.path or ("x.ui" if self.adapter.kind == "ui" else "x.qml"))
        self.collapsed.clear()
        self.selected = self._uid_at_preorder(sel_index)
        self._after_change()
        self.selectionChanged.emit()

    @Slot()
    def undo(self):
        if not self.undo_stack or self.adapter is None:
            return
        text, sel = self.undo_stack.pop()
        self.redo_stack.append((self.adapter.text(), self._preorder_index(self.selected)))
        self._restore(text, sel)

    @Slot()
    def redo(self):
        if not self.redo_stack or self.adapter is None:
            return
        text, sel = self.redo_stack.pop()
        self.undo_stack.append((self.adapter.text(), self._preorder_index(self.selected)))
        self._restore(text, sel)

    @Slot(str, result=bool)
    def applySource(self, text):  # noqa: N802
        if self.adapter is None:
            return False
        try:
            adapter = documents.open_document(text, self.path or ("x.ui" if self.adapter.kind == "ui" else "x.qml"))
        except PARSE_ERRORS as e:
            self._source_error = str(e)
            self.contentChanged.emit()
            return False
        if adapter.kind != self.adapter.kind:
            self._source_error = "The source must stay the same kind of document."
            self.contentChanged.emit()
            return False
        before = self.adapter.text()
        sel = self._preorder_index(self.selected)
        self._source_error = ""
        if adapter.text() == before:
            self.contentChanged.emit()
            return True
        self.undo_stack.append((before, sel))
        self.redo_stack.clear()
        self.adapter = adapter
        self.selected = self._uid_at_preorder(sel)
        self._after_change()
        self.selectionChanged.emit()
        return True

    def apply_text_fix(self, path, basis, edits):
        """Apply quick-fix edits (LSP positions into `basis`) to a document as an
        unsaved, undoable change. A file that isn't open is opened as a
        background tab first, so nothing is written until it is saved.
        Returns the new text, or None (with a message) if it can't be done."""
        from .lsp import apply_edits
        key = os.path.abspath(path)
        name = os.path.basename(key)
        if self.adapter is not None and key == self.path:
            if self.adapter.text() != basis:
                self.errorOccurred.emit(f"{name} has changed since it was checked; try again in a moment.")
                return None
            new = apply_edits(basis, edits)
            if not self.applySource(new):
                self.errorOccurred.emit(f"The fix would break {name}: {self._source_error}")
                return None
            return self.adapter.text()
        st = self.docs.get(key)
        if st is None:
            try:
                with open(key, encoding="utf-8") as fh:
                    disk = fh.read()
                adapter = documents.open_document(disk, key)
            except (OSError, UnicodeDecodeError, *PARSE_ERRORS) as e:
                self.errorOccurred.emit(f"Could not open {name}: {e}")
                return None
            st = DocState(key=key, adapter=adapter, path=key, saved_text=adapter.text(), disk_text=disk)
            fresh = True
        else:
            fresh = False
        before = st.adapter.text()
        if before != basis:
            self.errorOccurred.emit(f"{name} has changed since it was checked; try again in a moment.")
            return None
        try:
            adapter = documents.open_document(apply_edits(before, edits), key)
        except PARSE_ERRORS as e:
            self.errorOccurred.emit(f"The fix would break {name}: {e}")
            return None
        if fresh:
            self.docs[key] = st
            if key not in self.tab_order:
                self.tab_order.append(key)
        st.undo.append((before, 0))
        st.redo.clear()
        st.adapter = adapter
        self.documentsChanged.emit()
        self.stateChanged.emit()
        self._project_state_changed()
        return adapter.text()

    @Slot(str, result="QVariantMap")
    def typeDescription(self, word):  # noqa: N802
        """The members of a QML type implemented in C++, as named in the current
        document (e.g. "Rectangle", "Kirigami.Icon"), from its .qmltypes; {} if
        unknown or written in QML (go to definition opens those)."""
        if self.adapter is None or self.adapter.kind != "qml" or not word:
            return {}
        near = os.path.dirname(self.path) if self.path else self.project_root
        try:
            return self._types.describe(word, self.adapter.doc.imports(), near)
        except Exception:  # noqa: BLE001 - a broken .qmltypes must not break the editor
            return {}

    @Slot("QVariantList", int, bool, result="QVariantMap")
    def signalFlow(self, kinds, focus_uid, show_all):  # noqa: N802
        """The current document's signal flow (see signalflow.py): the edges
        of these kinds ("signal", "binding", "layout"), only those of one
        object if focus_uid is set, placed in layers; show_all: the objects
        without edges too (a form's widgets, to connect them)."""
        if self.adapter is None:
            return {"nodes": [], "edges": [], "counts": {}}
        text = self.adapter.text()
        key = (id(self.adapter), text)
        if getattr(self, "_flow_key", None) != key:
            try:
                if self.adapter.kind == "qml":
                    self._flow_graph = signalflow.qml_flow(self.adapter.doc, text)
                else:
                    self._flow_graph = signalflow.ui_flow(self.adapter.doc, text)
            except Exception as e:  # noqa: BLE001 - the view must not take the editor down
                print(f"kreator: signal flow: {e!r}")
                self._flow_graph = signalflow._Graph()
            self._flow_key = key
        return signalflow.layout(self._flow_graph, set(kinds or []), focus_uid, show_all)

    @Slot(result="QVariantMap")
    def flowPositions(self):  # noqa: N802
        """The current document's objects moved by hand in the signal flow
        view: {stable key: [x, y]} (kept in the session)."""
        return dict(self._flow_positions.get(self.current_key, {}))

    @Slot("QVariantMap")
    def setFlowPositions(self, positions):  # noqa: N802
        clean = _clean_positions(positions)
        if clean:
            self._flow_positions[self.current_key] = clean
        else:
            self._flow_positions.pop(self.current_key, None)

    # ---------------------------------------------------------------- a form's connections
    def _ui_doc(self):
        return self.adapter.doc if self.adapter is not None and self.adapter.kind == "ui" else None

    @Slot(result="QVariantList")
    def uiConnectables(self):  # noqa: N802
        """[{name, type}] of the form's widgets and actions."""
        doc = self._ui_doc()
        return [{"name": n, "type": c} for n, c in doc.connectables()] if doc else []

    def _ui_class(self, name):
        doc = self._ui_doc()
        return next((c for n, c in doc.connectables() if n == name), "") if doc else ""

    @Slot(str, result="QVariantList")
    def uiSignals(self, name):  # noqa: N802
        doc = self._ui_doc()
        cls = self._ui_class(name)
        return signalflow.class_members(doc, cls)["signals"] if cls else []

    @Slot(str, str, result="QVariantList")
    def uiSlots(self, name, signal):  # noqa: N802
        """The slots of a widget that can take this signal (all if no signal)."""
        doc = self._ui_doc()
        cls = self._ui_class(name)
        if not cls:
            return []
        slots = signalflow.class_members(doc, cls)["slots"]
        return [s for s in slots if not signal or signalflow.compatible(signal, s)]

    @Slot(str, str, str, str, result=bool)
    def addConnection(self, sender, signal, receiver, slot):  # noqa: N802
        if self._ui_doc() is None:
            return False
        return self._edit(self.adapter.add_connection, sender, signal, receiver, slot) is not None

    @Slot(int, str, str, str, str, result=bool)
    def updateConnection(self, index, sender, signal, receiver, slot):  # noqa: N802
        if self._ui_doc() is None:
            return False
        return self._edit(self.adapter.update_connection, index, sender, signal, receiver, slot) is not None

    @Slot(int, result=bool)
    def removeConnection(self, index):  # noqa: N802
        if self._ui_doc() is None:
            return False
        return self._edit(self.adapter.remove_connection, index) is not None

    @Slot(int, str, str, result=bool)
    def removeMember(self, uid, name, kind):  # noqa: N802
        """Remove an object's declared member that nothing uses (a red port in
        the signal flow view): in QML a function ("name()"), signal or
        property; in a form a signal or slot it declares (kind "signal" /
        "function"). Undoable."""
        if self.adapter is None:
            return False
        if self.adapter.kind == "qml":
            return self._edit(self.adapter.remove_member, uid, name, kind) is not None
        return self._edit(self.adapter.remove_declared, uid, kind, name) is not None

    @Slot(str, str, str, result=bool)
    def applyFileEdit(self, path, basis, text):  # noqa: N802
        """Kate's LSP client changed a file that isn't shown (rename, code
        action): `basis` is the file's text it changed, `text` the result.
        Applied like a quick fix: an unsaved, undoable change (the file opens
        as a background tab)."""
        edits = [{"startLine": 0, "startChar": 0, "endLine": basis.count("\n") + 1, "endChar": 0, "text": text}]
        return self.apply_text_fix(path, basis, edits) is not None

    @Slot(str, result=int)
    def lineOfSelected(self, _dummy=""):  # noqa: N802
        """1-based line where the selected object starts in sourceText (best effort)."""
        if self.adapter is None or not self.selected:
            return 0
        if self.adapter.kind == "qml":
            pdoc, _mode, _names = preview.build_preview_document(self.adapter.doc, set())
            for i, ln in enumerate(preview.preview_text(pdoc).split("\n")):
                if f'"{preview.MARKER}{self.selected}"' in ln:
                    return i + 1
            return 0
        name = self.adapter.doc.find(self.selected)
        if name is None:
            return 0
        needle = f'name="{name.id}"'
        for i, ln in enumerate(self.adapter.text().split("\n")):
            if needle in ln:
                return i + 1
        return 0
