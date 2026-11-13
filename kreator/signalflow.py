"""Signal flow of a document: which objects make which others do something.

For a Qt Designer form this is exact: its <connections> (signal -> slot).

QML has no such list; the flow is in the code, and is found there by the ids
it names (a static reading, so what goes through JavaScript variables, models
or C++ isn't seen):

- signal handlers:  Button { onClicked: drawer.open() }   Button -> drawer
- Connections:      Connections { target: backend; function onSaved() { toast.show() } }
                                                          backend -> toast
- JS connections:   timer.triggered.connect(reload)       timer -> reload's object
- functions called / signals emitted from handlers and functions (an edge to
  the object declaring them: its own handlers and functions go on from there)
- bindings:         enabled: check.checked                 check -> this object
  (anchors, sizes and Layout.* are "layout" bindings, a separate kind)

Every edge keeps where it is written (line and column, 1-based), so the view
can show its code.
"""

from __future__ import annotations

import re

from . import qmldoc, uidoc

SIGNAL, BINDING, LAYOUT = "signal", "binding", "layout"

_HANDLER = re.compile(r"on[A-Z0-9]\w*")
_FUNC = re.compile(r"\s*(?:async\s+)?function\s+(\w+)\s*\(")
_SIGNAL_DECL = re.compile(r"\s*signal\s+(\w+)")
_ASSIGN = {"=", "+=", "-=", "*=", "/=", "%=", "&&=", "||=", "??=", "|=", "&=", "^=", "<<=", ">>=", "**="}
_LAYOUT_PROPS = {
    "x", "y", "z", "width", "height", "implicitWidth", "implicitHeight", "contentWidth", "contentHeight",
    "leftPadding", "rightPadding", "topPadding", "bottomPadding", "padding", "spacing",
    "leftMargin", "rightMargin", "topMargin", "bottomMargin", "margins",
}
_LABEL_PROPS = ("text", "title", "label", "name")


def _signal_name(handler: str) -> str:
    """onClicked -> clicked, Component.onCompleted -> Component.completed."""
    qual, _, name = handler.rpartition(".")
    sig = name[2:3].lower() + name[3:]
    return f"{qual}.{sig}" if qual else sig


def _is_layout(prop: str) -> bool:
    head = prop.split(".", 1)[0]
    return head in ("anchors", "Layout") or prop.rsplit(".", 1)[-1] in _LAYOUT_PROPS


def _code_tokens(code: str) -> list:
    try:
        toks = qmldoc.tokenize(code)
    except Exception:  # noqa: BLE001 - odd code: no references
        return []
    return [t for t in toks if t.kind not in ("comment", "newline")]


def _first_string(expr: str) -> str:
    """The text of a label-like binding: its first string, or for i18nc()
    and qsTranslate() the second (the first is the context)."""
    found = list(re.finditer(r"\"((?:\\.|[^\"\\])*)\"|'((?:\\.|[^'\\])*)'", expr or ""))
    if not found:
        return ""
    m = found[1] if len(found) > 1 and re.match(r"\s*(i18ncp?|qsTranslate|QT_TRANSLATE_NOOP)\s*\(", expr) else found[0]
    s = m.group(1) if m.group(1) is not None else m.group(2)
    return s if len(s) <= 24 else s[:23] + "…"


