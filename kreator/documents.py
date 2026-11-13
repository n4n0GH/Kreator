"""Common editing interface over QML and Qt Designer documents."""

from __future__ import annotations

import re

import shiboken6
from PySide6.QtCore import QMetaType, QObject

from . import lint, palette, qmldoc, uidoc
from .signalflow import _FUNC, _SIGNAL_DECL

TRANSLATABLE = {"text", "title", "subtitle", "placeholderText", "explanation", "label", "description",
                "tooltip", "toolTip", "statusTip", "whatsThis", "windowTitle", "heading", "helpfulAction"}
HIDDEN_LIVE = {"objectName", "parent", "data", "resources", "children", "visibleChildren", "states",
               "transitions", "transform", "contentChildren", "contentData", "layer", "anchors",
               "containmentMask", "childrenRect", "baselineOffset", "activeFocus", "activeFocusOnTab",
               "focusPolicy", "focusReason", "palette", "font", "locale", "background", "contentItem"}


class EditError(Exception):
    pass


_SAFE_TYPES = {
    "bool", "int", "uint", "double", "float", "qreal", "qlonglong", "qulonglong", "long", "short",
    "QString", "QColor", "QUrl", "QSize", "QSizeF", "QRect", "QRectF", "QPoint", "QPointF", "QFont",
}


# Types whose C++ getters crash outside their host application (plasmashell)
_UNREADABLE_CLASSES = ("PlasmoidItem", "ContainmentItem", "Plasma::", "WallpaperItem")


def _safe_read(prop, obj):
    """Read a property only if PySide can convert its type (some crash it)."""
    if not shiboken6.isValid(obj) or obj.metaObject().className().startswith(_UNREADABLE_CLASSES):
        return None
    tname = prop.typeName() or ""
    if not (prop.isEnumType() or tname in _SAFE_TYPES
            or (tname.endswith("*") and prop.metaType().flags() & QMetaType.TypeFlag.PointerToQObject)):
        return None
    try:
        return prop.read(obj)
    except Exception:  # noqa: BLE001
        return None


def _live_value(obj: QObject, name: str):
    """Read a (possibly dotted) property from a live object."""
    cur = obj
    for part in name.split("."):
        if cur is None or not isinstance(cur, QObject):
            return None
        mo = cur.metaObject()
        idx = mo.indexOfProperty(part)
        if idx < 0:
            return None
        cur = _safe_read(mo.property(idx), cur)
    return cur


def _fmt_live(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, (int, str)):
        return str(v)
    name = type(v).__name__
    try:
        if name == "QColor":
            return v.name()
        if name in ("QSizeF", "QSize"):
            return f"{v.width():g} × {v.height():g}"
        if name in ("QRectF", "QRect"):
            return f"{v.x():g}, {v.y():g}, {v.width():g} × {v.height():g}"
        if name in ("QPointF", "QPoint"):
            return f"{v.x():g}, {v.y():g}"
        if name == "QFont":
            return f"{v.family()} {v.pointSizeF():g}pt"
        if name == "QUrl":
            return v.toString()
    except Exception:  # noqa: BLE001
        pass
    if isinstance(v, QObject):
        return v.metaObject().className().split("_QML")[0]
    if isinstance(v, (list, tuple)):
        return f"[{len(v)}]"
    return ""


def live_properties(obj: QObject):
    """Yield (name, kind, value, enumKeys, enumScope, writable)."""
    if obj is None or not shiboken6.isValid(obj):
        return
    mo = obj.metaObject()
    for i in range(mo.propertyCount()):
        p = mo.property(i)
        name = p.name()
        if name.startswith("_") or name in HIDDEN_LIVE:
            continue
        value = _safe_read(p, obj)
        keys = []
        scope = ""
        tid = p.metaType().id()
        tname = p.typeName() or ""
        if p.isEnumType():
            me = p.enumerator()
            keys = [me.key(k) for k in range(me.keyCount())]
            scope = me.scope()
            kind = "set" if p.isFlagType() else "enum"
            try:
                ival = int(value) if not hasattr(value, "value") else int(value.value)
            except (TypeError, ValueError):
                ival = None
            if ival is not None:
                if p.isFlagType():
                    value = me.valueToKeys(ival).data().decode() if hasattr(me.valueToKeys(ival), "data") else str(me.valueToKeys(ival))
                else:
                    value = me.valueToKey(ival) or str(ival)
            else:
                value = str(value).rsplit(".", 1)[-1] if value is not None else ""
        elif tid == QMetaType.Type.Bool.value:
            kind = "bool"
        elif tid in (QMetaType.Type.Int.value, QMetaType.Type.Double.value, QMetaType.Type.Float.value,
                     QMetaType.Type.UInt.value, QMetaType.Type.LongLong.value):
            kind = "number"
        elif tid == QMetaType.Type.QString.value:
            kind = "string"
        elif tid == QMetaType.Type.QColor.value:
            kind = "color"
        elif tname in ("QSize", "QRect", "QPoint"):
            kind = tname[1:].lower()
        else:
            kind = "expression"
        yield name, kind, value if isinstance(value, str) else _fmt_live(value), keys, scope, p.isWritable()


# =========================================================================== QML

# objects that don't take children: inserting "into" one adds a sibling after it
LEAF_TYPES = {"Button", "Label", "TextField", "CheckBox", "Switch", "RadioButton", "Heading", "Icon",
              "Separator", "Slider", "SpinBox", "ComboBox", "ProgressBar", "BusyIndicator", "ToolButton",
              "SearchField", "Chip", "LinkButton", "SelectableLabel", "Image", "Timer", "Action", "Text",
              "ListElement"}

