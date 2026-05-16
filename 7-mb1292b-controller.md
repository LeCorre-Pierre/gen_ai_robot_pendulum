# emb-sw — Firmware STM32CubeIDE

Projet STM32CubeIDE pour le robot balancier sur MB1292B (STM32WB5MMG).
Remplace `mb1292b-controller` (structure ST pack trop profonde) et `stm32wb5mm-dk` (trop plat).

---

## Principes de conception

**Pas de génération CubeMX.** Tous les fichiers sont écrits ou copiés manuellement.
Le `.ioc` n'est pas utilisé ; les périphériques sont initialisés directement dans le code.

| Règle | Raison |
|---|---|
| `Core/` = glue HAL + RTOS, écrit manuellement | Pas de regénération surprise qui écrase le code |
| `App/` = tâches FreeRTOS uniquement | Orchestration seule — pas d'algo, pas de HAL direct |
| BSP `STM32WB5MM-DK/` réutilisé tel quel | Aucune surprise : bus, LCD, IMU déjà validés sur la carte |
| Bibliothèques robot dans `Utilities/` dédié | Séparation claire algo / BSP / tâches |
| `config.h` = seule source des constantes | Pas de magic numbers dispersés |
| `pin_mapping.h` = seule source des pins | Cohérence avec le tableau d'allocation |

---

## Arborescence du projet

