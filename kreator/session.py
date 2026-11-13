"""Compact storage of undo/redo history for the saved session.

The backend keeps full-text snapshots ((text, selection) pairs, up to 200 per
document). Snapshots next to each other differ only a little, so each one is
stored as a line diff against its neighbour that is closer to the current
text, and the whole chain is rebuilt from the current text on restore.
"""

from __future__ import annotations

import difflib
import hashlib
from functools import lru_cache


def text_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


@lru_cache(maxsize=4096)
def _delta(base: str, target: str) -> tuple:
    """Edits turning base into target: ((start, end, [lines]), ...) on base's lines."""
    a = base.splitlines(keepends=True)
    b = target.splitlines(keepends=True)
    ops = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    return tuple((i1, i2, tuple(b[j1:j2])) for tag, i1, i2, j1, j2 in ops if tag != "equal")


def _apply(base: str, delta) -> str:
    lines = base.splitlines(keepends=True)
    for i1, i2, new in reversed(delta):  # back to front keeps earlier indexes valid
        lines[i1:i2] = new
    return "".join(lines)


def encode_chain(current: str, stack: list) -> list:
    """Encode an undo or redo stack (its last entry is the one next to current)."""
    out = []
    prev = current
    for text, sel in reversed(stack):
        out.append([[list(e[:2]) + [list(e[2])] for e in _delta(prev, text)], sel])
        prev = text
    out.reverse()
    return out


def decode_chain(current: str, encoded) -> list:
    """The inverse of encode_chain; [] if the data doesn't fit."""
    stack = []
    prev = current
    try:
        for delta, sel in reversed(encoded):
            text = _apply(prev, [(int(i1), int(i2), [str(x) for x in new]) for i1, i2, new in delta])
            stack.append((text, int(sel)))
            prev = text
    except (TypeError, ValueError, IndexError):
        return []
    stack.reverse()
    return stack
