"""
VCP protocol — matches vcp_protocol.h (STM32 firmware).

Frame layout (little-endian):
  SOF1(0xAA) SOF2(0x55) VER TYPE FLAGS SEQ LEN_L LEN_H PAYLOAD… CRC16_L CRC16_H EOF(0x33)

CRC16-CCITT computed over bytes [2 .. 8+payload_len-1] (VER through end of payload).
All payload structs are __attribute__((packed)) on the firmware side — no alignment padding.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass

# ── Frame constants ────────────────────────────────────────────────────────────
SOF1 = 0xAA
SOF2 = 0x55
EOF  = 0x33
VER  = 0x01

# ── Packet type codes ──────────────────────────────────────────────────────────
TYPE_TELEMETRY_PID   = 0x10   # STM32 → PC
TYPE_CMD_SET_GAINS   = 0x20   # PC → STM32
TYPE_CMD_SET_SP      = 0x21
TYPE_CMD_STREAM_CTRL = 0x22
TYPE_CMD_MOTOR_CTRL  = 0x23
TYPE_ACK             = 0x30   # STM32 → PC

# ── Motor identifiers ──────────────────────────────────────────────────────────
MOTOR_LEFT  = 0
MOTOR_RIGHT = 1
MOTOR_BOTH  = 2

# ── Motor action codes ─────────────────────────────────────────────────────────
ACTION_COAST  = 0
ACTION_BRAKE  = 1
ACTION_ENABLE = 2

# ── Payload struct formats (little-endian, matches packed C structs) ───────────
#   VcpTelPid_t      : uint32 + 7×int16 = 18 bytes
#   VcpCmdSetGains_t : uint8  + 3×float = 13 bytes
#   VcpCmdSetSp_t    : int16             =  2 bytes
#   VcpCmdStreamCtrl : uint8 + uint16   =  3 bytes
#   VcpCmdMotorCtrl  : uint8             =  1 byte
#   VcpAck_t         : 2×uint8           =  2 bytes
_S_TEL      = struct.Struct('<Ihhhhhhh')   # 18 bytes
_S_GAINS    = struct.Struct('<Bfff')       # 13 bytes
_S_SP       = struct.Struct('<h')          #  2 bytes
_S_STREAM   = struct.Struct('<BH')         #  3 bytes
_S_MOTOR    = struct.Struct('<B')          #  1 byte
_S_ACK      = struct.Struct('<BB')         #  2 bytes


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class Packet:
    type:    int
    flags:   int
    seq:     int
    payload: bytes


@dataclass
class TelemetryPID:
    timestamp_ms: int
    sp_rpm:       int
    pv_l_rpm:     int
    pv_r_rpm:     int
    err_l:        int
    err_r:        int
    pwm_l_pct:    float   # normalised [-1..+1]
    pwm_r_pct:    float


# ── CRC16-CCITT ────────────────────────────────────────────────────────────────

def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc


# ── Frame encode / decode ──────────────────────────────────────────────────────

def encode(pkt: Packet) -> bytes:
    """Build a complete wire frame from a Packet."""
    pay = pkt.payload
    header = bytes([SOF1, SOF2, VER, pkt.type, pkt.flags, pkt.seq,
                    len(pay) & 0xFF, (len(pay) >> 8) & 0xFF])
    crc = crc16(header[2:] + pay)
    return header + pay + bytes([crc & 0xFF, crc >> 8, EOF])


def decode(frame: bytes) -> Packet | None:
    """Validate and decode a complete frame. Returns None on any error."""
    if len(frame) < 11:
        return None
    if frame[0] != SOF1 or frame[1] != SOF2:
        return None
    plen = frame[6] | (frame[7] << 8)
    expected = 11 + plen
    if len(frame) < expected:
        return None
    crc_calc = crc16(bytes(frame[2: 8 + plen]))
    crc_recv = frame[8 + plen] | (frame[9 + plen] << 8)
    if crc_calc != crc_recv:
        return None
    if frame[10 + plen] != EOF:
        return None
    return Packet(type=frame[3], flags=frame[4], seq=frame[5],
                  payload=bytes(frame[8: 8 + plen]))


# ── Command builders ───────────────────────────────────────────────────────────

def make_set_gains(motor: int, kp: float, ki: float, kd: float) -> Packet:
    return Packet(TYPE_CMD_SET_GAINS, 0, 0, _S_GAINS.pack(motor, kp, ki, kd))


def make_set_sp(sp_rpm: int) -> Packet:
    return Packet(TYPE_CMD_SET_SP, 0, 0, _S_SP.pack(int(sp_rpm)))


def make_stream_ctrl(enable: bool, rate_hz: int = 50) -> Packet:
    return Packet(TYPE_CMD_STREAM_CTRL, 0, 0, _S_STREAM.pack(int(enable), int(rate_hz)))


def make_motor_ctrl(action: int) -> Packet:
    return Packet(TYPE_CMD_MOTOR_CTRL, 0, 0, _S_MOTOR.pack(action))


# ── Telemetry parser ───────────────────────────────────────────────────────────

def parse_telemetry(pkt: Packet) -> TelemetryPID | None:
    if pkt.type != TYPE_TELEMETRY_PID or len(pkt.payload) < _S_TEL.size:
        return None
    ts, sp, pv_l, pv_r, err_l, err_r, pwm_l, pwm_r = _S_TEL.unpack(
        pkt.payload[:_S_TEL.size]
    )
    return TelemetryPID(ts, sp, pv_l, pv_r, err_l, err_r,
                        pwm_l / 100.0, pwm_r / 100.0)


def motor_id(motor: str | int) -> int:
    """Accept 'left'/'right'/'both' or 0/1/2."""
    if isinstance(motor, int):
        return motor
    return {'left': MOTOR_LEFT, 'right': MOTOR_RIGHT, 'both': MOTOR_BOTH}[motor.lower()]
