"""
tools/system_id.py — Identification grey-box du pendule inversé.

Modèle physique (petits angles) :
    θ̈ = a·θ + b·u + c·θ̇
    a = g/L_eff   (terme instabilisant)
    b = Km/J      (gain moteur → couple)
    c = -fric/J   (frottement visqueux, négatif = amortissant)

Algorithme :
    1. Charger les fichiers sweep JSON (survived seulement)
    2. Calculer θ̈ par différences finies centrées (d²/dt²)
    3. Construire la matrice de régression A = [θ, u, θ̇]
    4. Résoudre [a, b, c] = lstsq(A, θ̈)
    5. Valider : simuler avec solve_ivp, calculer RMS erreur vs hardware
    6. Sauvegarder model.json

Usage :
    python tools/system_id.py sweeps/ --output model.json --plot
    python tools/system_id.py sweeps/ --validate   # valide uniquement
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.linalg import lstsq  # type: ignore[import-untyped]
from scipy.integrate import solve_ivp  # type: ignore[import-untyped]

_TOOLS_DIR = str(Path(__file__).parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)


# ── Chargement des données ────────────────────────────────────────────────────

def _load_all_samples(
    directory: str,
    min_samples: int = 10,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Charge et concatène les échantillons de tous les trials survived.

    Retourne (theta_rad, u, theta_dot_rad_s, dt_s).
    Les angles sont convertis en radians pour l'identification.
    """
    from sweep_analysis import load_sweeps, rank_trials

    trials = load_sweeps(directory)
    survived = rank_trials(trials, key="rms_deg", survived_only=True)

    if not survived:
        raise ValueError(f"Aucun essai 'survived' trouvé dans {directory}")

    all_theta:  list[np.ndarray] = []
    all_u:      list[np.ndarray] = []
    all_dtheta: list[np.ndarray] = []
    dt_samples: list[float]      = []

    for t in survived:
        samples = t.get("samples", [])
        if len(samples) < min_samples:
            continue

        ts   = np.array([s["t_s"]        for s in samples])
        pts  = np.array([s["pitch"]       for s in samples])  # degrés
        drv  = np.array([s["drive"]       for s in samples])
        pr   = np.array([s.get("pitch_rate", 0.0) for s in samples])  # °/s

        # Estimer dt médian de cet essai
        dts = np.diff(ts)
        if len(dts) == 0:
            continue
        dt = float(np.median(dts[dts > 0]))
        if dt <= 0:
            continue
        dt_samples.append(dt)

        # Convertir en radians
        theta    = np.deg2rad(pts)
        dtheta   = np.deg2rad(pr)

        # Recalcul θ̇ par différences finies si pitch_rate non disponible
        if np.all(pr == 0.0):
            dtheta = np.gradient(theta, dt)

        all_theta.append(theta)
        all_u.append(drv)
        all_dtheta.append(dtheta)

    if not all_theta:
        raise ValueError("Pas assez de données valides pour l'identification")

    theta_arr  = np.concatenate(all_theta)
    u_arr      = np.concatenate(all_u)
    dtheta_arr = np.concatenate(all_dtheta)
    dt_mean    = float(np.mean(dt_samples))

    return theta_arr, u_arr, dtheta_arr, dt_mean


# ── Identification grey-box ───────────────────────────────────────────────────

def identify_model(
    theta: np.ndarray,
    u: np.ndarray,
    dtheta: np.ndarray,
    dt: float,
) -> dict[str, float]:
    """Identifie les paramètres (a, b, c) par moindres carrés.

    θ̈ = a·θ + b·u + c·θ̇

    Retourne un dict avec a, b, c et les statistiques de la régression.
    """
    # Calculer θ̈ par différences finies centrées (plus précis que forward)
    ddtheta = np.gradient(dtheta, dt)

    # Retirer les 2 premiers et 2 derniers points (bords bruités)
    idx = slice(2, len(theta) - 2)
    A   = np.column_stack([theta[idx], u[idx], dtheta[idx]])
    y   = ddtheta[idx]

    # Filtrer les valeurs aberrantes (|θ̈| > 5000 rad/s²)
    valid = np.abs(y) < 5000.0
    A, y  = A[valid], y[valid]

    if len(y) < 10:
        raise ValueError("Pas assez de points valides pour la régression")

    coeffs, residuals, rank, sv = lstsq(A, y)
    a, b, c = float(coeffs[0]), float(coeffs[1]), float(coeffs[2])

    # Qualité de l'ajustement
    y_pred  = A @ coeffs
    ss_res  = float(np.sum((y - y_pred) ** 2))
    ss_tot  = float(np.sum((y - np.mean(y)) ** 2))
    r2      = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    rmse    = float(np.sqrt(np.mean((y - y_pred) ** 2)))

    return {
        "a": round(a, 4),         # g/L_eff (rad/s² par rad, ≈ positif > 0)
        "b": round(b, 4),         # Km/J    (rad/s² par unité de commande)
        "c": round(c, 4),         # -fric/J (rad/s² par rad/s, ≈ négatif)
        "r2":   round(r2,   4),
        "rmse": round(rmse, 4),
        "n_points": int(len(y)),
        "dt_s": round(dt, 5),
    }


# ── Validation ────────────────────────────────────────────────────────────────

