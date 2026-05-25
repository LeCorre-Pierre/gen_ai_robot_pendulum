#!/usr/bin/env python3
"""
Reglage PID manuel -- moteurs DC -- cible 50 RPM, COM4.

Methode :
  Etape 1 -- Baseline avec les gains par defaut du firmware
  Etape 2 -- Balayage Kp seul (Ki=0) : trouve la reactivite P pure
  Etape 3 -- Balayage Ki avec le meilleur Kp : elimine l'erreur statique
  Etape 4 -- Tableau recapitulatif et recommandation finale

Protocole VCP utilise (pas d'optimizer automatique) :
  MOTOR_ENABLE -> SET_GAINS -> STREAM_CTRL(start) -> SET_SP(50) ->
  record 3 s -> SET_SP(0) -> MOTOR_COAST -> STREAM_CTRL(stop)
"""

from __future__ import annotations

import sys
import os
import time
from dataclasses import dataclass

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pid_tuner.robot_client import RobotClient

# ── Parametres de seance ───────────────────────────────────────────────────────
PORT          = "COM4"
BAUD          = 115200
TARGET_RPM    = 50
STREAM_HZ     = 50      # Hz telemetrie
STEP_DUR      = 5.0     # secondes d'enregistrement par test (assez long pour integrale)
REST_DUR      = 2.5     # pause entre tests pour que le moteur s'arrete
TOL_PCT       = 5.0     # tolerance +/-5 % pour le temps d'etablissement

# Infos firmware (motor_control.h)
MTR_MAX_RPM   = 250.0
DEADBAND      = 0.15    # 15 % pleine echelle


# ── Metriques de reponse indicielle ───────────────────────────────────────────

@dataclass
class StepResult:
    kp:              float
    ki:              float
    kd:              float
    rise_time_s:     float   # temps pour atteindre la consigne la 1re fois
    overshoot_pct:   float   # depassement en %
    settling_time_s: float   # dernier instant ou |pv - sp| > tolerance
    steady_error:    float   # erreur moyenne sur les 20 % finaux (RPM)
    n_samples:       int


def analyze(samples: list, sp: int) -> "StepResult | None":
    """Calcule les metriques d'une reponse indicielle a partir des telemetries."""
    if not samples:
        return None

    t0   = samples[0].timestamp_ms
    ts   = np.array([(s.timestamp_ms - t0) / 1000.0 for s in samples])
    pv_l = np.array([float(s.pv_l_rpm) for s in samples])
    pv_r = np.array([float(s.pv_r_rpm) for s in samples])
    pv   = (pv_l + pv_r) / 2.0
    sp_f = float(sp)
    tol  = abs(sp_f) * TOL_PCT / 100.0

    # Temps de montee : premier depassement de la consigne
    above = np.where(pv >= sp_f)[0]
    rise  = float(ts[above[0]]) if len(above) else float(ts[-1])

    # Depassement maximum
    peak      = float(np.max(pv))
    overshoot = max(0.0, (peak - abs(sp_f)) / abs(sp_f) * 100.0)

    # Temps d'etablissement : dernier indice hors tolerance
    outside  = np.where(np.abs(pv - sp_f) > tol)[0]
    settling = float(ts[outside[-1]]) if len(outside) else 0.0

    # Erreur statique : moyenne des 20 % finaux
    tail   = max(0, int(len(pv) * 0.80))
    steady = float(np.mean(np.abs(pv[tail:] - sp_f))) if tail < len(pv) else 999.0

    return StepResult(0.0, 0.0, 0.0, rise, overshoot, settling, steady, len(samples))


def cost(r: StepResult) -> float:
    """Cout scalaire pour comparer les resultats (plus bas = mieux)."""
    return r.overshoot_pct * 0.5 + r.settling_time_s * 2.0 + r.steady_error * 0.1


# ── Execution d'un test ────────────────────────────────────────────────────────

