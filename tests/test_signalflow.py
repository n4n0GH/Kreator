"""Unit tests for the signal flow analysis (signalflow.py)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kreator import qmldoc, signalflow, uidoc  # noqa: E402

QML = """import QtQuick
import QtQuick.Controls as QQC2

Item {
    id: root
    signal saved()

    function save() {
        dialog.open()
        root.saved()
    }

    QQC2.Button {
        text: qsTr("Save")
        onClicked: save()
    }
    QQC2.CheckBox { id: check }
    QQC2.TextField {
        id: field
        enabled: check.checked
        anchors.left: check.right
        onAccepted: {
            const field = 1
            status.text = "x"
        }
    }
    QQC2.Label { id: status }
    QQC2.Dialog { id: dialog }
    Timer {
        id: timer
        Component.onCompleted: timer.triggered.connect(save)
    }
    Connections {
        target: Backend
        function onNotify(msg) { status.text = msg }
        function onOther() { console.log("x") }
    }
}
"""

UI = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QDialog" name="Dialog">
  <layout class="QVBoxLayout" name="layout">
   <item><widget class="QDialogButtonBox" name="buttonBox"/></item>
  </layout>
 </widget>
 <connections>
  <connection>
   <sender>buttonBox</sender>
   <signal>accepted()</signal>
   <receiver>Dialog</receiver>
   <slot>accept()</slot>
  </connection>
 </connections>
</ui>
"""


def edges(graph):
    """{(from, output port, to, input port, kind): [labels]}"""
    names = {k: n["label"] for k, n in graph.nodes.items()}
    return {(names[e["from"]], e["fromPort"], names[e["to"]], e["toPort"], e["kind"]): [i["label"] for i in e["items"]]
            for e in graph.edges.values()}


class QmlFlowTest(unittest.TestCase):
    def setUp(self):
        doc = qmldoc.parse(QML)
        self.g = signalflow.qml_flow(doc, QML)
        self.e = edges(self.g)

    def test_handler_calls_function(self):
        self.assertEqual(self.e[("“Save”", "clicked", "root", "save()", "signal")], ["clicked → save()"])

    def test_function_body(self):
        self.assertEqual(self.e[("root", "save()", "dialog", "open()", "signal")], ["save() → dialog.open()"])

    def test_binding_and_layout(self):
        self.assertEqual(self.e[("check", "checked", "field", "enabled", "binding")], ["check.checked → enabled"])
        self.assertEqual(self.e[("check", "right", "field", "anchors.left", "layout")], ["check.right → anchors.left"])

    def test_assignment_in_handler(self):
        self.assertEqual(self.e[("field", "accepted", "status", "text", "signal")], ["accepted → status.text ="])

    def test_js_connect(self):
        self.assertEqual(self.e[("timer", "triggered", "root", "save()", "signal")], ["triggered → save()"])

    def test_connections(self):
        self.assertEqual(self.e[("Backend", "notify", "status", "text", "signal")], ["notify → status.text ="])
        # no object named: the object holding the Connections
        self.assertEqual(self.e[("Backend", "other", "root", "", "signal")], ["other"])
        self.assertTrue(self.g.nodes["xBackend"]["external"])

    def test_positions(self):
        item = self.g.edges[next(k for k in self.g.edges if self.g.nodes[k[0]]["label"] == "“Save”")]["items"][0]
        self.assertEqual(QML.split("\n")[item["line"] - 1].strip(), "onClicked: save()")
        self.assertEqual(item["column"], 9)

    def test_uids_are_the_documents(self):
        doc = qmldoc.parse(QML)
        g = signalflow.qml_flow(doc, doc.to_text())
        uids = {n.uid for n, *_ in doc.walk()}
        self.assertTrue(all(n["uid"] in uids for n in g.nodes.values() if not n["external"]))

    def test_ports(self):
        out = signalflow.layout(self.g, {"signal", "binding"})
        ports = {n["label"]: {p["name"]: (p["in"], p["out"], p["kind"], p["line"]) for p in n["ports"]}
                 for n in out["nodes"] if not n["dummy"]}
        # a function: called (in) and doing something (out), written at line 8
        self.assertEqual(ports["root"]["save()"], (True, True, "function", 8))
        self.assertEqual(ports["dialog"]["open()"], (True, False, "function", 0))
        self.assertEqual(ports["“Save”"]["clicked"], (False, True, "signal", 15))
        self.assertEqual(ports["field"]["enabled"][:3], (True, False, "property"))
        # ports in the order they are written
        self.assertEqual([p["name"] for p in next(n for n in out["nodes"] if n.get("label") == "field")["ports"]],
                         ["enabled", "accepted"])

    def test_dialog_example(self):
        text = """import QtQuick
import org.kde.kirigami as Kirigami
Kirigami.Dialog {
    id: dialog
    onOpened: {
        nameField.forceActiveFocus()
    }
    onAccepted: {
        console.log("VM Name:", nameField.text);
    }
    Item { Kirigami.FormTextField { id: nameField } }
}
"""
        g = signalflow.qml_flow(qmldoc.parse(text), text)
        self.assertEqual(set(edges(g)), {("dialog", "opened", "nameField", "forceActiveFocus()", "signal"),
                                         ("dialog", "accepted", "nameField", "text", "signal")})

    def test_layout(self):
        out = signalflow.layout(self.g, {"signal", "binding"})
        real = [n for n in out["nodes"] if not n["dummy"]]
        self.assertEqual(len({(n["layer"], n["order"]) for n in out["nodes"]}), len(out["nodes"]))
        layer = {n["key"]: n["layer"] for n in out["nodes"]}
        for e in out["edges"]:
            # each path goes one column at a time, left to right
            self.assertEqual([layer[k] for k in e["path"]],
                             list(range(layer[e["path"][0]], layer[e["path"][0]] + len(e["path"]))))
        self.assertNotIn("layout", {e["kind"] for e in out["edges"]})
        self.assertEqual(out["counts"]["layout"], 1)
        self.assertTrue(real)

    def test_focus(self):
        status = next(n["uid"] for n in self.g.nodes.values() if n["label"] == "status")
        out = signalflow.layout(self.g, {"signal", "binding"}, status)
        self.assertEqual(sorted(n["label"] for n in out["nodes"] if not n["dummy"]), ["Backend", "field", "status"])

    def test_cycle(self):
        text = "import QtQuick\nItem {\n    Item { id: a; onXChanged: b.x = 1 }\n    Item { id: b; onXChanged: a.x = 1 }\n}\n"
        g = signalflow.qml_flow(qmldoc.parse(text), text)
        out = signalflow.layout(g, {"signal"})
        self.assertEqual(len(out["edges"]), 2)
        self.assertEqual(sum(e["reversed"] for e in out["edges"]), 1)

    def test_label_of_i18nc(self):
        text = 'import QtQuick\nItem {\n    Button { text: i18nc("verb", "Create"); onClicked: x.y() }\n    Item { id: x }\n}\n'
        g = signalflow.qml_flow(qmldoc.parse(text), text)
        self.assertIn("“Create”", [n["label"] for n in g.nodes.values()])


