# CBC Tuner — Design Specification

## Product Vision

A desktop engineering tool to develop, validate, and tune a two-wheeled self-balancing robot.  
The interface must feel **fast, focused, and data-dense** — engineered for a roboticist at a bench, not a casual user.  
Connection: USB VCP via STLink onboard the STM32WB5MMG board.

---

## Design Principles

| Principle | Expression |
|---|---|
| **Telemetry first** | Live data visible on every screen. Never navigate away to see what the robot is doing. |
| **One click to act** | Gain change → robot updates immediately. No modal dialogs to send commands. |
| **State is visible** | Connection, stream rate, active control mode, safety state — always in the toolbar. |
| **Dark, dense, precise** | Dark theme, monospace numbers, compact layout. Inspired by oscilloscopes and flight instruments. |

---

## Typography

| Role | Font | Size | Weight | Color |
|---|---|---|---|---|
| Section title | System | 11 px | Bold | text-primary |
| Gain label (Kp/Ki/Kd) | Consolas | 11 px | Bold | text-primary |
| Numeric value | Consolas | 11–12 px | Normal | #e0e0e0 |
| Large instrument value | Consolas | 16–20 px | Bold | varies by state |
| Countdown / hero number | Consolas | 48 px | Bold | varies by state |
| Unit label | Consolas | 9–10 px | Normal | text-secondary |
| Log / journal text | Consolas | 10 px | Normal | #90a4ae |
| Status / hint | Consolas | 10 px | Normal | text-secondary |

---

## Application Shell

### Persistent Toolbar (top)

```
╔══════════════════════════════════════════════════════════════════════════╗
║  Port [COM3 ⭐ STM32 ▾] [↺]  Baud [115200 ▾]  [  Connecter  ]         ║
║  │  Cadence [20 Hz ▾]  [▶ Stream]  Fenêtre [20s]  [Effacer]            ║
║  │  ● RX: 128 kB  PKT: 4521  │  IPC: 127.0.0.1:3334                    ║
╚══════════════════════════════════════════════════════════════════════════╝
```

**Connection state badge**: When connected → toolbar edge gets a 2 px `status-ok` left border.  
**RX LED**: 14×14 px dot, flashes `status-ok` on each received packet.  
**IPC label**: green if MCP server running, red if port busy.

---

### Main Layout

```
┌── Toolbar ──────────────────────────────────────────────────────────────┐
│                                                                         │
├── LEFT RAIL (260–380 px, scrollable) ──┬── RIGHT WORKSPACE ────────────┤
│                                        │                               │
│  Angle PID — boucle interne            │  ┌─ Tab Bar ────────────────┐ │
│  Speed PID — boucle externe            │  │ Live │Validate│Tune│Ident│ │
│  Control Mode                          │  └──────────────────────────┘ │
│  Signal Chain (live)                   │                               │
│  Display Options                       │  (Tab content — full width)   │
│  ─────────────────────────────────     │                               │
│  Robot Logo                            │                               │
└────────────────────────────────────────┴───────────────────────────────┘
```

The left rail is **always visible** regardless of the active tab — gains and live chain values are always accessible.

---

## Left Rail Components

### Gain Panel — `_PidRow` (reusable atom)

```
Kp  ══════════════════════════════════  0.24100
    0.000                               0.500
```

- Label: 24 px wide · Consolas 11 px bold
- Spinbox: 0.00001 resolution · adaptive step · 96 px
- Slider: continuous from lo to hi; editable bound spinboxes (gray 9 px each side)
- Signal: emitted on `editingFinished` or slider release (debounce 300 ms)

---

### `Angle PID Panel`

**GroupBox title**: "Angle PID — boucle interne"

| Gain | Range | Default |
|---|---|---|
| Kp | 0.000 – 0.500 | 0.241 |
| Ki | 0.000 – 0.100 | 0.000 |
| Kd | 0.000 – 0.050 | 0.00041 |

Status line: `→  Kp=0.2410  Ki=0.0000  Kd=0.0004` (Consolas 10 px, text-secondary)

Buttons: `[Reset (0,0,0)]` · `[✓ Appliquer]`  
Sends `VCP_TYPE_CMD_SET_BALANCE_GAINS loop_id=0`.

