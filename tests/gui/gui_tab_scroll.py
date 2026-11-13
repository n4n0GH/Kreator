"""A tab bar with more tabs than fit: scrolling, the current tab in view."""


from PySide6.QtCore import QObject, Qt, QEvent, QPointF, QPoint, QMetaObject, Q_ARG
from PySide6.QtGui import QMouseEvent, QWheelEvent, QGuiApplication
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
def v(x): return x.toVariant() if hasattr(x, "toVariant") else x
D = f"{OUT}/many"
def names(): return [d["name"] for d in v(backend.property("openDocuments"))]
def find_all(pred):
    out = []; stack = [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
def tabbar(): return find_all(lambda it: it.metaObject().indexOfProperty("overflowing") >= 0)[0]
def lst(): return tabbar().property("list")
def tab_items():
    ts = find_all(lambda it: it.metaObject().className().startswith("TabButton") and it.metaObject().indexOfProperty("dragOffset") >= 0 and it.parentItem() is not None)
    return sorted(ts, key=lambda t: t.property("index"))
def visible_in_bar(t):
    l = lst()
    a = t.mapToScene(QPointF(0, 0)).x(); b = a + t.width()
    la = l.mapToScene(QPointF(0, 0)).x(); lb = la + l.width()
    return a >= la - 1 and b <= lb + 1
def current_tab():
    i = names().index(next(d["name"] for d in v(backend.property("openDocuments")) if d["current"]))
    return tab_items()[i]
def send(t, p, b, btn=Qt.LeftButton):
    QGuiApplication.sendEvent(win, QMouseEvent(t, QPointF(p), QPointF(p), QPointF(win.mapToGlobal(p)), btn if t != QEvent.MouseMove else Qt.NoButton, b, Qt.NoModifier))
backend.openFolder(D)
for i in range(1, 15):
    QMetaObject.invokeMethod(win, "switchFile", Q_ARG("QVariant", f"{D}/Component{i:02d}.qml"))
def s1():
    tb = tabbar()
    print("tabs:", len(names()), "contentWidth", round(lst().property("contentWidth")), "width", round(lst().width()), "contentX", round(lst().property("contentX")))
    check(tb.property("overflowing"), "tab bar overflows")
    # tabs scrolled out of view are not drawn outside the bar (over the sidebar)
    check(tb.clip() or lst().clip(), "the tab bar clips its scrolled tabs")
    check(visible_in_bar(current_tab()), "current (last opened) tab scrolled into view")
    arrows = find_all(lambda it: it.metaObject().className().startswith("ToolButton") and it.property("text") in ("Scroll Tabs Left", "Scroll Tabs Right", "All Documents") and it.isVisible())
    check(len(arrows) == 3, "◀ ▶ and document list buttons shown")
    win.grabWindow().save(f"{OUT}/tabscroll1.png")
    QTest.keyClick(win, Qt.Key_Tab, Qt.ControlModifier)   # wraps to the first tab
    QTimer.singleShot(600, s2)
def s2():
    check(names()[0] == "Component01.qml" and visible_in_bar(tab_items()[0]), "Ctrl+Tab to the first tab scrolls it into view")
    # wheel over the tab bar
    t = tab_items()[0]
    pos = t.mapToScene(QPointF(t.width() / 2, t.height() / 2))
    x0 = lst().property("contentX")
    QGuiApplication.sendEvent(win, QWheelEvent(pos, pos, QPoint(0, 0), QPoint(0, -240), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
    x1 = lst().property("contentX")
    check(x1 > x0 + 20, f"wheel scrolls the tabs ({round(x0)} -> {round(x1)})")
    # right arrow
    rb = [it for it in find_all(lambda it: it.metaObject().className().startswith("ToolButton") and it.property("text") == "Scroll Tabs Right")][0]
    p = rb.mapToScene(QPointF(rb.width() / 2, rb.height() / 2)).toPoint()
    send(QEvent.MouseButtonPress, p, Qt.LeftButton); send(QEvent.MouseButtonRelease, p, Qt.NoButton)
    QTimer.singleShot(400, lambda: s3(x1))
def s3(x1):
    check(lst().property("contentX") > x1 + 20, f"▶ scrolls further ({round(x1)} -> {round(lst().property('contentX'))})")
    # drag the first visible tab to the right edge and hold -> autoscroll
    QMetaObject.invokeMethod(tabbar(), "scrollTo", Q_ARG("QVariant", -1e9), Q_ARG("QVariant", False))
    t = tab_items()[0]
    a = t.mapToScene(QPointF(t.width() / 2, t.height() / 2)).toPoint()
    l = lst()
    edge = l.mapToScene(QPointF(l.width() - 8, 0)).toPoint()
    send(QEvent.MouseButtonPress, a, Qt.LeftButton)
    for k in range(1, 13):
        send(QEvent.MouseMove, QPoint(a.x() + (edge.x() - a.x()) * k // 12, a.y()), Qt.LeftButton)
    QTimer.singleShot(1500, lambda: s4(a, edge))
def s4(a, edge):
    check(not visible_in_bar(tab_items()[1]), "holding a dragged tab at the edge scrolls the bar (second tab scrolled out)")
    win.grabWindow().save(f"{OUT}/tabscroll2.png")
    send(QEvent.MouseButtonRelease, QPoint(edge.x(), a.y()), Qt.NoButton)
    QTimer.singleShot(400, s5)
def s5():
    n = names()
    print("order now:", [x.replace("Component", "C").replace(".qml", "") for x in n])
    check(n.index("Component01.qml") > 8, f"the dragged tab moved past the originally visible area (now #{n.index('Component01.qml') + 1})")
    # document list menu
    menus = [o for o in win.findChildren(QObject) if o.metaObject().className().startswith("Menu") and o.metaObject().indexOfProperty("count") >= 0]
    lb = [it for it in find_all(lambda it: it.metaObject().className().startswith("ToolButton") and it.property("text") == "All Documents")][0]
    p = lb.mapToScene(QPointF(lb.width() / 2, lb.height() / 2)).toPoint()
    send(QEvent.MouseButtonPress, p, Qt.LeftButton); send(QEvent.MouseButtonRelease, p, Qt.NoButton)
    QTimer.singleShot(400, s6)
def s6():
    menu = [o for o in win.findChildren(QObject) if o.metaObject().indexOfProperty("count") >= 0 and o.metaObject().indexOfMethod("popup()") >= 0 and o.property("opened")]
    check(menu and menu[0].property("count") == 14, f"document menu lists all 14 tabs ({menu[0].property('count') if menu else None})")
    win.grabWindow().save(f"{OUT}/tabscroll3.png")
    app.quit()
QTimer.singleShot(2000, s1)
