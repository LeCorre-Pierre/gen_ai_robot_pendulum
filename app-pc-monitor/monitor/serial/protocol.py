"""
Binary framing protocol — matches 4-stlink-vcp-interface.md §3.

Frame layout:
    SOF1(0xAA) SOF2(0x55) VER TYPE FLAGS SEQ LEN_L LEN_H PAYLOAD... CRC_L CRC_H EOF(0x33)

CRC16-CCITT (poly=0x1021, init=0xFFFF, no reflection) computed over VER..PAYLOAD.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

# ── Frame constants ──────────────────────────────────────────────────────────
SOF1: int = 0xAA
SOF2: int = 0x55
EOF_BYTE: int = 0x33
PROTO_VER: int = 0x01
HEADER_SIZE: int = 8   # SOF1 SOF2 VER TYPE FLAGS SEQ LEN_L LEN_H
FOOTER_SIZE: int = 3   # CRC_L CRC_H EOF
MAX_PAYLOAD: int = 256


# ── Message types ────────────────────────────────────────────────────────────
class MsgType(IntEnum):
    # Link / discovery
    PING               = 0x01
    PONG               = 0x02
    GET_DEVICE_INFO    = 0x03
    DEVICE_INFO        = 0x04
    ACK                = 0x05
    NACK               = 0x06
    # Telemetry control
    SET_STREAM_CONFIG  = 0x10
    GET_STREAM_CONFIG  = 0x11
    STREAM_CONFIG      = 0x12
    TELEMETRY_SAMPLE   = 0x13
    TELEMETRY_BURST    = 0x14
    # Parameters
    GET_PARAMETER_TABLE = 0x20
    PARAMETER_TABLE    = 0x21
    READ_PARAMETER     = 0x22
    WRITE_PARAMETER    = 0x23
    PARAMETER_VALUE    = 0x24
    SAVE_PARAMETERS    = 0x25
    LOAD_PARAMETERS    = 0x26
    # Commands
    SET_CONTROL_MODE   = 0x30
    SET_MANUAL_COMMAND = 0x31
    EMERGENCY_STOP     = 0x32
    CLEAR_FAULT        = 0x33
    START_TEST         = 0x34
    STOP_TEST          = 0x35
    SET_LOG_LEVEL      = 0x36
    # Events / faults / logs
    EVENT              = 0x40
    FAULT              = 0x41
    LOG_TEXT           = 0x42
    STATE_SNAPSHOT     = 0x43
    # Capture
    CAPTURE_CONFIG     = 0x50
    CAPTURE_ARM        = 0x51
    CAPTURE_STATUS     = 0x52
    CAPTURE_DATA       = 0x53


# ── Flags ────────────────────────────────────────────────────────────────────
class Flags(IntEnum):
    NONE   = 0x00
    ACK_REQ = 0x01
    STREAM  = 0x02
    ERROR   = 0x80


# ── Packet dataclass ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Packet:
    ver:     int
    type:    int
    flags:   int
    seq:     int
    payload: bytes

    @property
    def msg_type(self) -> MsgType | None:
        try:
            return MsgType(self.type)
        except ValueError:
            return None


# ── CRC16-CCITT (CRC-16/CCITT-FALSE) ─────────────────────────────────────────
def crc16_ccitt(data: bytes) -> int:
    """CRC16-CCITT: poly=0x1021, init=0xFFFF, no reflection, no final XOR."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


# ── Encoder ──────────────────────────────────────────────────────────────────
_seq_counter: int = 0


def encode_packet(
    msg_type: int | MsgType,
    payload: bytes = b"",
    seq: int | None = None,
    flags: int = Flags.NONE,
) -> bytes:
    """Build a complete frame ready to write to the serial port."""
    global _seq_counter
    if seq is None:
        seq = _seq_counter & 0xFF
        _seq_counter += 1

    payload_len = len(payload)
    if payload_len > MAX_PAYLOAD:
        raise ValueError(f"Payload too large: {payload_len} > {MAX_PAYLOAD}")

    crc_input = bytes([PROTO_VER, int(msg_type), flags, seq,
                       payload_len & 0xFF, (payload_len >> 8) & 0xFF]) + payload
    crc = crc16_ccitt(crc_input)

    frame = bytearray()
    frame += bytes([SOF1, SOF2, PROTO_VER, int(msg_type), flags, seq,
                    payload_len & 0xFF, (payload_len >> 8) & 0xFF])
    frame += payload
    frame += bytes([crc & 0xFF, (crc >> 8) & 0xFF, EOF_BYTE])
    return bytes(frame)