---

### `Speed PID Panel`

**GroupBox title**: "Speed PID — boucle externe"

| Gain | Range | Default |
|---|---|---|
| Kp | 0.000 – 0.100 | 0.000 |
| Ki | 0.000 – 0.050 | 0.000 |
| Kd | 0.000 – 0.020 | 0.000 |

Sends `loop_id=1`.

---

### `Control Mode Panel`

**GroupBox title**: "Mode de contrôle"

Three exclusive mode buttons in a row:

```
[ Vitesse ]   [ Position ]   [ Angle direct ]
```

Active mode button: `btn-primary` background.

**Vitesse mode** (stacked widget page 0):
```
Consigne  [  0  RPM]  ─────────────────  [-85 … +85]
          [↑ Envoyer]
```

**Position mode** (page 1):
```
Cible  [  0.0 cm ]  ──────────────────  [-50 … +50]
       [▶ Activer Hold]
  Offset équilibre  [0.0 °]  ─────  [-5°…+5°]  [Reset]
```

**Angle direct mode** (page 2):
```
Cible  [  0.0 ° ]  ───────────────  [-8° … +8°]
       [↑ Envoyer]
```

---

### `Signal Chain Panel`

**GroupBox title**: "Chaîne de régulation (temps réel)"

Read-only instrument display. Each row:
```
[Label            115px] [value right-aligned bold] [unit 32px]
```

**── Boucle Vitesse (externe) ──**
- Consigne vitesse / rpm
- RPM gauche / rpm
- RPM droite / rpm  
- → Pitch cible / ° *(yellow if > 5°)*

**── Boucle Angle (interne) ──**
- Pitch mesuré / ° *(red if > 30°)*
- Erreur / °
- Drive output / % *(orange if > 90%)*

**── Sorties moteurs ──**
- Gauche / %
- Droite / %

---

### `Display Options Panel`

**GroupBox title**: "Affichage"

Per-curve control row:
```
● [name     ] [☑] max: [10.00 ] [° ] [☑ inv]
```

| Curve | Color | Default max | Unit | Inv |
|---|---|---|---|---|
| pitch | `#ef5350` | 10.0 | ° | ✓ |
| P | `#ef5350` | 1.0 | | |
| I | `#66bb6a` | 1.0 | | |
| D | `#42a5f5` | 1.0 | | |
| drive | `#ffffff` | 1.0 | | |
| sp RPM | `#b0bec5` | 85.0 | RPM | |
| RPM G | `#ffd54f` | 85.0 | RPM | |
| RPM D | `#4dd0e1` | 85.0 | RPM | |
| PWM G | `#ff8a65` | 1.0 | | |
| PWM D | `#a5d6a7` | 1.0 | | |

---

## Tab: Live

**Purpose**: Continuous telemetry overview — the default view.

```
┌─────────────────────────────────────────────────────────────┐
│  Pitch · PID · Moteurs  (tout normalisé)                    │
│                                                             │
│  1.0 ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  │
│                                                             │
│  0   ──────────────────────────────────────────────────────  │
│                                                             │
│ -1.0 ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  │
│  0s                     10s                     20s        │
└─────────────────────────────────────────────────────────────┘
```

**Curves** (10 total, visibility controlled by left rail Display Options):

| Curve | Color | Style | Width |
|---|---|---|---|
| pitch | `#ef5350` | solid | 2 |
| P term | `#ef5350` | solid | 2 |
| I term | `#66bb6a` | solid | 2 |
| D term | `#42a5f5` | solid | 2 |
| drive | `#ffffff` | dashed | 2 |
| SP RPM | `#b0bec5` | dashed | 1 |
| RPM G | `#ffd54f` | solid | 2 |
| RPM D | `#4dd0e1` | solid | 2 |
| PWM G | `#ff8a65` | dotted | 1 |
| PWM D | `#a5d6a7` | dotted | 1 |

Reference lines: `y=0` gray dashed · `y=±1` dark dashed.  
Buffer: 12 000 samples. Refresh: 25 Hz.

---

## Tab: Validate

Sub-tabs for individual hardware component validation.  
Each sub-tab follows the same layout pattern: **left controls / status** | **right plot(s)**.

