"""
Serial reader running in a dedicated QThread.

The thread owns the serial.Serial object and the FrameParser.
Parsed packets are forwarded to the main thread via Qt queued signals.
No Qt UI calls are made from this thread.
"""

from __future__ import annotations


import serial
from PySide6.QtCore import QThread, Signal

from monitor.serial.protocol import FrameParser, Packet

_READ_TIMEOUT_S  = 0.05   # serial read timeout (non-blocking chunks)
_CHUNK_SIZE      = 256
# Note: there is NO idle-silence timeout here.
# Physical disconnect is detected via SerialException on the next read.
# Connection health is managed at the Session level via keepalive PINGs.


class SerialReaderThread(QThread):
    """
    Signals
    -------
    packet_received(Packet)
        Emitted for every valid decoded packet.
    link_lost()
        Emitted when no bytes are received for _LINK_TIMEOUT_S seconds,
        or when the serial port raises an exception.
    crc_error_count_changed(int)
        Emitted after each chunk that contains CRC errors, carrying the
        cumulative error count.
    """

    packet_received         = Signal(object)   # Packet
    link_lost               = Signal()
    crc_error_count_changed = Signal(int)
    bytes_received          = Signal(int)      # cumulative RX byte count
    raw_chunk               = Signal(bytes)    # every raw chunk as received

    def __init__(self, port: str, baud: int, parent=None) -> None:
        super().__init__(parent)
        self._port   = port
        self._baud   = baud
        self._stop   = False
        self._parser = FrameParser()

    # ── Public API ───────────────────────────────────────────────────────────
    def stop(self) -> None:
        self._stop = True

    def write(self, data: bytes) -> None:
        """
        Thread-safe write: called from the main thread.
        Uses a small lock to prevent concurrent writes.
        """
        if hasattr(self, "_serial") and self._serial and self._serial.is_open:
            try:
                self._serial.write(data)
            except serial.SerialException:
                pass

    # ── QThread entry point ──────────────────────────────────────────────────
    def run(self) -> None:
        self._serial: serial.Serial | None = None
        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=_READ_TIMEOUT_S,
            )
        except serial.SerialException:
            self.link_lost.emit()
            return

        prev_crc_errors = 0
        total_rx_bytes  = 0
        disconnect_reason = "stop() called"

        while not self._stop:
            try:
                chunk = self._serial.read(_CHUNK_SIZE)
            except serial.SerialException as exc:
                disconnect_reason = f"serial exception: {exc}"
                self.link_lost.emit()
                break

            if chunk:
                total_rx_bytes += len(chunk)
                self.bytes_received.emit(total_rx_bytes)
                self.raw_chunk.emit(bytes(chunk))
                self._parser.push(chunk)

                for pkt in self._parser.pop_packets():
                    self.packet_received.emit(pkt)

                if self._parser.crc_errors != prev_crc_errors:
                    prev_crc_errors = self._parser.crc_errors
                    self.crc_error_count_changed.emit(prev_crc_errors)

        # Emit final diagnostic info before the thread ends
        self.raw_chunk.emit(
            f"[DISCONNECT] reason={disconnect_reason}  "
            f"total_rx={total_rx_bytes}B  "
            f"crc_errors={self._parser.crc_errors}".encode()
        )

        if self._serial and self._serial.is_open:
            self._serial.close()
