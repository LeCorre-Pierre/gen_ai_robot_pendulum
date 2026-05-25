"""
RobotClient — serial connection + command API.

RX runs in a daemon thread that assembles VCP frames and dispatches them to
typed queues.  All public methods are blocking and safe to call from any thread
or from asyncio via run_in_executor.
"""

from __future__ import annotations
import threading
import queue
import time
import serial
from . import protocol as P


class RobotClient:
    def __init__(self, port: str, baud: int = 115200, ack_timeout: float = 2.0):
        self.port        = port
        self.baud        = baud
        self.ack_timeout = ack_timeout
        self._ser: serial.Serial | None = None
        self._tel_q: queue.Queue[P.TelemetryPID] = queue.Queue(maxsize=4000)
        self._ack_q: queue.Queue[int]             = queue.Queue(maxsize=32)
        self._seq    = 0
        self._lock   = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    # ── Connection ─────────────────────────────────────────────────────────────

    def connect(self) -> None:
        self._ser = serial.Serial(self.port, self.baud, timeout=0.05)
        self._running = True
        self._thread = threading.Thread(target=self._reader, daemon=True, name="vcp-rx")
        self._thread.start()

    def disconnect(self) -> None:
        self._running = False
        if self._ser and self._ser.is_open:
            self._ser.close()

    def is_connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    # ── Commands ───────────────────────────────────────────────────────────────

    def set_gains(self, motor: str | int, kp: float, ki: float, kd: float = 0.0) -> bool:
        return self._send_ack(P.make_set_gains(P.motor_id(motor), kp, ki, kd))

    def set_setpoint(self, rpm: int) -> bool:
        return self._send_ack(P.make_set_sp(rpm))

    def start_stream(self, rate_hz: int = 50) -> bool:
        return self._send_ack(P.make_stream_ctrl(True, rate_hz))

    def stop_stream(self) -> bool:
        return self._send_ack(P.make_stream_ctrl(False, 0))

    def motor_coast(self) -> bool:
        return self._send_ack(P.make_motor_ctrl(P.ACTION_COAST))

    def motor_brake(self) -> bool:
        return self._send_ack(P.make_motor_ctrl(P.ACTION_BRAKE))

    def motor_enable(self) -> bool:
        return self._send_ack(P.make_motor_ctrl(P.ACTION_ENABLE))

    # ── Telemetry ──────────────────────────────────────────────────────────────

    def drain_telemetry(self) -> None:
        while not self._tel_q.empty():
            try:
                self._tel_q.get_nowait()
            except queue.Empty:
                break

    def get_telemetry(self, timeout: float = 0.2) -> P.TelemetryPID | None:
        try:
            return self._tel_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def record_telemetry(self, duration_s: float) -> list[P.TelemetryPID]:
        """Collect all telemetry frames arriving in the next duration_s seconds."""
        samples: list[P.TelemetryPID] = []
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            tel = self.get_telemetry(timeout=min(0.05, remaining))
            if tel is not None:
                samples.append(tel)
        return samples

    # ── Private ────────────────────────────────────────────────────────────────

    def _send_ack(self, pkt: P.Packet) -> bool:
        with self._lock:
            pkt.seq = self._seq & 0xFF
            self._seq += 1
            frame = P.encode(pkt)
            self._ser.write(frame)

        deadline = time.monotonic() + self.ack_timeout
        while time.monotonic() < deadline:
            try:
                ack_cmd = self._ack_q.get(timeout=0.05)
                if ack_cmd == pkt.type:
                    return True
            except queue.Empty:
                pass
        return False

    def _dispatch(self, pkt: P.Packet) -> None:
        if pkt.type == P.TYPE_TELEMETRY_PID:
            tel = P.parse_telemetry(pkt)
            if tel is not None:
                try:
                    self._tel_q.put_nowait(tel)
                except queue.Full:
                    # Drop oldest sample to make room
                    try:
                        self._tel_q.get_nowait()
                        self._tel_q.put_nowait(tel)
                    except queue.Empty:
                        pass
        elif pkt.type == P.TYPE_ACK and len(pkt.payload) >= 1:
            try:
                self._ack_q.put_nowait(pkt.payload[0])
            except queue.Full:
                pass

    def _reader(self) -> None:
        """Daemon thread: read bytes, assemble frames, dispatch."""
        buf = bytearray()
        state = 'SOF1'
        frame_total = 0

        while self._running:
            try:
                chunk = self._ser.read(64)
            except serial.SerialException:
                break

            for b in chunk:
                if state == 'SOF1':
                    if b == P.SOF1:
                        buf = bytearray([b])
                        state = 'SOF2'

                elif state == 'SOF2':
                    if b == P.SOF2:
                        buf.append(b)
                        frame_total = 0
                        state = 'BODY'
                    else:
                        state = 'SOF1'
                        buf.clear()

                elif state == 'BODY':
                    buf.append(b)
                    if len(buf) == 8 and frame_total == 0:
                        plen = buf[6] | (buf[7] << 8)
                        frame_total = 11 + plen
                        if frame_total > 128:    # sanity guard
                            state = 'SOF1'
                            buf.clear()
                            frame_total = 0
                            continue
                    if frame_total > 0 and len(buf) == frame_total:
                        pkt = P.decode(bytes(buf))
                        if pkt is not None:
                            self._dispatch(pkt)
                        state = 'SOF1'
                        buf.clear()
                        frame_total = 0
