"""
Connection state machine and session coordinator.

Owns the SerialReaderThread and routes decoded packets to the
appropriate model/panel via Qt signals.
"""

from __future__ import annotations

import struct
import time
from enum import Enum

from PySide6.QtCore import QObject, Signal, QTimer

from monitor.serial.protocol import (
    MsgType, Packet,
    make_ping, make_get_device_info, make_get_parameter_table,
    make_set_stream_config, make_write_parameter, make_save_parameters,
    make_load_parameters, make_set_control_mode, make_set_manual_command,
    make_emergency_stop, make_clear_fault, make_start_test, make_stop_test,
    make_capture_arm, make_capture_config,
)
from monitor.serial.reader_thread import SerialReaderThread
from monitor.model.telemetry import TelemetryDecoder, STREAM_DEFS
from monitor.model.parameters import ParameterModel


# ── Device modes (matches firmware) ──────────────────────────────────────────
class DeviceMode(Enum):
    BOOT        = 0
    IDLE        = 1
    ARMED       = 2
    BALANCING   = 3
    FAULT       = 4
    CALIBRATION = 5
    TEST        = 6
    UNKNOWN     = 255

    @classmethod
    def from_int(cls, v: int) -> "DeviceMode":
        try:
            return cls(v)
        except ValueError:
            return cls.UNKNOWN


# ── Fault names ───────────────────────────────────────────────────────────────
FAULT_NAMES: dict[int, str] = {
    0x0001: "FAULT_TILT_LIMIT",
    0x0002: "FAULT_OVERCURRENT_LEFT",
    0x0003: "FAULT_OVERCURRENT_RIGHT",
    0x0004: "FAULT_IMU_TIMEOUT",
    0x0005: "FAULT_IMU_DATA_INVALID",
    0x0006: "FAULT_CONTROL_OVERRUN",
    0x0007: "FAULT_WATCHDOG_PRE_RESET",
    0x0008: "FAULT_PARAM_OUT_OF_RANGE",
    0x0009: "FAULT_MOTOR_DRIVER_INHIBITED",
    0x000A: "FAULT_COMMAND_TIMEOUT",
}

EVENT_NAMES: dict[int, str] = {
    0x0101: "EVENT_BOOT_COMPLETE",
    0x0102: "EVENT_MODE_CHANGED",
    0x0103: "EVENT_PARAMETER_CHANGED",
    0x0104: "EVENT_PARAMETERS_SAVED",
    0x0105: "EVENT_CAPTURE_READY",
    0x0106: "EVENT_STREAM_OVERRUN",
}