```
Validate: [Motor] [Encoders] [IMU] [Current] [OLED] [Kalman]
```

---

### Validate / Motor

**Purpose**: Validate motor control and calibrate drive parameters.

```
┌── Controls (270 px) ─────────────┬── Plot ──────────────────────────────┐
│                                  │                                      │
│  [GroupBox: Mode]                │  Top: RPM L & R vs time              │
│  ○ Open loop  ○ Speed PID        │  Bottom: Drive command vs RPM scatter │
│                                  │  (linearity / dead zone visible)     │
│  [GroupBox: Drive]               │                                      │
│  Drive  [──────────── 0.00 ]     │                                      │
│  [-1000 ──────────── +1000]      │                                      │
│  [→ Envoyer]                     │                                      │
│                                  │                                      │
│  [GroupBox: Calibration]         │                                      │
│  ▶ Démarrer calib moteurs        │                                      │
│                                  │                                      │
│  Dead zone auto-detect           │                                      │
│  Kv (RPM/%) : — (fit)            │                                      │
│  Friction+  : —  Friction- : —   │                                      │
│                                  │                                      │
│  [GroupBox: Télémétrie]          │                                      │
│  Drive norm.   ——                │                                      │
│  RPM Gauche   ——  rpm            │                                      │
│  RPM Droite   ——  rpm            │                                      │
│  Phase calib  ——                 │                                      │
└──────────────────────────────────┴──────────────────────────────────────┘
```

**Calibration procedure**:
1. Click "▶ Démarrer calib moteurs" → enters dedicated calib mode on firmware
2. App sweeps drive from 0% upward until motor starts moving → records dead zone
3. Fit: linear RPM vs drive in working range → computes Kv
4. "💾 Sauvegarder" exports JSON

---

### Validate / Encoders

**Purpose**: Verify encoder counting, direction, and resolution.

```
┌── Controls (270 px) ─────────────┬── Plots ─────────────────────────────┐
│                                  │                                      │
│  [GroupBox: État]                │  Top: Ticks L & R vs time            │
│  Ticks L   —— ticks              │  (raw accumulator, unbounded)        │
│  Ticks R   —— ticks              │                                      │
│  RPM L     —— rpm                │  Bottom: RPM L & R vs time           │
│  RPM R     —— rpm                │                                      │
│                                  │                                      │
│  [GroupBox: Test]                │                                      │
│  Drive test [──── 0.20]          │                                      │
│  [▶ Tourner avant]               │                                      │
│  [▶ Tourner arrière]             │                                      │
│  [⏹ Stop]                        │                                      │
│                                  │                                      │
│  [GroupBox: Validation]          │                                      │
│  Ticks/rev attendus : 7424       │                                      │
│  Ticks/rev mesurés  : ——         │                                      │
│  Symétrie L/R       : ——  %      │                                      │
│  ✓ OK / ✗ ERREUR (colored)      │                                      │
└──────────────────────────────────┴──────────────────────────────────────┘
```

---

### Validate / IMU

**Purpose**: Verify IMU axis mapping, offset, and noise level.

```
┌── Controls (270 px) ─────────────┬── Plots ─────────────────────────────┐
│                                  │                                      │
│  [GroupBox: Valeurs brutes]      │  Top: Accéléromètre (3 axes)         │
│  Ax  —— g   Ay  —— g            │  ax (red) · ay (green) · az (blue)   │
│  Az  —— g                        │                                      │
│  Gx  —— °/s Gy  —— °/s          │  Bottom: Gyroscope (3 axes)          │
│  Gz  —— °/s                      │  gx · gy · gz                       │
│                                  │                                      │
│  [GroupBox: Mapping physique]    │                                      │
│  Gravité     → Ay  [+1.00 g] ✓  │                                      │
│  Pitch accel → Az  [+0.00 g] ✓  │                                      │
│  Pitch gyro  → Gx  [+0.0°/s] ✓  │                                      │
│  Yaw gyro    → Gy  [+0.0°/s] ✓  │                                      │
│                                  │                                      │
│  [GroupBox: Bruit]               │                                      │
│  σ Ay  ——  mg  (robot immobile)  │                                      │
│  σ Gx  ——  °/s                   │                                      │
│                                  │                                      │
│  [▶ Capturer offset (robot ↑)]   │                                      │
└──────────────────────────────────┴──────────────────────────────────────┘
```