class _Graph:
    """Nodes (objects) with ports (their signals, functions and properties
    that take part), and edges from an output port to an input port."""

    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: dict[tuple, dict] = {}
        self.order: dict[str, int] = {}
        # (node key, port name) -> {kind, line, column}: where a port is defined
        self.port_info: dict[tuple, dict] = {}
        # (node key, port name) -> {"in", "out"}: members defined in the file
        # (functions, signals, handlers), shown even when nothing connects to them
        self.defined: dict[tuple, set] = {}
        # (node key, port name): used without an edge to draw (an object
        # calling its own function, a handler that connects others)
        self.used: set[tuple] = set()
        # (node key, port name) -> whether its declaration can be removed when
        # nothing connects to it (a declared function, signal or property; not
        # a handler, whose code may do something not drawn)
        self.removable: dict[tuple, bool] = {}

    def define(self, node: str, name: str, kind: str, sides: tuple, line: int = 0, column: int = 0,
               removable: bool = False):
        self.port(node, name, kind, line, column)
        self.defined.setdefault((node, name), set()).update(sides)
        self.removable[(node, name)] = removable and self.removable.get((node, name), True)

    def node(self, key: str, **info) -> str:
        if key not in self.nodes:
            self.nodes[key] = {"key": key, **info}
        return key

    def port(self, node: str, name: str, kind: str, line: int = 0, column: int = 0):
        """A port's kind ("signal", "function", "property") and, the first
        time it is given, where it is written."""
        info = self.port_info.setdefault((node, name), {"kind": kind, "line": 0, "column": 0})
        if line and not info["line"]:
            info.update(line=line, column=column)
        if kind != "property" and info["kind"] == "property":
            info["kind"] = kind

    def edge(self, src: str, src_port: str, dst: str, dst_port: str, kind: str, label: str, line: int, column: int,
             allow_self=False, src_kind="signal", dst_kind="function", **extra):
        """An edge from src's output src_port to dst's input dst_port ("" is
        the object itself), written at line/column (1-based)."""
        if src == dst and not allow_self:
            return
        if src_port:
            self.port(src, src_port, src_kind)
        if dst_port:
            self.port(dst, dst_port, dst_kind)
        e = self.edges.setdefault((src, src_port, dst, dst_port, kind),
                                  {"from": src, "fromPort": src_port, "to": dst, "toPort": dst_port,
                                   "kind": kind, "items": []})
        item = {"label": label, "line": line, "column": column, **extra}
        if item not in e["items"]:
            e["items"].append(item)


# --------------------------------------------------------------------------- QML

