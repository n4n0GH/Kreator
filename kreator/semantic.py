"""Syntax + semantic highlighting for QML in the source view.

KSyntaxHighlighting (used through its QML module otherwise) gives every token
an explicit colour, so semantic colours from the language server cannot be
layered under or over it from outside.  For QML with semantic highlighting on,
this highlighter does both layers itself, like Kate's renderer:

1. lexical colours from the Kate theme's text styles (keywords, strings,
   comments, numbers, types, property names, imports, …);
2. qmlls' semantic tokens on top (ids, properties, methods, enum values, …).

A line only gets semantic colours while its text equals the text the tokens
were computed for, so typing never shows colours of a different line; the
next token update (a few hundred milliseconds later) catches up.
"""

from __future__ import annotations

import re

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

KEYWORDS = {
    "import", "as", "pragma", "property", "readonly", "required", "default", "signal", "alias", "component",
    "enum", "on", "function", "return", "if", "else", "for", "while", "do", "switch", "case", "break",
    "continue", "var", "let", "const", "new", "delete", "typeof", "instanceof", "in", "of", "try", "catch",
    "finally", "throw", "this", "async", "await", "yield", "class", "extends", "super", "static", "get", "set",
    "void", "with", "debugger", "final", "virtual", "override",
}
CONSTANTS = {"true", "false", "null", "undefined", "NaN", "Infinity"}
PROPERTY_TYPES = {"int", "real", "double", "bool", "string", "url", "var", "variant", "color", "date", "list",
                  "point", "rect", "size", "font", "vector2d", "vector3d", "vector4d", "quaternion", "matrix4x4"}

_TOKEN = re.compile(r"""
    (?P<comment>//.*)
  | (?P<bcomment>/\*)
  | (?P<string>"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?)
  | (?P<template>`)
  | (?P<number>0[xX][0-9a-fA-F_]+|(?:\d[\d_]*\.?[\d_]*|\.\d+)(?:[eE][+-]?\d+)?)
  | (?P<ident>[A-Za-z_$][\w$]*)
  | (?P<op>[-+*/%=<>!&|^~?:]+)
""", re.VERBOSE)

IN_COMMENT, IN_TEMPLATE = 1, 2


