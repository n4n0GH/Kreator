"""Qt Designer (.ui) document model built on ElementTree."""

from __future__ import annotations

import copy
import itertools
import re
import xml.etree.ElementTree as ET

_uid_counter = itertools.count(1_000_000)

CONTAINER_CLASSES = {
    "QWidget", "QFrame", "QGroupBox", "QDialog", "QScrollArea", "QTabWidget", "QStackedWidget",
    "QToolBox", "QDockWidget", "QMainWindow", "QSplitter", "QMdiArea", "QWizardPage",
}
PAGED_CLASSES = {"QTabWidget", "QStackedWidget", "QToolBox", "QWizard"}
LAYOUT_CLASSES = {"QVBoxLayout", "QHBoxLayout", "QGridLayout", "QFormLayout"}
SIMPLE_TYPES = ("string", "bool", "number", "double", "enum", "set", "cstring", "UInt", "longlong", "char")


class UiError(Exception):
    pass


class UiNode:
    """Wraps a <widget>, <layout>, <spacer> or <action> element."""

    __slots__ = ("el", "uid")

    def __init__(self, el: ET.Element):
        self.el = el
        self.uid = next(_uid_counter)

    @property
    def kind(self) -> str:
        return self.el.tag  # widget | layout | spacer | action

    @property
    def type_name(self) -> str:
        if self.el.tag == "spacer":
            return "Spacer"
        if self.el.tag == "action":
            return "QAction"
        return self.el.get("class", "")

    @property
    def short_type(self) -> str:
        return self.type_name

    @property
    def id(self) -> str:
        return self.el.get("name", "")


def _text_of(valel: ET.Element) -> str:
    return valel.text or ""


