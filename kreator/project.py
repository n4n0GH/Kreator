"""Folders opened as projects: which files to show in the project sidebar,
and new projects."""

from __future__ import annotations

import json
import os
from xml.sax.saxutils import escape as _xml_escape

UI_EXTENSIONS = (".qml", ".ui")
SKIP_DIRS = {"build", "target", "node_modules", "__pycache__", "dist", "_build", "out", "venv", ".venv"}


def _skip_dir(name: str) -> bool:
    return (name.startswith(".") or name in SKIP_DIRS or name.startswith(("build-", "cmake-build"))
            or name.endswith(".egg-info"))


def scan(root: str, max_files: int = 5000) -> tuple[list[str], list[str]]:
    """(files, dirs) relative to root: UI files, and the folders that contain some.

    Hidden folders and build output are skipped, as are folders without any
    .qml or .ui file below them.
    """
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not _skip_dir(d))
        rel = os.path.relpath(dirpath, root)
        for f in sorted(filenames, key=str.lower):
            if f.lower().endswith(UI_EXTENSIONS) and not f.startswith((".kreator-", ".qviewer-")):
                files.append(f if rel == "." else os.path.join(rel, f))
                if len(files) >= max_files:
                    break
        if len(files) >= max_files:
            break
    dirs = set()
    for f in files:
        d = os.path.dirname(f)
        while d:
            dirs.add(d)
            d = os.path.dirname(d)
    return files, sorted(dirs, key=str.lower)


def tree_rows(root: str, files: list[str], dirs: list[str], collapsed: set[str]) -> list[dict]:
    """Rows for a flattened tree: folders first, then files, alphabetically."""
    children: dict[str, list[tuple[bool, str]]] = {}
    for d in dirs:
        children.setdefault(os.path.dirname(d), []).append((True, d))
    for f in files:
        children.setdefault(os.path.dirname(f), []).append((False, f))
    rows: list[dict] = []

    def add(parent: str, depth: int):
        for is_dir, rel in sorted(children.get(parent, []), key=lambda e: (not e[0], os.path.basename(e[1]).lower())):
            path = os.path.join(root, rel)
            row = {"key": path, "relPath": rel, "name": os.path.basename(rel), "depth": depth, "isDir": is_dir,
                   "expanded": is_dir and rel not in collapsed,
                   "kind": "dir" if is_dir else ("ui" if rel.lower().endswith(".ui") else "qml")}
            rows.append(row)
            if is_dir and rel not in collapsed:
                add(rel, depth + 1)

    add("", 0)
    return rows


def fuzzy_score(query: str, text: str) -> int:
    """>0 if all characters of query appear in text in order; higher is better."""
    q, t = query.lower(), text.lower()
    if not q:
        return 1
    if q in t:
        # contiguous match; a match in the file name scores best
        name = t.rsplit("/", 1)[-1]
        return 1000 - t.index(q) + (500 if q in name else 0) + (300 if name.startswith(q) else 0)
    i = 0
    score = 100
    for ch in t:
        if i < len(q) and ch == q[i]:
            i += 1
        elif i:
            score -= 1
    return max(1, score) if i == len(q) else 0


# --------------------------------------------------------------------------- new projects
# A project is a folder with its user interface files; a new one starts with
# one file. The QML ones need nothing else to run: `qml6 Main.qml` (which is
# why their texts are translated with qsTr(): i18n() only exists in an
# application that sets up KLocalizedContext).
# In the texts, @TITLE@ is the project's name as a QML string literal (or, in
# a form, as XML text) and @CLASS@ a class name made from it.

