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

import asyncio
import json
import math
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

import numpy as np
from mcp.server.fastmcp import FastMCP

_STATE_URL  = "http://127.0.0.1:3334"
_TIMEOUT    = 3.0   # secondes
_DOWNSAMPLE = 4     # série temporelle : 1 point sur N  (20 Hz → ~5 Hz)

KP_MAX = 0.5
KI_MAX = 0.2
KD_MAX = 0.05

VEL_KP_MAX = 0.10
VEL_KI_MAX = 0.05
VEL_KD_MAX = 0.02


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
        "Architecture CASCADE : "
        "  Boucle INTERNE (angle) : pitch_deg → drive [-1,+1]. "
        "  Boucle EXTERNE (vitesse) : vel_avg_rpm → target_pitch_deg (consigne interne). "
        "Procédure : commence par stabiliser la boucle angle (set_angle_gains), "
        "puis active progressivement la boucle vitesse (set_velocity_gains). "
        f"Limites angle  : Kp≤{KP_MAX}, Ki≤{KI_MAX}, Kd≤{KD_MAX}. "
        f"Limites vitesse: Kp≤{VEL_KP_MAX}, Ki≤{VEL_KI_MAX}, Kd≤{VEL_KD_MAX}. "
        "target_pitch_deg = sortie boucle vitesse (< ±8° = normal). "
        "pitch_deg > 0 = robot incliné vers l'avant. "
        "pid_p, pid_i, pid_d en unités normalisées [-1,+1]. "
        "Appelle emergency_stop si le robot devient incontrôlable."
    ),
)


