"""The signal flow view of a large document: the selected object's connections
first, with a notice; Show All shows everything."""

import time

# a document with 50 objects, each calling functions of others and binding to
# another's property: 200 arrows, more than the view shows at once (150; sizes
# would count as layout, which is hidden by default)
N = 50
parts = ["import QtQuick\n\nItem {\n    id: root\n"]
for i in range(N):
    parts.append(f"""    Item {{
        id: o{i}
        opacity: o{(i + 2) % N}.opacity
        function f() {{}}
        function g() {{}}
        onXChanged: o{(i + 1) % N}.f()
        onYChanged: o{(i + 3) % N}.g()
        onWidthChanged: o{(i + 5) % N}.f()
    }}
""")
parts.append("}\n")
with open(f"{OUT}/flowproj/Large.qml", "w") as fh:
    fh.write("".join(parts))

backend.openFolder(f"{OUT}/flowproj")
backend.openFile(f"{OUT}/flowproj/Large.qml")
page.setProperty("flowMode", True)


def nodes():
    return [i for i in find_all(lambda it: it.objectName().startswith("flowNode_")) if i.isVisible()]


def s1():
    pane = find_all(lambda i: i.objectName() == "flowPane")[0]
    msg = find_all(lambda i: i.objectName() == "flowTooBig")[0]
    check(pane.property("tooBig") and msg.isVisible(), "large document: the notice is shown")
    # (the root is selected at first, which connects to nothing itself)
    check(len(nodes()) < 15, f"only the selected object's connections ({len(nodes())} objects)")
    # selecting another object follows it
    backend.select(next(r["uid"] for r in backend.outline.rows() if r["objectId"] == "o7"))
    QTimer.singleShot(600, lambda: s2(pane))


def s2(pane):
    names = sorted(n.objectName()[len("flowNode_"):] for n in nodes())
    check("o7" in names and "o8" in names and len(names) < 15, f"another object selected: its connections ({names})")
    t = time.time()
    pane.setProperty("showAllAnyway", True)
    pane.reload()
    QTimer.singleShot(200, lambda: s3(t))


def s3(t):
    check(len(nodes()) >= N, f"Show All shows every object ({len(nodes())})")
    check(time.time() - t < 10, f"and lays them out in reasonable time ({time.time() - t:.1f} s)")
    backend.discardAll()
    QTimer.singleShot(300, app.quit)


QTimer.singleShot(2500, s1)