class UiDocument:
    def __init__(self, tree: ET.ElementTree):
        self.tree = tree
        self.ui = tree.getroot()
        self._nodes: dict[int, UiNode] = {}  # id(element) -> node, keeps uids stable
        if self.ui.tag != "ui":
            raise UiError("not a Qt Designer file (root element is not <ui>)")

    # -- parsing ---------------------------------------------------------------
    @classmethod
    def parse(cls, text: str) -> "UiDocument":
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        try:
            root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text, parser=parser)
        except ET.ParseError as e:
            raise UiError(str(e)) from e
        return cls(ET.ElementTree(root))

    def to_text(self) -> str:
        root = copy.deepcopy(self.ui)
        ET.indent(root, space=" ")
        body = ET.tostring(root, encoding="unicode", short_empty_elements=True)
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"

    # -- node identity ---------------------------------------------------------
    def node(self, el: ET.Element) -> UiNode:
        n = self._nodes.get(id(el))
        if n is None or n.el is not el:
            n = UiNode(el)
            self._nodes[id(el)] = n
        return n

    @property
    def root_el(self) -> ET.Element | None:
        return self.ui.find("widget")

    @property
    def root(self) -> UiNode | None:
        el = self.root_el
        return self.node(el) if el is not None else None

    # -- structure -------------------------------------------------------------
    def children_of(self, el: ET.Element):
        """Yield (child element, label) for the outline."""
        if el.tag == "widget":
            for c in el:
                if c.tag in ("widget", "layout"):
                    label = ""
                    title = c.find("attribute[@name='title']/string")
                    if title is None:
                        title = c.find("attribute[@name='label']/string")
                    if title is not None and title.text:
                        label = title.text
                    yield c, label
                elif c.tag == "action":
                    yield c, ""
        elif el.tag == "layout":
            for item in el.findall("item"):
                for c in item:
                    if c.tag in ("widget", "layout", "spacer"):
                        lbl = ""
                        if item.get("row") is not None:
                            lbl = f"{item.get('row')},{item.get('column', '0')}"
                        yield c, lbl

    def walk(self):
        """Yield (node, depth, parent node, label) in preorder."""
        root = self.root_el
        if root is None:
            return

        def rec(el, depth, parent, label):
            node = self.node(el)
            yield node, depth, parent, label
            for c, lbl in self.children_of(el):
                yield from rec(c, depth + 1, node, lbl)

        yield from rec(root, 0, None, "")

    def find(self, uid: int) -> UiNode | None:
        for n, *_ in self.walk():
            if n.uid == uid:
                return n
        return None

    def parent_map(self) -> dict:
        return {c: p for p in self.ui.iter() for c in p}

    def container_of(self, el: ET.Element):
        """Return (parent element, item element or None)."""
        pm = self.parent_map()
        p = pm.get(el)
        if p is not None and p.tag == "item":
            return pm.get(p), p
        return p, None

    def all_names(self) -> set[str]:
        return {e.get("name") for e in self.ui.iter() if e.get("name") and e.tag in ("widget", "layout", "spacer", "action")}

    def unique_name(self, base: str) -> str:
        names = self.all_names()
        if base not in names:
            return base
        for i in itertools.count(2):
            if f"{base}_{i}" not in names:
                return f"{base}_{i}"
        return base

    # -- signal/slot connections ---------------------------------------------
    # <ui> children in the order Qt Designer writes them; <connections> goes
    # after the ones before it
    _BEFORE_CONNECTIONS = ("author", "comment", "exportmacro", "class", "widget", "layoutdefault",
                           "layoutfunction", "pixmapfunction", "customwidgets", "tabstops", "images",
                           "includes", "resources")

    def connections(self) -> list[dict]:
        out = []
        conns = self.ui.find("connections")
        for c in conns.findall("connection") if conns is not None else []:
            out.append({k: c.findtext(k, "") for k in ("sender", "signal", "receiver", "slot")})
        return out

    def connectables(self) -> list[tuple[str, str]]:
        """(name, class) of the widgets and actions that can be connected."""
        out = []
        for e in self.ui.iter():
            if e.tag in ("widget", "action") and e.get("name"):
                out.append((e.get("name"), "QAction" if e.tag == "action" else e.get("class", "")))
        return out

    def _connection_el(self, index: int) -> ET.Element:
        conns = self.ui.find("connections")
        items = conns.findall("connection") if conns is not None else []
        if not 0 <= index < len(items):
            raise UiError("this connection no longer exists")
        return items[index]

    def _check_connection(self, sender, signal, receiver, slot):
        names = {n for n, _c in self.connectables()}
        for what, name in (("sender", sender), ("receiver", receiver)):
            if name not in names:
                raise UiError(f"there is no widget or action named '{name}' ({what})")
        for what, sig in (("signal", signal), ("slot", slot)):
            if not re.fullmatch(r"\w+\([^()]*\)", sig or ""):
                raise UiError(f"'{sig}' is not a {what} signature such as clicked() or setText(QString)")

    def add_connection(self, sender, signal, receiver, slot) -> int:
        self._check_connection(sender, signal, receiver, slot)
        conns = self.ui.find("connections")
        if conns is None:
            conns = ET.Element("connections")
            idx = 0
            for i, c in enumerate(list(self.ui)):
                if c.tag in self._BEFORE_CONNECTIONS:
                    idx = i + 1
            self.ui.insert(idx, conns)
        c = ET.SubElement(conns, "connection")
        for k, v in (("sender", sender), ("signal", signal), ("receiver", receiver), ("slot", slot)):
            ET.SubElement(c, k).text = v
        return len(conns.findall("connection")) - 1

    def update_connection(self, index, sender, signal, receiver, slot):
        self._check_connection(sender, signal, receiver, slot)
        c = self._connection_el(index)
        moved = c.findtext("sender") != sender or c.findtext("receiver") != receiver
        for k, v in (("sender", sender), ("signal", signal), ("receiver", receiver), ("slot", slot)):
            e = c.find(k)
            if e is None:
                e = ET.SubElement(c, k)
            e.text = v
        hints = c.find("hints")
        if moved and hints is not None:  # Designer's drawing positions belong to the old widgets
            c.remove(hints)

    def remove_connection(self, index):
        conns = self.ui.find("connections")
        conns.remove(self._connection_el(index))
        if not conns.findall("connection"):
            self.ui.remove(conns)

    def remove_declared(self, cls: str, kind: str, signature: str):
        """Remove a signal or slot (kind "signal" / "slot") the form declares
        for a class; an emptied <slots> goes too."""
        holders = []
        if self.root_el is not None and self.root_el.get("class") == cls:
            holders.append(self.ui)
        holders += [cw for cw in self.ui.iterfind("customwidgets/customwidget") if cw.findtext("class") == cls]
        for h in holders:
            slots = h.find("slots")
            if slots is None:
                continue
            for e in slots.findall(kind):
                if (e.text or "").strip() == signature:
                    slots.remove(e)
                    if len(slots) == 0:
                        h.remove(slots)
                    return
        raise UiError(f"{signature} is not declared for {cls}")

    def declared_members(self, cls: str) -> tuple[list[str], list[str], str]:
        """Signals and slots declared in the form for a class (the form's own
        class: <slots> of <ui>; a custom widget: its <customwidget>), and the
        class it extends ("" if none)."""
        sigs, slots, extends = [], [], ""
        holders = []
        root = self.root_el
        if root is not None and root.get("class") == cls:
            holders.append(self.ui.find("slots"))
        for cw in self.ui.iterfind("customwidgets/customwidget"):
            if cw.findtext("class") == cls:
                extends = cw.findtext("extends", "") or ""
                holders.append(cw.find("slots"))
        for h in holders:
            if h is None:
                continue
            sigs += [e.text for e in h.findall("signal") if e.text]
            slots += [e.text for e in h.findall("slot") if e.text]
        return sigs, slots, extends

    # -- properties ------------------------------------------------------------
    @staticmethod
    def prop_elements(el: ET.Element):
        for p in el.findall("property"):
            yield p.get("name"), p, "property"
        for a in el.findall("attribute"):
            yield a.get("name"), a, "attribute"

    def properties(self, node: UiNode):
        """Return list of dicts: name, kind, value, editable, section."""
        out = []
        el = node.el
        for name, p, origin in self.prop_elements(el):
            val = next(iter(p), None)
            kind, display, editable = describe_value(val)
            out.append({
                "name": name if origin == "property" else f"attribute:{name}",
                "kind": kind, "value": display, "editable": editable,
            })
        # layout item placement
        parent, item = self.container_of(el)
        if item is not None:
            for attr in ("row", "column", "rowspan", "colspan", "alignment"):
                if item.get(attr) is not None:
                    out.append({"name": f"layout:{attr}", "kind": "number" if attr != "alignment" else "set",
                                "value": item.get(attr), "editable": True})
        if el.tag == "layout":
            for attr in ("stretch", "rowstretch", "columnstretch"):
                if el.get(attr) is not None:
                    out.append({"name": f"layout:{attr}", "kind": "expression", "value": el.get(attr), "editable": True})
        return out

    def get_property(self, node: UiNode, name: str):
        if name.startswith("attribute:"):
            return node.el.find(f"attribute[@name='{name[10:]}']")
        return node.el.find(f"property[@name='{name}']")

    def set_property(self, node: UiNode, name: str, kind: str, value: str):
        el = node.el
        if name.startswith("layout:"):
            attr = name[7:]
            if attr in ("stretch", "rowstretch", "columnstretch"):
                el.set(attr, value)
            else:
                _parent, item = self.container_of(el)
                if item is not None:
                    item.set(attr, value)
            return
        if name.startswith("attribute:"):
            tag, pname = "attribute", name[10:]
        else:
            tag, pname = "property", name
        p = el.find(f"{tag}[@name='{pname}']")
        if p is None:
            p = ET.Element(tag, {"name": pname})
            if node.kind == "spacer" or (node.kind == "layout" and pname not in ("spacing", "margin")):
                pass
            # Designer keeps properties before child elements
            insert_at = 0
            for i, c in enumerate(el):
                if c.tag in ("property", "attribute"):
                    insert_at = i + 1
            el.insert(insert_at, p)
        for c in list(p):
            p.remove(c)
        p.append(encode_value(kind, value))

    def remove_property(self, node: UiNode, name: str) -> bool:
        if name.startswith("layout:"):
            attr = name[7:]
            target = node.el
            if attr not in ("stretch", "rowstretch", "columnstretch"):
                _parent, target = self.container_of(node.el)
            if target is not None and attr in target.attrib:
                del target.attrib[attr]
                return True
            return False
        p = self.get_property(node, name)
        if p is None:
            return False
        node.el.remove(p)
        return True

    def rename(self, node: UiNode, new_name: str):
        old = node.el.get("name", "")
        node.el.set("name", new_name)
        # update references (buddy, connections, tab stops, addaction)
        for e in self.ui.iter():
            if e.tag in ("cstring", "sender", "receiver", "tabstop") and e.text == old:
                e.text = new_name
            if e.tag == "addaction" and e.get("name") == old:
                e.set("name", new_name)

    # -- insertion -------------------------------------------------------------
    def make_element(self, spec: dict) -> ET.Element:
        cls = spec["type"]
        if cls == "Spacer":
            orient = spec.get("orientation", "Qt::Vertical")
            base = "verticalSpacer" if orient == "Qt::Vertical" else "horizontalSpacer"
            el = ET.Element("spacer", {"name": self.unique_name(base)})
            el.append(_prop("orientation", "enum", orient))
            size = ET.Element("property", {"name": "sizeHint", "stdset": "0"})
            size.append(encode_value("size", "20, 40" if orient == "Qt::Vertical" else "40, 20"))
            el.append(size)
            return el
        tag = "layout" if cls in LAYOUT_CLASSES else "widget"
        base = spec.get("objectName") or (
            cls[1:2].lower() + cls[2:] if cls[:1] in ("Q", "K") and cls[1:2].isupper() else cls[:1].lower() + cls[1:])
        el = ET.Element(tag, {"class": cls, "name": self.unique_name(base)})
        for pname, (kind, val) in spec.get("props", {}).items():
            el.append(_prop(pname, kind, val))
        return el

    def insert(self, target: UiNode | None, spec: dict) -> ET.Element:
        new = self.make_element(spec)
        if target is None:
            target = self.root
        if target is None:
            raise UiError("document has no root widget")
        el = target.el
        is_layout = new.tag == "layout"

        if el.tag == "layout":
            self._add_to_layout(el, new)
            return new
        if el.tag in ("spacer",) or (el.tag == "widget" and not self._is_container(el)):
            # insert as sibling after the target
            parent, item = self.container_of(el)
            if parent is not None and parent.tag == "layout" and item is not None:
                self._add_to_layout(parent, new, after=item)
                return new
            if parent is not None and parent.tag == "widget":
                self._add_to_widget(parent, new)
                return new
            raise UiError("cannot insert here")
        # container widget
        self._add_to_widget(el, new)
        return new

    def _is_container(self, el: ET.Element) -> bool:
        return el.get("class") in CONTAINER_CLASSES or el.find("layout") is not None

    def _add_to_widget(self, w: ET.Element, new: ET.Element):
        cls = w.get("class")
        if cls == "QMainWindow":
            central = w.find("widget[@class='QWidget']")
            if central is None:
                central = ET.SubElement(w, "widget", {"class": "QWidget", "name": self.unique_name("centralwidget")})
            return self._add_to_widget(central, new)
        if cls == "QScrollArea":
            contents = w.find("widget")
            if contents is None:
                contents = ET.SubElement(w, "widget", {"class": "QWidget", "name": self.unique_name("scrollAreaWidgetContents")})
            return self._add_to_widget(contents, new)
        if cls in PAGED_CLASSES and new.tag == "widget" and new.get("class") == "QWidget":
            if cls in ("QTabWidget", "QToolBox"):
                attr = ET.SubElement(new, "attribute", {"name": "title" if cls == "QTabWidget" else "label"})
                ET.SubElement(attr, "string").text = f"Page {len(w.findall('widget')) + 1}"
            w.append(new)
            return
        lay = w.find("layout")
        if new.tag == "layout":
            if lay is None:
                w.append(new)
            else:
                self._add_to_layout(lay, new)
            return
        if cls in PAGED_CLASSES:
            # put into the current/last page
            pages = w.findall("widget")
            if not pages:
                page = self.make_element({"type": "QWidget", "objectName": "page"})
                self._add_to_widget(w, page)
                pages = [page]
            return self._add_to_widget(pages[-1], new)
        if lay is None:
            lay = ET.SubElement(w, "layout", {"class": "QVBoxLayout", "name": self.unique_name("verticalLayout")})
        self._add_to_layout(lay, new)

    def _add_to_layout(self, lay: ET.Element, new: ET.Element, after: ET.Element | None = None):
        item = ET.Element("item")
        item.append(new)
        cls = lay.get("class")
        items = lay.findall("item")
        if cls == "QGridLayout":
            if after is not None:
                row = int(after.get("row", 0)) + 1
                for it in items:
                    if int(it.get("row", 0)) >= row:
                        it.set("row", str(int(it.get("row", 0)) + 1))
            else:
                row = max((int(it.get("row", 0)) + int(it.get("rowspan", 1)) for it in items), default=0)
            item.set("row", str(row))
            item.set("column", "0")
        elif cls == "QFormLayout":
            rows = {}
            for it in items:
                rows.setdefault(int(it.get("row", 0)), set()).add(int(it.get("column", 0)))
            is_label = new.get("class") == "QLabel"
            last = max(rows, default=-1)
            if not is_label and last >= 0 and rows[last] == {0}:
                row, col = last, 1
            else:
                row, col = last + 1, 0 if is_label else 1
            item.set("row", str(row))
            item.set("column", str(col))
        if after is not None and after in list(lay):
            lay.insert(list(lay).index(after) + 1, item)
        else:
            lay.append(item)

    # -- deletion / moving -----------------------------------------------------
    def delete(self, node: UiNode) -> bool:
        el = node.el
        if el is self.root_el:
            return False
        parent, item = self.container_of(el)
        if item is not None:
            parent.remove(item)
        elif parent is not None:
            parent.remove(el)
        else:
            return False
        if el.tag == "action":
            name = el.get("name")
            for p in self.ui.iter():
                for c in list(p):
                    if c.tag == "addaction" and c.get("name") == name:
                        p.remove(c)
        return True

    def move(self, node: UiNode, delta: int) -> bool:
        el = node.el
        parent, item = self.container_of(el)
        if parent is None:
            return False
        movable = item if item is not None else el
        siblings = [c for c in parent if c.tag == movable.tag]
        idx = siblings.index(movable)
        j = idx + delta
        if not 0 <= j < len(siblings):
            return False
        other = siblings[j]
        children = list(parent)
        a, b = children.index(movable), children.index(other)
        parent.remove(movable)
        parent.insert(b, movable)
        if item is not None and parent.get("class") in ("QGridLayout", "QFormLayout"):
            for attr in ("row", "column"):
                va, vb = movable.get(attr), other.get(attr)
                if va is not None and vb is not None:
                    movable.set(attr, vb)
                    other.set(attr, va)
        _ = a
        return True

    def element_text(self, node: UiNode) -> str:
        el = copy.deepcopy(node.el)
        ET.indent(el, space=" ")
        return ET.tostring(el, encoding="unicode")

    def paste(self, target: UiNode | None, xml_text: str) -> ET.Element:
        try:
            new = ET.fromstring(xml_text)
        except ET.ParseError as e:
            raise UiError(f"clipboard does not contain a widget: {e}") from e
        if new.tag not in ("widget", "layout", "spacer"):
            raise UiError("clipboard does not contain a widget")
        self._rename_unique(new)
        if target is None:
            target = self.root
        el = target.el
        if el.tag == "layout":
            self._add_to_layout(el, new)
        elif el.tag == "widget" and self._is_container(el):
            self._add_to_widget(el, new)
        else:
            parent, item = self.container_of(el)
            if parent is not None and parent.tag == "layout":
                self._add_to_layout(parent, new, after=item)
            elif parent is not None:
                self._add_to_widget(parent, new)
        return new

    def _rename_unique(self, el: ET.Element):
        for e in el.iter():
            if e.tag in ("widget", "layout", "spacer") and e.get("name"):
                base = re.sub(r"_\d+$", "", e.get("name"))
                e.set("name", self.unique_name(base))

    def duplicate(self, node: UiNode) -> ET.Element | None:
        if node.el is self.root_el:
            return None
        new = copy.deepcopy(node.el)
        self._rename_unique(new)
        parent, item = self.container_of(node.el)
        if item is not None:
            self._add_to_layout(parent, new, after=item)
        else:
            parent.insert(list(parent).index(node.el) + 1, new)
        return new


