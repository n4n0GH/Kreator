"""Hanging indents for the source view, like Kate's dynamic word wrap.

Each logical line (QTextBlock) gets a left margin equal to its indentation and
the same negative first-line indent: the first row stays where it is, wrapped
rows line up under the indented code.  As in Kate, lines indented deeper than
a share of the view width ("Dynamic Word Wrap Align Indent") are not aligned.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QFontMetricsF, QTextCursor


class TextLayout(QObject):
    @Slot(QObject, int, int, bool)
    def applyHangingIndent(self, quick_document, tab_width, align_percent, enabled):  # noqa: N802
        """Update the block margins of a QML TextEdit's document.

        The source view keeps its own undo history (text snapshots), so the
        document's undo stack is switched off and formatting is never undone.
        """
        doc = quick_document.textDocument() if hasattr(quick_document, "textDocument") else None
        if doc is None:
            return
        space = QFontMetricsF(doc.defaultFont()).horizontalAdvance(" ")
        limit = doc.textWidth() * align_percent / 100 if doc.textWidth() > 0 else float("inf")
        tab_width = max(1, tab_width)

        changes = []
        block = doc.begin()
        while block.isValid():
            px = 0.0
            if enabled and align_percent > 0:
                cols = 0
                for ch in block.text():
                    if ch == " ":
                        cols += 1
                    elif ch == "\t":
                        cols = (cols // tab_width + 1) * tab_width
                    else:
                        break
                px = cols * space
                if px > limit:
                    px = 0.0
            fmt = block.blockFormat()
            if abs(fmt.leftMargin() - px) > 0.01 or abs(fmt.textIndent() + px) > 0.01:
                changes.append((block.position(), px))
            block = block.next()
        if not changes:
            return

        if doc.isUndoRedoEnabled():
            doc.setUndoRedoEnabled(False)
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        for pos, px in changes:
            cursor.setPosition(pos)
            fmt = cursor.blockFormat()
            fmt.setLeftMargin(px)
            fmt.setTextIndent(-px)
            cursor.setBlockFormat(fmt)
        cursor.endEditBlock()

    @Slot(QObject)
    def disableUndo(self, quick_document):  # noqa: N802
        doc = quick_document.textDocument() if hasattr(quick_document, "textDocument") else None
        if doc is not None and doc.isUndoRedoEnabled():
            doc.setUndoRedoEnabled(False)

    @Slot(QObject, "QVariantList")
    def setHiddenLines(self, quick_document, hidden):  # noqa: N802
        """Code folding: hide the given (0-based) lines, show all others.

        Changing a block's visibility alone does not make the TextEdit re-measure,
        so the block format is touched as well (a no-op user property), which
        reports the change to the layout and the item.
        """
        doc = quick_document.textDocument() if hasattr(quick_document, "textDocument") else None
        if doc is None:
            return
        hidden = {int(h) for h in hidden}
        if doc.isUndoRedoEnabled():
            doc.setUndoRedoEnabled(False)
        cursor = None
        block = doc.begin()
        n = 0
        while block.isValid():
            visible = n not in hidden
            if block.isVisible() != visible:
                block.setVisible(visible)
                if cursor is None:
                    cursor = QTextCursor(doc)
                    cursor.beginEditBlock()
                cursor.setPosition(block.position())
                fmt = cursor.blockFormat()
                fmt.setProperty(_FOLDED_PROPERTY, not visible)
                cursor.setBlockFormat(fmt)
            block = block.next()
            n += 1
        if cursor is not None:
            cursor.endEditBlock()


_FOLDED_PROPERTY = 0x100000 + 1  # QTextFormat.UserProperty + 1