class QmlHighlighter(QSyntaxHighlighter):
    def __init__(self, document=None):
        super().__init__(document)
        self._formats: dict[str, QTextCharFormat] = {}
        self._styles: dict = {}
        self._tokens: dict[int, list] = {}       # line -> [(start, length, style, italic, strike)]
        self._token_lines: list[str] = []        # line texts the tokens belong to

    # ----------------------------------------------------------- configuration
    def set_styles(self, styles: dict):
        self._styles = styles
        self._formats = {}
        self.rehighlight()

    def fmt(self, style: str, italic=False, strike=False) -> QTextCharFormat | None:
        key = f"{style}{'/i' if italic else ''}{'/s' if strike else ''}"
        f = self._formats.get(key)
        if f is None:
            st = self._styles.get(style)
            if not st:
                return None
            f = QTextCharFormat()
            if st.get("text-color"):
                f.setForeground(QColor(st["text-color"]))
            if st.get("bold"):
                f.setFontWeight(QFont.Weight.Bold)
            if st.get("italic") or italic:
                f.setFontItalic(True)
            if st.get("underline"):
                f.setFontUnderline(True)
            if st.get("strike-through") or strike:
                f.setFontStrikeOut(True)
            self._formats[key] = f
        return f

    def set_tokens(self, lines: list[str], tokens: dict[int, list]):
        """New semantic tokens for the given text; re-highlight changed lines only."""
        old_tokens, old_lines = self._tokens, self._token_lines
        self._tokens, self._token_lines = tokens, lines
        doc = self.document()
        if doc is None:
            return
        block = doc.begin()
        n = 0
        while block.isValid():
            before = old_tokens.get(n) if n < len(old_lines) and old_lines[n] == block.text() else None
            after = tokens.get(n) if n < len(lines) and lines[n] == block.text() else None
            if before != after:
                self.rehighlightBlock(block)
            block = block.next()
            n += 1

    def clear_tokens(self):
        if self._tokens:
            self._tokens, self._token_lines = {}, []
            self.rehighlight()

    # ----------------------------------------------------------- highlighting
    def highlightBlock(self, text: str):  # noqa: N802
        if not self._styles:
            return
        state = self.previousBlockState()
        i = 0
        self.setCurrentBlockState(0)
        if state == IN_COMMENT:
            end = text.find("*/")
            if end < 0:
                self._set(0, len(text), "Comment")
                self.setCurrentBlockState(IN_COMMENT)
                return
            self._set(0, end + 2, "Comment")
            i = end + 2
        elif state == IN_TEMPLATE:
            end = _template_end(text, 0)
            if end < 0:
                self._set(0, len(text), "String")
                self.setCurrentBlockState(IN_TEMPLATE)
                return
            self._set(0, end + 1, "String")
            i = end + 1
        self._lexical(text, i)
        self._semantic(text)

    def _set(self, start, length, style, italic=False, strike=False):
        f = self.fmt(style, italic, strike)
        if f is not None and length > 0:
            self.setFormat(start, length, f)

    def _lexical(self, text: str, i: int):
        stripped = text.lstrip()
        member_start = len(text) - len(stripped)
        is_import = stripped.startswith(("import ", "pragma "))
        prev_word = ""
        while i < len(text):
            m = _TOKEN.search(text, i)
            if not m:
                break
            kind, start, end = m.lastgroup, m.start(), m.end()
            word = m.group(0)
            if kind == "comment":
                self._set(start, len(text) - start, "Comment")
                return
            if kind == "bcomment":
                close = text.find("*/", start + 2)
                if close < 0:
                    self._set(start, len(text) - start, "Comment")
                    self.setCurrentBlockState(IN_COMMENT)
                    return
                self._set(start, close + 2 - start, "Comment")
                i = close + 2
                continue
            if kind == "template":
                close = _template_end(text, start + 1)
                if close < 0:
                    self._set(start, len(text) - start, "String")
                    self.setCurrentBlockState(IN_TEMPLATE)
                    return
                self._set(start, close + 1 - start, "String")
                i = close + 1
                continue
            if kind == "string":
                self._set(start, end - start, "Import" if is_import else "String")
            elif kind == "number":
                self._set(start, end - start, "DecVal")
            elif kind == "op":
                self._set(start, end - start, "Operator")
            elif kind == "ident":
                self._ident(text, word, start, end, member_start, is_import, prev_word)
                prev_word = word
            i = end

    def _ident(self, text, word, start, end, member_start, is_import, prev_word):
        if is_import:
            style = "Keyword" if word in ("import", "as", "pragma") else ("DataType" if prev_word == "as" else "Import")
            self._set(start, end - start, style)
            return
        if word in CONSTANTS:
            self._set(start, end - start, "Constant" if self._styles.get("Constant") else "Keyword")
            return
        if word in KEYWORDS and not _followed_by_colon(text, end):
            self._set(start, end - start, "Keyword")
            return
        if prev_word == "property" and (word in PROPERTY_TYPES or word[:1].isupper()):
            self._set(start, end - start, "DataType")
            return
        if prev_word in ("signal", "function"):
            self._set(start, end - start, "Function")
            return
        # a property name at the start of a member: `text:` / `anchors.fill:`
        if start == member_start or _member_chain_start(text, member_start, start):
            if _chain_followed_by_colon(text, end):
                self._set(start, end - start, "DataType" if word[:1].isupper() else "Attribute")
                return
        if prev_word in PROPERTY_TYPES and text[member_start:].startswith(("property", "readonly", "required", "default")):
            self._set(start, end - start, "Attribute")
            return
        if word[:1].isupper():
            self._set(start, end - start, "DataType")

    def _semantic(self, text: str):
        n = self.currentBlock().blockNumber()
        if n >= len(self._token_lines) or self._token_lines[n] != text:
            return
        for start, length, style, italic, strike in self._tokens.get(n, []):
            self._set(start, length, style, italic, strike)