class _QmlFlow:
    def __init__(self, doc: qmldoc.QmlDocument, uids: dict[int, int], text: str = ""):
        self.doc = doc
        self.uids = uids        # node uid in doc -> uid the application knows
        self.g = _Graph()
        self.parent: dict[int, qmldoc.ObjectNode | None] = {}
        self.ids: dict[str, qmldoc.ObjectNode] = {}
        self.funcs: dict[str, list[qmldoc.ObjectNode]] = {}
        self.signals: dict[str, list[qmldoc.ObjectNode]] = {}
        self.preorder: dict[int, int] = {}
        # how often each name is written in the file (for declared properties
        # that nothing uses: their name appears only in their declaration)
        self.names: dict[str, int] = {}
        for t in _code_tokens(text or doc.to_text()):
            if t.kind == "ident":
                self.names[t.text] = self.names.get(t.text, 0) + 1
        # a key that stays the same over restarts (uids don't): the id, else
        # the place in the tree (type and index among the parent's children)
        self.stable: dict[int, str] = {}
        seen_children: dict[int, int] = {}
        for i, (n, _d, parent, _l) in enumerate(doc.walk()):
            self.parent[n.uid] = parent
            self.preorder[n.uid] = i
            if parent is None:
                place = n.short_type
            else:
                k = seen_children.get(parent.uid, 0)
                seen_children[parent.uid] = k + 1
                place = f"{self.stable[parent.uid].removeprefix('id:')}/{n.short_type}[{k}]"
            self.stable[n.uid] = f"id:{n.id}" if n.id else place
            if n.id:
                self.ids.setdefault(n.id, n)
            for m in n.members:
                if isinstance(m, qmldoc.RawMember):
                    fm = _FUNC.match(m.text)
                    if fm:
                        self.funcs.setdefault(fm.group(1), []).append(n)
                    sm = _SIGNAL_DECL.match(m.text)
                    if sm:
                        self.signals.setdefault(sm.group(1), []).append(n)

    # nodes
    def obj(self, n: qmldoc.ObjectNode) -> str:
        key = f"o{n.uid}"
        if key not in self.g.nodes:
            label = n.id
            if not label:
                for p in _LABEL_PROPS:
                    b = n.binding(p)
                    s = _first_string(b.value) if b is not None and b.is_expression else ""
                    if s:
                        label = f"“{s}”"
                        break
            self.g.node(key, uid=self.uids.get(n.uid, 0), id=n.id, type=n.short_type, label=label,
                        stable=self.stable.get(n.uid, key),
                        external=False, line=n.line, column=n.column, root=self.parent.get(n.uid) is None)
            self.g.order[key] = self.preorder.get(n.uid, 0)
        return key

    def external(self, expr: str) -> str:
        key = f"x{expr}"
        if key not in self.g.nodes:
            self.g.node(key, uid=0, id="", type="", label=expr, external=True, line=0, column=0, root=False,
                        stable=f"ext:{expr}")
            self.g.order[key] = 100000 + len(self.g.nodes)
        return key

    def nearest(self, owners: list, n: qmldoc.ObjectNode) -> qmldoc.ObjectNode:
        """The declaring object in scope from n: an ancestor if any."""
        chain = []
        p = n
        while p is not None:
            chain.append(p.uid)
            p = self.parent.get(p.uid)
        for uid in chain:
            for o in owners:
                if o.uid == uid:
                    return o
        return owners[0]

    def resolve(self, word: str, n: qmldoc.ObjectNode):
        if word in self.ids:
            return self.ids[word]
        if word == "parent":
            return self.parent.get(n.uid)
        return None

    # code -> [(access, target object, member, extra)]: access is "call",
    # "emit", "set", "read" or "connect" (extra: the function connected)
    def refs(self, code: str, n: qmldoc.ObjectNode, with_parent: bool = True):
        toks = _code_tokens(code)
        out = []
        locals_: set[str] = set()
        for i, t in enumerate(toks):
            if t.kind != "ident":
                continue
            prev = toks[i - 1].text if i else ""
            if prev in ("var", "let", "const", "function"):
                locals_.add(t.text)
                continue
            if prev in (".", "?.") or t.text in locals_:
                continue
            nxt = toks[i + 1].text if i + 1 < len(toks) else ""
            if nxt == ":" and i and toks[i - 1].text in ("{", ","):
                continue  # object literal key
            target = self.resolve(t.text, n) if (with_parent or t.text != "parent") else None
            if target is not None:
                member = toks[i + 2].text if nxt in (".", "?.") and i + 2 < len(toks) and toks[i + 2].kind == "ident" else ""
                after = toks[i + 3].text if member and i + 3 < len(toks) else ""
                if member and after == "." and i + 5 < len(toks) and toks[i + 4].text == "connect" and toks[i + 5].text == "(":
                    fn = toks[i + 6].text if i + 6 < len(toks) else ""
                    out.append(("connect", target, member, fn))
                elif member and after == "(":
                    is_signal = any(o is target for o in self.signals.get(member, []))
                    out.append(("emit" if is_signal else "call", target, member, t.text))
                elif member and after in _ASSIGN:
                    out.append(("set", target, member, t.text))
                elif member:
                    out.append(("read", target, member, t.text))
                else:
                    out.append(("read", target, "", t.text))
            elif nxt == "(" and t.text in self.funcs:
                out.append(("call", self.nearest(self.funcs[t.text], n), t.text, ""))
            elif nxt == "(" and t.text in self.signals:
                out.append(("emit", self.nearest(self.signals[t.text], n), t.text, ""))
        return out

    @staticmethod
    def _target_port(access: str, member: str) -> tuple[str, str]:
        """The input port (name, kind) an access reaches: open() for a call,
        the signal for an emit, the property for a read or an assignment."""
        if not member:
            return "", "property"
        if access == "call":
            return f"{member}()", "function"
        if access == "emit":
            return member, "signal"
        return member, "property"

    @staticmethod
    def _describe(access: str, via: str, member: str) -> str:
        what = f"{via}.{member}" if via and member else (via or member)
        return {"call": f"{what}()", "emit": f"emit {what}()", "set": f"{what} ="}.get(access, what)

    def code_edges(self, src_key: str, trigger: str, trigger_kind: str, code: str, n: qmldoc.ObjectNode,
                   line: int, column: int, fallback: qmldoc.ObjectNode | None = None):
        """Edges for code run on `trigger` (a signal of src, or a function):
        from that output port to what the code calls, emits, sets or reads."""
        self.g.port(src_key, trigger, trigger_kind, line, column)
        found = False
        for access, target, member, extra in self.refs(code, n):
            if access == "connect":
                self.g.used.add((src_key, trigger))
                # target.member.connect(fn): target's signal runs fn
                owners = self.funcs.get(extra)
                dst = self.obj(self.nearest(owners, n)) if owners else self.obj(n)
                self.g.edge(self.obj(target), member, dst, f"{extra}()" if owners else "", SIGNAL,
                            f"{member} → {extra}()", line, column)
                continue
            dst = self.obj(target)
            port, kind = self._target_port(access, member)
            if dst == src_key:  # its own: not drawn, but both ends are in use
                self.g.used.update({(src_key, trigger), (dst, port)})
                continue
            self.g.edge(src_key, trigger, dst, port, SIGNAL, f"{trigger} → {self._describe(access, extra, member)}",
                        line, column, src_kind=trigger_kind, dst_kind=kind, access=access)
            found = True
        if not found and fallback is not None:
            self.g.edge(src_key, trigger, self.obj(fallback), "", SIGNAL, trigger, line, column, src_kind=trigger_kind)

    def binding_edges(self, prop: str, code: str, n: qmldoc.ObjectNode, line: int, column: int):
        kind = LAYOUT if _is_layout(prop) else BINDING
        me = self.obj(n)
        for access, target, member, via in self.refs(code, n, with_parent=False):
            # a function called in a binding: its value flows from its output
            port, port_kind = self._target_port(access, member) if access in ("call", "emit") else (member, "property")
            if target is n:
                self.g.used.add((me, port))
                continue
            self.g.port(me, prop, "property", line, column)
            self.g.edge(self.obj(target), port, me, prop, kind,
                        f"{self._describe(access if access == 'call' else 'read', via, member)} → {prop}",
                        line, column, src_kind=port_kind, dst_kind="property")

    def unused_property(self, name: str) -> bool:
        """Its name is written only where it is declared: nothing reads or
        sets it, and there is no on…Changed handler (a name used anywhere
        else, even on another object, counts as used)."""
        handler = f"on{name[:1].upper()}{name[1:]}Changed"
        return self.names.get(name, 0) <= 1 and not self.names.get(handler)

    def connections_source(self, n: qmldoc.ObjectNode) -> str:
        b = n.binding("target")
        expr = b.value.strip() if b is not None and b.is_expression else ""
        if not expr:
            p = self.parent.get(n.uid)
            return self.obj(p) if p is not None else self.obj(n)
        target = self.resolve(expr, n)
        return self.obj(target) if target is not None else self.external(expr)

    def run(self) -> _Graph:
        for n, *_ in self.doc.walk():
            is_conn = n.short_type == "Connections"
            src = None
            if is_conn:
                src = self.connections_source(n)
                fallback = self.parent.get(n.uid) or n
            members = []
            for m in n.members:
                if isinstance(m, qmldoc.GroupNode):
                    members += [(f"{m.name}.{gm.name}", gm) for gm in m.members]
                else:
                    members.append((getattr(m, "name", ""), m))
            for name, m in members:
                if isinstance(m, qmldoc.Binding) and m.is_expression and name != "id":
                    last = name.rsplit(".", 1)[-1]
                    if _HANDLER.fullmatch(last):
                        sig = _signal_name(name)
                        if not is_conn:
                            self.g.define(self.obj(n), sig, "signal", ("out",), m.line, m.column)
                        if is_conn:
                            self.code_edges(src, sig, "signal", m.value, n, m.line, m.column, fallback)
                        else:
                            self.code_edges(self.obj(n), sig, "signal", m.value, n, m.line, m.column)
                    elif not (is_conn and name in ("target", "enabled", "ignoreUnknownSignals")):
                        self.binding_edges(name, m.value, n, m.line, m.column)
                elif isinstance(m, qmldoc.PropertyDecl):
                    if isinstance(m.value, str) and m.value.strip():
                        self.binding_edges(m.name, m.value, n, m.line, m.column)
                    if not is_conn and self.unused_property(m.name):
                        # (set and read: both sides, neither connected)
                        self.g.define(self.obj(n), m.name, "property", ("in", "out"), m.line, m.column,
                                      removable=True)
                elif isinstance(m, qmldoc.RawMember):
                    sm = _SIGNAL_DECL.match(m.text)
                    if sm and not is_conn:  # emitted (in) and handled (out)
                        self.g.define(self.obj(n), sm.group(1), "signal", ("in", "out"), m.line, m.column,
                                      removable=True)
                    fm = _FUNC.match(m.text)
                    if not fm:
                        continue
                    if not is_conn:
                        self.g.define(self.obj(n), f"{fm.group(1)}()", "function", ("in", "out"), m.line, m.column,
                                      removable=not _HANDLER.fullmatch(fm.group(1)))
                    fname = fm.group(1)
                    body = m.text[m.text.find("{", fm.end()):] if "{" in m.text[fm.end():] else ""
                    if is_conn and _HANDLER.fullmatch(fname):
                        self.code_edges(src, _signal_name(fname), "signal", body, n, m.line, m.column, fallback)
                    else:
                        self.code_edges(self.obj(n), f"{fname}()", "function", body, n, m.line, m.column)
        return self.g


