"""
Protocol unit tests — run without physical hardware.
Verify that Python framing matches the STM32 vcp_protocol.c implementation.
"""

import struct
import pytest
from pid_tuner import protocol as P


# ── CRC16-CCITT ───────────────────────────────────────────────────────────────

def test_crc16_known_values():
    # "123456789" → 0x29B1  (standard CRC16-CCITT test vector)
    assert P.crc16(b"123456789") == 0x29B1

def test_crc16_empty():
    assert P.crc16(b"") == 0xFFFF

def test_crc16_single_byte():
    crc = P.crc16(bytes([0xAA]))
    assert isinstance(crc, int)
    assert 0 <= crc <= 0xFFFF


# ── Frame encode / decode round-trip ──────────────────────────────────────────

def test_encode_decode_roundtrip():
    pkt = P.Packet(type=P.TYPE_CMD_SET_SP, flags=0, seq=42, payload=b"\x32\x00")
    frame = P.encode(pkt)
    recovered = P.decode(frame)
    assert recovered is not None
    assert recovered.type    == pkt.type
    assert recovered.flags   == pkt.flags
    assert recovered.seq     == pkt.seq
    assert recovered.payload == pkt.payload

def test_encode_has_correct_delimiters():
    pkt = P.Packet(type=0x21, flags=0, seq=0, payload=b"\x00\x00")
    frame = P.encode(pkt)
    assert frame[0] == P.SOF1
    assert frame[1] == P.SOF2
    assert frame[-1] == P.EOF

def test_decode_bad_crc_returns_none():
    pkt = P.Packet(type=0x21, flags=0, seq=0, payload=b"\x01\x02")
    frame = bytearray(P.encode(pkt))
    frame[-2] ^= 0xFF     # corrupt CRC
    assert P.decode(bytes(frame)) is None

def test_decode_bad_eof_returns_none():
    pkt = P.Packet(type=0x21, flags=0, seq=0, payload=b"\x01\x02")
    frame = bytearray(P.encode(pkt))
    frame[-1] = 0x00      # corrupt EOF
    assert P.decode(bytes(frame)) is None

def test_decode_too_short_returns_none():
    assert P.decode(b"\xAA\x55") is None


# ── Command builders ───────────────────────────────────────────────────────────

def test_make_set_gains_payload_size():
    pkt = P.make_set_gains(P.MOTOR_LEFT, 0.004, 0.002, 0.0)
    assert len(pkt.payload) == 13          # uint8 + 3×float

def test_make_set_gains_values():
    kp, ki, kd = 0.005, 0.003, 0.001
    pkt = P.make_set_gains(P.MOTOR_BOTH, kp, ki, kd)
    motor_id, kp_r, ki_r, kd_r = struct.unpack('<Bfff', pkt.payload)
    assert motor_id == P.MOTOR_BOTH
    assert abs(kp_r - kp) < 1e-6
    assert abs(ki_r - ki) < 1e-6

def test_make_set_sp_payload():
    pkt = P.make_set_sp(75)
    (val,) = struct.unpack('<h', pkt.payload)
    assert val == 75

def test_make_set_sp_negative():
    pkt = P.make_set_sp(-100)
    (val,) = struct.unpack('<h', pkt.payload)
    assert val == -100

def test_make_stream_ctrl_enable():
    pkt = P.make_stream_ctrl(True, 50)
    en, rate = struct.unpack('<BH', pkt.payload)
    assert en == 1
    assert rate == 50

def test_make_stream_ctrl_disable():
    pkt = P.make_stream_ctrl(False, 0)
    en, rate = struct.unpack('<BH', pkt.payload)
    assert en == 0

def test_make_motor_ctrl_coast():
    pkt = P.make_motor_ctrl(P.ACTION_COAST)
    assert pkt.payload == bytes([P.ACTION_COAST])


# ── Telemetry parser ───────────────────────────────────────────────────────────

def _build_tel_payload(ts=1000, sp=50, pv_l=48, pv_r=47,
                        err_l=2, err_r=3, pwm_l=45, pwm_r=43):
    return struct.pack('<Ihhhhhhh', ts, sp, pv_l, pv_r, err_l, err_r, pwm_l, pwm_r)

def test_parse_telemetry_values():
    payload = _build_tel_payload()
    pkt = P.Packet(type=P.TYPE_TELEMETRY_PID, flags=0, seq=0, payload=payload)
    tel = P.parse_telemetry(pkt)
    assert tel is not None
    assert tel.timestamp_ms == 1000
    assert tel.sp_rpm       == 50
    assert tel.pv_l_rpm     == 48
    assert tel.pv_r_rpm     == 47
    assert tel.err_l        == 2
    assert tel.err_r        == 3
    assert abs(tel.pwm_l_pct - 0.45) < 0.01
    assert abs(tel.pwm_r_pct - 0.43) < 0.01

def test_parse_telemetry_wrong_type_returns_none():
    payload = _build_tel_payload()
    pkt = P.Packet(type=P.TYPE_ACK, flags=0, seq=0, payload=payload)
    assert P.parse_telemetry(pkt) is None

def test_parse_telemetry_too_short_returns_none():
    pkt = P.Packet(type=P.TYPE_TELEMETRY_PID, flags=0, seq=0, payload=b"\x00" * 4)
    assert P.parse_telemetry(pkt) is None


# ── motor_id helper ───────────────────────────────────────────────────────────

def test_motor_id_strings():
    assert P.motor_id("left")  == P.MOTOR_LEFT
    assert P.motor_id("RIGHT") == P.MOTOR_RIGHT
    assert P.motor_id("both")  == P.MOTOR_BOTH

def test_motor_id_int_passthrough():
    assert P.motor_id(0) == 0
    assert P.motor_id(1) == 1

def test_motor_id_unknown_raises():
    with pytest.raises(KeyError):
        P.motor_id("center")
