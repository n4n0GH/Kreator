"""The compiled part of Kreator: Kate's editor (KTextEditor) as a QML module.

It is built from kreator/native/kateeditor with CMake the first time it's
needed (and again when its sources change). The module links the system's
libKF6TextEditor dynamically, so updates of KTextEditor from the distribution
apply without rebuilding. If it can't be built, Kreator falls back to its own
source editor.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIR = os.path.join(HERE, "native", "kateeditor")
BUILD_DIR = os.path.join(HERE, "native", "build")
QML_DIR = os.path.join(BUILD_DIR, "qml")
URI = "org.kde.kreator.kate"
PACKAGES = "kf6-ktexteditor-devel qt6-declarative-devel cmake gcc-c++"


def _plugin_file() -> str:
    found = glob.glob(os.path.join(QML_DIR, *URI.split("."), "lib*.so"))
    return found[0] if found else ""


def _sources_mtime() -> float:
    files = [os.path.join(SOURCE_DIR, f) for f in os.listdir(SOURCE_DIR)
             if f.endswith((".cpp", ".h", ".txt"))] if os.path.isdir(SOURCE_DIR) else []
    return max((os.path.getmtime(f) for f in files), default=0)


def kate_editor_module(log=None) -> tuple[str, str]:
    """(qml import dir, "") when the module is ready, else ("", why not)."""
    log = log or (lambda msg: print(msg, file=sys.stderr, flush=True))
    plugin = _plugin_file()
    if plugin and os.path.getmtime(plugin) >= _sources_mtime():
        return QML_DIR, ""
    if not os.path.isdir(SOURCE_DIR):
        return "", "the editor module's sources are missing"
    if not shutil.which("cmake"):
        return "", f"building Kate's editor needs cmake (install: {PACKAGES})"
    log("Kreator: building Kate's editor module (once; this takes a moment)…")
    try:
        if not os.path.exists(os.path.join(BUILD_DIR, "CMakeCache.txt")):
            subprocess.run(["cmake", "-S", SOURCE_DIR, "-B", BUILD_DIR, "-DCMAKE_BUILD_TYPE=RelWithDebInfo"],
                           check=True, capture_output=True, text=True, timeout=300)
        subprocess.run(["cmake", "--build", BUILD_DIR, "-j", str(os.cpu_count() or 2)],
                       check=True, capture_output=True, text=True, timeout=900)
    except subprocess.CalledProcessError as e:
        out = (e.stderr or e.stdout or "").strip().splitlines()
        hint = next((ln for ln in out if "Could not find" in ln or "error" in ln.lower()), out[-1] if out else "")
        return "", f"building Kate's editor failed ({hint.strip()[:160]}); packages needed: {PACKAGES}"
    except (OSError, subprocess.TimeoutExpired) as e:
        return "", f"building Kate's editor failed: {e}"
    return (QML_DIR, "") if _plugin_file() else ("", "the editor module was not produced by the build")
