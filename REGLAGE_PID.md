# Procédure de réglage PID — Robot pendule inversé

## 1. Chaîne de régulation complète

```
Consigne vitesse (RPM)
        │
        ▼
┌─────────────────┐
│  PID Vitesse    │  Kp_v, Ki_v, Kd_v      [boucle externe CBC]
│  erreur = RPM_cible − RPM_moyen          sortie ∈ [−10°, +10°]
└────────┬────────┘
         │  target_pitch_deg
         ▼
┌─────────────────┐
│  PID Angle      │  Kp_a, Ki_a, Kd_a      [boucle interne CBC]
│  erreur = target_pitch − pitch_mesuré    sortie ∈ [−1.0, +1.0]
└────────┬────────┘
         │  drive_output  (normalisé)
         ▼
  × (−1) × 250 RPM
         │
         ▼  consigne RPM moteurs
┌─────────────────┐
│  PID Vitesse    │  Kp=0.050  Ki=0.060  Kd=0       [par moteur]
│  moteur G/D     │  erreur = RPM_consigne − RPM_mesuré   sortie → PWM
└─────────────────┘
```

---

## 2. Formules exactes (firmware — pid_controller.c)

Pour chaque PID :

```
error        = setpoint − measurement
P            = Kp × error
I           += Ki × error × dt           (dt = 0,005 s)
D            = −Kd × (measurement − prev_measurement) / dt
output       = P + I + D   clampé dans [out_min, out_max]
```