# Properties that hold an object (or a list of them) and that a component
# from the Add tab can be put into instead of among an object's children:
# a page's header, a control's contentItem, a view's delegate… Offered for an
# object when its live counterpart in the preview has the property.
SLOT_PROPERTIES = ("header", "footer", "contentItem", "background", "delegate", "highlight", "indicator",
                   "handle", "actions", "leftActions", "rightActions", "globalDrawer", "contextDrawer",
                   "titleDelegate", "helpfulAction", "sourceComponent")
# a Kirigami window's first page
PAGE_SLOT = "pageStack.initialPage"

# a palette snippet's translated text with an argument: {T}("Item %1", index + 1)
_TR_WITH_ARGUMENT = re.compile(r'\{T\}\(("(?:[^"\\]|\\.)*"), ([^()]+)\)')

# `property int count`, `required property string title`, as typed where a
# property is added: declares the property instead of setting one
_DECLARATION = re.compile(r"((?:(?:readonly|required|default|final)\s+)*)property\s+"
                          r"([A-Za-z_][\w.]*(?:<[\w.]+>)?)\s+([A-Za-z_]\w*)")

# x / y values that placing an object may replace: numbers and Kirigami units
_POSITION_VALUE = re.compile(r"-?\d+(\.\d+)?|(\w+\.)?Units\.\w+(\s*\*\s*-?\d+(\.\d+)?)?")
# the Kirigami units a design grid can be measured in
GRID_UNITS = ("smallSpacing", "largeSpacing", "gridUnit")


