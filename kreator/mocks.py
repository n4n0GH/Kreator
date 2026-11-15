"""Stand-ins for QML modules that only exist inside an application binary.

Many apps (e.g. cxx-qt / CMake `qt_add_qml_module` with a static plugin) define
their own QML module whose C++/Rust types live in the executable.  Outside the
app such an import fails with 'module "x" is not installed'.  For previews we
build a substitute module in a temporary import directory:

* QML types come from the module's build `qmldir`, with each file taken from the
  source directory next to the opened document when it exists there (so edits
  show up), otherwise from the build copy;
* C++ types described in the build's `plugin.qmltypes` become stub QML objects
  with the same properties (default values), signals, methods and enums;
* without any build output, the .qml files next to the document are used.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import tempfile
import time

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".cache", "deps", "incremental", ".fingerprint"}
_DEFAULTS = {
    "bool": "false", "int": "0", "uint": "0", "double": "0", "float": "0", "qreal": "0",
    "qlonglong": "0", "qulonglong": "0", "QString": '""', "QUrl": '""', "QStringList": "[]",
    "QVariantList": "[]", "QVariantMap": "({})", "QColor": '"transparent"',
}


def _find_qmldirs(start_dir: str, uri: str, max_up: int = 5, max_depth: int = 9) -> list[str]:
    """qmldir files declaring `module uri`, searched below the ancestors of start_dir."""
    rel = uri.replace(".", os.sep)
    found = []
    seen_roots = set()
    d = os.path.abspath(start_dir)
    for _ in range(max_up + 1):
        if d in seen_roots:
            break
        seen_roots.add(d)
        base_depth = d.rstrip(os.sep).count(os.sep)
        for root, dirs, files in os.walk(d):
            depth = root.count(os.sep) - base_depth
            dirs[:] = [x for x in dirs if x not in _SKIP_DIRS and not x.startswith(".") and depth < max_depth]
            if "qmldir" in files and root.endswith(rel):
                path = os.path.join(root, "qmldir")
                try:
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        if re.search(r"^\s*module\s+" + re.escape(uri) + r"\s*$", fh.read(), re.M):
                            found.append(path)
                except OSError:
                    pass
        if found:
            break
        parent = os.path.dirname(d)
        if parent == d or os.path.exists(os.path.join(d, ".git")):
            break
        d = parent
    # newest build output first
    found.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return found


_QMLDIR_KEYWORDS = {"module", "plugin", "optional", "classname", "typeinfo", "prefer", "depends", "import",
                    "designersupported", "linktarget", "default", "static", "system"}


def _qmldir_module(path: str) -> tuple[str, set[str]]:
    """(the module's URI, the base names of the QML files it lists)."""
    uri, files = "", set()
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) == 2 and parts[0] == "module":
                    uri = parts[1]
                elif len(parts) >= 3 and parts[0] not in _QMLDIR_KEYWORDS and parts[-1].endswith(".qml"):
                    files.add(os.path.basename(parts[-1]))
    except OSError:
        pass
    return uri, files


_PROJECT_FILES = ("CMakeLists.txt", "Cargo.toml", "meson.build")
_module_scans: dict[str, tuple[float, list[tuple[str, str, set[str]]]]] = {}


def _project_root(src_dir: str, max_up: int = 5) -> str | None:
    """The project's folder: the one with its repository, else the outermost
    one with a build description, a few levels up at most (None: not in a
    project, and nowhere to look for its build)."""
    root = None
    d = src_dir
    for _ in range(max_up + 1):
        if os.path.exists(os.path.join(d, ".git")):
            return d
        if any(os.path.isfile(os.path.join(d, f)) for f in _PROJECT_FILES):
            root = d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return root


def _project_modules(root: str, max_depth: int = 9, keep: float = 10.0) -> list[tuple[str, str, set[str]]]:
    """(qmldir, URI, listed QML files) of the modules below `root`. Looked up
    again after a while only: previews are made anew as one types."""
    now = time.monotonic()
    cached = _module_scans.get(root)
    if cached and now - cached[0] < keep:
        return cached[1]
    found = []
    base_depth = root.rstrip(os.sep).count(os.sep)
    for d, dirs, files in os.walk(root):
        depth = d.count(os.sep) - base_depth
        dirs[:] = [x for x in dirs if x not in _SKIP_DIRS and not x.startswith(".") and depth < max_depth]
        if "qmldir" in files:
            path = os.path.join(d, "qmldir")
            uri, listed = _qmldir_module(path)
            if uri and listed:
                found.append((path, uri, listed))
    _module_scans[root] = (now, found)
    return found