def reset_seq() -> None:
    global _seq_counter
    _seq_counter = 0


# ── NACK error code names (shared with session and frame inspector) ───────────
NACK_ERROR_NAMES: dict[int, str] = {
    0x01: "ERR_UNKNOWN_TYPE",
    0x02: "ERR_INVALID_LENGTH",
    0x03: "ERR_INVALID_STATE",
    0x04: "ERR_NOT_READY",
    0x05: "ERR_INVALID_PARAM",
    0x06: "ERR_ACCESS_DENIED",
    0x07: "ERR_CHECKSUM",
    0x08: "ERR_TIMEOUT",
    0x09: "ERR_OVERFLOW",
    0xFF: "ERR_GENERIC",
}


def _type_name(v: int) -> str:
    try:
        return MsgType(v).name
    except ValueError:
        return f"0x{v:02X}"


def _fmt_duration(ms: int) -> str:
    if ms < 1_000:
        return f"{ms}ms"
    if ms < 60_000:
        return f"{ms / 1000:.1f}s"
    if ms < 3_600_000:
        return f"{ms // 60_000}m{(ms % 60_000) // 1000}s"
    return f"{ms // 3_600_000}h{(ms % 3_600_000) // 60_000}m"


def decode_payload_fields(msg_type_int: int, payload: bytes) -> dict[str, str]:
    """Return human-readable field name → value for each known message type."""
    try:
        mt = MsgType(msg_type_int)
    except ValueError:
        return {"raw": payload.hex(" ").upper()} if payload else {}

    p = payload
    f: dict[str, str] = {}

    if mt == MsgType.PONG:
        if len(p) >= 4:
            uptime_ms = struct.unpack_from("<I", p, 0)[0]
            f["uptime_ms"] = str(uptime_ms)
            f["uptime"]    = _fmt_duration(uptime_ms)
        if len(p) >= 5:
            f["proto_ver"] = f"0x{p[4]:02X}"

    elif mt == MsgType.DEVICE_INFO:
        if len(p) >= 3:
            f["fw_ver"] = f"{p[0]}.{p[1]}.{p[2]}"
        if len(p) >= 5:
            f["capabilities"] = f"0x{struct.unpack_from('<H', p, 3)[0]:04X}"

    elif mt == MsgType.ACK:
        if len(p) >= 2:
            f["acked"] = _type_name(p[0])
            f["seq"]   = str(p[1])

    elif mt == MsgType.NACK:
        if len(p) >= 3:
            f["nacked"] = _type_name(p[0])
            f["seq"]    = str(p[1])
            ec = p[2]
            f["error"]  = f"{ec} ({NACK_ERROR_NAMES.get(ec, '?')})"

    elif mt in (MsgType.SET_STREAM_CONFIG, MsgType.STREAM_CONFIG):
        if len(p) >= 4:
            sid, enable, period = struct.unpack_from("<BBH", p)
            f["stream_id"] = f"0x{sid:02X}"
            f["enable"]    = "true" if enable else "false"
            f["period_ms"] = str(period)
        elif p:
            f["stream_id"] = f"0x{p[0]:02X}"

    elif mt == MsgType.GET_STREAM_CONFIG:
        if p:
            f["stream_id"] = f"0x{p[0]:02X}"

    elif mt == MsgType.TELEMETRY_SAMPLE:
        if p:
            f["stream_id"]   = f"0x{p[0]:02X}"
            f["payload_len"] = str(len(p) - 1)

    elif mt == MsgType.TELEMETRY_BURST:
        if p:
            f["stream_id"] = f"0x{p[0]:02X}"
            f["len"]       = str(len(p))

    elif mt == MsgType.READ_PARAMETER:
        if len(p) >= 2:
            f["param_id"] = f"0x{struct.unpack_from('<H', p)[0]:04X}"

    elif mt in (MsgType.WRITE_PARAMETER, MsgType.PARAMETER_VALUE):
        if len(p) >= 2:
            f["param_id"]  = f"0x{struct.unpack_from('<H', p)[0]:04X}"
            f["value_raw"] = p[2:].hex(" ").upper() if len(p) > 2 else ""

    elif mt == MsgType.LOAD_PARAMETERS:
        if p:
            f["slot"] = str(p[0])

    elif mt == MsgType.SET_CONTROL_MODE:
        if p:
            f["mode"] = str(p[0])

    elif mt == MsgType.SET_MANUAL_COMMAND:
        if len(p) >= 8:
            fwd, turn = struct.unpack_from("<ff", p)
            f["forward"] = f"{fwd:.3f}"
            f["turn"]    = f"{turn:.3f}"

    elif mt == MsgType.EMERGENCY_STOP:
        if p:
            f["reason"] = str(p[0])

    elif mt == MsgType.START_TEST:
        if p:
            f["test_id"] = str(p[0])
            if len(p) > 1:
                f["args"] = p[1:].hex(" ").upper()

    elif mt == MsgType.SET_LOG_LEVEL:
        if p:
            f["level"] = str(p[0])

    elif mt == MsgType.EVENT:
        if len(p) >= 2:
            code = struct.unpack_from("<H", p)[0]
            f["event_code"] = f"0x{code:04X}"
            if len(p) > 2:
                f["context_len"] = str(len(p) - 2)

    elif mt == MsgType.FAULT:
        if len(p) >= 2:
            code = struct.unpack_from("<H", p)[0]
            f["fault_code"] = f"0x{code:04X}"

    elif mt == MsgType.LOG_TEXT:
        if len(p) >= 4:
            f["ts_ms"] = str(struct.unpack_from("<I", p)[0])
        if len(p) > 4:
            f["level"]  = str(p[4])
        if len(p) > 5:
            f["module"] = str(p[5])

    elif mt == MsgType.CAPTURE_CONFIG:
        if len(p) >= 6:
            trigger, sig_mask, pre, post = struct.unpack_from("<BBHH", p)
            f["trigger"]      = str(trigger)
            f["signal_mask"]  = f"0x{sig_mask:02X}"
            f["pre_samples"]  = str(pre)
            f["post_samples"] = str(post)

    elif mt == MsgType.CAPTURE_STATUS:
        if p:
            status_map = {0: "IDLE", 1: "ARMED", 2: "TRIGGERED", 3: "DONE"}
            f["status"] = status_map.get(p[0], f"0x{p[0]:02X}")

    return f