# --------------------------------------------------------------------------- values

def _prop(name: str, kind: str, value: str) -> ET.Element:
    p = ET.Element("property", {"name": name})
    p.append(encode_value(kind, value))
    return p


def describe_value(val: ET.Element | None):
    """(kind, display, editable) for a property value element."""
    if val is None:
        return "expression", "", False
    tag = val.tag
    if tag == "string":
        return "string", val.text or "", True
    if tag == "bool":
        return "bool", (val.text or "false").strip(), True
    if tag in ("number", "UInt", "longlong", "double", "char"):
        return "number", (val.text or "0").strip(), True
    if tag in ("enum",):
        return "enum", (val.text or "").strip(), True
    if tag in ("set",):
        return "set", (val.text or "").strip(), True
    if tag == "cstring":
        return "cstring", val.text or "", True
    if tag == "rect":
        vals = [(val.findtext(k) or "0") for k in ("x", "y", "width", "height")]
        return "rect", ", ".join(vals), True
    if tag == "size":
        return "size", ", ".join(val.findtext(k) or "0" for k in ("width", "height")), True
    if tag == "point":
        return "point", ", ".join(val.findtext(k) or "0" for k in ("x", "y")), True
    if tag == "color":
        try:
            r, g, b = (int(val.findtext(k) or 0) for k in ("red", "green", "blue"))
            return "color", f"#{r:02x}{g:02x}{b:02x}", True
        except ValueError:
            return "color", "#000000", True
    if tag == "iconset":
        theme = val.get("theme")
        if theme:
            return "icon", theme, True
        return "readonly", (val.findtext("normaloff") or val.text or "icon").strip(), False
    if tag == "font":
        parts = []
        for k in ("family", "pointsize", "weight", "bold", "italic"):
            v = val.findtext(k)
            if v:
                parts.append(f"{k}={v}")
        return "readonly", ", ".join(parts) or "font", False
    if tag == "sizepolicy":
        return "readonly", f"{val.get('hsizetype')}, {val.get('vsizetype')}", False
    if tag == "stringlist":
        return "readonly", ", ".join(s.text or "" for s in val.findall("string")), False
    return "readonly", tag, False


