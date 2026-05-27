# Régulation — Architecture MB1292B

**Version:** 1.0  
**Date:** 2026-05-26  

---

## 1. Vue d'ensemble

Le robot utilise une **régulation en cascade** à trois boucles imbriquées, toutes exécutées sur le Cortex-M4 du STM32WB5MMG à **200 Hz** (période 5 ms).

```
                    ┌──────────────────────────────────────────────────────┐
  Commande          │               Boucle de contrôle @ 200 Hz            │
  (BLE/VCP)         │                                                      │
  ─────────►  vel_target ──► [Boucle vitesse] ──► angle_target             │
                    │              (PID 1)                                  │
                    │                         angle_target ──► [Boucle angle] ──► drive_output
                    │                                  (PID 2)             │
                    │         yaw_target  ──► [Boucle yaw]  ──► yaw_output │
                    │                              (PID 3)                  │
                    │                                                       │
                    │         drive_output + yaw_output ──► moteur gauche  │
                    │         drive_output - yaw_output ──► moteur droit   │
                    └──────────────────────────────────────────────────────┘
```

---

## 2. Chaîne de mesure

```
ISM330DHCX (I2C3)
    │
    ├── Accéléromètre (mg)  ──┐
    │                         ├──► AngleEstimator (filtre complémentaire) ──► pitch_deg
    └── Gyroscope (mdps)   ──┘
            │
            └── gyro_y_dps ──────────────────────────────────────────────► yaw_rate

Encodeur gauche (TIM1 QEI) ──┐
                              ├──► moyenne ──► vel_avg_rpm
Encodeur droit  (TIM2 QEI) ──┘
```

### 2.1 Filtre complémentaire (AngleEstimator)

```
angle[n] = α × (angle[n-1] + gyro_pitch_dps × dt)
         + (1 − α) × atan2(accel_pitch, accel_gravity) × (180/π)
```

| Paramètre | Valeur | Rôle |
|-----------|--------|------|
| `α` (alpha) | 0.98 | Poids du gyroscope — haute fréquence fiable, pas de drift |
| `1 − α` | 0.02 | Poids de l'accéléromètre — corrige le drift sur le long terme |
| `dt` | 5 ms | Période de la boucle |

**Mapping axes BSP → rôle physique** (confirmé 2026-05-26 via `tools/imu_viewer.py`) :

| Rôle physique | Axe BSP | Variable firmware | Valeur upright |
|---------------|---------|-------------------|----------------|
| Gravité (vertical) | **Ay** | `imu.accel_y_g` | ≈ +1.0 g |
| Tangage accel | **Az** | `imu.accel_z_g` | ≈  0.0 g, change avec inclinaison |
| Tangage gyro (pitch rate) | **Gx** | `imu.gyro_x_dps` | ≈  0 °/s |
| Lacet gyro (yaw rate) | **Gy** | `imu.gyro_y_dps` | ≈  0 °/s |

> **Convention de signe (confirmée 2026-05-26) :** Az et Gx sont négés à l'entrée du filtre
> pour que **inclinaison avant → pitch positif**. Voir `task_control.c`.

### 2.2 Mesure de vitesse (encodeurs)

```
vel_rpm = (Δticks / MTR_ENC_TICKS_PER_REV) / dt × 60
        = (Δticks / 7424) / 0.005 × 60
```

La vitesse moyenne des deux roues est utilisée comme mesure de la boucle de vitesse :
```
vel_avg_rpm = (vel_left_rpm + vel_right_rpm) / 2
```

---

## 3. Boucles de régulation

### 3.1 Architecture cascade

```
                              ┌──────────────┐
  vel_target_rpm ──────────►  │  Boucle      │
                              │  vitesse     │──► angle_target_deg (clampé ±10°)
  vel_avg_rpm ─────────────►  │  (PID vel)   │
                              └──────────────┘
                                      │
                              ┌───────▼──────┐
  angle_target_deg ─────────► │  Boucle      │
                              │  angle       │──► drive_output (clampé ±1.0)
  pitch_deg ─────────────────►│  (PID angle) │
                              └──────────────┘

  yaw_target_rate ──────────► ┌──────────────┐
                              │  Boucle yaw  │──► yaw_output (clampé ±0.3)
  gyro_y_dps ────────────────►│  (PID yaw)   │
                              └──────────────┘

  left_output  = clamp(drive_output + yaw_output, −1.0, +1.0)
  right_output = clamp(drive_output − yaw_output, −1.0, +1.0)
```

---

