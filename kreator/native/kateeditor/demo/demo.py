"""Prototype: Kate's editor (KTextEditor) inside a Kirigami window.

Run from the Kreator source tree after building the module:
    cmake -S kreator/native/kateeditor -B kreator/native/build && cmake --build kreator/native/build
    python3 kreator/native/kateeditor/demo/demo.py [file.qml]

KTextEditor reads its settings from the application's own config
(~/.config/kreatorrc). To look like Kate, the editor sections of
~/.config/katerc are copied there first (katerc itself is only read).
"""

import configparser
import os
import sys

from PySide6.QtCore import QCoreApplication, QStandardPaths, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD_QML = os.path.normpath(os.path.join(HERE, "..", "..", "build", "qml"))
EDITOR_GROUPS = ("KTextEditor Document", "KTextEditor View", "KTextEditor Renderer", "KTextEditor Editor")


def copy_kate_settings():
    """Kate's editor settings -> kreatorrc (only those groups; read-only for katerc)."""
    cfg_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericConfigLocation)
    src, dst = os.path.join(cfg_dir, "katerc"), os.path.join(cfg_dir, "kreatorrc")
    if not os.path.exists(src):
        return
    kate = configparser.RawConfigParser(strict=False, interpolation=None)
    kate.optionxform = str
    kate.read(src, encoding="utf-8")
    ours = configparser.RawConfigParser(strict=False, interpolation=None)
    ours.optionxform = str
    if os.path.exists(dst):
        ours.read(dst, encoding="utf-8")
    for g in EDITOR_GROUPS:
        if kate.has_section(g):
            if ours.has_section(g):
                ours.remove_section(g)
            ours.add_section(g)
            for k, v in kate.items(g):
                ours.set(g, k, v)
    with open(dst, "w", encoding="utf-8") as fh:
        ours.write(fh, space_around_delimiters=False)


def main():
    QCoreApplication.setOrganizationName("kreator")
    QCoreApplication.setApplicationName("kreator")
    if not os.environ.get("QT_QUICK_CONTROLS_STYLE"):
        QQuickStyle.setStyle("org.kde.desktop")
    copy_kate_settings()
    app = QApplication(sys.argv)
    engine = QQmlApplicationEngine()
    engine.addImportPath(BUILD_QML)
    text = ""
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as fh:
            text = fh.read()
    else:
        with open(os.path.join(HERE, "..", "..", "..", "qml", "PropertyRow.qml"), encoding="utf-8") as fh:
            text = fh.read()
    engine.rootContext().setContextProperty("demoText", text)
    engine.load(QUrl.fromLocalFile(os.path.join(HERE, "Demo.qml")))
    if not engine.rootObjects():
        return 1
    root = engine.rootObjects()[0]  # keep a reference (PySide)
    ret = app.exec()
    del root
    sys.stdout.flush()
    os._exit(ret)  # skip PySide's teardown, as Kreator does


if __name__ == "__main__":
    sys.exit(main())
