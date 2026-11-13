"""Run: saves the application's files and starts the project's Main.qml (or
the shown QML file) with qml6; Stop ends it; what it prints is collected,
and problems are reported."""

NEEDS = ["qml6"]
RUNS = 2

import os

from PySide6.QtCore import QMetaObject, QObject, Q_ARG

P = f"{OUT}/runproj"
PID_FILE = f"{OUT}/running.pid"

# --- run 0 ---
os.makedirs(P)
with open(f"{P}/Main.qml", "w", encoding="utf-8") as fh:
    fh.write("""import QtQuick
import QtQuick.Controls

ApplicationWindow {
    id: window

    visible: true
    width: 200
    height: 100
    title: qsTr("Run Me")
    Component.onCompleted: console.log("started: " + greeting.text)

    Greeting {
        id: greeting
    }
}
""")
with open(f"{P}/Greeting.qml", "w", encoding="utf-8") as fh:
    fh.write('import QtQuick\nimport QtQuick.Controls\n\nLabel {\n    text: "hello"\n}\n')

problems, endings, errors = [], [], []
backend.runProblem.connect(problems.append)
backend.runFinished.connect(lambda name, code, failed: endings.append((name, code, failed)))
backend.errorOccurred.connect(errors.append)
action = page.findChild(QObject, "runAction")


def trigger():
    QMetaObject.invokeMethod(action, "trigger")


def s1():
    check(action is not None and action.property("text") == "Run" and not action.property("enabled"),
          "nothing open: Run is disabled")
    backend.openFolder(P)
    check(backend.canRun and backend.runName == "Main.qml" and action.property("enabled"),
          "a project with a Main.qml can be run, also with no document shown")
    QMetaObject.invokeMethod(win, "switchFile", Q_ARG("QVariant", f"{P}/Greeting.qml"))
    QTimer.singleShot(700, s2)


def s2():
    backend.setProperty("text", "string", "hello again")
    check(backend.modified and backend.runName == "Main.qml", "a file of the project is shown, changed: Run starts Main.qml")
    trigger()
    wait_until(lambda: "started:" in backend.runOutput, s3, what="the application starts and prints")


def s3():
    check("started: hello again" in backend.runOutput and backend.runOutput.startswith("$ "),
          "it runs what was just changed: " + backend.runOutput.replace("\n", " | "))
    check(not backend.modified and '"hello again"' in open(f"{P}/Greeting.qml", encoding="utf-8").read(),
          "the changed file was saved first")
    check(backend.running and action.property("text") == "Stop", "while it runs, the action is Stop")
    check(page.property("sourceMode") is False and backend.hasDocument, "Kreator stays as it was")
    trigger()
    wait_until(lambda: not backend.running, s4, what="Stop ends it")


def s4():
    check(action.property("text") == "Run" and backend.runOutput.endswith("(stopped)")
          and endings == [("Main.qml", endings[0][1], False)] and not problems,
          f"stopped: not reported as a failure {endings}")
    # an application with a mistake, that ends with an exit code
    QMetaObject.invokeMethod(win, "switchFile", Q_ARG("QVariant", f"{P}/Main.qml"))
    QTimer.singleShot(700, s5)


def s5():
    text = backend.sourceText.replace('console.log("started: " + greeting.text)', "console.log(missing.thing)")
    text = text.replace("    Greeting {", "    Timer {\n        interval: 400\n        running: true\n"
                        "        onTriggered: Qt.exit(3)\n    }\n\n    Greeting {")
    check(backend.applySource(text), "Main.qml changed in the source view")
    del endings[:]
    trigger()
    wait_until(lambda: endings, s6, what="the application ends by itself")


def s6():
    check(len(problems) == 1 and "ReferenceError" in problems[0] and "missing" in problems[0],
          f"the application's error is reported once {problems}")
    check(endings == [("Main.qml", 3, True)] and not backend.running and "exit code 3" in backend.runOutput,
          f"ending with an exit code is a failure {endings}")
    check("Main.qml:" in backend.runOutput and not backend.modified, "the output has the error's place")
    # the output dialog
    QMetaObject.invokeMethod(win, "showRunOutput")
    wait_until(lambda: win.findChild(QObject, "runOutputDialog").property("opened"), s7, what="the output dialog opens")


def s7():
    shown = win.findChild(QObject, "runOutputText").property("text")
    check(shown == backend.runOutput and "ReferenceError" in shown, "Run Output… shows what was printed")
    win.grabWindow().save(f"{OUT}/run_output.png")
    win.findChild(QObject, "runOutputDialog").close()
    # what Run starts for other documents
    backend.openFile(f"{OUT}/work/SettingsPage.qml")
    check(backend.canRun and backend.runName == "SettingsPage.qml", "a QML file outside the project: that file")
    backend.openFile(f"{OUT}/work/dialog.ui")
    check(not backend.canRun and backend.runName == "" and not action.property("enabled"),
          "a form outside the project: nothing to run")
    check(backend.run() is False and len(errors) == 1, f"… and Run says so {errors}")
    backend.newDocument("qtquick")
    check(backend.canRun and backend.runName == "", "an untitled QML document can be run (once it is saved)")
    backend.closeDocument()
    backend.switchTo(f"{P}/Greeting.qml")
    # running again starts it anew; quitting Kreator ends it
    text = open(f"{P}/Main.qml", encoding="utf-8").read().replace("Qt.exit(3)", "console.log(\"still here\")")
    open(f"{P}/Main.qml", "w", encoding="utf-8").write(text)
    QTimer.singleShot(900, s8)       # (Kreator reloads the changed Main.qml)


def s8():
    del endings[:]
    check(backend.run() and backend.running, "started")
    wait_until(lambda: "still here" in backend.runOutput, s9, what="it runs")


def s9():
    check(backend.run() and backend.running and "still here" not in backend.runOutput,
          "Run while it runs starts it anew, with new output")
    wait_until(lambda: "still here" in backend.runOutput, s10, what="it runs again")


def s10():
    check(endings and endings[0][2] is False, f"the first one was ended, not failed {endings}")
    pid = backend._runner._process.processId()
    check(os.path.exists(f"/proc/{pid}"), "the application is running when Kreator quits")
    with open(PID_FILE, "w", encoding="utf-8") as fh:
        fh.write(str(pid))
    app.quit()


QTimer.singleShot(800, s1)

# --- run 1 ---
with open(PID_FILE, encoding="utf-8") as fh:
    check(not os.path.exists(f"/proc/{fh.read()}"), "quitting Kreator ended the application")
check(not backend.running and backend.runOutput == "", "nothing runs after a restart")
QTimer.singleShot(500, app.quit)
