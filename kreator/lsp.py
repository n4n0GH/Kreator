"""Language server support for the source view, using Qt's qmlls.

qmlls is the QML language server that ships with Qt (and the one Kate's LSP
client uses).  It respects a project's `.qmlls.ini` (build directory, import
paths), so app-specific modules such as cxx-qt or CMake QML modules are found.

`LspClient` speaks JSON-RPC over the server's stdio with a QProcess, so nothing
blocks the UI. It also shares its server with Kate's LSP client in the source
view (one qmlls for both): Kate starts lspbridge.py, which connects back to
Kreator, and LspClient.attach() serves that connection from the same server.  `LanguageSupport` is what QML sees (as the `Lsp` context
property): one open document at a time, completion, diagnostics, definitions
and formatting.  Line/character positions are passed through unchanged: both
QML strings and LSP count UTF-16 code units.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys

from PySide6.QtCore import (
    Property, QFileSystemWatcher, QLibraryInfo, QObject, QProcess, QTimer, QUrl, Signal, Slot,
)
from PySide6.QtNetwork import QLocalServer

from . import katestyle

# KDE's i18n functions come from KLocalizedContext at run time; qmlls cannot
# know them and flags every call, so those warnings are dropped.
_I18N = {"i18n", "i18nc", "i18np", "i18ncp", "i18nd", "i18ndc", "i18ndp", "i18ndcp",
         "xi18n", "xi18nc", "xi18np", "xi18ncp", "xi18nd", "xi18ndc"}


def find_qmlls(configured: str = "") -> str:
    if configured:
        p = shutil.which(os.path.expanduser(configured)) or (configured if os.access(configured, os.X_OK) else "")
        if p:
            return p
    for name in ("qmlls6", "qmlls"):
        p = shutil.which(name)
        if p:
            return p
    for where in (QLibraryInfo.LibraryPath.BinariesPath, QLibraryInfo.LibraryPath.LibraryExecutablesPath):
        p = os.path.join(QLibraryInfo.path(where), "qmlls")
        if os.access(p, os.X_OK):
            return p
    return ""


def project_root(path: str) -> str:
    """Directory with a .qmlls.ini, else the git root, else the file's folder."""
    d = os.path.dirname(os.path.abspath(path))
    start = d
    while True:
        if os.path.exists(os.path.join(d, ".qmlls.ini")):
            return d
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return start
        d = parent


def _frames(buffer: bytes):
    """([messages], rest) from LSP's Content-Length framed stream."""
    out = []
    while True:
        head_end = buffer.find(b"\r\n\r\n")
        if head_end < 0:
            break
        m = re.search(rb"Content-Length:\s*(\d+)", buffer[:head_end], re.I)
        if not m:
            buffer = buffer[head_end + 4:]
            continue
        start = head_end + 4
        length = int(m.group(1))
        if len(buffer) < start + length:
            break
        body, buffer = buffer[start:start + length], buffer[start + length:]
        try:
            out.append(json.loads(body))
        except ValueError:
            continue
    return out, buffer


def _frame(msg: dict) -> bytes:
    body = json.dumps(msg).encode("utf-8")
    return b"Content-Length: %d\r\n\r\n" % len(body) + body


def _apply_change(text: str, change: dict) -> str:
    """One entry of didChange's contentChanges (full text or a UTF-16 range)."""
    rng = change.get("range")
    if not rng:
        return change.get("text", "")
    s, e = rng.get("start", {}), rng.get("end", {})
    return apply_edits(text, [{"startLine": s.get("line", 0), "startChar": s.get("character", 0),
                               "endLine": e.get("line", 0), "endChar": e.get("character", 0),
                               "text": change.get("text", "")}])


class RemoteSession(QObject):
    """A client of Kreator's qmlls other than Kreator itself: Kate's LSP client,
    connected through lspbridge.py."""

    def __init__(self, socket, on_message, on_closed, parent=None):
        super().__init__(parent)
        self.socket = socket
        socket.setParent(self)
        self.client = None          # the LspClient serving it
        self.docs: dict[str, list] = {}   # uri -> [text, languageId], as this client sees them
        self._buffer = b""
        self._on_message = on_message
        socket.readyRead.connect(self._read)
        socket.disconnected.connect(lambda: on_closed(self))

    def send(self, msg):
        if self.socket.state() == self.socket.LocalSocketState.ConnectedState:
            self.socket.write(_frame(msg))

    def close(self):
        self.socket.disconnectFromServer()

    def _read(self):
        self._buffer += bytes(self.socket.readAll())
        msgs, self._buffer = _frames(self._buffer)
        for msg in msgs:
            self._on_message(self, msg)


_SYNC = ("textDocument/didOpen", "textDocument/didChange", "textDocument/didClose")


def _update_docs(docs: dict, method: str, params: dict) -> str:
    """Apply a document sync notification to {uri: [text, languageId]}; the uri."""
    td = params.get("textDocument") or {}
    uri = td.get("uri", "")
    if not uri:
        return ""
    if method == "textDocument/didOpen":
        docs[uri] = [td.get("text", ""), td.get("languageId") or "qml"]
    elif method == "textDocument/didChange":
        entry = docs.get(uri)
        if entry is None:
            return ""
        for change in params.get("contentChanges") or []:
            entry[0] = _apply_change(entry[0], change)
    else:
        docs.pop(uri, None)
    return uri


