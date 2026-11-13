"""Run: starts a QML file with Qt's `qml` runtime, as `qml6 Main.qml` does in
a terminal, and collects what it prints."""

from __future__ import annotations

import os
import re
import shutil

from PySide6.QtCore import QLibraryInfo, QObject, QProcess, QProcessEnvironment, QTimer, Signal

MAX_OUTPUT_LINES = 2000
# a line that tells of a problem in the application (qml reports them and goes on)
_PROBLEM = re.compile(r"Error\b|error:|is not installed|is not a type|Cannot assign|Unable to assign|"
                      r"is not defined|No such file|failed to load|Failed to load")


def find_qml_runtime() -> str:
    """The program that runs a QML file: Qt 6's `qml` ("" if there is none)."""
    for name in ("qml6", "qml-qt6"):
        p = shutil.which(name)
        if p:
            return p
    for where in (QLibraryInfo.LibraryPath.BinariesPath, QLibraryInfo.LibraryPath.LibraryExecutablesPath):
        p = os.path.join(QLibraryInfo.path(where), "qml")
        if os.access(p, os.X_OK):
            return p
    return ""


def problem_in(line: str) -> bool:
    return bool(_PROBLEM.search(line))


class Runner(QObject):
    """One running application at a time."""

    changed = Signal()                  # started or stopped
    outputChanged = Signal()
    problemReported = Signal(str)       # the first line of a run that tells of a problem
    finished = Signal(str, int, bool)   # file name, exit code, failed (crashed, or a code other than 0)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process: QProcess | None = None
        self._lines: list[str] = []
        self._partial = ""
        self._path = ""
        self._reported = False
        self._stopping = False

    # -- state
    @property
    def running(self) -> bool:
        return self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning

    @property
    def path(self) -> str:
        """The file that is running, or ran last."""
        return self._path

    @property
    def output(self) -> str:
        return "\n".join(self._lines + ([self._partial] if self._partial else []))

    # -- running
    def start(self, path: str, import_paths=()) -> str:
        """Run `path` (stopping what runs); returns why it couldn't be ("" if it was started)."""
        program = find_qml_runtime()
        if not program:
            return ("Qt's QML runtime (qml6) was not found. It is part of Qt's declarative tools "
                    "(for example the package qt6-declarative-tools).")
        if not os.path.isfile(path):
            return f"{path} does not exist."
        self.stop(wait=True)
        self._path = path
        self._lines = [f"$ {os.path.basename(program)} {os.path.basename(path)}"]
        self._partial = ""
        self._reported = False
        self._stopping = False
        process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        # (without a terminal, Qt would send the application's messages to the journal)
        env.insert("QT_FORCE_STDERR_LOGGING", "1")
        process.setProcessEnvironment(env)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.setWorkingDirectory(os.path.dirname(path))
        args = []
        for p in import_paths:
            args += ["-I", p]
        process.setProgram(program)
        process.setArguments([*args, path])
        process.readyReadStandardOutput.connect(lambda: self._read(process))
        process.finished.connect(lambda code, status: self._finished(process, code, status))
        process.errorOccurred.connect(lambda error: self._failed(process, error))
        self._process = process
        process.start()
        self.changed.emit()
        self.outputChanged.emit()
        return ""

    def stop(self, wait=False):
        """End the running application (asked to, then made to)."""
        process = self._process
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            return
        self._stopping = True
        process.terminate()
        if wait:
            if not process.waitForFinished(1500):
                process.kill()
                process.waitForFinished(1500)
        else:
            def kill():
                # (once it has ended, it is no longer self._process, and may be deleted)
                if self._process is process and process.state() != QProcess.ProcessState.NotRunning:
                    process.kill()
            QTimer.singleShot(2000, kill)

    # -- the process
    def _read(self, process):
        if process is not self._process:
            return
        text = self._partial + bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        *lines, self._partial = text.split("\n")
        self._add(lines)

    def _add(self, lines):
        if not lines:
            return
        self._lines.extend(ln.rstrip("\r") for ln in lines)
        if len(self._lines) > MAX_OUTPUT_LINES:
            del self._lines[1:len(self._lines) - MAX_OUTPUT_LINES + 1]
        self.outputChanged.emit()
        if not self._reported:
            first = next((ln for ln in lines if problem_in(ln)), None)
            if first is not None:
                self._reported = True
                # (Main.qml:12, not file:///…/Main.qml:12)
                here = "file://" + os.path.dirname(self._path) + "/"
                self.problemReported.emit(first.strip().replace(here, ""))

    def _failed(self, process, error):
        if process is not self._process or error != QProcess.ProcessError.FailedToStart:
            return
        self._add([f"Could not start {process.program()}: {process.errorString()}"])
        self._process = None
        process.deleteLater()
        self.changed.emit()
        self.finished.emit(os.path.basename(self._path), -1, True)

    def _finished(self, process, code, status):
        if process is not self._process:
            process.deleteLater()
            return
        self._read(process)
        if self._partial:
            self._add([self._partial])
            self._partial = ""
        crashed = status == QProcess.ExitStatus.CrashExit and not self._stopping
        failed = crashed or (code != 0 and not self._stopping)
        self._add(["(stopped)" if self._stopping else "(crashed)" if crashed else f"(ended with exit code {code})"
                   if code else "(ended)"])
        self._process = None
        process.deleteLater()
        self.changed.emit()
        self.finished.emit(os.path.basename(self._path), code, failed)