Robot orientation indicator: simple 2D rectangle that rotates live with `Ay/Az` angle.

---

### Validate / Current

**Purpose**: Monitor motor current and electrical power consumption.

```
┌── Controls (200 px) ─────────────┬── Plots ─────────────────────────────┐
│                                  │                                      │
│  [GroupBox: Valeurs temps réel]  │  Top: Courant moteurs (A)            │
│  Moteur Gauche                   │  I_left (red) · I_right (orange)     │
│    Courant  —— A  [⚠ > 1.5A]   │                                      │
│    Puissance —— W                │  Bottom: Puissance électrique (W)    │
│  Moteur Droite                   │  P_left · P_right · P_total (yellow) │
│    Courant  —— A                 │                                      │
│    Puissance —— W                │                                      │
│  Total                           │                                      │
│    Puissance —— W                │                                      │
│                                  │                                      │
│  [Effacer]                       │                                      │
└──────────────────────────────────┴──────────────────────────────────────┘
```

Thresholds: current warn > 0.8 A (`status-warn`) · error > 1.5 A (`status-error`).  
Power warn > 9 W · error > 18 W.

---

### Validate / OLED

**Purpose**: Test and send content to the onboard OLED display.

```
┌── Controls (270 px) ─────────────┬── Preview ───────────────────────────┐
│                                  │                                      │
│  [GroupBox: Écrans disponibles]  │  ┌────────────────────────────────┐  │
│  ○ Screen 0 — Idle               │  │  128×64 OLED preview           │  │
│  ○ Screen 1 — Telemetry          │  │  (scaled ×3 for visibility)    │  │
│  ○ Screen 2 — PID                │  │                                │  │
│  ○ Screen 3 — Motor              │  │  [rendered content here]       │  │
│  ○ Screen 4 — Debug              │  │                                │  │
│  ○ Screen 5 — Error              │  └────────────────────────────────┘  │
│                                  │                                      │
│  [▶ Afficher cet écran]          │  Pixel: ON = white · OFF = #263238  │
│                                  │                                      │
│  [GroupBox: Test texte custom]   │                                      │
│  Ligne 1 [_______________]       │                                      │
│  Ligne 2 [_______________]       │                                      │
│  [→ Envoyer texte custom]        │                                      │
└──────────────────────────────────┴──────────────────────────────────────┘
```

---

### Validate / Kalman

**Purpose**: Visualize and tune the complementary / Kalman filter for angle estimation.

```
┌── Controls (270 px) ─────────────┬── Plots ─────────────────────────────┐
│                                  │                                      │
│  [GroupBox: Filtre]              │  Top: Angle estimé vs t              │
│  Type  [Complémentaire ▾]        │  θ_accel (gray) · θ_gyro (yellow)   │
│                                  │  θ_filtre (red bold) · θ_raw (muted) │
│  α (compl.)  [0.980  ]           │                                      │
│  [────────────────────]          │  Bottom: Résidu / Bruit              │
│                                  │  θ_filtre − θ_accel                  │
│  [GroupBox: Kalman]              │                                      │
│  Q  [0.001  ]                    │                                      │
│  R  [0.010  ]                    │                                      │
│  P₀ [1.000  ]                    │                                      │
│                                  │                                      │
│  [GroupBox: Métriques]           │                                      │
│  σ filtre   —— °                 │                                      │
│  Latence    —— ms                │                                      │
│  [Appliquer au firmware]         │                                      │
└──────────────────────────────────┴──────────────────────────────────────┘
```

---

## Tab: Tune

Sub-tabs for high-level PID tuning with sweep and heatmap.

```
Tune: [Angle PID] [Speed PID] [Position PID] [Sweep]
```

---

### Tune / Angle PID

**Purpose**: Fine-tune angle balance loop with live simulation comparison.