class LspClient(QObject):
    """Minimal JSON-RPC client for one language server process.

    Several clients can share the server: Kreator itself (request / notify)
    and remote sessions (Kate's LSP client, attach()). Requests get server ids
    of their own; the documents each client has open are merged, the editor's
    (a remote session's) text winning, and the server only ever sees one
    version sequence per document (qmlls skips versions it has seen)."""

    notification = Signal(str, "QVariant")   # method, params
    started = Signal()
    stopped = Signal(str)                     # reason

    def __init__(self, program: str, args: list[str], root: str, parent=None):
        super().__init__(parent)
        self.root = root
        self._buffer = b""
        self._next_id = 0
        self._callbacks: dict[int, object] = {}
        self._ready = False
        self._queue: list[bytes] = []
        self.capabilities: dict = {}
        self.server_info: dict = {}
        # sharing (see the class doc)
        self._sessions: list[RemoteSession] = []
        self._local_docs: dict[str, list] = {}   # uri -> [text, languageId] opened by Kreator
        self._sent: dict[str, str] = {}          # uri -> text the server has
        self._doc_version = 0
        self._pending_inits: list = []           # (session, id) waiting for the server
        self._remote_ids: dict[int, tuple] = {}  # server id -> (session, their id)
        # uri -> whether this server takes the editor's copy of a document (the
        # editor keeps a document per tab: other projects' are for their servers)
        self.accepts = None
        self.proc = QProcess(self)
        self.proc.setProgram(program)
        self.proc.setArguments(args)
        self.proc.setWorkingDirectory(root)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.readyReadStandardError.connect(lambda: self.proc.readAllStandardError())
        self.proc.finished.connect(lambda code, _status: self._finished(f"qmlls exited ({code})"))
        self.proc.errorOccurred.connect(lambda err: self._finished(f"qmlls could not run ({err.name})"))

    def start(self):
        self.proc.start()
        root_uri = QUrl.fromLocalFile(self.root).toString()
        self._send({"jsonrpc": "2.0", "id": self._new_id(self._on_initialized), "method": "initialize", "params": {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(self.root)}],
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": False},
                    "completion": {"completionItem": {"snippetSupport": False,
                                                      "documentationFormat": ["plaintext"]}},
                    "publishDiagnostics": {"relatedInformation": False},
                    "definition": {}, "formatting": {},
                    "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                    "codeAction": {"codeActionLiteralSupport": {"codeActionKind": {"valueSet": ["quickfix"]}}},
                    "semanticTokens": {"requests": {"full": True}, "tokenTypes": [], "tokenModifiers": [],
                                       "formats": ["relative"]},
                },
                "workspace": {"configuration": False, "workspaceFolders": True},
            },
        }}, force=True)

    def stop(self, wait=True):
        """Ask the server to exit. wait: block until it has (up to 0.6 s;
        when quitting); else it is killed a moment later if still running,
        without holding up the UI."""
        if self.proc.state() != QProcess.ProcessState.NotRunning:
            try:
                self._send({"jsonrpc": "2.0", "id": self._new_id(None), "method": "shutdown"}, force=True)
                self._send({"jsonrpc": "2.0", "method": "exit"}, force=True)
            except RuntimeError:
                pass
            if not wait:
                proc = self.proc
                def kill():
                    try:
                        if proc.state() != QProcess.ProcessState.NotRunning:
                            proc.kill()
                    except RuntimeError:  # already gone
                        pass
                QTimer.singleShot(2000, kill)
                return
            if not self.proc.waitForFinished(300):
                self.proc.kill()
                self.proc.waitForFinished(300)

    def _on_initialized(self, result, _error):
        self.capabilities = (result or {}).get("capabilities", {})
        self.server_info = (result or {}).get("serverInfo", {})
        self._send({"jsonrpc": "2.0", "method": "initialized", "params": {}}, force=True)
        self._ready = True
        for data in self._queue:
            self.proc.write(data)
        self._queue.clear()
        for session, mid in self._pending_inits:
            self._answer_initialize(session, mid)
        self._pending_inits.clear()
        self.started.emit()

    def _finished(self, reason):
        self._ready = False
        self._callbacks.clear()
        self._fail_remote_requests(reason)
        self.stopped.emit(reason)

    # ----------------------------------------------------------- sharing the server
    def attach(self, session: RemoteSession):
        """Serve a remote client (Kate's LSP client) from this server."""
        if session in self._sessions:
            return
        self._sessions.append(session)
        session.client = self
        for uri in list(session.docs):
            self._reconcile(uri)

    def detach(self, session: RemoteSession):
        if session not in self._sessions:
            return
        self._sessions.remove(session)
        if session.client is self:
            session.client = None
        for sid, (s, _mid) in list(self._remote_ids.items()):
            if s is session:
                del self._remote_ids[sid]
                self._callbacks.pop(sid, None)
        for uri in list(session.docs):
            self._reconcile(uri)

    def _fail_remote_requests(self, reason):
        for _sid, (session, mid) in list(self._remote_ids.items()):
            session.send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": reason}})
        self._remote_ids.clear()

    def _answer_initialize(self, session, mid):
        session.send({"jsonrpc": "2.0", "id": mid, "result": {
            "capabilities": self.capabilities, "serverInfo": self.server_info}})

    def remote_message(self, session: RemoteSession, msg: dict):
        method, mid = msg.get("method"), msg.get("id")
        if method is None:
            return  # an answer to a server request: Kreator answers those
        params = msg.get("params") or {}
        if method == "initialize":
            # the server is initialized once, by Kreator: tell what it can do
            if self._ready:
                self._answer_initialize(session, mid)
            else:
                self._pending_inits.append((session, mid))
        elif method == "shutdown":
            session.send({"jsonrpc": "2.0", "id": mid, "result": None})
        elif method == "exit":
            session.close()
        elif method in _SYNC:
            self._sync(session.docs, method, params)
        elif method == "$/cancelRequest":
            theirs = params.get("id")
            sid = next((k for k, (s, m) in self._remote_ids.items() if s is session and m == theirs), None)
            if sid is not None:
                self._send({"jsonrpc": "2.0", "method": "$/cancelRequest", "params": {"id": sid}})
        elif mid is not None:
            sid = self._new_id(lambda res, err, s=session, m=mid: self._remote_answer(s, m, res, err))
            self._remote_ids[sid] = (session, mid)
            self._send({"jsonrpc": "2.0", "id": sid, "method": method, "params": params})
        # other notifications (didSave, configuration, workspace folders): the
        # server is Kreator's, set up by Kreator: not passed on

    def _remote_answer(self, session, mid, result, error):
        for sid, (s, m) in list(self._remote_ids.items()):
            if s is session and m == mid:
                del self._remote_ids[sid]
                break
        msg = {"jsonrpc": "2.0", "id": mid}
        if error:
            msg["error"] = error
        else:
            msg["result"] = result
        session.send(msg)

    def _sync(self, docs: dict, method: str, params: dict):
        uri = _update_docs(docs, method, params)
        if uri:
            self._reconcile(uri)

    def _reconcile(self, uri: str):
        """Bring the server's copy of a document in line with its clients: the
        editor's text (a remote session's) if it has the document open, else
        Kreator's, else closed."""
        want = None
        if self.accepts is None or self.accepts(uri):
            want = next((s.docs[uri] for s in self._sessions if uri in s.docs), None)
        if want is None:
            want = self._local_docs.get(uri)
        have = self._sent.get(uri)
        if want is None:
            if have is not None:
                del self._sent[uri]
                self._send({"jsonrpc": "2.0", "method": "textDocument/didClose", "params": {"textDocument": {"uri": uri}}})
            return
        if have == want[0]:
            return
        self._doc_version += 1
        if have is None:
            self._send({"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {"textDocument": {
                "uri": uri, "languageId": want[1], "version": self._doc_version, "text": want[0]}}})
        else:
            self._send({"jsonrpc": "2.0", "method": "textDocument/didChange", "params": {
                "textDocument": {"uri": uri, "version": self._doc_version}, "contentChanges": [{"text": want[0]}]}})
        self._sent[uri] = want[0]

    def _new_id(self, callback):
        self._next_id += 1
        self._callbacks[self._next_id] = callback
        return self._next_id

    def request(self, method, params, callback):
        rid = self._new_id(callback)
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        return rid

    def notify(self, method, params):
        if method in _SYNC:
            self._sync(self._local_docs, method, params)
            return
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _send(self, msg, force=False):
        data = _frame(msg)
        if self._ready or force:
            self.proc.write(data)
        else:
            self._queue.append(data)

    def _read(self):
        self._buffer += bytes(self.proc.readAllStandardOutput())
        msgs, self._buffer = _frames(self._buffer)
        for msg in msgs:
            self._dispatch(msg)

    def _dispatch(self, msg):
        if "id" in msg and "method" in msg:
            # a request from the server: answer the ones qmlls sends politely
            result = [] if msg["method"] == "workspace/configuration" else None
            self._send({"jsonrpc": "2.0", "id": msg["id"], "result": result}, force=True)
            return
        if "id" in msg:
            cb = self._callbacks.pop(msg["id"], None)
            if cb is not None:
                cb(msg.get("result"), msg.get("error"))
            return
        if "method" in msg:
            # (diagnostics etc. go to every client; versions are the server's)
            if self._sessions:
                fwd = dict(msg)
                if isinstance(fwd.get("params"), dict) and "version" in fwd["params"]:
                    fwd["params"] = {k: v for k, v in fwd["params"].items() if k != "version"}
                for session in list(self._sessions):
                    session.send(fwd)
            self.notification.emit(msg["method"], msg.get("params"))


_KIND_ICONS = {
    1: "format-text-code", 2: "code-function", 3: "code-function", 4: "code-function",
    5: "code-variable", 6: "code-variable", 7: "code-class", 8: "code-class", 9: "code-block",
    10: "code-variable", 11: "code-typedef", 12: "code-variable", 13: "enum", 14: "code-context",
    15: "format-text-code", 18: "code-variable", 20: "enum", 21: "code-variable", 22: "code-class",
    23: "code-context", 25: "code-typedef",
}