def qml_flow(doc: qmldoc.QmlDocument, text: str) -> _Graph:
    """The flow of `doc` (the application's model; its uids are kept), with
    positions in `text` (what the source view shows)."""
    try:
        fresh = qmldoc.parse(text)
        a = [n for n, *_ in doc.walk()]
        b = [n for n, *_ in fresh.walk()]
        if len(a) == len(b) and all(x.type_name == y.type_name for x, y in zip(a, b)):
            return _QmlFlow(fresh, {y.uid: x.uid for x, y in zip(a, b)}, text).run()
    except qmldoc.QmlSyntaxError:
        pass
    return _QmlFlow(doc, {n.uid: n.uid for n, *_ in doc.walk()}).run()


# --------------------------------------------------------------------------- .ui

def ui_flow(doc: uidoc.UiDocument, text: str) -> _Graph:
    g = _Graph()
    by_name = {}
    for i, (n, *_r) in enumerate(doc.walk()):
        if n.id:
            by_name[n.id] = (n, i)
    for a in doc.ui.iter("action"):
        n = doc.node(a)
        if n.id and n.id not in by_name:
            by_name[n.id] = (n, 50000 + len(by_name))
    lines = [i + 1 for i, ln in enumerate(text.split("\n")) if "<connection>" in ln]

    def node(name):
        key = f"u{name}"
        if key not in g.nodes:
            n, order = by_name.get(name, (None, 100000 + len(g.nodes)))
            g.node(key, uid=n.uid if n else 0, id=name, type=n.type_name if n else "", label=name, stable=f"id:{name}",
                   external=n is None, line=0, column=0, root=n is not None and n.el is doc.root_el)
            g.order[key] = order
        return key

    # every widget and action: a form's connections can be edited, between any of them
    for name, _cls in doc.connectables():
        node(name)
    # signals and slots the form declares (its own class, custom widgets'):
    # shown on their widgets even when nothing is connected to them
    # (a declaration belongs to a class: removable only if no widget of the
    # class is connected through it)
    classes = dict(doc.connectables())
    in_use = set()
    for c in doc.connections():
        in_use.add((classes.get(c["sender"]), c["signal"]))
        in_use.add((classes.get(c["receiver"]), c["slot"]))
    for name, cls in doc.connectables():
        sigs, slots, _ext = doc.declared_members(cls)
        for sig in sigs:
            g.define(node(name), sig, "signal", ("out",), removable=(cls, sig) not in in_use)
        for slot in slots:
            g.define(node(name), slot, "function", ("in",), removable=(cls, slot) not in in_use)
    for i, c in enumerate(doc.connections()):
        sender, receiver, sig, slot = c["sender"], c["receiver"], c["signal"], c["slot"]
        if not sender or not receiver:
            continue
        line = lines[i] if i < len(lines) else 0
        g.edge(node(sender), sig, node(receiver), slot, SIGNAL, f"{sender}.{sig} → {receiver}.{slot}", line, 1,
               allow_self=True, src_kind="signal", dst_kind="function",
               index=i, sender=sender, signal=sig, receiver=receiver, slot=slot)
    return g