```
emb-sw/                                       ← racine du projet CubeIDE (= workspace folder)
│
├── STM32WB5MMGHX_FLASH.ld                   ← linker script (copié depuis mb1292b-controller)
├── .project                                  ← Eclipse project file
├── .cproject                                 ← CDT project file
├── .settings/                                ← préférences IDE Eclipse
│
├── Core/                                     ← [GLUE HAL + RTOS — écrit manuellement]
│   ├── Inc/
│   │   ├── main.h                            ← extern des handles HAL (htim1, hi2c3, husart1…)
│   │   ├── stm32wb5mm_dk_conf.h              ← config BSP (adapté depuis _conf_template.h)
│   │   ├── stm32wbxx_hal_conf.h              ← modules HAL activés
│   │   ├── stm32wbxx_it.h
│   │   └── FreeRTOSConfig.h                  ← heap 8 kB, tick 1 ms, priorités max
│   └── Src/
│       ├── main.c                            ← HAL_Init, SystemClock_Config, init périph, création tâches
│       ├── stm32wbxx_hal_msp.c               ← MSP callbacks : GPIO clocks, DMA, alternate functions
│       ├── stm32wbxx_it.c                    ← IRQ handlers (SysTick, USART1, TIM1/TIM2…)
│       ├── system_stm32wbxx.c                ← SystemCoreClock, vecteurs système
│       ├── syscalls.c                        ← stubs newlib-nano (_write → USART, _read, _close…)
│       └── sysmem.c                          ← _sbrk (heap, utilise _end/_estack du linker)
│
├── App/                                      ← [TÂCHES FREERTOS — orchestration uniquement]
│   ├── Inc/
│   │   ├── config.h                          ← constantes compile-time (fréquences, seuils, filtres…)
│   │   ├── pin_mapping.h                     ← TOUS les defines GPIO/périphérique (source unique)
│   │   └── robot_types.h                     ← types partagés entre tâches (RobotState_t, MotorCmd_t…)
│   └── Src/
│       └── tasks/
│           ├── task_control.c/.h             ← boucle d'équilibre @200 Hz (IMU → PID → moteurs)
│           ├── task_comms.c/.h               ← télémétrie USART + réception paramètres PC
│           └── task_safety.c/.h              ← watchdog, coupure tilt, timeout BLE
│
├── Drivers/
│   ├── BSP/
│   │   ├── Components/                       ← drivers composants ST (non modifiés)
│   │   │   ├── Common/                       ← interfaces génériques (motion_sensor.h, lcd.h…)
│   │   │   ├── ism330dhcx/                   ← IMU 6 axes (accel + gyro)
│   │   │   │   ├── ism330dhcx.c/.h
│   │   │   │   └── ism330dhcx_reg.c/.h
│   │   │   ├── ssd1315/                      ← contrôleur OLED 128×64
│   │   │   │   ├── ssd1315.c/.h
│   │   │   │   └── ssd1315_reg.c/.h
│   │   │   ├── s25fl128s/                    ← flash QSPI 128 Mbit
│   │   │   │   └── s25fl128s.c/.h
│   │   │   └── vl53l0x/                      ← capteur ToF distance (depuis Core/Src/vl53l0x/)
│   │   │       ├── vl53l0x_api.c/.h
│   │   │       ├── vl53l0x_api_calibration.c/.h
│   │   │       ├── vl53l0x_api_core.c/.h
│   │   │       └── vl53l0x_platform.c/.h
│   │   └── STM32WB5MM-DK/                    ← BSP carte officiel ST (utilisé tel quel, non modifié, le répertoire entier est copié depuis mb1292b-controller)
│   │       ├── stm32wb5mm_dk.c/.h            ← init carte, LED, bouton
│   │       ├── stm32wb5mm_dk_bus.c/.h        ← init I2C1/I2C3/SPI, fonctions R/W pour composants
│   │       ├── stm32wb5mm_dk_lcd.c/.h        ← driver LCD OLED (via ssd1315)
│   │       ├── stm32wb5mm_dk_motion_sensors.c/.h     ← API IMU (via ism330dhcx)
│   │       ├── stm32wb5mm_dk_motion_sensors_ex.c/.h  ← extensions IMU (FIFO, tap…)
│   │       ├── stm32wb5mm_dk_env_sensors.c/.h        ← capteur température (stts22h)
│   │       ├── stm32wb5mm_dk_qspi.c/.h       ← flash QSPI (via s25fl128s)
│   │       └── stm32wb5mm_dk_errno.h          ← codes d'erreur BSP
│   │
│   └── STM32WBxx_HAL_Driver/                 ← ST HAL (non modifié, copié depuis mb1292b-controller)
│       ├── Inc/
│       └── Src/
│
├── Utilities/
│   │
│   │                    ── [ST — réutilisés tels quels depuis mb1292b-controller] ──
│   ├── CPU/                                  ← cpu_utils.c/.h (monitoring stack, CPU load)
│   ├── Fonts/                                ← font8/12/16/20/24.c, fonts.h (pour LCD OLED)
│   ├── Fusion/                               ← AHRS Fusion (algo orientation 3D, alternative au filtre complémentaire)
│   │   └── Fusion/
│   │       ├── FusionAhrs.c/.h
│   │       ├── FusionBias.c/.h
│   │       └── ...
│   ├── LCD/                                  ← stm32_lcd.c/.h (abstraction texte/formes sur OLED)
│   └── lpm/tiny_lpm/                         ← stm32_lpm.c/.h (low power manager — si basse conso souhaitée)
│   │
│   │                    ── [ROBOT — nouvelles bibliothèques créées pour le projet] ──
│   ├── Control/                              ← algorithmes de contrôle (sans HAL, testables sur PC)
│   │   ├── pid_controller.c/.h              ← PID générique avec anti-windup et clamp (depuis mb1292b-controller)
│   │   └── cascade_balance_controller.c/.h  ← cascade PID : vitesse roue → angle → commande moteur
│   ├── MotorControl/                         ← driver moteurs (PWM + DIR + BRAKE)
│   │   └── motor_control.c/.h               ← set_speed(-1.0…+1.0), brake, enable (depuis mb1292b-controller)
│   ├── Encoder/                              ← lecture codeurs incrémentaux
│   │   └── encoder.c/.h                     ← QEI TIM1/TIM2, ticks → vitesse rad/s (NOUVEAU)
│   ├── AngleEstimator/                       ← estimation de l'angle de tangage
│   │   └── angle_estimator.c/.h             ← filtre complémentaire accél + gyro → pitch ° (NOUVEAU)
│   └── Protocol/                             ← communication PC
│       └── vcp_protocol.c/.h                ← framing VCP : SOF/EOF, CRC16-CCITT, Packet (NOUVEAU)
│
├── Middlewares/
│   └── Third_Party/
│       └── FreeRTOS/                         ← FreeRTOS kernel (copié depuis mb1292b-controller)
│
├── Startup/
│   └── startup_stm32wb5mmghx.s               ← vecteur d'interruptions, reset handler
│
└── Debug/                                    ← artefacts build (.gitignore)
    ├── emb-sw.elf
    ├── emb-sw.map
    └── ...
```

---

## Responsabilité de chaque fichier clé

### `App/Inc/config.h`
Toutes les constantes de tuning rassemblées ici. Exemple de contenu :

```c
#define CONTROL_LOOP_HZ         200u
#define CONTROL_LOOP_MS         (1000u / CONTROL_LOOP_HZ)

#define SAFETY_TILT_MAX_DEG     45.0f
#define SAFETY_BLE_TIMEOUT_MS   200u
#define SAFETY_WATCHDOG_MS      50u

#define ENCODER_TICKS_PER_REV   1856u   /* 29:1 × 64 CPR */
#define MOTOR_PWM_FREQ_HZ       20000u

#define COMPL_FILTER_ALPHA      0.98f   /* poids gyro dans le filtre complémentaire */
```

### `App/Inc/pin_mapping.h`
Source unique des pins. Cohérent avec `4-stm32wb5m-pins-allocations.txt` :

