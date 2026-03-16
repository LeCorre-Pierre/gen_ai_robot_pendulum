# MCU Comparison Matrix — Self-Balancing Robot

**Version:** 0.1 | **Date:** 2026-03-16
**Evaluation criteria based on:** `1-requirements.md`

---

## Candidates

| # | Board / Module | Chip | Core | Clock |
|---|----------------|------|------|-------|
| 1 | Raspberry Pico 2 | RP2350 | 2× Cortex-M33 (ou 2× RISC-V) | 150 MHz |
| 2 | MB1641C (NUCLEO-WB15CC) | STM32WB15CC | Cortex-M4 + Cortex-M0+ radio | 64 MHz / 32 MHz |
| 3 | Arduino Uno R3 | ATmega328P | 8-bit AVR | 16 MHz |
| 4 | MB1292B (STM32WB5MM-DK) | STM32WB5MMG | Cortex-M4 + Cortex-M0+ radio | 64 MHz / 32 MHz |
| 5 | MB1184C (32L476GDISCOVERY) | STM32L476VG | Cortex-M4 + FPU | 80 MHz |
| 6 | Raspberry Pi 3 Model B | BCM2837 | 4× Cortex-A53 | 1 200 MHz |

---

## Matrice de critères

Légende : ✅ Satisfait | ⚠️ Possible avec contrainte | ❌ Non satisfait

| Critère | Requis par | Pico 2 | STM32WB15CC | Arduino Uno R3 | STM32WB5MM-DK | STM32L476 | RPi 3B |
|---------|-----------|--------|-------------|----------------|---------------|-----------|--------|
| **Temps réel déterministe ≥200 Hz** | FW-002 | ✅ bare-metal, dual-core | ✅ M4 bare-metal / FreeRTOS | ⚠️ 16 MHz sans FPU, limite | ✅ M4 bare-metal | ✅ 80 MHz + FPU | ❌ Linux, non RT |
| **BLE natif (sans module externe)** | FW-020, HW-004 | ⚠️ Pico 2 W seulement | ✅ BLE 5.2 certifié | ❌ | ✅ BLE 5.2 certifié | ❌ | ⚠️ BT 4.1 (pas BLE 5.x) |
| **Hardware QEI (2 encodeurs)** | HW-002, FW-010 | ⚠️ PIO peut émuler QEI | ✅ TIM1/2/3 encoder mode | ❌ 2 INT seulement (1 encodeur) | ✅ TIM encoder mode | ✅ TIM2/3/4/5 encoder | ❌ pas de QEI matériel |
| **PWM moteurs ≥2 canaux** | HW-001, HW-024 | ✅ 24 canaux PWM | ✅ multi-timers | ✅ 6 canaux | ✅ multi-timers | ✅ multi-timers | ⚠️ GPIO PWM logiciel |
| **I²C ≥400 kHz (MPU6050)** | HW-003, HW-013 | ✅ 2× I²C | ✅ I²C Fast Mode | ✅ TWI 400 kHz | ✅ I²C Fast Mode | ✅ I²C Fast Mode+ | ✅ I²C |
| **FPU (calcul PID float)** | FW-001, FW-003 | ✅ Cortex-M33 FPU | ✅ Cortex-M4 FPU | ❌ soft-float AVR | ✅ Cortex-M4 FPU | ✅ Cortex-M4 FPU | ✅ (mais OS overhead) |
| **RAM/Flash suffisant** | NFR-001 | ✅ 520 KB / 4 MB | ⚠️ ~192 KB SRAM¹ / 1 MB | ❌ 2 KB / 32 KB | ✅ 256 KB / 1 MB | ✅ 128 KB / 1 MB | ✅ 1 GB / µSD |
| **Stack BLE mature & certifié** | FW-020–023 | ⚠️ CYW43439, moins documenté | ✅ ST BLE stack certifié | ❌ | ✅ ST BLE stack certifié | ❌ | ⚠️ BlueZ (Linux, lourd) |
| **Compatibilité Arduino Motor Shield** | HW-022 | ❌ pas de form factor UNO | ❌ format NUCLEO-64 | ✅ natif (même form factor) | ❌ Discovery board | ❌ Discovery board | ❌ |
| **Intégration physique (robot compact)** | SYS-004 | ✅ petit (51×21 mm) | ✅ compact (NUCLEO-64 : 70×55 mm) | ✅ standard (68×53 mm) | ❌ très grand Discovery | ❌ très grand Discovery | ❌ grand + Linux SD |
| **Consommation (autonomie)** | HW-030 | ✅ faible | ✅ ultra-low power | ⚠️ modéré | ✅ faible | ✅ ultra-low power | ❌ 2–3 W minimum |
| **Facilité de développement** | NFR-001 | ✅ SDK C/C++, CMake | ⚠️ STM32CubeIDE, HAL/LL | ✅ Arduino IDE, vaste communauté | ⚠️ STM32CubeIDE | ⚠️ STM32CubeIDE | ⚠️ Linux, pas RT |
| **Debugger embarqué (ST-Link / SWD)** | NFR-001 | ⚠️ SWD via picoprobe externe | ✅ ST-Link onboard (NUCLEO) | ⚠️ ICSP, pas de debug HW facile | ✅ ST-Link onboard | ✅ ST-Link onboard | ❌ pas de SWD |
| **Coût estimé** | — | ✅ ~7 € (Pico 2 W) | ✅ ~20–25 € | ✅ ~25 € | ⚠️ ~50–70 € (Discovery) | ⚠️ ~30–50 € (Discovery) | ❌ ~35–45 € + alim |