class QmlAdapter:
    kind = "qml"
    # type name -> {slot property: is a list}, as live objects showed (see slots())
    _slots_of_type: dict[str, dict[str, bool]] = {}

    def __init__(self, text: str):
        self.doc = qmldoc.parse(text)
        if self.doc.root is None:
            raise qmldoc.QmlSyntaxError("the file contains no QML object")

    def text(self) -> str:
        return self.doc.to_text()

    # -- conventions --------------------------------------------------------
    def tr_fn(self) -> str:
        src = self.doc.to_text()
        if re.search(r"\bi18nc?\(", src):
            return "i18n"
        if "qsTr(" in src:
            return "qsTr"
        return "i18n" if self.doc.import_alias("org.kde.kirigami") is not None else "qsTr"

    def prefixes(self, ensure=()):
        """Prefixes for Kirigami / Controls / Layouts; import modules listed in `ensure`."""
        out = {}
        for key, (mod, alias) in {"K": palette.KIRIGAMI, "C": palette.CONTROLS, "L": palette.LAYOUTS}.items():
            if key in ensure:
                out[key] = self.doc.ensure_import(mod, alias)
            else:
                a = self.doc.import_alias(mod)
                out[key] = (a + ".") if a else ("" if a == "" else (alias + "." if alias else ""))
        return out

    # -- outline --------------------------------------------------------------
    def outline(self):
        for node, depth, _parent, label in self.doc.walk():
            has_children = any(True for _ in node.child_slots())
            yield {
                "uid": node.uid, "depth": depth, "typeName": node.short_type,
                "fullType": node.type_name, "objectId": node.id,
                "label": label + (f" on {node.on_target}" if node.on_target else "")
                + (f"component {node.component_name}" if node.component_name else ""),
                "hasChildren": has_children,
            }

    def node(self, uid):
        n = self.doc.find(uid)
        if n is None:
            raise EditError("the selected object no longer exists")
        return n

    def node_info(self, uid):
        n = self.doc.find(uid)
        if n is None:
            return None
        return {"type": n.type_name, "id": n.id, "idLabel": "id"}

    # -- properties -------------------------------------------------------------
    def properties(self, uid, live: QObject | None, parent_type: str = ""):
        n = self.doc.find(uid)
        if n is None:
            return []
        rows = []
        seen = {"id"}
        for name, b in n.bindings():
            if name == "id":
                continue
            seen.add(name)
            kind, display = qmldoc.classify(b.value)
            first = name.split(".", 1)[0]
            if re.match(r"on[A-Z]", name.rsplit(".", 1)[-1]):
                section = "Signal handlers"
                kind = "script" if kind == "expression" else kind
            elif first[:1].isupper():
                section = "Attached"
            else:
                section = "Properties"
            if kind == "expression" and "\n" in display:
                kind = "script"
            live_val = _fmt_live(_live_value(live, name)) if live is not None and section == "Properties" else ""
            rows.append(self._row(name, kind, display, True, section, live=live_val,
                                  raw=b.value if isinstance(b.value, str) else ""))
        for d in n.declarations():
            seen.add(d.name)
            if d.value is None:
                kind, display = "unset", ""
            else:
                kind, display = qmldoc.classify(d.value)
                if kind == "expression" and "\n" in display:
                    kind = "script"
            live_val = _fmt_live(_live_value(live, d.name)) if live is not None else ""
            rows.append(self._row(d.name, kind, display, d.value is not None, "Declared properties",
                                  live=live_val, typeName=" ".join(d.modifiers + [d.type_name]),
                                  raw=d.value if isinstance(d.value, str) else ""))
        # attached-property suggestions based on the parent
        pk = self.prefixes()
        sugg = []
        if parent_type.rsplit(".", 1)[-1] in ("ColumnLayout", "RowLayout", "GridLayout", "FormLayout"):
            L = pk["L"]
            sugg += [(f"{L}Layout.fillWidth", "bool", "false"), (f"{L}Layout.fillHeight", "bool", "false"),
                     (f"{L}Layout.alignment", "expression", ""), (f"{L}Layout.preferredWidth", "number", ""),
                     (f"{L}Layout.maximumWidth", "number", "")]
        if parent_type.rsplit(".", 1)[-1] == "FormLayout":
            K = pk["K"]
            sugg = [(f"{K}FormData.label", "string", ""), (f"{K}FormData.isSection", "bool", "false"),
                    (f"{K}FormData.buddyFor", "expression", "")] + sugg
        for name, kind, val in sugg:
            if name not in seen:
                seen.add(name)
                rows.append(self._row(name, kind, val, False, "Attached"))
        if live is not None:
            live_list = list(live_properties(live))
            enums = {name: keys for name, kind, _v, keys, _s, _w in live_list if kind == "enum"}
            # show enum bindings such as `QQC2.Label.AlignHCenter` as drop-downs
            for r in rows:
                keys = enums.get(r["name"])
                if keys and r["kind"] == "expression":
                    key = r["value"].rsplit(".", 1)[-1]
                    if key in keys:
                        r["kind"], r["value"], r["enumKeys"] = "enum", key, keys
            for name, kind, value, keys, _scope, writable in live_list:
                if name in seen or not writable:
                    continue
                if kind == "set":
                    kind = "expression"
                rows.append(self._row(name, kind, value, False, "All properties", enumKeys=keys))
        order = {"Properties": 0, "Attached": 1, "Declared properties": 2, "Signal handlers": 3, "All properties": 4}
        rows.sort(key=lambda r: order.get(r["section"], 5))
        return rows

    @staticmethod
    def _row(name, kind, value, is_set, section, live="", enumKeys=None, typeName="", raw=""):
        return {"name": name, "kind": kind, "value": str(value), "isSet": is_set, "section": section,
                "liveValue": live, "enumKeys": enumKeys or [], "typeName": typeName,
                "raw": str(raw)}

    def encode(self, n: qmldoc.ObjectNode, name: str, kind: str, value: str) -> str:
        b = n.binding(name)
        old = b.value if b is not None and isinstance(b.value, str) else None
        if old is None:
            for d in n.declarations():
                if d.name == name and isinstance(d.value, str):
                    old = d.value
        value = value if value is not None else ""
        if kind == "bool":
            return "true" if value in ("true", True, "1") else "false"
        if kind == "number":
            v = value.strip()
            if not re.fullmatch(r"-?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", v):
                raise EditError(f"“{v}” is not a number. Switch to an expression to use a binding.")
            return v
        if kind in ("string", "translated"):
            if old is not None:
                okind, _ = qmldoc.classify(old)
                if okind == "translated":
                    return qmldoc.replace_translated_text(old, value)
                if okind == "string":
                    return qmldoc.quote(value)
            short = name.rsplit(".", 1)[-1]
            # (a ListElement's values can't be script, such as i18n())
            if (short in TRANSLATABLE or kind == "translated") and n.short_type != "ListElement":
                return f"{self.tr_fn()}({qmldoc.quote(value)})"
            return qmldoc.quote(value)
        if kind == "color":
            return qmldoc.quote(value.strip())
        if kind == "enum":
            return f"{n.type_name}.{value.strip()}"
        # expression / script
        if not value.strip():
            raise EditError("empty expression")
        try:
            qmldoc.parse(f"Item {{\n    __x: {value}\n}}\n")
        except qmldoc.QmlSyntaxError as e:
            raise EditError(f"invalid expression: {e}") from e
        return value.strip()

    def set_property(self, uid, name, kind, value):
        n = self.node(uid)
        name = (name or "").strip()
        decl = _DECLARATION.fullmatch(name)
        if decl:
            return self.declare_property(uid, decl.group(1).split(), decl.group(2), decl.group(3), value)
        if not re.fullmatch(r"[A-Za-z_][\w]*(\.[A-Za-z_]\w*)*", name):
            raise EditError(f"“{name}” is not a valid property name")
        if name == "id":
            return self.set_id(uid, value)
        encoded = self.encode(n, name, kind, value)
        if kind in ("expression", "script"):
            encoded = self._objects_in(encoded)
        n.set_binding(name, encoded)

    def _objects_in(self, value: str):
        """An expression that is an object (`QQC2.ToolBar {}`) or a list of
        objects becomes one in the document, so it shows in the outline and
        can be selected and filled like any other."""
        objects = qmldoc.parse_value_objects(value)
        if objects is None:
            return value
        for top in ([objects] if isinstance(objects, qmldoc.ObjectNode) else objects):
            self._uniquify_ids(top)
        return objects

    def declare_property(self, uid, modifiers, type_name, name, value=""):
        """Declare a property of the object: `[modifiers] property <type> <name>[: value]`."""
        n = self.node(uid)
        if name == "id" or any(d.name == name for d in n.declarations()):
            raise EditError(f"“{name}” is already declared in this object")
        decl = qmldoc.PropertyDecl(modifiers=list(modifiers), type_name=type_name, name=name)
        if value is not None and value.strip():
            decl.value = self._objects_in(self.encode(n, name, "expression", value))
        # after the declarations there are, else right after the id
        at = 0
        for i, m in enumerate(n.members):
            if isinstance(m, qmldoc.PropertyDecl) or (isinstance(m, qmldoc.Binding) and m.name == "id"):
                at = i + 1
        n.members.insert(at, decl)

    def remove_member(self, uid, name, kind):
        """Remove a declared member of an object, with its comments: a
        function ("name()"), a signal or a property (kind "function",
        "signal", "property")."""
        n = self.node(uid)
        for m in n.members:
            if kind == "property" and isinstance(m, qmldoc.PropertyDecl) and m.name == name:
                break
            if isinstance(m, qmldoc.RawMember):
                if kind == "function" and (fm := _FUNC.match(m.text)) and f"{fm.group(1)}()" == name:
                    break
                if kind == "signal" and (sm := _SIGNAL_DECL.match(m.text)) and sm.group(1) == name:
                    break
        else:
            raise EditError(f"“{name}” is not declared in this object")
        n.members.remove(m)
        return True

    def remove_property(self, uid, name):
        n = self.node(uid)
        if not n.remove_binding(name):
            raise EditError(f"“{name}” is not set")

    def set_id(self, uid, value):
        n = self.node(uid)
        value = value.strip()
        if not value:
            n.remove_binding("id")
            return
        if not re.fullmatch(r"[a-z_][\w]*", value):
            raise EditError("ids must start with a lower-case letter or underscore")
        if value != n.id and value in self.doc.all_ids():
            raise EditError(f"the id “{value}” is already used")
        old = n.id
        n.set_binding("id", value)
        if old and old != value:
            self._rename_references(old, value)

    def _rename_references(self, old, new):
        pat = re.compile(r"(?<![\w.$])" + re.escape(old) + r"(?![\w$])")

        def fix(v):
            return pat.sub(new, v) if isinstance(v, str) else v

        for node, *_ in self.doc.walk():
            for m in node.members:
                if isinstance(m, (qmldoc.Binding, qmldoc.PropertyDecl)) and isinstance(m.value, str) and m.name != "id":
                    m.value = fix(m.value)
                elif isinstance(m, qmldoc.RawMember):
                    m.text = fix(m.text)
                elif isinstance(m, qmldoc.GroupNode):
                    for gm in m.members:
                        if isinstance(gm, qmldoc.Binding) and isinstance(gm.value, str):
                            gm.value = fix(gm.value)

    def set_type(self, uid, type_name):
        n = self.node(uid)
        if not re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*", type_name.strip()) or not qmldoc._is_type_name(type_name.strip()):
            raise EditError("type names must start with an upper-case letter")
        n.type_name = type_name.strip()

    # -- structure ------------------------------------------------------------
    def palette(self):
        return palette.QML_COMPONENTS

    def insert(self, uid, entry: dict, slot: str = "", slot_is_list: bool = False) -> int:
        """Add a palette component to an object: among its children (where
        that kind of component belongs), or into the property `slot`."""
        target = self.doc.find(uid) if uid else self.doc.root
        if target is None:
            target = self.doc.root
        tr = self.tr_fn()  # decide before imports change
        mod, alias = entry["module"]
        need = {"K"} if "{K}" in entry["qml"] else set()
        need |= {"C"} if "{C}" in entry["qml"] else set()
        need |= {"L"} if "{L}" in entry["qml"] else set()
        own_prefix = self.doc.ensure_import(mod, alias)
        if "QtQuick" not in [m for m, _ in self.doc.imports()]:
            self.doc.ensure_import("QtQuick")
        pk = self.prefixes(ensure=need)
        snippet = entry["qml"]
        if not tr.startswith("i18n"):
            # i18n("Item %1", n) is qsTr("Item %1").arg(n)
            snippet = _TR_WITH_ARGUMENT.sub(r"{T}(\1).arg(\2)", snippet)
        snippet = snippet.replace("{T}", tr).replace("{M}", own_prefix)
        for k, v in pk.items():
            snippet = snippet.replace("{" + k + "}", v)
        node = qmldoc.parse_object_snippet(snippet)
        if entry.get("id", True):
            node.set_binding("id", self.doc.unique_id(entry["name"]))
        if slot:
            self._place_in_slot(target, node, slot, slot_is_list)
            return node.uid
        target = self._content_target(target, entry)
        parent_of_target = self.doc.locate(target.uid)
        # Form layout children get a label
        if target.short_type == "FormLayout" and entry.get("slot") is None and entry["name"] not in ("Separator",):
            node.set_binding(f"{pk['K'] or self.doc.ensure_import('org.kde.kirigami', 'Kirigami')}FormData.label",
                             f'{tr}("{entry["name"]}:")')
        if target.short_type in ("ColumnLayout", "RowLayout", "GridLayout") and entry["name"] in (
                "TextField", "TextArea", "ProgressBar", "Slider", "SearchField", "ListView", "ScrollView"):
            node.set_binding(f"{pk['L']}Layout.fillWidth", "true")
        self._place(target, node, entry.get("slot"), parent_of_target)
        return node.uid

    def _window_page(self, target):
        """The first page of a Kirigami window, when the window declares it."""
        if target is self.doc.root and target.short_type == "ApplicationWindow":
            b = target.binding(PAGE_SLOT)
            if b is not None and isinstance(b.value, qmldoc.ObjectNode):
                return b.value
        return None

    def _content_target(self, target, entry):
        """Where a component added to `target` goes: what is drawn belongs on
        a Kirigami window's page, not over it; models, dialogs and the like
        stay with the window."""
        if entry.get("visual", True) and not entry.get("slot"):
            return self._window_page(target) or target
        return target

    def slots(self, uid, live: QObject | None = None) -> list[dict]:
        """The properties of an object that a component can be put into:
        [{name, isList, holds, full}]. `holds` says what is there now, and
        `full` that nothing can be added (a single object, or an expression)."""
        n = self.doc.find(uid)
        if n is None:
            return []
        # What the type has is asked of the live object, and remembered: just
        # after an edit, or when the preview fails, there is none to ask.
        known = None
        if live is not None and shiboken6.isValid(live):
            mo = live.metaObject()
            known = {}
            for name in SLOT_PROPERTIES:
                i = mo.indexOfProperty(name)
                if i < 0:
                    continue
                prop = mo.property(i)
                tname = prop.typeName() or ""
                if tname.startswith("QQmlListProperty"):
                    known[name] = True
                elif prop.isWritable() and (tname.endswith("*") or tname in ("QVariant", "QJSValue")):
                    known[name] = False
            self._slots_of_type[n.type_name] = known
        else:
            known = self._slots_of_type.get(n.type_name)
        names = list(SLOT_PROPERTIES)
        if n is self.doc.root and n.short_type == "ApplicationWindow" and self.doc.import_alias(palette.KIRIGAMI[0]) is not None:
            names.insert(0, PAGE_SLOT)
        out = []
        for name in names:
            holder = n.binding(name) or next((d for d in n.declarations() if d.name == name), None)
            value = holder.value if holder is not None else None
            is_list = isinstance(value, list)
            if name == PAGE_SLOT:
                pass
            elif known is not None:
                if name not in known:
                    continue
                is_list = is_list or known[name]
            elif value is None:
                continue    # nothing known about the type: only what the object already uses
            if isinstance(value, qmldoc.ObjectNode):
                holds = value.short_type
            elif isinstance(value, list):
                holds = str(len(value))
            elif isinstance(value, str) and value.strip() not in ("", "[]", "null", "undefined"):
                holds = "expression"
            else:
                holds = ""
            full = holds == "expression" or (isinstance(value, qmldoc.ObjectNode) and not is_list)
            out.append({"name": name, "isList": is_list, "holds": holds, "full": full})
        return out

    def _place_in_slot(self, target, node, slot, is_list=False):
        """Put node into the property `slot` of target (appending to a list)."""
        if not re.fullmatch(r"[a-z_]\w*(\.[a-z_]\w*)*", slot):
            raise EditError(f"“{slot}” is not a property that takes an object")
        holder = target.binding(slot) or next((d for d in target.declarations() if d.name == slot), None)
        value = holder.value if holder is not None else None
        if isinstance(value, list):
            value.append(node)
        elif isinstance(value, qmldoc.ObjectNode):
            if not is_list:
                raise EditError(f"“{slot}” already holds a {value.short_type}. Select it to change it, "
                                "or delete it first.")
            holder.value = [value, node]
        elif isinstance(value, str) and value.strip() not in ("", "[]", "null", "undefined"):
            raise EditError(f"“{slot}” is set by an expression. Change it in the properties or the source view.")
        elif holder is not None:
            holder.value = node
        else:
            # after the object's other properties (a header added before a
            # footer stays before it), and before its children
            at = target._insert_index_for_binding()
            for i, m in enumerate(target.members):
                if isinstance(m, (qmldoc.Binding, qmldoc.PropertyDecl, qmldoc.GroupNode)):
                    at = max(at, i + 1)
            target.members.insert(at, qmldoc.Binding(name=slot, value=node))

    def _place(self, target, node, slot, parent_of_target):
        """Insert node into target, honouring special slots (actions, page, drawer)."""
        if slot == "actions":
            # find nearest page-like ancestor or the target itself
            b = target.binding("actions")
            if b is None and target.short_type not in ("Page", "ScrollablePage", "ActionToolBar", "GlobalDrawer",
                                                        "ContextDrawer", "Card", "AbstractCard", "Action"):
                target.members.append(node)
                return
            if target.short_type == "Action":
                b = target.binding("children")
                if b is None:
                    target.members.append(node)
                    return
            if b is None:
                b = qmldoc.Binding(name="actions", value=[])
                target.members.insert(target._insert_index_for_binding(), b)
            if isinstance(b.value, list):
                b.value.append(node)
            elif isinstance(b.value, qmldoc.ObjectNode):
                b.value = [b.value, node]
            else:
                raise EditError("this object's actions are set by an expression")
            return
        if slot == "page" and target.short_type == "ApplicationWindow" and target.binding("pageStack.initialPage") is None:
            target.set_binding("pageStack.initialPage", node)
            return
        if slot == "globalDrawer" and target.short_type == "ApplicationWindow":
            target.set_binding("globalDrawer", node)
            return
        # leaf controls: insert as sibling after target
        if target.short_type in LEAF_TYPES and parent_of_target is not None:
            _p, container, idx = parent_of_target
            if isinstance(container, list):
                container.insert(idx + 1, node)
                return
        target.members.append(node)

    # -- placing on the design grid ---------------------------------------------
    def container_for(self, uid) -> int:
        """The object that a component added to `uid` becomes a child of."""
        target = self.doc.find(uid) if uid else self.doc.root
        if target is None:
            target = self.doc.root
        if target.short_type in LEAF_TYPES:
            loc = self.doc.locate(target.uid)
            if loc and isinstance(loc[1], list):
                return loc[0].uid
        return (self._window_page(target) or target).uid

    def placement_problem(self, uid) -> str:
        """Why the object can't be given a position of its own ("" if it can).
        (Whether its parent positions it, a layout, is known from the preview.)"""
        n = self.node(uid)
        if n is self.doc.root:
            return "the root object fills the preview"
        for m in n.members:
            if isinstance(m, (qmldoc.Binding, qmldoc.GroupNode)) and (m.name == "anchors" or m.name.startswith("anchors.")):
                return "it is anchored"
        for name in ("x", "y"):
            b = n.binding(name)
            if b is not None and not (isinstance(b.value, str) and _POSITION_VALUE.fullmatch(b.value.strip())):
                return f"its {name} is set by an expression"
        return ""

    def position_value(self, value: float, step: float = 0, unit: str = "") -> str:
        """A coordinate as QML: a multiple of the Kirigami unit the grid is
        measured in when it is one (and Kirigami is imported), else pixels."""
        if unit in GRID_UNITS and step > 0 and self.doc.import_alias(palette.KIRIGAMI[0]) is not None:
            k = value / step
            if abs(k - round(k)) < 0.01:
                k = round(k)
                if k == 0:
                    return "0"
                base = f"{self.prefixes()['K']}Units.{unit}"
                return base if k == 1 else f"{base} * {k}"
        return str(round(value))

    def size_problem(self, uid) -> str:
        """Why the object can't be given a size of its own ("" if it can)."""
        n = self.node(uid)
        if n is self.doc.root:
            return "the root object fills the preview"
        for m in n.members:
            if isinstance(m, (qmldoc.Binding, qmldoc.GroupNode)) and (m.name == "anchors" or m.name.startswith("anchors.")):
                return "it is anchored"
        for name in ("width", "height"):
            b = n.binding(name)
            if b is not None and not (isinstance(b.value, str) and _POSITION_VALUE.fullmatch(b.value.strip())):
                return f"its {name} is set by an expression"
        return ""

    def set_geometry(self, uid, x, y, w, h, step=0, unit="", move=True):
        """Resize an object (and move it, for its left or top edge)."""
        problem = self.size_problem(uid) or (self.placement_problem(uid) if move else "")
        if problem:
            raise EditError(f"this object can't be resized: {problem}")
        n = self.node(uid)
        if move:
            n.set_binding("x", self.position_value(x, step, unit))
            n.set_binding("y", self.position_value(y, step, unit))
        n.set_binding("width", self.position_value(max(1, w), step, unit))
        n.set_binding("height", self.position_value(max(1, h), step, unit))
        return True

    def set_position(self, uid, x, y, step=0, unit=""):
        problem = self.placement_problem(uid)
        if problem:
            raise EditError(f"this object can't be placed: {problem}")
        n = self.node(uid)
        n.set_binding("x", self.position_value(x, step, unit))
        n.set_binding("y", self.position_value(y, step, unit))
        return True

    def delete(self, uid):
        n = self.node(uid)
        loc = self.doc.locate(uid)
        if loc is None:
            raise EditError("the root object cannot be deleted")
        parent, container, idx = loc
        if isinstance(container, list):
            container.pop(idx)
            for name, b in list(parent.bindings()):
                if isinstance(b.value, list) and not b.value and b.value is container:
                    parent.remove_binding(name)
        else:
            # single object assigned to a property
            if isinstance(container, qmldoc.PropertyDecl):
                container.value = None
            else:
                parent.members.remove(container) if container in parent.members else parent.remove_binding(container.name)
        _ = n
        return parent.uid

    def move(self, uid, delta):
        loc = self.doc.locate(uid)
        if loc is None:
            return False
        parent, container, idx = loc
        if not isinstance(container, list):
            return False
        # move among object siblings only
        positions = [i for i, m in enumerate(container) if isinstance(m, qmldoc.ObjectNode)]
        k = positions.index(idx)
        j = k + delta
        if not 0 <= j < len(positions):
            return False
        a, b = positions[k], positions[j]
        container[a], container[b] = container[b], container[a]
        return True

    def copy_text(self, uid) -> str:
        return qmldoc.node_to_text(self.node(uid))

    def paste(self, uid, text) -> int:
        try:
            node = qmldoc.parse_object_snippet(text)
        except qmldoc.QmlSyntaxError as e:
            raise EditError(f"the clipboard does not contain a QML object ({e})") from e
        self._uniquify_ids(node)
        target = self.doc.find(uid) if uid else self.doc.root
        self._place(target or self.doc.root, node, None, self.doc.locate(target.uid) if target else None)
        return node.uid

    def _uniquify_ids(self, node):
        used = self.doc.all_ids()
        for sub in qmldoc.iter_subtree(node):
            if sub.id and sub.id in used:
                new = self.doc.unique_id(re.sub(r"\d+$", "", sub.id))
                sub.set_binding("id", new)
                used.add(new)

    def duplicate(self, uid) -> int:
        n = self.node(uid)
        loc = self.doc.locate(uid)
        if loc is None:
            raise EditError("the root object cannot be duplicated")
        _parent, container, idx = loc
        if not isinstance(container, list):
            raise EditError("this object is the value of a property and cannot be duplicated")
        clone = qmldoc.clone_node(n)
        self._uniquify_ids(clone)
        container.insert(idx + 1, clone)
        return clone.uid

    # -- guidelines -----------------------------------------------------------
    def lint(self):
        return lint.lint_qml(self.doc)

    def apply_fix(self, issue):
        return lint.apply_qml_fix(self.doc, issue, self.tr_fn())

    def parent_type(self, uid):
        loc = self.doc.locate(uid)
        return loc[0].type_name if loc else ""