def run_test(
    client:  RobotClient,
    kp:      float,
    ki:      float,
    kd:      float = 0.0,
    label:   str   = "",
) -> "StepResult | None":
    """
    Execute un test de reponse indicielle complet et imprime les resultats.

    Sequence :
      1. SET_GAINS(both, kp, ki, kd)
      2. MOTOR_ENABLE   (mode velocity PID)
      3. drain + START_STREAM(50 Hz)
      4. SET_SP(50 RPM)  (echelon)
      5. Enregistrement 3 s
      6. SET_SP(0) + MOTOR_COAST + STOP_STREAM
      7. Analyse metriques
    """
    lbl = label or "Kp={:.4f}  Ki={:.5f}  Kd={:.4f}".format(kp, ki, kd)
    print("")
    print("  " + "-" * 64)
    print("  TEST : " + lbl)
    print("  " + "-" * 64)

    # 1. Appliquer les gains
    init_p = kp * TARGET_RPM
    flag   = "OK > deadband" if init_p > DEADBAND else "WARN: sous deadband -- moteur immobile!"
    print("  [1] SET_GAINS both  Kp={:.4f}  Ki={:.5f}  Kd={:.4f}".format(kp, ki, kd))
    print("      Sortie P initiale prevue : {:.4f} x {} = {:.3f}  [{}]".format(
        kp, TARGET_RPM, init_p, flag))

    if not client.set_gains("both", kp, ki, kd):
        print("      FAIL: Timeout ACK -- robot ne repond pas, test abandonne")
        return None
    print("      ACK OK")

    # 2. Activer le mode velocity (PID ferme)
    print("  [2] MOTOR_ENABLE -> mode velocity (MTR_SetControlMode + PID_Reset)")
    client.motor_enable()
    time.sleep(0.15)

    # 3. Purge + demarrage telemetrie
    client.drain_telemetry()
    print("  [3] STREAM_CTRL start @ {} Hz".format(STREAM_HZ))
    client.start_stream(STREAM_HZ)
    time.sleep(0.05)

    # 4. Echelon de consigne
    print("  [4] SET_SP -> {} RPM  (sp_norm = {}/{} = {:.2f})".format(
        TARGET_RPM, TARGET_RPM, int(MTR_MAX_RPM), TARGET_RPM / MTR_MAX_RPM))
    client.set_setpoint(TARGET_RPM)

    # 5. Enregistrement
    print("  [5] Enregistrement {} s @ {} Hz -> ~{} echantillons attendus".format(
        STEP_DUR, STREAM_HZ, int(STEP_DUR * STREAM_HZ)))
    samples = client.record_telemetry(STEP_DUR)

    # 6. Arret propre
    print("  [6] SET_SP(0) + MOTOR_COAST + STOP_STREAM")
    client.set_setpoint(0)
    time.sleep(0.1)
    client.motor_coast()
    client.stop_stream()

    if not samples:
        print("  FAIL: Aucun echantillon recu (telemetrie inactive?)")
        time.sleep(REST_DUR)
        return None

    # 7. Analyse
    r = analyze(samples, TARGET_RPM)
    if r is None:
        time.sleep(REST_DUR)
        return None
    r.kp = kp
    r.ki = ki
    r.kd = kd

    print("")
    print("  Resultats ({} echantillons) :".format(r.n_samples))
    print("    Temps de montee          : {:.3f} s".format(r.rise_time_s))
    print("    Depassement max          : {:.1f} %".format(r.overshoot_pct))
    print("    Temps d'etabl. (+/-{}%)   : {:.3f} s".format(int(TOL_PCT), r.settling_time_s))
    print("    Erreur statique (20% fin): {:.1f} RPM".format(r.steady_error))
    print("    Cout (OS*0.5+Ts*2+ES*0.1): {:.2f}".format(cost(r)))

    # Diagnostic rapide
    notes = []
    if r.rise_time_s >= STEP_DUR - 0.1:
        notes.append("n'atteint jamais la cible -> Kp trop faible ou deadband")
    if r.overshoot_pct > 30:
        notes.append("depassement severe -> reduire Kp")
    elif r.overshoot_pct > 15:
        notes.append("depassement modere")
    if r.steady_error > 5 and ki < 0.001:
        notes.append("erreur statique attendue (Ki=0)")
    elif r.steady_error > 5:
        notes.append("erreur statique > 5 RPM -> augmenter Ki")
    if r.settling_time_s > 2.0:
        notes.append("temps d'etablissement long")
    if r.rise_time_s < 0.5 and r.overshoot_pct < 10 and r.steady_error < 3:
        notes.append("*** Excellente reponse! ***")
    elif r.rise_time_s < 1.0 and r.overshoot_pct < 20 and r.steady_error < 5:
        notes.append("-- Bonne reponse")
    if notes:
        print("    Diagnostic               : " + " | ".join(notes))

    print("")
    print("  Pause {} s (attente arret moteur)...".format(REST_DUR))
    time.sleep(REST_DUR)
    return r