# ── FrameRecord (for Frame Inspector panel) ───────────────────────────────────
from dataclasses import dataclass as _dc, field as _field


@_dc
class FrameRecord:
    """One captured TX or RX frame, with decoded fields."""
    ts_ms:     int
    direction: str          # "TX" or "RX"
    type_name: str
    seq:       int
    flags:     int
    payload:   bytes
    raw:       bytes        # full frame bytes (TX) or empty (RX)
    fields:    dict         # str → str decoded payload fields


# ── Decoder / frame parser ────────────────────────────────────────────────────
class ParseError(Exception):
    pass


class FrameParser:
    """
    Stateful streaming byte parser.

    Feed bytes incrementally via push().
    Complete valid packets are collected in packets (list).
    crc_errors counts frames dropped due to bad CRC.
    """

    _STATE_WAIT_SOF1 = 0
    _STATE_WAIT_SOF2 = 1
    _STATE_HEADER    = 2
    _STATE_PAYLOAD   = 3
    _STATE_CRC_L     = 4
    _STATE_CRC_H     = 5
    _STATE_EOF       = 6

    def __init__(self) -> None:
        self.packets:    list[Packet] = []
        self.crc_errors: int = 0
        self._reset()

    def _reset(self) -> None:
        self._state     = self._STATE_WAIT_SOF1
        self._buf       = bytearray()
        self._payload   = bytearray()
        self._payload_remaining = 0
        self._crc_low   = 0

    def push(self, data: bytes | bytearray) -> None:
        """Feed raw bytes into the parser."""
        for byte in data:
            self._feed(byte)

    def _feed(self, b: int) -> None:
        s = self._state

        if s == self._STATE_WAIT_SOF1:
            if b == SOF1:
                self._buf = bytearray([b])
                self._state = self._STATE_WAIT_SOF2

        elif s == self._STATE_WAIT_SOF2:
            if b == SOF2:
                self._buf.append(b)
                self._state = self._STATE_HEADER
            else:
                self._reset()

        elif s == self._STATE_HEADER:
            self._buf.append(b)
            if len(self._buf) == HEADER_SIZE:
                # buf: [SOF1, SOF2, VER, TYPE, FLAGS, SEQ, LEN_L, LEN_H]
                payload_len = self._buf[6] | (self._buf[7] << 8)
                if payload_len > MAX_PAYLOAD:
                    self._reset()
                    return
                self._payload_remaining = payload_len
                self._payload = bytearray()
                if payload_len == 0:
                    self._state = self._STATE_CRC_L
                else:
                    self._state = self._STATE_PAYLOAD

        elif s == self._STATE_PAYLOAD:
            self._payload.append(b)
            self._payload_remaining -= 1
            if self._payload_remaining == 0:
                self._state = self._STATE_CRC_L

        elif s == self._STATE_CRC_L:
            self._crc_low = b
            self._state = self._STATE_CRC_H

        elif s == self._STATE_CRC_H:
            received_crc = self._crc_low | (b << 8)
            self._state = self._STATE_EOF
            # Compute expected CRC over VER..PAYLOAD (skip SOF1, SOF2)
            crc_data = bytes(self._buf[2:]) + bytes(self._payload)
            expected_crc = crc16_ccitt(crc_data)
            if received_crc != expected_crc:
                self.crc_errors += 1
                self._reset()
                return
            # stash for EOF check
            self._pending_ver    = self._buf[2]
            self._pending_type   = self._buf[3]
            self._pending_flags  = self._buf[4]
            self._pending_seq    = self._buf[5]
            self._pending_payload = bytes(self._payload)

        elif s == self._STATE_EOF:
            if b == EOF_BYTE:
                pkt = Packet(
                    ver=self._pending_ver,
                    type=self._pending_type,
                    flags=self._pending_flags,
                    seq=self._pending_seq,
                    payload=self._pending_payload,
                )
                self.packets.append(pkt)
            else:
                self.crc_errors += 1  # malformed frame end
            self._reset()

    def pop_packets(self) -> list[Packet]:
        """Return and clear the accumulated packet list."""
        pkts = self.packets
        self.packets = []
        return pkts


