"""
app-cbc-tuning/mcp_server.py — Serveur MCP stdio pour CBC Tuner.

Lancé en sous-processus par Claude Code. Communique avec l'application Qt
via l'API REST IPC locale (localhost:3334). L'application Qt doit être
démarrée en premier.

Configuration dans .claude/settings.json :
  {
    "mcpServers": {
      "cbc-tuner": {
        "command": "py",
        "args": ["-3.11", "d:\\Projects\\gen_ai_robot_pendulum\\app-cbc-tuning\\mcp_server.py"],
        "cwd":  "d:\\Projects\\gen_ai_robot_pendulum\\app-cbc-tuning"
      }
    }
  }
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import numpy as np
from mcp.server.fastmcp import FastMCP

_STATE_URL  = "http://127.0.0.1:3334"
_TIMEOUT    = 3.0   # secondes
_DOWNSAMPLE = 4     # série temporelle : 1 point sur N  (20 Hz → ~5 Hz)

KP_MAX = 0.5
KI_MAX = 0.2
KD_MAX = 0.05


# ── Helpers IPC ───────────────────────────────────────────────────────────────

def _get(path: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(f"{_STATE_URL}{path}", timeout=_TIMEOUT) as r:
            return json.loads(r.read())  # type: ignore[no-any-return]
    except urllib.error.URLError:
        return {"error": "L'application CBC Tuner n'est pas lancée (localhost:3334 inaccessible)."}
    except Exception as exc:
        return {"error": str(exc)}


def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        f"{_STATE_URL}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return json.loads(r.read())  # type: ignore[no-any-return]
    except urllib.error.URLError:
        return {"error": "L'application CBC Tuner n'est pas lancée (localhost:3334 inaccessible)."}
    except Exception as exc:
        return {"error": str(exc)}


# ── Serveur MCP ───────────────────────────────────────────────────────────────

app = FastMCP(
    "CBC Tuner",
    instructions=(
        "Tu es un assistant de réglage PID pour un robot pendule inversé à deux roues. "
        "Le robot est contrôlé par un PID Angle (boucle interne CBC) dont tu peux modifier "
        "les gains Kp, Ki, Kd via UART. "
        "Procédure : utilise get_telemetry pour observer, set_angle_gains pour ajuster, "
        "itère jusqu'à la stabilisation. "
        f"Limites de sécurité absolues : Kp≤{KP_MAX}, Ki≤{KI_MAX}, Kd≤{KD_MAX}. "
        "pitch_deg > 0 = robot incliné vers l'avant. "
        "pid_p, pid_i, pid_d sont en unités normalisées [-1, +1] ; au-delà le firmware sature. "
        "Appelle emergency_stop si le robot devient incontrôlable."
    ),
)


@app.tool()
def get_telemetry(duration_s: float = 5.0) -> str:
    """Retourne la télémétrie du robot : valeurs actuelles, statistiques
    et série temporelle sous-échantillonnée à ~5 Hz.

    Args:
        duration_s: Durée d'historique en secondes (0.5 – 60).
    """
    state = _get("/state")
    if "error" in state:
        return json.dumps(state)

    t_list: list[float] = state.get("t", [])
    if not t_list:
        return json.dumps({
            "error": "Aucune donnée. Connecter l'appli à la carte et démarrer le stream."
        })

    duration_s = min(max(float(duration_s), 0.5), 60.0)

    t_arr  = np.array(t_list,                     dtype=float)
    p_arr  = np.array(state.get("pitch", []),     dtype=float)
    pp_arr = np.array(state.get("pid_p", []),     dtype=float)
    pi_arr = np.array(state.get("pid_i", []),     dtype=float)
    pd_arr = np.array(state.get("pid_d", []),     dtype=float)

    t_now = float(t_arr[-1])
    mask  = t_arr >= (t_now - duration_s)
    tw    = t_arr[mask] - t_now   # temps relatif : 0 = maintenant
    pw    = p_arr[mask]
    ppw   = pp_arr[mask]
    piw   = pi_arr[mask]
    pdw   = pd_arr[mask]

    def _stats(arr: np.ndarray) -> dict[str, float]:
        if len(arr) == 0:
            return {}
        return {
            "mean": round(float(np.mean(arr)), 3),
            "std":  round(float(np.std(arr)),  3),
            "min":  round(float(np.min(arr)),  3),
            "max":  round(float(np.max(arr)),  3),
        }

    idx = range(0, len(tw), _DOWNSAMPLE)
    samples = [
        {
            "t_s":   round(float(tw[i]),  2),
            "pitch": round(float(pw[i]),  2),
            "pid_p": round(float(ppw[i]), 3),
            "pid_i": round(float(piw[i]), 3),
            "pid_d": round(float(pdw[i]), 3),
        }
        for i in idx
    ]

    gains: dict[str, float] = state.get("gains", {})
    kp = gains.get("kp", 0.0)
    saturation_threshold: float | None = round(1.0 / kp, 1) if kp > 0 else None

    return json.dumps({
        "current": {
            "pitch_deg":     round(float(pw[-1]),   2) if len(pw)  else 0.0,
            "pid_p":         round(float(ppw[-1]),  3) if len(ppw) else 0.0,
            "pid_i":         round(float(piw[-1]),  3) if len(piw) else 0.0,
            "pid_d":         round(float(pdw[-1]),  3) if len(pdw) else 0.0,
            "rpm_left":      state.get("rpm_l", 0),
            "rpm_right":     state.get("rpm_r", 0),
            "pwm_left_pct":  round(float(state.get("pwm_l", 0.0)) * 100.0, 1),
            "pwm_right_pct": round(float(state.get("pwm_r", 0.0)) * 100.0, 1),
        },
        "gains": {
            "kp": kp,
            "ki": gains.get("ki", 0.0),
            "kd": gains.get("kd", 0.0),
            "saturation_threshold_deg": saturation_threshold,
        },
        "statistics": {
            "pitch": _stats(pw),
            "pid_p": _stats(ppw),
            "pid_i": _stats(piw),
            "pid_d": _stats(pdw),
        },
        "samples":           samples,
        "sample_count":      int(len(pw)),
        "actual_duration_s": round(float(tw[-1] - tw[0]), 2) if len(tw) > 1 else 0.0,
        "connected":         state.get("connected", False),
    }, ensure_ascii=False)


@app.tool()
def set_angle_gains(kp: float, ki: float, kd: float) -> str:
    """Envoie de nouveaux gains PID angle au firmware via UART.
    Met aussi à jour les sliders dans l'interface graphique.

    Args:
        kp: Gain proportionnel [0, 0.5]  — seuil saturation = 1/kp degrés
        ki: Gain intégral      [0, 0.2]  — compense l'offset d'équilibre
        kd: Gain dérivé        [0, 0.05] — amortit les oscillations
    """
    errors = []
    if not (0.0 <= kp <= KP_MAX):
        errors.append(f"kp={kp} hors [0, {KP_MAX}]")
    if not (0.0 <= ki <= KI_MAX):
        errors.append(f"ki={ki} hors [0, {KI_MAX}]")
    if not (0.0 <= kd <= KD_MAX):
        errors.append(f"kd={kd} hors [0, {KD_MAX}]")
    if errors:
        return json.dumps({"error": " | ".join(errors)})

    result = _post("/gains", {"kp": kp, "ki": ki, "kd": kd})
    if "error" in result:
        return json.dumps(result)

    note = f"Seuil saturation P : ±{round(1.0/kp, 1)}°" if kp > 0 else "P désactivé"
    return json.dumps({"ok": True, "kp": kp, "ki": ki, "kd": kd, "note": note})


@app.tool()
def emergency_stop() -> str:
    """Remet immédiatement tous les gains PID angle à 0.
    À appeler si le robot devient incontrôlable.
    """
    result = _post("/gains", {"kp": 0.0, "ki": 0.0, "kd": 0.0})
    if "error" in result:
        return json.dumps(result)
    return json.dumps({"ok": True, "message": "Gains remis à 0."})


@app.tool()
def get_status() -> str:
    """Retourne l'état de connexion, les gains actifs et les derniers RPM."""
    state = _get("/state")
    if "error" in state:
        return json.dumps(state)
    return json.dumps({
        "connected":    state.get("connected", False),
        "gains":        state.get("gains", {}),
        "rpm_left":     state.get("rpm_l", 0),
        "rpm_right":    state.get("rpm_r", 0),
        "sample_count": len(state.get("t", [])),
    })


if __name__ == "__main__":
    app.run(transport="stdio")
