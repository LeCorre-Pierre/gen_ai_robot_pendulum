"""
tools/sweep_analysis.py — Analyse comparative de sessions de sweep PID.

Usage :
    python tools/sweep_analysis.py sweeps/ --plot
    python tools/sweep_analysis.py sweeps/ --top 10
    python tools/sweep_analysis.py sweeps/ --plot --output report.png

Fonctions publiques utilisables depuis d'autres scripts :
    load_sweeps(directory)
    rank_trials(trials, key="rms_deg")
    stability_map(trials)
    pareto_front(trials)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np


# ── Chargement ────────────────────────────────────────────────────────────────

def load_sweeps(directory: str) -> list[dict[str, Any]]:
    """Charge tous les fichiers JSON d'un dossier de sweep.

    Retourne une liste de dicts, chacun étant le contenu d'un fichier trial.
    Les fichiers non conformes sont ignorés silencieusement.
    """
    trials: list[dict[str, Any]] = []
    p = Path(directory)
    if not p.is_dir():
        raise FileNotFoundError(f"Dossier introuvable : {directory}")
    for f in sorted(p.glob("*.json")):
        try:
            with f.open(encoding="utf-8") as fh:
                data = json.load(fh)
            if "trial" in data and "metrics" in data:
                data["_file"] = f.name
                trials.append(data)
        except (json.JSONDecodeError, KeyError):
            pass
    return trials


# ── Métriques & classement ────────────────────────────────────────────────────

def rank_trials(
    trials: list[dict[str, Any]],
    key: str = "rms_deg",
    survived_only: bool = True,
) -> list[dict[str, Any]]:
    """Trie les trials par métrique croissante.

    Args:
        key:           Clé de métrique ('rms_deg', 'max_abs_deg', 'settling_time_s', …)
        survived_only: Si True, exclut les essais 'early_stop' et 'failed'
    """
    filtered = [t for t in trials if not survived_only or t.get("result") == "survived"]
    return sorted(filtered, key=lambda t: t.get("metrics", {}).get(key, math.inf))


# ── Carte de stabilité ────────────────────────────────────────────────────────

def stability_map(
    trials: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Construit une grille Kp × Kd avec la valeur RMS pour chaque cellule.

    Retourne (kp_values, kd_values, rms_grid) où rms_grid[i, j] correspond à
    kp_values[i], kd_values[j]. NaN = essai absent ou non-survived.
    """
    kp_vals = sorted({t["trial"]["kp"] for t in trials})
    kd_vals = sorted({t["trial"]["kd"] for t in trials})
    kp_arr  = np.array(kp_vals)
    kd_arr  = np.array(kd_vals)
    grid    = np.full((len(kp_arr), len(kd_arr)), np.nan)

    kp_idx = {v: i for i, v in enumerate(kp_vals)}
    kd_idx = {v: i for i, v in enumerate(kd_vals)}

    for t in trials:
        if t.get("result") != "survived":
            continue
        kp = t["trial"]["kp"]
        kd = t["trial"]["kd"]
        rms = t.get("metrics", {}).get("rms_deg", math.nan)
        if kp in kp_idx and kd in kd_idx and not math.isnan(rms):
            i, j = kp_idx[kp], kd_idx[kd]
            if math.isnan(grid[i, j]) or rms < grid[i, j]:
                grid[i, j] = rms

    return kp_arr, kd_arr, grid


# ── Front de Pareto ───────────────────────────────────────────────────────────

def pareto_front(
    trials: list[dict[str, Any]],
    metric_x: str = "max_abs_deg",
    metric_y: str = "settling_time_s",
) -> list[dict[str, Any]]:
    """Retourne les trials sur le front de Pareto (minimisation des deux métriques).

    Un trial est dominant si aucun autre ne le bat sur les deux métriques en même temps.
    """
    survived = [t for t in trials if t.get("result") == "survived"]

    def _get(t: dict, k: str) -> float:
        return t.get("metrics", {}).get(k, math.inf)

    front = []
    for t in survived:
        x, y = _get(t, metric_x), _get(t, metric_y)
        dominated = any(
            _get(other, metric_x) <= x and _get(other, metric_y) <= y and other is not t
            for other in survived
        )
        if not dominated:
            front.append(t)
    return sorted(front, key=lambda t: _get(t, metric_x))


