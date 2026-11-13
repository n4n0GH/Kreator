"""A small, round-trip friendly QML document model.

The parser understands the declarative structure of QML (objects, bindings,
property declarations, inline components, attached / grouped properties) and
keeps everything it does not need to edit (functions, signals, enums, JS
expressions, comments) as verbatim text, so loading and saving a file keeps it
recognisable.
"""

from __future__ import annotations

import copy
import itertools
import re
from dataclasses import dataclass, field

INDENT = "    "
_uid_counter = itertools.count(1)


class QmlSyntaxError(Exception):
    def __init__(self, message: str, line: int = 0):
        super().__init__(f"Line {line}: {message}" if line else message)
        self.line = line


# --------------------------------------------------------------------------- tokens

@dataclass
class Tok:
    kind: str  # ident, number, string, template, punct, comment, newline, regex
    text: str
    start: int
    end: int
    line: int


_PUNCT = sorted(
    """>>>= === !== >>> <<= >>= **= ... ?. ?? &&= ||= ??= == != <= >= && || ++ -- += -= *= /= %= &= |= ^= << >> ** =>
    { } ( ) [ ] ; , < > + - * / % & | ^ ! ~ ? : = . @ #""".split(),
    key=len,
    reverse=True,
)
_TOKEN_RE = re.compile(
    r"""
    (?P<ws>[ \t\r\f\v\ufeff\xa0\u2000-\u200b\u3000]+)
  | (?P<newline>\n)
  | (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
  | (?P<template>`(?:\\.|[^`\\])*`)
  | (?P<number>0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|(?:\d[\d_]*\.?[\d_]*|\.\d[\d_]*)(?:[eE][+-]?\d+)?n?)
  | (?P<ident>[A-Za-z_$\u00c0-\uffff][\w$\u00c0-\uffff]*)
  | (?P<punct>"""
    + "|".join(re.escape(p) for p in _PUNCT)
    + r""")
    """,
    re.VERBOSE | re.DOTALL,
)

# tokens after which a `/` starts a regular expression instead of a division
_REGEX_PREV = set("( , = : [ ! & | ? { } ; + - * % < > ~ ^ return typeof case".split()) | {
    "==", "===", "!=", "!==", "&&", "||", "??", "=>", "<=", ">=", "+=", "-=",
}
_REGEX_RE = re.compile(r"/(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^/\\\n\[])+/[a-z]*")


def tokenize(text: str) -> list[Tok]:
    toks: list[Tok] = []
    pos = 0
    line = 1
    n = len(text)
    while pos < n:
        if text[pos] == "/" and pos + 1 < n and text[pos + 1] not in "/*":
            prev = next((t for t in reversed(toks) if t.kind not in ("comment", "newline")), None)
            if prev is None or prev.text in _REGEX_PREV:
                m = _REGEX_RE.match(text, pos)
                if m:
                    toks.append(Tok("regex", m.group(0), pos, m.end(), line))
                    pos = m.end()
                    continue
        m = _TOKEN_RE.match(text, pos)
        if not m:
            raise QmlSyntaxError(f"unexpected character {text[pos]!r}", line)
        kind = m.lastgroup
        tok_text = m.group(0)
        if kind != "ws":
            toks.append(Tok(kind, tok_text, pos, m.end(), line))
        line += tok_text.count("\n")
        pos = m.end()
    return toks


# --------------------------------------------------------------------------- model

class Verbatim(str):
    """Source text that must be written back without re-indentation
    (it contains a multi-line string literal)."""


def _dedent_block(text: str, column: int) -> list[str]:
    """Split verbatim source into lines, removing the member's original indentation."""
    lines = text.split("\n")
    rest = [ln for ln in lines[1:] if ln.strip()]
    if rest:
        column = min(column, min(len(ln) - len(ln.lstrip(" \t")) for ln in rest))
    out = [lines[0]]
    for ln in lines[1:]:
        strip = 0
        while strip < column and strip < len(ln) and ln[strip] in " \t":
            strip += 1
        out.append(ln[strip:])
    return out


@dataclass
class Member:
    comments: list[list[str]] = field(default_factory=list)  # each comment = lines
    blank_before: bool = False
    trailing_comment: str = ""
    # where the member starts in the parsed text (1-based; 0 for new members)
    line: int = field(default=0, compare=False, kw_only=True)
    column: int = field(default=0, compare=False, kw_only=True)