# ── Convenience payload builders ─────────────────────────────────────────────
def make_ping() -> bytes:
    return encode_packet(MsgType.PING)


def make_get_device_info() -> bytes:
    return encode_packet(MsgType.GET_DEVICE_INFO)


def make_get_parameter_table() -> bytes:
    return encode_packet(MsgType.GET_PARAMETER_TABLE)


def make_read_parameter(param_id: int) -> bytes:
    return encode_packet(MsgType.READ_PARAMETER, struct.pack("<H", param_id))


def make_write_parameter(param_id: int, raw_value: bytes) -> bytes:
    return encode_packet(MsgType.WRITE_PARAMETER,
                         struct.pack("<H", param_id) + raw_value)


def make_save_parameters() -> bytes:
    return encode_packet(MsgType.SAVE_PARAMETERS)


def make_load_parameters(profile_slot: int = 0) -> bytes:
    return encode_packet(MsgType.LOAD_PARAMETERS, struct.pack("<B", profile_slot))


def make_set_stream_config(stream_id: int, enable: bool, period_ms: int) -> bytes:
    return encode_packet(MsgType.SET_STREAM_CONFIG,
                         struct.pack("<BBH", stream_id, int(enable), period_ms))


def make_set_control_mode(mode: int) -> bytes:
    return encode_packet(MsgType.SET_CONTROL_MODE, struct.pack("<B", mode))


def make_set_manual_command(forward: float, turn: float) -> bytes:
    return encode_packet(MsgType.SET_MANUAL_COMMAND, struct.pack("<ff", forward, turn))


def make_emergency_stop(reason: int = 0) -> bytes:
    return encode_packet(MsgType.EMERGENCY_STOP, struct.pack("<B", reason))


def make_clear_fault() -> bytes:
    return encode_packet(MsgType.CLEAR_FAULT)


def make_start_test(test_id: int, args: bytes = b"") -> bytes:
    return encode_packet(MsgType.START_TEST, struct.pack("<B", test_id) + args)


def make_stop_test() -> bytes:
    return encode_packet(MsgType.STOP_TEST)


def make_capture_arm() -> bytes:
    return encode_packet(MsgType.CAPTURE_ARM)


def make_capture_config(trigger: int, signal_mask: int,
                        pre_samples: int, post_samples: int) -> bytes:
    return encode_packet(MsgType.CAPTURE_CONFIG,
                         struct.pack("<BBHH", trigger, signal_mask,
                                     pre_samples, post_samples))