class LanguageSupport(QObject):
    """The `Lsp` object used by the source view."""

    stateChanged = Signal()
    diagnosticsChanged = Signal()
    completionReady = Signal(int, "QVariantList")        # request id, items
    definitionReady = Signal(int, str, int, int)          # request id, path, line, character (0-based)
    formattingReady = Signal(int, "QVariantList")         # request id, edits
    requestFailed = Signal(str)                           # message from the server
    referencesReady = Signal(int, "QVariantList")         # request id, locations
    renameReady = Signal(int, "QVariantList", "QVariantList")  # request id, edits here, other files

    def __init__(self, settings_getter, import_paths, parent=None):
        super().__init__(parent)
        self._settings = settings_getter
        self._import_paths = import_paths
        self._bridge: QLocalServer | None = None
        self._sessions: list[RemoteSession] = []
        self._client: LspClient | None = None
        self._root = ""
        self._status = ""
        self._ready = False
        self._uri = ""
        self._path = ""
        self._version = 0
        self._vcounter = 0      # document versions only ever grow (also across close/open)
        self._text = ""
        self._open = False
        self._diagnostics: list[dict] = []
        self._req = 0
        self._renames: dict[int, dict] = {}   # rid -> {path: [edits]} for other files
        self._fix_text = ""                     # text the current quick fixes were made for
        self._fix_generation = 0
        self._fix_emit = QTimer(self, singleShot=True, interval=30)
        self._fix_emit.timeout.connect(self.diagnosticsChanged)
        # semantic highlighting
        self._symbols: list[dict] = []
        self._want_symbols = False
        self._sym_timer = QTimer(self, singleShot=True, interval=400)
        self._sym_timer.timeout.connect(self._request_symbols)
        self._sem_doc = None            # QQuickTextDocument of the source view
        self._sem_styles: dict = {}     # theme text-styles
        self._hl = None                 # QmlHighlighter / XmlHighlighter while active
        self._had_hl = False
        self._is_qml = False
        self._sem_timer = QTimer(self, singleShot=True, interval=250)
        self._sem_timer.timeout.connect(self._request_semantic)
        self._change_timer = QTimer(self, singleShot=True, interval=120)
        self._change_timer.timeout.connect(self._flush_change)
        # project index: document symbols of every project file, fetched in
        # the background so the symbol view has them before a file is shown
        self._project_dir = ""
        self._index_cache: dict[str, tuple[str, list]] = {}   # path -> (text, symbol rows)
        self._index_stat: dict[str, tuple] = {}               # path -> (mtime, size) when indexed
        self._index_queue: list[str] = []
        self._index_total = 0
        self._index_done = 0
        self._index_busy = False
        self._index_inflight = ""
        self._index_file = ""
        self._index_open_uri = ""       # file opened only for indexing
        self._index_gen = 0
        self._priming = False
        self._primed_root = ""
        # servers of other project roots, kept running so that switching back
        # to their files is instant (root -> (client, types loaded)), oldest first
        self._parked: dict[str, tuple] = {}
        self._index_elsewhere: list[str] = []   # files queued for another root's server
        # qmllint diagnostics of every indexed file (path -> converted list)
        self._project_diags: dict[str, list] = {}
        self._index_diags: list | None = None     # for the file being indexed
        self._index_symbols_done = False
        self._index_pending: tuple | None = None   # (path, uri, text, st) waiting for diagnostics
        self._index_diag_timer = QTimer(self, singleShot=True, interval=3000)
        self._index_diag_timer.timeout.connect(self._index_finish)
        self._pdiag_timer = QTimer(self, singleShot=True, interval=150)
        self._pdiag_timer.timeout.connect(self._rebuild_project_diags)
        self._pdiag_rows: list[dict] = []
        self._project_texts: dict[str, str] = {}   # path -> text its findings are for
        self._index_overrides: dict[str, str] = {} # path -> unsaved text to check instead of the file
        self.edit_handler = None    # (path, basis text, edits) -> new text or None; set by the app
        # re-index files changed by other programs
        self._index_watcher = QFileSystemWatcher(self)
        self._index_watcher.fileChanged.connect(self._on_index_file_changed)
        self._index_changed: set[str] = set()
        self._index_watch_timer = QTimer(self, singleShot=True, interval=300)
        self._index_watch_timer.timeout.connect(self._reindex_changed)

    # ----------------------------------------------------------- properties
    def _config(self):
        lsp = self._settings().get("lsp", {})
        return bool(lsp.get("enabled", True)), str(lsp.get("command", ""))

    available = Property(bool, lambda self: bool(find_qmlls(self._config()[1])), notify=stateChanged)
    enabled = Property(bool, lambda self: self._config()[0], notify=stateChanged)
    running = Property(bool, lambda self: self._ready, notify=stateChanged)
    status = Property(str, lambda self: self._status, notify=stateChanged)
    serverPath = Property(str, lambda self: find_qmlls(self._config()[1]), notify=stateChanged)

    def _server_command(self) -> list:
        """qmlls with Kreator's import paths (for Kate's LSP client in the
        source view); empty when the language server is off or missing."""
        enabled, command = self._config()
        program = find_qmlls(command) if enabled else ""
        if not program:
            return []
        cmd = [program]
        for p in self._import_paths():
            cmd += ["-I", p]
        return cmd

    serverCommand = Property("QVariantList", _server_command, notify=stateChanged)

    # ----------------------------------------------------------- Kate's LSP client
    # Kate's LSP client (in the source view) shares Kreator's qmlls: it starts
    # lspbridge.py, which connects to this local server.
    def _kate_server_command(self) -> list:
        if not self._server_command():
            return []
        if self._bridge is None:
            srv = QLocalServer(self)
            srv.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
            name = f"kreator-lsp-{os.getpid()}"
            QLocalServer.removeServer(name)
            if not srv.listen(name):
                return []
            srv.newConnection.connect(self._bridge_connected)
            # (Kate starts the bridge as a child process: it inherits this)
            os.environ["KREATOR_LSP_SOCKET"] = srv.fullServerName()
            self._bridge = srv
        return [sys.executable, "-I", "-S", os.path.join(os.path.dirname(os.path.abspath(__file__)), "lspbridge.py")]

    kateServerCommand = Property("QVariantList", _kate_server_command, notify=stateChanged)

    def _bridge_connected(self):
        while self._bridge.hasPendingConnections():
            session = RemoteSession(self._bridge.nextPendingConnection(), self._remote_message,
                                    self._remote_closed, self)
            self._sessions.append(session)
            if self._client is not None:
                self._client.attach(session)
            else:
                # no server yet: start one for the shown file / the project
                path = self._path or next(iter(self._index_cache), "") or (
                    os.path.join(self._project_dir, "_.qml") if self._project_dir else "")
                if not path or not self._ensure_server(path):
                    session.close()

    def _remote_message(self, session, msg):
        if session.client is not None:
            session.client.remote_message(session, msg)
            return
        # between servers (restarting, settings changed): keep the documents
        # current, and ask again later
        method, mid = msg.get("method"), msg.get("id")
        if method in _SYNC:
            _update_docs(session.docs, method, msg.get("params") or {})
        elif method == "exit":
            session.close()
        elif method is not None and mid is not None:
            if method == "initialize" and (self._path or self._project_dir):
                path = self._path or os.path.join(self._project_dir, "_.qml")
                if self._ensure_server(path) and session.client is not None:
                    session.client.remote_message(session, msg)
                    return
            session.send({"jsonrpc": "2.0", "id": mid, "error": {
                "code": -32002, "message": "qmlls is restarting"}})

    def _remote_closed(self, session):
        if session in self._sessions:
            self._sessions.remove(session)
        if session.client is not None:
            session.client.detach(session)
        session.docs.clear()
        session.deleteLater()
    diagnostics = Property("QVariantList", lambda self: self._diagnostics, notify=diagnosticsChanged)
    errorCount = Property(int, lambda self: sum(1 for d in self._diagnostics if d["severity"] == 1),
                          notify=diagnosticsChanged)
    warningCount = Property(int, lambda self: sum(1 for d in self._diagnostics if d["severity"] != 1),
                            notify=diagnosticsChanged)

    # ----------------------------------------------------------- server lifecycle
    def _ensure_server(self, path) -> bool:
        enabled, command = self._config()
        if not enabled:
            self._set_status("")
            return False
        program = find_qmlls(command)
        if not program:
            self._set_status("qmlls not found")
            return False
        root = self._root_for(path)
        if self._client is not None and self._root == root:
            return True
        if self._client is not None:
            self._park()
        else:
            self._index_reset()
        self._requeue_elsewhere(root)
        if self._resume(root):
            return True
        args = []
        for p in self._import_paths():
            args += ["-I", p]
        self._client = LspClient(program, args, root, self)
        known: dict[str, bool] = {}

        def accepts(uri, root=root):
            if uri not in known:
                known[uri] = self._root_for(QUrl(uri).toLocalFile()) == root
            return known[uri]
        self._client.accepts = accepts
        self._root = root
        for session in self._sessions:   # Kate's LSP client moves along
            self._client.attach(session)
        client = self._client
        # signals of a replaced client (settings changed) are ignored
        client.started.connect(lambda c=client: self._on_started() if c is self._client else None)
        client.stopped.connect(lambda reason, c=client: self._on_stopped(reason) if c is self._client else None)
        client.notification.connect(lambda m, p, c=client: self._on_notification(m, p) if c is self._client else None)
        self._set_status("Starting qmlls…")
        self._client.start()
        return True

    _KEEP_SERVERS = 3   # running at once (the current one and parked ones)

    def _park(self):
        """Put the current server aside (another project's file is shown):
        it keeps running, with its types loaded, for when its files are
        shown again."""
        client, root = self._client, self._root
        primed = self._primed_root == root and not self._priming
        self._index_reset()
        for session in self._sessions:
            client.detach(session)
        self._client = None
        self._ready = False
        self._open = False
        self._root = ""
        self._parked.pop(root, None)
        self._parked[root] = (client, primed)
        while len(self._parked) >= self._KEEP_SERVERS:
            old = next(iter(self._parked))
            self._stop_client(self._parked.pop(old)[0], wait=False)

    def _resume(self, root) -> bool:
        """Make a parked server of this root the current one again."""
        if root not in self._parked:
            return False
        client, primed = self._parked.pop(root)
        if client.proc.state() != QProcess.ProcessState.Running:
            self._stop_client(client, wait=False)
            return False
        self._client = client
        self._root = root
        self._primed_root = root if primed else ""
        for session in self._sessions:
            client.attach(session)
        self._ready = client._ready
        self._set_status("qmlls" if self._ready else "Starting qmlls…")
        if self._ready:
            QTimer.singleShot(0, self._index_next)
        return True

    def _requeue_elsewhere(self, root):
        """Files of this root that waited for its server: index them now."""
        mine = [p for p in self._index_elsewhere if self._root_for(p) == root]
        if not mine:
            return
        self._index_elsewhere = [p for p in self._index_elsewhere if p not in mine]
        if not self._index_queue and not self._index_busy:
            self._index_total = self._index_done = 0
        mine = [p for p in mine if p not in self._index_queue]
        self._index_queue += mine
        self._index_total += len(mine)
        self.indexChanged.emit()

    def _stop_client(self, client, wait=True):
        for session in self._sessions:
            client.detach(session)
        client.stop(wait=wait)
        if wait:
            client.deleteLater()
        else:
            client.proc.finished.connect(client.deleteLater)
            if client.proc.state() == QProcess.ProcessState.NotRunning:
                client.deleteLater()

    def _next_version(self) -> int:
        # qmlls doesn't check a version it has seen again, so a file opened
        # again (e.g. after a quick fix) needs a newer one
        self._vcounter += 1
        return self._vcounter

    def _root_for(self, path) -> str:
        """project_root(), but files of the open folder share one server even
        without a .qmlls.ini or git checkout."""
        root = project_root(path)
        d = self._project_dir
        if d and root == os.path.dirname(os.path.abspath(path)) and os.path.abspath(path).startswith(d + os.sep):
            if not os.path.exists(os.path.join(root, ".qmlls.ini")) and not os.path.exists(os.path.join(root, ".git")):
                return d
        return root

    def _on_started(self):
        if self._client is None:
            return
        self._ready = True
        self._set_status("qmlls")
        QTimer.singleShot(0, self._index_next)
        # Load the type information now, so the first real completion is quick:
        # a completion inside the root object's body makes qmlls load all imports.
        # Symbols and colours are asked for first: that load can take seconds.
        if self._open:
            self._request_semantic()
            cached = self._index_cache.get(os.path.abspath(self._path)) if self._path else None
            if self._want_symbols and not (cached is not None and cached[0] == self._text):
                self._request_symbols()
            if self._primed_root == self._root:
                return  # the types are loaded already
            # the root object: an unindented `Type {` line (a "{" in a header
            # comment would not count)
            m = re.search(r"^[A-Za-z_][\w.]*(?:\s+on\s+\w+)?\s*\{", self._text, re.M)
            line = self._text.count("\n", 0, m.start()) + 1 if m else 0
            self._client.request("textDocument/completion", {
                "textDocument": {"uri": self._uri}, "position": {"line": line, "character": 0}},
                lambda *_: None)

    def _on_stopped(self, reason):
        self._index_reset()
        self._ready = False
        if self._client is not None:
            for session in self._sessions:
                self._client.detach(session)
        self._client = None
        self._root = ""
        self._open = False
        self._set_status(reason)

    def _set_status(self, s):
        self._status = s
        self.stateChanged.emit()

    @Slot()
    def shutdown(self, wait=True):
        """Stop the servers (all: parked ones too)."""
        self._index_reset()
        for client, _primed in self._parked.values():
            self._stop_client(client, wait)
        self._parked.clear()
        if self._client is not None:
            client, self._client = self._client, None
            self._stop_client(client, wait)
        self._ready = False
        self._open = False
        self._root = ""

    @Slot()
    def settingsChanged(self):  # noqa: N802
        self._update_highlighter()
        self.shutdown(wait=False)
        self._diagnostics = []
        self.diagnosticsChanged.emit()
        self.stateChanged.emit()
        if self._path:
            self.openDocument(self._path, self._text, True)
        if self._config()[0]:
            self.indexFiles(list(self._index_cache) + self._index_queue, self._project_dir)

    # ----------------------------------------------------------- documents
    @Slot(str, str, bool)
    def openDocument(self, path, text, is_qml):  # noqa: N802
        """Called by the source view when it loads a document."""
        self._is_qml = bool(is_qml)
        self._update_highlighter()
        if not is_qml:
            self.closeDocument()
            return
        if not path:  # untitled: give the server a file name in the current folder
            path = os.path.join(os.getcwd(), "untitled.qml")
        uri = QUrl.fromLocalFile(os.path.abspath(path)).toString()
        if self._open and uri == self._uri and self._client is not None:
            self.changeDocument(text)
            return
        # (the symbol view is redrawn once: with the new file's symbols if
        # indexed already, else empty until they come)
        self._close(keep_symbols=True)
        self._path, self._uri, self._text = path, uri, text
        self.prioritize(path)
        cached = self._index_cache.get(os.path.abspath(path))
        self._set_symbols(cached[1] if cached is not None and cached[0] == text else [])
        if not self._ensure_server(path):
            return
        if self._index_open_uri == uri:
            # open for indexing right now: take it over instead of opening it twice
            self._index_open_uri = ""
            self._version = self._next_version()
            self._client.notify("textDocument/didChange", {
                "textDocument": {"uri": uri, "version": self._version}, "contentChanges": [{"text": text}]})
        else:
            self._version = self._next_version()
            self._client.notify("textDocument/didOpen", {"textDocument": {
                "uri": uri, "languageId": "qml", "version": self._version, "text": text}})
        self._open = True
        if self._ready:
            self._on_started()

    @Slot()
    def closeDocument(self):  # noqa: N802
        self._close()

    def _set_symbols(self, rows):
        if rows != self._symbols:
            self._symbols = rows
            self.symbolsChanged.emit()

    def _close(self, keep_symbols=False):
        if not keep_symbols:
            self._set_symbols([])
        if self._hl is not None:
            self._hl.clear_tokens()
        if self._open and self._client is not None:
            self._client.notify("textDocument/didClose", {"textDocument": {"uri": self._uri}})
        self._open = False
        self._path = ""
        if self._diagnostics:
            self._diagnostics = []
            self.diagnosticsChanged.emit()

    @Slot(str)
    def changeDocument(self, text):  # noqa: N802
        self._text = text
        self._fix_generation += 1  # pending code actions are for the old text
        if self._open:
            self._change_timer.start()

    def _flush_change(self):
        self._change_timer.stop()
        if not self._open or self._client is None:
            return
        self._version = self._next_version()
        self._client.notify("textDocument/didChange", {
            "textDocument": {"uri": self._uri, "version": self._version},
            "contentChanges": [{"text": self._text}]})
        self._sem_timer.start()
        if self._want_symbols:
            self._sym_timer.start()

    # ----------------------------------------------------------- requests
    def _position(self, line, character):
        return {"textDocument": {"uri": self._uri}, "position": {"line": line, "character": character}}

    @Slot(int, int, result=int)
    def complete(self, line, character):
        """Request completions at (0-based) line/character; answer via completionReady."""
        if not self._open or self._client is None:
            return -1
        self._flush_change()
        self._req += 1
        rid = self._req
        self._client.request("textDocument/completion", self._position(line, character),
                             lambda res, err, rid=rid: self._on_completion(rid, res, err))
        return rid

    def _on_completion(self, rid, result, error):
        if error or result is None:
            self.completionReady.emit(rid, [])
            return
        items = result.get("items", []) if isinstance(result, dict) else result
        out = []
        seen = set()
        for it in items:
            label = it.get("label", "")
            if label.startswith(("__", "_q_")):  # JS / engine internals
                continue
            key = (label, it.get("kind"))
            if key in seen:  # qmlls lists some types once per exported version
                continue
            seen.add(key)
            edit = it.get("textEdit")
            out.append({
                "label": label,
                "detail": (it.get("detail") or "").strip(),
                "kind": it.get("kind", 0),
                "icon": _KIND_ICONS.get(it.get("kind", 0), "code-context"),
                "insertText": (edit or {}).get("newText") or it.get("insertText") or label,
                "filterText": it.get("filterText") or label,
                "sortText": it.get("sortText") or label,
            })
        self.completionReady.emit(rid, out)

    @Slot(int, int, result=int)
    def definition(self, line, character):
        if not self._open or self._client is None:
            return -1
        self._flush_change()
        self._req += 1
        rid = self._req
        self._client.request("textDocument/definition", self._position(line, character),
                             lambda res, err, rid=rid: self._on_definition(rid, res, err))
        return rid

    def _on_definition(self, rid, result, error=None):
        if error:
            self.requestFailed.emit(error.get("message") or "The language server could not answer")
            self.definitionReady.emit(rid, "", -2, -2)
            return
        loc = result[0] if isinstance(result, list) and result else result
        if not isinstance(loc, dict):
            self.definitionReady.emit(rid, "", -1, -1)
            return
        uri = loc.get("uri") or loc.get("targetUri", "")
        rng = loc.get("range") or loc.get("targetSelectionRange") or {}
        start = rng.get("start", {})
        self.definitionReady.emit(rid, QUrl(uri).toLocalFile(), start.get("line", 0), start.get("character", 0))

    @Slot(int, result=int)
    def format(self, tab_size):
        if not self._open or self._client is None:
            return -1
        self._flush_change()
        self._req += 1
        rid = self._req
        self._client.request("textDocument/formatting", {
            "textDocument": {"uri": self._uri}, "options": {"tabSize": tab_size, "insertSpaces": True}},
            lambda res, err, rid=rid: (self.requestFailed.emit(err.get("message", "")) if err else None) or self.formattingReady.emit(rid, [
                {"startLine": e["range"]["start"]["line"], "startChar": e["range"]["start"]["character"],
                 "endLine": e["range"]["end"]["line"], "endChar": e["range"]["end"]["character"],
                 "text": e.get("newText", "")} for e in (res or [])]))
        return rid

    # ----------------------------------------------------------- references & rename
    def _lines_of(self, path):
        if path == self._path or QUrl.fromLocalFile(path).toString() == self._uri:
            return self._text.split("\n")
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read().split("\n")
        except OSError:
            return []

    @Slot(int, int, result=int)
    def references(self, line, character):
        if not self._open or self._client is None:
            return -1
        self._flush_change()
        self._req += 1
        rid = self._req
        params = self._position(line, character)
        params["context"] = {"includeDeclaration": True}
        self._client.request("textDocument/references", params,
                             lambda res, err, rid=rid: self._on_references(rid, res, err))
        return rid

    def _on_references(self, rid, result, error):
        if error:
            self.requestFailed.emit(error.get("message", ""))
            self.referencesReady.emit(rid, [])
            return
        cache: dict[str, list] = {}
        out = []
        for loc in result or []:
            path = QUrl(loc.get("uri", "")).toLocalFile()
            rng = loc.get("range", {})
            s, e = rng.get("start", {}), rng.get("end", {})
            if path not in cache:
                cache[path] = self._lines_of(path)
            lines = cache[path]
            ln = s.get("line", 0)
            text = lines[ln] if 0 <= ln < len(lines) else ""
            # line text with the reference marked, in UTF-16 units like LSP
            u = text.encode("utf-16-le")
            a, b = s.get("character", 0) * 2, (e.get("character", 0) if e.get("line") == ln else len(u) // 2) * 2
            before = u[:a].decode("utf-16-le", "replace")
            match = u[a:b].decode("utf-16-le", "replace")
            after = u[b:].decode("utf-16-le", "replace")
            strip = len(before) - len(before.lstrip())
            out.append({
                "path": path, "fileName": os.path.basename(path),
                "current": path == self._path or loc.get("uri") == self._uri,
                "line": ln, "character": s.get("character", 0),
                "endLine": e.get("line", ln), "endCharacter": e.get("character", 0),
                "before": before[strip:], "match": match, "after": after.rstrip(),
            })
        out.sort(key=lambda r: (not r["current"], r["path"], r["line"], r["character"]))
        self.referencesReady.emit(rid, out)

    @Slot(int, int, str, result=int)
    def rename(self, line, character, new_name):
        if not self._open or self._client is None:
            return -1
        self._flush_change()
        self._req += 1
        rid = self._req
        params = self._position(line, character)
        params["newName"] = new_name
        self._client.request("textDocument/rename", params,
                             lambda res, err, rid=rid: self._on_rename(rid, res, err))
        return rid

    def _on_rename(self, rid, result, error):
        if error:
            self.requestFailed.emit(error.get("message", ""))
            self.renameReady.emit(rid, [], [])
            return
        per_file: dict[str, list] = {}
        result = result or {}
        for uri, edits in (result.get("changes") or {}).items():
            per_file.setdefault(uri, []).extend(edits)
        for change in result.get("documentChanges") or []:
            if "textDocument" in change:  # (create/rename/delete file operations are not used by qmlls)
                per_file.setdefault(change["textDocument"]["uri"], []).extend(change.get("edits", []))

        def conv(e):
            r = e["range"]
            return {"startLine": r["start"]["line"], "startChar": r["start"]["character"],
                    "endLine": r["end"]["line"], "endChar": r["end"]["character"], "text": e.get("newText", "")}

        here, others, pending = [], [], {}
        for uri, edits in per_file.items():
            path = QUrl(uri).toLocalFile()
            if uri == self._uri or path == self._path:
                here = [conv(e) for e in edits]
            else:
                pending[path] = [conv(e) for e in edits]
                others.append({"path": path, "fileName": os.path.basename(path), "count": len(edits)})
        self._renames[rid] = pending
        self.renameReady.emit(rid, here, others)

    @Slot(int, result=str)
    def applyRenameToFiles(self, rid):  # noqa: N802
        """Write a rename's edits into the other (not open) files; "" or an error."""
        pending = self._renames.pop(rid, {})
        for path, edits in pending.items():
            try:
                with open(path, encoding="utf-8", newline="") as fh:
                    text = fh.read()
                text = apply_edits(text, edits)
                with open(path, "w", encoding="utf-8", newline="") as fh:
                    fh.write(text)
            except OSError as e:
                return f"{os.path.basename(path)}: {e.strerror}"
        return ""

    @Slot(int)
    def discardRename(self, rid):  # noqa: N802
        self._renames.pop(rid, None)

    # ----------------------------------------------------------- document symbols
    symbolsChanged = Signal()
    _SYMBOL_ICONS = {1: "text-x-generic", 2: "code-context", 3: "code-context", 5: "code-class", 6: "code-function",
                     7: "code-variable", 8: "code-variable", 10: "enum", 11: "code-class", 12: "code-function",
                     13: "code-variable", 14: "code-variable", 19: "code-block", 20: "tag", 22: "enum",
                     23: "code-class", 24: "code-function"}
    symbols = Property("QVariantList", lambda self: self._symbols, notify=symbolsChanged)

    @Slot(bool)
    def setWantSymbols(self, want):  # noqa: N802
        """The symbol view is visible: keep symbols up to date."""
        self._want_symbols = want
        if want:
            self._sym_timer.start(50)

    def _request_symbols(self):
        if not self._open or self._client is None or not self._ready:
            return
        text = self._text
        self._client.request("textDocument/documentSymbol", {"textDocument": {"uri": self._uri}},
                             lambda res, err, text=text: self._on_symbols(text, res, err))

    def _on_symbols(self, text, result, error):
        if error or text != self._text:
            return
        rows = self._symbol_rows(text, result)
        if self._path:
            self._index_cache[os.path.abspath(self._path)] = (text, rows)
        self._set_symbols(rows)

    def _symbol_rows(self, text, result) -> list:
        rows = []
        lines = text.split("\n")
        declaration = re.compile(r"^\s*(?:(?:readonly|required|default|final|virtual|override)\s+)*(property|signal|function|enum)\b")

        def walk(items, depth, parent_path):
            def start(sym):
                r = sym.get("selectionRange") or sym.get("range") or sym.get("location", {}).get("range", {})
                return (r.get("start", {}).get("line", 0), r.get("start", {}).get("character", 0))
            for sym in sorted(items or [], key=start):
                kind = sym.get("kind", 0)
                if kind == 20:  # `id: foo` — shown next to its object instead
                    continue
                line, char = start(sym)
                rng = sym.get("range") or {}
                detail = " ".join(str(sym.get("detail") or "").split())
                name = sym.get("name", "")
                path = f"{parent_path}/{name}" if parent_path else name
                rows.append({
                    "key": f"{path}@{line}", "name": name, "detail": detail[:48] + ("…" if len(detail) > 48 else ""),
                    "kind": kind, "icon": self._SYMBOL_ICONS.get(kind, "code-context"), "depth": depth,
                    "line": line, "character": char, "endLine": rng.get("end", {}).get("line", line),
                    # qmlls gives declared properties and plain bindings the same
                    # kind; declarations (property/signal/function lines) are shown
                    # by default, bindings only on request
                    "isObject": kind in (5, 19, 23),
                    "isBinding": kind in (7, 8, 13, 14) and not (0 <= line < len(lines) and declaration.match(lines[line])),
                    "hasChildren": bool(sym.get("children")),
                })
                walk(sym.get("children"), depth + 1, path)

        walk(result, 0, "")
        return rows

    # ----------------------------------------------------------- project index
    indexChanged = Signal()
    indexing = Property(bool, lambda self: bool(self._index_queue) or self._index_busy, notify=indexChanged)
    indexTotal = Property(int, lambda self: self._index_total, notify=indexChanged)
    indexDone = Property(int, lambda self: self._index_done, notify=indexChanged)
    indexFile = Property(str, lambda self: self._index_file, notify=indexChanged)
    loadingTypes = Property(bool, lambda self: self._priming, notify=indexChanged)

    @Slot("QVariantList", str)
    def setProjectFiles(self, paths, project_dir=""):  # noqa: N802
        """The complete set of files to know about: others are forgotten
        (a closed folder, deleted files), these are indexed if needed."""
        keep = {os.path.abspath(str(p)) for p in paths or []}
        for p in [p for p in self._project_diags if p not in keep]:
            del self._project_diags[p]
            self._project_texts.pop(p, None)
            self._pdiag_timer.start()
        self._index_elsewhere = [p for p in self._index_elsewhere if p in keep]
        dropped = [p for p in self._index_queue if p not in keep]
        if dropped:
            self._index_queue = [p for p in self._index_queue if p in keep]
            self._index_total = max(self._index_done, self._index_total - len(dropped))
        self.indexFiles(paths, project_dir)

    @Slot("QVariantList", str)
    def indexFiles(self, paths, project_dir=""):  # noqa: N802
        """Fetch the symbols of these .qml files in the background (skipping
        ones that haven't changed since), then load their imports' types."""
        self._project_dir = os.path.abspath(project_dir) if project_dir else ""
        enabled, command = self._config()
        if not enabled or not find_qmlls(command):
            return
        todo = []
        for p in dict.fromkeys(os.path.abspath(str(p)) for p in paths or []):
            if not p.endswith(".qml") or p in self._index_queue:
                continue
            try:
                st = os.stat(p)
            except OSError:
                self._index_cache.pop(p, None)
                if self._project_diags.pop(p, None) is not None:
                    self._pdiag_timer.start()
                continue
            if self._index_stat.get(p) == (st.st_mtime_ns, st.st_size) and p in self._index_cache:
                continue
            todo.append(p)
        if not todo:
            return
        if not self._index_queue and not self._index_busy:
            self._index_total = self._index_done = 0
        self._index_queue += todo
        self._index_total += len(todo)
        self.indexChanged.emit()
        if self._client is None:
            self._ensure_server(todo[0])
        elif self._ready:
            self._index_next()

    @Slot(str)
    def prioritize(self, path):
        """Index this file next (the one being looked at)."""
        p = os.path.abspath(path) if path else ""
        if p in self._index_queue and self._index_queue[0] != p:
            self._index_queue.remove(p)
            self._index_queue.insert(0, p)

    def _index_reset(self):
        """The server went away: what was in flight is asked again from the next one."""
        self._index_gen += 1
        if self._index_busy and self._index_inflight and self._index_inflight not in self._index_queue:
            self._index_queue.insert(0, self._index_inflight)
        self._index_inflight = ""
        self._primed_root = ""
        self._index_busy = False
        self._index_open_uri = ""
        self._index_pending = None
        self._index_diag_timer.stop()
        self._priming = False
        self.indexChanged.emit()

    def _index_next(self):
        if self._index_busy or self._client is None or not self._ready:
            return
        while self._index_queue:
            p = self._index_queue.pop(0)
            if self._root_for(p) != self._root:
                # another project's (another server's): when its server is the
                # current one
                self._index_total -= 1
                if p not in self._index_elsewhere:
                    self._index_elsewhere.append(p)
                continue
            uri = QUrl.fromLocalFile(p).toString()
            own = self._open and uri == self._uri
            try:
                st = os.stat(p)
                if own:
                    text = self._text
                elif p in self._index_overrides:
                    text = self._index_overrides.pop(p)
                else:
                    with open(p, encoding="utf-8") as fh:
                        text = fh.read()
            except (OSError, UnicodeDecodeError):
                self._index_done += 1
                continue
            cached = self._index_cache.get(p)
            if cached is not None and cached[0] == text:
                self._index_stat[p] = (st.st_mtime_ns, st.st_size)
                self._index_done += 1
                continue
            self._index_busy = True
            self._index_inflight = p
            self._index_file = os.path.basename(p)
            self._index_diags = None
            self._index_symbols_done = False
            if not own:
                self._index_open_uri = uri
                self._client.notify("textDocument/didOpen", {"textDocument": {
                    "uri": uri, "languageId": "qml", "version": self._next_version(), "text": text}})
            gen = self._index_gen
            self._client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}},
                                 lambda res, err, p=p, uri=uri, text=text, st=st, gen=gen:
                                 self._on_index_symbols(gen, p, uri, text, st, res, err))
            self.indexChanged.emit()
            return
        self._index_file = ""
        self.indexChanged.emit()
        self._prime_types()

    def _on_index_symbols(self, gen, path, uri, text, st, result, error):
        if gen != self._index_gen:
            return
        if not error and result is not None:
            rows = self._symbol_rows(text, result)
            self._index_cache[path] = (text, rows)
            self._index_stat[path] = (st.st_mtime_ns, st.st_size)
            if path not in self._index_watcher.files() and len(self._index_watcher.files()) < 1000:
                self._index_watcher.addPath(path)
            # the shown document, if the view has nothing newer
            if self._open and uri == self._uri and text == self._text and not self._symbols:
                self._symbols = rows
                self.symbolsChanged.emit()
        self._index_symbols_done = True
        self._index_pending = (path, uri, text)
        if self._index_open_uri != uri or self._index_diags is not None:
            self._index_finish()  # (the shown file gets its diagnostics live)
        else:
            self._index_diag_timer.start()  # qmllint runs a little after the symbols

    def _index_diags_in(self, uri, diagnostics):
        pend = self._index_pending
        text = pend[2] if pend and pend[1] == uri else None
        if text is None:
            # arrived before the symbols: read what was sent
            p = QUrl(uri).toLocalFile()
            try:
                with open(p, encoding="utf-8") as fh:
                    text = fh.read()
            except (OSError, UnicodeDecodeError):
                text = ""
        self._index_diags = self._convert_diagnostics(text, diagnostics)
        if self._index_symbols_done:
            self._index_finish()

    def _index_finish(self):
        self._index_diag_timer.stop()
        pend, self._index_pending = self._index_pending, None
        if pend is None:
            return
        path, uri, text = pend
        if self._index_diags is not None:
            self._set_project_diags(path, self._index_diags, text)
        self._index_diags = None
        if self._index_open_uri == uri:
            self._index_open_uri = ""
            if self._client is not None:
                self._client.notify("textDocument/didClose", {"textDocument": {"uri": uri}})
        self._index_busy = False
        self._index_inflight = ""
        self._index_done += 1
        self.indexChanged.emit()
        QTimer.singleShot(0, self._index_next)

    # ----------------------------------------------------------- project diagnostics
    projectDiagnosticsChanged = Signal()
    projectDiagnostics = Property("QVariantList", lambda self: self._pdiag_rows, notify=projectDiagnosticsChanged)
    projectErrorCount = Property(int, lambda self: sum(1 for r in self._pdiag_rows if r["severity"] == 1),
                                 notify=projectDiagnosticsChanged)
    projectWarningCount = Property(int, lambda self: sum(1 for r in self._pdiag_rows if r["severity"] == 2),
                                   notify=projectDiagnosticsChanged)
    projectInfoCount = Property(int, lambda self: sum(1 for r in self._pdiag_rows if r["severity"] > 2),
                                notify=projectDiagnosticsChanged)

    def _set_project_diags(self, path, diags, text):
        self._project_texts[path] = text
        if self._project_diags.get(path) != diags:
            self._project_diags[path] = diags
            self._pdiag_timer.start()

    def _rebuild_project_diags(self):
        base = self._project_dir
        rows = []
        for path in sorted(self._project_diags, key=lambda p: os.path.relpath(p, base).lower() if base else p.lower()):
            rel = os.path.relpath(path, base) if base and path.startswith(base + os.sep) else path
            for i, d in enumerate(self._project_diags[path]):
                fixes = self._suggested_fixes(d)
                usable = [f for f in fixes if not f["placeholder"]]
                rows.append({"path": path, "file": rel, "index": i, "line": d["line"], "character": d["character"],
                             "severity": d["severity"], "message": d["message"],
                             "fix": usable[0]["title"] if usable else "",
                             "fixDetail": usable[0]["detail"] if usable else "",
                             "autoFix": bool(usable and usable[0]["auto"]),
                             "needsInput": bool(fixes) and not usable})
        self._pdiag_rows = rows
        self.projectDiagnosticsChanged.emit()

    @staticmethod
    def _suggested_fixes(d) -> list:
        """qmllint's suggestions carried in the diagnostic: [{title, detail, edits, auto, placeholder}]."""
        out = []
        for sg in ((d.get("_raw") or {}).get("data") or {}).get("suggestions") or []:
            edits = [{"startLine": e.get("lspBeginLine", 0), "startChar": e.get("lspBeginCharacter", 0),
                      "endLine": e.get("lspEndLine", 0), "endChar": e.get("lspEndCharacter", 0),
                      "text": e.get("replacement", "")} for e in sg.get("documentEdits") or []]
            if not edits:
                continue
            detail = " ".join(str(sg.get("message", "")).split())
            out.append({"title": _fix_title(detail, edits), "detail": detail, "edits": edits,
                        "auto": bool(sg.get("autoApplicable")),
                        "placeholder": any("<id>" in e["text"] for e in edits)})
        return out

    def _apply_file_fixes(self, path, fixes) -> int:
        """Apply non-overlapping fixes to one file (through the app, as an
        unsaved, undoable change); 0 if the file changed since it was checked."""
        if self.edit_handler is None or path not in self._project_texts:
            return 0
        chosen, taken = [], []
        for f in sorted(fixes, key=lambda f: min((e["startLine"], e["startChar"]) for e in f["edits"])):
            spans = [((e["startLine"], e["startChar"]), (e["endLine"], e["endChar"])) for e in f["edits"]]
            if any(a < tb and ta < b or (a == b == ta) for a, b in spans for ta, tb in taken):
                continue  # overlaps one already chosen: fixed on the next round
            taken += spans
            chosen.append(f)
        if not chosen:
            return 0
        basis = self._project_texts[path]
        new = self.edit_handler(path, basis, [e for f in chosen for e in f["edits"]])
        if new is None:
            return 0
        # check again what is there now (the shown file updates by itself)
        if not (self._open and QUrl.fromLocalFile(path).toString() == self._uri):
            self.recheck(path, new)
        return len(chosen)

    @Slot(str, int, result=bool)
    def applyProjectFix(self, path, index):  # noqa: N802
        diags = self._project_diags.get(path) or []
        if not 0 <= index < len(diags):
            return False
        fixes = [f for f in self._suggested_fixes(diags[index]) if not f["placeholder"]]
        return bool(fixes) and self._apply_file_fixes(path, fixes[:1]) > 0

    @Slot(str, result=int)
    def applyProjectFixes(self, path):  # noqa: N802
        """Every automatic (safe) fix of one file, or of all files for ""."""
        total = 0
        for p in ([path] if path else list(self._project_diags)):
            fixes = [f for d in self._project_diags.get(p) or [] for f in self._suggested_fixes(d)[:1]
                     if f["auto"] and not f["placeholder"]]
            if fixes:
                total += self._apply_file_fixes(p, fixes)
        return total

    @Slot(str, str)
    def documentEdited(self, path, text):  # noqa: N802
        """A document changed outside the source view (design view, undo):
        keep its findings in the project list current."""
        if not path or not path.endswith(".qml"):
            return
        p = os.path.abspath(path)
        if (self._open and QUrl.fromLocalFile(p).toString() == self._uri) or self._project_texts.get(p) == text:
            return  # the source view keeps it current / nothing new
        if p in self._project_diags or p in self._index_cache:
            self.recheck(p, text)

    @Slot(str, str)
    def recheck(self, path, text):  # noqa: N802
        """Check this (unsaved) text of a file instead of what is on disk."""
        p = os.path.abspath(path)
        self._index_overrides[p] = text
        self._index_stat.pop(p, None)
        self._index_cache.pop(p, None)
        self.indexFiles([p], self._project_dir)
        self.prioritize(p)

    def _on_index_file_changed(self, path):
        self._index_changed.add(path)
        self._index_watch_timer.start()

    def _reindex_changed(self):
        paths, self._index_changed = sorted(self._index_changed), set()
        for p in paths:  # saved by replacing the file: watch the new one
            if os.path.exists(p) and p not in self._index_watcher.files():
                self._index_watcher.addPath(p)
        self.indexFiles(paths, self._project_dir)

    def _prime_types(self):
        """Have qmlls load the imported modules' types once, so the first
        completion (and semantic colours) in the source view come quickly."""
        if self._primed_root == self._root or self._client is None or not self._index_cache:
            return
        path = next((p for p in self._index_cache if self._root_for(p) == self._root), "")
        if not path:
            return
        text = self._index_cache[path][0]
        uri = QUrl.fromLocalFile(path).toString()
        own = self._open and uri == self._uri
        if not own:
            self._client.notify("textDocument/didOpen", {"textDocument": {
                "uri": uri, "languageId": "qml", "version": self._next_version(), "text": text}})
        m = re.search(r"^[A-Za-z_][\w.]*(?:\s+on\s+\w+)?\s*\{", text, re.M)
        line = text.count("\n", 0, m.start()) + 1 if m else 0
        self._priming = True
        self._primed_root = self._root
        gen = self._index_gen
        self.indexChanged.emit()

        def done(*_a):
            if gen != self._index_gen:
                return
            if not own and not (self._open and uri == self._uri) and self._client is not None:
                self._client.notify("textDocument/didClose", {"textDocument": {"uri": uri}})
            self._priming = False
            self.indexChanged.emit()
        self._client.request("textDocument/completion", {
            "textDocument": {"uri": uri}, "position": {"line": line, "character": 0}}, done)

    # ----------------------------------------------------------- semantic highlighting
    # qmlls tells what each identifier is (id, property, method, enum value…).
    # KSyntaxHighlighting colours every token itself, so semantic colours cannot
    # be layered onto it; for QML with semantic highlighting on, Kreator's own
    # highlighter (semantic.QmlHighlighter) draws both the lexical and the
    # semantic colours, from the same Kate theme.
    _STYLE_FOR = {
        "namespace": "DataType", "type": "DataType", "enum": "DataType",
        "parameter": "Variable", "variable": "Variable", "jsScopeVar": "Variable",
        "property": "Attribute", "field": "Attribute", "qmlRootObjectProperty": "Attribute",
        "qmlScopeObjectProperty": "Attribute", "qmlExternalObjectProperty": "Attribute",
        "enumMember": "Constant", "qmlStateName": "Constant", "method": "Function",
        "qmlLocalId": "Extension", "qmlExternalId": "Extension", "jsGlobalVar": "BuiltIn",
        "jsImportVar": "Import", "keyword": "Keyword", "comment": "Comment", "string": "String",
        "number": "DecVal", "regexp": "SpecialString", "operator": "Operator", "decorator": "Annotation",
    }
    highlighterChanged = Signal()

    def _semantic_enabled(self):
        enabled, command = self._config()
        return enabled and bool(self._settings().get("lsp", {}).get("semantic", True)) and bool(find_qmlls(command))

    ownHighlighting = Property(bool, lambda self: self._had_hl, notify=highlighterChanged)

    @Slot(QObject)
    def attachDocument(self, quick_document):  # noqa: N802
        self._sem_doc = quick_document
        self._update_highlighter()

    def _update_highlighter(self):
        doc = self._sem_doc.textDocument() if self._sem_doc is not None and hasattr(self._sem_doc, "textDocument") else None
        # Kreator's highlighters handle both .qml and .ui while semantic
        # highlighting is on, so changing documents never swaps between them
        # and KSyntaxHighlighting (whose queued re-highlights can outlive the
        # text they refer to)
        from .semantic import QmlHighlighter, XmlHighlighter
        want = None
        if doc is not None and self._semantic_enabled():
            want = QmlHighlighter if self._is_qml else XmlHighlighter
        if self._hl is not None and type(self._hl) is not want:
            hl, self._hl = self._hl, None
            hl.setDocument(None)
            hl.deleteLater()
        if want is not None and self._hl is None:
            self._hl = want(doc)
            self._hl.set_styles(self._sem_styles)
        if (self._hl is not None) != self._had_hl:
            self._had_hl = self._hl is not None
            self.highlighterChanged.emit()

    @Slot()
    def rehighlight(self):
        """After the other highlighter went away (it clears all formats)."""
        if self._hl is not None:
            self._hl.rehighlight()

    @Slot(str)
    def setSemanticTheme(self, name):  # noqa: N802
        theme = katestyle.load_theme(name) or {}
        self._sem_styles = theme.get("text-styles", {})
        if self._hl is not None:
            self._hl.set_styles(self._sem_styles)

    def _request_semantic(self):
        if not self._open or self._client is None or not self._ready or self._hl is None:
            return
        text = self._text
        self._client.request("textDocument/semanticTokens/full", {"textDocument": {"uri": self._uri}},
                             lambda res, err, text=text: self._on_semantic(text, res, err))

    def _on_semantic(self, text, result, error):
        if error or not isinstance(result, dict) or text != self._text or self._hl is None:
            return  # outdated; the next change brings new tokens
        legend = (self._client.capabilities.get("semanticTokensProvider") or {}).get("legend", {}) if self._client else {}
        types, mods = legend.get("tokenTypes", []), legend.get("tokenModifiers", [])
        deprecated = 1 << mods.index("deprecated") if "deprecated" in mods else 0
        data = result.get("data") or []
        tokens: dict[int, list] = {}
        line = char = 0
        for i in range(0, len(data) - 4, 5):
            dl, dc, length, t, m = data[i:i + 5]
            line += dl
            char = char + dc if dl == 0 else dc
            if not 0 <= t < len(types):
                continue
            style = self._STYLE_FOR.get(types[t])
            if style:
                tokens.setdefault(line, []).append((char, length, style, types[t] == "parameter", bool(m & deprecated)))
        self._hl.set_tokens(text.split("\n"), tokens)

    # ----------------------------------------------------------- diagnostics
    def _on_notification(self, method, params):
        if method != "textDocument/publishDiagnostics" or not isinstance(params, dict):
            return
        uri = params.get("uri")
        if uri == self._index_open_uri:  # a file opened for indexing
            self._index_diags_in(uri, params.get("diagnostics", []))
            return
        if uri != self._uri:
            return  # e.g. the empty list sent when a file is closed
        out = self._convert_diagnostics(self._text, params.get("diagnostics", []))
        self._diagnostics = out
        if self._path:  # the project list follows the shown file's live state
            self._set_project_diags(os.path.abspath(self._path), out, self._text)
        self._request_fixes()
        self.diagnosticsChanged.emit()

    @staticmethod
    def _convert_diagnostics(text, diagnostics) -> list:
        lines = text.split("\n")
        out = []
        for d in diagnostics or []:
            rng = d.get("range", {})
            s, e = rng.get("start", {}), rng.get("end", {})
            msg = d.get("message", "")
            if "[unqualified]" in msg or "Unqualified access" in msg:
                word = _utf16_slice(lines, s.get("line", 0), s.get("character", 0), e.get("character", 0))
                if word in _I18N:
                    continue
            out.append({
                "line": s.get("line", 0), "character": s.get("character", 0),
                "endLine": e.get("line", 0), "endCharacter": e.get("character", 0),
                "severity": d.get("severity", 2), "message": msg, "fixes": [],
                "_raw": d,
            })
        out.sort(key=lambda d: (d["line"], d["character"]))
        return out

    # ----------------------------------------------------------- quick fixes (qmllint via code actions)
    def _request_fixes(self):
        """Ask for the code actions of every diagnostic that has suggestions."""
        self._fix_generation += 1
        gen = self._fix_generation
        self._fix_text = self._text
        if self._client is None:
            return
        for index, d in enumerate(self._diagnostics):
            raw = d["_raw"]
            if not (raw.get("data") or {}).get("suggestions"):
                continue
            self._client.request("textDocument/codeAction", {
                "textDocument": {"uri": self._uri}, "range": raw["range"],
                "context": {"diagnostics": [raw], "only": ["quickfix"]}},
                lambda res, err, gen=gen, index=index: self._on_fixes(gen, index, res))

    def _on_fixes(self, gen, index, result):
        if gen != self._fix_generation or index >= len(self._diagnostics):
            return  # the text changed meanwhile; new diagnostics bring new fixes
        d = self._diagnostics[index]
        suggestions = (d["_raw"].get("data") or {}).get("suggestions") or []
        fixes = []
        for action in result or []:
            if not isinstance(action, dict) or "edit" not in action:
                continue  # commands are not used by qmlls
            edits = []
            for uri, raw_edits in _workspace_edits(action["edit"]).items():
                if uri != self._uri and QUrl(uri).toLocalFile() != self._path:
                    edits = None  # fixes are expected to stay in this file
                    break
                edits += [_conv_edit(e) for e in raw_edits]
            if not edits:
                continue
            text = edits[0]["text"]
            auto = any(sg.get("autoApplicable") and any(de.get("replacement") == text for de in sg.get("documentEdits", []))
                       for sg in suggestions)
            fixes.append({"title": _fix_title(action.get("title", ""), edits), "detail": " ".join(action.get("title", "").split()),
                          "edits": edits, "auto": bool(auto),
                          "placeholder": "<id>" if "<id>" in text else ""})
        d["fixes"] = fixes
        self._fix_emit.start()

    @Slot(str, result=bool)
    def isFixTextCurrent(self, text):  # noqa: N802
        """Are the quick fixes for this exact text? (else they are being updated)"""
        return text == self._fix_text and not self._change_timer.isActive()


