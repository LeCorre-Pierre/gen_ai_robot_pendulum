"""Enumerate COM ports, tagging ST-Link VCP adapters."""

from __future__ import annotations

from dataclasses import dataclass

import serial.tools.list_ports as _lp

# Known USB VID:PID combos for ST-Link VCP
_STLINK_VIDS = {0x0483}  # STMicroelectronics
_STLINK_PIDS = {0x374B, 0x374E, 0x3748}  # ST-Link/V2, V2-1, V3


@dataclass
class PortInfo:
    device: str
    description: str
    is_stlink: bool


def list_ports() -> list[PortInfo]:
    """Return all available serial ports. ST-Link adapters are flagged."""
    ports: list[PortInfo] = []
    for p in _lp.comports():
        vid = getattr(p, "vid", None)
        pid = getattr(p, "pid", None)
        is_st = (vid in _STLINK_VIDS) and (pid in _STLINK_PIDS)
        desc = p.description or p.device
        ports.append(PortInfo(device=p.device, description=desc, is_stlink=is_st))
    # Sort: ST-Link first, then alphabetical
    ports.sort(key=lambda p: (not p.is_stlink, p.device))
    return ports