```
┌── Left (320 px fixed) ───────────────┬── Right plots ───────────────────┐
│                                      │                                  │
│  [GroupBox: Système UFOPDT]          │  Top: Angle (°)                  │
│  Pôle a   [6.56] rad/s               │  θ sim (red) · θ live (orange    │
│  Gain K   [4400] °/s²                │  dashed if snapshot loaded)      │
│  Retard τd [0.005] s                 │  Safety ±20° (orange dashed)     │
│                                      │                                  │
│  [GroupBox: Gains PID]               │  Bottom: PID output (normalized) │
│  Kp [──────────── 0.150  ]           │  drive (white) · P (red)         │
│     [0.000]          [0.500]         │  I (green) · D (blue)            │
│  Ki [──────────── 0.000  ]           │                                  │
│  Kd [──────────── 0.030  ]           │                                  │
│                                      │                                  │
│  [↓ Copier gains depuis Live]        │                                  │
│  [📌 Gel θ réel]  [✕]               │                                  │
│                                      │                                  │
│  [GroupBox: Simulation]              │                                  │
│  θ₀  [2.0°]   Durée [5.0 s]         │                                  │
│                                      │                                  │
│  ╔══════════════════════════════╗    │                                  │
│  ║ Survécu  RMS=1.23°  Max=5.4°║    │                                  │
│  ║ Settled=0.85s               ║    │                                  │
│  ╚══════════════════════════════╝    │                                  │
│                                      │                                  │
│  [Robot viz — animated replay]       │                                  │
│    ┌──┐                              │                                  │
│    │╱ │  +2.3°                       │                                  │
│    ○  ○                              │                                  │
└──────────────────────────────────────┴──────────────────────────────────┘
```

**Robot viz** (`_RobotViz`): min 120 px, animates simulation at 5× speed. Red body on crash.

**Status box**: color-coded — green (survived), red (CRASH t=0.32s θ=21.3°).

---

### Tune / Speed PID

**Purpose**: Tune velocity outer loop. Control robot forward/backward from the app.

```
┌── Left (320 px) ─────────────────────┬── Right plots ───────────────────┐
│                                      │                                  │
│  [GroupBox: Gains Speed PID]         │  Top: RPM vs time                │
│  Kp/Ki/Kd sliders (same pattern)     │  SP (gray dashed) · L (yellow)   │
│                                      │  R (cyan)                        │
│  [GroupBox: Contrôle manuel]         │                                  │
│  Consigne  [  0  RPM ]               │  Bottom: Target pitch vs time    │
│            [──────────]              │  target_pitch (blue)             │
│  [-85 ─────────────── +85]           │  measured_pitch (red)            │
│  [↑ Envoyer]  [⏹ Stop (0 RPM)]      │                                  │
│                                      │                                  │
│  [GroupBox: Symétrie L/R]            │                                  │
│  Écart L-R  —— rpm  (live)           │                                  │
│  Correction yaw —— (auto)            │                                  │
└──────────────────────────────────────┴──────────────────────────────────┘
```

---

### Tune / Position PID

**Purpose**: Tune position hold loop and sinusoidal trajectory.

```
┌── Left (scrollable, 320 px) ─────────┬── Right plot ────────────────────┐
│                                      │                                  │
│  [GroupBox: Gains Position PID]      │  Position (cm)                   │
│  Kp [0.0–2.0] default 0.5            │  Consigne (blue dashed)          │
│  Ki [0.0–0.5] default 0.0            │  Position (red solid)            │
│  Kd [0.0–0.5] default 0.0            │  30 s rolling window             │
│  [Reset]  [✓ Appliquer]              │                                  │
│                                      │                                  │
│  [GroupBox: Mode]                    │                                  │
│  [Hold ▾ / Sinusoïde ▾]             │                                  │
│                                      │                                  │
│  Hold:                               │                                  │
│    Cible [0.0 cm]  [▶ Activer Hold]  │                                  │
│                                      │                                  │
│  Sinusoïde:                          │                                  │
│    Amplitude [10 cm]                 │                                  │
│    Période   [4.0 s]                 │                                  │
│    [▶ Démarrer sinus]                │                                  │
│                                      │                                  │
│  [↩ Retour Mode Vitesse]             │                                  │
│                                      │                                  │
│  [GroupBox: État]                    │                                  │
│  Mode / Position / Consigne / Erreur │                                  │
│  Vel SP                              │                                  │
└──────────────────────────────────────┴──────────────────────────────────┘
```