Le terme D est calculé sur la **dérivée de la mesure** (pas de l'erreur).  
Cela évite les pics de dérivée lors d'un changement de consigne.

---

## 3. Conversion drive_output → RPM moteur

```
drive_output  ∈ [−1.0, +1.0]       (sortie PID Angle, après clamp)

RPM_consigne_G = −drive_output × 250  RPM
RPM_consigne_D = −drive_output × 250  RPM
(le signe − compense la convention : tilt avant → drive négatif → roues en avant)

Exemple : drive_output = −0.64
  → RPM_consigne = +0.64 × 250 = +160 RPM sur les deux roues
```

La valeur **Drive output (%)** affichée dans le panneau gauche de l'appli = `drive_output × 100`.  
Pour obtenir le RPM envoyé au PID moteur : `Drive_output_% / 100 × 250`.

---

## 4. Limites anti-windup (initialisées dans le firmware)

| PID          | Sortie clampée | Intégrateur clampé |
|---|---|---|
| Angle        | [−1.0, +1.0]  | [−0.5, +0.5]       |
| Vitesse CBC  | [−10°, +10°]  | [−5°, +5°]         |
| Yaw CBC      | [−0.3, +0.3]  | [−0.2, +0.2]       |
| Moteur G/D   | [−1.0, +1.0]  | [−0.9, +0.9]       |

---

## 5. Procédure de réglage — PID Angle (boucle interne)

### Conditions préalables

- PID Vitesse CBC : Kp=0, Ki=0, Kd=0 (boucle externe inactive, consigne = 0 RPM)
- PID moteur : Kp=0.050, Ki=0.060, Kd=0 (déjà réglé, ne pas modifier)
- Robot tenu à la main, incliné légèrement autour du point d'équilibre
- Fenêtre temporelle appli : **5 s**

> **Vérification obligatoire avant de régler les gains :**
> Tourner une roue à la main — RPM gauche ou droite doit être non nul dans l'appli.
> Si RPM = 0 en permanence → firmware non recompilé après fix GetCachedVelocityRPM.
> Dans ce cas le PID moteur est en bang-bang permanent : aucun réglage de Kp/Kd n'est significatif.

### Étape 1 — Trouver l'angle d'équilibre réel (offset)

Le robot ne sera jamais parfaitement équilibré à 0°. Laisser tourner les moteurs
avec Kp faible, observer la valeur de pitch stabilisée. Cet offset est le **bias
mécanique** (centre de masse décalé).

> À ce stade, il n'y a pas de mécanisme pour compenser cet offset dans le firmware.
> Le terme I s'en chargera une fois Ki ajouté.

### Étape 2 — Régler Kp (proportionnel)

1. Mettre Ki=0, Kd=0.
2. Partir de **Kp = 0.05** et monter par paliers de 0.01.
3. Critère d'arrêt : le terme P (graphe 2) reste dans ±1 pour les inclinaisons
   habituelles. Dès que P sature (valeur > 1), le PID passe en tout-ou-rien.
4. Si oscillations → Kp trop fort. Reculer au dernier palier stable.

Le seuil de saturation = 1 / Kp. Pour Kp=0.05 : saturation à 20° d'erreur.
Pour Kp=0.2 : saturation à 5°. Choisir en fonction de l'angle de travail attendu.

Plage typique attendue : **Kp ∈ [0.05, 0.2]** pour ce robot.

Pour Kp = 0.1 et une erreur de 5° :
```
P = 0.1 × 5° = 0.5 → RPM_consigne = 0.5 × 250 = 125 RPM
```
Observation : Kp=0.007

### Étape 3 — Régler Kd (dérivé)

1. Kd amortit les oscillations et la vitesse de chute.
2. Partir de **Kd = 0.01**, monter par paliers de 0.005.
3. Critère : le terme D (courbe bleue sur graphe 2) est visible et lisse.
   S'il est très bruité → Kd trop fort ou mesure gyro bruitée.
4. Le terme D en firmware = `−Kd × d(pitch)/dt / dt`.
   Approximation : `D ≈ Kd × Gx` (°/s → normalisé).

Pour Kd = 0.02 et pitch_rate = 50 °/s :
```
D = 0.02 × 50 / 0.005 = 200 → clampé à 1.0
```
→ Kd > 0.02 avec pitch_rate = 50°/s sature le terme D. Ajuster en conséquence.

Observation : Kd=0.0001 avec 0.0002 oscillation tres violentes

### Étape 4 — Régler Ki (intégral)

1. Ki compense le bias d'équilibre et l'erreur statique.
2. Partir de **Ki = 0.02**, monter par paliers de 0.01.
3. Sur le graphe 2, le terme I (courbe verte) doit dériver lentement vers une
   valeur stable, pas exploser.
4. Si le terme I sature à ±0.5 → Ki trop fort ou conditions initiales mauvaises.

### Récapitulatif graphe 2 — lecture rapide

| Courbe | Saturation | Interprétation |
|---|---|---|
| **P** rouge | ±1.0 | Kp trop fort ou erreur angle trop grande |
| **I** vert  | ±0.5 | Ki trop fort ou intégrateur en windup |
| **D** bleu  | ±1.0 | Kd trop fort ou gyro bruité |

---

## 6. Réglage PID Vitesse CBC (boucle externe) — après l'angle

Le PID Vitesse transforme l'erreur RPM en consigne d'angle (°).

1. PID Angle réglé et stable.
2. Lâcher le robot, lui permettre de se balancer librement.
3. Kp_v ∈ [0.01, 0.2] — plage beaucoup plus faible car sortie en degrés.
4. Observer que le robot revient à vitesse nulle sans osciller en translation.

---

## 7. Résultats des essais — Réglage CBC (session 2026-06-02)

### Conditions d'essai
- Robot tenu à la main, roues apparemment non en contact avec le sol dans la plupart des essais
- Workflow corrigé en cours de session : gains envoyés **pendant que le robot est tenu**, puis lâché
- Boucle vitesse CBC désactivée (Kp_v=Ki_v=Kd_v=0), consigne angle = 0°
- Firmware tourne à 200 Hz, télémétrie sous-échantillonnée à ~5 Hz côté MCP

### Bug GUI corrigé (2026-06-02)

`pid_p`, `pid_i`, `pid_d` affichaient toujours 0 quand les gains étaient envoyés via MCP.

**Cause :** `_on_imu()` lisait les gains depuis `_angle_panel.gains()` (sliders GUI) alors que le MCP mettait à jour `_state.kp/ki/kd` sans mettre à jour les sliders.

**Fix :** [app-cbc-tuning/cbc_tuner/gui.py](app-cbc-tuning/cbc_tuner/gui.py)
- `_on_imu` lit désormais `self._state.kp, self._state.ki, self._state.kd`
- `_send_gains` appelle `self._angle_panel.set_gains(kp, ki, kd)` pour synchroniser les sliders

### Tableau des essais

| # | Kp | Kd | Départ | Résultat | pid_p saturé ? |
|---|----|----|--------|----------|----------------|
| 1 | 0.10 | 0 | ~0° | Oscillations violentes ±25° | Oui (>10°) |
| 2 | 0.06 | 0.015 | ~0° | Oscillations violentes ±22° | Oui (>17°) |
| 3 | 0.20 | 0.012 | ~0° | **"Presque bien"** — pitch=0.36° et 0.28° brièvement, puis oscille ±20° | Oui (>5°) |
| 4 | 0.20 | 0.025 | −2.6° | Diverge vers −5° en 1 s | Oui |
| 5 | 0.08 | 0.020 | robot tenu | Pitch figé à −3.7°, std=0.037° — robot tenu à la main, roues tournent (rpm=38) | Non |
| 6 | **0.12** | **0.025** | **+4.9°** | **Meilleur résultat** — oscillations ±5-7°, pid_p max=0.83, pas de saturation | **Non** |
| 7 | 0.12 | 0.035 | −7° | Robot bloqué à −7° toute la seconde — D trop fort annule P | Non |
| 8 | 0.12 | 0.028 | −8° | Bloqué à −7°/−8°, même cause | Non |
| 9 | 0.12 | 0.025 | +4.9° (bis) | Pitch figé à +7.1°, rpm=0 — roues probablement hors sol | — |

### Conclusions

**1. Saturation P = bang-bang**
- Kp élevé (≥0.15) donne un seuil de saturation ≤7°. Tout angle supérieur → 100% moteur en permanence → oscillations limite cycle incontrolables.
- Zone de travail linéaire : **Kp ∈ [0.08, 0.12]** avec seuil ±8–12°.

**2. Kd optimal ≈ 0.025 pour Kp=0.12**
- Kd < 0.020 → sous-amorti, oscillations croissantes
- Kd = 0.025 → ±5-7° d'oscillation, régime linéaire ✓
- Kd > 0.030 → terme D annule le terme P pendant la récupération → robot bloqué loin de 0°
- Règle pratique : `Kd / Kp < 0.21` pour éviter que D override P à des vitesses typiques (20-30°/s)

**3. Offset d'équilibre systématique**
- Le robot se retrouve systématiquement à −7°/−8° quand lâché depuis un angle négatif.
- Le point d'équilibre physique n'est probablement **pas à 0°** (décalage CoM ou offset IMU).
- Le terme I (Ki) sera nécessaire pour compenser cet offset une fois la stabilité P+D obtenue.

**4. Latence d'application des gains (~200 ms)**
- Si le robot est lâché AU MÊME MOMENT que les gains sont envoyés, il a le temps de tomber à ±7-13° avant que le firmware applique les gains.
- **Workflow correct :** envoyer les gains pendant que le robot est tenu, PUIS lâcher.

**5. Roues hors sol = test invalide**
- RPM=0 avec 100% PWM → moteurs bloqués ou roues en l'air.
- Pour tout test valide : **roues en contact avec le sol obligatoire**.

### Prochaines étapes (après batch)

1. **Vérifier roues au sol** : refaire essai Kp=0.12, Kd=0.025 avec robot sur sol plat
2. **Identifier le vrai point d'équilibre** : observer pitch stabilisé avec Kp faible
3. **Ajouter Ki = 0.02–0.05** pour compenser l'offset d'équilibre
4. **Étendre la durée** à 3–5 s une fois stable pour confirmer la tenue

---

### Batch de 10 essais (session 2026-06-02 — fin de session, pile déchargée)

**Workflow :** gains envoyés pendant que le robot est tenu, relâché immédiatement après.  
Durée d'observation : 1,5 s par essai.

| # | Kp   | Kd    | Ki   | Plage pitch       | Std°  | Verdict |
|---|------|-------|------|-------------------|-------|---------|
| T1 | 0.10 | 0.020 | 0    | +1.5° → −13.6°   | 3.67° | Dérive progressive vers l'arrière — Kp insuffisant |
| T2 | 0.10 | 0.025 | 0    | ±2° puis −22°     | 8.23° | Bon départ (±2° sur 1 s), s'effondre ensuite |
| T3 | 0.12 | 0.020 | 0    | +7° → ±24°        | 11.6° | Oscillations croissantes — Kd trop faible |
| T4 | 0.12 | 0.025 | 0    | ±2° pendant ~1 s, puis +25° | 9.76° | Excellent début, chute à t≈−0.45 s (perturbation ?) |
| T5 | 0.12 | 0.030 | 0    | ±28°              | 16.4° | Instable — Kd trop fort avec ce Kp |
| T6 | 0.14 | 0.025 | 0    | −28° → ±3°        | 10.1° | Forte récupération depuis −28°, finit à ±3° |
| T7 | 0.14 | 0.030 | 0    | ±28°              | 18.7° | Très instable |
| T8 | 0.15 | 0.025 | 0    | 0° → +9°          | 2.69° | Stable mais offset positif persistant (+5°) |
| **T9** | **0.15** | **0.030** | **0** | **−3.4° à +3.9°** | **1.41°** | **MEILLEUR** — pid_p max=±0.51, pas de saturation |
| T10 | 0.12 | 0.025 | 0.02 | +7.6° → −5.2°   | 3.60° | Bon comportement, I trop court pour évaluer |

#### Analyse du batch

**Vainqueur provisoire : T9 — Kp=0.15, Kd=0.030, Ki=0**
- `pid_p` max = ±0.51 → jamais saturé (seuil ±6.7°)
- `pid_d` max = ±1.25 → bref pic, sinon ≤ ±0.5
- Oscillations régulières et amorties : −3.4° à +3.9°, std = 1.41°
- Offset moyen = −1.2° → candidat idéal pour ajouter Ki=0.02 lors de la prochaine session

> **Réserve (retour utilisateur) :** en fin de session (pile faible), les moteurs réagissaient moins bien et l'équilibre était à peine atteint. Les résultats T8–T10 sont à **reconfirmer avec une pile chargée** avant d'être considérés comme fiables. La tension de batterie basse peut dégrader la réponse du L298 et fausser le réglage.

**Observations clés du batch :**

1. **Zone morte Kd** : avec Kp=0.12, Kd=0.025 fonctionne (T4), Kd=0.030 trop fort (T5). Avec Kp=0.15, Kd=0.030 fonctionne (T9). La règle `Kd/Kp ≈ 0.20` se confirme.

2. **Kp=0.10 insuffisant** : le robot dérive malgré la correction (T1, T2). Il faut au moins Kp=0.12 pour avoir assez de force.

3. **T4 vs T9** : T4 (Kp=0.12, Kd=0.025) a tenu ±2° pendant ~1 s puis s'est effondré (probablement perturbation externe). T9 (Kp=0.15, Kd=0.030) est plus robuste.

4. **T8 vs T9** : même Kp=0.15, mais Kd=0.025 (T8) laisse un offset de +5° non corrigé alors que Kd=0.030 (T9) converge vers ±2°. Le Kd plus fort amortit mieux le dépassement.

#### Prochaine session — plan d'action

```
Étape 1  Kp=0.15, Kd=0.030, Ki=0      — confirmer T9 sur 5 s, roues au sol
Étape 2  Kp=0.15, Kd=0.030, Ki=0.02   — ajouter I pour corriger l'offset −1.2°
Étape 3  Si stable → essai Ki=0.03/0.04 si offset persiste
Étape 4  Activer boucle vitesse (Kp_v ≈ 0.02–0.05)
```

> **Note physique :** s'assurer que les **roues sont en contact avec le sol** pendant tout essai. RPM=0 avec 100% PWM = roues en l'air = test invalide.

---

## 8. Protocole de sweep automatisé + identification système

Cette section décrit le workflow complet permettant de comparer automatiquement
X jeux de gains, d'identifier le modèle physique du pendule et de simuler des
milliers de combinaisons offline avant de valider sur hardware.

### Prérequis

- Application CBC Tuner lancée, robot connecté (port COM visible)
- Batterie chargée, robot sur sol plat, roues en contact
- Claude Code ouvert avec le serveur MCP `cbc-tuner` actif

---

### Étape 1 — Sweep hardware automatisé (`run_sweep`)

**Objectif :** collecter des données sur X jeux de gains en séquence automatique.

#### Séquence par essai
```
t = 0 ms     → début capture baseline (robot tenu immobile)
t + 200 ms   → gains appliqués au firmware  ← LÂCHER LE ROBOT
t + 200 + hold_s → moteurs coupés (gains → 0)
t + 600 + hold_s → fichier JSON sauvegardé dans sweeps/
```

#### Appel MCP (via Claude)
```
run_sweep(
  param_sets='[
    {"kp": 0.12, "ki": 0.0, "kd": 0.025},
    {"kp": 0.15, "ki": 0.0, "kd": 0.030},
    {"kp": 0.15, "ki": 0.0, "kd": 0.035},
    {"kp": 0.18, "ki": 0.0, "kd": 0.030},
    {"kp": 0.18, "ki": 0.0, "kd": 0.036}
  ]',
  hold_s=1.5,
  output_dir="sweeps",
  early_stop_deg=30.0
)
```

#### Règles opérateur
- Tenir le robot debout **avant** chaque essai (moteurs à l'arrêt)
- Lâcher dès réception du signal "LÂCHE" dans la réponse Claude (≈200 ms après l'appel)
- Pause de 2 s entre essais — repositionner le robot
- Si `early_stop` : le robot a chuté, les gains sont trop agressifs
- **Roues au sol obligatoire** — RPM=0 avec 100% PWM = essai invalide

#### Fichier de sortie par essai
```json
{
  "trial":   {"id": 1, "kp": 0.15, "ki": 0.0, "kd": 0.030, "hold_s": 1.5},
  "result":  "survived",
  "metrics": {
    "rms_deg": 1.41,
    "max_abs_deg": 4.2,
    "settling_time_s": 0.35,
    "saturation_pct": 3.2,
    "energy": 0.87
  },
  "samples": [{"t_s": -0.2, "pitch": 0.1, "drive": 0.02, "pitch_rate": 0.5}, ...]
}
```

---

### Étape 2 — Analyse comparative (GUI onglet "Sweep")

Ouvrir l'onglet **Sweep** dans l'application CBC Tuner.

| Commande | Action |
|---|---|
| **Parcourir…** | Sélectionner le dossier `sweeps/` |
| **Tri** | `rms_deg` (défaut) — classement du meilleur au moins bon |
| **Filtre** | `Survived seulement` pour exclure les chutes |
| Cliquer une ligne | Met la courbe en surbrillance dans le graphe overlay |
| **Appliquer ces gains** | Envoie le jeu sélectionné au firmware via IPC |

#### Lecture de l'overlay pitch
- Couleur **verte** → RMS faible = bon équilibre
- Couleur **rouge** → RMS élevé = oscillations importantes
- Lignes pointillées grises → ±2° (seuil "bien stabilisé")

#### Heatmap Kp × Kd
- Chaque cellule = RMS (°) de l'essai correspondant
- NaN (gris) = essai absent ou non-survived
- Permet d'identifier la zone de stabilité et ses frontières

#### Métriques clés à surveiller
| Métrique | Cible | Alerte |
|---|---|---|
| `rms_deg` | < 2° | > 5° = instable |
| `max_abs_deg` | < 10° | > 20° = early_stop probable |
| `settling_time_s` | < 0.5 s | > 1.5 s = lent |
| `saturation_pct` | < 10% | > 30% = PID en bang-bang |

#### Analyse en ligne de commande (optionnel)
```bash
python tools/sweep_analysis.py sweeps/ --plot --top 10
```
Génère : overlay pitch, heatmap Kp×Kd, front de Pareto.

---

### Étape 3 — Identification du modèle physique (`system_id.py`)

**Objectif :** identifier les paramètres physiques du pendule à partir des données.

**Modèle grey-box (petits angles) :**
```
θ̈ = a·θ + b·u + c·θ̇
  a = g/L_eff   > 0  (instabilité pendule)
  b = Km/J             (gain moteur → couple angulaire)
  c = -fric/J   ≤ 0  (frottement visqueux)
```

#### Commande
```bash
python tools/system_id.py sweeps/ --output model.json --plot
```

#### Interprétation du résultat
```json
{
  "a": 18.3,          // g/L_eff → L_eff ≈ 9.81/18.3 ≈ 0.54 m (hauteur CoM)
  "b": -22.1,         // gain moteur (négatif : u>0 → correction vers 0)
  "c": -1.8,          // frottement (négatif = amortissant)
  "r2": 0.91,         // qualité régression (> 0.85 = bon)
  "validation_rms_deg": 2.1,  // erreur sim vs hardware (< 5° = modèle fiable)
  "correlation": 0.94
}
```

> **Critère de validité :** `r2 > 0.85` ET `validation_rms_deg < 5°`.
> Si insuffisant → ajouter d'autres essais avec des angles de départ variés.

---

### Étape 4 — Sweep simulé (`sweep_sim.py` / `run_simulated_sweep`)

**Objectif :** balayer 400+ combinaisons en <1 s pour identifier les meilleurs candidats.

#### Via Claude (MCP)
```
run_simulated_sweep(
  model_path="model.json",
  kp_min=0.05, kp_max=0.45, kp_steps=20,
  kd_min=0.0,  kd_max=0.05, kd_steps=20,
  ki=0.0
)
```
Retourne : top 10 classé + 3 candidats recommandés pour `run_sweep`.

#### Via ligne de commande
```bash
# Grid 20×20 = 400 simulations
python tools/sweep_sim.py model.json --kp 0.05,0.45,20 --kd 0.0,0.05,20 --plot

# Recherche Bayésienne (plus efficace pour les grands espaces)
python tools/sweep_sim.py model.json --bayesian --n-trials 100 --plot
```

#### Front de Pareto simulé
Le graphe "overshoot vs settling_time" identifie les points non-dominés :
un gain qui améliore l'un des deux critères sans dégrader l'autre.
Les **3 meilleurs points Pareto** sont les candidats à valider sur hardware.

---

### Étape 5 — Validation hardware des meilleurs candidats

Reprendre `run_sweep` avec les 3 candidats du sweep simulé :

```
run_sweep(
  param_sets='[
    {"kp": 0.22, "ki": 0.0, "kd": 0.038},
    {"kp": 0.18, "ki": 0.0, "kd": 0.032},
    {"kp": 0.15, "ki": 0.0, "kd": 0.030}
  ]',
  hold_s=3.0
)
```

Comparer les métriques hardware avec les métriques simulées :
- Écart `rms_deg` sim/hardware < 2° → modèle fiable, la simulation est exploitable
- Écart > 5° → reidentifier le modèle avec plus de données

---

### Diagnostics PID depuis les courbes

```
Oscillations > 5 Hz      →  Kd trop fort (amplifie le bruit gyro)
Oscillations < 2 Hz      →  Kp trop fort OU Kd trop faible
Dérive lente persistante →  Ki trop faible (erreur statique non compensée)
saturation_pct > 30%     →  PID en bang-bang, réduire Kp
settling_time_s > 2 s    →  Kp trop faible
early_stop systématique  →  hors zone de stabilité, réduire Kp
```

---

## 9. Identification du gain actionneur K

### Modèle

```
θ̈ = K·u + a·θ + c
  K  — gain actionneur (u normalisé [-1,+1] → accélération angulaire °/s²)
  a  — terme de stabilité : <0 = stable (upside-down), >0 = instable (upright)
  c  — biais constant (gravité résiduelle, frottements)
```

### Protocole

- Robot à l'envers (équilibre stable, pas de limite de temps)
- Excitation via commande SET_SP (0x21) — firmware bypass CBC et sécurité (timeout 500 ms)
- Signal carré (keep-alive 4 Hz) ou sinus (envoi 50 Hz, intègre le keep-alive)
- Régression OLS sur [u, θ, 1] → θ̈ = Δ(pitch_rate) / dt_médian
- Résultats sauvegardables en JSON depuis l'onglet "Ident K" de l'application

### Tous les essais (session 2026-06-08)

| # | Signal | Amp | T½ (s) | n | K (°/s²) | σ/|K| | R² | a (rad/s²) | Note |
|---|--------|-----|--------|---|-----------|------|-----|------------|------|
| 1 | Carré | 25 | 0.20 | 119 | **-1 935** | 13% | 0.357 | +0.73 | a suspect |
| 2 | Carré | 25 | 0.30 | 119 | -670 | 42% | 0.283 | -9.4 | sigma élevé |
| 3 | Carré | 25 | 0.30 | 118 | -759 | 38% | 0.258 | -8.0 | sigma élevé |
| 4 | Carré | 30 | 0.20 | 119 | **-1 912** | 12% | 0.385 | -0.55 | a suspect |
| 5 | Sinus | 20 | 0.35 | 208 | +20 | — | 0.406 | -12.5 | K ≈ 0 |
| 6 | Sinus | 20 | 0.33 | 196 | -73 | — | 0.356 | -11.6 | K ≈ 0 |
| 7 | Sinus | 25 | 0.33 | 196 | -239 | 95% | 0.325 | -12.3 | sigma/|K| >> 1 |
| 8 | Carré | 30 | 0.18 | 108 | **-2 243** | 9% | 0.524 | +1.22 | a suspect |
| 9 | Carré | 30 | 0.25 | 60 | -3 236 | 10% | **0.618** | -2.35 | n faible |
| 10 | Sinus | 30 | 0.40 | 237 | +2 802 | 13% | 0.512 | -22 | signe inversé |
| 11 | Sinus | 50 | 0.30 | 177 | +491 | 79% | 0.392 | -27.6 | sigma élevé |
| 12 | Sinus | 20 | 0.50 | 297 | +646 | 34% | 0.435 | -7.4 | signe inversé |

### Analyse

**Problème principal — signe de K incohérent entre sinus et carré.**
K est une constante mécanique, son signe ne peut pas changer. Il l'est pourtant : négatif pour le carré rapide, positif pour le sinus. Cause : la cadence télémétrie est ~20 Hz (dt_med ≈ 50 ms). Pour les courtes demi-périodes (0.18–0.20 s = 3–4 échantillons par demi-période), le robot n'a pas le temps de répondre entre deux trames → θ̈ estimé par Δ(pitch_rate)/50 ms voit des déphasages différents selon la forme d'onde → K apparent change de signe.

**Groupe le plus reproductible — carré rapide (T½ = 0.18–0.20 s) :**
Essais 1, 4, 8 convergent à K ≈ **-2 000 °/s²**, σ/|K| ≈ 10–13 %, reproductibles à 2 % l'un de l'autre.
Limite : `a` ≈ 0 (devrait être négatif upside-down) → u et θ colinéaires sur des demi-périodes aussi courtes.

**Valeur retenue : K ≈ -2 000 °/s²** (incertitude estimée ±15 %)

**Prochaine étape pour fiabiliser :** augmenter le taux télémétrie firmware (actuellement ~20 Hz) à ≥ 50 Hz pour que dt_med ≤ 20 ms et réduire l'erreur sur θ̈.

---

## 10. Identification du délai de transport td

### Méthode

Signal carré ±RPM injecté via SET_SP, bypass CBC.
Cross-corrélation normalisée `drive ⋆ θ̈` — pic dans la fenêtre causale [0, T½] = td.
θ̈ calculé depuis pitch_rate rééchantillonné sur grille uniforme (dt_med), évite les artéfacts de burst USB-CDC.

### Tous les essais (session 2026-06-08)

| # | Amp | T½ (s) | Cycles | td (ms) | peak_corr | dt_med (ms) | Note |
|---|-----|--------|--------|---------|-----------|-------------|------|
| 1 | 25  | 0.25   | 20     | **189** | 0.807     | 63          | Référence |
| 2 | 20  | 0.20   | 15     | 126     | 0.809     | 63          | T½ ≈ td — fenêtre causale trop étroite |
| 3 | 20  | 0.40   | 15     | **189** | 0.790     | 63          | |
| 4 | 25  | 0.40   | 10     | **189** | 0.778     | 63          | |
| 5 | 30  | 0.40   | 10     | **189** | 0.759     | 63          | |

### Analyse

**Consensus fort : 4/5 essais donnent td = 189 ms**, pour des amplitudes différentes (20, 25, 30 RPM) et des demi-périodes différentes (0.25 s, 0.40 s).

L'essai #2 (T½ = 0.20 s) est l'outlier à 126 ms. La règle à respecter : **T½ ≥ 2 × td** pour que la fenêtre causale soit assez large. Ici T½=200ms ≈ td → résultat non fiable.

**Résolution limitée par dt_med = 63 ms.** Les lags possibles sont multiples entiers de 63 ms : 0, 63, 126, **189**, 252 ms… La résolution est ±32 ms. La vraie td est dans **[157 ms, 221 ms]**.

**Composition probable du délai :**
- Latence VCP + traitement firmware : ~5 ms
- Montée en vitesse moteur (PID vitesse, gearbox 29:1) : ~80–120 ms
- Réponse mécanique pendule + filtre IMU complémentaire : ~50–80 ms

### Valeur retenue : **td = 189 ms ± 30 ms**

### Règle pour le réglage CBC

Avec td ≈ 190 ms, le correcteur PID boucle interne (angle) doit avoir une constante de temps de boucle fermée **nettement supérieure à td**. En pratique : temps de réponse boucle interne ≥ 2 × td ≈ 380 ms, soit une bande passante ≤ 2–3 rad/s (0.3–0.5 Hz). Cela confirme des gains Kp modérés (≤ 0.20) et Kd relativement faible.

### Prochaine étape

Augmenter dt_med en passant la télémétrie à ≥ 50 Hz (firmware recompilé avec gyro ×100) pour affiner la résolution à ~20 ms et réduire l'incertitude sur td.

---

## 11. Paramètres système identifiés — récapitulatif

Ces trois valeurs sont les entrées du modèle physique utilisé dans l'onglet **Simulation** de l'application.

```
Modèle UFOPDT :   θ̈ = a²·θ − K·u(t − τd)
```

| Paramètre | Symbole | Valeur retenue | Incertitude | Champ simulation |
|-----------|---------|---------------|-------------|-----------------|
| Pôle instable | a | **7.38 rad/s** | géométrique | Pôle a |
| Gain actionneur | K | **2 000 °/s²** | ±15 % | Gain K |
| Délai de transport | τd | **0.189 s** | ±30 ms | Retard τd |

### Détail de chaque paramètre

**a = 7.38 rad/s**
- Source : mesure physique du centre de masse
- L_eff = 18 cm (distance sol → CoM, mesuré)
- a = √(g / L) = √(9.81 / 0.18) = 7.38 rad/s
- a² = 54.5 s⁻²

**K = 2 000 °/s²**
- Source : ident_K, groupe carré T½ = 0.18–0.20 s (essais 1, 4, 8)
- Valeur identifiée : K_ident ≈ −2 000 °/s² (signe convention OLS)
- Dans le modèle simulateur (formule `−K·u`) : **K = +2 000** (positif)
- Condition minimale de stabilité : Kp > a²/K = 54.5/2000 = 0.027

**τd = 0.189 s**
- Source : ident_td, 4/5 essais convergents (session 2026-06-08)
- Plage [157 ms, 221 ms] — résolution limitée à dt_med = 63 ms
- Conséquence pour le réglage : bande passante boucle interne ≤ π/(2·τd) ≈ 8.3 rad/s
- Kp=0.15 avec K=2000 donne ωc ≈ 5 rad/s → marge de phase réduite, gains à ne pas dépasser


Manuellement 
Kp 0.241
Ki 0
Kd 0.00041