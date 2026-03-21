# mb1292b-controller — Documentation architecture

## Description

Application BLE Sensor de référence STMicroelectronics pour la carte STM32WB5MM-DK (MB1292B), démontrant la diffusion en temps réel de données multi-capteurs via BLE 5.2 avec affichage OLED local.

---

## Architecture

### Plateforme matérielle

| Composant | Détail |
|-----------|--------|
| MCU | STM32WB5MMGHx (LGA86) |
| Cœur application | Cortex-M4 @ 64MHz (CM4) |
| Cœur BLE | Cortex-M0+ (CM0+) — stack BLE 5.2 pré-compilée |
| Flash | 512 KB |
| RAM CM4 | 196 KB |
| RAM partagée CM4/CM0+ | 10 KB (IPCC mailbox) |
| IMU | ISM330DHCX — accéléro 3 axes + gyro 3 axes (I2C3, addr 0x6B) |
| Capteur température | STTS22H (I2C3, addr variable) |
| Capteur distance | VL53L0X ToF — optionnel (I2C3, addr 0x53) |
| Afficheur | SSD1315 OLED 128×64 px, 1 bit, Font12 |
| UART debug | USART1 (PB6/PB7) via ST-LINK VCP |
| UART bridge externe | LPUART1 (PB5/PC0) sur connecteur Arduino D0/D1 |

### Structure logicielle

```
BLE_Sensor/
├── Core/Src/
│   ├── main.c                  — init horloge (HSE+PLL → 64MHz), boucle principale
│   ├── app_entry.c             — init périphériques (LCD, IMU, capteur ToF, boutons, UART)
│   ├── app_vl53l0x.c           — pilote VL53L0X, timer 500ms, affichage OLED distance
│   ├── hw_uart.c               — couche UART avec DMA et callbacks
│   └── hw_timerserver.c        — serveur de timers virtuels basé sur RTC
│
├── STM32_WPAN/App/
│   ├── app_ble.c               — init stack BLE, FSM connexion GAP/GATT, affichage boot
│   ├── motenv_server_app.c     — agrégateur MOTENV : orchestre les timers Motion/Env
│   ├── motion_server_app.c     — service Motion : lecture ISM330DHCX, notif BLE, affichage
│   ├── env_server_app.c        — service Env : lecture STTS22H, notif BLE, affichage
│   ├── p2p_server_app.c        — service P2P : contrôle LED RGB, bouton SW1 notify
│   └── wb5m_sensor_stm.h/c     — définition des services/caractéristiques GATT MOTENV
│
└── STM32_WPAN/Target/
    └── hw_ipcc.c               — communication inter-cœurs CM4 ↔ CM0+ (6 canaux IPCC)
```

### Modèle d'exécution

Pas de FreeRTOS. L'application utilise deux primitives STM32 :

- **STM32 Sequencer (`UTIL_SEQ`)** : ordonnanceur coopératif. Les tâches sont enregistrées (`RegTask`) puis déclenchées (`SetTask`). La boucle principale appelle `UTIL_SEQ_Run()` en continu.
- **Timer Server (`HW_TS`)** : jusqu'à 6 timers virtuels basés sur le RTC (LSE 32 kHz). Chaque expiration pose un drapeau `UTIL_SEQ_SetTask()`.

Exemple de chaîne distance :
```
RTC timer 500ms → VL53L0X_PROXIMITY_Update_Timer_Callback()
  → UTIL_SEQ_SetTask(CFG_TASK_GET_MEASURE_TOF_ID)
    → VL53L0X_PROXIMITY_PrintValue()   [tâche séquentielle]
      → VL53L0X_PROXIMITY_GetDistance() → I2C3 → mesure single-shot
      → UTIL_LCD_DisplayStringAtLine(2, "Distance : NNN cm")
      → BSP_LCD_Refresh(0)
```

### Services GATT BLE

Nom d'annonce : **"WB5M DK"** (P2P\_SERVER1)
PIN BLE : **111111**
Timeout advertising : 30s fast → 60s slow → arrêt

| Service | UUID | Caractéristique | Taux | Format payload |
|---------|------|-----------------|------|----------------|
| MOTENV Motion | custom STM | AccGyroMag | 50 ms (20 Hz) | `[2B timestamp, 2B ax, 2B ay, 2B az, 2B gx, 2B gy, 2B gz]` (little-endian) |
| MOTENV Env | custom STM | Temperature | 500 ms | `[2B timestamp, 2B temp×10 °C]` |
| P2P Server | custom STM | LED / Button | sur événement | write (LED on/off), notify (SW1) |

---

## Écrans OLED — Description détaillée

L'OLED SSD1315 (128×64 px) est organisée en 5 lignes logiques (Font12, hauteur ≈ 12px). Il n'existe pas de système de menu à navigation : l'affichage est piloté par les événements BLE et les timers.

---

### Écran 1 — Info BLE au démarrage (durée 4 s)

Affiché une seule fois au démarrage dans `app_ble.c`, immédiatement après l'init de la stack BLE.

