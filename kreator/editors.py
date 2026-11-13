"""Opening documents in external text editors.

Kate is supported out of the box: it is found automatically (also as a
Flatpak), opened at the selected object's line, can use a Kate session and can
reuse or start a new window.  Any other editor is configured by the user with a
command and an argument template using {file}, {line}, {column} and {dir}.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shlex
import shutil
import urllib.parse

KATE_ID = "kate"

# Templates offered when adding an editor; the user can change everything.
PRESETS = [
    {"name": "Zed", "command": "zed", "args": "{file}:{line}:{column}", "icon": "zed"},
    {"name": "Visual Studio Code", "command": "code", "args": "--goto {file}:{line}:{column}",
     "icon": "com.visualstudio.code"},
    {"name": "VSCodium", "command": "codium", "args": "--goto {file}:{line}:{column}", "icon": "vscodium"},
    {"name": "Sublime Text", "command": "subl", "args": "{file}:{line}:{column}", "icon": "sublime-text"},
    {"name": "KWrite", "command": "kwrite", "args": "--line {line} --column {column} {file}", "icon": "kwrite"},
    {"name": "Neovim (in Konsole)", "command": "konsole", "args": "-e nvim +{line} {file}", "icon": "nvim"},
    {"name": "Emacs", "command": "emacsclient", "args": "-c -n +{line}:{column} {file}", "icon": "emacs"},
    {"name": "Custom", "command": "", "args": "{file}", "icon": "accessories-text-editor"},
]

DEFAULT_SETTINGS = {
    "default": KATE_ID,
    "autoReload": True,
    "useKateStyle": True,
    "useKateEditor": True,     # Kate's editor (KTextEditor) in the source view
    "restoreSession": True,
    "keepUnsaved": True,
    "sessionInterval": 15,   # seconds between session saves; 0 = only on quit
    "lsp": {"enabled": True, "command": "", "semantic": True},
    "kate": {"session": "", "newWindow": False, "gotoObject": True},
    "custom": [],
}


class EditorError(Exception):
    pass


# --------------------------------------------------------------------------- settings

def load_settings(raw) -> dict:
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        data = json.loads(raw) if isinstance(raw, str) and raw else {}
    except ValueError:
        data = {}
    if isinstance(data, dict):
        for k in ("default", "autoReload", "useKateStyle", "useKateEditor", "restoreSession", "keepUnsaved", "sessionInterval"):
            if k in data:
                s[k] = data[k]
        if isinstance(data.get("lsp"), dict):
            s["lsp"].update({k: v for k, v in data["lsp"].items() if k in s["lsp"]})
        if isinstance(data.get("kate"), dict):
            s["kate"].update({k: v for k, v in data["kate"].items() if k in s["kate"]})
        if isinstance(data.get("custom"), list):
            s["custom"] = [normalize_custom(e) for e in data["custom"] if isinstance(e, dict)]
    return s


def normalize_custom(e: dict) -> dict:
    eid = str(e.get("id") or "")
    if not re.fullmatch(r"custom-\d+", eid):
        eid = ""
    return {"id": eid, "name": str(e.get("name") or "Editor"), "command": str(e.get("command") or ""),
            "args": str(e.get("args") or "{file}"), "icon": str(e.get("icon") or "accessories-text-editor")}


def assign_ids(settings: dict) -> dict:
    used = {e["id"] for e in settings["custom"] if e["id"]}
    n = 1
    for e in settings["custom"]:
        if not e["id"]:
            while f"custom-{n}" in used:
                n += 1
            e["id"] = f"custom-{n}"
            used.add(e["id"])
    ids = {KATE_ID} | used
    if settings["default"] not in ids:
        settings["default"] = KATE_ID
    return settings


# --------------------------------------------------------------------------- kate

def find_kate() -> list[str] | None:
    """Command to start Kate, or None."""
    path = shutil.which("kate")
    if path:
        return [path]
    for base in ("/var/lib/flatpak/app/org.kde.kate", os.path.expanduser("~/.local/share/flatpak/app/org.kde.kate")):
        if os.path.isdir(base) and shutil.which("flatpak"):
            return ["flatpak", "run", "org.kde.kate"]
    return None


def kate_sessions() -> list[str]:
    dirs = [os.path.expanduser("~/.local/share/kate/sessions"),
            os.path.expanduser("~/.var/app/org.kde.kate/data/kate/sessions")]
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        dirs.insert(0, os.path.join(xdg, "kate", "sessions"))
    names = []
    for d in dirs:
        for f in glob.glob(os.path.join(d, "*.katesession")):
            name = urllib.parse.unquote(os.path.basename(f)[: -len(".katesession")])
            if name not in names:
                names.append(name)
    return sorted(names, key=str.lower)


def kate_argv(settings: dict, file: str, line: int, column: int) -> list[str]:
    base = find_kate()
    if base is None:
        raise EditorError("Kate is not installed.")
    k = settings["kate"]
    argv = list(base)
    if k.get("session"):
        argv += ["--start", k["session"]]
    if k.get("newWindow"):
        argv.append("--new")
    if k.get("gotoObject", True) and line > 0:
        argv += ["--line", str(line)]
        if column > 0:
            argv += ["--column", str(column)]
    argv.append(file)
    return argv


# --------------------------------------------------------------------------- custom

def resolve_program(command: str) -> list[str] | None:
    """Split a command ('flatpak run x', '~/bin/zed') and check it exists."""
    try:
        parts = shlex.split(os.path.expanduser(command.strip()))
    except ValueError:
        return None
    if not parts:
        return None
    prog = parts[0]
    found = shutil.which(prog) if os.sep not in prog else (prog if os.access(prog, os.X_OK) else None)
    if not found:
        return None
    return [found, *parts[1:]]


def custom_argv(entry: dict, file: str, line: int, column: int) -> list[str]:
    prog = resolve_program(entry["command"])
    if prog is None:
        raise EditorError(f"“{entry['command'] or entry['name']}” was not found. Check the editor's path "
                          "in the external editor settings.")
    try:
        tokens = shlex.split(entry["args"] or "{file}")
    except ValueError as e:
        raise EditorError(f"The arguments of {entry['name']} are not valid: {e}") from e
    values = {"file": file, "line": str(max(line, 1)), "column": str(max(column, 1)),
              "dir": os.path.dirname(file)}
    # substitute per token, so paths with spaces stay one argument
    out = [re.sub(r"\{(file|line|column|dir)\}", lambda m: values[m.group(1)], t) for t in tokens]
    if not any("{file}" in t for t in tokens):
        out.append(file)
    return prog + out


# --------------------------------------------------------------------------- editors

def editors(settings: dict) -> list[dict]:
    """All editors for menus: id, name, icon, available, detail."""
    kate = find_kate()
    out = [{"id": KATE_ID, "name": "Kate", "icon": "kate", "available": kate is not None,
            "detail": " ".join(kate) if kate else "Not installed"}]
    for e in settings["custom"]:
        prog = resolve_program(e["command"])
        out.append({"id": e["id"], "name": e["name"], "icon": e["icon"], "available": prog is not None,
                    "detail": prog[0] if prog else (f"“{e['command']}” not found" if e["command"] else "No command set")})
    return out


def argv_for(settings: dict, editor_id: str, file: str, line: int, column: int) -> list[str]:
    if editor_id == KATE_ID:
        return kate_argv(settings, file, line, column)
    for e in settings["custom"]:
        if e["id"] == editor_id:
            return custom_argv(e, file, line, column)
    raise EditorError("This editor is not configured any more.")
