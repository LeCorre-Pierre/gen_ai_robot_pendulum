# GPIO Mapping — STM32WB5MMG (MB1292B) ↔ Périphériques

**Version:** 0.2 | **Date:** 2026-03-16
**Source :** Validé contre UM2825 (STM32WB5MM-DK User Manual, Rev 4, April 2025)

---

## Pins onboard MB1292B — À NE PAS UTILISER

Ces pins sont câblées aux périphériques du Discovery kit. Les réutiliser nécessiterait de dessouder des composants.

| Pin | Usage onboard | Remarque |
|-----|--------------|---------|
| PA8 | SAI1_CK2 — microphone numérique | **BLOQUANT** — ne pas utiliser |
| PA9 | SAI1_DI2 — microphone numérique | **BLOQUANT** — ne pas utiliser |
| PA7 | SPI1_MOSI — OLED + RGB LED | **BLOQUANT** |
| PA1 | SPI1_SCK — OLED | **BLOQUANT** |
| PH0 | SPI1_NSS — OLED chip select | Non accessible |
| PB9 | QSPI_BK_IO0 — Flash NOR 128 Mbit | **BLOQUANT** |
| PA3 | QSPI_BK_SCK — Flash NOR | **BLOQUANT** |
| PD3 | QSPI_BK_NCS — Flash NOR | — |
| PC8 | RST_DISP — reset OLED | **BLOQUANT** |
| PC9 | D/C_DISP — data/cmd OLED | **BLOQUANT** |
| PB13 | I2C3_SCL — ISM330DHCX onboard | **UTILISÉ** — IMU balance |
| PB11 | I2C3_SDA — ISM330DHCX onboard | **UTILISÉ** — IMU balance |
| PC6 | TSC_G4_IO1 — touch sensor | — |
| PB6 | USART1_TX — ST-Link VCP | Réservé debug |
| PB7 | USART1_RX — ST-Link VCP | Réservé debug |
| PA13 | SWDIO — débogage SWD | Réservé debug |
| PA14 | SWCLK — débogage SWD | Réservé debug |
| PA11 | USB_DM | — |
| PA12 | USB_DP | — |
| PC12 | Bouton utilisateur B1 (WKUP3) | **BLOQUANT** |
| PC13 | Bouton utilisateur B2 (WKUP2) | — |
| PB0 / PB1 | Non disponibles sur MB1292B | **BLOQUANT** |

> **IMU :** ISM330DHCX onboard sur I2C3 (PB13/PB11) — adresse `0x6B` — driver BSP ST — aucun câblage externe requis.

---

## Allocation des périphériques STM32 — Mapping corrigé

| Périphérique STM32 | Affectation | Justification |
|-------------------|-------------|---------------|
| **TIM1** | PWM moteurs A et B | CH1=PD14 (D3), CH2=PD15 (D9) — confirmés dans UM2825 |
| **TIM2** | Encodeur moteur A (32 bits) | CH1=PA15, CH2=PB3 — pas de conflit onboard |
| **TIM3** | Encodeur moteur B | CH1=PB4 (D12), CH2=PC7 — pas de conflit onboard |
| **I2C3** | ISM330DHCX onboard | SCL=PB13, SDA=PB11 — câblage interne MB1292B, drivers ST BSP |
| **LPUART1** | Liaison UART → RPi 3B | TX=PB5 (D1), RX=PC0 (D0) — confirmés dans UM2825 |
| **ADC1** | Tension batterie + courant moteurs | PA2 (A1), PA5 (A2), PC3 (A0) |

---

## Table de mapping GPIO complète — Version validée

### Moteurs — Driver L298 (Arduino Motor Shield)