---

### Tune / Sweep

**Purpose**: Explore Kp × Kd space systematically. Click heatmap → instantly apply to robot.

```
┌── Left (320 px) ──────────────────────────────────────────────────────┐
│                                                                       │
│  [GroupBox: Plage des gains]                                         │
│  Kp  min [0.04] → max [0.30]  N [10] → 10 vals                     │
│  Kd  min [0.005] → max [0.06] N [10] → 10 vals                     │
│  Ki fixe [0.000]                                                     │
│  θ₀ [2.0°]  Durée [5.0 s]                                           │
│  ── 10 × 10 = 100 essais  (~0.1 s) ──                               │
│                                                                       │
│  [▶ Lancer sweep ──────────────────────]  [⏹]                       │
│  ████████████████░░░░░░  72%                                         │
│  Terminé — 98/100 survivants                                         │
│                                                                       │
│  Couleur : [RMS 1s (°) ▾]                                           │
│                                                                       │
│  ┌─────────────────────────────────────┐                             │
│  │  Kp │  Kd │  Ki │ RMS° │ Max° │ Settled │                       │
│  ├─────┼─────┼─────┼──────┼──────┼─────────┤                       │
│  │0.150│0.030│0.000│ 1.23 │  5.4 │  0.85   │  ← selected (blue)   │
│  │0.140│0.035│0.000│ 1.41 │  6.1 │  0.92   │                       │
│  └─────────────────────────────────────┘                             │
│                                                                       │
│  [→ Appliquer sur le robot]                                          │
└───────────────────────────────────────────────────────────────────────┘
```

**Right side** (vertical split):

```
┌── Heatmap Kp × Kd (stretch=2) ──────────────────────────────────────┐
│                                                                      │
│  Kd ↑                                                                │
│      ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■                         │
│      ██▓▓▓▒▒▒▒░░░░░░░░░░░░▒▒▒▓▓██████████                         │
│      ██▓▒▒░░░░░ ◯ ░░░░░░░░░░░░▒▓▓█████████   ◯ = selection        │
│      ██▓▒░░░░░░░░░░░░░░░░░░░░░▒▒▓▓█▓▓█████                         │
│      ████████████████████████████████████████                       │
│                                           Kp →                      │
│  █ crash  ▓ bad  ▒ mid  ░ good  · best                             │
└──────────────────────────────────────────────────────────────────────┘
┌── Essai sélectionné — angle (°) (stretch=1) ─────────────────────────┐
│  Kp=0.150  Kd=0.030  Ki=0.000  |  OK  RMS=1.23°  settled=0.85s      │
│                                                                      │
│   5°╷╭─╮                                                             │
│     │╰─╯╲___________________                                         │
│   0°│                                                                │
│  -5°╵                         t (s)                                 │
└──────────────────────────────────────────────────────────────────────┘
```

**Click behavior**: Clicking any heatmap cell selects it (white ring overlay), highlights matching table row, shows trial curve. Button "→ Appliquer sur le robot" sends Kp/Ki/Kd AND updates the left rail Angle PID panel.

**Color scale** (green=best, red=worst, dark red=crash):
- Survived: `lerp(#66bb6a → #ffd54f → #ef5350)` based on metric percentile
- Crash / did not survive: `#781414`
- No data: `#263238`

---

## Tab: Ident

System identification screens. Each uses the same two-column pattern.

```
Ident: [K — Gain actionneur] [td — Retard] [a — Pôle] [Sweep réel]
```

---

### Ident / K — Gain actionneur

**Purpose**: Measure K (°/s² per normalized drive unit) from live telemetry.