### 3.2 Boucle externe — Vitesse (`velocity_pid`)

| Paramètre | Valeur par défaut | Description |
|-----------|------------------|-------------|
| Entrée setpoint | 0.0 RPM (arrêt) | Consigne en RPM roue sortie réducteur |
| Entrée mesure | `vel_avg_rpm` | Moyenne des deux roues |
| Sortie | `angle_target_deg` | Inclinaison cible pour la boucle interne |
| Plage sortie | ±10° | Max inclinaison autorisée |
| Plage intégrateur | ±5° | Anti-windup |
| Kp, Ki, Kd | **0, 0, 0** | **À tuner** |
| Fréquence | 200 Hz | Même tâche que la boucle interne |

**Interprétation physique :** si le robot recule (`vel_avg < 0`), l'erreur est positive → le contrôleur de vitesse demande une inclinaison vers l'avant (`angle_target > 0`) → la boucle d'angle commande les moteurs en avant → le robot rattrape.

---

### 3.3 Boucle interne — Angle (`angle_pid`)

| Paramètre | Valeur par défaut | Description |
|-----------|------------------|-------------|
| Entrée setpoint | `angle_target_deg` | Issu de la boucle vitesse |
| Entrée mesure | `pitch_deg` | Angle estimé (filtre complémentaire) |
| Sortie | `drive_output` | Commande PWM normalisée |
| Plage sortie | ±1.0 | Pleine échelle moteur |
| Plage intégrateur | ±0.5 | Anti-windup |
| Kp, Ki, Kd | **0, 0, 0** | **À tuner en premier** |
| Fréquence | 200 Hz | |

**C'est la boucle la plus critique.** Un Kp trop faible → le robot tombe. Trop élevé → oscillations.

**Dérivée sur mesure** (`derivative-on-measurement`) : le terme D agit sur `-d(pitch)/dt` et non sur `d(erreur)/dt`, ce qui évite les pics de commande lors d'un changement de setpoint.

---

### 3.4 Boucle yaw — Lacet (`yaw_pid`)

| Paramètre | Valeur par défaut | Description |
|-----------|------------------|-------------|
| Entrée setpoint | 0.0 dps (tout droit) | Consigne de vitesse de rotation |
| Entrée mesure | `gyro_y_dps` | Vitesse de lacet mesurée (Gy, confirmé 2026-05-26) |
| Sortie | `yaw_output` | Terme différentiel gauche/droite |
| Plage sortie | ±0.3 | Fraction de la pleine échelle |
| Plage intégrateur | ±0.2 | Anti-windup |
| Kp, Ki, Kd | **0, 0, 0** | **À tuner en dernier** |

**Application différentielle :**
```
left_output  = drive_output + yaw_output
right_output = drive_output − yaw_output
```
Un `yaw_output` positif accélère la roue gauche et freine la droite → rotation droite.

---

## 4. Chaîne de sécurité

```
pitch_deg ──► MTR_SafetyUpdate()
                  │
                  ├── |pitch| > 45° ──────────────────► MTR_EmergencyStop()
                  ├── courant gauche > 1.8 A ──────────► MTR_EmergencyStop()
                  └── courant droit  > 1.8 A ──────────► MTR_EmergencyStop()

IMU_Read() échoue 3× consécutifs ──────────────────────► MTR_EmergencyStop()
```

`MTR_EmergencyStop()` est **irréversible** : BRAKE actif sur les deux moteurs, flag bloquant tout `SetSpeed`. Seul `MTR_Init()` remet le système en état.

| Seuil | Valeur | Constante |
|-------|--------|-----------|
| Angle de chute | ±45° | `MTR_DEFAULT_TILT_CUTOFF_DEG` |
| Courant max par moteur | 1.8 A | `MTR_DEFAULT_CURRENT_LIMIT_A` |
| IMU miss consécutifs | 3 | `IMU_MAX_MISS` dans `task_control.c` |

---

## 5. Tâche FreeRTOS et timing

```
task_control (priorité 3, 200 Hz)
│
├── IMU_Read()                          ~250 µs (2× I2C 400 kHz 6 octets)
├── AngleEstimator_Update()             < 1 µs
├── MTR_SafetyUpdate()                  < 1 µs (+ ADC polling ~1 µs)
├── MTR_GetVelocityRPM() × 2           < 1 µs chacun
├── CBC_Update()                        < 1 µs
└── MTR_SetDifferential()               < 1 µs

Budget total estimé : ~270 µs / 5000 µs disponibles (5.4% charge CPU)
```