| Fonction | Signal Motor Shield | Pin STM32 | Arduino | Mode | Notes |
|----------|--------------------|-----------|---------|----- |-------|
| PWM vitesse moteur A | PWMA | **PD14** | D3 | TIM1_CH1 AF1 | Fréq ≥ 1 kHz |
| PWM vitesse moteur B | PWMB | **PD15** | D9 | TIM1_CH2 AF1 | Fréq ≥ 1 kHz |
| Direction moteur A | DIRA | **PD12** | D2 | GPIO Output | 1=avant, 0=arrière |
| Frein moteur A | BRAKEA | **PD13** | D8 | GPIO Output | 0=roue libre |
| Direction moteur B | DIRB | **PE4** | D4 | GPIO Output | 1=avant, 0=arrière |
| Frein moteur B | BRAKEB | **PE0** | D6 | GPIO Output | 0=roue libre |
| Courant moteur A | CS_A | **PA5** | A2 | ADC1_IN10 | Optionnel |
| Courant moteur B | CS_B | **PC3** | A0 | ADC1_IN4 | Optionnel |

**Logique de commande L298 par le Motor Shield (1 pin DIR par moteur) :**

| Action | DIRA / DIRB | PWM | BRAKE |
|--------|------------|-----|-------|
| Avant | HIGH | duty% | LOW |
| Arrière | LOW | duty% | LOW |
| Roue libre | X | 0 | LOW |
| Frein rapide | X | X | HIGH |

---

### Encodeurs quadrature (mode QEI hardware)

| Fonction | Signal | Pin STM32 | Arduino / Conn. | Mode | Notes |
|----------|--------|-----------|-----------------|------|-------|
| Encodeur A — Phase A | ENC_A_CHA | **PA15** | STMod+ pin 14 | TIM2_CH1 AF1 | Pull-up interne |
| Encodeur A — Phase B | ENC_A_CHB | **PB3** | — | TIM2_CH2 AF1 | ⚠️ SWO — désactiver en Release |
| Encodeur B — Phase A | ENC_B_CHA | **PB4** | D12 | TIM3_CH1 AF2 | SPI1_MISO — OLED write-only, pin libre |
| Encodeur B — Phase B | ENC_B_CHB | **PC7** | — | TIM3_CH2 AF2 | TSC non utilisé → pin libre |

**Configuration TIM2 / TIM3 :**
- Mode : `TIM_ENCODERMODE_TI12` — comptage sur les deux fronts (×4)
- Résolution : 64 CPR × 4 × 29 = **7 424 ticks/tour**
- TIM2 (32 bits) : compteur signé ±2 147 483 648 — overflow impossible en session
- TIM3 (16 bits) : accumulation dans un `int32_t` logiciel à chaque cycle de contrôle

---

### IMU — ISM330DHCX (onboard MB1292B)

Le ISM330DHCX est câblé en interne sur le MB1292B. Aucun fil externe requis.

| Fonction | Signal | Pin STM32 | Mode | Notes |
|----------|--------|-----------|------|-------|
| Horloge I²C | SCL | **PB13** | I2C3_SCL AF4 | Câblage interne DK — pull-up onboard |
| Données I²C | SDA | **PB11** | I2C3_SDA AF4 | Câblage interne DK — pull-up onboard |
| Interruption data-ready | INT1 | **PB5** ou non câblé | GPIO EXTI | À vérifier dans schéma MB1292B — polling en fallback |

**Adresse I²C ISM330DHCX :** `0x6B` (SA0=VCC, défaut MB1292B)
**Driver :** utiliser le BSP `stm32wb5mm_dk_motion_sensors.c` (`USE_MOTION_SENSOR_ISM330DHCX_0`) ou le driver ST `ism330dhcx_reg.c` via CubeMX.
**Pins libérées :** PB8 (D15), PA10 (D14), PB2 (D7) — disponibles pour usage futur.

---

### Liaison UART — Raspberry Pi 3B

| Fonction | Signal | Pin STM32 | Arduino | Mode | Côté RPi |
|----------|--------|-----------|---------|------|----------|
| Émission STM→RPi | TX | **PB5** | D1 | LPUART1_TX AF8 | GPIO15 (RXD) — pin 10 |
| Réception RPi→STM | RX | **PC0** | D0 | LPUART1_RX AF8 | GPIO14 (TXD) — pin 8 |
| Masse commune | GND | GND | — | — | Pin 6 ou 14 |

**Niveaux logiques :** STM32 = 3,3 V / RPi GPIO = 3,3 V → **compatibles directement.**
**Vitesse :** 115 200 baud, 8N1