def own_module(doc_path: str) -> str | None:
    """The URI of the module that the document is a part of, from the build's
    qmldir that lists it (None: not known).

    The files of a module (`qt_add_qml_module`) use its other types, the C++
    ones too, without importing it. From the source folder that only works
    for the QML files next to the document: there is no qmldir there."""
    if not doc_path:
        return None
    src_dir = os.path.dirname(os.path.abspath(doc_path))
    if os.path.isfile(os.path.join(src_dir, "qmldir")):
        return None
    root = _project_root(src_dir)
    if root is None:
        return None
    name = os.path.basename(doc_path)
    try:
        siblings = {f for f in os.listdir(src_dir) if f.endswith(".qml")}
    except OSError:
        return None
    best = None
    for path, uri, listed in _project_modules(root):
        if not listed & siblings:
            continue
        try:
            # the one that lists the document itself, then most of the
            # folder's files, then the newest build
            key = (name in listed, len(listed & siblings), os.path.getmtime(path))
        except OSError:
            continue
        if best is None or key > best[0]:
            best = (key, uri)
    return best[1] if best else None


# --------------------------------------------------------------------------- qmltypes

def _parse_qmltypes(text: str) -> list[dict]:
    """Very small reader for the QML-like qmltypes format."""
    toks = re.findall(r'"(?:\\.|[^"\\])*"|[A-Za-z_][\w.]*|-?\d+(?:\.\d+)?|[{}\[\]:;,]', text)
    pos = 0

    def value():
        nonlocal pos
        t = toks[pos]
        if t == "[":
            pos += 1
            out = []
            while toks[pos] != "]":
                if toks[pos] != ",":
                    out.append(value())
                else:
                    pos += 1
            pos += 1
            return out
        pos += 1
        return t[1:-1] if t.startswith('"') else t

    def obj():
        nonlocal pos
        kind = toks[pos]
        pos += 2  # name, {
        node = {"_kind": kind, "_children": []}
        while toks[pos] != "}":
            if toks[pos] == ";":
                pos += 1
                continue
            name = toks[pos]
            if toks[pos + 1] == ":":
                pos += 2
                node[name] = value()
            elif toks[pos + 1] == "{":
                node["_children"].append(obj())
            else:
                pos += 1
        pos += 1
        return node

    while pos < len(toks) and toks[pos] != "Module":
        pos += 1
    if pos >= len(toks):
        return []
    return [c for c in obj()["_children"] if c["_kind"] == "Component"]


def _ident(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z_][\w]*", name or "")) and name not in ("objectName",)


