"""Kate's editor look and behaviour for the built-in source view.

Kate's editing component (KTextEditor) is a QtWidgets part without Python or
QML bindings, so it cannot be embedded in a Kirigami window.  What *can* be
shared is everything around it:

* syntax highlighting — the same KSyntaxHighlighting engine and definitions
  (used from QML through `org.kde.syntaxhighlighting`);
* the colour theme Kate uses ("Color Theme" in katerc), including its editor
  colours for background, current line, line numbers and selection, read from
  the theme files shipped inside libKF6SyntaxHighlighting or installed by the
  user;
* Kate's font, indentation width, tabs-vs-spaces, auto brackets and line
  number settings.
"""

from __future__ import annotations

import ctypes
import glob
import json
import os

from PySide6.QtCore import QDir, QFile, QIODevice, QSettings
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QPalette

_THEME_DIR_QRC = ":/org.kde.syntax-highlighting/themes"


def _config_dir() -> str:
    return os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")


def katerc_path() -> str:
    """Kate's config; KWrite's if only that exists."""
    for name in ("katerc", "kwriterc"):
        p = os.path.join(_config_dir(), name)
        if os.path.exists(p):
            return p
    return os.path.join(_config_dir(), "katerc")


def _ensure_library():
    """Make the theme files compiled into KSyntaxHighlighting readable."""
    if QDir(_THEME_DIR_QRC).exists():
        return
    for lib in glob.glob("/usr/lib*/libKF6SyntaxHighlighting.so.6*") + glob.glob("/usr/lib/*/libKF6SyntaxHighlighting.so.6*"):
        try:
            ctypes.CDLL(lib)
            return
        except OSError:
            continue


def _theme_files():
    _ensure_library()
    data_dirs = [os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")]
    data_dirs += (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    for d in data_dirs:  # user themes override built-in ones
        yield from glob.glob(os.path.join(d, "org.kde.syntax-highlighting", "themes", "*.theme"))
    for name in QDir(_THEME_DIR_QRC).entryList():
        yield f"{_THEME_DIR_QRC}/{name}"


def _read(path: str) -> dict | None:
    f = QFile(path)
    if not f.open(QIODevice.OpenModeFlag.ReadOnly):
        return None
    try:
        return json.loads(bytes(f.readAll()).decode("utf-8"))
    except ValueError:
        return None
    finally:
        f.close()


def load_theme(name: str) -> dict | None:
    for path in _theme_files():
        data = _read(path)
        if data and data.get("metadata", {}).get("name") == name:
            return data
    return None


def _system_is_dark() -> bool:
    app = QGuiApplication.instance()
    if app is None:
        return False
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def _bool(v, default):
    if v is None:
        return default
    return str(v).lower() in ("true", "1")


def _int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def kate_style() -> dict:
    """Everything the source view needs, as plain values for QML."""
    cfg = QSettings(katerc_path(), QSettings.Format.IniFormat)
    found = os.path.exists(katerc_path())

    def val(section, key, default=None):
        return cfg.value(f"{section}/{key}", default)

    theme_name = val("KTextEditor Renderer", "Color Theme") or ""
    theme = load_theme(theme_name) if theme_name else None
    if theme is None:  # Kate follows the system colours by default
        theme_name = "Breeze Dark" if _system_is_dark() else "Breeze Light"
        theme = load_theme(theme_name) or {}
    ec = theme.get("editor-colors", {})
    normal = theme.get("text-styles", {}).get("Normal", {})

    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font_str = val("KTextEditor Renderer", "Text Font")
    if font_str:
        f = QFont()
        if f.fromString(font_str if isinstance(font_str, str) else ",".join(font_str)):
            font = f

    def color(key, fallback=""):
        return ec.get(key, fallback)

    indent = val("KTextEditor Document", "Indentation Width", 4)
    try:
        indent = max(1, int(indent))
    except (TypeError, ValueError):
        indent = 4
    return {
        "found": found,
        "theme": theme_name,
        "fontFamily": font.family(),
        "fontPointSize": font.pointSizeF() if font.pointSizeF() > 0 else 10,
        "background": color("BackgroundColor"),
        "text": normal.get("text-color", ""),
        "selectedText": normal.get("selected-text-color", ""),
        "selection": color("TextSelection"),
        "currentLine": color("CurrentLine"),
        "lineNumbers": color("LineNumbers"),
        "currentLineNumber": color("CurrentLineNumber"),
        "border": color("IconBorder"),
        "separator": color("Separator", color("LineNumbers")),
        "bracketMatching": color("BracketMatching"),
        "searchHighlight": color("SearchHighlight"),
        "replaceHighlight": color("ReplaceHighlight"),
        "indentWidth": indent,
        "replaceTabs": _bool(val("KTextEditor Document", "ReplaceTabsDyn"), True),
        "autoBrackets": _bool(val("KTextEditor View", "Auto Brackets"), True),
        "lineNumbersShown": _bool(val("KTextEditor View", "Line Numbers"), True),
        "animateBrackets": _bool(val("KTextEditor Renderer", "Animate Bracket Matching"), False),
        "dynamicWordWrap": _bool(val("KTextEditor View", "Dynamic Word Wrap"), True),
        "wrapAlignIndent": _int(val("KTextEditor View", "Dynamic Word Wrap Align Indent"), 80),
    }