```
BD_ad=AABBCCDDEEFF          ← ligne 0, aligné gauche
BLE Stack=v1.x.x            ← ligne 1, aligné gauche
Branch=x Type=x             ← ligne 2, aligné gauche
FUS v1.x.x                  ← ligne 3, aligné gauche
```

| Champ | Source | Description |
|-------|--------|-------------|
| `BD_ad=` | `BleGetBdAddress()` | Adresse MAC BLE publique (6 octets, MSB first) |
| `BLE Stack=v` | `SHCI_GetWirelessFwInfo()` | Version majeur.mineur.sub du firmware CM0+ |
| `Branch=` | idem | Branche de build et type de release |
| `FUS v` | idem | Version du Firmware Update Service (OTA bootloader CM0+) |

Après 1 seconde (`HAL_Delay(1000)`), l'écran est effacé et remplacé par l'écran principal.

---

### Écran 2 — Écran principal / advertising

Affiché en continu dès la fin de l'écran de boot. C'est l'état par défaut tant qu'aucune notification BLE n'est active.

L'écran est divisé en deux zones :
- **En-tête fixe** (y=0 à y=30) : dessiné une seule fois dans `APP_BLE_Init()`, jamais effacé par la logique distance.
- **Zone dynamique** (y=32 à y=63) : effacée et redessinée toutes les 500 ms par `VL53L0X_PROXIMITY_PrintValue()`.

```
┌─────────────────────────────┐  y=0
│       ** LENA **            │  Font16 (16px), centré  ← y=1
│    -- BLE Sensor --         │  Font12 (12px), centré  ← y=19
├─────────────────────────────┤  y=32  (zone dynamique)
│   Distance: NNN cm          │  Font12  ← y=32, mis à jour /500ms
│   [indicateur de zone]      │  Font12  ← y=47, mis à jour /500ms
└─────────────────────────────┘  y=63
```

**Zones de distance — indicateurs visuels :**

| Plage | Ligne distance (y=32) | Ligne statut (y=47) | Signification |
|-------|-----------------------|---------------------|---------------|
| 0 – 30 cm | `  Distance:  NN cm` | ` !! TRES PROCHE !!` | Objet très proche, zone d'alerte |
| 31 – 199 cm | `  Distance: NNN cm` | `    -- OK :) --   ` | Distance normale, tout va bien |
| ≥ 200 cm | `  Distance > 200cm` | `  ...Trop loin... ` | Hors de portée du capteur |

**Fonctionnement de la mesure de distance :**

Le capteur VL53L0X est un télémètre Time-of-Flight laser (infrarouge 940 nm) capable de mesurer de 0 à 2 m.

- Initialisation (`VL53L0X_PROXIMITY_Init()`) :
  1. Init I2C3 partagée avec l'IMU
  2. Lecture du registre `VL53L0X_REG_IDENTIFICATION_MODEL_ID` → vérifie `0xEEAA` (identifiant constructeur)
  3. `VL53L0X_DataInit()` → calibration interne
  4. `SetupSingleShot()` → configure le mode de mesure unique (single-shot ranging)
  5. Enregistrement de la tâche séquentielle `CFG_TASK_GET_MEASURE_TOF_ID`
  6. Création du timer RTC `PROXIMITY_UPDATE_PERIOD` = 500 ms

- Mesure (`VL53L0X_PROXIMITY_PrintValue()`) :
  ```c
  prox_value = VL53L0X_PROXIMITY_GetDistance();       // retourne mm (uint16_t)
  BSP_LCD_FillRect(0, 0, 32, 128, 32, SSD1315_COLOR_BLACK);  // efface zone dynamique
  if (prox_value < 2000) {
      distance = prox_value / 10;                      // division entière mm → cm
      sprintf(distLine, "  Distance: %3d cm", distance);
      if (distance <= 30)
          strcpy(statusLine, " !! TRES PROCHE !!");    // zone 0-30 cm
      else
          strcpy(statusLine, "    -- OK :) --   ");    // zone 31-199 cm
  } else {
      strcpy(distLine,   "  Distance > 200cm");        // hors portée
      strcpy(statusLine, "  ...Trop loin... ");
  }
  UTIL_LCD_DisplayStringAt(0, 32, distLine, LEFT_MODE);
  UTIL_LCD_DisplayStringAt(0, 47, statusLine, LEFT_MODE);
  BSP_LCD_Refresh(0);
  ```

- La zone dynamique est effacée proprement avec `BSP_LCD_FillRect` (32px de hauteur, largeur totale 128px) avant chaque redessinage, évitant tout artefact.
- La conversion mm → cm est une **division entière par 10** (15 mm → 1 cm, troncature).
- Le timer VL53L0X tourne en permanence (démarré via `VL53L0X_Start_Measure()` dans `APP_BLE_Init()`).

**Interactions avec les autres écrans :** Quand les notifications Motion ou Env sont actives (écrans 3/4), ces modes écrivent sur les lignes Font12 2/3/4 (y=24-59), ce qui recouvre la zone dynamique distance (y=32-59). L'en-tête `** LENA **` et `-- BLE Sensor --` (y=1 à y=30) n'est jamais touché car les modes Motion/Env n'effacent que les lignes 2, 3 et 4.