# ── Connection states ─────────────────────────────────────────────────────────
class ConnectionState(Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING   = "CONNECTING"
    CONNECTED    = "CONNECTED"


# ── NACK error code table ─────────────────────────────────────────────────────
# These are best-guess names based on common embedded protocol conventions.
# The firmware team should confirm / correct these definitions.
_NACK_ERROR_NAMES: dict[int, str] = {
    0x01: "ERR_UNKNOWN_TYPE",
    0x02: "ERR_INVALID_LENGTH",
    0x03: "ERR_INVALID_STATE",     # device not in a mode that accepts this command
    0x04: "ERR_NOT_READY",         # subsystem not initialised yet, or busy
    0x05: "ERR_INVALID_PARAM",     # parameter value out of range or unknown ID
    0x06: "ERR_ACCESS_DENIED",     # read-only parameter or protected command
    0x07: "ERR_CHECKSUM",
    0x08: "ERR_TIMEOUT",
    0x09: "ERR_OVERFLOW",
    0xFF: "ERR_GENERIC",
}


def _nack_context(nacked_type: int, error_code: int) -> str:
    """Return a human-readable hint for the firmware team based on cmd + error."""
    if nacked_type == MsgType.SET_STREAM_CONFIG:
        if error_code == 0x03:
            return ("Device is not in a state that accepts stream config. "
                    "Expected: IDLE, ARMED or BALANCING. "
                    "Ask firmware: what mode is required for SET_STREAM_CONFIG?")
        if error_code == 0x04:
            return ("Device returned NOT_READY for SET_STREAM_CONFIG. "
                    "Possible causes: (1) stream subsystem not yet initialised, "
                    "(2) unsupported stream ID, "
                    "(3) period value rejected. "
                    "PC sent: stream_id=0x02  enable=1  period_ms=20. "
                    "Ask firmware: what stream IDs and periods are supported?")
        if error_code == 0x05:
            return ("Invalid parameter in SET_STREAM_CONFIG. "
                    "PC payload was: stream_id(u8) enable(u8) period_ms(u16 LE). "
                    "Ask firmware: confirm payload layout and valid stream IDs.")
    if nacked_type == MsgType.GET_PARAMETER_TABLE:
        return "Firmware does not support GET_PARAMETER_TABLE in current state."
    if nacked_type == MsgType.WRITE_PARAMETER:
        return ("Parameter write rejected. "
                "Check: parameter is writable, value within min/max, correct mode.")
    return ""


# ── Session ────────────────────────────────────────────────────────────────────
class Session(QObject):
    """
    Signals emitted to the UI:
    - connection_state_changed(ConnectionState)
    - device_mode_changed(DeviceMode)
    - fault_changed(int, str)          # (code, name), code=0 means cleared
    - uptime_ms_changed(int)
    - telemetry_sample(int, dict)      # (stream_id, {name: value})
    - event_received(int, str, bytes)  # (code, name, raw_context)
    - fault_received(int, str, bytes)  # (code, name, raw_payload)
    - log_received(int, int, int, str) # (timestamp_ms, level, module, text)
    - parameter_value(int, float)      # (param_id, value)
    - parameter_table_received(list)   # list[ParameterDescriptor]
    - crc_errors_changed(int)
    - capture_status_changed(str)      # "IDLE" | "ARMED" | "TRIGGERED" | "DONE"
    - capture_data_chunk(bytes)
    """

    connection_state_changed   = Signal(object)   # ConnectionState
    device_mode_changed        = Signal(object)   # DeviceMode
    fault_changed              = Signal(int, str)
    uptime_ms_changed          = Signal(object)   # Python int, u32 range
    firmware_info              = Signal(dict)
    telemetry_sample           = Signal(int, dict)
    event_received             = Signal(int, str, bytes)
    fault_received             = Signal(int, str, bytes)
    log_received               = Signal(int, int, int, str)
    parameter_value            = Signal(int, float)
    crc_errors_changed         = Signal(int)
    capture_status_changed     = Signal(str)
    capture_data_chunk         = Signal(bytes)
    pong_received              = Signal(int)   # round-trip latency ms
    rx_activity                = Signal(int)   # cumulative RX bytes

    def __init__(self, param_model: ParameterModel, parent=None) -> None:
        super().__init__(parent)
        self._param_model = param_model
        self._decoder     = TelemetryDecoder()
        self._reader:     SerialReaderThread | None = None
        self._state       = ConnectionState.DISCONNECTED
        self._mode        = DeviceMode.UNKNOWN

        # Ping retry timer (connection startup — fires once after 200 ms)
        self._ping_timer = QTimer(self)
        self._ping_timer.setSingleShot(True)
        self._ping_timer.timeout.connect(self._on_ping_timeout)

        # Keepalive: periodic PING every 5 s once connected
        _KEEPALIVE_INTERVAL_MS = 5_000
        self._keepalive_timer = QTimer(self)
        self._keepalive_timer.setInterval(_KEEPALIVE_INTERVAL_MS)
        self._keepalive_timer.timeout.connect(self._on_keepalive_tick)

        # Keepalive PONG watchdog: if no PONG within 3 s of a keepalive PING → link dead
        _KEEPALIVE_PONG_TIMEOUT_MS = 3_000
        self._keepalive_pong_timer = QTimer(self)
        self._keepalive_pong_timer.setSingleShot(True)
        self._keepalive_pong_timer.setInterval(_KEEPALIVE_PONG_TIMEOUT_MS)
        self._keepalive_pong_timer.timeout.connect(self._on_keepalive_timeout)

        # Manual ping tracking
        self._ping_sent_at: float | None = None
        self._keepalive_pending: bool = False

        # Telemetry sample counters per stream (for log rate limiting)
        self._telem_counts: dict[int, int] = {}

        self._param_model.parameter_write_requested.connect(
            self._on_parameter_write_requested
        )

    # ── Public API ────────────────────────────────────────────────────────────
    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def mode(self) -> DeviceMode:
        return self._mode

    def connect(self, port: str, baud: int) -> None:
        if self._reader is not None:
            self._teardown_reader()
        self._set_state(ConnectionState.CONNECTING)
        self._reader = SerialReaderThread(port, baud)
        self._reader.packet_received.connect(self._on_packet)
        self._reader.link_lost.connect(self._on_link_lost)
        self._reader.crc_error_count_changed.connect(self.crc_errors_changed)
        self._reader.bytes_received.connect(self.rx_activity)
        self._reader.raw_chunk.connect(self._on_raw_chunk)
        self._reader.start()

        self._log(2, "COMM", f"Port opened: {port}  baud={baud}")
        self._log(2, "COMM", "Waiting 200 ms before first PING…")
        # Send PING after a short delay to allow the port to settle
        self._ping_timer.start(200)

    def disconnect(self) -> None:
        self._ping_timer.stop()
        self._keepalive_timer.stop()
        self._keepalive_pong_timer.stop()
        self._keepalive_pending = False
        self._teardown_reader()
        self._set_state(ConnectionState.DISCONNECTED)

    def send(self, data: bytes) -> None:
        if self._reader:
            self._reader.write(data)
            self._log_tx(data)

    def _log_tx(self, data: bytes) -> None:
        """Log every outgoing frame at DEBUG level with decoded type name."""
        if len(data) < 4:
            self._log(3, "COMM", f"TX {len(data)}B (malformed): {data.hex(' ').upper()}")
            return
        msg_type_byte = data[3]
        try:
            name = MsgType(msg_type_byte).name
        except ValueError:
            name = f"UNKNOWN_0x{msg_type_byte:02X}"
        hex_str = data.hex(" ").upper()
        self._log(3, "COMM", f"TX {len(data)}B [{name}]: {hex_str}")

    # ── Stream helpers ────────────────────────────────────────────────────────
    def enable_stream(self, stream_id: int, period_ms: int) -> None:
        from monitor.model.telemetry import STREAM_DEFS
        label = STREAM_DEFS[stream_id].label if stream_id in STREAM_DEFS else f"0x{stream_id:02X}"
        self._log(2, "COMM",
                  f"Enabling stream 0x{stream_id:02X} ({label})  period={period_ms} ms")
        self.send(make_set_stream_config(stream_id, True, period_ms))

    def disable_stream(self, stream_id: int) -> None:
        from monitor.model.telemetry import STREAM_DEFS
        label = STREAM_DEFS[stream_id].label if stream_id in STREAM_DEFS else f"0x{stream_id:02X}"
        self._log(2, "COMM", f"Disabling stream 0x{stream_id:02X} ({label})")
        self.send(make_set_stream_config(stream_id, False, 0))

    # ── Command helpers ────────────────────────────────────────────────────────
    def emergency_stop(self) -> None:
        self.send(make_emergency_stop(0))

    def set_control_mode(self, mode: int) -> None:
        self.send(make_set_control_mode(mode))

    def set_manual_command(self, forward: float, turn: float) -> None:
        self.send(make_set_manual_command(forward, turn))

    def clear_fault(self) -> None:
        self.send(make_clear_fault())

    def save_parameters(self) -> None:
        self.send(make_save_parameters())

    def load_defaults(self) -> None:
        self.send(make_load_parameters(0))

    def start_test(self, test_id: int, args: bytes = b"") -> None:
        self.send(make_start_test(test_id, args))

    def stop_test(self) -> None:
        self.send(make_stop_test())

    def send_ping(self) -> None:
        """Send a manual PING and record the send time for latency measurement."""
        self._ping_sent_at = time.monotonic()
        ping_frame = make_ping()
        self._log(2, "COMM", f"Manual PING sent: {ping_frame.hex(' ').upper()}")
        self.send(ping_frame)

    def _on_parameter_write_requested(self, param_id: int, value: float) -> None:
        node = self._param_model._id_to_node.get(param_id)
        if node is None:
            return
        try:
            raw = node.desc.encode_value(value)
            self.send(make_write_parameter(param_id, raw))
        except Exception:
            pass

    def arm_capture(self) -> None:
        self.send(make_capture_arm())

    def configure_capture(self, trigger: int, signal_mask: int,
                          pre: int, post: int) -> None:
        self.send(make_capture_config(trigger, signal_mask, pre, post))

    # ── Internal ──────────────────────────────────────────────────────────────
    def _set_state(self, s: ConnectionState) -> None:
        if s != self._state:
            self._state = s
            self.connection_state_changed.emit(s)

    def _teardown_reader(self) -> None:
        if self._reader:
            self._reader.stop()
            self._reader.wait(3000)
            self._reader = None

    def _log(self, level: int, module: str, text: str) -> None:
        """Emit a synthetic log line visible in the Log panel.
        level: 0=ERROR 1=WARN 2=INFO 3=DEBUG 4=TRACE
        module: string key matched against _MODULE_NAMES order.
        """
        _MODULE_ORDER = ["SYSTEM", "CONTROL", "IMU", "MOTOR",
                         "ENCODER", "COMM", "SAFETY", "STORAGE"]
        try:
            module_idx = _MODULE_ORDER.index(module)
        except ValueError:
            module_idx = 5  # default COMM
        ts_ms = int(time.monotonic() * 1000)
        self.log_received.emit(ts_ms, level, module_idx, text)

    def _on_raw_chunk(self, chunk: bytes) -> None:
        """Log every raw RX chunk as a hex dump at TRACE level."""
        # Detect printable ASCII in the chunk — common sign that the firmware
        # is sending plain printf/text instead of binary frames.
        try:
            text = chunk.decode("ascii")
            printable = all(0x20 <= c < 0x7F or c in (0x0A, 0x0D) for c in chunk)
        except Exception:
            printable = False
            text = ""

        hex_str = chunk.hex(" ").upper() if len(chunk) <= 64 \
                  else chunk[:64].hex(" ").upper() + f" … (+{len(chunk)-64}B)"

        if chunk.startswith(b"[DISCONNECT]"):
            # Diagnostic sentinel emitted by the reader thread on exit
            self._log(1, "COMM", chunk.decode(errors="replace"))
            return

        if printable and text.strip():
            # Firmware is sending human-readable text — very important diagnostic
            self._log(1, "COMM",
                      f"⚠ RAW ASCII from firmware ({len(chunk)}B): "
                      f"{repr(text.rstrip())}")
            self._log(1, "COMM",
                      "  → Firmware appears to be sending printf/text output. "
                      "Binary framing (SOF=0xAA 0x55) not yet active.")
        else:
            self._log(4, "COMM", f"RX {len(chunk)}B: {hex_str}")

        # Check if SOF bytes are present anywhere in the chunk
        if b"\xAA\x55" not in chunk and len(chunk) > 4:
            self._log(3, "COMM",
                      f"  → No SOF marker (AA 55) found in this chunk. "
                      f"First 4 bytes: {chunk[:4].hex(' ').upper()}")

    def _on_ping_timeout(self) -> None:
        if self._state == ConnectionState.CONNECTING:
            from monitor.serial.protocol import make_ping
            ping_frame = make_ping()
            self._log(2, "COMM",
                      f"Sending PING: {ping_frame.hex(' ').upper()}")
            self.send(ping_frame)

    def _on_keepalive_tick(self) -> None:
        if self._state != ConnectionState.CONNECTED:
            return
        if self._keepalive_pending:
            return  # previous keepalive already waiting
        self._keepalive_pending = True
        ping_frame = make_ping()
        self._log(4, "COMM", f"Keepalive PING → {ping_frame.hex(' ').upper()}")
        self.send(ping_frame)
        self._keepalive_pong_timer.start()

    def _on_keepalive_timeout(self) -> None:
        self._log(0, "COMM",
                  "Keepalive PONG not received within 3 s — link considered dead.")
        self._keepalive_pending = False
        self._on_link_lost()

    def _on_link_lost(self) -> None:
        self._log(1, "COMM", "Link lost — connection closed by serial error or keepalive timeout.")
        self._ping_timer.stop()
        self._keepalive_timer.stop()
        self._keepalive_pong_timer.stop()
        self._keepalive_pending = False
        self._teardown_reader()
        self._set_state(ConnectionState.DISCONNECTED)

    def _on_packet(self, pkt: Packet) -> None:
        mt = pkt.msg_type
        p  = pkt.payload

        if mt == MsgType.PONG:
            # Measure manual-ping latency if one was pending
            if self._ping_sent_at is not None:
                latency_ms = int((time.monotonic() - self._ping_sent_at) * 1000)
                self._ping_sent_at = None
                self.pong_received.emit(latency_ms)
                self._log(2, "COMM", f"PONG received — round-trip {latency_ms} ms")

            # Reset keepalive watchdog — any PONG counts
            self._keepalive_pong_timer.stop()
            self._keepalive_pending = False

            prev_state = self._state
            self._set_state(ConnectionState.CONNECTED)
            self._ping_timer.stop()
            if len(p) >= 4:
                uptime_ms = int(struct.unpack_from("<I", p, 0)[0])
                proto_ver = p[4] if len(p) >= 5 else None
                uptime_days = uptime_ms / 86_400_000
                pv_str = f"0x{proto_ver:02X}" if proto_ver is not None else "?"
                self._log(2, "COMM",
                          f"PONG: uptime={uptime_ms}ms ({uptime_days:.1f} days)  "
                          f"proto_ver={pv_str}  "
                          f"raw_payload={p.hex(' ').upper()}")
                if uptime_days > 7:
                    self._log(1, "COMM",
                              f"⚠ Uptime={uptime_days:.1f} days looks suspicious. "
                              "PC reads uptime as u32 LE at payload offset 0. "
                              "Ask firmware: confirm PONG payload layout "
                              "(uptime_ms u32 + proto_ver u8).")
                self.uptime_ms_changed.emit(uptime_ms)
            # On first PONG: run handshake and start keepalive
            if prev_state != ConnectionState.CONNECTED:
                self._log(2, "COMM", "Sending GET_DEVICE_INFO…")
                self.send(make_get_device_info())
                self._keepalive_timer.start()
                self._log(3, "COMM", "Keepalive PING started (every 5 s)")

        elif mt == MsgType.DEVICE_INFO:
            info = self._parse_device_info(p)
            self.firmware_info.emit(info)
            self._log(2, "COMM",
                      f"DEVICE_INFO: fw={info.get('fw_version','?')}  "
                      f"capabilities=0x{info.get('capabilities',0):04X}  "
                      f"raw={p.hex(' ').upper()}")
            self._log(2, "COMM", "Sending GET_PARAMETER_TABLE…")
            self.send(make_get_parameter_table())

        elif mt == MsgType.PARAMETER_TABLE:
            self._log(2, "COMM",
                      f"PARAMETER_TABLE received ({len(p)}B payload). "
                      "Using PC-side default descriptors.")
            # descriptors parsing is firmware-version-specific; use defaults

        elif mt == MsgType.PARAMETER_VALUE:
            if len(p) >= 3:
                param_id = struct.unpack_from("<H", p, 0)[0]
                raw_val  = p[2:]
                node = self._param_model._id_to_node.get(param_id)
                if node:
                    try:
                        value = node.desc.decode_value(raw_val)
                        self._param_model.update_from_firmware(param_id, value)
                        self.parameter_value.emit(param_id, value)
                    except Exception:
                        pass

        elif mt == MsgType.TELEMETRY_SAMPLE:
            if p:
                stream_id = p[0]
                decoded   = self._decoder.decode(stream_id, p)
                count = self._telem_counts.get(stream_id, 0) + 1
                self._telem_counts[stream_id] = count
                if decoded:
                    self.telemetry_sample.emit(stream_id, decoded)
                    # Log first sample and every 100th for each stream
                    if count == 1:
                        summary = "  ".join(
                            f"{k}={v:.3g}" for k, v in list(decoded.items())[:5]
                        )
                        self._log(2, "COMM",
                                  f"Stream 0x{stream_id:02X} first sample: {summary}")
                    elif count % 100 == 0:
                        self._log(4, "COMM",
                                  f"Stream 0x{stream_id:02X} sample #{count}")
                    # Update device mode from stream 0x01 if present
                    if stream_id == 0x01 and "mode" in decoded:
                        new_mode = DeviceMode.from_int(int(decoded["mode"]))
                        if new_mode != self._mode:
                            self._mode = new_mode
                            self.device_mode_changed.emit(new_mode)
                else:
                    if count <= 3:
                        hex_preview = p.hex(" ").upper()[:60]
                        self._log(1, "COMM",
                                  f"Stream 0x{stream_id:02X} TELEMETRY_SAMPLE decode FAILED "
                                  f"({len(p)}B). Raw: {hex_preview}")

        elif mt == MsgType.EVENT:
            if len(p) >= 2:
                code = struct.unpack_from("<H", p, 0)[0]
                name = EVENT_NAMES.get(code, f"EVENT_0x{code:04X}")
                self.event_received.emit(code, name, p[2:])
                if code == 0x0102 and len(p) >= 3:
                    self._mode = DeviceMode.from_int(p[2])
                    self.device_mode_changed.emit(self._mode)

        elif mt == MsgType.FAULT:
            if len(p) >= 2:
                code = struct.unpack_from("<H", p, 0)[0]
                name = FAULT_NAMES.get(code, f"FAULT_0x{code:04X}")
                self.fault_received.emit(code, name, p)
                self.fault_changed.emit(code, name)

        elif mt == MsgType.ACK:
            if len(p) >= 2:
                acked_type = p[0]
                acked_seq  = p[1] if len(p) >= 2 else "?"
                try:
                    type_name = MsgType(acked_type).name
                except ValueError:
                    type_name = f"0x{acked_type:02X}"
                self._log(3, "COMM", f"ACK for [{type_name}] seq={acked_seq}")
            else:
                self._log(3, "COMM", "ACK received (no payload)")

        elif mt == MsgType.NACK:
            if len(p) >= 3:
                nacked_type = p[0]
                nacked_seq  = p[1]
                error_code  = p[2]
                try:
                    type_name = MsgType(nacked_type).name
                except ValueError:
                    type_name = f"0x{nacked_type:02X}"
                err_label = _NACK_ERROR_NAMES.get(error_code,
                                                  f"UNKNOWN_0x{error_code:02X}")
                self._log(0, "COMM",
                          f"NACK  cmd=[{type_name}]  seq={nacked_seq}"
                          f"  error={error_code} ({err_label})"
                          f"  raw={p.hex(' ').upper()}")
                # Extra context per rejected command type
                extra = _nack_context(nacked_type, error_code)
                if extra:
                    self._log(0, "COMM", f"  ↳ {extra}")
                # Mark parameter NACKed if applicable
                if nacked_type == MsgType.WRITE_PARAMETER:
                    param_id = struct.unpack_from("<H", p, 1)[0]
                    self._param_model.mark_nack(param_id)
            else:
                self._log(0, "COMM",
                          f"NACK received (short payload {len(p)}B): "
                          f"{p.hex(' ').upper()}")

        elif mt == MsgType.STREAM_CONFIG:
            # Firmware confirmed stream config
            if len(p) >= 4:
                sid, enabled, period = struct.unpack_from("<BBH", p, 0)
                self._log(2, "COMM",
                          f"STREAM_CONFIG confirmed: stream=0x{sid:02X}  "
                          f"enabled={bool(enabled)}  period={period}ms")

        elif mt == MsgType.LOG_TEXT:
            self._parse_log_text(p)

        elif mt == MsgType.CAPTURE_STATUS:
            status_map = {0: "IDLE", 1: "ARMED", 2: "TRIGGERED", 3: "DONE"}
            if p:
                self.capture_status_changed.emit(status_map.get(p[0], "UNKNOWN"))

        elif mt == MsgType.CAPTURE_DATA:
            self.capture_data_chunk.emit(p)

    @staticmethod
    def _parse_device_info(p: bytes) -> dict:
        info: dict = {}
        if len(p) >= 4:
            info["fw_version"] = f"{p[0]}.{p[1]}.{p[2]}"
            info["capabilities"] = struct.unpack_from("<H", p, 3)[0] if len(p) >= 5 else 0
        return info

    def _parse_log_text(self, p: bytes) -> None:
        if len(p) < 4:
            return
        ts_ms  = struct.unpack_from("<I", p, 0)[0]
        level  = p[4] if len(p) > 4 else 0
        module = p[5] if len(p) > 5 else 0
        tlen   = p[6] if len(p) > 6 else 0
        text_bytes = p[7:7 + tlen] if len(p) >= 7 + tlen else p[7:]
        try:
            text = text_bytes.decode("utf-8", errors="replace")
        except Exception:
            text = repr(text_bytes)
        self.log_received.emit(ts_ms, level, module, text)