def encode_value(kind: str, value: str) -> ET.Element:
    value = value if value is not None else ""
    if kind in ("string", "translated"):
        e = ET.Element("string")
        e.text = value
        return e
    if kind == "bool":
        e = ET.Element("bool")
        e.text = "true" if str(value).lower() in ("true", "1") else "false"
        return e
    if kind == "number":
        try:
            float(value)
        except ValueError as exc:
            raise UiError(f"'{value}' is not a number") from exc
        e = ET.Element("double" if re.search(r"[.eE]", value) else "number")
        e.text = value.strip()
        return e
    if kind in ("enum", "set", "cstring"):
        e = ET.Element(kind)
        e.text = value.strip()
        return e
    if kind in ("rect", "size", "point"):
        nums = [n.strip() for n in re.split(r"[,x×\s]+", value.strip()) if n.strip()]
        keys = {"rect": ("x", "y", "width", "height"), "size": ("width", "height"), "point": ("x", "y")}[kind]
        if len(nums) != len(keys) or not all(re.fullmatch(r"-?\d+", n) for n in nums):
            raise UiError(f"expected {len(keys)} integers ({', '.join(keys)})")
        e = ET.Element(kind)
        for k, n in zip(keys, nums):
            ET.SubElement(e, k).text = n
        return e
    if kind == "color":
        m = re.fullmatch(r"#?([0-9a-fA-F]{6})", value.strip())
        if not m:
            raise UiError("expected a colour like #3daee9")
        h = m.group(1)
        e = ET.Element("color")
        for k, i in (("red", 0), ("green", 2), ("blue", 4)):
            ET.SubElement(e, k).text = str(int(h[i:i + 2], 16))
        return e
    if kind == "icon":
        e = ET.Element("iconset", {"theme": value.strip()})
        return e
    raise UiError(f"cannot edit values of type {kind}")


NEW_UI_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry">
   <rect>
    <x>0</x>
    <y>0</y>
    <width>480</width>
    <height>360</height>
   </rect>
  </property>
  <property name="windowTitle">
   <string>Form</string>
  </property>
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="nameLabel">
     <property name="text">
      <string>&amp;Name:</string>
     </property>
     <property name="buddy">
      <cstring>nameEdit</cstring>
     </property>
    </widget>
   </item>
   <item row="0" column="1">
    <widget class="QLineEdit" name="nameEdit">
     <property name="placeholderText">
      <string>Your name</string>
     </property>
    </widget>
   </item>
   <item row="1" column="1">
    <widget class="QCheckBox" name="notifyCheck">
     <property name="text">
      <string>Show notifications</string>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""