def validate_model(
    model: dict[str, float],
    theta_hw: np.ndarray,
    u_hw: np.ndarray,
    dt: float,
    theta0_rad: float | None = None,
    dtheta0_rad: float | None = None,
) -> dict[str, float]:
    """Simule le modèle et compare avec les données hardware.

    Utilise l'entrée réelle u(t) comme excitation de la simulation.
    Retourne RMS erreur et corrélation.
    """
    a, b, c = model["a"], model["b"], model["c"]

    theta0   = float(theta0_rad  if theta0_rad  is not None else theta_hw[0])
    dtheta0  = float(dtheta0_rad if dtheta0_rad is not None else 0.0)

    t_span = np.arange(len(theta_hw)) * dt

    # Interpolateur pour l'entrée u(t)
    from scipy.interpolate import interp1d
    u_interp = interp1d(t_span, u_hw, kind="linear", fill_value="extrapolate")

    def ode(t: float, y: list[float]) -> list[float]:
        th, dth = y
        u_t     = float(u_interp(t))
        ddth    = a * th + b * u_t + c * dth
        return [dth, ddth]

    sol = solve_ivp(
        ode, [t_span[0], t_span[-1]], [theta0, dtheta0],
        t_eval=t_span, method="RK45", max_step=dt * 2,
    )

    if not sol.success or len(sol.y[0]) != len(theta_hw):
        return {"validation_rms_deg": float("nan"), "correlation": float("nan")}

    theta_sim = sol.y[0]
    err_deg   = np.rad2deg(theta_hw - theta_sim)
    rms_deg   = float(np.sqrt(np.mean(err_deg ** 2)))
    corr      = float(np.corrcoef(theta_hw, theta_sim)[0, 1])

    return {
        "validation_rms_deg": round(rms_deg, 3),
        "correlation":        round(corr, 4),
        "theta_sim":          theta_sim.tolist(),
    }


# ── Pipeline complet ──────────────────────────────────────────────────────────

def run_identification(
    directory: str,
    output_path: str | None = None,
    plot: bool = False,
) -> dict[str, float]:
    """Lance le pipeline complet : chargement → identification → validation.

    Retourne le dict du modèle enrichi avec les statistiques de validation.
    """
    print(f"Chargement des données depuis : {directory}")
    theta, u, dtheta, dt = _load_all_samples(directory)
    print(f"  {len(theta)} échantillons, dt={dt*1000:.1f} ms")

    print("Identification grey-box…")
    model = identify_model(theta, u, dtheta, dt)
    print(f"  a={model['a']:.4f}  b={model['b']:.4f}  c={model['c']:.4f}")
    print(f"  R²={model['r2']:.4f}  RMSE={model['rmse']:.4f} rad/s²")

    # Validation sur le premier essai survived
    from sweep_analysis import load_sweeps, rank_trials
    survived = rank_trials(load_sweeps(directory), survived_only=True)
    val_result: dict[str, float] = {}
    if survived:
        first = survived[0]
        samples = first.get("samples", [])
        if len(samples) > 10:
            pts_hw = np.deg2rad([s["pitch"] for s in samples])
            u_hw   = np.array([s["drive"]   for s in samples])
            val    = validate_model(model, pts_hw, u_hw, dt)
            val_result = {
                "validation_rms_deg": val["validation_rms_deg"],
                "correlation":        val["correlation"],
            }
            print(f"  Validation : RMS={val['validation_rms_deg']:.2f}°  corr={val['correlation']:.3f}")
            if plot:
                _plot_validation(
                    samples, np.rad2deg(val.get("theta_sim", pts_hw)), dt
                )

    model.update(val_result)

    if output_path:
        Path(output_path).write_text(
            json.dumps(model, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Modèle sauvegardé : {output_path}")

    return model


# ── Tracé ─────────────────────────────────────────────────────────────────────

def _plot_validation(
    samples: list[dict],
    theta_sim_deg: np.ndarray,
    dt: float,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib non disponible pour le tracé", file=sys.stderr)
        return

    ts  = np.array([s["t_s"]    for s in samples])
    pts = np.array([s["pitch"]  for s in samples])
    u   = np.array([s["drive"]  for s in samples])

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    fig.suptitle("Validation modèle vs hardware", fontsize=12)

    axes[0].plot(ts, pts,          label="Hardware", color="#ef5350", linewidth=2)
    axes[0].plot(ts, theta_sim_deg, label="Simulation", color="#42a5f5",
                 linewidth=1.5, linestyle="--")
    axes[0].set_ylabel("Pitch (°)")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    axes[0].axhline(0, color="gray", linewidth=0.8)

    axes[1].plot(ts, u, color="#66bb6a", linewidth=1.5, label="Drive output")
    axes[1].set_ylabel("Commande (norm.)")
    axes[1].set_xlabel("Temps (s)")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Identification grey-box du pendule inversé")
    parser.add_argument("directory", help="Dossier contenant les fichiers sweep JSON")
    parser.add_argument("--output",   default=None,  help="Fichier de sortie model.json")
    parser.add_argument("--plot",     action="store_true", help="Afficher le tracé de validation")
    parser.add_argument("--validate", action="store_true", help="Charger model.json et valider")
    args = parser.parse_args()

    if args.validate and args.output and Path(args.output).exists():
        model = json.loads(Path(args.output).read_text(encoding="utf-8"))
        print("Paramètres du modèle chargé :")
        for k, v in model.items():
            if not isinstance(v, list):
                print(f"  {k} = {v}")
        return

    model = run_identification(args.directory, output_path=args.output, plot=args.plot)

    print("\nParamètres physiques estimés :")
    print(f"  g/L_eff  (a) = {model['a']:.4f} rad/s²/rad  "
          f"→ L_eff ≈ {9.81/model['a']:.3f} m" if model.get('a', 0) > 0 else "  a ≤ 0 (vérifier données)")
    print(f"  Km/J     (b) = {model['b']:.4f} rad/s²/cmd")
    print(f"  -fric/J  (c) = {model['c']:.4f} rad/s²/(rad/s)")


if __name__ == "__main__":
    main()