@dataclass
class Binding(Member):
    name: str = ""
    # str (expression lines joined by \n), ObjectNode, or list[ObjectNode]
    value: object = ""

    @property
    def is_expression(self) -> bool:
        return isinstance(self.value, str)


@dataclass
class PropertyDecl(Member):
    modifiers: list[str] = field(default_factory=list)
    type_name: str = "var"
    name: str = ""
    value: object = None  # None, str, ObjectNode or list[ObjectNode]


@dataclass
class RawMember(Member):
    text: str = ""  # functions, signals, enums, …; stored dedented


@dataclass
class GroupNode(Member):
    name: str = ""
    members: list = field(default_factory=list)


@dataclass
class ObjectNode(Member):
    type_name: str = "Item"
    members: list = field(default_factory=list)
    component_name: str = ""  # inline component:  component Foo: Bar {}
    on_target: str = ""  # value source / interceptor:  Behavior on x {}
    end_comments: list[list[str]] = field(default_factory=list)
    uid: int = field(default_factory=lambda: next(_uid_counter))
    line: int = 0    # 1-based position in the parsed text (0 for new objects)
    column: int = 0  # 1-based

    # -- convenience ---------------------------------------------------------
    @property
    def short_type(self) -> str:
        return self.type_name.rsplit(".", 1)[-1]

    @property
    def id(self) -> str:
        b = self.binding("id")
        return b.value.strip() if b and isinstance(b.value, str) else ""

    def binding(self, name: str) -> Binding | None:
        if "." in name:
            head, rest = name.split(".", 1)
            for m in self.members:
                if isinstance(m, GroupNode) and m.name == head:
                    for gm in m.members:
                        if isinstance(gm, Binding) and gm.name == rest:
                            return gm
        for m in self.members:
            if isinstance(m, Binding) and m.name == name:
                return m
        return None

    def bindings(self):
        """Yield (qualified name, Binding) for all bindings, flattening groups."""
        for m in self.members:
            if isinstance(m, Binding):
                yield m.name, m
            elif isinstance(m, GroupNode):
                for gm in m.members:
                    if isinstance(gm, Binding):
                        yield f"{m.name}.{gm.name}", gm

    def declarations(self):
        return [m for m in self.members if isinstance(m, PropertyDecl)]

    def _insert_index_for_binding(self) -> int:
        idx = 0
        for i, m in enumerate(self.members):
            if isinstance(m, (Binding, PropertyDecl, GroupNode)) and not (
                isinstance(m, Binding) and not m.is_expression
            ):
                idx = i + 1
            elif isinstance(m, (ObjectNode, RawMember)) or (isinstance(m, Binding) and not m.is_expression):
                break
        return idx

    def set_binding(self, name: str, value) -> Binding:
        b = self.binding(name)
        if b is None:
            for d in self.declarations():
                if d.name == name:
                    d.value = value
                    return d  # type: ignore[return-value]
            b = Binding(name=name, value=value)
            if name == "id":
                self.members.insert(0, b)
            else:
                self.members.insert(self._insert_index_for_binding(), b)
        else:
            b.value = value
        return b

    def remove_binding(self, name: str) -> bool:
        if "." in name:
            head, rest = name.split(".", 1)
            for m in list(self.members):
                if isinstance(m, GroupNode) and m.name == head:
                    for gm in list(m.members):
                        if isinstance(gm, Binding) and gm.name == rest:
                            m.members.remove(gm)
                            if not any(isinstance(x, Binding) for x in m.members):
                                self.members.remove(m)
                            return True
        for m in list(self.members):
            if isinstance(m, Binding) and m.name == name:
                self.members.remove(m)
                return True
        for d in self.declarations():
            if d.name == name and d.value is not None:
                d.value = None
                return True
        return False

    def child_slots(self):
        """Yield (container list, index, label) for every child object, in source order.

        `label` is the property name for objects assigned to a property, or ""
        for default-property children.
        """
        for i, m in enumerate(self.members):
            if isinstance(m, ObjectNode):
                yield self.members, i, ""
            elif isinstance(m, (Binding, PropertyDecl)):
                if isinstance(m.value, ObjectNode):
                    yield m, None, m.name
                elif isinstance(m.value, list):
                    for j in range(len(m.value)):
                        yield m.value, j, m.name