def _utf16_slice(lines, line, start, end):
    if not 0 <= line < len(lines):
        return ""
    data = lines[line].encode("utf-16-le")
    return data[start * 2:end * 2].decode("utf-16-le", errors="replace")


def apply_edits(text: str, edits: list[dict]) -> str:
    """Apply LSP-style edits (UTF-16 positions) to text, last edit first."""
    lines = text.split("\n")
    starts = [0]
    for ln in lines[:-1]:
        starts.append(starts[-1] + len(ln) + 1)

    def offset(line, char):
        if line >= len(lines):
            return len(text)
        u = lines[line].encode("utf-16-le")[: char * 2]
        return starts[line] + len(u.decode("utf-16-le", "replace"))

    for e in sorted(edits, key=lambda e: (e["startLine"], e["startChar"]), reverse=True):
        a, b = offset(e["startLine"], e["startChar"]), offset(e["endLine"], e["endChar"])
        text = text[:a] + e["text"] + text[b:]
    return text


def _workspace_edits(edit: dict) -> dict:
    """{uri: [TextEdit]} from a WorkspaceEdit ("changes" or "documentChanges")."""
    out: dict[str, list] = {}
    for uri, edits in (edit.get("changes") or {}).items():
        out.setdefault(uri, []).extend(edits)
    for change in edit.get("documentChanges") or []:
        if "textDocument" in change:
            out.setdefault(change["textDocument"]["uri"], []).extend(change.get("edits", []))
    return out


def _conv_edit(e: dict) -> dict:
    r = e["range"]
    return {"startLine": r["start"]["line"], "startChar": r["start"]["character"],
            "endLine": r["end"]["line"], "endChar": r["end"]["character"], "text": e.get("newText", "")}


def _fix_title(title: str, edits: list[dict]) -> str:
    """Short menu titles; qmlls' own titles can be long explanations."""
    title = " ".join(title.split())
    e = edits[0] if len(edits) == 1 else None
    if e is not None and (e["startLine"], e["startChar"]) == (e["endLine"], e["endChar"]):
        if e["text"] == "<id>.":
            return "Qualify with the parent’s id…"
        if e["text"].endswith("."):
            return f"Qualify with “{e['text'][:-1]}”"
        return f"Insert “{e['text']}”"
    if len(title) <= 60:
        return title
    if e is not None:
        return f"Replace with “{e['text']}”"
    return title[:57] + "…"