```c
/* Encodeur gauche — TIM1 QEI */
#define ENC_L_CHA_PIN   GPIO_PIN_14     /* PD14 — TIM1_CH1 */
#define ENC_L_CHB_PIN   GPIO_PIN_15     /* PD15 — TIM1_CH2 */

/* Encodeur droit — TIM2 QEI */
#define ENC_R_CHA_PIN   GPIO_PIN_15     /* PA15 — TIM2_CH1 */
#define ENC_R_CHB_PIN   GPIO_PIN_3      /* PB3  — TIM2_CH2 (SWO désactivé) */

/* Moteur gauche */
#define MOT_L_PWM_PIN   GPIO_PIN_1      /* PC1  — LPTIM1_OUT  20 kHz */
#define MOT_L_DIR_PIN   GPIO_PIN_12     /* PD12 — GPIO out */
#define MOT_L_BRK_PIN   GPIO_PIN_13     /* PD13 — GPIO out */

/* Moteur droit */
#define MOT_R_PWM_PIN   GPIO_PIN_0      /* PE0  — TIM16_CH1   20 kHz */
#define MOT_R_DIR_PIN   GPIO_PIN_3      /* PE3  — GPIO out */
#define MOT_R_BRK_PIN   GPIO_PIN_2      /* PB2  — GPIO out */

/* VCP — ST-Link intégré */
#define VCP_TX_PIN      GPIO_PIN_6      /* PB6  — USART1_TX */
#define VCP_RX_PIN      GPIO_PIN_7      /* PB7  — USART1_RX */

/* IMU ISM330DHCX — I2C3 interne */
#define IMU_SCL_PIN     GPIO_PIN_13     /* PB13 — I2C3_SCL */
#define IMU_SDA_PIN     GPIO_PIN_11     /* PB11 — I2C3_SDA */
#define IMU_I2C_ADDR    0x6Bu
```

### `App/Inc/robot_types.h`
Types partagés entre les tâches (passés via files de messages FreeRTOS) :

```c
typedef enum { ROBOT_IDLE, ROBOT_BALANCING, ROBOT_FALLEN, ROBOT_ERROR } RobotState_t;

typedef struct {
    float pitch_deg;
    float pitch_rate_dps;
} ImuSample_t;

typedef struct {
    float left;   /* −1.0 … +1.0 */
    float right;
} MotorCmd_t;
```

---

## Tâches FreeRTOS

| Tâche | Priorité | Période | Rôle |
|---|---|---|---|
| `task_control` | High (4) | 5 ms (200 Hz) | Lit IMU → filtre angle → PID cascade → commande moteurs |
| `task_comms` | Normal (2) | event-driven | Envoie télémétrie USART, reçoit params PC |
| `task_safety` | Highest (5) | 10 ms | Vérifie tilt, watchdog, timeout BLE → coupe moteurs |
| Idle | 0 | — | FreeRTOS idle hook (basse conso) |

---

## Règles de build CubeIDE

- **Ne jamais éditer** : `Debug/makefile`, `Debug/objects.list`, `Debug/*.d`, `Debug/*/subdir.mk` — regénérés à chaque build.
- **Modifier directement** : `.project`, `.cproject` pour les propriétés du projet.
- Specs : `--specs=nano.specs --specs=nosys.specs` → `syscalls.c` + `sysmem.c` obligatoires.
- Optimisation Debug : `-Og -g3` ; Release : `-O2`.

---

## Commandes build

```bash
# depuis Git Bash (alias définis dans .bashrc)
mbuild      # make -j16 all   (depuis Debug/)
mclean      # make -j16 clean
mrebuild    # clean + build
```

---

## Migration depuis mb1292b-controller

Ce que l'on **migre** :

