# GPIO Mapping — STM32WB5MMG (MB1292B) ↔ Périphériques

**Version:** 0.1 | **Date:** 2026-03-16
**⚠️ À valider contre le schéma MB1292B (UM2619) avant câblage — certains pins peuvent être occupés par les périphériques onboard du Discovery kit (LCD, capteurs, etc.)**

---

## Allocation des périphériques STM32

| Périphérique STM32 | Affectation | Justification |
|-------------------|-------------|---------------|
| **TIM1** (avancé) | PWM moteurs A et B | Timer avancé : meilleure résolution, deadtime, complémentaires |
| **TIM2** (32 bits) | Encodeur moteur A | 32 bits = pas d'overflow sur la durée de session |
| **TIM3** | Encodeur moteur B | Mode encoder hardware, 16 bits suffisant |
| **I2C1** | MPU6050 | Fast Mode 400 kHz |
| **LPUART1** | Liaison UART → RPi 3B | Basse consommation, pins PA2/PA3 libres |
| **ADC1** | Tension batterie + courant moteurs (optionnel) | Canaux IN5, IN6, IN14 |

---

## Table de mapping GPIO complète

### Moteurs — Driver L298 (Arduino Motor Shield)

| Fonction | Signal L298 | Pin STM32 | Mode | Alternate Function | Notes |
|----------|------------|-----------|------|--------------------|-------|
| Vitesse moteur A | ENA (PWM) | **PA8** | AF | TIM1_CH1 — AF1 | PWM ≥ 1 kHz |
| Vitesse moteur B | ENB (PWM) | **PA9** | AF | TIM1_CH2 — AF1 | PWM ≥ 1 kHz |
| Direction A avant | IN1 | **PB0** | GPIO Output | — | HIGH = avant |
| Direction A arrière | IN2 | **PB1** | GPIO Output | — | HIGH = arrière |
| Direction B avant | IN3 | **PC4** | GPIO Output | — | HIGH = avant |
| Direction B arrière | IN4 | **PC5** | GPIO Output | — | HIGH = arrière |
| Frein moteur A | BRAKE_A | **PC8** | GPIO Output | — | LOW = roue libre |
| Frein moteur B | BRAKE_B | **PC9** | GPIO Output | — | LOW = roue libre |
| Courant moteur A | CS_A | **PA5** | Analog | ADC1_IN10 — AF | Optionnel |
| Courant moteur B | CS_B | **PA4** | Analog | ADC1_IN9 — AF | Optionnel |

**Logique de commande moteur A (IN1 / IN2 / ENA) :**

| Action | IN1 | IN2 | ENA |
|--------|-----|-----|-----|
| Avant | 1 | 0 | PWM |
| Arrière | 0 | 1 | PWM |
| Roue libre | 0 | 0 | 0 |
| Frein rapide | 1 | 1 | 1 |

---

### Encodeurs quadrature (mode QEI hardware)

| Fonction | Signal | Pin STM32 | Mode | Alternate Function | Notes |
|----------|--------|-----------|------|--------------------|-------|
| Encodeur A — Phase A | ENC_A_CHA | **PA15** | AF | TIM2_CH1 — AF1 | Pull-up interne activé |
| Encodeur A — Phase B | ENC_A_CHB | **PB3** | AF | TIM2_CH2 — AF1 | Pull-up interne activé |
| Encodeur B — Phase A | ENC_B_CHA | **PA6** | AF | TIM3_CH1 — AF2 | Pull-up interne activé |
| Encodeur B — Phase B | ENC_B_CHB | **PA7** | AF | TIM3_CH2 — AF2 | Pull-up interne activé |

**Configuration TIM2 / TIM3 :**
- Mode : `TIM_ENCODERMODE_TI12` (comptage sur les deux fronts, ×4)
- Résolution effective : 64 CPR × 4 × 29 = **7424 ticks/tour**
- TIM2 (32 bits) : compteur signé, range ±2 147 483 648 — débordement impossible
- TIM3 (16 bits) : lire et accumuler dans un int32 logiciel à chaque cycle

---

### IMU — MPU6050

| Fonction | Signal | Pin STM32 | Mode | Alternate Function | Notes |
|----------|--------|-----------|------|--------------------|-------|
| Horloge I²C | SCL | **PB8** | AF | I2C1_SCL — AF4 | Pull-up 4.7 kΩ externe |
| Données I²C | SDA | **PB9** | AF | I2C1_SDA — AF4 | Pull-up 4.7 kΩ externe |
| Interruption data-ready | INT | **PC12** | GPIO EXTI | — | EXTI12, front montant |

**Adresse I²C :** `0x68` (AD0 à GND) ou `0x69` (AD0 à VCC)

---

### Liaison UART — Raspberry Pi 3B

| Fonction | Signal | Pin STM32 | Mode | Alternate Function | Côté RPi |
|----------|--------|-----------|------|--------------------|----------|
| Émission STM→RPi | TX | **PA2** | AF | LPUART1_TX — AF8 | GPIO15 (RXD) — pin 10 |
| Réception RPi→STM | RX | **PA3** | AF | LPUART1_RX — AF8 | GPIO14 (TXD) — pin 8 |