PROJECT_TEMPLATES = {
    "kirigami-app": ("Main.qml", """import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root

    title: qsTr(@TITLE@)
    width: Kirigami.Units.gridUnit * 24
    height: Kirigami.Units.gridUnit * 28

    pageStack.initialPage: Kirigami.ScrollablePage {
        id: page

        title: qsTr(@TITLE@)
    }
}
"""),
    "qtquick": ("Main.qml", """import QtQuick
import QtQuick.Layouts
import QtQuick.Controls

ApplicationWindow {
    id: window

    width: 640
    height: 480
    visible: true
    title: qsTr(@TITLE@)

    ColumnLayout {
        anchors.centerIn: parent

        Label {
            text: qsTr(@TITLE@)
        }
    }
}
"""),
    "widgets-form": ("form.ui", """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>@CLASS@</class>
 <widget class="QWidget" name="@CLASS@">
  <property name="geometry">
   <rect>
    <x>0</x>
    <y>0</y>
    <width>480</width>
    <height>360</height>
   </rect>
  </property>
  <property name="windowTitle">
   <string>@TITLE@</string>
  </property>
  <layout class="QVBoxLayout" name="verticalLayout"/>
 </widget>
 <resources/>
 <connections/>
</ui>
"""),
}
DEFAULT_PROJECT_TEMPLATE = "kirigami-app"


def project_folder(name: str, location: str) -> str:
    """The folder a project called `name` gets below `location`."""
    return os.path.join(os.path.abspath(os.path.expanduser(location.strip())), name.strip())


def project_file(name: str, location: str, template: str) -> str:
    """The file a new project starts with."""
    file_name = PROJECT_TEMPLATES.get(template, PROJECT_TEMPLATES[DEFAULT_PROJECT_TEMPLATE])[0]
    return os.path.join(project_folder(name, location), file_name)


def project_problem(name: str, location: str) -> str:
    """Why a project called `name` can't be created in `location` ("" if it can)."""
    name, location = name.strip(), location.strip()
    if not name:
        return "Give the project a name."
    if name in (".", "..") or name.startswith(".") or any(c in name for c in "/\\\0\n"):
        return "The name is used as the folder's name: it can't contain “/” or start with a dot."
    if not location:
        return "Choose the folder to create the project in."
    parent = os.path.abspath(os.path.expanduser(location))
    if os.path.exists(parent) and not os.path.isdir(parent):
        return f"{parent} is not a folder."
    folder = os.path.join(parent, name)
    if os.path.isdir(folder) and os.listdir(folder):
        return f"The folder {folder} already exists and is not empty."
    if os.path.exists(folder) and not os.path.isdir(folder):
        return f"{folder} already exists."
    # the nearest existing folder has to be writable
    probe = parent
    while probe and not os.path.exists(probe) and os.path.dirname(probe) != probe:
        probe = os.path.dirname(probe)
    if not os.access(probe, os.W_OK | os.X_OK):
        return f"You can't write to {probe}."
    return ""


def _class_name(name: str) -> str:
    words = [w for w in "".join(c if c.isalnum() else " " for c in name).split() if w]
    cls = "".join(w[:1].upper() + w[1:] for w in words)
    if not cls or not (cls[0].isalpha() and cls[0].isascii()):
        cls = "Form" + cls
    return "".join(c for c in cls if c.isascii()) or "Form"


def project_text(name: str, template: str) -> str:
    """The text of a new project's first file."""
    file_name, text = PROJECT_TEMPLATES.get(template, PROJECT_TEMPLATES[DEFAULT_PROJECT_TEMPLATE])
    name = name.strip()
    if file_name.endswith(".ui"):
        return text.replace("@CLASS@", _class_name(name)).replace("@TITLE@", _xml_escape(name))
    # (a JSON string is a valid QML string literal)
    return text.replace("@TITLE@", json.dumps(name, ensure_ascii=False))


def create_project(name: str, location: str, template: str = DEFAULT_PROJECT_TEMPLATE) -> tuple[str, str]:
    """Create the project's folder and its first file; returns (folder, file).

    Raises ValueError (with a message for the user) if it can't be created."""
    problem = project_problem(name, location)
    if problem:
        raise ValueError(problem)
    folder = project_folder(name, location)
    path = project_file(name, location, template)
    try:
        os.makedirs(folder, exist_ok=True)
        # ("x": never over a file that appeared meanwhile)
        with open(path, "x", encoding="utf-8") as fh:
            fh.write(project_text(name, template))
    except OSError as e:
        raise ValueError(f"Could not create {path}: {e.strerror}") from e
    return folder, path