@dataclass
class QmlDocument:
    header: str = ""
    root: ObjectNode | None = None
    trailer: str = ""

    # -- imports -------------------------------------------------------------
    def imports(self) -> list[tuple[str, str]]:
        """Return (module, alias) pairs."""
        out = []
        for ln in self.header.splitlines():
            m = re.match(r"\s*import\s+([\w.]+|\"[^\"]*\")\s*(?:[\d.]+)?\s*(?:as\s+(\w+))?", ln)
            if m:
                out.append((m.group(1), m.group(2) or ""))
        return out

    def import_alias(self, module: str) -> str | None:
        """None if not imported, "" if imported unqualified, else the alias."""
        for mod, alias in self.imports():
            if mod == module:
                return alias
        return None

    def ensure_import(self, module: str, preferred_alias: str = "") -> str:
        """Make sure `module` is imported, return the prefix to use ("Alias." or "")."""
        alias = self.import_alias(module)
        if alias is None:
            alias = preferred_alias
            line = f"import {module}" + (f" as {alias}" if alias else "")
            lines = self.header.rstrip("\n").split("\n") if self.header.strip() else []
            last_import = max((i for i, ln in enumerate(lines) if ln.strip().startswith("import ")), default=-1)
            if last_import >= 0:
                lines.insert(last_import + 1, line)
            else:
                lines.append(line)
            self.header = "\n".join(lines) + "\n\n"
        return f"{alias}." if alias else ""

    # -- traversal -----------------------------------------------------------
    def walk(self):
        """Yield (node, depth, parent, label) in preorder."""
        if self.root is None:
            return

        def rec(node, depth, parent, label):
            yield node, depth, parent, label
            for container, idx, lbl in node.child_slots():
                child = container.value if idx is None else container[idx]
                yield from rec(child, depth + 1, node, lbl)

        yield from rec(self.root, 0, None, "")

    def find(self, uid: int) -> ObjectNode | None:
        for node, *_ in self.walk():
            if node.uid == uid:
                return node
        return None

    def locate(self, uid: int):
        """Return (parent, container, index) where container[index] is the node.

        container is a list (members or object list), or a Binding when the
        node is the single value of a property (index None).
        """
        for node, _d, _p, _l in self.walk():
            for container, idx, _lbl in node.child_slots():
                child = container.value if idx is None else container[idx]
                if child.uid == uid:
                    return node, container, idx
        return None

    def all_ids(self) -> set[str]:
        return {n.id for n, *_ in self.walk() if n.id}

    def unique_id(self, base: str) -> str:
        ids = self.all_ids()
        base = re.sub(r"\W", "", base[:1].lower() + base[1:]) or "item"
        if base not in ids:
            return base
        for i in itertools.count(2):
            if f"{base}{i}" not in ids:
                return f"{base}{i}"
        return base

    # -- serialisation -------------------------------------------------------
    def to_text(self) -> str:
        if self.root is None:
            return self.header
        out = []
        serialize_object(self.root, 0, out)
        body = "\n".join(out)
        header = self.header
        if header and not header.endswith("\n"):
            header += "\n"
        trailer = self.trailer.rstrip()
        return header + body + "\n" + (trailer + "\n" if trailer else "")


# --------------------------------------------------------------------------- parser

def _is_type_name(name: str) -> bool:
    last = name.rsplit(".", 1)[-1]
    return bool(last) and last[0].isupper()