> ¹ STM32WB15CC : SRAM totale 320 KB mais ~128 KB est réservé au core radio selon la configuration BLE.

---

## Score synthétique

Les critères **CRITICAL** (FW-002, HW-001–004, FW-020, FW-030) comptent double.

| Candidat | ✅ | ⚠️ | ❌ | Score /14 | Bloquants |
|----------|----|----|-----|-----------|-----------|
| **STM32WB15CC** | 10 | 3 | 1 | **11.5** | RAM à vérifier selon config BLE |
| **STM32WB5MM-DK** | 9 | 3 | 2 | **10.5** | Form factor (Discovery board) |
| **Raspberry Pico 2 (W)** | 9 | 4 | 1 | **11** | BLE uniquement sur Pico 2 W, QEI via PIO |
| **STM32L476** | 8 | 2 | 4 | **9** | Pas de BLE natif (critique) |
| **Arduino Uno R3** | 5 | 3 | 6 | **6.5** | QEI insuffisant, RAM critique, pas de FPU |
| **Raspberry Pi 3B** | 3 | 3 | 8 | **4.5** | Pas de temps réel, pas de QEI |

---

## Analyse détaillée par candidat

### 1. Raspberry Pico 2 (W) — RP2350
**Pour :**
- Dual-core 150 MHz : core 0 = boucle de contrôle, core 1 = BLE + comms
- PIO (Programmable I/O) : émulation hardware QEI sans charge CPU, très puissant
- 520 KB SRAM large confort, 4 MB flash
- 24 canaux PWM
- Très faible coût (~7 € pour la version W avec BLE)
- SDK C/C++ moderne, CMake, support FreeRTOS

**Contre :**
- BLE uniquement sur Pico **2 W** (version W) — la Pico 2 standard n'a pas BLE
- Stack BLE (CYW43439) moins mature que ST pour les GATT custom
- Pas de ST-Link embarqué → picoprobe ou debugger externe
- Pas de form factor Arduino → Motor Shield non compatible en plug-in

---

### 2. STM32WB15CC (MB1641C - NUCLEO-WB15CC) ⭐ Recommandé
**Pour :**
- Architecture dual-core dédiée : M4 = application temps réel, M0+ = stack BLE isolée → **zéro contention** entre contrôle et BLE
- BLE 5.2 certifié CE/FCC, stack ST robuste avec profils GATT customisables
- Hardware timers avec **encoder interface mode** natif (TIM1, TIM2, TIM3)
- Ultra-low power → excellente autonomie sur batterie
- ST-Link V3 embarqué sur NUCLEO → debug SWD/JTAG direct
- STM32CubeIDE, HAL/LL, FreeRTOS disponible
- Format NUCLEO-64 compact (70×55 mm)

**Contre :**
- RAM applicative réduite selon config BLE (vérifier partage mémoire M4/M0+)
- Courbe d'apprentissage STM32CubeIDE + stack BLE propriétaire ST
- Fréquence M4 limitée à 64 MHz (suffisant, mais moins que STM32L476 à 80 MHz)
- Non compatible plug-in avec Arduino Motor Shield → câblage manuel requis

---