def _template_end(text: str, i: int) -> int:
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "`":
            return i
        i += 1
    return -1


def _followed_by_colon(text: str, end: int) -> bool:
    rest = text[end:].lstrip()
    return rest.startswith(":") and not rest.startswith("::")


def _member_chain_start(text: str, member_start: int, start: int) -> bool:
    """Is `start` inside a dotted name that begins the member (a.b.c: …)?"""
    return re.fullmatch(r"[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)*\.", text[member_start:start]) is not None


def _chain_followed_by_colon(text: str, end: int) -> bool:
    m = re.match(r"(\.[A-Za-z_$][\w$]*)*\s*:(?!:)", text[end:])
    return m is not None


class XmlHighlighter(QmlHighlighter):
    """Qt Designer (.ui) files, with the styles of KSyntaxHighlighting's XML
    definition (element = Keyword, attribute = Others, value = String, …).

    Used instead of KSyntaxHighlighting while Kreator's QML highlighter is on,
    so switching between .qml and .ui never swaps highlighter implementations
    under a document that is being replaced.
    """

    _RE = re.compile(r"""
        (?P<comment><!--)
      | (?P<cdata><!\[CDATA\[)
      | (?P<pi><\?[\w:.-]*)
      | (?P<doctype><!DOCTYPE)
      | (?P<tag></?[A-Za-z_][\w:.-]*)
      | (?P<entity>&[#\w]+;)
    """, re.VERBOSE)
    _ATTR = re.compile(r"""\s*(?:(?P<end>/?>|\?>)|(?P<name>[A-Za-z_][\w:.-]*)\s*(?P<eq>=)?\s*(?P<value>"[^"]*"?|'[^']*'?)?)""")
    IN_TAG, IN_CDATA = 3, 4

    def highlightBlock(self, text: str):  # noqa: N802
        if not self._styles:
            return
        state = self.previousBlockState()
        self.setCurrentBlockState(0)
        i = 0
        if state == IN_COMMENT:
            i = self._until(text, 0, "-->", "Comment", IN_COMMENT)
        elif state == self.IN_CDATA:
            i = self._until(text, 0, "]]>", "BaseN", self.IN_CDATA)
        elif state == self.IN_TAG:
            i = self._attributes(text, 0)
        while 0 <= i < len(text):
            m = self._RE.search(text, i)
            if not m:
                return
            kind, start = m.lastgroup, m.start()
            if kind == "comment":
                i = self._until(text, start, "-->", "Comment", IN_COMMENT)
            elif kind == "cdata":
                i = self._until(text, start, "]]>", "BaseN", self.IN_CDATA)
            elif kind == "entity":
                self._set(start, m.end() - start, "DecVal")
                i = m.end()
            else:
                style = {"pi": "Function", "doctype": "DataType", "tag": "Keyword"}[kind]
                self._set(start, m.end() - start, style)
                i = self._attributes(text, m.end(), style if kind != "tag" else None)

    def _until(self, text, start, end_marker, style, state):
        end = text.find(end_marker, start + 1)
        if end < 0:
            self._set(start, len(text) - start, style)
            self.setCurrentBlockState(state)
            return -1
        self._set(start, end + len(end_marker) - start, style)
        return end + len(end_marker)

    def _attributes(self, text, i, whole_style=None):
        """name="value" pairs up to the end of the tag (which may be on a later line)."""
        while i < len(text):
            m = self._ATTR.match(text, i)
            if not m or m.end() == i:
                break
            if m.group("end"):
                self._set(m.start("end"), len(m.group("end")), whole_style or "Keyword")
                return m.end()
            self._set(m.start("name"), len(m.group("name")), whole_style or "Others")
            if m.group("eq"):
                self._set(m.start("eq"), 1, whole_style or "Others")
            if m.group("value"):
                self._set(m.start("value"), len(m.group("value")), whole_style or "String")
            i = m.end()
        if i >= len(text.rstrip()):
            self.setCurrentBlockState(self.IN_TAG)  # tag continues on the next line
            return -1
        return i