def _stub_qml(comp: dict) -> str:
    lines = []
    if comp.get("isSingleton") == "true":
        lines.append("pragma Singleton")
    proto = comp.get("prototype", "QObject")
    visual = "Item" in proto or "Quick" in proto
    lines += ["import QtQuick", "", ("Item" if visual else "QtObject") + " {"]
    used = set()
    for ch in comp["_children"]:
        kind = ch["_kind"]
        name = ch.get("name", "")
        if kind == "Property" and _ident(name) and name not in used:
            used.add(name)
            t = ch.get("type", "var")
            default = _DEFAULTS.get(t)
            if ch.get("isList") == "true":
                default = "[]"
            lines.append(f"    property var {name}" + (f": {default}" if default else ""))
    for ch in comp["_children"]:
        kind = ch["_kind"]
        name = ch.get("name", "")
        if kind == "Signal" and name.endswith("Changed") and name[:-7] in used:
            continue  # QML creates the change signal of a property itself
        if kind == "Signal" and _ident(name) and name not in used:
            used.add(name)
            params = [p.get("name", f"a{i}") for i, p in enumerate(ch["_children"]) if p["_kind"] == "Parameter"]
            lines.append(f"    signal {name}({', '.join('var ' + p for p in params)})")
        elif kind == "Method" and _ident(name) and name not in used:
            used.add(name)
            params = [p.get("name", f"a{i}") for i, p in enumerate(ch["_children"]) if p["_kind"] == "Parameter"]
            params = [p if _ident(p) else f"a{i}" for i, p in enumerate(params)]
            ret = _DEFAULTS.get(ch.get("returnType", ""), "undefined")
            lines.append(f"    function {name}({', '.join(params)}) {{ return {ret} }}")
        elif kind == "Enum" and re.fullmatch(r"[A-Z]\w*", name):
            vals = [v for v in ch.get("values", []) if re.fullmatch(r"[A-Z]\w*", v)]
            if vals:
                lines.append(f"    enum {name} {{ {', '.join(vals)} }}")
    lines.append("}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- builder

class MockModules:
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="kreator-modules-")
        self.built: dict[str, str] = {}  # uri -> description

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def build(self, uri: str, doc_path: str, own: bool = False) -> str | None:
        """Create a stand-in for `uri`; return a short description or None.

        `own`: the document is one of the module's files (see own_module())."""
        if uri in self.built:
            return self.built[uri]
        src_dir = os.path.dirname(os.path.abspath(doc_path)) if doc_path else os.getcwd()
        target = os.path.join(self.root, uri.replace(".", os.sep))
        os.makedirs(target, exist_ok=True)
        entries: list[str] = []
        stubs: list[str] = []
        origin = ""

        qmldirs = _find_qmldirs(src_dir, uri)
        if qmldirs:
            qmldir = qmldirs[0]
            mdir = os.path.dirname(qmldir)
            origin = os.path.relpath(mdir, src_dir)
            with open(qmldir, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
            for line in lines:
                parts = line.split()
                if not parts or parts[0] in ("module", "plugin", "optional", "classname", "typeinfo",
                                             "prefer", "depends", "import", "designersupported", "linktarget"):
                    if parts and parts[0] in ("depends", "import"):
                        entries.append(line)
                    continue
                singleton = parts[0] == "singleton"
                p = parts[1:] if singleton or parts[0] == "internal" else parts
                if len(p) < 3:
                    continue
                name, rel = p[0], p[-1]
                build_file = os.path.join(mdir, rel)
                source_file = os.path.join(src_dir, os.path.basename(rel))
                real = source_file if os.path.isfile(source_file) else build_file
                if not os.path.isfile(real):
                    continue
                self._link(real, os.path.join(target, rel))
                entries.append(line)
            if own:
                # files of the folder that the build doesn't know yet
                listed = {ln.split()[-1] for ln in entries}
                version = next((ln.split()[-2] for ln in entries if ln.endswith(".qml")), "1.0")
                for f in sorted(os.listdir(src_dir)):
                    if f.endswith(".qml") and f[:1].isupper() and f not in listed:
                        self._link(os.path.join(src_dir, f), os.path.join(target, f))
                        entries.append(f"{f[:-4]} {version} {f}")
            # stand-ins for compiled types
            typeinfo = next((ln.split()[1] for ln in lines if ln.startswith("typeinfo ")), "plugin.qmltypes")
            tpath = os.path.join(mdir, typeinfo)
            if not os.path.isfile(tpath):
                # (not every build names it in the qmldir)
                tpath = next(iter(sorted(glob.glob(os.path.join(mdir, "*.qmltypes")))), tpath)
            if os.path.isfile(tpath):
                with open(tpath, encoding="utf-8", errors="replace") as fh:
                    comps = _parse_qmltypes(fh.read())
                for comp in comps:
                    for exp in comp.get("exports", []) if isinstance(comp.get("exports"), list) else []:
                        m = re.fullmatch(re.escape(uri) + r"/(\w+) ([\d.]+)", exp)
                        if not m:
                            continue
                        name, ver = m.group(1), m.group(2)
                        fname = f"_stubs/{name}.qml"
                        os.makedirs(os.path.join(target, "_stubs"), exist_ok=True)
                        with open(os.path.join(target, fname), "w", encoding="utf-8") as fh:
                            fh.write(_stub_qml(comp))
                        prefix = "singleton " if comp.get("isSingleton") == "true" else ""
                        entries.append(f"{prefix}{name} {ver} {fname}")
                        stubs.append(name)
                        break
            # companion files (js, images …) next to linked QML files
            for line in list(entries):
                parts = line.split()
                if parts and parts[-1].endswith(".qml") and not parts[-1].startswith("_stubs/"):
                    rel_dir = os.path.dirname(parts[-1])
                    for d in (os.path.join(mdir, rel_dir), src_dir):
                        if not os.path.isdir(d):
                            continue
                        for f in os.listdir(d):
                            if not f.endswith(".qml") and f != "qmldir" and os.path.isfile(os.path.join(d, f)):
                                self._link(os.path.join(d, f), os.path.join(target, rel_dir, f), keep=True)
        else:
            # no build output: treat the document's directory as the module
            for f in sorted(os.listdir(src_dir)):
                if f.endswith(".qml") and f[:1].isupper():
                    self._link(os.path.join(src_dir, f), os.path.join(target, f))
                    entries.append(f"{f[:-4]} 1.0 {f}")
                elif not f.endswith(".qml") and f != "qmldir" and os.path.isfile(os.path.join(src_dir, f)):
                    self._link(os.path.join(src_dir, f), os.path.join(target, f), keep=True)
            origin = "."
        if not entries:
            return None
        # The stand-in's own qmldir. Never a link to the real one (the
        # companion files above are links): writing it would go through the
        # link, and replace the qmldir of the user's build.
        own_qmldir = os.path.join(target, "qmldir")
        if os.path.islink(own_qmldir):
            os.remove(own_qmldir)
        with open(own_qmldir, "w", encoding="utf-8") as fh:
            fh.write(f"module {uri}\n" + "\n".join(dict.fromkeys(entries)) + "\n")
        if origin == ".":
            desc = f"{uri} (the QML files in this folder"
        else:
            desc = f"{uri} (built module in {origin}, with this folder's QML sources"
        desc += f"; dummy {', '.join(stubs)} objects)" if stubs else ")"
        self.built[uri] = desc
        return desc

    @staticmethod
    def _link(src: str, dst: str, keep: bool = False):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.lexists(dst):
            if keep:
                return
            os.remove(dst)
        try:
            os.symlink(src, dst)
        except OSError:
            shutil.copy2(src, dst)