# =========================================================================== .ui

class UiAdapter:
    kind = "ui"

    def __init__(self, text: str):
        self.doc = uidoc.UiDocument.parse(text)
        if self.doc.root is None:
            raise uidoc.UiError("the form contains no widget")

    def text(self) -> str:
        return self.doc.to_text()

    def outline(self):
        for node, depth, _parent, label in self.doc.walk():
            yield {
                "uid": node.uid, "depth": depth, "typeName": node.type_name, "fullType": node.type_name,
                "objectId": node.id, "label": label,
                "hasChildren": any(True for _ in self.doc.children_of(node.el)),
            }

    def node(self, uid):
        n = self.doc.find(uid)
        if n is None:
            raise EditError("the selected object no longer exists")
        return n

    def node_info(self, uid):
        n = self.doc.find(uid)
        if n is None:
            return None
        return {"type": n.type_name, "id": n.id, "idLabel": "objectName"}

    def properties(self, uid, live: QObject | None, parent_type: str = ""):
        n = self.doc.find(uid)
        if n is None:
            return []
        rows = []
        seen = set()
        live_info = {}
        if live is not None:
            for name, kind, value, keys, scope, writable in live_properties(live):
                live_info[name] = (kind, value, keys, scope, writable)
        for p in self.doc.properties(n):
            name = p["name"]
            seen.add(name)
            kind = p["kind"]
            keys = []
            if kind in ("enum",) and name in live_info:
                _k, _v, lk, scope, _w = live_info[name]
                keys = [f"{scope}::{k}" for k in lk]
            section = "Layout item" if name.startswith("layout:") else (
                "Page" if name.startswith("attribute:") else "Properties")
            if not p["editable"]:
                kind = "readonly"
            rows.append(QmlAdapter._row(name, kind, p["value"], True, section, enumKeys=keys))
        for name, (kind, value, keys, scope, writable) in live_info.items():
            if name in seen or not writable or kind == "expression":
                continue
            if kind in ("enum", "set"):
                keys = [f"{scope}::{k}" for k in keys]
                if kind == "enum":
                    value = f"{scope}::{value}" if value and "::" not in value else value
                else:
                    value = "|".join(f"{scope}::{v}" for v in str(value).split("|") if v)
            rows.append(QmlAdapter._row(name, kind, value, False, "All properties", enumKeys=keys))
        order = {"Properties": 0, "Layout item": 1, "Page": 2, "All properties": 3}
        rows.sort(key=lambda r: order.get(r["section"], 4))
        return rows

    def set_property(self, uid, name, kind, value):
        n = self.node(uid)
        if name == "objectName":
            return self.set_id(uid, value)
        try:
            if kind in ("expression", "script", "unset"):
                kind = "string"
            self.doc.set_property(n, name, kind, value)
        except uidoc.UiError as e:
            raise EditError(str(e)) from e

    def remove_property(self, uid, name):
        if not self.doc.remove_property(self.node(uid), name):
            raise EditError(f"“{name}” is not set")

    def set_id(self, uid, value):
        n = self.node(uid)
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z_]\w*", value):
            raise EditError("object names must be valid C++ identifiers")
        if value != n.id and value in self.doc.all_names():
            raise EditError(f"the name “{value}” is already used")
        self.doc.rename(n, value)

    def set_type(self, uid, type_name):
        n = self.node(uid)
        if n.kind not in ("widget", "layout") or not re.fullmatch(r"[A-Za-z_][\w:]*", type_name.strip()):
            raise EditError("invalid class name")
        n.el.set("class", type_name.strip())

    def palette(self):
        return palette.UI_COMPONENTS

    def insert(self, uid, entry):
        target = self.doc.find(uid) if uid else None
        try:
            el = self.doc.insert(target, entry)
        except uidoc.UiError as e:
            raise EditError(str(e)) from e
        return self.doc.node(el).uid

    def delete(self, uid):
        n = self.node(uid)
        parent, _item = self.doc.container_of(n.el)
        if not self.doc.delete(n):
            raise EditError("the top-level widget cannot be deleted")
        while parent is not None and parent.tag not in ("widget", "layout"):
            parent = self.doc.container_of(parent)[0]
        return self.doc.node(parent).uid if parent is not None else None

    def move(self, uid, delta):
        return self.doc.move(self.node(uid), delta)

    def copy_text(self, uid):
        return self.doc.element_text(self.node(uid))

    def paste(self, uid, text):
        target = self.doc.find(uid) if uid else None
        try:
            el = self.doc.paste(target, text)
        except uidoc.UiError as e:
            raise EditError(str(e)) from e
        return self.doc.node(el).uid

    def duplicate(self, uid):
        el = self.doc.duplicate(self.node(uid))
        if el is None:
            raise EditError("the top-level widget cannot be duplicated")
        return self.doc.node(el).uid

    def lint(self):
        return lint.lint_ui(self.doc)

    def apply_fix(self, issue):
        return lint.apply_ui_fix(self.doc, issue)

    # signal/slot connections (the result is truthy: Backend._edit treats None as failure)
    def add_connection(self, sender, signal, receiver, slot):
        try:
            return self.doc.add_connection(sender, signal, receiver, slot)
        except uidoc.UiError as e:
            raise EditError(str(e)) from e

    def update_connection(self, index, sender, signal, receiver, slot):
        try:
            self.doc.update_connection(index, sender, signal, receiver, slot)
        except uidoc.UiError as e:
            raise EditError(str(e)) from e
        return True

    def remove_declared(self, uid, kind, signature):
        """Remove a signal or slot (kind "signal" / "function") the form
        declares for this widget's class."""
        cls = dict(self.doc.connectables()).get(self.node(uid).id, "")
        try:
            self.doc.remove_declared(cls, "signal" if kind == "signal" else "slot", signature)
        except uidoc.UiError as e:
            raise EditError(str(e)) from e
        return True

    def remove_connection(self, index):
        try:
            self.doc.remove_connection(index)
        except uidoc.UiError as e:
            raise EditError(str(e)) from e
        return True

    # -- placing on the design grid ---------------------------------------------
    _PLACING_PARENTS = uidoc.PAGED_CLASSES | {"QMainWindow", "QScrollArea", "QDockWidget", "QSplitter", "QMdiArea"}

    def placement_problem(self, uid) -> str:
        n = self.node(uid)
        if n.kind != "widget":
            return "only widgets can be placed freely"
        parent, item = self.doc.container_of(n.el)
        if parent is None or n.el is self.doc.root_el:
            return "it is the form itself"
        if parent.tag == "layout" or item is not None:
            return "it is in a layout"
        if parent.get("class") in self._PLACING_PARENTS:
            return f"its parent ({parent.get('class')}) places it"
        return ""

    def free_container(self, uid):
        """The widget without a layout that a widget dropped on `uid` is placed
        in, or None if it goes into a layout."""
        n = self.doc.find(uid) if uid else self.doc.root
        el = n.el if n is not None else self.doc.root_el
        while el is not None and not (el.tag == "widget" and self.doc._is_container(el)):
            el = self.doc.container_of(el)[0]
        if el is None:
            return None
        if el.get("class") == "QMainWindow":
            el = el.find("widget[@class='QWidget']")
        if el is None or el.get("class") in self._PLACING_PARENTS or el.find("layout") is not None:
            return None
        return self.doc.node(el).uid

    def size_problem(self, uid) -> str:
        return self.placement_problem(uid)

    def set_geometry(self, uid, x, y, w, h, step=0, unit="", move=True):
        problem = self.placement_problem(uid)
        if problem:
            raise EditError(f"this widget can't be placed: {problem}")
        self.set_property(uid, "geometry", "rect", f"{round(x)}, {round(y)}, {max(1, round(w))}, {max(1, round(h))}")
        return True

    def insert_free(self, container_uid, entry, x, y, w, h) -> int:
        """Add a widget to a widget without a layout, at a position."""
        container = self.node(container_uid)
        el = self.doc.make_element(entry)
        if el.tag != "widget":
            raise EditError("only widgets can be placed freely")
        container.el.append(el)
        uid = self.doc.node(el).uid
        self.set_property(uid, "geometry", "rect", f"{round(x)}, {round(y)}, {max(1, round(w))}, {max(1, round(h))}")
        return uid

    def parent_type(self, uid):
        n = self.doc.find(uid)
        if n is None:
            return ""
        p, _ = self.doc.container_of(n.el)
        return p.get("class", "") if p is not None else ""


