"""
Step-response analysis and Nelder-Mead PID optimization.

analyze_step()   — compute overshoot, settling time, rise time, steady-state error
optimize_pid()   — automated Kp/Ki sweep using scipy minimize
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.optimize import minimize

from .robot_client import RobotClient
from . import protocol as P


# ── Metrics ────────────────────────────────────────────────────────────────────

@dataclass
class StepMetrics:
    overshoot_pct:   float   # (peak − |sp|) / |sp| × 100, 0 if none
    settling_time_s: float   # last time |pv − sp| > tolerance
    steady_error:    float   # mean |pv − sp| over last 20 % of recording (RPM)
    rise_time_s:     float   # time to first reach setpoint (s), ∞ if never
    n_samples:       int


def analyze_step(
    samples: list,
    setpoint: int,
    tolerance_pct: float = 5.0,
) -> StepMetrics:
    """
    Analyse a list of TelemetryPID samples from a step-response recording.
    Uses the average of pv_l_rpm and pv_r_rpm as the measured variable.
    """
    if not samples:
        return StepMetrics(999.0, 999.0, 999.0, 999.0, 0)

    t0   = samples[0].timestamp_ms
    ts   = np.array([(s.timestamp_ms - t0) / 1000.0 for s in samples])
    pv_l = np.array([s.pv_l_rpm for s in samples], dtype=float)
    pv_r = np.array([s.pv_r_rpm for s in samples], dtype=float)
    pv   = (pv_l + pv_r) / 2.0
    sp   = float(setpoint)

    if abs(sp) < 1e-6:
        return StepMetrics(0.0, 0.0, float(np.mean(np.abs(pv))), 0.0, len(samples))

    tol_abs = abs(sp) * tolerance_pct / 100.0

    # Rise time: first time pv crosses setpoint from below (positive sp)
    if sp > 0:
        cross_idx = np.where(pv >= sp)[0]
    else:
        cross_idx = np.where(pv <= sp)[0]
    rise_time = float(ts[cross_idx[0]]) if len(cross_idx) else float(ts[-1])

    # Overshoot: max absolute excursion beyond setpoint
    peak = float(np.max(np.abs(pv))) if sp > 0 else float(np.min(pv))
    overshoot = max(0.0, (abs(peak) - abs(sp)) / abs(sp) * 100.0)

    # Settling time: last index where error exceeds tolerance
    outside = np.where(np.abs(pv - sp) > tol_abs)[0]
    settling = float(ts[outside[-1]]) if len(outside) else 0.0

    # Steady-state error: mean absolute error over final 20 %
    tail_start = max(0, int(len(pv) * 0.80))
    steady = float(np.mean(np.abs(pv[tail_start:] - sp))) if tail_start < len(pv) else 999.0

    return StepMetrics(overshoot, settling, steady, rise_time, len(samples))


# ── Optimization ───────────────────────────────────────────────────────────────

ProgressCallback = Callable[[int, float, float, float, StepMetrics], None]


def optimize_pid(
    client: RobotClient,
    motor: str | int,
    target_rpm: int,
    duration_s: float = 2.0,
    stream_rate_hz: int = 50,
    max_iter: int = 30,
    progress_cb: ProgressCallback | None = None,
) -> tuple[float, float, float, StepMetrics]:
    """
    Optimize (Kp, Ki) using Nelder-Mead to minimise a cost function that
    combines overshoot, settling time and steady-state error.

    Cost = overshoot_pct × 0.5 + settling_time_s × 2.0 + steady_error × 0.1

    Returns: (kp_opt, ki_opt, kd=0.0, final_metrics)
    """
    iteration = [0]

    def _run_step(kp: float, ki: float) -> tuple[list, StepMetrics]:
        client.set_gains(motor, kp, ki, 0.0)
        client.motor_enable()
        client.drain_telemetry()
        client.start_stream(stream_rate_hz)
        client.set_setpoint(target_rpm)
        samples = client.record_telemetry(duration_s)
        client.set_setpoint(0)
        client.motor_coast()
        return samples, analyze_step(samples, target_rpm)

    def cost(gains: np.ndarray) -> float:
        kp = max(0.0, float(gains[0]))
        ki = max(0.0, float(gains[1]))
        _, metrics = _run_step(kp, ki)
        c = (metrics.overshoot_pct * 0.5
             + metrics.settling_time_s * 2.0
             + metrics.steady_error * 0.1)
        iteration[0] += 1
        if progress_cb:
            progress_cb(iteration[0], kp, ki, c, metrics)
        return c

    x0 = np.array([0.004, 0.002])
    result = minimize(
        cost, x0,
        method='Nelder-Mead',
        options={'maxiter': max_iter, 'xatol': 1e-5, 'fatol': 0.05, 'disp': False},
    )

    kp_opt = max(0.0, float(result.x[0]))
    ki_opt = max(0.0, float(result.x[1]))

    # Final validation run with optimal gains
    client.set_gains(motor, kp_opt, ki_opt, 0.0)
    _, final_metrics = _run_step(kp_opt, ki_opt)

    return kp_opt, ki_opt, 0.0, final_metrics
