"""
Data-driven telemetry stream definitions and decoder.

Adding a new firmware stream requires only extending STREAM_DEFS.
No UI code needs to change.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


# ── Signal descriptor ────────────────────────────────────────────────────────
@dataclass
class SignalDef:
    name:    str
    unit:    str
    fmt:     str   # single struct format character, e.g. 'f', 'I', 'H', 'i', 'h', 'B'
    default_visible: bool = True
    color:   str = "#4fc3f7"  # default plot colour


# ── Stream descriptor ────────────────────────────────────────────────────────
@dataclass
class StreamDef:
    stream_id:      int
    label:          str
    default_period_ms: int
    signals:        list[SignalDef]

    @property
    def struct_fmt(self) -> str:
        return "<" + "".join(s.fmt for s in self.signals)

    @property
    def struct_size(self) -> int:
        return struct.calcsize(self.struct_fmt)


# ── Stream definitions ────────────────────────────────────────────────────────
STREAM_DEFS: dict[int, StreamDef] = {

    0x01: StreamDef(
        stream_id=0x01,
        label="Control fast",
        default_period_ms=10,
        signals=[
            SignalDef("timestamp_ms",        "ms",  "I", default_visible=False, color="#90a4ae"),
            SignalDef("control_cycle",        "",    "I", default_visible=False, color="#78909c"),
            SignalDef("mode",                 "",    "B", default_visible=False, color="#b0bec5"),
            SignalDef("pitch_deg",            "°",   "f", default_visible=True,  color="#ef5350"),
            SignalDef("pitch_rate_dps",       "°/s", "f", default_visible=False, color="#ef9a9a"),
            SignalDef("target_pitch_deg",     "°",   "f", default_visible=True,  color="#ff8a65"),
            SignalDef("velocity_left_rpm",    "rpm", "f", default_visible=False, color="#42a5f5"),
            SignalDef("velocity_right_rpm",   "rpm", "f", default_visible=False, color="#64b5f6"),
            SignalDef("velocity_mean_rpm",    "rpm", "f", default_visible=False, color="#90caf9"),
            SignalDef("target_velocity_rpm",  "rpm", "f", default_visible=False, color="#1e88e5"),
            SignalDef("drive_output",         "",    "f", default_visible=True,  color="#66bb6a"),
            SignalDef("yaw_output",           "",    "f", default_visible=False, color="#a5d6a7"),
            SignalDef("motor_left_cmd",       "",    "f", default_visible=True,  color="#ab47bc"),
            SignalDef("motor_right_cmd",      "",    "f", default_visible=True,  color="#ce93d8"),
        ],
    ),

    0x02: StreamDef(
        stream_id=0x02,
        label="Sensors",
        default_period_ms=20,
        signals=[
            SignalDef("timestamp_ms",      "ms",  "I", default_visible=False, color="#90a4ae"),
            SignalDef("acc_x_g",           "g",   "f", default_visible=False, color="#ef5350"),
            SignalDef("acc_y_g",           "g",   "f", default_visible=False, color="#ef9a9a"),
            SignalDef("acc_z_g",           "g",   "f", default_visible=False, color="#ffcdd2"),
            SignalDef("gyro_x_dps",        "°/s", "f", default_visible=True,  color="#42a5f5"),
            SignalDef("gyro_y_dps",        "°/s", "f", default_visible=False, color="#64b5f6"),
            SignalDef("gyro_z_dps",        "°/s", "f", default_visible=False, color="#90caf9"),
            SignalDef("pitch_fused_deg",   "°",   "f", default_visible=True,  color="#66bb6a"),
            SignalDef("roll_fused_deg",    "°",   "f", default_visible=True,  color="#a5d6a7"),
            SignalDef("yaw_fused_deg",     "°",   "f", default_visible=False, color="#c8e6c9"),
            SignalDef("ahrs_flags",        "",    "H", default_visible=False, color="#ffd54f"),
            SignalDef("imu_sample_age_ms", "ms",  "H", default_visible=False, color="#ffe082"),
        ],
    ),

    0x03: StreamDef(
        stream_id=0x03,
        label="Actuators and power",
        default_period_ms=20,
        signals=[
            SignalDef("timestamp_ms",           "ms", "I", default_visible=False, color="#90a4ae"),
            SignalDef("motor_left_current_a",   "A",  "f", default_visible=True,  color="#ef5350"),
            SignalDef("motor_right_current_a",  "A",  "f", default_visible=True,  color="#ff8a65"),
            SignalDef("battery_v",              "V",  "f", default_visible=True,  color="#ffee58"),
            SignalDef("left_pwm",               "",   "H", default_visible=False, color="#42a5f5"),
            SignalDef("right_pwm",              "",   "H", default_visible=False, color="#64b5f6"),
            SignalDef("left_brake",             "",   "B", default_visible=False, color="#ab47bc"),
            SignalDef("right_brake",            "",   "B", default_visible=False, color="#ce93d8"),
            SignalDef("safety_flags",           "",   "H", default_visible=False, color="#ffd54f"),
        ],
    ),

    0x04: StreamDef(
        stream_id=0x04,
        label="Runtime health",
        default_period_ms=100,
        signals=[
            SignalDef("timestamp_ms",              "ms",   "I", default_visible=False, color="#90a4ae"),
            SignalDef("uptime_ms",                 "ms",   "I", default_visible=False, color="#78909c"),
            SignalDef("cpu_load_permille",         "‰",    "H", default_visible=True,  color="#ef5350"),
            SignalDef("control_loop_period_us",    "µs",   "H", default_visible=False, color="#ffee58"),
            SignalDef("control_loop_jitter_us",    "µs",   "H", default_visible=True,  color="#ff8a65"),
            SignalDef("missed_control_deadlines",  "",     "H", default_visible=False, color="#ef9a9a"),
            SignalDef("uart_rx_overruns",          "",     "H", default_visible=False, color="#42a5f5"),
            SignalDef("uart_tx_drops",             "",     "H", default_visible=False, color="#64b5f6"),
            SignalDef("watchdog_resets",           "",     "H", default_visible=False, color="#ab47bc"),
            SignalDef("fault_code_active",         "",     "H", default_visible=False, color="#ff5252"),
        ],
    ),

    0x05: StreamDef(
        stream_id=0x05,
        label="Encoders",
        default_period_ms=20,
        signals=[
            SignalDef("timestamp_ms",     "ms",  "I", default_visible=False, color="#90a4ae"),
            SignalDef("enc_left_count",   "",    "i", default_visible=False, color="#42a5f5"),
            SignalDef("enc_right_count",  "",    "i", default_visible=False, color="#64b5f6"),
            SignalDef("enc_left_delta",   "",    "h", default_visible=False, color="#90caf9"),
            SignalDef("enc_right_delta",  "",    "h", default_visible=False, color="#bbdefb"),
            SignalDef("wheel_left_rpm",   "rpm", "f", default_visible=True,  color="#66bb6a"),
            SignalDef("wheel_right_rpm",  "rpm", "f", default_visible=True,  color="#a5d6a7"),
        ],
    ),
}


# ── Decoder ──────────────────────────────────────────────────────────────────
class TelemetryDecoder:
    """Decode raw TELEMETRY_SAMPLE payloads."""

    def decode(self, stream_id: int, payload: bytes) -> dict[str, float] | None:
        """
        Return a dict mapping signal name → float value, or None if the
        stream is unknown or the payload is too short.

        The first byte of the payload is the stream_id byte itself
        (as prepended by the firmware).
        """
        if not payload:
            return None

        # First byte: stream identifier
        sid = payload[0]
        body = payload[1:]

        sdef = STREAM_DEFS.get(sid)
        if sdef is None:
            return None

        expected = sdef.struct_size
        if len(body) < expected:
            return None

        values = struct.unpack_from(sdef.struct_fmt, body)
        return {sig.name: float(v) for sig, v in zip(sdef.signals, values)}

    def signal_names(self, stream_id: int) -> list[str]:
        sdef = STREAM_DEFS.get(stream_id)
        return [s.name for s in sdef.signals] if sdef else []