| Tâche | Priorité | Fréquence | Rôle |
|-------|---------|-----------|------|
| `task_control` | 3 (haute) | 200 Hz | Boucle de régulation principale |
| `task_comms` | 2 | événementiel | Télémétrie VCP / BLE |
| `task_display` | 1 (basse) | ~10 Hz | OLED |
| `task_safety` | stub | — | (à implémenter : watchdog) |

---

## 6. Paramètres hardware moteurs

| Paramètre | Valeur | Source |
|-----------|--------|--------|
| Résolution encodeur | 7424 ticks/tour roue | 64 CPR × 4 (QEI ×4) × 29:1 |
| Vitesse max (12 V) | ~250 RPM (roue) | Mesurée moteur libre |
| Deadband PWM | 15% | `MTR_DEFAULT_DEADBAND` |
| PWM fréquence | 20 kHz | LPTIM1 / TIM16, ARR=3199 |
| Inversion gauche | `DIR_FWD_LEFT = HIGH` | Moteurs montés côtés opposés |
| Inversion droite | `DIR_FWD_RIGHT = LOW` | |

---

## 7. Configuration IMU (ISM330DHCX)

| Paramètre | Valeur | Justification |
|-----------|--------|---------------|
| Fréquence accéléromètre | 208 Hz | ≥ boucle de contrôle (200 Hz) |
| Fréquence gyroscope | 208 Hz | Idem |
| Plage accéléromètre | ±2 g | Résolution maximale pour faibles angles |
| Plage gyroscope | ±250 dps | Suffisant pour les rotations du robot |
| Interface | I2C3, 400 kHz | PB13=SCL, PB11=SDA, adresse 0x6B |
| Driver | BSP `stm32wb5mm_dk_motion_sensors` | Fourni ST |

---

## 8. Fichiers source

| Fichier | Rôle |
|---------|------|
| `App/Src/task_control.c` | Point d'entrée de la boucle, câblage de tous les modules |
| `App/Src/imu.c` | Init ODR/full-scale + lecture axes BSP |
| `Utilities/AngleEstimator/angle_estimator.c` | Filtre complémentaire |
| `Utilities/Control/cascade_balance_controller.c` | Cascade PID (angle + vitesse + yaw) |
| `Utilities/Control/pid_controller.c` | PID générique (dérivée sur mesure, anti-windup) |
| `Utilities/MotorControl/motor_control.c` | PWM, encodeurs, courant, sécurité |

---

## 9. Ordre de mise au point

### Phase 1 — Validation de l'angle (maintenant)
1. Lire `pitch_deg` via télémétrie VCP
2. Tenir le robot debout → angle ≈ 0°
3. Pencher vers l'avant → angle positif (sinon inverser `accel_x_g` dans `imu.c`)
4. Vérifier que le gyroscope contribue (signal lisse sans vibrations)

### Phase 2 — Tuner la boucle interne (angle_pid)
> Mettre `velocity_pid` Kp/Ki/Kd = 0 pour que `angle_target = 0` fixe.

Méthode : partir avec Kp faible (ex. 1.0), augmenter jusqu'à oscillation, reculer de 40%, ajouter Kd pour amortir, Ki en dernier pour corriger l'erreur statique.

Valeurs typiques pour ce type de robot (point de départ uniquement) :

| Gain | Ordre de grandeur |
|------|------------------|
| Kp angle | 5 – 15 |
| Ki angle | 0.5 – 5 |
| Kd angle | 0.1 – 1 |

### Phase 3 — Tuner la boucle externe (velocity_pid)
> La boucle interne doit être stable avant de toucher ceci.

Valeurs typiques :

| Gain | Ordre de grandeur |
|------|------------------|
| Kp vitesse | 0.01 – 0.1 |
| Ki vitesse | 0.001 – 0.05 |
| Kd vitesse | 0 (souvent inutile) |

### Phase 4 — Tuner le yaw (yaw_pid)
> En dernier, une fois que le robot tient en équilibre et avance/recule.

---

## 10. Documents liés

| Fichier | Contenu |
|---------|---------|
| [1-requirements.md](1-requirements.md) | Exigences système (SYS-*, HW-*, FW-*) |
| [2-system.md](2-system.md) | Architecture matérielle inter-cartes |
| [4-stm32wb5m-pins-allocations.txt](4-stm32wb5m-pins-allocations.txt) | Tableau complet des broches |
| [CLAUDE.md](CLAUDE.md) | Instructions de build et structure du projet |