_CONTINUE_AFTER = set(
    "+ - * / % = == === != !== < > <= >= && || ?? ? : , . ( [ { ! ~ & | ^ => ** += -= *= /= ?. new typeof in instanceof".split()
)
_CONTINUE_BEFORE = set(
    ". ?. ? : + - * / % == === != !== < > <= >= && || ?? & | ^ ** in instanceof ) ] }".split()
)


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.toks = tokenize(text)
        self.pos = 0
        self.multiline_strings = [
            (t.start, t.end) for t in self.toks if t.kind in ("string", "template") and "\n" in t.text
        ]

    # helpers
    def peek(self, offset=0, skip_nl=True) -> Tok | None:
        i = self.pos
        seen = 0
        while i < len(self.toks):
            t = self.toks[i]
            if t.kind == "comment" or (skip_nl and t.kind == "newline"):
                i += 1
                continue
            if seen == offset:
                return t
            seen += 1
            i += 1
        return None

    def next_sig(self, skip_nl=True) -> Tok:
        while self.pos < len(self.toks):
            t = self.toks[self.pos]
            self.pos += 1
            if t.kind == "comment" or (skip_nl and t.kind == "newline"):
                continue
            return t
        raise QmlSyntaxError("unexpected end of file", self.toks[-1].line if self.toks else 0)

    def expect(self, text: str) -> Tok:
        t = self.next_sig()
        if t.text != text:
            raise QmlSyntaxError(f"expected '{text}' but found '{t.text}'", t.line)
        return t

    def column(self, offset: int) -> int:
        return offset - (self.text.rfind("\n", 0, offset) + 1)

    def raw(self, start: int, end: int, col: int | None = None) -> str:
        if any(s >= start and e <= end for s, e in self.multiline_strings):
            return Verbatim(self.text[start:end])
        if col is None:
            col = self.column(start)
        return "\n".join(_dedent_block(self.text[start:end], col))

    def qualified_name(self) -> tuple[str, Tok]:
        t = self.next_sig()
        if t.kind != "ident":
            raise QmlSyntaxError(f"expected a name but found '{t.text}'", t.line)
        name = t.text
        first = t
        while True:
            a, b = self.peek(0, False), self.peek(1, False)
            if a is not None and a.text == "." and b is not None and b.kind == "ident":
                self.next_sig(False)
                self.next_sig(False)
                name += "." + b.text
            else:
                break
        return name, first

    def take_comments(self) -> list[list[str]]:
        out = []
        while self.pos < len(self.toks) and self.toks[self.pos].kind in ("comment", "newline"):
            t = self.toks[self.pos]
            if t.kind == "comment":
                out.append(_dedent_block(t.text, self.column(t.start)))
            self.pos += 1
        return out

    def lookahead_object(self) -> bool:
        """Is the upcoming token sequence `Type.Name {` or `Type on prop {`?"""
        i = 0
        t = self.peek(i)
        if t is None or t.kind != "ident":
            return False
        name = t.text
        while True:
            a, b = self.peek(i + 1), self.peek(i + 2)
            if a is not None and a.text == "." and b is not None and b.kind == "ident":
                name += "." + b.text
                i += 2
            else:
                break
        nxt = self.peek(i + 1)
        if nxt is None:
            return False
        if nxt.text == "{":
            return _is_type_name(name)
        if nxt.text == "on":
            after = self.peek(i + 2)
            return after is not None and after.kind == "ident" and _is_type_name(name)
        return False

    # document
    def parse_document(self) -> QmlDocument:
        doc = QmlDocument()
        # header: import/pragma lines and comments before the root object
        i = 0
        root_tok = None
        while i < len(self.toks):
            t = self.toks[i]
            if t.kind in ("comment", "newline") or t.text == ";":
                i += 1
                continue
            if t.kind == "ident" and t.text in ("import", "pragma"):
                while i < len(self.toks) and self.toks[i].kind != "newline":
                    i += 1
                continue
            root_tok = t
            break
        if root_tok is None:
            doc.header = self.text
            return doc
        # keep comments directly attached to the root with the header
        doc.header = self.text[: self.text.rfind("\n", 0, root_tok.start) + 1]
        self.pos = i
        doc.root = self.parse_object()
        # trailer
        if self.pos < len(self.toks):
            rest = [t for t in self.toks[self.pos:] if t.kind != "newline"]
            if any(t.kind != "comment" for t in rest):
                bad = next(t for t in rest if t.kind != "comment")
                raise QmlSyntaxError(f"unexpected '{bad.text}' after the root object", bad.line)
            if rest:
                doc.trailer = self.text[rest[0].start:]
        return doc

    def parse_object(self, prefix_component: str = "") -> ObjectNode:
        type_name, first = self.qualified_name()
        node = ObjectNode(type_name=type_name, component_name=prefix_component,
                          line=first.line, column=self.column(first.start) + 1)
        nxt = self.peek()
        if nxt is not None and nxt.text == "on":
            self.next_sig()
            node.on_target, _ = self.qualified_name()
        self.expect("{")
        self.parse_members(node.members, node)
        return node

    def parse_members(self, members: list, owner) -> None:
        pending: list[list[str]] = []
        newlines = 0
        last_member = None
        last_end_line = -1
        while True:
            if self.pos >= len(self.toks):
                raise QmlSyntaxError("missing '}'", self.toks[-1].line if self.toks else 0)
            t = self.toks[self.pos]
            if t.kind == "newline":
                newlines += 1
                self.pos += 1
                continue
            if t.text == ";" or t.text == ",":
                self.pos += 1
                continue
            if t.kind == "comment":
                self.pos += 1
                if last_member is not None and t.line == last_end_line and not pending and newlines == 0:
                    last_member.trailing_comment = t.text
                else:
                    if newlines > 1 and not pending and last_member is not None:
                        pending.append([])  # marker: blank line before comment
                    pending.append(_dedent_block(t.text, self.column(t.start)))
                newlines = 0
                continue
            if t.text == "}":
                self.pos += 1
                comments = [c for c in pending if c]
                if isinstance(owner, ObjectNode):
                    owner.end_comments = comments
                else:
                    members.extend(RawMember(text="\n".join(c)) for c in comments)
                return
            blank = newlines > 1 or (bool(pending) and pending[0] == [])
            comments = [c for c in pending if c]
            member = self.parse_member()
            if not member.line:
                member.line, member.column = t.line, self.column(t.start) + 1
            member.comments = comments
            member.blank_before = blank and last_member is not None
            members.append(member)
            pending = []
            newlines = 0
            last_member = member
            last_end_line = self.toks[self.pos - 1].line + self.toks[self.pos - 1].text.count("\n")

    def parse_member(self) -> Member:
        t = self.peek()
        start = t.start
        word = t.text
        self.member_col = self.column(start)

        if word == "@":  # annotation, e.g. @Deprecated { reason: "…" }
            self.next_sig()
            self.qualified_name()
            nt = self.peek(0, False)
            if nt is not None and nt.text == "{":
                self.next_sig()
                depth = 1
                while depth:
                    tk = self.next_sig()
                    depth += {"{": 1, "}": -1}.get(tk.text, 0)
            return RawMember(text=self.raw(start, self.toks[self.pos - 1].end))

        # property declarations
        mods = []
        i = 0
        while True:
            tk = self.peek(i)
            if tk is not None and tk.kind == "ident" and tk.text in ("readonly", "required", "default", "final", "virtual", "override"):
                nt = self.peek(i + 1)
                if nt is not None and nt.kind == "ident" and nt.text != ":" :
                    mods.append(tk.text)
                    i += 1
                    continue
            break
        tk = self.peek(i)
        if tk is not None and tk.text == "property" and (self.peek(i + 1) or tk).kind == "ident":
            for _ in range(i + 1):
                self.next_sig()
            return self.parse_property_decl(mods)
        if mods and tk is not None and tk.kind == "ident":
            # `required foo` (no type)
            return self.parse_raw_line(start)

        if t.kind == "ident" and word == "signal":
            return self.parse_raw_until_balanced(start, stop_at_newline=True)
        if t.kind == "ident" and word in ("function", "async"):
            return self.parse_raw_function(start)
        if t.kind == "ident" and word == "enum":
            return self.parse_raw_function(start)
        if t.kind == "ident" and word == "component":
            nt = self.peek(1)
            if nt is not None and nt.kind == "ident":
                self.next_sig()
                comp_name = self.next_sig().text
                self.expect(":")
                return self.parse_object(prefix_component=comp_name)

        if self.lookahead_object():
            return self.parse_object()

        name, first = self.qualified_name()
        nt = self.peek(0, False)
        if nt is not None and nt.text == "{":
            # grouped property:  font { bold: true }
            self.next_sig()
            group = GroupNode(name=name)
            self.parse_members(group.members, group)
            return group
        nt = self.next_sig()
        if nt.text != ":":
            raise QmlSyntaxError(f"expected ':' after '{name}' but found '{nt.text}'", nt.line)
        value = self.parse_value()
        return Binding(name=name, value=value)

    def parse_property_decl(self, mods) -> PropertyDecl:
        # type (may be dotted or list<…>)
        type_tok = self.next_sig()
        type_name = type_tok.text
        while True:
            a = self.peek(0, False)
            if a is not None and a.text == "." :
                self.next_sig(False)
                type_name += "." + self.next_sig(False).text
            elif a is not None and a.text == "<":
                depth = 0
                while True:
                    tk = self.next_sig(False)
                    if tk.text == "<":
                        depth += 1
                        type_name += "<"
                    elif tk.text in (">", ">>"):
                        depth -= len(tk.text)
                        type_name += tk.text
                        if depth <= 0:
                            break
                    elif tk.text == ".":
                        type_name += "."
                    else:
                        type_name += tk.text
            else:
                break
        name_tok = self.next_sig(False)
        decl = PropertyDecl(modifiers=mods, type_name=type_name, name=name_tok.text)
        nt = self.peek(0, False)
        if nt is not None and nt.text == ":":
            self.next_sig(False)
            decl.value = self.parse_value()
        return decl

    def parse_raw_line(self, start: int) -> RawMember:
        end = start
        while self.pos < len(self.toks) and self.toks[self.pos].kind != "newline" and self.toks[self.pos].text not in (";", "}"):
            if self.toks[self.pos].kind != "comment":
                end = self.toks[self.pos].end
            self.pos += 1
        return RawMember(text=self.raw(start, end))

    def parse_raw_until_balanced(self, start: int, stop_at_newline=False) -> RawMember:
        depth = 0
        end = start
        while self.pos < len(self.toks):
            t = self.toks[self.pos]
            if t.kind == "newline" and depth == 0 and stop_at_newline:
                break
            if t.text in ("(", "[", "{"):
                depth += 1
            elif t.text in (")", "]", "}"):
                if depth == 0:
                    break
                depth -= 1
            elif t.text == ";" and depth == 0:
                break
            if t.kind not in ("comment", "newline"):
                end = t.end
            self.pos += 1
        return RawMember(text=self.raw(start, end))

    def parse_raw_function(self, start: int) -> RawMember:
        # consume until the first top-level { … } block closes
        depth = 0
        seen_brace = False
        end = start
        while self.pos < len(self.toks):
            t = self.toks[self.pos]
            self.pos += 1
            if t.kind not in ("comment", "newline"):
                end = t.end
            if t.text in ("(", "[", "{"):
                if t.text == "{" and depth == 0:
                    seen_brace = True
                depth += 1
            elif t.text in (")", "]", "}"):
                depth -= 1
                if depth == 0 and t.text == "}" and seen_brace:
                    break
        return RawMember(text=self.raw(start, end))

    def parse_value(self):
        t = self.peek()
        if t is None:
            raise QmlSyntaxError("missing value", self.toks[-1].line)
        if t.text == "[":
            # list of objects?
            save = self.pos
            self.next_sig()
            nt = self.peek()
            if nt is not None and (self.lookahead_object()):
                items = []
                while True:
                    comments = self.take_comments()
                    obj = self.parse_object()
                    obj.comments = comments
                    items.append(obj)
                    nt = self.next_sig()
                    if nt.text == "]":
                        return items
                    if nt.text != ",":
                        raise QmlSyntaxError(f"expected ',' or ']' but found '{nt.text}'", nt.line)
                    if self.peek() is not None and self.peek().text == "]":
                        self.next_sig()
                        return items
            self.pos = save
        elif self.lookahead_object():
            return self.parse_object()
        return self.parse_expression()

    def parse_expression(self) -> str:
        # skip leading comments / newlines
        while self.pos < len(self.toks) and self.toks[self.pos].kind in ("comment", "newline"):
            self.pos += 1
        start_tok = self.toks[self.pos]
        depth = 0
        last = None
        while self.pos < len(self.toks):
            t = self.toks[self.pos]
            if t.kind == "comment":
                if depth == 0 and last is not None and last.text not in _CONTINUE_AFTER:
                    nxt = self.peek(0)
                    if nxt is None or nxt.text not in _CONTINUE_BEFORE or nxt.text == "}":
                        break
                self.pos += 1
                continue
            if depth == 0:
                if t.text in (";", "}", ")", "]", ",") and last is not None:
                    break
                if t.kind == "newline":
                    if last is not None and last.text not in _CONTINUE_AFTER:
                        nxt = self.peek(0)
                        if nxt is None or nxt.text not in _CONTINUE_BEFORE or nxt.text == "}":
                            break
                    self.pos += 1
                    continue
            elif t.kind == "newline":
                self.pos += 1
                continue
            if t.text in ("(", "[", "{"):
                depth += 1
            elif t.text in (")", "]", "}"):
                depth -= 1
            last = t
            self.pos += 1
        if last is None:
            raise QmlSyntaxError("missing value", start_tok.line)
        return self.raw(start_tok.start, last.end, getattr(self, "member_col", None))


