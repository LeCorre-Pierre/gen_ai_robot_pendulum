"""
Unit tests for monitor.model.telemetry.TelemetryDecoder
"""

import struct
import pytest

from monitor.model.telemetry import TelemetryDecoder, STREAM_DEFS


def _pack_stream(stream_id: int, *values) -> bytes:
    """Pack values using the stream's struct format and prepend stream_id."""
    sdef = STREAM_DEFS[stream_id]
    body = struct.pack(sdef.struct_fmt, *values)
    return bytes([stream_id]) + body


class TestTelemetryDecoder:
    def setup_method(self):
        self.dec = TelemetryDecoder()

    def test_unknown_stream_returns_none(self):
        result = self.dec.decode(0xFF, b"\xFF" + b"\x00" * 64)
        assert result is None

    def test_empty_payload_returns_none(self):
        result = self.dec.decode(0x01, b"")
        assert result is None

    def test_payload_too_short_returns_none(self):
        # 1 byte (stream_id only, no body)
        result = self.dec.decode(0x01, b"\x01")
        assert result is None

    # ── Stream 0x01 — Control fast ────────────────────────────────────────────
    def test_stream_01_all_fields_decoded(self):
        vals = (
            1000,    # timestamp_ms u32
            42,      # control_cycle u32
            3,       # mode u8
            12.34,   # pitch_deg f32
            -5.67,   # pitch_rate_dps f32
            0.0,     # target_pitch_deg f32
            100.0,   # velocity_left_rpm f32
            102.0,   # velocity_right_rpm f32
            101.0,   # velocity_mean_rpm f32
            90.0,    # target_velocity_rpm f32
            0.75,    # drive_output f32
            -0.1,    # yaw_output f32
            0.80,    # motor_left_cmd f32
            0.70,    # motor_right_cmd f32
        )
        payload = _pack_stream(0x01, *vals)
        result  = self.dec.decode(0x01, payload)
        assert result is not None
        assert result["timestamp_ms"]   == pytest.approx(1000.0)
        assert result["control_cycle"]  == pytest.approx(42.0)
        assert result["mode"]           == pytest.approx(3.0)
        assert result["pitch_deg"]      == pytest.approx(12.34, rel=1e-5)
        assert result["drive_output"]   == pytest.approx(0.75, rel=1e-5)
        assert result["motor_right_cmd"] == pytest.approx(0.70, rel=1e-5)

    def test_stream_01_returns_dict_with_all_signal_names(self):
        sdef = STREAM_DEFS[0x01]
        vals = [0] * len(sdef.signals)
        payload = _pack_stream(0x01, *vals)
        result  = self.dec.decode(0x01, payload)
        for sig in sdef.signals:
            assert sig.name in result

    # ── Stream 0x02 — Sensors ─────────────────────────────────────────────────
    def test_stream_02_decoded(self):
        sdef = STREAM_DEFS[0x02]
        vals = [0] * len(sdef.signals)
        vals[7] = 5.5   # pitch_fused_deg
        payload = _pack_stream(0x02, *vals)
        result  = self.dec.decode(0x02, payload)
        assert result is not None
        assert result["pitch_fused_deg"] == pytest.approx(5.5, rel=1e-5)

    # ── Stream 0x03 — Actuators and power ─────────────────────────────────────
    def test_stream_03_battery_voltage(self):
        sdef = STREAM_DEFS[0x03]
        vals = [0] * len(sdef.signals)
        vals[3] = 11.8   # battery_v
        payload = _pack_stream(0x03, *vals)
        result  = self.dec.decode(0x03, payload)
        assert result["battery_v"] == pytest.approx(11.8, rel=1e-5)

    # ── Stream 0x04 — Runtime health ─────────────────────────────────────────
    def test_stream_04_cpu_load(self):
        sdef = STREAM_DEFS[0x04]
        vals = [0] * len(sdef.signals)
        vals[2] = 450   # cpu_load_permille (u16)
        payload = _pack_stream(0x04, *vals)
        result  = self.dec.decode(0x04, payload)
        assert result["cpu_load_permille"] == pytest.approx(450.0)

    # ── Stream 0x05 — Encoders ────────────────────────────────────────────────
    def test_stream_05_encoder_counts(self):
        sdef = STREAM_DEFS[0x05]
        vals = [0] * len(sdef.signals)
        vals[1] = -12345   # enc_left_count (i32)
        vals[2] = 99999    # enc_right_count (i32)
        payload = _pack_stream(0x05, *vals)
        result  = self.dec.decode(0x05, payload)
        assert result["enc_left_count"]  == pytest.approx(-12345.0)
        assert result["enc_right_count"] == pytest.approx(99999.0)

    # ── Signal names helper ───────────────────────────────────────────────────
    def test_signal_names_known_stream(self):
        names = self.dec.signal_names(0x01)
        assert "pitch_deg" in names
        assert "motor_left_cmd" in names

    def test_signal_names_unknown_stream(self):
        names = self.dec.signal_names(0xFF)
        assert names == []

    # ── All streams have correct struct size ──────────────────────────────────
    def test_all_stream_struct_sizes_nonzero(self):
        for sid, sdef in STREAM_DEFS.items():
            assert sdef.struct_size > 0, f"Stream 0x{sid:02X} has zero struct size"

    def test_struct_size_matches_signal_count(self):
        """Each stream's struct must have exactly len(signals) fields."""
        for sid, sdef in STREAM_DEFS.items():
            # Count format characters (skip '<')
            fmt_chars = [c for c in sdef.struct_fmt if c.isalpha()]
            assert len(fmt_chars) == len(sdef.signals), \
                f"Stream 0x{sid:02X}: {len(fmt_chars)} fmt chars but {len(sdef.signals)} signals"
