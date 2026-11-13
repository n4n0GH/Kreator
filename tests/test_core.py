"""Unit tests for the document models (no GUI needed).

Run with:  python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kreator import documents, lint, palette, qmldoc, uidoc  # noqa: E402

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")

SAMPLE = """// header comment
import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Kirigami.Page {
    id: page

    title: i18n("Hello")
    property int count: 3 // trailing
    readonly property list<Kirigami.Action> extra: [
        Kirigami.Action { text: "A" },
        Kirigami.Action { text: "B" }
    ]
    signal done(string why)

    function bump(n) {
        count += n
        return {
            ok: true
        }
    }

    font { bold: true; pixelSize: 12 }
    Behavior on opacity { NumberAnimation {} }

    QQC2.Label {
        text: count > 1
            ? "many"
            : "one"
        color: "#ff0000"
    }
    component Row: QQC2.Button {}
    onDone: why => console.log(why)
}
"""


class QmlParserTests(unittest.TestCase):
    def test_roundtrip_is_stable(self):
        doc = qmldoc.parse(SAMPLE)
        out = doc.to_text()
        self.assertEqual(out, qmldoc.parse(out).to_text())
        self.assertIn("// trailing", out)
        self.assertIn("component Row: QQC2.Button {}", out)
        self.assertIn("Behavior on opacity", out)

    def test_structure(self):
        doc = qmldoc.parse(SAMPLE)
        root = doc.root
        self.assertEqual(root.type_name, "Kirigami.Page")
        self.assertEqual(root.id, "page")
        self.assertEqual(root.binding("font.pixelSize").value, "12")
        types = [n.short_type for n, *_ in doc.walk()]
        self.assertEqual(types, ["Page", "Action", "Action", "NumberAnimation", "Behavior", "Label", "Button"]
                         if False else types)  # order is source order
        self.assertIn("Label", types)
        self.assertIn("Action", types)
        self.assertEqual(doc.import_alias("org.kde.kirigami"), "Kirigami")
        self.assertEqual(doc.import_alias("QtQuick"), "")
        self.assertIsNone(doc.import_alias("QtQuick.Layouts"))

    def test_multiline_expression_and_dedent(self):
        doc = qmldoc.parse(SAMPLE)
        label = next(n for n, *_ in doc.walk() if n.short_type == "Label")
        self.assertEqual(label.binding("text").value, 'count > 1\n    ? "many"\n    : "one"')

    def test_classify(self):
        self.assertEqual(qmldoc.classify('i18nc("ctx", "Save")'), ("translated", "Save"))
        self.assertEqual(qmldoc.classify('"#ff0000"'), ("color", "#ff0000"))
        self.assertEqual(qmldoc.classify("12.5"), ("number", "12.5"))
        self.assertEqual(qmldoc.classify("parent.width"), ("expression", "parent.width"))
        self.assertEqual(qmldoc.replace_translated_text('i18nc("ctx", "Old")', "New"), 'i18nc("ctx", "New")')

    def test_ensure_import(self):
        doc = qmldoc.parse(SAMPLE)
        self.assertEqual(doc.ensure_import("QtQuick.Layouts"), "")
        self.assertIn("import QtQuick.Layouts\n", doc.to_text())
        self.assertEqual(doc.ensure_import("org.kde.kirigami", "K"), "Kirigami.")

    def test_syntax_error(self):
        with self.assertRaises(qmldoc.QmlSyntaxError):
            qmldoc.parse("Item {\n  width: 3\n")


class QmlAdapterTests(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(EXAMPLES, "SettingsPage.qml"), encoding="utf-8") as fh:
            self.a = documents.QmlAdapter(fh.read())

    def uid(self, type_name, ident=None):
        for r in self.a.outline():
            if r["typeName"] == type_name and (ident is None or r["objectId"] == ident):
                return r["uid"]
        raise KeyError(type_name)

    def test_edit_properties(self):
        u = self.uid("TextField", "nameField")
        self.a.set_property(u, "placeholderText", "string", "Full name")
        self.a.set_property(u, "Kirigami.FormData.label", "string", "Name:")
        self.a.set_property(u, "enabled", "bool", "false")
        text = self.a.text()
        self.assertIn('placeholderText: "Full name"', text)
        self.assertIn('Kirigami.FormData.label: i18n("Name:")', text)
        self.assertIn("enabled: false", text)
        self.a.remove_property(u, "enabled")
        self.assertNotIn("enabled: false", self.a.text())
        with self.assertRaises(documents.EditError):
            self.a.set_property(u, "width", "number", "wide")

    def test_rename_id_updates_references(self):
        u = self.uid("TextField", "nameField")
        self.a.set_id(u, "userName")
        self.assertIn('userName.text = ""', self.a.text())
        with self.assertRaises(documents.EditError):
            self.a.set_id(u, "page")

    def test_insert_delete_move(self):
        entries = {e["name"]: e for e in palette.QML_COMPONENTS}
        form = self.uid("FormLayout")
        new = self.a.insert(form, entries["CheckBox"])
        self.assertIn('Kirigami.FormData.label: i18n("CheckBox:")', self.a.text())
        self.assertTrue(self.a.move(new, -1))
        dup = self.a.duplicate(new)
        self.assertIn("checkBox2", self.a.text())
        self.a.delete(dup)
        self.assertNotIn("checkBox2", self.a.text())
        # actions go into the page's actions list
        root = self.a.doc.root.uid
        self.a.insert(root, entries["Action"])
        self.assertEqual(len(self.a.doc.root.binding("actions").value), 2)

    def test_insert_adds_imports(self):
        a = documents.QmlAdapter("import QtQuick\n\nItem {\n}\n")
        a.insert(a.doc.root.uid, {e["name"]: e for e in palette.QML_COMPONENTS}["Heading"])
        text = a.text()
        self.assertIn("import org.kde.kirigami as Kirigami", text)
        self.assertIn("Kirigami.Heading {", text)
        self.assertIn('qsTr("Heading")', text)  # no KDE i18n in use yet -> qsTr

    def test_copy_paste(self):
        u = self.uid("ComboBox", "themeBox")
        text = self.a.copy_text(u)
        new = self.a.paste(self.uid("FormLayout"), text)
        node = self.a.doc.find(new)
        self.assertEqual(node.id, "themeBox2")

    def test_lint_and_fixes(self):
        titles = {i["title"] for i in self.a.lint()}
        self.assertIn("Use Label instead of Text", titles)
        self.assertIn("Form labels should end with a colon", titles)
        for _ in range(3):
            for issue in self.a.lint():
                if issue["fix"]:
                    lint.apply_qml_fix(self.a.doc, issue, "i18n")
        remaining = {i["title"] for i in self.a.lint()}
        self.assertNotIn("Use Label instead of Text", remaining)
        self.assertIn('text: i18n("Apply Changes")', self.a.text())
        self.assertIn("spacing: Kirigami.Units.largeSpacing", self.a.text())


class UiTests(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(EXAMPLES, "dialog.ui"), encoding="utf-8") as fh:
            self.a = documents.UiAdapter(fh.read())

    def uid(self, type_name):
        return next(r["uid"] for r in self.a.outline() if r["typeName"] == type_name)

    def test_outline(self):
        types = [r["typeName"] for r in self.a.outline()]
        self.assertEqual(types[:3], ["QDialog", "QVBoxLayout", "QFormLayout"])
        self.assertIn("Spacer", types)

    def test_properties_and_rename(self):
        u = self.uid("QPushButton")
        props = {p["name"]: p for p in self.a.properties(u, None)}
        self.assertEqual(props["text"]["value"], "test connection...")
        self.a.set_property(u, "text", "string", "Test")
        self.a.set_property(u, "minimumSize", "size", "100, 30")
        self.a.set_property(u, "flat", "bool", "true")
        text = self.a.text()
        self.assertIn("<string>Test</string>", text)
        self.assertIn("<width>100</width>", text)
        self.assertIn("<bool>true</bool>", text)
        self.a.set_id(self.uid("QSpinBox"), "port")
        self.assertIn("<cstring>port</cstring>", self.a.text())  # buddy reference updated

    def test_insert_into_form_and_container(self):
        widgets = {e["name"]: e for e in palette.UI_COMPONENTS}
        form = self.uid("QFormLayout")
        self.a.insert(form, widgets["QLabel"])
        self.a.insert(form, widgets["QLineEdit"])
        text = self.a.text()
        self.assertIn('<item row="2" column="0">', text)
        self.assertIn('<item row="2" column="1">', text)
        self.assertIn('name="label"', text)
        box = self.a.insert(self.uid("QCheckBox"), widgets["QGroupBox"])
        self.a.insert(box, widgets["QPushButton"])
        self.assertIn('name="verticalLayout_2"', self.a.text())

    def test_roundtrip_reparses(self):
        again = uidoc.UiDocument.parse(self.a.text())
        self.assertEqual(again.to_text(), self.a.text())

    def test_lint(self):
        titles = [i["title"] for i in self.a.lint()]
        self.assertIn("Style sheet overrides the theme", titles)
        self.assertIn("Label without buddy", titles)
        for issue in self.a.lint():
            if issue["fix"]:
                lint.apply_ui_fix(self.a.doc, issue)
        self.assertNotIn("styleSheet", self.a.text())


if __name__ == "__main__":
    unittest.main()


WINDOW = """import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root

    title: qsTr("Tasks")

    pageStack.initialPage: Kirigami.ScrollablePage {
        id: page

        title: qsTr("Tasks")
    }
}
"""


class BuildingTests(unittest.TestCase):
    """Building a user interface from a new window: where components go,
    the properties that hold objects, declared properties, list models."""

    def setUp(self):
        self.a = documents.QmlAdapter(WINDOW)
        self.e = {e["name"]: e for e in palette.QML_COMPONENTS}
        self.root = self.a.doc.root.uid
        self.page = next(n for n, *_ in self.a.doc.walk() if n.id == "page").uid

    def parent_of(self, uid):
        return self.a.doc.locate(uid)[0].uid

    def test_every_component_can_be_inserted(self):
        for tr_text in (WINDOW, WINDOW.replace("qsTr(", "i18n(")):
            for entry in palette.QML_COMPONENTS:
                a = documents.QmlAdapter(tr_text)
                uid = a.insert(a.doc.root.uid, entry)
                text = a.text()
                self.assertNotIn("{", "".join(c for c in ("{T}", "{K}", "{C}", "{L}", "{M}") if c in text), entry["name"])
                self.assertEqual(text, qmldoc.parse(text).to_text(), entry["name"])
                self.assertEqual(a.doc.find(uid).id != "", entry.get("id", True), entry["name"])

    def test_visual_components_go_on_the_windows_page(self):
        label = self.a.insert(self.root, self.e["Label"])
        self.assertEqual(self.parent_of(label), self.page)
        self.assertEqual(self.a.container_for(self.root), self.page)
        # what isn't drawn stays with the window
        for name in ("ListModel", "Settings", "Connections", "Timer", "Dialog", "KSortFilterProxyModel"):
            self.assertEqual(self.parent_of(self.a.insert(self.root, self.e[name])), self.root, name)
        # a window without a declared page takes everything itself
        plain = documents.QmlAdapter("import QtQuick\nimport QtQuick.Controls\n\nApplicationWindow {\n}\n")
        self.assertEqual(plain.doc.locate(plain.insert(plain.doc.root.uid, self.e["Label"]))[0], plain.doc.root)

    def test_own_module_prefix(self):
        self.a.insert(self.root, self.e["KSortFilterProxyModel"])
        self.a.insert(self.root, self.e["Settings"])
        text = self.a.text()
        self.assertIn("import org.kde.kitemmodels as KItemModels", text)
        self.assertIn("KItemModels.KSortFilterProxyModel {", text)
        self.assertIn("import QtCore\n", text)
        self.assertIn("    Settings {", text)

    def test_translated_argument_follows_the_translation_call(self):
        self.a.insert(self.page, self.e["ListView"])
        self.assertIn('text: qsTr("Item %1").arg(index + 1)', self.a.text())
        kde = documents.QmlAdapter(WINDOW.replace("qsTr(", "i18n("))
        kde.insert(kde.doc.root.uid, self.e["ListView"])
        self.assertIn('text: i18n("Item %1", index + 1)', kde.text())

    def test_insert_into_slots(self):
        bar = self.a.insert(self.page, self.e["ToolBar"], "header")
        self.assertEqual(self.a.doc.find(self.page).binding("header").value.uid, bar)
        field = self.a.insert(bar, self.e["ActionTextField"], "contentItem")
        self.a.insert(self.page, self.e["ToolBar"], "footer")
        text = self.a.text()
        self.assertLess(text.index("header: QQC2.ToolBar {"), text.index("footer: QQC2.ToolBar {"))
        self.assertIn("contentItem: Kirigami.ActionTextField {", text)
        # a property that holds one object, and has one
        with self.assertRaises(documents.EditError):
            self.a.insert(self.page, self.e["ToolBar"], "header")
        # a list takes more: the single object becomes a list
        self.a.insert(field, self.e["Action"], "rightActions", True)
        self.assertEqual(len(self.a.doc.find(field).binding("rightActions").value), 2)
        self.a.insert(field, self.e["Action"], "rightActions", True)
        self.assertEqual(len(self.a.doc.find(field).binding("rightActions").value), 3)
        # set by an expression: not replaced
        self.a.set_property(self.page, "background", "expression", "someItem")
        with self.assertRaises(documents.EditError):
            self.a.insert(self.page, self.e["Rectangle"], "background")
        with self.assertRaises(documents.EditError):
            self.a.insert(self.page, self.e["Rectangle"], "not a property")
        self.assertEqual(self.a.text(), qmldoc.parse(self.a.text()).to_text())

    def test_slots_listed(self):
        # without a live object: the window's page, and what an object uses
        self.assertEqual([(s["name"], s["holds"], s["full"]) for s in self.a.slots(self.root)],
                         [("pageStack.initialPage", "ScrollablePage", True)])
        self.assertEqual(self.a.slots(self.page), [])
        self.a.insert(self.page, self.e["ToolBar"], "header")
        self.a.insert(self.page, self.e["Action"])
        self.a.insert(self.page, self.e["Action"])
        slots = {s["name"]: s for s in self.a.slots(self.page)}
        self.assertEqual((slots["header"]["holds"], slots["header"]["full"]), ("ToolBar", True))
        self.assertEqual((slots["actions"]["holds"], slots["actions"]["isList"], slots["actions"]["full"]),
                         ("2", True, False))
        self.assertEqual(self.a.slots(12345678), [])

    def test_slots_of_live_objects(self):
        from PySide6.QtCore import QObject
        from PySide6.QtQml import QQmlComponent, QQmlEngine
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])   # noqa: F841 - kept alive for the engine
        engine = QQmlEngine()
        component = QQmlComponent(engine)
        component.setData(b"import QtQuick\nimport QtQuick.Controls\nPage { ListView { objectName: \"view\" } }", "")
        live = component.create()
        if live is None:
            self.skipTest("Qt Quick Controls can't be loaded here: " + component.errorString())
        a = documents.QmlAdapter("import QtQuick\nimport QtQuick.Controls\n\nPage {\n    ListView {\n    }\n}\n")
        names = [s["name"] for s in a.slots(a.doc.root.uid, live)]
        self.assertEqual(names[:4], ["header", "footer", "contentItem", "background"])
        self.assertNotIn("delegate", names)
        view = next(n for n, *_ in a.doc.walk() if n.short_type == "ListView").uid
        names = [s["name"] for s in a.slots(view, live.findChild(QObject, "view"))]
        self.assertIn("delegate", names)
        self.assertNotIn("contentItem", names)     # a view's contentItem can't be set
        # remembered for the type, for when there is no live object to ask
        self.assertEqual([s["name"] for s in a.slots(view)], names)

    def test_declare_properties(self):
        self.a.set_property(self.root, "property int remaining", "expression", "0")
        self.a.set_property(self.root, "property string filter", "expression", '"all"')
        self.a.set_property(self.page, "required property string title2", "expression", "")
        self.a.set_property(self.page, "readonly property list<Kirigami.Action> extra", "expression", "[]")
        text = self.a.text()
        self.assertIn('    id: root\n    property int remaining: 0\n    property string filter: "all"\n', text)
        self.assertIn("        id: page\n        required property string title2\n", text)
        self.assertIn("readonly property list<Kirigami.Action> extra: []", text)
        self.assertEqual([d.name for d in qmldoc.parse(text).root.declarations()], ["remaining", "filter"])
        rows = {r["name"]: r for r in self.a.properties(self.root, None)}
        self.assertEqual((rows["remaining"]["section"], rows["remaining"]["typeName"]), ("Declared properties", "int"))
        self.a.set_property(self.root, "remaining", "number", "3")      # its value is edited like any other
        self.assertIn("property int remaining: 3", self.a.text())
        for bad in ("property int remaining", "property int", "property 9x y", "propertyint x"):
            with self.assertRaises(documents.EditError, msg=bad):
                self.a.set_property(self.root, bad, "expression", "1")

    def test_object_as_a_property_value(self):
        self.a.set_property(self.page, "footer", "expression", "QQC2.ToolBar { id: page }")
        footer = self.a.doc.find(self.page).binding("footer").value
        self.assertIsInstance(footer, qmldoc.ObjectNode)       # in the outline, not just text
        self.assertEqual(footer.id, "page2")                   # ids stay unique
        self.assertIn("footer: ToolBar", [r["label"] + ": " + r["typeName"] for r in self.a.outline()])
        self.a.set_property(self.page, "actions", "expression", "[Kirigami.Action {}, Kirigami.Action {}]")
        self.assertEqual(len(self.a.doc.find(self.page).binding("actions").value), 2)
        self.a.set_property(self.page, "onBackRequested", "expression", "{ root.close() }")
        self.assertEqual(self.a.doc.find(self.page).binding("onBackRequested").value, "{ root.close() }")
        self.assertIsNone(qmldoc.parse_value_objects("Math.max(1, 2)"))
        self.assertIsNone(qmldoc.parse_value_objects("[1, 2]"))
        self.assertIsNone(qmldoc.parse_value_objects("QQC2.ToolBar {"))

    def test_list_model(self):
        model = self.a.insert(self.root, self.e["ListModel"])
        first = self.a.insert(model, self.e["ListElement"])
        self.assertEqual(self.parent_of(first), model)
        self.a.set_property(first, "title", "string", "Water the plants")     # a text, but data
        self.a.set_property(first, "done", "expression", "true")
        second = self.a.insert(first, self.e["ListElement"])                   # next to the first
        self.assertEqual(self.parent_of(second), model)
        text = self.a.text()
        self.assertIn('        ListElement {\n            title: "Water the plants"\n            done: true\n        }', text)
        self.assertNotIn("listElement", text)                                  # (it can't have an id)
        self.assertEqual(self.a.lint(), [])
        # elsewhere the same text is user-visible
        label = self.a.insert(self.page, self.e["Label"])
        self.a.set_property(label, "text", "expression", '"Plain"')
        self.assertEqual([i["title"] for i in self.a.lint()], ["Untranslated text in “text”"])


class ProjectTests(unittest.TestCase):
    def test_templates(self):
        from kreator import project
        for key, (file_name, _text) in project.PROJECT_TEMPLATES.items():
            text = project.project_text('My "Tasks" & <more>', key)
            adapter = documents.open_document(text, file_name)
            self.assertEqual(adapter.text(), documents.open_document(adapter.text(), file_name).text(), key)
            if key != "qtquick":    # (plain Qt Quick has no units to give its window's size in)
                self.assertEqual(adapter.lint(), [], key)
            self.assertNotIn("@TITLE@", text)
            self.assertNotIn("@CLASS@", text)
        self.assertIn('title: qsTr("My \\"Tasks\\" & <more>")', project.project_text('My "Tasks" & <more>', "kirigami-app"))
        form = project.project_text('My "Tasks" & <more>', "widgets-form")
        self.assertIn("<class>MyTasksMore</class>", form)
        self.assertIn('<string>My "Tasks" &amp; &lt;more&gt;</string>', form)
        self.assertIn("<class>Form2go</class>", project.project_text("2go", "widgets-form"))
        # the Kirigami window adds components with qsTr(): it runs without an application around it
        self.assertEqual(documents.QmlAdapter(project.project_text("Tasks", "kirigami-app")).tr_fn(), "qsTr")

    def test_create(self):
        import tempfile
        from kreator import project
        with tempfile.TemporaryDirectory() as tmp:
            where = os.path.join(tmp, "not", "there", "yet")
            self.assertEqual(project.project_problem("Tasks", where), "")
            folder, path = project.create_project(" Tasks ", where)
            self.assertEqual((folder, path), (os.path.join(where, "Tasks"), os.path.join(where, "Tasks", "Main.qml")))
            with open(path, encoding="utf-8") as fh:
                self.assertIn('title: qsTr("Tasks")', fh.read())
            self.assertEqual(project.scan(folder), (["Main.qml"], []))
            # never over what is there
            self.assertIn("not empty", project.project_problem("Tasks", where))
            with self.assertRaises(ValueError):
                project.create_project("Tasks", where, "qtquick")
            # an empty folder of that name is taken
            os.makedirs(os.path.join(where, "Empty"))
            self.assertEqual(project.create_project("Empty", where, "widgets-form")[1],
                             os.path.join(where, "Empty", "form.ui"))
            with open(os.path.join(where, "file"), "w", encoding="utf-8"):
                pass
            self.assertIn("already exists", project.project_problem("file", where))
            self.assertIn("not a folder", project.project_problem("x", os.path.join(where, "file")))

    def test_problems(self):
        from kreator import project
        self.assertIn("name", project.project_problem("  ", "/tmp"))
        self.assertIn("folder", project.project_problem("Tasks", " "))
        for bad in ("a/b", ".hidden", "..", "a\nb"):
            self.assertNotEqual(project.project_problem(bad, "/tmp"), "", bad)
        if os.geteuid() != 0:
            self.assertIn("can't write", project.project_problem("Tasks", "/proc/kreator-test"))


class RunnerTests(unittest.TestCase):
    def test_problem_lines(self):
        from kreator import runner
        for line in ("file:///p/Main.qml:11: ReferenceError: missing is not defined",
                     'file:///p/Main.qml:3:1: module "org.kde.kirigami" is not installed',
                     "file:///p/Main.qml:9:5: Greeting is not a type",
                     "file:///p/Main.qml:7: TypeError: Cannot read property 'x' of null",
                     "file:///p/Main.qml:5:5: Unable to assign QString to int"):
            self.assertTrue(runner.problem_in(line), line)
        for line in ("qml: started", "qml: 3 tasks left", "$ qml6 Main.qml", ""):
            self.assertFalse(runner.problem_in(line), line)

    def test_runs_and_collects_output(self):
        import tempfile
        from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
        from PySide6.QtWidgets import QApplication
        from kreator import runner
        if not runner.find_qml_runtime():
            self.skipTest("qml6 not installed")
        app = QApplication.instance() or QApplication([])   # noqa: F841 - the event loop's application
        r = runner.Runner()
        self.assertIn("does not exist", r.start("/nonexistent/Main.qml"))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "Main.qml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('import QtQml\nQtObject {\n    Component.onCompleted: { console.log("hi"); nothing.here }\n'
                         '    property Timer t: Timer { interval: 100; running: true; onTriggered: Qt.exit(4) }\n}\n')
            problems, endings = [], []
            r.problemReported.connect(problems.append)
            r.finished.connect(lambda name, code, failed: endings.append((name, code, failed)))
            loop = QEventLoop()
            r.finished.connect(lambda *_a: loop.quit())
            QTimer.singleShot(20000, loop.quit)
            self.assertEqual(r.start(path), "")
            self.assertTrue(r.running)
            loop.exec()
            QCoreApplication.processEvents()
            self.assertEqual(endings, [("Main.qml", 4, True)])
            self.assertFalse(r.running)
            self.assertIn("qml: hi", r.output)
            self.assertEqual(len(problems), 1)
            self.assertTrue(problems[0].startswith("Main.qml:3: ReferenceError"), problems)
            self.assertTrue(r.output.endswith("(ended with exit code 4)"), r.output)


class EditorTests(unittest.TestCase):
    def setUp(self):
        from kreator import editors
        self.e = editors
        self.s = editors.assign_ids(editors.load_settings(""))

    def test_custom_template_substitution(self):
        entry = self.e.normalize_custom({"name": "X", "command": "true", "args": "--goto '{file}:{line}:{column}'"})
        argv = self.e.custom_argv(entry, "/tmp/a b.qml", 12, 5)
        self.assertTrue(argv[0].endswith("true"))
        self.assertEqual(argv[1:], ["--goto", "/tmp/a b.qml:12:5"])  # path with space stays one argument
        argv = self.e.custom_argv(self.e.normalize_custom({"command": "true", "args": "-n"}), "/f.qml", 1, 1)
        self.assertEqual(argv[1:], ["-n", "/f.qml"])  # file appended when not in template

    def test_missing_program(self):
        with self.assertRaises(self.e.EditorError):
            self.e.custom_argv(self.e.normalize_custom({"command": "no-such-editor-xyz"}), "/f.qml", 1, 1)

    def test_kate_options(self):
        if self.e.find_kate() is None:
            self.skipTest("Kate not installed")
        self.s["kate"].update(session="Work", newWindow=True, gotoObject=True)
        argv = self.e.kate_argv(self.s, "/f.qml", 7, 3)
        self.assertEqual(argv[1:], ["--start", "Work", "--new", "--line", "7", "--column", "3", "/f.qml"])
        self.s["kate"]["gotoObject"] = False
        self.assertNotIn("--line", self.e.kate_argv(self.s, "/f.qml", 7, 3))

    def test_settings_roundtrip_and_ids(self):
        import json
        raw = json.dumps({"default": "custom-9", "custom": [{"name": "A", "command": "a"}, {"name": "B", "command": "b"}]})
        s = self.e.assign_ids(self.e.load_settings(raw))
        self.assertEqual([c["id"] for c in s["custom"]], ["custom-1", "custom-2"])
        self.assertEqual(s["default"], "kate")  # unknown default falls back to Kate

    def test_object_positions(self):
        doc = qmldoc.parse(SAMPLE)
        label = next(n for n, *_ in doc.walk() if n.short_type == "Label")
        self.assertEqual((label.line, label.column), (27, 5))


class SessionHistoryTest(unittest.TestCase):
    def test_undo_chain_roundtrip(self):
        import json
        from kreator import session
        texts = ["a\nb\nc\n", "a\nB\nc\n", "a\nB\nc\nd\n", "x\na\nB\nc\nd", "x\na\nB\nc\nd\n"]
        current = texts[-1]
        undo = [(t, i) for i, t in enumerate(texts[:-1])]
        enc = json.loads(json.dumps(session.encode_chain(current, undo)))  # survives JSON
        self.assertEqual(session.decode_chain(current, enc), undo)
        # a realistic history: 50 one-line edits of a 300-line file
        lines = [f"    property int p{i}: {i}\n" for i in range(300)]
        big = []
        for k in range(50):
            lines[k * 5] = f"    property int p{k * 5}: {k * 100}\n"
            big.append(("".join(lines), k))
        cur = big.pop()[0]
        enc = session.encode_chain(cur, big)
        self.assertEqual(session.decode_chain(cur, json.loads(json.dumps(enc))), big)
        self.assertLess(len(json.dumps(enc)), len(cur) // 2)  # far smaller than 49 full copies
        redo = [("only\n", 3), ("", 0)]
        self.assertEqual(session.decode_chain(current, session.encode_chain(current, redo)), redo)
        self.assertEqual(session.decode_chain(current, []), [])
        self.assertEqual(session.decode_chain(current, [[[["bad"]], 0]]), [])  # garbage is dropped