def parse(text: str) -> QmlDocument:
    return _Parser(text).parse_document()


def parse_object_snippet(text: str) -> ObjectNode:
    p = _Parser(text)
    while p.pos < len(p.toks) and p.toks[p.pos].kind in ("comment", "newline"):
        p.pos += 1
    node = p.parse_object()
    return node


def parse_value_objects(text: str):
    """The object or list of objects that `text` is as the value of a
    binding (`QQC2.ToolBar {}`, `[Action {}, Action {}]`), or None if it is an
    expression. The objects are new ones: they have no source position."""
    try:
        doc = parse("Item {\n    __x: " + text + "\n}\n")
    except QmlSyntaxError:
        return None
    members = doc.root.members if doc.root is not None else []
    if len(members) != 1 or not isinstance(members[0], Binding) or members[0].name != "__x":
        return None
    value = members[0].value
    if isinstance(value, str):
        return None
    for top in ([value] if isinstance(value, ObjectNode) else value):
        for node in iter_subtree(top):
            node.line = node.column = 0
            for m in node.members:
                m.line = m.column = 0
    return value


# --------------------------------------------------------------------------- writer

def _emit_comments(comments, indent, out):
    for c in comments:
        out.append(indent + c[0])
        out.extend((indent + ln) if ln.strip() else "" for ln in c[1:])