```
┌── Controls (270 px) ─────────────┬── Plots ─────────────────────────────┐
│                                  │                                      │
│  [🔓 Entrer mode identification]  │  Top: drive (%) et pitch_rate (°/s) │
│  (turns purple when active)      │  vs time — last 2000 samples         │
│  ⚠ Robot à l'envers              │  drive × 100 (green) · ω (red)       │
│                                  │                                      │
│  [GroupBox: Signal d'excitation] │  Bottom: pitch_rate mesuré           │
│  Forme  [Sinus ▾]                │  vs fit sinusoïdal R·sin(ωt+ψ)      │
│  Amplitude ± [25 %]              │  scatter (yellow dots)               │
│  Demi-période [0.40 s]           │  fit (green line)                    │
│  Nb cycles   [15]                │                                      │
│                                  │                                      │
│  🟢 En cours… 0 pts             │                                      │
│  [▶ Lancer]  [⏹ STOP]           │                                      │
│  [🗑 Effacer données]            │                                      │
│                                  │                                      │
│  [GroupBox: Télémétrie]          │                                      │
│  Pitch     —— °                  │                                      │
│  pitch_rate —— °/s               │                                      │
│  Drive norm —— /                 │                                      │
│                                  │                                      │
│  [GroupBox: Résultat]            │                                      │
│  K = 4400 ± 200 °/s²  (large)   │                                      │
│  R² = 0.956   n = 450 pts        │                                      │
│  ψ = –87° (idéal –90°) Δt≈5ms   │                                      │
│  [💾 Sauvegarder JSON]           │                                      │
└──────────────────────────────────┴──────────────────────────────────────┘
```

Result color: green if R² > 0.85 · yellow > 0.5 · red otherwise.

---

### Ident / td — Retard

**Purpose**: Measure actuator dead time τd.  
Same layout as Ident K. Method: step pulse → measure delay between command and pitch_rate response.  
Output: τd (ms), quality metric.

---

### Ident / a — Pôle

**Purpose**: Measure pole location `a` (natural instability rate).  
Same layout as Ident K. Method: impulse response → fit `θ̈ = a²·θ`.  
Output: a (rad/s), uncertainty, R².

---

### Ident / Sweep réel

**Purpose**: Run a Kp × Kd gain sweep on the **real robot** (as opposed to simulation).

```
┌── Left: Plan ────────────────────┬── Right: Run + Results ──────────────┐
│                                  │                                      │
│  [Plan] identical to Tune/Sweep  │  Top: Like Tune/Run panel            │
│  grid + timing config            │  countdown · pitch live · star rating│
│                                  │                                      │
│  [Envoyer au Run ▶]             │  Bottom: Heatmap (same as Tune/Sweep)│
│                                  │  with real-world ⭐ ratings instead  │
│                                  │  of simulated RMS                    │
└──────────────────────────────────┴──────────────────────────────────────┘
```

---

## Reusable Components

### `_PidRow` — Gain slider with editable bounds

```
States:
  normal    — slider/spinbox are white-on-dark
  focused   — blue accent border on spinbox
  changed   — spinbox text turns accent-blue until committed
  disabled  — all elements dimmed (btn-disabled colors)
```

### `_GainSlider` (simulation variant)

```
[Kp]  [0.150   ]
      [0.000] ═══════════════════ [0.500]
```
- Spinbox 72 px · bounds are editable (gray 54 px each, 9 px Consolas)
- Hint below: "← bornes grises éditables  |  valeur = spinbox"

### `_StarRating`

```
Score :  ☆ ☆ ☆ ☆ ☆   (non noté)
```

- 5 buttons 38×38 px
- ☆ empty (gray) · ★ filled (`#ffd54f`)
- Click same star again → deselects
- Descriptions: "(non noté)" · "Chute immédiate" · "Tient un peu" · "Instable mais debout" · "Bon équilibre" · "Parfait"

### `_RobotViz` — Robot silhouette

```
         ┌──┐
         │  │   +2.3°
        ╱│  │╲
       ○    ○        wheels on floor line
```

- Rotates with angle (capped ±89°)
- Body: `#37474f` normal · `#ef5350` on crash
- Floor line: gray dashed
- Angle text below: green if < 15° · yellow if < 30° · red if ≥ 30°

### `_RxLed` — Packet indicator

- 14×14 px circle
- Off: `bg-border` · On: `status-ok` · Flashes for 120 ms per packet

### `_RobotLogo` (bottom of left rail, 110 px fixed height)

Two-wheeled pendulum robot illustration:
- Background: `bg-deep`
- Body + head: `#37474f` rounded rects, `#546e7a` highlight
- Eyes: `#42a5f5` with radial gradient
- Antenna: `#66bb6a` line + dot
- Wheels: `#263238` fill, `#ef5350` rim, `#546e7a` hub
- Footer: "CBC Tuner v1.0 · pendule inversé" · `text-muted` · Consolas 7 px

