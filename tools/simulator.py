"""
tools/simulator.py — Simulation discrète du pendule inversé + PID.

Modèle :  θ̈ = a·θ + b·u + c·θ̇
Intégration RK4 à pas fixe dt.

Usage (module) :
    from simulator import InvertedPendulumSim, PIDController, simulate_trial
    sim = InvertedPendulumSim(a=15.0, b=-20.0, c=-0.5, dt=0.005)
    pid = PIDController(kp=0.15, ki=0.0, kd=0.03, dt=0.005)
    result = simulate_trial(sim, pid, duration_s=1.0, theta0_deg=2.0)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


# ── Modèle du pendule (intégration RK4) ──────────────────────────────────────

@dataclass
class InvertedPendulumSim:
    """Pendule inversé sur roues — modèle grey-box θ̈ = a·θ + b·u + c·θ̇."""

    a:  float   # g/L_eff  > 0
    b:  float   # Km/J     (souvent < 0 si convention : u>0 → roue avance → penche en avant)
    c:  float   # -fric/J  ≤ 0
    dt: float   # pas d'intégration en secondes

    def ode(self, theta: float, dtheta: float, u: float) -> tuple[float, float]:
        """dθ/dt et dθ̇/dt."""
        ddtheta = self.a * theta + self.b * u + self.c * dtheta
        return dtheta, ddtheta

    def step(self, theta: float, dtheta: float, u: float) -> tuple[float, float]:
        """Avance d'un pas dt par intégration RK4."""
        dt = self.dt
        k1_th, k1_dth = self.ode(theta,                    dtheta,                    u)
        k2_th, k2_dth = self.ode(theta + 0.5*dt*k1_th,    dtheta + 0.5*dt*k1_dth,    u)
        k3_th, k3_dth = self.ode(theta + 0.5*dt*k2_th,    dtheta + 0.5*dt*k2_dth,    u)
        k4_th, k4_dth = self.ode(theta + dt*k3_th,         dtheta + dt*k3_dth,         u)

        theta_new  = theta  + (dt / 6.0) * (k1_th  + 2*k2_th  + 2*k3_th  + k4_th)
        dtheta_new = dtheta + (dt / 6.0) * (k1_dth + 2*k2_dth + 2*k3_dth + k4_dth)
        return theta_new, dtheta_new


# ── Contrôleur PID discret ────────────────────────────────────────────────────

@dataclass
class PIDController:
    """PID discret avec anti-windup et dérivée sur la mesure."""

    kp:       float
    ki:       float
    kd:       float
    dt:       float
    out_min:  float = -1.0
    out_max:  float =  1.0
    int_min:  float = -0.5
    int_max:  float =  0.5

    _integrator:    float = field(default=0.0, init=False, repr=False)
    _prev_meas:     float = field(default=0.0, init=False, repr=False)

    def reset(self) -> None:
        self._integrator = 0.0
        self._prev_meas  = 0.0

    def update(self, setpoint: float, measurement: float) -> float:
        """Retourne la commande PID pour un cycle."""
        error = setpoint - measurement

        p_term = self.kp * error
        self._integrator = max(self.int_min, min(self.int_max,
                               self._integrator + self.ki * error * self.dt))
        i_term = self._integrator
        d_term = -self.kd * (measurement - self._prev_meas) / self.dt

        output = p_term + i_term + d_term
        output = max(self.out_min, min(self.out_max, output))

        # Anti-windup : annuler l'accumulation si saturé dans le mauvais sens
        if (output >= self.out_max and error > 0) or (output <= self.out_min and error < 0):
            self._integrator -= self.ki * error * self.dt

        self._prev_meas = measurement
        return output


# ── Métriques (même définition que run_sweep) ────────────────────────────────

def _compute_sim_metrics(
    t_arr:     list[float],
    theta_deg: list[float],
    u_arr:     list[float],
    t_start:   float = 0.0,
) -> dict[str, float]:
    import numpy as np
    t  = np.array(t_arr)
    p  = np.array(theta_deg)
    u  = np.array(u_arr)
    m  = t >= t_start
    if m.sum() == 0:
        return {}
    pt, ut = p[m], u[m]
    rms     = float(np.sqrt(np.mean(pt ** 2)))
    max_abs = float(np.max(np.abs(pt)))
    energy  = float(np.mean(np.abs(ut)))
    sat_pct = float(100.0 * np.mean(np.abs(ut) > 0.9))

    idxs = np.where(np.abs(pt) > 2.0)[0]
    settling = float(t[m][idxs[-1]] - t_start) if len(idxs) else 0.0

    return {
        "rms_deg":         round(rms,     3),
        "max_abs_deg":     round(max_abs, 3),
        "settling_time_s": round(settling, 3),
        "saturation_pct":  round(sat_pct,  1),
        "energy":          round(energy,   3),
    }


# ── Simulation d'un essai complet ─────────────────────────────────────────────

def simulate_trial(
    sim: InvertedPendulumSim,
    pid: PIDController,
    duration_s: float = 1.5,
    theta0_deg: float = 2.0,
    fall_threshold_deg: float = 45.0,
) -> dict:
    """Simule un essai et retourne le même format que les fichiers sweep JSON.

    Args:
        theta0_deg:         Angle initial (°) — simule le lâcher du robot
        fall_threshold_deg: Seuil de chute → résultat 'early_stop'
    """
    pid.reset()
    theta  = math.radians(theta0_deg)
    dtheta = 0.0
    n      = int(duration_s / sim.dt)

    t_list:     list[float] = []
    theta_list: list[float] = []
    u_list:     list[float] = []

    result = "survived"
    for i in range(n):
        t = i * sim.dt
        u = pid.update(0.0, theta)   # setpoint = 0° (équilibre)

        theta_deg = math.degrees(theta)
        t_list.append(round(t, 4))
        theta_list.append(round(theta_deg, 4))
        u_list.append(round(u, 5))

        if abs(theta_deg) > fall_threshold_deg:
            result = "early_stop"
            break

        theta, dtheta = sim.step(theta, dtheta, u)

    metrics = _compute_sim_metrics(t_list, theta_list, u_list, t_start=0.0)

    return {
        "result":  result,
        "metrics": metrics,
        "samples": [
            {"t_s": t, "pitch": p, "drive": u}
            for t, p, u in zip(t_list, theta_list, u_list)
        ],
    }