def _emit_lines(first_prefix: str, text: str, indent: str, out: list, suffix: str = ""):
    lines = text.split("\n")
    if isinstance(text, Verbatim):
        out.append(first_prefix + lines[0])
        out.extend(lines[1:])
        return
    out.append(first_prefix + lines[0])
    for ln in lines[1:]:
        out.append((indent + ln) if ln.strip() else "")
    if suffix:
        out[-1] += suffix


def _emit_value(prefix: str, value, level: int, out: list, trailing: str = ""):
    indent = INDENT * level
    if isinstance(value, ObjectNode):
        serialize_object(value, level, out, prefix=prefix)
    elif isinstance(value, list):
        if not value:
            out.append(f"{indent}{prefix}[]")
        else:
            out.append(f"{indent}{prefix}[")
            for i, obj in enumerate(value):
                serialize_object(obj, level + 1, out, emit_comments=True)
                if i < len(value) - 1:
                    out[-1] += ","
            out.append(f"{indent}]")
    else:
        _emit_lines(indent + prefix, value if isinstance(value, str) else str(value), indent, out)
    if trailing:
        out[-1] += " " + trailing


def serialize_member(m: Member, level: int, out: list):
    indent = INDENT * level
    _emit_comments(m.comments, indent, out)
    if isinstance(m, ObjectNode):
        serialize_object(m, level, out, emit_comments=False)
        if m.trailing_comment:
            out[-1] += " " + m.trailing_comment
    elif isinstance(m, Binding):
        _emit_value(f"{m.name}: ", m.value, level, out, m.trailing_comment)
    elif isinstance(m, PropertyDecl):
        head = " ".join(m.modifiers + ["property", m.type_name, m.name])
        if m.value is None:
            out.append(indent + head + (" " + m.trailing_comment if m.trailing_comment else ""))
        else:
            _emit_value(head + ": ", m.value, level, out, m.trailing_comment)
    elif isinstance(m, GroupNode):
        out.append(f"{indent}{m.name} {{")
        for i, gm in enumerate(m.members):
            if gm.blank_before and i:
                out.append("")
            serialize_member(gm, level + 1, out)
        out.append(f"{indent}}}" + (" " + m.trailing_comment if m.trailing_comment else ""))
    elif isinstance(m, RawMember):
        _emit_lines(indent, m.text, indent, out)
        if m.trailing_comment:
            out[-1] += " " + m.trailing_comment