# ── Affichage texte ───────────────────────────────────────────────────────────

def print_table(trials: list[dict[str, Any]], top: int = 10) -> None:
    """Affiche un tableau récapitulatif dans le terminal."""
    header = f"{'#':>3}  {'kp':>6}  {'ki':>6}  {'kd':>7}  {'rms°':>6}  {'max°':>6}  {'settle s':>8}  {'sat%':>5}  {'E':>5}  {'résultat'}"
    print(header)
    print("-" * len(header))
    for rank, t in enumerate(trials[:top], 1):
        tr = t["trial"]
        m  = t.get("metrics", {})
        print(
            f"{rank:>3}  {tr['kp']:>6.3f}  {tr['ki']:>6.3f}  {tr['kd']:>7.4f}"
            f"  {m.get('rms_deg', float('nan')):>6.3f}"
            f"  {m.get('max_abs_deg', float('nan')):>6.3f}"
            f"  {m.get('settling_time_s', float('nan')):>8.3f}"
            f"  {m.get('saturation_pct', float('nan')):>5.1f}"
            f"  {m.get('energy', float('nan')):>5.3f}"
            f"  {t.get('result', '?')}"
        )


# ── Tracés matplotlib ─────────────────────────────────────────────────────────

def plot_all(
    trials: list[dict[str, Any]],
    output: str | None = None,
) -> None:
    """Génère 3 graphiques : overlay pitch, heatmap stabilité, front de Pareto."""
    try:
        import matplotlib
        if output:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        from matplotlib.colors import Normalize
    except ImportError:
        print("matplotlib non disponible. Installer avec : pip install matplotlib", file=sys.stderr)
        return

    survived = [t for t in trials if t.get("result") == "survived"]
    all_t    = [t for t in trials]

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle("Sweep PID — Analyse comparative", fontsize=13, fontweight="bold")

    # ── 1. Overlay pitch ───────────────────────────────────────────────────
    ax1 = axes[0]
    if survived:
        rms_values = [t["metrics"]["rms_deg"] for t in survived]
        rms_min, rms_max = min(rms_values), max(rms_values)
        norm = Normalize(vmin=rms_min, vmax=rms_max)
        cmap = cm.RdYlGn_r  # rouge=mauvais, vert=bon

        for t in survived:
            samples = t.get("samples", [])
            if not samples:
                continue
            ts  = np.array([s["t_s"]   for s in samples])
            pts = np.array([s["pitch"] for s in samples])
            rms = t["metrics"]["rms_deg"]
            col = cmap(norm(rms))
            tr  = t["trial"]
            ax1.plot(ts, pts, color=col, alpha=0.7, linewidth=1.2,
                     label=f"kp={tr['kp']:.3f} kd={tr['kd']:.4f} rms={rms:.2f}°")

        ax1.axhline(0, color="white", linewidth=0.8, linestyle="--", alpha=0.5)
        ax1.axhline(2,  color="gray", linewidth=0.5, linestyle=":", alpha=0.5)
        ax1.axhline(-2, color="gray", linewidth=0.5, linestyle=":", alpha=0.5)
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        fig.colorbar(sm, ax=ax1, label="RMS (°)")

    ax1.set_xlabel("Temps (s)")
    ax1.set_ylabel("Pitch (°)")
    ax1.set_title(f"Overlay pitch — {len(survived)} essais réussis")
    ax1.set_facecolor("#1e1e1e")
    ax1.grid(True, alpha=0.2)

    # ── 2. Heatmap stabilité Kp × Kd ──────────────────────────────────────
    ax2 = axes[1]
    kp_arr, kd_arr, grid = stability_map(all_t)

    if len(kp_arr) > 1 and len(kd_arr) > 1:
        im = ax2.imshow(
            grid,
            aspect="auto",
            origin="lower",
            cmap="RdYlGn_r",
            interpolation="nearest",
        )
        ax2.set_xticks(range(len(kd_arr)))
        ax2.set_xticklabels([f"{v:.4f}" for v in kd_arr], rotation=45, ha="right", fontsize=7)
        ax2.set_yticks(range(len(kp_arr)))
        ax2.set_yticklabels([f"{v:.3f}" for v in kp_arr], fontsize=7)
        fig.colorbar(im, ax=ax2, label="RMS (°)")
        # Annoter les cellules avec la valeur RMS
        for i in range(len(kp_arr)):
            for j in range(len(kd_arr)):
                val = grid[i, j]
                if not math.isnan(val):
                    ax2.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=6)
    else:
        ax2.text(0.5, 0.5, "Grille insuffisante\n(besoin ≥ 2 valeurs Kp et Kd)",
                 ha="center", va="center", transform=ax2.transAxes)

    ax2.set_xlabel("Kd")
    ax2.set_ylabel("Kp")
    ax2.set_title("Heatmap stabilité Kp × Kd (RMS °)")

    # ── 3. Front de Pareto ─────────────────────────────────────────────────
    ax3 = axes[2]
    if survived:
        xs = [t["metrics"].get("max_abs_deg",    float("nan")) for t in survived]
        ys = [t["metrics"].get("settling_time_s", float("nan")) for t in survived]
        ax3.scatter(xs, ys, c="steelblue", alpha=0.6, s=40, label="Tous essais")

        front = pareto_front(survived)
        if front:
            fx = [t["metrics"].get("max_abs_deg",    float("nan")) for t in front]
            fy = [t["metrics"].get("settling_time_s", float("nan")) for t in front]
            ax3.scatter(fx, fy, c="lime", s=80, zorder=5, label="Front Pareto")
            # Annoter les points Pareto
            for t, x, y in zip(front, fx, fy):
                tr = t["trial"]
                ax3.annotate(
                    f"kp={tr['kp']:.2f}\nkd={tr['kd']:.3f}",
                    (x, y), textcoords="offset points", xytext=(5, 5), fontsize=6,
                )

    ax3.set_xlabel("Max |pitch| (°)")
    ax3.set_ylabel("Settling time (s)")
    ax3.set_title("Front de Pareto  (overshoot vs settling)")
    ax3.legend(fontsize=8)
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()
    if output:
        plt.savefig(output, dpi=150, bbox_inches="tight")
        print(f"Rapport sauvegardé : {output}")
    else:
        plt.show()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse des sweeps PID")
    parser.add_argument("directory",      help="Dossier contenant les fichiers sweep JSON")
    parser.add_argument("--plot",         action="store_true", help="Afficher les graphiques")
    parser.add_argument("--top",          type=int, default=10, help="Nombre de trials à afficher")
    parser.add_argument("--key",          default="rms_deg",   help="Métrique de classement")
    parser.add_argument("--output",       default=None,        help="Sauvegarder le graphique (PNG)")
    parser.add_argument("--all",          action="store_true", help="Inclure les essais non-survived")
    args = parser.parse_args()

    trials = load_sweeps(args.directory)
    if not trials:
        print(f"Aucun fichier sweep trouvé dans : {args.directory}")
        sys.exit(1)

    print(f"\n{len(trials)} essais chargés depuis {args.directory}")
    survived = sum(1 for t in trials if t.get("result") == "survived")
    print(f"  survived: {survived}  /  total: {len(trials)}\n")

    ranked = rank_trials(trials, key=args.key, survived_only=not args.all)
    print(f"Top {args.top} par '{args.key}' :")
    print_table(ranked, top=args.top)

    front = pareto_front(trials)
    if front:
        print(f"\nFront de Pareto ({len(front)} points) :")
        print_table(front, top=len(front))

    if args.plot or args.output:
        plot_all(trials, output=args.output)


if __name__ == "__main__":
    main()