| Source (mb1292b-controller) | Destination (emb-sw) | Note |
|---|---|---|
| `Drivers/BSP/STM32WB5MM-DK/` | `Drivers/BSP/STM32WB5MM-DK/` | Tel quel, non modifié |
| `Drivers/BSP/Components/Common/` | `Drivers/BSP/Components/Common/` | Tel quel |
| `Drivers/BSP/Components/ism330dhcx/` | `Drivers/BSP/Components/ism330dhcx/` | Tel quel |
| `Drivers/BSP/Components/ssd1315/` | `Drivers/BSP/Components/ssd1315/` | Tel quel |
| `Drivers/BSP/Components/s25fl128s/` | `Drivers/BSP/Components/s25fl128s/` | Tel quel |
| `Core/Src/vl53l0x/` | `Drivers/BSP/Components/vl53l0x/` | Déplacé dans Components |
| `Drivers/STM32WBxx_HAL_Driver/` | `Drivers/STM32WBxx_HAL_Driver/` | Tel quel |
| `Middlewares/Third_Party/FreeRTOS/` | `Middlewares/Third_Party/FreeRTOS/` | Tel quel |
| `Utilities/CPU/` | `Utilities/CPU/` | Tel quel |
| `Utilities/Fonts/` | `Utilities/Fonts/` | Tel quel |
| `Utilities/Fusion/` | `Utilities/Fusion/` | Tel quel |
| `Utilities/LCD/` | `Utilities/LCD/` | Tel quel |
| `Utilities/lpm/tiny_lpm/` | `Utilities/lpm/tiny_lpm/` | Tel quel |
| `Utilities/Control/pid_controller.c/.h` | `Utilities/Control/pid_controller.c/.h` | Conservé tel quel |
| `Utilities/Control/cascade_balance_controller.c/.h` | `Utilities/Control/cascade_balance_controller.c/.h` | Conservé tel quel |
| `Utilities/MotorControl/motor_control.c/.h` | `Utilities/MotorControl/motor_control.c/.h` | Conservé tel quel |
| `Core/Src/stm32wbxx_hal_msp.c` | `Core/Src/stm32wbxx_hal_msp.c` | Reprendre les handles périph |
| `Core/Src/stm32wbxx_it.c` | `Core/Src/stm32wbxx_it.c` | Nettoyer IRQ inutiles (BLE…) |
| `STM32WB5MMGHX_FLASH.ld` | `STM32WB5MMGHX_FLASH.ld` | Tel quel |
| `Startup/startup_stm32wb5mmghx.s` | `Startup/startup_stm32wb5mmghx.s` | Tel quel |

Ce que l'on **ne migre pas** :

| Élément | Raison |
|---|---|
| BLE stack `Middlewares/ST/STM32_WPAN/` | Hors scope v1 — ajout futur si besoin |
| `Utilities/sequencer/stm32_seq` | Remplacé par FreeRTOS tasks |
| `Utilities/Log/lcd_log` | Non nécessaire pour le robot |
| `Drivers/BSP/Components/stm32wb_at/` | Module AT BLE — hors scope |
| `Drivers/BSP/Components/stts22h/` | Capteur température — non utilisé |
| Arborescence `Projects/STM32WB5MM-DK/Applications/BLE/` | Supprimée — structure pack trop profonde |

---

## Création du projet dans CubeIDE (pas à pas)

**Pas de génération CubeMX.** Tout est fait manuellement à partir de mb1292b-controller.

1. **File → New → STM32 Project** — MCU : `STM32WB5MMG`, nom : `emb-sw`. Décocher la génération de code CubeMX si proposée.
2. **Copier les répertoires** depuis `mb1292b-controller` vers `emb-sw/` selon la table de migration ci-dessus.
3. **Créer manuellement** : `App/Inc/`, `App/Src/tasks/`, `Utilities/Encoder/`, `Utilities/AngleEstimator/`, `Utilities/Protocol/`.
4. **Adapter** `Core/Inc/stm32wb5mm_dk_conf.h` depuis `stm32wb5mm_dk_conf_template.h` (activer seulement LCD, IMU, QSPI).
5. **Ajouter tous les chemins d'include** dans Project Properties → C/C++ Build → Settings → MCU GCC Compiler → Include paths :
   ```
   ../Core/Inc
   ../App/Inc
   ../Drivers/STM32WBxx_HAL_Driver/Inc
   ../Drivers/BSP/STM32WB5MM-DK
   ../Drivers/BSP/Components/Common
   ../Drivers/BSP/Components/ism330dhcx
   ../Drivers/BSP/Components/ssd1315
   ../Drivers/BSP/Components/s25fl128s
   ../Drivers/BSP/Components/vl53l0x
   ../Utilities/CPU
   ../Utilities/Fonts
   ../Utilities/Fusion/Fusion
   ../Utilities/LCD
   ../Utilities/lpm/tiny_lpm
   ../Utilities/Control
   ../Utilities/MotorControl
   ../Utilities/Encoder
   ../Utilities/AngleEstimator
   ../Utilities/Protocol
   ../Middlewares/Third_Party/FreeRTOS/Source/include
   ../Middlewares/Third_Party/FreeRTOS/Source/CMSIS_RTOS_V2
   ../Middlewares/Third_Party/FreeRTOS/Source/portable/GCC/ARM_CM4F
   ```
6. **Ajouter les sources** dans `.cproject` pour tous les `.c` des nouveaux dossiers.
7. **Linker** : option `-T ../STM32WB5MMGHX_FLASH.ld`.
8. **Désactiver SWO** dans Run → Debug Configurations → Debugger car PB3 = TIM2_CH2.
