"""
tools/sweep_sim.py — Sweep de paramètres PID sur le simulateur.

Usage :
    python tools/sweep_sim.py model.json --kp 0.05,0.45,20 --kd 0,0.05,20 --plot
    python tools/sweep_sim.py model.json --bayesian --n-trials 50 --plot

Retourne top N candidats classés par rms_deg, et peut sauvegarder
sim_results.json pour que run_simulated_sweep (MCP) les exploite.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

_TOOLS_DIR = str(Path(__file__).parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from simulator import InvertedPendulumSim, PIDController, simulate_trial


# ── Chargement du modèle ──────────────────────────────────────────────────────

def load_model(path: str) -> dict[str, float]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for k in ("a", "b", "c", "dt_s"):
        if k not in data:
            raise ValueError(f"model.json manque la clé '{k}'")
    return data


# ── Métriques de qualité ──────────────────────────────────────────────────────

def _score(trial: dict) -> float:
    """Score composite : pénalise les essais non-survived."""
    m = trial.get("metrics", {})
    if trial.get("result") != "survived":
        return math.inf
    rms     = m.get("rms_deg",       math.inf)
    max_abs = m.get("max_abs_deg",   math.inf)
    settle  = m.get("settling_time_s", math.inf)
    return rms + 0.3 * max_abs + 0.2 * settle


# ── Grid sweep ────────────────────────────────────────────────────────────────

def grid_sweep(
    model: dict[str, float],
    kp_min: float, kp_max: float, kp_steps: int,
    kd_min: float, kd_max: float, kd_steps: int,
    ki: float = 0.0,
    duration_s: float = 1.5,
    theta0_deg: float = 2.0,
) -> list[dict[str, Any]]:
    """Balayage systématique Kp × Kd, Ki fixe."""
    sim = InvertedPendulumSim(
        a=model["a"], b=model["b"], c=model["c"], dt=model["dt_s"]
    )
    kp_values = np.linspace(kp_min, kp_max, kp_steps)
    kd_values = np.linspace(kd_min, kd_max, kd_steps)
    results: list[dict[str, Any]] = []

    for kp in kp_values:
        for kd in kd_values:
            pid = PIDController(
                kp=float(kp), ki=float(ki), kd=float(kd),
                dt=model["dt_s"],
            )
            trial = simulate_trial(sim, pid, duration_s=duration_s, theta0_deg=theta0_deg)
            trial["trial"] = {
                "kp": round(float(kp), 4),
                "ki": round(float(ki), 4),
                "kd": round(float(kd), 5),
            }
            results.append(trial)

    return sorted(results, key=_score)


# ── Bayesian sweep ────────────────────────────────────────────────────────────

def bayesian_sweep(
    model: dict[str, float],
    kp_min: float, kp_max: float,
    kd_min: float, kd_max: float,
    ki: float = 0.0,
    n_trials: int = 50,
    duration_s: float = 1.5,
    theta0_deg: float = 2.0,
) -> list[dict[str, Any]]:
    """Optimisation Bayésienne avec optuna (fallback sur grid si absent)."""
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        print("optuna non disponible, fallback sur grid 10×10", file=sys.stderr)
        return grid_sweep(
            model,
            kp_min, kp_max, max(5, int(n_trials ** 0.5)),
            kd_min, kd_max, max(5, int(n_trials ** 0.5)),
            ki=ki, duration_s=duration_s, theta0_deg=theta0_deg,
        )

    sim = InvertedPendulumSim(
        a=model["a"], b=model["b"], c=model["c"], dt=model["dt_s"]
    )
    results: list[dict[str, Any]] = []

    def objective(trial_: optuna.Trial) -> float:
        kp = trial_.suggest_float("kp", kp_min, kp_max)
        kd = trial_.suggest_float("kd", kd_min, kd_max)
        pid = PIDController(
            kp=kp, ki=ki, kd=kd, dt=model["dt_s"]
        )
        t = simulate_trial(sim, pid, duration_s=duration_s, theta0_deg=theta0_deg)
        t["trial"] = {"kp": round(kp, 4), "ki": round(ki, 4), "kd": round(kd, 5)}
        results.append(t)
        return _score(t)

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return sorted(results, key=_score)


# ── Comparaison sim vs hardware ───────────────────────────────────────────────

def compare_sim_hardware(
    sim_trial: dict[str, Any],
    hw_trial:  dict[str, Any],
) -> dict[str, float]:
    """Compare les métriques d'un essai simulé et d'un essai hardware.

    Retourne les écarts absolus et relatifs pour chaque métrique.
    """
    sim_m = sim_trial.get("metrics", {})
    hw_m  = hw_trial.get("metrics", {})
    keys  = ("rms_deg", "max_abs_deg", "settling_time_s", "saturation_pct", "energy")
    diff  = {}
    for k in keys:
        sv = sim_m.get(k, float("nan"))
        hv = hw_m.get(k, float("nan"))
        if not math.isnan(sv) and not math.isnan(hv) and hv != 0:
            diff[f"{k}_sim"]     = sv
            diff[f"{k}_hw"]      = hv
            diff[f"{k}_abs_err"] = round(abs(sv - hv), 4)
            diff[f"{k}_rel_err"] = round(abs(sv - hv) / abs(hv) * 100, 1)
    return diff


# ── Affichage & tracé ─────────────────────────────────────────────────────────

def print_top(results: list[dict[str, Any]], top: int = 10) -> None:
    header = f"{'#':>3}  {'kp':>6}  {'ki':>6}  {'kd':>7}  {'rms°':>6}  {'max°':>6}  {'settle s':>8}  {'résultat'}"
    print(header)
    print("-" * len(header))
    for rank, t in enumerate(results[:top], 1):
        tr = t.get("trial", {})
        m  = t.get("metrics", {})
        print(
            f"{rank:>3}  {tr.get('kp',0):>6.3f}  {tr.get('ki',0):>6.3f}  {tr.get('kd',0):>7.4f}"
            f"  {m.get('rms_deg',float('nan')):>6.3f}"
            f"  {m.get('max_abs_deg',float('nan')):>6.3f}"
            f"  {m.get('settling_time_s',float('nan')):>8.3f}"
            f"  {t.get('result','?')}"
        )


def plot_results(results: list[dict[str, Any]], top: int = 10) -> None:
    try:
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        from matplotlib.colors import Normalize
    except ImportError:
        print("matplotlib non disponible", file=sys.stderr)
        return

    survived = [r for r in results if r.get("result") == "survived"]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Sweep simulé — Analyse PID", fontsize=12)

    # Overlay pitch (top N)
    ax = axes[0]
    top_t = survived[:top]
    if top_t:
        rms_vals = [t["metrics"]["rms_deg"] for t in top_t]
        norm     = Normalize(vmin=min(rms_vals), vmax=max(rms_vals))
        cmap     = cm.RdYlGn_r
        for t in top_t:
            samples = t.get("samples", [])
            if not samples:
                continue
            ts  = [s["t_s"]    for s in samples]
            pts = [s["pitch"]  for s in samples]
            col = cmap(norm(t["metrics"]["rms_deg"]))
            tr  = t["trial"]
            ax.plot(ts, pts, color=col, alpha=0.7, linewidth=1.2,
                    label=f"kp={tr['kp']:.3f} kd={tr['kd']:.4f}")
        ax.axhline(0, color="gray", linewidth=0.8)
        ax.axhline(2,  color="gray", linewidth=0.5, linestyle=":")
        ax.axhline(-2, color="gray", linewidth=0.5, linestyle=":")
    ax.set_xlabel("Temps (s)")
    ax.set_ylabel("Pitch (°)")
    ax.set_title(f"Top {top} pitch simulé")
    ax.grid(True, alpha=0.3)

    # Pareto
    ax2 = axes[1]
    xs = [t["metrics"].get("max_abs_deg",    float("nan")) for t in survived]
    ys = [t["metrics"].get("settling_time_s", float("nan")) for t in survived]
    ax2.scatter(xs, ys, c="steelblue", alpha=0.5, s=30)

    # Annoter top 5
    for t in survived[:5]:
        tr = t["trial"]
        x  = t["metrics"].get("max_abs_deg",    0)
        y  = t["metrics"].get("settling_time_s", 0)
        ax2.scatter(x, y, c="lime", s=80, zorder=5)
        ax2.annotate(f"kp={tr['kp']:.2f}\nkd={tr['kd']:.3f}",
                     (x, y), xytext=(5, 5), textcoords="offset points", fontsize=7)

    ax2.set_xlabel("Max |pitch| (°)")
    ax2.set_ylabel("Settling time (s)")
    ax2.set_title("Front de Pareto simulé")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep PID sur simulateur")
    parser.add_argument("model",        help="Fichier model.json (produit par system_id.py)")
    parser.add_argument("--kp",         default="0.05,0.45,20",
                        help="kp_min,kp_max,steps  (défaut 0.05,0.45,20)")
    parser.add_argument("--kd",         default="0.0,0.05,20",
                        help="kd_min,kd_max,steps  (défaut 0.0,0.05,20)")
    parser.add_argument("--ki",         type=float, default=0.0)
    parser.add_argument("--bayesian",   action="store_true",
                        help="Utiliser l'optimisation Bayésienne au lieu du grid")
    parser.add_argument("--n-trials",   type=int, default=50,
                        help="Nombre d'essais Bayésiens (défaut 50)")
    parser.add_argument("--theta0",     type=float, default=2.0,
                        help="Angle initial en degrés (défaut 2.0)")
    parser.add_argument("--duration",   type=float, default=1.5,
                        help="Durée de simulation en secondes (défaut 1.5)")
    parser.add_argument("--top",        type=int, default=10)
    parser.add_argument("--plot",       action="store_true")
    parser.add_argument("--output",     default=None,
                        help="Sauvegarder les résultats (sim_results.json)")
    args = parser.parse_args()

    model = load_model(args.model)
    print(f"Modèle : a={model['a']:.4f}  b={model['b']:.4f}  c={model['c']:.4f}  dt={model['dt_s']*1000:.1f}ms")

    kp_parts = [float(x) for x in args.kp.split(",")]
    kd_parts = [float(x) for x in args.kd.split(",")]
    kp_min, kp_max, kp_steps = kp_parts[0], kp_parts[1], int(kp_parts[2])
    kd_min, kd_max, kd_steps = kd_parts[0], kd_parts[1], int(kd_parts[2])

    if args.bayesian:
        print(f"Bayesian sweep ({args.n_trials} essais)…")
        results = bayesian_sweep(
            model, kp_min, kp_max, kd_min, kd_max,
            ki=args.ki, n_trials=args.n_trials,
            duration_s=args.duration, theta0_deg=args.theta0,
        )
    else:
        n_total = kp_steps * kd_steps
        print(f"Grid sweep {kp_steps}×{kd_steps} = {n_total} simulations…")
        results = grid_sweep(
            model, kp_min, kp_max, kp_steps, kd_min, kd_max, kd_steps,
            ki=args.ki, duration_s=args.duration, theta0_deg=args.theta0,
        )

    survived = sum(1 for r in results if r.get("result") == "survived")
    print(f"Terminé — {survived}/{len(results)} survived\n")

    print(f"Top {args.top} :")
    print_top(results, top=args.top)

    if args.output:
        # Sauvegarder sans les samples (trop volumineux)
        compact = [
            {"trial": r["trial"], "result": r["result"], "metrics": r.get("metrics", {})}
            for r in results
        ]
        Path(args.output).write_text(
            json.dumps(compact, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nRésultats sauvegardés : {args.output}")

    if args.plot:
        plot_results(results, top=args.top)


if __name__ == "__main__":
    main()
