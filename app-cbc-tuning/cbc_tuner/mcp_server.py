"""
cbc_tuner/mcp_server.py — État partagé GUI ↔ MCP + serveur HTTP IPC local.

StateServer expose une API REST minimaliste sur localhost:3334 pour que le
serveur MCP stdio (app-cbc-tuning/mcp_server.py) puisse lire la télémétrie
et envoyer des commandes sans partager la mémoire du processus Qt.

  GET  /state  → snapshot JSON de la télémétrie
  POST /gains  → {"kp":…, "ki":…, "kd":…}  → applique les gains
"""
from __future__ import annotations

import json
import threading
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

STATE_PORT    = 3334
_SNAPSHOT_MAX = 3000   # points max renvoyés par GET /state (≈150 s à 20 Hz)


# ── État partagé GUI ↔ serveur IPC ────────────────────────────────────────────

@dataclass
class TunerState:
    """Données partagées entre le thread Qt et le serveur HTTP IPC."""
    t:          deque[float] = field(default_factory=lambda: deque(maxlen=12_000))
    pitch:      deque[float] = field(default_factory=lambda: deque(maxlen=12_000))
    pitch_rate: deque[float] = field(default_factory=lambda: deque(maxlen=12_000))
    drive:      deque[float] = field(default_factory=lambda: deque(maxlen=12_000))
    pid_p:      deque[float] = field(default_factory=lambda: deque(maxlen=12_000))
    pid_i:      deque[float] = field(default_factory=lambda: deque(maxlen=12_000))
    pid_d:      deque[float] = field(default_factory=lambda: deque(maxlen=12_000))
    # Télémétrie moteur (série temporelle)
    t_motor:   deque[float] = field(default_factory=lambda: deque(maxlen=12_000))
    sp_rpm_ts: deque[float] = field(default_factory=lambda: deque(maxlen=12_000))
    rpm_l_ts:  deque[float] = field(default_factory=lambda: deque(maxlen=12_000))
    rpm_r_ts:  deque[float] = field(default_factory=lambda: deque(maxlen=12_000))
    pwm_l_ts:  deque[float] = field(default_factory=lambda: deque(maxlen=12_000))
    pwm_r_ts:  deque[float] = field(default_factory=lambda: deque(maxlen=12_000))
    rpm_l: int   = 0
    rpm_r: int   = 0
    pwm_l: float = 0.0
    pwm_r: float = 0.0
    kp: float    = 0.0
    ki: float    = 0.0
    kd: float    = 0.0
    connected: bool = False
    send_gains: Callable[[float, float, float], None] | None = None


# ── Serveur HTTP IPC ──────────────────────────────────────────────────────────

class StateServer:
    """Lance un serveur HTTP stdlib en thread daemon pour l'IPC avec le MCP stdio."""

    def __init__(self, state: TunerState, port: int = STATE_PORT):
        self._state  = state
        self._port   = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        """Démarre le serveur. Retourne False si le port est déjà occupé."""
        state = self._state
        port  = self._port

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                pass  # silence des logs de requêtes

            def _send_json(self, body: bytes, code: int = 200) -> None:
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/state":
                    self._send_json(b'{"error":"not found"}', 404)
                    return
                n  = len(state.t)
                sl = slice(max(0, n - _SNAPSHOT_MAX), n)
                data = {
                    "connected":  state.connected,
                    "gains":      {"kp": state.kp, "ki": state.ki, "kd": state.kd},
                    "rpm_l":      state.rpm_l,
                    "rpm_r":      state.rpm_r,
                    "pwm_l":      state.pwm_l,
                    "pwm_r":      state.pwm_r,
                    "t":          list(state.t)[sl],
                    "pitch":      list(state.pitch)[sl],
                    "pitch_rate": list(state.pitch_rate)[sl],
                    "drive":      list(state.drive)[sl],
                    "pid_p":      list(state.pid_p)[sl],
                    "pid_i":      list(state.pid_i)[sl],
                    "pid_d":      list(state.pid_d)[sl],
                }
                self._send_json(json.dumps(data).encode())

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/gains":
                    self._send_json(b'{"error":"not found"}', 404)
                    return
                length = int(self.headers.get("Content-Length", 0))
                try:
                    body = json.loads(self.rfile.read(length))
                    kp   = float(body["kp"])
                    ki   = float(body["ki"])
                    kd   = float(body["kd"])
                except (KeyError, ValueError, json.JSONDecodeError) as exc:
                    self._send_json(json.dumps({"error": str(exc)}).encode(), 400)
                    return
                if state.connected and state.send_gains is not None:
                    state.send_gains(kp, ki, kd)
                    self._send_json(b'{"ok":true}')
                else:
                    msg = json.dumps(
                        {"error": "Non connecté. Ouvrir la connexion dans l'appli d'abord."}
                    ).encode()
                    self._send_json(msg, 503)

        try:
            self._server = HTTPServer(("127.0.0.1", port), _Handler)
        except OSError:
            return False

        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="cbc-state-http"
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()

    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}"