# --------------------------------------------------------------------------- layout

def layout(g: _Graph, kinds: set[str], focus_uid: int = 0, show_all: bool = False) -> dict:
    """The nodes and edges to show, placed left to right in layers: each node
    gets a column (layer) and a row in it (order).

    An edge spanning several columns passes through waypoints in the columns
    between (nodes with "dummy": true), so it doesn't cross other nodes; its
    "path" lists the node keys it goes through, left to right ("reversed": it
    points right to left, closing a cycle)."""
    edges = [dict(e) for e in g.edges.values() if e["kind"] in kinds]
    if focus_uid:
        keys = {k for k, n in g.nodes.items() if n["uid"] == focus_uid}
        edges = [e for e in edges if e["from"] in keys or e["to"] in keys]
    used = {e["from"] for e in edges} | {e["to"] for e in edges}
    names = sorted(used, key=lambda k: g.order.get(k, 0))
    # the others (show_all): a column of their own, after the rest
    unused = sorted(set(g.nodes) - used, key=lambda k: g.order.get(k, 0)) if show_all and not focus_uid else []
    succ = {k: [] for k in names}
    for e in edges:
        if e["from"] != e["to"] and e["to"] not in succ[e["from"]]:
            succ[e["from"]].append(e["to"])

    # break cycles: the edges going back in a depth-first search point the other way
    state, back = {}, set()

    def dfs(k):
        state[k] = 1
        for s in succ[k]:
            if state.get(s) == 1:
                back.add((k, s))
            elif s not in state:
                dfs(s)
        state[k] = 2

    for k in names:
        if k not in state:
            dfs(k)
    fwd = {k: [] for k in names}
    for k in names:
        for s in succ[k]:
            a, b = (s, k) if (k, s) in back else (k, s)
            if b not in fwd[a]:
                fwd[a].append(b)

    # layer: longest path from a source
    layer = {k: 0 for k in names}
    indeg = {k: 0 for k in names}
    for k in names:
        for s in fwd[k]:
            indeg[s] += 1
    queue = [k for k in names if indeg[k] == 0]
    while queue:
        k = queue.pop(0)
        for s in fwd[k]:
            layer[s] = max(layer[s], layer[k] + 1)
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)

    # waypoints for edges spanning columns
    links: dict[str, list[str]] = {k: [] for k in names}   # left -> right neighbours
    for e in edges:
        a, b = e["from"], e["to"]
        e["reversed"] = layer[b] <= layer[a] and a != b
        if a == b:
            e["path"] = [a]
            continue
        left, right = (b, a) if e["reversed"] else (a, b)
        path = [left]
        for lay in range(layer[left] + 1, layer[right]):
            d = f"d{len(layer)}"
            layer[d] = lay
            links[d] = []
            path.append(d)
        path.append(right)
        for x, y in zip(path, path[1:]):
            links[x].append(y)
        e["path"] = path

    # order in each column: document order, then a few barycenter sweeps
    layers: dict[int, list[str]] = {}
    for k in layer:
        layers.setdefault(layer[k], []).append(k)
    pred = {k: [] for k in layer}
    for k, outs in links.items():
        for s in outs:
            pred[s].append(k)
    pos = {k: i for col in layers.values() for i, k in enumerate(col)}
    for sweep in range(8):
        down = sweep % 2 == 0
        for c in sorted(layers, reverse=not down):
            nb = pred if down else links

            def bary(k, nb=nb):
                ns = nb[k]
                return sum(pos[x] for x in ns) / len(ns) if ns else pos[k]
            layers[c].sort(key=bary)
            for i, k in enumerate(layers[c]):
                pos[k] = i

    # each node's ports: those the shown edges use, in the order they're written
    ports: dict[str, dict[str, dict]] = {k: {} for k in names}
    for e in edges:
        for node, port, side in ((e["from"], e["fromPort"], "out"), (e["to"], e["toPort"], "in")):
            if not port:
                continue
            p = ports[node].get(port)
            if p is None:
                info = g.port_info.get((node, port), {"kind": "property", "line": 0, "column": 0})
                p = ports[node][port] = {"name": port, "kind": info["kind"], "line": info["line"],
                                         "column": info["column"], "in": False, "out": False}
            p[side] = True

    # members defined here that nothing connects to (only on objects shown)
    for (node, port), sides in g.defined.items():
        if node in ports and port not in ports[node] and (node, port) not in g.used:
            info = g.port_info.get((node, port), {"kind": "function", "line": 0, "column": 0})
            ports[node][port] = {"name": port, "kind": info["kind"], "line": info["line"], "column": info["column"],
                                 "in": "in" in sides, "out": "out" in sides, "unconnected": True,
                                 "removable": g.removable.get((node, port), False)}

    # start in the order they're written, then untangle
    port_order = {k: [p["name"] for p in sorted(ports[k].values(), key=lambda p: (p["line"] or 10 ** 9, p["name"]))]
                  for k in names}
    _untangle(edges, layers, pos, port_order)

    def port_list(k):
        return [ports[k][name] for name in port_order[k]]

    nodes = [{**g.nodes[k], "dummy": False, "layer": layer[k], "order": pos[k], "ports": port_list(k)} for k in names]
    last = max(layer.values(), default=-1) + 1
    def loose_ports(k):
        out = []
        for (node, port), sides in g.defined.items():
            if node == k and (node, port) not in g.used:
                info = g.port_info.get((node, port), {"kind": "function", "line": 0, "column": 0})
                out.append({"name": port, "kind": info["kind"], "line": info["line"], "column": info["column"],
                            "in": "in" in sides, "out": "out" in sides, "unconnected": True,
                            "removable": g.removable.get((node, port), False)})
        return out

    nodes += [{**g.nodes[k], "dummy": False, "layer": last, "order": i, "unconnected": True, "ports": loose_ports(k)}
              for i, k in enumerate(unused)]
    nodes += [{"key": k, "dummy": True, "uid": 0, "layer": layer[k], "order": pos[k]}
              for k in layer if k not in g.nodes]
    return {"nodes": nodes, "edges": edges,
            "counts": {kind: sum(1 for e in g.edges.values() if e["kind"] == kind) for kind in (SIGNAL, BINDING, LAYOUT)}}


