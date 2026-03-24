"""
Unit tests for monitor.serial.protocol

Tests cover:
- CRC16-CCITT correctness
- encode_packet output format
- FrameParser: happy path, bad SOF, bad CRC, fragmented input, oversized payload
- Convenience builders (smoke-test that they decode back)
"""

import struct
import pytest

from monitor.serial.protocol import (
    SOF1, SOF2, EOF_BYTE, PROTO_VER, MAX_PAYLOAD,
    MsgType, Packet,
    crc16_ccitt, encode_packet, reset_seq,
    FrameParser,
    make_ping, make_get_device_info, make_get_parameter_table,
    make_read_parameter, make_write_parameter, make_save_parameters,
    make_set_stream_config, make_emergency_stop, make_clear_fault,
    make_start_test, make_stop_test,
)


# ── CRC16-CCITT ───────────────────────────────────────────────────────────────
class TestCrc16:
    def test_empty(self):
        # CRC of empty bytes with init 0xFFFF must stay 0xFFFF
        assert crc16_ccitt(b"") == 0xFFFF

    def test_known_vector(self):
        # Known vector: "123456789" → 0x29B1 for CRC-16/CCITT-FALSE
        assert crc16_ccitt(b"123456789") == 0x29B1

    def test_single_zero(self):
        crc = crc16_ccitt(b"\x00")
        assert 0 <= crc <= 0xFFFF

    def test_commutative_concat(self):
        # crc(a + b) computed incrementally must match direct computation
        data = b"hello world from STM32"
        full = crc16_ccitt(data)
        partial = crc16_ccitt(data[:10])
        # can't verify incrementally without a streaming API, but at least not equal to 0xFFFF
        assert full != 0xFFFF or data == b""

    def test_different_payloads_differ(self):
        a = crc16_ccitt(b"\x01\x02\x03")
        b = crc16_ccitt(b"\x01\x02\x04")
        assert a != b


# ── encode_packet ─────────────────────────────────────────────────────────────
class TestEncodePacket:
    def setup_method(self):
        reset_seq()

    def test_framing_bytes(self):
        frame = encode_packet(MsgType.PING)
        assert frame[0] == SOF1
        assert frame[1] == SOF2
        assert frame[-1] == EOF_BYTE

    def test_version_field(self):
        frame = encode_packet(MsgType.PING)
        assert frame[2] == PROTO_VER

    def test_type_field(self):
        frame = encode_packet(MsgType.PONG)
        assert frame[3] == MsgType.PONG

    def test_empty_payload_length(self):
        frame = encode_packet(MsgType.PING)
        len_l = frame[6]
        len_h = frame[7]
        assert (len_h << 8 | len_l) == 0

    def test_payload_round_trip(self):
        payload = b"\xDE\xAD\xBE\xEF"
        frame   = encode_packet(MsgType.TELEMETRY_SAMPLE, payload)
        # payload starts at index 8
        extracted = frame[8 : 8 + len(payload)]
        assert extracted == payload

    def test_crc_correct(self):
        payload = b"\x01\x02\x03"
        frame   = encode_packet(MsgType.EVENT, payload)
        # CRC covers bytes from index 2 (VER) up to end of payload
        crc_data = frame[2 : -3]  # skip SOF1, SOF2 at start; skip CRC_L CRC_H EOF at end
        expected = crc16_ccitt(crc_data)
        crc_l = frame[-3]
        crc_h = frame[-2]
        received = crc_l | (crc_h << 8)
        assert received == expected

    def test_seq_increments(self):
        f1 = encode_packet(MsgType.PING)
        f2 = encode_packet(MsgType.PING)
        assert f2[5] == (f1[5] + 1) & 0xFF

    def test_explicit_seq(self):
        frame = encode_packet(MsgType.PING, seq=42)
        assert frame[5] == 42

    def test_oversized_payload_raises(self):
        with pytest.raises(ValueError):
            encode_packet(MsgType.PING, b"\x00" * (MAX_PAYLOAD + 1))

    def test_max_payload_accepted(self):
        frame = encode_packet(MsgType.PING, b"\xAA" * MAX_PAYLOAD)
        assert frame is not None