---

### Écran 3 — Données capteur Motion (BLE actif)

Activé lorsque le client BLE (ex. app ST BLE Sensor) active les notifications sur la caractéristique Motion. Mis à jour à 20 Hz (toutes les 50 ms).

```
      WB BLE Sensor           ← ligne 0, inchangée
                              ← ligne 1, vide
Accelero and Gyro            ← ligne 2
AAAAA|BBBBB|CCCCC            ← ligne 3  — acc X | Y | Z  (mg, entiers, largeur 5)
DDDDD|EEEEE|FFFFF            ← ligne 4  — gyro X | Y | Z (dps, entiers, largeur 5)
```

- **Accéléromètre** : `BSP_MOTION_SENSOR_GetAxes(ISM330DHCX_0, MOTION_ACCELERO)` → `MOTION_SENSOR_Axes_t` (x, y, z en mg, int32)
- **Gyroscope** : `BSP_MOTION_SENSOR_GetAxes(ISM330DHCX_0, MOTION_GYRO)` → valeurs brutes divisées par 100 avant envoi BLE (`angular_velocity / 100`) pour obtenir mdps→dps
- Format OLED : `%5.0f|%5.0f|%5.0f` (3 colonnes de 5 caractères, séparateur `|`)
- À l'activation : les lignes 2-4 sont effacées (`UTIL_LCD_ClearStringLine`)
- À la désactivation : les lignes 2-4 sont effacées

---

### Écran 4 — Données capteur Environnement (BLE actif)

Activé lorsque le client BLE active les notifications sur la caractéristique Env. Mis à jour toutes les 500 ms.

```
      WB BLE Sensor           ← ligne 0, inchangée
                              ← ligne 1, vide
                              ← ligne 2, vide (effacée)
Temp 1 : XX.X C              ← ligne 3
                              ← ligne 4, vide (effacée)
```

- **Température** : `BSP_ENV_SENSOR_GetValue(STTS22H_0, ENV_TEMPERATURE)` → `float` en °C, formaté `%2.1f`
- Envoi BLE : `int16_t` = `intPart * 10 + decPart` (ex. 23.5°C → 235)
- Le capteur STTS22H est déclaré avec 1 capteur température uniquement (`hasTemperature = 1`) ; pression et humidité désactivés (`hasPressure = 0`, `hasHumidity = 0`)

---

### Contrôle LED RGB (service P2P, sans affichage OLED)

Le service P2P Server expose une caractéristique write-without-response permettant au client BLE de contrôler la LED RGB PWM de la carte :

- Write `0x01` → `LED_On(aPwmLedGsData)` (impulsion PWM, puis `LED_Deinit()` pour libérer SPI1/MOSI partagé avec le LCD)
- Write `0x00` → `LED_Off()`
- Bouton SW1 (GPIO_PIN_12, EXTI) → `APP_BLE_Key_Button1_Action()` → notification BLE vers le client
- Commande UART alternative : envoyer `SW1\r` ou `SW2\r` sur USART1 simule l'appui bouton par génération logicielle d'interruption EXTI

---

## Fichiers clés

| Fichier | Rôle |
|---------|------|
| [Core/Src/app_entry.c](mb1292b-controller/Projects/STM32WB5MM-DK/Applications/BLE/BLE_Sensor/Core/Src/app_entry.c) | Init globale : LCD, ISM330DHCX, STTS22H, VL53L0X, boutons, UART |
| [Core/Src/app_vl53l0x.c](mb1292b-controller/Projects/STM32WB5MM-DK/Applications/BLE/BLE_Sensor/Core/Src/app_vl53l0x.c) | Driver VL53L0X + affichage distance OLED |
| [STM32_WPAN/App/app_ble.c](mb1292b-controller/Projects/STM32WB5MM-DK/Applications/BLE/BLE_Sensor/STM32_WPAN/App/app_ble.c) | Init stack BLE, FSM connexion, écran boot + lancement mesure distance |
| [STM32_WPAN/App/motenv_server_app.c](mb1292b-controller/Projects/STM32WB5MM-DK/Applications/BLE/BLE_Sensor/STM32_WPAN/App/motenv_server_app.c) | Orchestrateur MOTENV : timers 50ms/500ms |
| [STM32_WPAN/App/motion_server_app.c](mb1292b-controller/Projects/STM32WB5MM-DK/Applications/BLE/BLE_Sensor/STM32_WPAN/App/motion_server_app.c) | Lecture ISM330DHCX, payload BLE, affichage OLED |
| [STM32_WPAN/App/env_server_app.c](mb1292b-controller/Projects/STM32WB5MM-DK/Applications/BLE/BLE_Sensor/STM32_WPAN/App/env_server_app.c) | Lecture STTS22H, payload BLE, affichage OLED |
| [STM32_WPAN/App/p2p_server_app.c](mb1292b-controller/Projects/STM32WB5MM-DK/Applications/BLE/BLE_Sensor/STM32_WPAN/App/p2p_server_app.c) | Contrôle LED RGB + notification bouton SW1 |