# --------------------------------------------------------------------------- untangling

# a node's proportions as the view draws them (in grid units): title bar and
# type line, then a row per port; dummies (waypoints) are small
_HEAD, _ROW, _GAP, _DUMMY = 2.5, 1.25, 1.2, 1.0


def _untangle(edges: list, layers: dict, pos: dict, port_order: dict, rounds: int = 20):
    """Reorder the nodes in each column and the ports in each node so fewer
    arrows cross: each goes where the arrows it has lead (the mean height of
    the other ends), and a round is kept only if it crosses fewer arrows.
    Changes layers[], pos{} and port_order{} in place."""
    # the arrows as straight segments between neighbouring columns, by ends:
    # (node, port) on the left, (node, port) on the right
    segments = []
    for e in edges:
        path = e["path"]
        if len(path) < 2 or e["reversed"]:
            continue  # drawn as loops, not between columns
        ends = [(path[0], e["fromPort"])] + [(k, None) for k in path[1:-1]] + [(path[-1], e["toPort"])]
        segments += list(zip(ends, ends[1:]))
    if not segments or len(segments) > 1500:
        return
    # big graphs get fewer rounds (each costs columns × arrows)
    rounds = max(1, min(rounds, 12000 // len(segments)))

    def heights():
        top = {}
        size = {k: _DUMMY if k not in port_order else _HEAD + len(port_order[k]) * _ROW for col in layers.values() for k in col}
        cols = {c: sum(size[k] for k in col) + _GAP * max(0, len(col) - 1) for c, col in layers.items()}
        full = max(cols.values(), default=0)
        for c, col in layers.items():
            y = (full - cols[c]) / 2
            for k in col:
                top[k] = y
                y += size[k] + _GAP
        return top

    def y_of(top, end):
        k, port = end
        if k not in port_order:
            return top[k] + _DUMMY / 2
        if not port:
            return top[k] + _HEAD / 3   # the title bar
        return top[k] + _HEAD + port_order[k].index(port) * _ROW + _ROW / 2

    def crossings():
        top = heights()
        by_gap: dict[int, list] = {}
        for left, right in segments:
            by_gap.setdefault(id(layers_of[left[0]]), []).append((y_of(top, left), y_of(top, right)))
        n = 0
        for segs in by_gap.values():
            segs.sort()
            rights = [r for _l, r in segs]
            for i in range(len(rights)):  # pairs that swap order
                ri, li = rights[i], segs[i][0]
                n += sum(1 for j in range(i + 1, len(rights)) if rights[j] < ri and segs[j][0] > li)
        return n

    layers_of = {k: col for col in layers.values() for k in col}
    best = crossings()
    snapshot = lambda: ({c: list(col) for c, col in layers.items()}, {k: list(v) for k, v in port_order.items()})  # noqa: E731
    saved = snapshot()
    column = {k: c for c, col in layers.items() for k in col}
    touching: dict[int, list] = {}
    for seg in segments:
        for end in seg:
            touching.setdefault(column[end[0]], []).append(seg)

    def pulls_now(c):
        """The heights of the other ends of the arrows of column c's ports
        (and waypoints)."""
        top = heights()
        pulls: dict[tuple, list] = {}
        for left, right in touching.get(c, []):
            pulls.setdefault(left, []).append(y_of(top, right))
            pulls.setdefault(right, []).append(y_of(top, left))
        return top, pulls

    # one column at a time (both sides at once would only swap past each
    # other), left to right, then back
    for r in range(rounds):
        for c in (sorted(layers) if r % 2 == 0 else sorted(layers, reverse=True)):
            col = layers[c]
            top, pulls = pulls_now(c)
            # ports: towards where their arrows go
            for k in col:
                order = port_order.get(k)
                if not order:
                    continue
                # (where each is now: taken before sorting, which empties the list meanwhile)
                now = {name: (y_of(top, (k, name)), i) for i, name in enumerate(order)}

                def want(name, k=k, now=now, pulls=pulls):
                    ys = pulls.get((k, name))
                    return (sum(ys) / len(ys) if ys else now[name][0], now[name][1])
                order.sort(key=want)
            # nodes: towards the mean of all their arrows' other ends
            top, pulls = pulls_now(c)
            by_node: dict[str, list] = {}
            for (k, _p), vals in pulls.items():
                by_node.setdefault(k, []).extend(vals)
            here = {k: i for i, k in enumerate(col)}
            col.sort(key=lambda k: (sum(by_node[k]) / len(by_node[k]) if by_node.get(k) else top[k], here[k]))
        n = crossings()
        if n < best:
            best, saved = n, snapshot()
    cols, ports = saved
    for c in layers:
        layers[c][:] = cols[c]
        for i, k in enumerate(layers[c]):
            pos[k] = i
    for k in port_order:
        port_order[k][:] = ports[k]


# --------------------------------------------------------------------------- .ui signals and slots

_SKIP_METHODS = {"deleteLater()", "destroyed()", "destroyed(QObject*)", "objectNameChanged(QString)"}


def _qt_class(name: str):
    from PySide6 import QtCore, QtGui, QtWidgets
    for mod in (QtWidgets, QtGui, QtCore):
        cls = getattr(mod, name, None)
        if cls is not None and hasattr(cls, "staticMetaObject"):
            return cls
    return None


_MEMBERS_CACHE: dict[str, tuple[list[str], list[str]]] = {}


def _meta_object(qt):
    try:
        mo = qt.staticMetaObject
        mo.methodCount()
        return mo, None
    except RuntimeError:
        # PySide's wrapper of a static meta object can go stale: ask an instance
        try:
            obj = qt()
        except Exception:  # noqa: BLE001 - not constructible here
            return None, None
        return obj.metaObject(), obj


def _qt_members(name: str) -> tuple[list[str], list[str]]:
    """(signals, slots) of a Qt class, public ones, from its meta object."""
    if name in _MEMBERS_CACHE:
        return _MEMBERS_CACHE[name]
    from PySide6.QtCore import QMetaMethod
    sigs, slots = [], []
    mo, keep = _meta_object(_qt_class(name))
    if mo is not None:
        for i in range(mo.methodCount()):
            m = mo.method(i)
            if m.access() != QMetaMethod.Access.Public:
                continue
            sig = bytes(m.methodSignature()).decode()
            if sig in _SKIP_METHODS or sig.startswith("_"):
                continue
            if m.methodType() == QMetaMethod.MethodType.Signal:
                sigs.append(sig)
            elif m.methodType() == QMetaMethod.MethodType.Slot:
                slots.append(sig)
    if keep is not None:
        keep.deleteLater()
    _MEMBERS_CACHE[name] = (sigs, slots)
    return sigs, slots


def class_members(doc: uidoc.UiDocument, cls: str) -> dict:
    """{"signals": [...], "slots": [...]} of a class used in a form: Qt's own
    (from its meta object), and those the form declares for it. A custom or
    KDE widget uses the class it extends (KLineEdit: QLineEdit)."""
    sigs, slots = [], []
    seen = set()
    name = cls
    while name and name not in seen:
        seen.add(name)
        own_sigs, own_slots, extends = doc.declared_members(name)
        sigs += own_sigs
        slots += own_slots
        qt = _qt_class(name)
        if qt is None and name[:1] == "K":
            qt = _qt_class("Q" + name[1:])
        if qt is not None:
            qs, ql = _qt_members(name if _qt_class(name) is not None else "Q" + name[1:])
            sigs += qs
            slots += ql
            break
        name = extends or ("QWidget" if name == cls else "")
    return {"signals": list(dict.fromkeys(sigs)), "slots": list(dict.fromkeys(slots))}


def _args(signature: str) -> list[str]:
    inner = signature[signature.find("(") + 1:signature.rfind(")")].strip()
    return [a.strip() for a in inner.split(",")] if inner else []


def compatible(signal: str, slot: str) -> bool:
    """A slot can take a signal when its arguments are the first of the signal's."""
    s, t = _args(signal), _args(slot)
    return len(t) <= len(s) and s[:len(t)] == t