def _build_telemetry(state: dict[str, Any], duration_s: float,
                     t_anchor: float | None = None) -> str:
    """Construit le JSON de télémétrie depuis un snapshot d'état.

    t_anchor : timestamp absolu (time.monotonic) servant d'origine temporelle.
               Si None, t_now du buffer est utilisé (comportement habituel).
    """
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

    vel_gains: dict[str, float] = state.get("vel_gains", {})

    return json.dumps({
        "current": {
            "pitch_deg":       round(float(pw[-1]),   2) if len(pw)  else 0.0,
            "target_pitch_deg": round(float(state.get("target_pitch", 0.0)), 2),
            "vel_avg_rpm":     round(float(state.get("vel_avg", 0.0)), 1),
            "pid_p":           round(float(ppw[-1]),  3) if len(ppw) else 0.0,
            "pid_i":           round(float(piw[-1]),  3) if len(piw) else 0.0,
            "pid_d":           round(float(pdw[-1]),  3) if len(pdw) else 0.0,
            "rpm_left":        state.get("rpm_l", 0),
            "rpm_right":       state.get("rpm_r", 0),
            "pwm_left_pct":    round(float(state.get("pwm_l", 0.0)) * 100.0, 1),
            "pwm_right_pct":   round(float(state.get("pwm_r", 0.0)) * 100.0, 1),
        },
        "gains": {
            "kp": kp,
            "ki": gains.get("ki", 0.0),
            "kd": gains.get("kd", 0.0),
            "saturation_threshold_deg": saturation_threshold,
        },
        "vel_gains": {
            "kp": vel_gains.get("kp", 0.0),
            "ki": vel_gains.get("ki", 0.0),
            "kd": vel_gains.get("kd", 0.0),
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
def get_telemetry(duration_s: float = 5.0) -> str:
    """Retourne la télémétrie du robot : valeurs actuelles, statistiques
    et série temporelle sous-échantillonnée à ~5 Hz.

    Args:
        duration_s: Durée d'historique en secondes (0.5 – 60).
    """
    state = _get("/state")
    if "error" in state:
        return json.dumps(state)
    return _build_telemetry(state, duration_s)


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
def set_velocity_gains(kp: float, ki: float, kd: float) -> str:
    """Envoie de nouveaux gains PID vitesse (boucle externe) au firmware.

    La boucle vitesse transforme la vitesse des roues en consigne d'angle
    pour la boucle interne. Commencer avec des gains très faibles (Kp ≈ 0.005).
    La consigne de vitesse est 0 RPM (position hold) par défaut.

    Args:
        kp: Gain proportionnel [0, 0.10]
        ki: Gain intégral      [0, 0.05]  — compense la dérive lente
        kd: Gain dérivé        [0, 0.02]
    """
    errors = []
    if not (0.0 <= kp <= VEL_KP_MAX):
        errors.append(f"kp={kp} hors [0, {VEL_KP_MAX}]")
    if not (0.0 <= ki <= VEL_KI_MAX):
        errors.append(f"ki={ki} hors [0, {VEL_KI_MAX}]")
    if not (0.0 <= kd <= VEL_KD_MAX):
        errors.append(f"kd={kd} hors [0, {VEL_KD_MAX}]")
    if errors:
        return json.dumps({"error": " | ".join(errors)})

    result = _post("/vel_gains", {"kp": kp, "ki": ki, "kd": kd})
    if "error" in result:
        return json.dumps(result)

    return json.dumps({"ok": True, "kp": kp, "ki": ki, "kd": kd,
                       "note": "Surveiller target_pitch_deg dans get_telemetry (< ±8°)"})


@app.tool()
def emergency_stop() -> str:
    """Remet immédiatement tous les gains PID (angle ET vitesse) à 0.
    À appeler si le robot devient incontrôlable.
    """
    _post("/vel_gains", {"kp": 0.0, "ki": 0.0, "kd": 0.0})
    result = _post("/gains", {"kp": 0.0, "ki": 0.0, "kd": 0.0})
    if "error" in result:
        return json.dumps(result)
    return json.dumps({"ok": True, "message": "Gains angle et vitesse remis à 0."})


@app.tool()
async def run_test(kp: float, ki: float, kd: float, hold_s: float = 2.0) -> str:
    """Lance une séquence de test temporisée complète.

    Séquence automatique :
      t=0        : début de la fenêtre de capture (baseline)
      t+200 ms   : applique kp/ki/kd au firmware  ← lâcher le robot maintenant
      t+200+hold : coupe les moteurs (gains → 0)
      t+600+hold : retourne la télémétrie de toute la fenêtre

    Le robot doit être tenu immobile AVANT l'appel. Lâcher dès réception
    du message "LÂCHE" (≈200 ms après l'appel).

    Args:
        kp:     Gain proportionnel [0, 0.5]  — seuil saturation = 1/kp degrés
        ki:     Gain intégral      [0, 0.2]  — compense l'offset d'équilibre
        kd:     Gain dérivé        [0, 0.05] — amortit les oscillations
        hold_s: Durée de la phase de test en secondes (0.5 – 5.0), défaut 2.0
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

    hold_s = min(max(float(hold_s), 0.5), 5.0)

    # Vérifier la connexion avant de démarrer la séquence
    status = _get("/state")
    if "error" in status:
        return json.dumps(status)
    if not status.get("connected", False):
        return json.dumps({"error": "Non connecté. Ouvrir la connexion dans l'appli d'abord."})

    t_start = time.monotonic()

    # Baseline 200 ms avant application des gains
    await asyncio.sleep(0.2)

    # Appliquer les gains → firmware actif → LÂCHER LE ROBOT
    result = _post("/gains", {"kp": kp, "ki": ki, "kd": kd})
    if "error" in result:
        return json.dumps(result)

    # Phase de test
    await asyncio.sleep(hold_s)

    # Couper les moteurs
    _post("/gains", {"kp": 0.0, "ki": 0.0, "kd": 0.0})

    # Attendre 400 ms pour que le buffer capture l'arrêt, puis lire
    await asyncio.sleep(0.4)

    state = _get("/state")
    if "error" in state:
        return json.dumps(state)

    total_window = hold_s + 1.0   # baseline + test + après coupure
    telemetry = _build_telemetry(state, total_window)

    # Injecter les métadonnées de séquence dans la réponse
    data = json.loads(telemetry)
    data["sequence"] = {
        "kp": kp, "ki": ki, "kd": kd,
        "hold_s": hold_s,
        "elapsed_s": round(time.monotonic() - t_start, 2),
    }
    return json.dumps(data, ensure_ascii=False)


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


# ── Helpers métriques sweep ───────────────────────────────────────────────────

def _compute_metrics(
    t_arr: np.ndarray,
    pitch_arr: np.ndarray,
    drive_arr: np.ndarray,
    t_start_s: float,
) -> dict[str, float]:
    """Calcule les métriques de qualité sur la fenêtre de test (t >= t_start_s)."""
    mask = t_arr >= t_start_s
    if mask.sum() == 0:
        return {}
    p = pitch_arr[mask]
    u = drive_arr[mask]
    rms     = float(np.sqrt(np.mean(p ** 2)))
    max_abs = float(np.max(np.abs(p)))
    energy  = float(np.mean(np.abs(u)))
    sat_pct = float(100.0 * np.mean(np.abs(u) > 0.9))

    # Temps d'établissement : dernier instant où |pitch| > 2°
    indices = np.where(np.abs(p) > 2.0)[0]
    if len(indices) == 0:
        t_rel = t_arr[mask]
        settling = float(t_rel[0] - t_start_s)
    else:
        t_rel    = t_arr[mask]
        settling = float(t_rel[indices[-1]] - t_start_s)

    return {
        "rms_deg":        round(rms,     3),
        "max_abs_deg":    round(max_abs, 3),
        "settling_time_s": round(settling, 3),
        "saturation_pct": round(sat_pct,  1),
        "energy":         round(energy,   3),
    }


def _build_sweep_samples(
    state: dict[str, Any],
    t_window_s: float,
) -> tuple[list[dict], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Extrait les échantillons full-rate depuis le snapshot d'état.

    Retourne (samples_list, t_arr, pitch_arr, drive_arr, pitch_rate_arr).
    """
    t_list    = state.get("t", [])
    p_list    = state.get("pitch", [])
    pr_list   = state.get("pitch_rate", [])
    drv_list  = state.get("drive", [])

    if not t_list:
        return [], np.array([]), np.array([]), np.array([]), np.array([])

    t_arr   = np.array(t_list,   dtype=float)
    p_arr   = np.array(p_list,   dtype=float)
    pr_arr  = np.array(pr_list,  dtype=float) if pr_list else np.zeros_like(t_arr)
    drv_arr = np.array(drv_list, dtype=float) if drv_list else np.zeros_like(t_arr)

    t_now = float(t_arr[-1])
    mask  = t_arr >= (t_now - t_window_s)

    tw   = t_arr[mask] - t_now   # temps relatif : 0 = fin de l'essai
    pw   = p_arr[mask]
    prw  = pr_arr[mask]
    drvw = drv_arr[mask]

    samples = [
        {
            "t_s":        round(float(tw[i]),   3),
            "pitch":      round(float(pw[i]),   3),
            "drive":      round(float(drvw[i]), 4),
            "pitch_rate": round(float(prw[i]),  3),
        }
        for i in range(len(tw))
    ]
    return samples, t_arr[mask], pw, drvw, prw


@app.tool()
async def run_sweep(
    param_sets: str,
    hold_s: float = 1.0,
    output_dir: str = "sweeps",
    early_stop_deg: float = 30.0,
) -> str:
    """Lance une batterie d'essais PID automatisés et sauvegarde chaque résultat.

    Pour chaque jeu de gains : baseline 200 ms → moteurs actifs hold_s s →
    coupure → fichier JSON avec télémétrie et métriques.

    Instructions : tenir le robot debout avant chaque essai, le lâcher au signal
    "LÂCHE" (≈200 ms après le début de chaque essai).

    Args:
        param_sets:     JSON array de jeux de gains, ex : '[{"kp":0.15,"ki":0,"kd":0.03}]'
        hold_s:         Durée phase active par essai en secondes (0.5 – 5.0)
        output_dir:     Dossier de sortie pour les fichiers JSON (créé si absent)
        early_stop_deg: Seuil |pitch| pour arrêt anticipé d'un essai (défaut 30°)
    """
    # Valider param_sets
    try:
        sets: list[dict[str, float]] = json.loads(param_sets)
        if not isinstance(sets, list) or len(sets) == 0:
            raise ValueError("param_sets doit être un tableau JSON non vide")
        for s in sets:
            for k in ("kp", "ki", "kd"):
                if k not in s:
                    raise ValueError(f"Jeu de gains sans clé '{k}': {s}")
    except (json.JSONDecodeError, ValueError) as exc:
        return json.dumps({"error": f"param_sets invalide: {exc}"})

    hold_s = min(max(float(hold_s), 0.5), 5.0)
    early_stop_deg = float(early_stop_deg)

    # Vérifier connexion
    status = _get("/state")
    if "error" in status:
        return json.dumps(status)
    if not status.get("connected", False):
        return json.dumps({"error": "Non connecté. Ouvrir la connexion dans l'appli d'abord."})

    # Créer le dossier de sortie
    out_path = os.path.join(os.path.dirname(__file__), output_dir)
    os.makedirs(out_path, exist_ok=True)

    results: list[dict[str, Any]] = []
    total = len(sets)

    for idx, gains in enumerate(sets):
        kp = float(gains.get("kp", 0.0))
        ki = float(gains.get("ki", 0.0))
        kd = float(gains.get("kd", 0.0))

        # Validation des limites de sécurité
        errs = []
        if not (0.0 <= kp <= KP_MAX): errs.append(f"kp={kp} > {KP_MAX}")
        if not (0.0 <= ki <= KI_MAX): errs.append(f"ki={ki} > {KI_MAX}")
        if not (0.0 <= kd <= KD_MAX): errs.append(f"kd={kd} > {KD_MAX}")
        if errs:
            results.append({
                "trial": {"id": idx + 1, "kp": kp, "ki": ki, "kd": kd},
                "result": "skipped",
                "reason": " | ".join(errs),
            })
            continue

        # ── Séquence d'un essai ──────────────────────────────────────────────
        t_trial_start = time.monotonic()
        result_code   = "survived"

        # Baseline 200 ms (robot tenu immobile)
        await asyncio.sleep(0.2)

        # Appliquer les gains → LÂCHER LE ROBOT
        apply_res = _post("/gains", {"kp": kp, "ki": ki, "kd": kd})
        if "error" in apply_res:
            results.append({
                "trial": {"id": idx + 1, "kp": kp, "ki": ki, "kd": kd},
                "result": "failed",
                "reason": apply_res["error"],
            })
            continue

        t_gains_applied = time.monotonic()

        # Phase active : polling early-stop toutes les 50 ms
        elapsed = 0.0
        while elapsed < hold_s:
            await asyncio.sleep(0.05)
            elapsed = time.monotonic() - t_gains_applied
            snap = _get("/state")
            if "error" not in snap:
                last_pitch = snap.get("pitch", [0.0])
                if last_pitch and abs(last_pitch[-1]) > early_stop_deg:
                    result_code = "early_stop"
                    break

        # Couper les moteurs
        _post("/gains", {"kp": 0.0, "ki": 0.0, "kd": 0.0})

        # Attendre 400 ms pour capturer l'arrêt
        await asyncio.sleep(0.4)

        # Lire le snapshot final
        state = _get("/state")
        if "error" in state:
            results.append({
                "trial": {"id": idx + 1, "kp": kp, "ki": ki, "kd": kd},
                "result": "failed",
                "reason": state["error"],
            })
            continue

        total_window = hold_s + 1.0
        samples, t_arr, p_arr, drv_arr, pr_arr = _build_sweep_samples(state, total_window)

        # t_start_s en temps relatif (0 = fin essai) : début phase active ≈ -(hold_s + 0.4)
        t_active_start = -(hold_s + 0.4)
        metrics = _compute_metrics(
            t_arr - t_arr[-1],  # relatif 0=fin
            p_arr, drv_arr,
            t_active_start,
        )

        # Construire le document trial
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{ts_str}_kp{kp:.3f}_ki{ki:.3f}_kd{kd:.3f}.json"
        trial_doc: dict[str, Any] = {
            "trial":   {"id": idx + 1, "kp": kp, "ki": ki, "kd": kd, "hold_s": hold_s},
            "result":  result_code,
            "metrics": metrics,
            "samples": samples,
        }

        # Sauvegarder le fichier
        filepath = os.path.join(out_path, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(trial_doc, f, ensure_ascii=False, indent=2)

        results.append({
            "trial":    {"id": idx + 1, "kp": kp, "ki": ki, "kd": kd},
            "result":   result_code,
            "metrics":  metrics,
            "file":     filename,
        })

        # Pause inter-essai pour que l'opérateur repositionne le robot
        if idx < total - 1:
            await asyncio.sleep(2.0)

    # Classement par rms_deg (survived en premier)
    survived = [r for r in results if r.get("result") == "survived"]
    survived.sort(key=lambda r: r.get("metrics", {}).get("rms_deg", math.inf))

    return json.dumps({
        "sweep_complete": True,
        "total_trials":   total,
        "survived":       len(survived),
        "output_dir":     out_path,
        "ranking":        survived[:5],
        "all_results":    results,
    }, ensure_ascii=False, indent=2)


@app.tool()
def run_simulated_sweep(
    model_path: str = "model.json",
    kp_min: float = 0.05,
    kp_max: float = 0.45,
    kp_steps: int = 20,
    kd_min: float = 0.0,
    kd_max: float = 0.05,
    kd_steps: int = 20,
    ki: float = 0.0,
    theta0_deg: float = 2.0,
) -> str:
    """Lance un sweep PID sur le simulateur à partir d'un modèle identifié.

    Exécute kp_steps × kd_steps simulations en <1 s, retourne le top 10
    classé par rms_deg. Les meilleurs candidats peuvent ensuite être validés
    physiquement avec run_sweep.

    Prérequis : model.json doit avoir été généré par system_id.py.

    Args:
        model_path: Chemin vers model.json (relatif au dossier du MCP server)
        kp_min/max/steps: Plage et résolution pour Kp
        kd_min/max/steps: Plage et résolution pour Kd
        ki:          Gain intégral fixe pour ce sweep (0 = désactivé)
        theta0_deg:  Angle initial en degrés pour les simulations
    """
    import sys as _sys
    _tools_dir = os.path.join(os.path.dirname(__file__), "..", "tools")
    _tools_dir = os.path.normpath(_tools_dir)
    if _tools_dir not in _sys.path:
        _sys.path.insert(0, _tools_dir)

    # Résoudre le chemin du modèle
    model_abs = os.path.join(os.path.dirname(__file__), model_path)
    if not os.path.exists(model_abs):
        return json.dumps({
            "error": f"model.json introuvable : {model_abs}. "
                     "Lancer d'abord : python tools/system_id.py sweeps/ --output model.json"
        })

    try:
        from sweep_sim import grid_sweep, load_model
        model = load_model(model_abs)
    except Exception as exc:
        return json.dumps({"error": f"Erreur chargement modèle : {exc}"})

    n_total = kp_steps * kd_steps
    try:
        results = grid_sweep(
            model,
            kp_min, kp_max, kp_steps,
            kd_min, kd_max, kd_steps,
            ki=ki,
            theta0_deg=theta0_deg,
        )
    except Exception as exc:
        return json.dumps({"error": f"Erreur simulation : {exc}"})

    survived = [r for r in results if r.get("result") == "survived"]

    # Formater le top 10 sans les samples (trop volumineux pour MCP)
    top10 = [
        {"trial": r["trial"], "result": r["result"], "metrics": r.get("metrics", {})}
        for r in results[:10]
    ]

    # Recommandation des 3 meilleurs pour run_sweep
    top3_sets = [r["trial"] for r in results[:3] if r.get("result") == "survived"]

    return json.dumps({
        "model": {k: model[k] for k in ("a", "b", "c", "dt_s")
                  if k in model},
        "sweep_config": {
            "kp_range": [kp_min, kp_max, kp_steps],
            "kd_range": [kd_min, kd_max, kd_steps],
            "ki": ki,
            "total_simulations": n_total,
        },
        "survived": len(survived),
        "total":    n_total,
        "top10":    top10,
        "recommended_for_run_sweep": top3_sets,
        "note": (
            "Utiliser run_sweep avec 'recommended_for_run_sweep' pour valider "
            "ces candidats sur le robot physique."
        ),
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    app.run(transport="stdio")
