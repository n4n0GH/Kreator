"""Applying source edits, and reporting source errors."""


def snap(name):
    win.grabWindow().save(f"{OUT}/{name}.png"); print("saved", name)
def check(c, m): print(("PASS " if c else "FAIL ") + m)
backend.newDocument("kirigami-app")
def s1():
    print("app: mode", backend.previewMode, "err", repr(backend.previewError), "note", backend.previewNote)
    print("issues:", [i["title"] for i in backend.issues])
    snap("app1")
    backend.newDocument("qtquick")
def s2():
    print("qtquick: mode", backend.previewMode, "err", repr(backend.previewError), "note", backend.previewNote)
    print("issues:", [i["title"] for i in backend.issues])
    snap("qtq1")
    # source mode
    page = win.findChild(QObject, "") 
    backend.newDocument("kirigami-page")
def s3():
    print("page: mode", backend.previewMode, "err", repr(backend.previewError))
    ok = backend.applySource(backend.sourceText.replace('title: i18n("Settings")', 'title: i18n("Preferences")\n    Rectangle { color: "red"; width: 50; height: 50 }'))
    check(ok and 'i18n("Preferences")' in backend.sourceText, "apply source")
    bad = backend.applySource("Item {")
    check(not bad and backend.sourceError != "", "source error reported: " + backend.sourceError)
    # error in preview
    backend.applySource(backend.sourceText.replace("spacing: Kirigami.Units.largeSpacing", "spacing: Kirigami.Units.largeSpacing\n        bogusProp: 3"))
def s4():
    print("after bogus: err", repr(backend.previewError), "note", repr(backend.previewNote))
    backend.applySource(backend.sourceText.replace("bogusProp: 3", "width: undefinedThing.foo"))
def s5():
    print("after runtime err: err", repr(backend.previewError), "note", repr(backend.previewNote))
    snap("page1")
    app.quit()
from PySide6.QtCore import QObject
seq = [s1, s2, s3, s4, s5]
def run(i=0):
    try: seq[i]()
    except Exception:
        import traceback; traceback.print_exc(); app.quit(); return
    if i + 1 < len(seq): QTimer.singleShot(1200, lambda: run(i + 1))
QTimer.singleShot(1200, run)
