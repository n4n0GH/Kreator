"""Runs one GUI test inside a real Kreator process (started by run.py).

    python3 host.py <test file> <workspace> <run number> [Kreator arguments…]

Kreator starts as usual (the session of the workspace's data folder is
restored). Once its window is up, the test file's code for this run is
executed in Kreator's process, with these names available:

    app, win          the QApplication and Kreator's window
    backend, lsp      the Backend and LanguageSupport objects (`Backend`, `Lsp` in QML)
    page              the editor page (objectName "editorPage")
    OUT               the workspace: a fresh copy of fixtures/ for this test
    REPO              the Kreator source tree
    RUN               which run this is (0, 1, … for tests that restart Kreator)
    QTimer            PySide6.QtCore.QTimer
    check(ok, text)   report one check ("PASS text" / "FAIL text")
    find_all(pred)    every item of the window's item tree for which pred(item) is true
    by_name(name)     the visible items with this objectName
    wait_until(pred, then, timeout=20, what="")
                      call then() once pred() is true; a failed check if it
                      isn't within timeout seconds

A test ends by quitting Kreator (app.quit(), or closing the window). The
process's exit code is printed as "@@exit <code>" so that run.py sees it
even when Kreator runs inside a KWin session. An uncaught exception in the
test's code (also in a timer's callback) ends Kreator with exit code 2.
"""

from __future__ import annotations

import gc
import os
import re
import sys
import time
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from PySide6.QtCore import QObject, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import kreator.app as kreator_app  # noqa: E402

RUN_MARKER = re.compile(r"^# --- run (\d+) ---[ \t]*$", re.M)


def run_code(text: str, run: int) -> str:
    """The code of one run: the part before the first run marker (shared),
    then the part after "# --- run <run> ---". Without markers: everything."""
    parts = RUN_MARKER.split(text)
    if len(parts) == 1:
        return text
    prologue, sections = parts[0], {int(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}
    if run not in sections:
        raise SystemExit(f"{run}: no '# --- run {run} ---' section")
    # (keep line numbers: blank lines in place of the other sections)
    out = []
    for i in range(1, len(parts), 2):
        body = parts[i + 1]
        out.append(body if int(parts[i]) == run else "\n" * body.count("\n"))
    return prologue + "\n" + "".join(out)


def check(ok, text):
    print(("PASS " if ok else "FAIL ") + str(text), flush=True)


def main():
    script, work, run = sys.argv[1], sys.argv[2], int(sys.argv[3])
    extra = sys.argv[4:]
    code = compile(run_code(open(script, encoding="utf-8").read(), run), script, "exec")

    real_exit = os._exit

    def reporting_exit(status):
        print(f"@@exit {status}", flush=True)
        real_exit(status)
    os._exit = reporting_exit

    original_exec = QApplication.exec

    def exec_with_test(*_args):
        def start():
            from kreator.backend import Backend
            from kreator.lsp import LanguageSupport
            app = QApplication.instance()
            win = next((w for w in app.topLevelWindows() if w.isVisible()), None)

            def find_all(pred):
                out, stack = [], [win.contentItem()]
                while stack:
                    it = stack.pop()
                    if pred(it):
                        out.append(it)
                    stack.extend(it.childItems())
                return out

            def by_name(name):
                return [i for i in find_all(lambda it: it.objectName() == name) if i.isVisible()]

            def wait_until(pred, then, timeout=20, what=""):
                t0 = time.time()

                def tick():
                    try:
                        ok = pred()
                    except Exception:  # noqa: BLE001 - not there yet
                        ok = False
                    if ok:
                        then()
                    elif time.time() - t0 > timeout:
                        check(False, f"{what or 'condition'} (timed out)")
                        then()
                    else:
                        QTimer.singleShot(100, tick)
                tick()

            ns = {
                "__name__": "__kreator_test__",
                "app": app, "win": win, "QTimer": QTimer, "OUT": work, "REPO": REPO, "RUN": run,
                "backend": next(o for o in gc.get_objects() if isinstance(o, Backend)),
                "lsp": next(o for o in gc.get_objects() if isinstance(o, LanguageSupport)),
                "page": win.findChild(QObject, "editorPage") if win else None,
                "check": check, "find_all": find_all, "by_name": by_name, "wait_until": wait_until,
            }
            try:
                exec(code, ns)
            except SystemExit:
                raise
            except BaseException:  # noqa: BLE001 - report and end the test
                traceback.print_exc()
                app.exit(2)
        QTimer.singleShot(int(os.environ.get("KREATOR_TEST_START_DELAY", "1500")), start)
        return original_exec()
    QApplication.exec = exec_with_test

    # an error in a test's callback ends the run at once (instead of waiting
    # for the runner's timeout); run.py reports the traceback as a failure
    def report_and_quit(kind, value, tb):
        traceback.print_exception(kind, value, tb)
        app = QApplication.instance()
        if app is not None:
            app.exit(2)
    sys.excepthook = report_and_quit

    status = kreator_app.main(["kreator", *extra])
    reporting_exit(status or 0)


if __name__ == "__main__":
    main()