def serialize_object(node: ObjectNode, level: int, out: list, prefix: str = "", emit_comments=False):
    indent = INDENT * level
    if emit_comments:
        _emit_comments(node.comments, indent, out)
    head = node.type_name
    if node.on_target:
        head += f" on {node.on_target}"
    if node.component_name:
        head = f"component {node.component_name}: {head}"
    if not node.members and not node.end_comments:
        out.append(f"{indent}{prefix}{head} {{}}")
        return
    out.append(f"{indent}{prefix}{head} {{")
    for i, m in enumerate(node.members):
        if m.blank_before and i:
            out.append("")
        serialize_member(m, level + 1, out)
    if node.end_comments:
        _emit_comments(node.end_comments, indent + INDENT, out)
    out.append(f"{indent}}}")


def node_to_text(node: ObjectNode) -> str:
    out: list[str] = []
    serialize_object(node, 0, out, emit_comments=True)
    return "\n".join(out) + "\n"


def clone_node(node: ObjectNode) -> ObjectNode:
    """Deep copy with fresh uids."""
    new = copy.deepcopy(node)

    def renew(n: ObjectNode):
        n.uid = next(_uid_counter)
        for container, idx, _ in n.child_slots():
            renew(container.value if idx is None else container[idx])

    renew(new)
    return new