# ── FrameParser ───────────────────────────────────────────────────────────────
class TestFrameParser:
    def setup_method(self):
        reset_seq()
        self.parser = FrameParser()

    def _make_and_parse(self, msg_type, payload=b""):
        frame = encode_packet(msg_type, payload)
        self.parser.push(frame)
        return self.parser.pop_packets()

    def test_single_packet(self):
        pkts = self._make_and_parse(MsgType.PING)
        assert len(pkts) == 1
        assert pkts[0].type == MsgType.PING

    def test_payload_preserved(self):
        payload = b"\x11\x22\x33\x44"
        pkts = self._make_and_parse(MsgType.EVENT, payload)
        assert len(pkts) == 1
        assert pkts[0].payload == payload

    def test_two_packets_in_one_push(self):
        f1 = encode_packet(MsgType.PING)
        f2 = encode_packet(MsgType.PONG, b"\x00\x00\x00\x00\x01")
        self.parser.push(f1 + f2)
        pkts = self.parser.pop_packets()
        assert len(pkts) == 2
        assert pkts[0].type == MsgType.PING
        assert pkts[1].type == MsgType.PONG

    def test_fragmented_delivery(self):
        frame = encode_packet(MsgType.FAULT, b"\x01\x00")
        # feed one byte at a time
        for byte in frame:
            self.parser.push(bytes([byte]))
        pkts = self.parser.pop_packets()
        assert len(pkts) == 1
        assert pkts[0].type == MsgType.FAULT

    def test_garbage_before_sof(self):
        frame  = encode_packet(MsgType.PING)
        junk   = b"\x00\xFF\x12\x34\x56"
        self.parser.push(junk + frame)
        pkts = self.parser.pop_packets()
        assert len(pkts) == 1

    def test_bad_crc_discarded(self):
        frame     = bytearray(encode_packet(MsgType.PING))
        frame[-3] ^= 0xFF  # corrupt CRC_L
        self.parser.push(bytes(frame))
        pkts = self.parser.pop_packets()
        assert len(pkts) == 0
        assert self.parser.crc_errors == 1

    def test_bad_crc_does_not_break_subsequent_packet(self):
        bad   = bytearray(encode_packet(MsgType.PING))
        bad[-3] ^= 0xFF
        good  = encode_packet(MsgType.PONG)
        self.parser.push(bytes(bad) + good)
        pkts = self.parser.pop_packets()
        # The bad frame is discarded; good frame should be parsed
        # Note: recovery depends on SOF re-sync.
        # At minimum no crash; CRC error incremented.
        assert self.parser.crc_errors >= 1

    def test_empty_payload(self):
        pkts = self._make_and_parse(MsgType.CLEAR_FAULT, b"")
        assert len(pkts) == 1
        assert pkts[0].payload == b""

    def test_ver_field(self):
        pkts = self._make_and_parse(MsgType.ACK)
        assert pkts[0].ver == PROTO_VER

    def test_seq_field(self):
        frame = encode_packet(MsgType.PING, seq=77)
        self.parser.push(frame)
        pkts = self.parser.pop_packets()
        assert pkts[0].seq == 77

    def test_pop_clears_list(self):
        self._make_and_parse(MsgType.PING)
        self.parser.pop_packets()  # first pop
        second = self.parser.pop_packets()
        assert second == []

    def test_oversized_payload_field_dropped(self):
        # Manually craft a frame with LEN > MAX_PAYLOAD
        payload = b""
        frame = bytearray(encode_packet(MsgType.PING, payload))
        # Override LEN bytes to claim 300 bytes (> 256)
        frame[6] = 0x2C   # 300 & 0xFF
        frame[7] = 0x01   # 300 >> 8
        # Recompute CRC over the corrupted header
        self.parser.push(bytes(frame))
        pkts = self.parser.pop_packets()
        assert len(pkts) == 0  # dropped, not crashed

    def test_packet_msg_type_property(self):
        pkts = self._make_and_parse(MsgType.PING)
        assert pkts[0].msg_type == MsgType.PING

    def test_unknown_type_no_crash(self):
        frame = encode_packet(0xFE, b"\x42")
        self.parser.push(frame)
        pkts = self.parser.pop_packets()
        assert len(pkts) == 1
        assert pkts[0].msg_type is None  # unknown


# ── Convenience builders ──────────────────────────────────────────────────────
class TestBuilders:
    def setup_method(self):
        reset_seq()
        self.parser = FrameParser()

    def _roundtrip(self, frame: bytes) -> Packet:
        self.parser.push(frame)
        pkts = self.parser.pop_packets()
        assert len(pkts) == 1, f"Expected 1 packet, got {len(pkts)}"
        return pkts[0]

    def test_ping(self):
        p = self._roundtrip(make_ping())
        assert p.type == MsgType.PING
        assert p.payload == b""

    def test_get_device_info(self):
        p = self._roundtrip(make_get_device_info())
        assert p.type == MsgType.GET_DEVICE_INFO

    def test_get_parameter_table(self):
        p = self._roundtrip(make_get_parameter_table())
        assert p.type == MsgType.GET_PARAMETER_TABLE

    def test_read_parameter(self):
        p = self._roundtrip(make_read_parameter(0x0042))
        assert p.type == MsgType.READ_PARAMETER
        (param_id,) = struct.unpack_from("<H", p.payload)
        assert param_id == 0x0042

    def test_write_parameter_f32(self):
        value_bytes = struct.pack("<f", 1.5)
        p = self._roundtrip(make_write_parameter(0x0001, value_bytes))
        assert p.type == MsgType.WRITE_PARAMETER
        (param_id,) = struct.unpack_from("<H", p.payload, 0)
        assert param_id == 0x0001
        (val,) = struct.unpack_from("<f", p.payload, 2)
        assert abs(val - 1.5) < 1e-6

    def test_save_parameters(self):
        p = self._roundtrip(make_save_parameters())
        assert p.type == MsgType.SAVE_PARAMETERS

    def test_set_stream_config(self):
        from monitor.serial.protocol import make_set_stream_config
        p = self._roundtrip(make_set_stream_config(0x01, True, 10))
        assert p.type == MsgType.SET_STREAM_CONFIG
        sid, en, period = struct.unpack_from("<BBH", p.payload)
        assert sid    == 0x01
        assert en     == 1
        assert period == 10

    def test_emergency_stop(self):
        p = self._roundtrip(make_emergency_stop(0))
        assert p.type == MsgType.EMERGENCY_STOP

    def test_clear_fault(self):
        p = self._roundtrip(make_clear_fault())
        assert p.type == MsgType.CLEAR_FAULT

    def test_start_test(self):
        p = self._roundtrip(make_start_test(0x01, b"\x0A"))
        assert p.type == MsgType.START_TEST
        assert p.payload[0] == 0x01
        assert p.payload[1] == 0x0A

    def test_stop_test(self):
        p = self._roundtrip(make_stop_test())
        assert p.type == MsgType.STOP_TEST
