"""
Parameter model: descriptors, validation, and Qt tree model.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from PySide6.QtCore import (
    QAbstractItemModel, QModelIndex, Qt, Signal, QObject
)


# ── Parameter type ────────────────────────────────────────────────────────────
class ParamType(IntEnum):
    BOOL = 0
    U8   = 1
    I32  = 2
    F32  = 3


_TYPE_STRUCT: dict[ParamType, str] = {
    ParamType.BOOL: "B",
    ParamType.U8:   "B",
    ParamType.I32:  "i",
    ParamType.F32:  "f",
}


# ── Flags ─────────────────────────────────────────────────────────────────────
class ParamFlags(IntEnum):
    READ_ONLY  = 0x01
    PERSISTENT = 0x02
    EXPERT     = 0x04


# ── Descriptor ────────────────────────────────────────────────────────────────
@dataclass
class ParameterDescriptor:
    param_id:      int
    type:          ParamType
    flags:         int
    min_value:     float
    max_value:     float
    default_value: float
    name:          str
    unit:          str
    group:         str

    @property
    def read_only(self) -> bool:
        return bool(self.flags & ParamFlags.READ_ONLY)

    @property
    def persistent(self) -> bool:
        return bool(self.flags & ParamFlags.PERSISTENT)

    def encode_value(self, value: float) -> bytes:
        fmt = "<" + _TYPE_STRUCT[self.type]
        if self.type == ParamType.BOOL:
            return struct.pack(fmt, 1 if value else 0)
        return struct.pack(fmt, value)

    def decode_value(self, raw: bytes) -> float:
        fmt = "<" + _TYPE_STRUCT[self.type]
        size = struct.calcsize(fmt)
        if len(raw) < size:
            raise ValueError(f"Not enough bytes to decode param {self.name}")
        (v,) = struct.unpack_from(fmt, raw)
        return float(v)

    def validate(self, value: float) -> bool:
        return self.min_value <= value <= self.max_value


# ── Default parameter table (bring-up defaults from spec §8.3) ───────────────
def default_parameter_table() -> list[ParameterDescriptor]:
    RO  = ParamFlags.READ_ONLY
    PER = ParamFlags.PERSISTENT
    F32 = ParamType.F32
    I32 = ParamType.I32
    U8  = ParamType.U8
    BOL = ParamType.BOOL

    return [
        # control.angle
        ParameterDescriptor(0x0001, F32, PER, 0.0, 100.0, 1.0,  "angle.kp",            "",    "control.angle"),
        ParameterDescriptor(0x0002, F32, PER, 0.0,  50.0, 0.0,  "angle.ki",            "",    "control.angle"),
        ParameterDescriptor(0x0003, F32, PER, 0.0,  20.0, 0.05, "angle.kd",            "",    "control.angle"),
        ParameterDescriptor(0x0004, F32, PER, 0.1,   1.0, 1.0,  "angle.output_limit",  "",    "control.angle"),
        ParameterDescriptor(0x0005, F32, PER, 0.0,  50.0, 5.0,  "angle.integral_limit","",    "control.angle"),
        # control.velocity
        ParameterDescriptor(0x0010, F32, PER, 0.0, 100.0, 0.5,  "velocity.kp",              "",    "control.velocity"),
        ParameterDescriptor(0x0011, F32, PER, 0.0,  50.0, 0.0,  "velocity.ki",              "",    "control.velocity"),
        ParameterDescriptor(0x0012, F32, PER, 0.0,  20.0, 0.0,  "velocity.kd",              "",    "control.velocity"),
        ParameterDescriptor(0x0013, F32, PER, 1.0, 200.0, 10.0, "velocity.target_limit_rpm","rpm",  "control.velocity"),
        ParameterDescriptor(0x0014, F32, PER, 0.0,  50.0, 5.0,  "velocity.integral_limit",  "",    "control.velocity"),
        # control.yaw
        ParameterDescriptor(0x0020, F32, PER, 0.0, 100.0, 0.3,  "yaw.kp",          "",  "control.yaw"),
        ParameterDescriptor(0x0021, F32, PER, 0.0,  50.0, 0.0,  "yaw.ki",          "",  "control.yaw"),
        ParameterDescriptor(0x0022, F32, PER, 0.0,  20.0, 0.0,  "yaw.kd",          "",  "control.yaw"),
        ParameterDescriptor(0x0023, F32, PER, 0.0,   1.0, 0.30, "yaw.output_limit","",  "control.yaw"),
        # control.general
        ParameterDescriptor(0x0030, F32, PER, 1.0,  50.0, 5.0,  "control.sample_time_ms",       "ms",  "control.general"),
        ParameterDescriptor(0x0031, BOL, PER, 0.0,   1.0, 0.0,  "control.balance_enable",       "",    "control.general"),
        ParameterDescriptor(0x0032, F32, PER,-10.0, 10.0, 0.0,  "control.target_pitch_bias_deg","°",   "control.general"),
        ParameterDescriptor(0x0033, F32, PER, 0.0,   0.5, 0.15, "control.deadband_left",        "",    "control.general"),
        ParameterDescriptor(0x0034, F32, PER, 0.0,   0.5, 0.15, "control.deadband_right",       "",    "control.general"),
        # safety
        ParameterDescriptor(0x0040, F32, PER,10.0, 90.0, 45.0, "safety.tilt_cutoff_deg",        "°",  "safety"),
        ParameterDescriptor(0x0041, F32, PER, 0.1,  5.0, 1.8,  "safety.current_limit_left_a",   "A",  "safety"),
        ParameterDescriptor(0x0042, F32, PER, 0.1,  5.0, 1.8,  "safety.current_limit_right_a",  "A",  "safety"),
        ParameterDescriptor(0x0043, F32, PER, 50.0,5000.0,500.0,"safety.command_timeout_ms",    "ms", "safety"),
        ParameterDescriptor(0x0044, F32, PER, 50.0,2000.0,200.0,"safety.ble_timeout_ms",        "ms", "safety"),
        # imu
        ParameterDescriptor(0x0050, F32, PER, 0.5,  4.0, 1.0,  "imu.accel_scale",     "",   "imu"),
        ParameterDescriptor(0x0051, F32, PER,125.0,2000.0,250.0,"imu.gyro_scale",     "dps", "imu"),
        ParameterDescriptor(0x0052, F32, PER,-20.0,20.0,  0.0,  "imu.pitch_offset_deg","°",  "imu"),
        ParameterDescriptor(0x0053, F32, PER, 0.0,  1.0,  0.5,  "imu.filter_gain",    "",    "imu"),
        ParameterDescriptor(0x0054, F32, PER, 0.0,  1.0,  0.1,  "imu.acc_rejection",  "",    "imu"),
        # robot
        ParameterDescriptor(0x0060, F32, PER, 0.01, 0.2, 0.037,"robot.wheel_radius_m",        "m",  "robot"),
        ParameterDescriptor(0x0061, I32, PER,  64, 4096, 1856,  "robot.encoder_ticks_per_rev", "",   "robot"),
        ParameterDescriptor(0x0062, F32, PER,  1.0, 50.0, 29.0, "robot.gear_ratio",            "",   "robot"),
        ParameterDescriptor(0x0063, I32, PER, -1,     1,    1,  "robot.motor_polarity_left",   "",   "robot"),
        ParameterDescriptor(0x0064, I32, PER, -1,     1,    1,  "robot.motor_polarity_right",  "",   "robot"),
    ]


# ── Qt tree model ─────────────────────────────────────────────────────────────
_COL_NAME    = 0
_COL_VALUE   = 1
_COL_UNIT    = 2
_COL_RANGE   = 3
_COL_ACCESS  = 4
COLUMN_HEADERS = ["Parameter", "Value", "Unit", "Range", "Access"]


class _GroupNode:
    def __init__(self, name: str, parent=None) -> None:
        self.name     = name
        self.parent   = parent
        self.children: list[_ParamNode] = []

    def child_count(self) -> int:
        return len(self.children)


class _ParamNode:
    def __init__(self, desc: ParameterDescriptor, parent: _GroupNode) -> None:
        self.desc           = desc
        self.parent         = parent
        self.current_value: float = desc.default_value
        self.confirmed_value: float = desc.default_value
        self.pending: bool  = False   # local edit not yet ACKed


class ParameterModel(QAbstractItemModel):
    """
    Qt tree model: root → group nodes → parameter nodes.
    Emits parameter_write_requested when the user edits a value.
    """

    parameter_write_requested = Signal(int, float)  # param_id, value

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._groups:     list[_GroupNode] = []
        self._id_to_node: dict[int, _ParamNode] = {}
        self._populate(default_parameter_table())

    # ── Population ────────────────────────────────────────────────────────────
    def _populate(self, descriptors: list[ParameterDescriptor]) -> None:
        self.beginResetModel()
        self._groups.clear()
        self._id_to_node.clear()
        group_map: dict[str, _GroupNode] = {}
        for desc in descriptors:
            if desc.group not in group_map:
                g = _GroupNode(desc.group)
                group_map[desc.group] = g
                self._groups.append(g)
            g = group_map[desc.group]
            node = _ParamNode(desc, g)
            g.children.append(node)
            self._id_to_node[desc.param_id] = node
        self.endResetModel()

    def load_descriptors(self, descriptors: list[ParameterDescriptor]) -> None:
        self._populate(descriptors)

    # ── Value updates from firmware ────────────────────────────────────────────
    def update_from_firmware(self, param_id: int, value: float) -> None:
        node = self._id_to_node.get(param_id)
        if node is None:
            return
        node.current_value   = value
        node.confirmed_value = value
        node.pending         = False
        self._notify_node(node)

    def mark_nack(self, param_id: int) -> None:
        node = self._id_to_node.get(param_id)
        if node is None:
            return
        node.current_value = node.confirmed_value
        node.pending       = False
        self._notify_node(node)

    def _notify_node(self, node: _ParamNode) -> None:
        g = node.parent
        gi = self._groups.index(g)
        pi = g.children.index(node)
        parent_idx = self.index(gi, 0, QModelIndex())
        tl = self.index(pi, 0, parent_idx)
        br = self.index(pi, len(COLUMN_HEADERS) - 1, parent_idx)
        self.dataChanged.emit(tl, br)

    # ── QAbstractItemModel ─────────────────────────────────────────────────────
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not parent.isValid():
            return len(self._groups)
        item = parent.internalPointer()
        if isinstance(item, _GroupNode):
            return item.child_count()
        return 0

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(COLUMN_HEADERS)

    def index(self, row: int, col: int,
              parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if not parent.isValid():
            if row < len(self._groups):
                return self.createIndex(row, col, self._groups[row])
            return QModelIndex()
        g = parent.internalPointer()
        if isinstance(g, _GroupNode) and row < len(g.children):
            return self.createIndex(row, col, g.children[row])
        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()
        item = index.internalPointer()
        if isinstance(item, _GroupNode):
            return QModelIndex()
        if isinstance(item, _ParamNode):
            g = item.parent
            gi = self._groups.index(g)
            return self.createIndex(gi, 0, g)
        return QModelIndex()

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.DisplayRole) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMN_HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        item = index.internalPointer()
        col  = index.column()

        if isinstance(item, _GroupNode):
            if role == Qt.DisplayRole and col == _COL_NAME:
                return item.name
            if role == Qt.FontRole:
                from PySide6.QtGui import QFont
                f = QFont()
                f.setBold(True)
                return f
            return None

        if isinstance(item, _ParamNode):
            desc = item.desc
            if role == Qt.DisplayRole:
                if col == _COL_NAME:
                    return desc.name
                if col == _COL_VALUE:
                    if desc.type == ParamType.BOOL:
                        return "True" if item.current_value else "False"
                    if desc.type in (ParamType.I32, ParamType.U8):
                        return str(int(item.current_value))
                    return f"{item.current_value:.4g}"
                if col == _COL_UNIT:
                    return desc.unit
                if col == _COL_RANGE:
                    return f"{desc.min_value:.4g} … {desc.max_value:.4g}"
                if col == _COL_ACCESS:
                    return "R" if desc.read_only else "R/W"

            if role == Qt.ForegroundRole:
                from PySide6.QtGui import QColor
                if col == _COL_VALUE:
                    if item.pending:
                        return QColor("#ffd54f")   # amber = unsaved edit
                    if not desc.validate(item.current_value):
                        return QColor("#ef5350")   # red = out of range
                return None

            if role == Qt.EditRole and col == _COL_VALUE:
                return item.current_value

            if role == Qt.ToolTipRole:
                return (f"ID: 0x{desc.param_id:04X}  "
                        f"Default: {desc.default_value:.4g}  "
                        f"{'Persistent' if desc.persistent else ''}")

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        item = index.internalPointer()
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if isinstance(item, _ParamNode) and index.column() == _COL_VALUE:
            if not item.desc.read_only:
                return base | Qt.ItemIsEditable
        return base

    def setData(self, index: QModelIndex, value: Any,
                role: int = Qt.EditRole) -> bool:
        if role != Qt.EditRole:
            return False
        item = index.internalPointer()
        if not isinstance(item, _ParamNode):
            return False
        desc = item.desc
        try:
            v = float(value)
        except (TypeError, ValueError):
            return False
        if not desc.validate(v):
            return False
        item.current_value = v
        item.pending       = True
        self.dataChanged.emit(index, index)
        self.parameter_write_requested.emit(desc.param_id, v)
        return True

    def get_all_values(self) -> dict[str, float]:
        """Return {name: current_value} for all parameters."""
        result: dict[str, float] = {}
        for g in self._groups:
            for node in g.children:
                result[node.desc.name] = node.current_value
        return result