### 3. Arduino Uno R3 — ATmega328P
**Pour :**
- **Seul candidat compatible plug-in avec l'Arduino Motor Shield** (même form factor)
- Écosystème Arduino massif, bibliothèques disponibles pour MPU6050, PID, encodeurs
- Prototypage très rapide
- Faible coût

**Contre :**
- **2 KB RAM = bloquant** : buffer BLE + PID + encoder + IMU dépasse largement
- **Seulement 2 interruptions externes** (INT0/INT1) : impossible de gérer 2 encodeurs quadrature en interruption (il faut 4 canaux). PCINT utilisables mais bien plus lents
- **Pas de FPU** : calcul PID flottant × 200 Hz + I²C MPU6050 dépasse la capacité à 16 MHz
- **Pas de BLE** : nécessite module externe (HC-05, HM-10, etc.), complexité supplémentaire
- Pas scalable pour l'extension de fonctionnalités

---

### 4. STM32WB5MM-DK (MB1292B)
**Pour :**
- Même cœur applicatif que STM32WB15CC (M4 64 MHz + BLE 5.2)
- Plus de RAM disponible (moins contrainte par la radio)
- Capteurs onboard (accéléro, etc.) utiles en dev
- ST-Link embarqué

**Contre :**
- **Discovery board très large** → non intégrable dans le robot final
- Coût élevé pour ce qui est fonctionnellement identique au NUCLEO-WB15CC
- Sert mieux de **plateforme de développement** que de carte finale embarquée

---

### 5. STM32L476 Discovery (MB1184C)
**Pour :**
- **80 MHz + FPU** → meilleure puissance de calcul temps réel de la gamme STM32 présentée
- Hardware QEI natif sur multiple timers
- 128 KB RAM / 1 MB Flash — confortable
- IMU onboard (gyroscope + accéléromètre) → peut remplacer le MPU6050
- Ammeter embarqué → profiling consommation précieux
- ST-Link embarqué

**Contre :**
- **Pas de BLE natif** → module externe obligatoire (HM-10, nRF52...), câblage, firmware additionnel : **critère CRITICAL non satisfait**
- Discovery board grande et lourde → intégration robot difficile
- Devient pertinent uniquement si le BLE est délégué à un module externe et le budget permet un module de qualité

---

### 6. Raspberry Pi 3 Model B
**Pour :**
- Puissance CPU massive, Linux = facilité pour l'application de tuning
- BT 4.1 + WiFi intégré
- Idéal pour rôle de **master/companion computer** (IA, vision, interface haut niveau)

**Contre :**
- **Linux n'est pas temps réel** → boucle de contrôle à 200 Hz non garantie sans RT-kernel patch
- **Pas de QEI hardware** → encodeurs sur GPIO avec interruptions Linux = latence variable
- **PWM GPIO non déterministe** sous Linux
- Consommation 2–3 W : autonomie réduite
- **Non recommandé comme MCU de contrôle** — rôle possible uniquement comme couche supervision

---

## Recommandation

### Option A — Production / Optimal (recommandé)
> **STM32WB15CC (NUCLEO-WB15CC)**

Architecture dual-core M4+M0+ garantissant l'isolation totale entre la boucle de contrôle temps réel et la stack BLE. Tous les critères CRITICAL sont satisfaits. L'investissement dans la courbe d'apprentissage STM32 est rentabilisé sur la durée du projet.

### Option B — Prototypage rapide / Alternatif
> **Raspberry Pico 2 W**

Si la priorité est la vitesse de démarrage et le coût minimal. La puissance brute (150 MHz dual-core) et les PIO compensent l'absence de QEI matériel. Attention : vérifier la version **W** impérativement pour le BLE.

### Option C — Développement uniquement (pas la carte finale)
> **STM32WB5MM-DK** ou **STM32L476 Discovery**

Utiles pour la phase de développement firmware (ST-Link, périphériques de debug), mais trop volumineux pour le robot final. À coupler avec une migration vers le NUCLEO-WB15CC pour la production.

### À ne pas retenir comme MCU de contrôle
- **Arduino Uno R3** : RAM et interruptions insuffisants pour les exigences du projet. Conserver uniquement si le Motor Shield est réutilisé en le pilotant via I²C/UART depuis un MCU capable.
- **Raspberry Pi 3B** : rôle de superviseur haute couche possible, mais pas de contrôleur bas niveau.
