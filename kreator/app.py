"""Application entry point."""

from __future__ import annotations

import argparse
import os
import signal
import sys

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlContext
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from . import __version__
from .backend import Backend
from .preview import PluginPreloader, UiImageProvider
from .lsp import LanguageSupport
from . import native
from .textlayout import TextLayout

QML_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qml")


def _migrate_from_qviewer():
    """Kreator used to be called QViewer: take over its settings and session once."""
    import shutil
    from PySide6.QtCore import QSettings, QStandardPaths
    moves = [(QSettings("qviewer", "qviewer").fileName(), QSettings("kreator", "kreator").fileName())]
    data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    moves.append((os.path.join(data, "qviewer", "session.json"), os.path.join(data, "kreator", "session.json")))
    for old, new in moves:
        if os.path.isfile(old) and not os.path.exists(new):
            try:
                os.makedirs(os.path.dirname(new), exist_ok=True)
                shutil.copy2(old, new)
            except OSError:
                pass


def main(argv=None):
    argv = sys.argv if argv is None else argv
    parser = argparse.ArgumentParser(prog="kreator", description="View and edit Qt Quick / Kirigami and Qt Designer UI files.")
    parser.add_argument("file", nargs="?", help=".qml or .ui file to open")
    parser.add_argument("-I", "--import-path", action="append", default=[], help="additional QML import path")
    parser.add_argument("--new", choices=["kirigami-app", "kirigami-page", "qtquick", "widgets-form"],
                        help="start with a new document from a template")
    args, qt_args = parser.parse_known_args(argv[1:])

    if not os.environ.get("QT_QUICK_CONTROLS_STYLE"):
        QQuickStyle.setStyle("org.kde.desktop")
    QCoreApplication.setOrganizationName("kreator")
    QCoreApplication.setApplicationName("kreator")
    QCoreApplication.setApplicationVersion(__version__)
    _migrate_from_qviewer()

    # Qt WebEngine has to be set up before the application object exists, or
    # previewing a WebEngineView crashes.
    try:
        from PySide6.QtWebEngineQuick import QtWebEngineQuick
        QtWebEngineQuick.initialize()
    except ImportError:
        pass

    app = QApplication([argv[0], *qt_args])
    app.setApplicationDisplayName("Kreator")
    app.setDesktopFileName("kreator")
    if not QIcon.themeName():
        QIcon.setThemeName("breeze")
    app.setWindowIcon(QIcon.fromTheme("document-preview", QIcon.fromTheme("applications-development")))
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    engine = QQmlApplicationEngine()
    for p in args.import_path:
        engine.addImportPath(os.path.abspath(p))

    preloader = PluginPreloader(engine)
    # the application UI itself needs these (see PluginPreloader for why)
    for uri in ("QtQuick", "QtQuick.Controls", "QtQuick.Layouts", "QtQuick.Dialogs", "org.kde.kirigami",
                "org.kde.desktop", "org.kde.qqc2desktopstyle.private", "org.kde.kirigami.delegates",
                "org.kde.kirigami.layouts", "org.kde.kirigami.primitives", "org.kde.kirigami.platform",
                "org.kde.syntaxhighlighting"):
        preloader.preload_module(uri)

    ui_provider = UiImageProvider()
    engine.addImageProvider("kreatorui", ui_provider)

    backend = Backend(engine, preloader, ui_provider)
    # NB: qmlRegisterSingletonInstance() breaks QML type registration with
    # PySide 6.12, so the backend is exposed as a context property instead.
    # Not of the engine's root context, which the previews' contexts descend
    # from too: a previewed application that has a `Backend` of its own would
    # get Kreator's (and call its `undo()`). Kreator's interface is created in
    # a context of its own, which only its own QML files see.
    ui_context = QQmlContext(engine.rootContext(), engine)
    ui_context.setContextProperty("Backend", backend)
    text_layout = TextLayout()
    ui_context.setContextProperty("TextLayout", text_layout)
    extra_imports = [os.path.abspath(p) for p in args.import_path]
    backend.import_paths = extra_imports     # also for what Run starts
    lsp = LanguageSupport(backend._editor_settings, lambda: extra_imports)
    ui_context.setContextProperty("Lsp", lsp)
    backend.editorsChanged.connect(lsp.settingsChanged)

    def index_project():
        """Symbols of every project file (and open tab), fetched in the background."""
        files = [f["key"] for f in backend.projectFileList]
        files += [k for k in backend.tab_order if not k.startswith("untitled:")]
        lsp.setProjectFiles(files, backend.projectPath)
    backend.projectChanged.connect(index_project)
    lsp.edit_handler = backend.apply_text_fix   # quick fixes from the project's qmllint list
    # design view edits and undo: re-check the shown file a moment later
    from PySide6.QtCore import QTimer
    recheck_timer = QTimer(singleShot=True, interval=800)
    recheck_timer.timeout.connect(lambda: lsp.documentEdited(backend.path, backend.adapter.text())
                                  if backend.adapter is not None else None)
    backend.contentChanged.connect(recheck_timer.start)
    backend.documentChanged.connect(lambda: lsp.prioritize(backend.path))

    # Kate's editor for the source view: built once from native/, linked to the
    # system's KTextEditor (so Kate's updates reach Kreator)
    if backend._editor_settings().get("useKateEditor", True):
        kate_dir, kate_problem = native.kate_editor_module()
        if kate_dir:
            engine.addImportPath(kate_dir)
            preloader.preload_module(native.URI)
            backend.set_kate_editor(True)
        else:
            print(f"Kreator: using the built-in source editor: {kate_problem}", file=sys.stderr)
            backend.set_kate_editor(False, kate_problem)
    else:
        backend.set_kate_editor(False, "switched off in the settings")

    startup_warnings = []
    engine.warnings.connect(lambda ws: startup_warnings.extend(w.toString() for w in ws))
    # (not engine.load(), which creates in the root context)
    ui_component = QQmlComponent(engine, QUrl.fromLocalFile(os.path.join(QML_DIR, "Main.qml")))
    window = ui_component.create(ui_context)
    if window is None:
        # say why, rather than exiting silently
        for w in [e.toString() for e in ui_component.errors()] + startup_warnings:
            print(w, file=sys.stderr)
        return 1

    # the last session first (it may hold unsaved edits), then what was asked for
    backend.claimSession()
    backend.restoreSession()
    if args.file:
        backend.openFile(os.path.abspath(args.file))
    elif args.new:
        backend.newDocument(args.new)
    index_project()

    app.aboutToQuit.connect(backend.shutdown)
    app.aboutToQuit.connect(lsp.shutdown)
    ret = app.exec()
    # destroy the window and engine before the Python objects they reference
    window.deleteLater()
    app.processEvents()
    # PySide occasionally crashes while the interpreter tears down Qt objects
    # (destructor ordering). Everything is saved by now, so skip that phase.
    backend.settings.sync()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(ret)


if __name__ == "__main__":
    sys.exit(main())
