"""Generic list model with incremental updates (keeps delegates and scroll position)."""

from __future__ import annotations

import difflib

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Qt, Property, Signal


class RowsModel(QAbstractListModel):
    countChanged = Signal()

    def __init__(self, roles: list[str], key: str, parent=None):
        super().__init__(parent)
        self._roles = roles
        self._key = key
        self._rows: list[dict] = []

    def roleNames(self):  # noqa: N802
        return {Qt.ItemDataRole.UserRole + i: QByteArray(r.encode()) for i, r in enumerate(self._roles)}

    def rowCount(self, parent=QModelIndex()):  # noqa: N802, B008
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        i = role - Qt.ItemDataRole.UserRole
        if role == Qt.ItemDataRole.DisplayRole:
            i = 0
        if 0 <= i < len(self._roles):
            return self._rows[index.row()].get(self._roles[i])
        return None

    @Property(int, notify=countChanged)
    def count(self):
        return len(self._rows)

    def rows(self):
        return self._rows

    def row(self, i):
        return self._rows[i] if 0 <= i < len(self._rows) else None

    def set_rows(self, rows: list[dict]):
        old_keys = [r.get(self._key) for r in self._rows]
        new_keys = [r.get(self._key) for r in rows]
        if len(set(new_keys)) != len(new_keys) or len(set(old_keys)) != len(old_keys):
            self.beginResetModel()
            self._rows = list(rows)
            self.endResetModel()
            self.countChanged.emit()
            return
        sm = difflib.SequenceMatcher(a=old_keys, b=new_keys, autojunk=False)
        ops = sm.get_opcodes()
        # apply structural changes back to front so indices stay valid
        for tag, i1, i2, j1, j2 in reversed(ops):
            if tag in ("delete", "replace"):
                self.beginRemoveRows(QModelIndex(), i1, i2 - 1)
                del self._rows[i1:i2]
                self.endRemoveRows()
            if tag in ("insert", "replace"):
                self.beginInsertRows(QModelIndex(), i1, i1 + (j2 - j1) - 1)
                self._rows[i1:i1] = rows[j1:j2]
                self.endInsertRows()
        # now refresh contents
        for i, r in enumerate(rows):
            if self._rows[i] != r:
                self._rows[i] = r
                idx = self.index(i, 0)
                self.dataChanged.emit(idx, idx)
        if len(old_keys) != len(new_keys):
            self.countChanged.emit()