class UiFlowTest(unittest.TestCase):
    def test_connections(self):
        doc = uidoc.UiDocument.parse(UI)
        g = signalflow.ui_flow(doc, UI)
        self.assertEqual(edges(g), {("buttonBox", "accepted()", "Dialog", "accept()", "signal"):
                                    ["buttonBox.accepted() → Dialog.accept()"]})
        item = next(iter(g.edges.values()))["items"][0]
        self.assertEqual(UI.split("\n")[item["line"] - 1].strip(), "<connection>")
        self.assertEqual(g.nodes["uDialog"]["uid"], doc.root.uid)


if __name__ == "__main__":
    unittest.main()


class UiEditTest(unittest.TestCase):
    def setUp(self):
        self.doc = uidoc.UiDocument.parse(UI.replace("<item><widget class=\"QDialogButtonBox\" name=\"buttonBox\"/></item>",
                                                     "<item><widget class=\"QDialogButtonBox\" name=\"buttonBox\"/></item>"
                                                     "<item><widget class=\"QCheckBox\" name=\"check\"/></item>"))

    def test_add_update_remove(self):
        i = self.doc.add_connection("check", "toggled(bool)", "buttonBox", "setEnabled(bool)")
        self.assertEqual(i, 1)
        self.doc.update_connection(1, "check", "clicked()", "Dialog", "reject()")
        self.assertEqual(self.doc.connections()[1],
                         {"sender": "check", "signal": "clicked()", "receiver": "Dialog", "slot": "reject()"})
        self.doc.remove_connection(0)
        self.doc.remove_connection(0)
        self.assertIsNone(self.doc.ui.find("connections"))
        # a new <connections> goes where Designer puts it
        self.doc.add_connection("check", "clicked()", "Dialog", "accept()")
        tags = [c.tag for c in self.doc.ui]
        self.assertEqual(tags.index("connections"), tags.index("widget") + 1)

    def test_checks(self):
        with self.assertRaises(uidoc.UiError):
            self.doc.add_connection("nope", "clicked()", "Dialog", "accept()")
        with self.assertRaises(uidoc.UiError):
            self.doc.add_connection("check", "clicked", "Dialog", "accept()")
        with self.assertRaises(uidoc.UiError):
            self.doc.remove_connection(5)

    def test_members(self):
        m = signalflow.class_members(self.doc, "QCheckBox")
        self.assertIn("toggled(bool)", m["signals"])
        self.assertIn("setChecked(bool)", m["slots"])
        self.assertNotIn("deleteLater()", m["slots"])
        # KDE / unknown classes: the Qt class they stand for, else QWidget
        self.assertIn("textChanged(QString)", signalflow.class_members(self.doc, "KLineEdit")["signals"])
        self.assertIn("close()", signalflow.class_members(self.doc, "MyWidget")["slots"])

    def test_declared(self):
        text = UI.replace("</ui>", "<slots><slot>apply()</slot><signal>done()</signal></slots></ui>")
        doc = uidoc.UiDocument.parse(text)
        m = signalflow.class_members(doc, "QDialog")
        self.assertIn("apply()", m["slots"])
        self.assertIn("done()", m["signals"])

    def test_compatible(self):
        self.assertTrue(signalflow.compatible("toggled(bool)", "setEnabled(bool)"))
        self.assertTrue(signalflow.compatible("toggled(bool)", "close()"))
        self.assertFalse(signalflow.compatible("clicked()", "setEnabled(bool)"))
        self.assertFalse(signalflow.compatible("textChanged(QString)", "setEnabled(bool)"))

    def test_all_widgets(self):
        g = signalflow.ui_flow(self.doc, self.doc.to_text())
        out = signalflow.layout(g, {"signal"}, 0, True)
        free = [n["id"] for n in out["nodes"] if n.get("unconnected")]
        self.assertEqual(free, ["check"])
        self.assertEqual({n["layer"] for n in out["nodes"] if n.get("unconnected")}, {2})