**Configuration RPi (/boot/firmware/config.txt) :**
```
enable_uart=1
dtoverlay=disable-bt
```
Et dans `/boot/firmware/cmdline.txt` : supprimer `console=serial0,115200`

---

### Surveillance tension batterie

| Fonction | Signal | Pin STM32 | Arduino | Mode | Notes |
|----------|--------|-----------|---------|------|-------|
| Tension batterie | VBAT_MON | **PA2** | A1 | ADC1_IN7 | Diviseur 100 kΩ / 22 kΩ |

**Formule :** `V_bat = (ADC / 4095.0) × 3.3 × (100 + 22) / 22`
Plage : 10 V → ADC ≈ 1 800 | 14 V → ADC ≈ 2 520

---

## Récapitulatif final — Tous les pins utilisés

```
PA2  ─── ADC1_IN7       (surveillance batterie)
PA5  ─── ADC1_IN10      (courant moteur A, optionnel)
PA15 ─── TIM2_CH1       (encodeur A phase A)

PB3  ─── TIM2_CH2       (encodeur A phase B) ⚠️ SWO release only
PB4  ─── TIM3_CH1       (encodeur B phase A)
PB5  ─── LPUART1_TX     (→ RPi)
PB11 ─── I2C3_SDA       (ISM330DHCX onboard — interne)
PB13 ─── I2C3_SCL       (ISM330DHCX onboard — interne)

PC0  ─── LPUART1_RX     (← RPi)
PC3  ─── ADC1_IN4       (courant moteur B, optionnel)
PC7  ─── TIM3_CH2       (encodeur B phase B)

PD12 ─── GPIO Output    (direction moteur A)
PD13 ─── GPIO Output    (frein moteur A)
PD14 ─── TIM1_CH1       (PWM moteur A)
PD15 ─── TIM1_CH2       (PWM moteur B)

PE0  ─── GPIO Output    (frein moteur B)
PE4  ─── GPIO Output    (direction moteur B)

-- Pins libérées (ex-MPU6050 externe) --
PA10 ─── libre (ex I2C1_SDA)
PB2  ─── libre (ex MPU6050 INT)
PB8  ─── libre (ex I2C1_SCL)
```

---

## Points d'attention avant câblage

| # | Point | Action |
|---|-------|--------|
| 1 | **PB3 = SWO (debug trace)** | Fonctionnel en Release. En Debug, désactiver le tracé SWO dans CubeIDE ou choisir un autre pin |
| 2 | **PB4 = SPI1_MISO** | L'OLED est en mode write-only (pas de lecture) → MISO non utilisé → pin libre ✅ |
| 3 | **PC7 = TSC touch** | Le Touch Sense Controller n'est pas activé → PC7 libre ✅ |
| 4 | **PA15 = STMod+ pin 14** | Accessible via le connecteur STMod+ ou un fil soudé |
| 5 | **I2C3 — ISM330DHCX** | PB13/PB11 câblés en interne sur le DK. Activer I2C3 dans CubeMX, utiliser driver BSP ST. Adresse `0x6B`. ✅ |
| 6 | **Pins libérées** | PB8, PA10, PB2 (ex-MPU6050) sont libres pour usage futur si besoin. |

---

## Câblage Motor Shield → STM32 (manuel, fils volants)

| Motor Shield header | Arduino pin | Connecter au pin STM32 |
|--------------------|-----------|-----------------------|
| PWMA | D3 | PD14 (D3 Arduino MB1292B) |
| DIRA | D12 | PD12 (D2 Arduino MB1292B) |
| BRAKEA | D9 | PD13 (D8 Arduino MB1292B) |
| PWMB | D11 | PD15 (D9 Arduino MB1292B) |
| DIRB | D13 | PE4 (D4 Arduino MB1292B) |
| BRAKEB | D8 | PE0 (D6 Arduino MB1292B) |
| CS_A | A0 | PA5 (A2 Arduino MB1292B) |
| CS_B | A1 | PC3 (A0 Arduino MB1292B) |
| VCC (5V logique) | 5V | Rail 5V buck converter |
| GND | GND | GND commun |
| Vin (moteurs) | — | 12V batterie directement |