def open_document(text: str, path: str):
    if path.lower().endswith(".ui") or text.lstrip().startswith("<?xml") or text.lstrip().startswith("<ui"):
        return UiAdapter(text)
    return QmlAdapter(text)


TEMPLATES = {
    "kirigami-app": ("main.qml", """import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root

    title: i18n("My Application")
    width: Kirigami.Units.gridUnit * 40
    height: Kirigami.Units.gridUnit * 30

    globalDrawer: Kirigami.GlobalDrawer {
        isMenu: true
        actions: [
            Kirigami.Action {
                icon.name: "application-exit"
                text: i18n("Quit")
                shortcut: StandardKey.Quit
                onTriggered: Qt.quit()
            }
        ]
    }

    pageStack.initialPage: Kirigami.ScrollablePage {
        id: mainPage

        title: i18n("Home")
        actions: [
            Kirigami.Action {
                icon.name: "list-add"
                text: i18n("Add Item")
            }
        ]

        Kirigami.FormLayout {
            QQC2.TextField {
                id: nameField
                Kirigami.FormData.label: i18n("Name:")
                placeholderText: i18n("Your name")
            }
            QQC2.Switch {
                id: notifySwitch
                Kirigami.FormData.label: i18n("Notifications:")
                text: i18n("Show notifications")
            }
        }
    }
}
"""),
    "kirigami-page": ("Page.qml", """import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page

    title: i18n("Settings")
    actions: [
        Kirigami.Action {
            icon.name: "document-save"
            text: i18n("Apply")
        }
    ]

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            type: Kirigami.MessageType.Information
            text: i18n("Changes are applied when you press Apply.")
            visible: true
        }
        Kirigami.FormLayout {
            Layout.fillWidth: true

            QQC2.ComboBox {
                Kirigami.FormData.label: i18n("Theme:")
                model: [i18n("Breeze"), i18n("Breeze Dark")]
            }
            QQC2.CheckBox {
                text: i18n("Show tooltips")
            }
        }
    }
}
"""),
    "qtquick": ("Main.qml", """import QtQuick
import QtQuick.Layouts
import QtQuick.Controls

ApplicationWindow {
    id: window

    width: 640
    height: 480
    visible: true
    title: qsTr("Hello World")

    ColumnLayout {
        anchors.centerIn: parent

        Label {
            text: qsTr("Hello World")
        }
        Button {
            text: qsTr("Click Me")
        }
    }
}
"""),
    "widgets-form": ("form.ui", uidoc.NEW_UI_TEMPLATE),
}