---

## Interaction Patterns

### Gain change → robot update

1. User moves slider or edits spinbox
2. 300 ms debounce
3. VCP frame sent silently (no confirmation dialog)
4. Status line in panel updates: `→  Kp=0.2410  Ki=0.0000  Kd=0.0004`

### Heatmap click → apply

1. Click any heatmap cell
2. White ring appears on cell
3. Matching table row highlights in blue
4. Trial curve appears in detail panel below
5. "→ Appliquer sur le robot" becomes enabled
6. On click: gains sent to robot AND left rail Angle PID panel updates

### Connection flow

1. Select port from dropdown (STM32 VCP ports marked ⭐)
2. Click "Connecter"
3. Auto-starts stream at selected cadence
4. Restored gains sent 200 ms later
5. Left toolbar border turns `status-ok` green

### Safety behavior

- If |pitch| > 20° in simulation → red robot, red status, stop animation
- If |drive| > 90% → orange color in Signal Chain "Drive output"
- If |pitch| > 30° live → "Pitch mesuré" label turns red in Signal Chain

---

## VCP Frame Protocol

```
SOF1(0xAA) SOF2(0x55) VER TYPE FLAGS SEQ LEN_L LEN_H [PAYLOAD…] CRC16_L CRC16_H EOF(0x33)
```
CRC16-CCITT over `VER…PAYLOAD`.

### Commands (PC → Robot)

| Command | Type | Payload format |
|---|---|---|
| Stream control | 0x22 | `bool enable · u16 rate_hz` |
| Set balance gains | 0x24 | `u8 loop_id · f32 kp · f32 ki · f32 kd` |
| Set velocity SP | 0x21 | `i16 rpm` (clamped ±85) |
| Set angle offset | 0x2A | `f32 offset_deg` |
| Set angle target | 0x2B | `f32 deg` (direct angle mode) |
| Set drive direct | 0x29 | `i16 drive_x1000` |
| Set position SP | 0x26 | `f32 sp_cm` |
| Set position traj | 0x27 | `u8 mode · f32 ampl_cm · f32 period_s` |
| Motor calib | 0x25 | `u8 enable` |

**loop_id**: 0 = angle · 1 = speed · 2 = yaw · 3 = position

### Telemetry (Robot → PC)

| Packet | Type | Fields |
|---|---|---|
| IMU | 0x11 | `u32 ts · i16 ax ay az gx gy gz pitch_x100 drive_x100` |
| PID | 0x10 | `u32 ts · i16 sp pv_l pv_r target_pitch_x100 _r pwm_l pwm_r` |
| Position | 0x13 | `u32 ts · i16 pos_x10 sp_x10 vel_sp · u8 ctrl traj` |
| Calib | 0x12 | `u32 ts · i16 drive_x1000 vel_l vel_r · u8 phase active` |

---

## Settings Persistence

File: `~/.config/cbc-tuner/settings.ini`

| Key | Default |
|---|---|
| geometry | (last window size/position) |
| splitter_main | [300, remainder] |
| time_window_s | 20 |
| last_port | "" |
| last_baud | "115200" |
| gains/angle_kp | 0.241 |
| gains/angle_ki | 0.0 |
| gains/angle_kd | 0.00041 |
| gains/vel_kp | 0.0 |
| gains/vel_ki | 0.0 |
| gains/vel_kd | 0.0 |
| gains/pos_kp | 0.5 |
| gains/pos_ki | 0.0 |
| gains/pos_kd | 0.0 |

---

## Simulation Physics

Model: UFOPDT inverted pendulum  
`θ̈ = a²·θ − K·u(t − τd)`

Identified defaults:
- a = 6.562 rad/s
- K = 4400 °/s²
- τd = 5 ms

PID: anti-windup, integrator clamped ±0.5.  
Crash threshold: |θ| ≥ 20°.  
Metrics: RMS (last 1 s) · max |θ| · settling time · saturation %.  
Sweep step: dt = 5 ms. Parallel rows computed iteratively to keep UI responsive.