**⚠️ Niveaux logiques :** STM32 = 3,3 V / RPi = 3,3 V → **compatibles directement, pas de level shifter requis.**
**Vitesse :** 115 200 baud, 8N1
**GND commun obligatoire** entre les deux cartes.

---

### Surveillance batterie

| Fonction | Signal | Pin STM32 | Mode | Notes |
|----------|--------|-----------|------|-------|
| Tension batterie | VBAT_MON | **PA0** | Analog ADC1_IN5 | Diviseur résistif : 100 kΩ / 22 kΩ → 12 V mappe sur ~2,16 V (< 3,3 V) |

**Formule :** `V_bat = ADC_value × (3.3 / 4095) × (100 + 22) / 22`

---

## Récapitulatif des pins utilisés

```
PA0  — ADC (tension batterie)
PA2  — LPUART1_TX (→ RPi)
PA3  — LPUART1_RX (← RPi)
PA4  — ADC (courant moteur B, optionnel)
PA5  — ADC (courant moteur A, optionnel)
PA6  — TIM3_CH1 (encodeur B phase A)
PA7  — TIM3_CH2 (encodeur B phase B)
PA8  — TIM1_CH1 (PWM moteur A)
PA9  — TIM1_CH2 (PWM moteur B)
PA15 — TIM2_CH1 (encodeur A phase A)
PB0  — GPIO (IN1 moteur A)
PB1  — GPIO (IN2 moteur A)
PB3  — TIM2_CH2 (encodeur A phase B)
PB8  — I2C1_SCL (MPU6050)
PB9  — I2C1_SDA (MPU6050)
PC4  — GPIO (IN3 moteur B)
PC5  — GPIO (IN4 moteur B)
PC8  — GPIO (BRAKE moteur A)
PC9  — GPIO (BRAKE moteur B)
PC12 — GPIO EXTI (MPU6050 INT)
```

---

## Connexion au Raspberry Pi 3B

| RPi Header Pin | RPi Signal | ←→ | STM32 Pin | Fonction |
|----------------|------------|-----|-----------|---------|
| Pin 8 | GPIO14 (TXD) | → | PA3 (RX) | RPi envoie → STM32 reçoit |
| Pin 10 | GPIO15 (RXD) | ← | PA2 (TX) | STM32 envoie → RPi reçoit |
| Pin 6 | GND | — | GND | Masse commune |

**Activation UART matériel RPi :** désactiver la console série et activer `uart0` dans `/boot/config.txt` :
```
enable_uart=1
dtoverlay=disable-bt   # libère /dev/ttyAMA0 du Bluetooth interne
```

---

## Notes de câblage avec l'Arduino Motor Shield

Le Motor Shield est conçu pour se clipser sur un Arduino Uno. Ici on câble manuellement ses broches de contrôle vers le STM32.

**Broches utiles sur le Motor Shield (côté Arduino header) :**

| Motor Shield | Arduino pin | Connecter à |
|-------------|------------|-------------|
| PWMA | D3 | PA8 (STM32) |
| DIRA | D12 | PB0 (STM32) |
| BRAKEA | D9 | PC8 (STM32) |
| PWMB | D11 | PA9 (STM32) |
| DIRB | D13 | PC4 (STM32) |
| BRAKEB | D8 | PC9 (STM32) |
| CS_A | A0 | PA5 (STM32) |
| CS_B | A1 | PA4 (STM32) |
| 5V | 5V | Rail 5V régulé |
| GND | GND | GND commun |
| Vin | — | 12V batterie directement |

**Remarque IN1/IN2 :** Le Motor Shield simplifie le L298 avec une logique DIR unique (1 seul signal de direction). En interne, il câble IN1 = DIR et IN2 = ~DIR. On n'a donc besoin que de PB0 pour DIR_A et PC4 pour DIR_B, pas de IN2/IN4 séparés — PB1 et PC5 peuvent être réservés ou ignorés selon la version du shield.

---

## Conflits potentiels à vérifier sur MB1292B

| Pin | Usage proposé | Risque de conflit avec le Discovery kit |
|-----|---------------|----------------------------------------|
| PA8 | TIM1_CH1 PWM | Vérifier : LCD SPI ou LED onboard ? |
| PA9 | TIM1_CH2 PWM | Vérifier : connecteur CN |
| PB8 / PB9 | I2C1 | Vérifier : I2C onboard capteurs Discovery |
| PC8 / PC9 | GPIO | Vérifier : LED verte/orange du Discovery |
| PA15 | TIM2_CH1 | Vérifier : JTDI (debug) — désactiver en release |
| PB3 | TIM2_CH2 | Vérifier : JTDO/SWO (debug) — désactiver en release |

**Action requise :** consulter le schéma électrique MB1292B (document UM2619, disponible sur st.com) pour confirmer la disponibilité de chaque pin sur le connecteur d'extension avant câblage.