# ── Tableau recapitulatif ──────────────────────────────────────────────────────

def print_table(results: list) -> None:
    print("")
    print("=" * 86)
    print("  TABLEAU RECAPITULATIF -- TOUS LES TESTS")
    print("=" * 86)
    print("  {:<26}  {:>7}  {:>8}  {:>8}  {:>6}  {:>8}  {:>7}  {:>7}".format(
        "Label", "Kp", "Ki", "Montee", "OS%", "Etabl.", "ErrSS", "Cout"))
    print("  " + "-" * 82)
    for label, r in results:
        c = cost(r)
        print("  {:<26}  {:>7.4f}  {:>8.5f}  {:>7.3f}s  {:>5.1f}%  {:>7.3f}s  {:>6.1f}R  {:>7.2f}".format(
            label, r.kp, r.ki, r.rise_time_s, r.overshoot_pct,
            r.settling_time_s, r.steady_error, c))


# ── Point d'entree ─────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 68)
    print("  REGLAGE PID MANUEL -- MOTEURS DC -- CIBLE 50 RPM")
    print("=" * 68)
    print("")
    print("  Port  : {} @ {} baud".format(PORT, BAUD))
    print("  Cible : {} RPM  (= {:.0%} de MTR_MAX_RPM={})".format(
        TARGET_RPM, TARGET_RPM / MTR_MAX_RPM, int(MTR_MAX_RPM)))
    print("  Duree test : {} s  |  Pause : {} s  |  Tel. : {} Hz".format(
        STEP_DUR, REST_DUR, STREAM_HZ))
    print("  Deadband PWM : {:.0f}%  ->  Kp_min ~= {:.4f}".format(
        DEADBAND * 100, DEADBAND / TARGET_RPM))

    print("")
    print("  Connexion au robot...")
    client = RobotClient(PORT, BAUD)
    try:
        client.connect()
        print("  OK Connexion etablie sur " + PORT)
    except Exception as exc:
        print("  FAIL Impossible de se connecter : {}".format(exc))
        sys.exit(1)

    results: list = []

    try:
        # ──────────────────────────────────────────────────────────────────────
        # ETAPE 1 -- BASELINE (gains par defaut firmware)
        # ──────────────────────────────────────────────────────────────────────
        print("")
        print("=" * 68)
        print("  ETAPE 1 -- BASELINE : gains par defaut du firmware")
        print("  Kp = 0.0040   Ki = 0.0020   Kd = 0")
        print("=" * 68)
        print("""
  Objectif : mesurer les performances avec les valeurs initiales
  definies dans motor_control.h (MTR_VEL_KP_DEFAULT / KI_DEFAULT).
  Cette reference sert a evaluer le gain apporte par le reglage.
        """.rstrip())

        r = run_test(client, 0.0040, 0.0020, label="Defauts Kp=.004 Ki=.002")
        if r:
            results.append(("1-Defauts", r))

        # ──────────────────────────────────────────────────────────────────────
        # ETAPE 2 -- BALAYAGE Kp SEUL (Ki = 0)
        # ──────────────────────────────────────────────────────────────────────
        print("")
        print("=" * 68)
        print("  ETAPE 2 -- BALAYAGE Kp (Ki = 0, Kd = 0)")
        print("=" * 68)
        print("""
  Avec Ki=0 le regulateur est purement proportionnel.
  L'erreur statique sera non-nulle (normal : pas d'integrale),
  mais on observe la reactivite brute.

  Regle deadband : Kp x 50 RPM > 0.15  ->  Kp > 0.003
  Regle saturation: Kp x 50 RPM < 1.0  ->  Kp < 0.020
  (Au-dessus la sortie P seule sature a 100% des le debut)

  Candidats : 0.010  0.015  0.020  0.025  0.035  0.050
        """.rstrip())

        kp_candidates = [0.010, 0.015, 0.020, 0.025, 0.035, 0.050]
        kp_results: list = []

        for kp in kp_candidates:
            r = run_test(client, kp, 0.0, label="Kp={:.3f} Ki=0".format(kp))
            if r:
                results.append(("2-Kp={:.3f} Ki=0".format(kp), r))
                kp_results.append((kp, r))

        # Selection du meilleur Kp :
        # Avec P seul, aucun test n'atteint 50 RPM (friction du reducteur 29:1).
        # On choisit le Kp qui minimise l'erreur statique — c'est le plus reactif
        # et celui qui laisse le moins de travail a l'integrateur.
        if kp_results:
            best_kp, _ = min(kp_results, key=lambda x: x[1].steady_error)
        else:
            best_kp = 0.025

        print("")
        print("  -> Kp optimal retenu pour l'etape 3 : Kp = {:.3f}".format(best_kp))
        print("     (critere : montee rapide ET depassement < 30 %)")

        # ──────────────────────────────────────────────────────────────────────
        # ETAPE 3 -- BALAYAGE Ki (avec le meilleur Kp)
        # ──────────────────────────────────────────────────────────────────────
        print("")
        print("=" * 68)
        print("  ETAPE 3 -- BALAYAGE Ki (Kp fixe, Kd = 0)")
        print("=" * 68)
        print("""
  On fixe Kp = {:.3f} (trouve a l'etape 2).
  L'integrateur accumule : integ += Ki x erreur x 0.005 s
  a chaque cycle 200 Hz.  Un Ki trop fort -> oscillations.

  Estimatif : pour corriger 10 RPM d'erreur statique en ~0.5 s,
  on a besoin que Ki x 10 x 0.005 x 100 cycles ~= 0.05
  -> Ki ~= 0.01 (ordre de grandeur).

  Anti-windup actif dans le firmware (recul de l'integrateur
  quand la sortie sature).

  Candidats Ki : 0.010  0.020  0.040  0.060  0.080  0.120
        """.format(best_kp).rstrip())

        ki_candidates = [0.010, 0.020, 0.040, 0.060, 0.080, 0.120]
        ki_results: list = []

        for ki in ki_candidates:
            r = run_test(client, best_kp, ki,
                         label="Kp={:.3f} Ki={:.4f}".format(best_kp, ki))
            if r:
                results.append(("3-Kp={:.3f} Ki={:.4f}".format(best_kp, ki), r))
                ki_results.append((ki, r))

        # ──────────────────────────────────────────────────────────────────────
        # ETAPE 4 -- RECOMMANDATION FINALE
        # ──────────────────────────────────────────────────────────────────────
        print_table(results)

        if ki_results:
            best_ki, best_r = min(ki_results, key=lambda x: cost(x[1]))

            print("")
            print("=" * 68)
            print("  RECOMMANDATION FINALE")
            print("=" * 68)
            print("  Kp = {:.4f}".format(best_kp))
            print("  Ki = {:.5f}".format(best_ki))
            print("  Kd = 0.000")
            print("")
            print("  Performances mesurees :")
            print("    Temps de montee  : {:.3f} s".format(best_r.rise_time_s))
            print("    Depassement      : {:.1f} %".format(best_r.overshoot_pct))
            print("    Temps d'etabl.   : {:.3f} s".format(best_r.settling_time_s))
            print("    Erreur statique  : {:.1f} RPM".format(best_r.steady_error))
            print("    Cout             : {:.2f}".format(cost(best_r)))
            print("")
            print("  Pour perenniser ces gains dans le firmware, modifier")
            print("  emb-sw/Utilities/MotorControl/motor_control.h :")
            print("    #define MTR_VEL_KP_DEFAULT  {:.4f}f".format(best_kp))
            print("    #define MTR_VEL_KI_DEFAULT  {:.5f}f".format(best_ki))
            print("    #define MTR_VEL_KD_DEFAULT  0.00000f")
        else:
            print("")
            print("  WARN: Aucun resultat exploitable -- verifier la connexion moteurs.")

    except KeyboardInterrupt:
        print("")
        print("  WARN: Interruption -- arret d'urgence moteurs...")
        client.motor_coast()
        client.stop_stream()

    finally:
        client.disconnect()
        print("")
        print("  Connexion fermee.")


if __name__ == "__main__":
    main()