class StableKeyTest(unittest.TestCase):
    def test_stable_over_reparse(self):
        a = signalflow.qml_flow(qmldoc.parse(QML), QML)
        b = signalflow.qml_flow(qmldoc.parse(QML), QML)
        sa = sorted(n["stable"] for n in a.nodes.values())
        self.assertEqual(sa, sorted(n["stable"] for n in b.nodes.values()))
        self.assertIn("root/Button[0]", sa)      # no id: its place in the tree
        self.assertIn("id:status", sa)
        self.assertIn("ext:Backend", sa)

    def test_clean_positions(self):
        from kreator.backend import _clean_positions
        self.assertEqual(_clean_positions({"id:a": [1.234, 5], "b": "x", "c": [-1, 2], 3: [1, 1]}),
                         {"id:a": [1.2, 5.0]})
        self.assertEqual(_clean_positions(None), {})


class PortsTest(unittest.TestCase):
    def ports(self, text):
        out = signalflow.layout(signalflow.qml_flow(qmldoc.parse(text), text), {"signal", "binding"})
        return {(n["label"], p["name"]): p for n in out["nodes"] if not n["dummy"] for p in n["ports"]}

    def test_unconnected(self):
        text = """import QtQuick
Item {
    id: root
    signal saved()
    signal never()
    function save() { root.saved(); other.x = 1 }
    function lonely() { console.log("x") }
    Item { id: other; onXChanged: Backend.go() }
    Item { id: b; onYChanged: root.save() }
}
"""
        p = self.ports(text)
        loose = sorted(k for k, v in p.items() if v.get("unconnected"))
        # emitted by its own function: used; a C++ call only: nothing here connects
        self.assertEqual(loose, [("other", "xChanged"), ("root", "lonely()"), ("root", "never")])
        self.assertEqual((p[("root", "never")]["in"], p[("root", "never")]["out"]), (True, True))
        self.assertEqual(p[("root", "lonely()")]["line"], 7)
        self.assertNotIn(("root", "saved"), loose)

    def test_function_in_binding(self):
        text = """import QtQuick
Item {
    id: root
    function label(x) { return x }
    Text { text: root.label(1) }
}
"""
        p = self.ports(text)
        self.assertTrue(p[("root", "label()")]["out"])
        self.assertFalse(p[("root", "label()")].get("unconnected", False))

    def test_form_declared(self):
        text = UI.replace("</ui>", "<slots><slot>apply()</slot><signal>done()</signal></slots></ui>")
        doc = uidoc.UiDocument.parse(text)
        out = signalflow.layout(signalflow.ui_flow(doc, text), {"signal"})
        dialog = next(n for n in out["nodes"] if n.get("id") == "Dialog")
        loose = {p["name"]: (p["in"], p["out"]) for p in dialog["ports"] if p.get("unconnected")}
        self.assertEqual(loose, {"apply()": (True, False), "done()": (False, True)})

    def test_untangle(self):
        # a's two outputs, written top to bottom, lead to b's ports written the other way round
        text = """import QtQuick
Item {
    Item { id: a
        onXChanged: b.second()
        onYChanged: b.first()
    }
    Item { id: b
        function first() {}
        function second() {}
    }
}
"""
        out = signalflow.layout(signalflow.qml_flow(qmldoc.parse(text), text), {"signal"})
        a = next(n for n in out["nodes"] if n.get("id") == "a")
        b = next(n for n in out["nodes"] if n.get("id") == "b")
        a_order = [p["name"] for p in a["ports"]]
        b_order = [p["name"] for p in b["ports"]]
        # straight across: xChanged -> second(), yChanged -> first() on the same rows
        want = {"xChanged": "second()", "yChanged": "first()"}
        self.assertEqual([want[x] for x in a_order], b_order)