def iter_subtree(node: ObjectNode):
    yield node
    for container, idx, _ in node.child_slots():
        yield from iter_subtree(container.value if idx is None else container[idx])


# --------------------------------------------------------------------------- values

_STRING_RE = re.compile(r'^("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')$', re.DOTALL)
_TR_RE = re.compile(
    r'^(qsTr|qsTrId|qsTranslate|i18n|i18nc|xi18n|xi18nc|i18ndc|i18nd|qsTrNoOp)\(\s*(.*)\)$', re.DOTALL
)
_NUMBER_RE = re.compile(r"^-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def unquote(s: str) -> str:
    body = s[1:-1]
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), body)


def quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def classify(value) -> tuple[str, str]:
    """Return (kind, display value) for a binding value.

    kinds: bool, number, string, translated, color, object, list, expression
    """
    if isinstance(value, ObjectNode):
        return "object", value.type_name
    if isinstance(value, list):
        return "list", f"[{len(value)} objects]"
    v = str(value).strip()
    if v in ("true", "false"):
        return "bool", v
    if _NUMBER_RE.match(v):
        return "number", v
    if _STRING_RE.match(v):
        s = unquote(v)
        if _COLOR_RE.match(s):
            return "color", s
        return "string", s
    m = _TR_RE.match(v)
    if m:
        args = m.group(2)
        # i18nc("context", "text") — the user visible text is the 2nd argument
        parts = _split_args(args)
        idx = 1 if m.group(1) in ("i18nc", "xi18nc", "i18nd") else (2 if m.group(1) == "i18ndc" else 0)
        if m.group(1) == "qsTranslate":
            idx = 1
        if len(parts) > idx and _STRING_RE.match(parts[idx].strip()) and len(parts) == idx + 1:
            return "translated", unquote(parts[idx].strip())
    return "expression", v


def _split_args(args: str) -> list[str]:
    parts, depth, cur, q = [], 0, "", None
    i = 0
    while i < len(args):
        c = args[i]
        if q:
            cur += c
            if c == "\\" and i + 1 < len(args):
                cur += args[i + 1]
                i += 1
            elif c == q:
                q = None
        elif c in "\"'`":
            q = c
            cur += c
        elif c in "([{":
            depth += 1
            cur += c
        elif c in ")]}":
            depth -= 1
            cur += c
        elif c == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    if cur.strip():
        parts.append(cur)
    return parts


def replace_translated_text(expr: str, new_text: str) -> str:
    """Replace the user visible string inside qsTr(…)/i18n(…)/i18nc(…)."""
    m = _TR_RE.match(expr.strip())
    if not m:
        return quote(new_text)
    fn = m.group(1)
    parts = _split_args(m.group(2))
    idx = 1 if fn in ("i18nc", "xi18nc", "i18nd", "qsTranslate") else (2 if fn == "i18ndc" else 0)
    parts[idx] = (" " if idx else "") + quote(new_text)
    return f"{fn}({','.join(parts)})"