class UnusedPropertyTest(unittest.TestCase):
    def test_unused_properties(self):
        text = """import QtQuick
Item {
    id: root
    property int unusedCount: 5
    property bool shown: true
    property string title
    property real watched: 1
    onWatchedChanged: other.x = 1
    property var linked: other.y
    Item { id: other; visible: root.shown; onXChanged: root.go() }
    function go() {}
    Text { text: title }
}
"""
        out = signalflow.layout(signalflow.qml_flow(qmldoc.parse(text), text), {"signal", "binding"})
        root = next(n for n in out["nodes"] if n.get("id") == "root")
        red = {p["name"]: (p["in"], p["out"], p["line"]) for p in root["ports"] if p.get("unconnected")}
        # read unqualified (title), with a handler (watched), connected (shown, linked): not red
        self.assertEqual(red, {"unusedCount": (True, True, 4)})


class RemoveMemberTest(unittest.TestCase):
    QML = """import QtQuick
Item {
    id: root
    // never read
    property int leftover: 3
    signal pinged()
    signal used()
    onUsed: console.log("x")
    function lonely() {
        return 1
    }
    function onSomething() {}
    Text { text: "hi"; onTextChanged: root.visible = false }
}
"""

    def test_qml(self):
        from kreator import documents
        a = documents.QmlAdapter(self.QML)
        out = signalflow.layout(signalflow.qml_flow(a.doc, self.QML), {"signal", "binding"})
        root = next(n for n in out["nodes"] if n.get("id") == "root")
        red = {p["name"]: p["removable"] for p in root["ports"] if p.get("unconnected")}
        # a signal with a handler, a handler-named function: not removable
        self.assertEqual(red, {"leftover": True, "pinged": True, "used": False, "lonely()": True,
                               "onSomething()": False})
        for name, kind in (("leftover", "property"), ("pinged", "signal"), ("lonely()", "function")):
            a.remove_member(root["uid"], name, kind)
        text = a.text()
        for gone in ("leftover", "never read", "pinged", "lonely", "return 1"):
            self.assertNotIn(gone, text)
        for kept in ("signal used()", "onUsed", "onSomething", 'text: "hi"'):
            self.assertIn(kept, text)
        with self.assertRaises(documents.EditError):
            a.remove_member(root["uid"], "lonely()", "function")

    def test_ui(self):
        from kreator import documents
        text = UI.replace("</ui>", "<slots><slot>apply()</slot><slot>used()</slot><signal>done()</signal></slots></ui>")
        a = documents.UiAdapter(text)
        conns = a.doc.connections()
        c = conns[0]
        a.add_connection(c["sender"], c["signal"], "Dialog", "used()")
        out = signalflow.layout(signalflow.ui_flow(a.doc, a.text()), {"signal"})
        dialog = next(n for n in out["nodes"] if n.get("id") == "Dialog")
        red = {p["name"]: p["removable"] for p in dialog["ports"] if p.get("unconnected")}
        self.assertEqual(red, {"apply()": True, "done()": True})
        a.remove_declared(dialog["uid"], "function", "apply()")
        self.assertNotIn("apply()", a.text())
        a.remove_declared(dialog["uid"], "signal", "done()")
        self.assertIn("<slot>used()</slot>", a.text())
        self.assertNotIn("done()", a.text())
        with self.assertRaises(documents.EditError):
            a.remove_declared(dialog["uid"], "function", "apply()")
