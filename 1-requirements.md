# Requirements - Self-Balancing Inverted Pendulum Robot

**Version:** 0.4  
**Date:** 2026-04-08  
**Status:** Draft - architecture revue, Ajout des fonction native de la carte conservée de plus:
 - RGB Led
 - User Button B1 and B2
 - OLED display
 - QUAD SPI flash

**Version:** 0.3  
**Date:** 2026-04-06  
**Status:** Draft - architecture revue, Raspberry Pi retire

---

## Glossary

| Term | Definition |
|------|------------|
| MCU | Microcontroller Unit |
| IMU | Inertial Measurement Unit |
| BLE | Bluetooth Low Energy |
| PID | Proportional-Integral-Derivative controller |
| CPR | Counts Per Revolution (encoder) |
| RT | Real-Time |
| QEI | Quadrature Encoder Interface (hardware) |
| VCP | Virtual COM Port |

---

## Architecture materielle retenue

```text
┌──────────────────────────────────────────────────────────────┐
│                           ROBOT                              │
│                                                              │
│   ┌──────────────────────┐          USB ST-LINK VCP          │
│   │ STM32WB5MMG          │◄──────────────────────────────► PC │
│   │ (MB1292B)            │                                  │
│   │                      │                                  │
│   │ • Balance PID        │                                  │
│   │ • Moteurs (L298P)    │                                  │
│   │ • Encodeurs (QEI)    │                                  │
│   │ • ISM330DHCX (I2C3)  │                                  │
│   │ • BLE 5.2            │                                  │
│   │ • Tuning via ST-Link │                                  │
│   └──────────────────────┘                                  │
│              │ BLE 5.2                                       │
└──────────────┼───────────────────────────────────────────────┘
               │
        Smartphone
        App BLE
        (conduite temps reel)
```

### Sous-systemes

| # | Sous-systeme | Support materiel | Role |
|---|--------------|------------------|------|
| 1 | **Firmware STM32** | STM32WB5MMG | Controle RT, BLE smartphone, telemetrie filaire |
| 2 | **PC d'ingenierie** | PC / laptop | Pilotage filaire, tuning, affichage telemetrie, logs |
| 3 | **App smartphone** | iOS / Android | Conduite via BLE |

---

## 1. System-Level Requirements

### 1.1 Mission

| ID | Requirement | Priorite |
|----|-------------|----------|
| SYS-001 | Le robot **doit** maintenir l'equilibre sur deux roues sur surface plane sans intervention humaine. | CRITICAL |
| SYS-002 | Le robot **doit** etre telecommande (translation avant/arriere, rotation) depuis une app smartphone via BLE. | CRITICAL |
| SYS-003 | Le robot **doit** permettre le reglage de ses parametres de controle depuis un PC via le ST-Link Virtual COM Port, sans electronique intermediaire. | HIGH |
| SYS-004 | Les echanges PC<->robot pour pilotage, tuning, diagnostic et telemetrie **doivent** passer exclusivement par le ST-Link VCP. | HIGH |
| SYS-005 | Le STM32WB5MMG **doit** rester le seul maitre de la boucle de controle et de la commande moteurs. | CRITICAL |

### 1.2 Conditions operatoires

| ID | Requirement | Priorite |
|----|-------------|----------|
| SYS-010 | Le robot **doit** s'equilibrer sur surface dure et plane (carrelage, parquet, linoleum). | CRITICAL |
| SYS-011 | Le robot **doit** recuperer l'equilibre apres une perturbation impulsionnelle < 5 N.s appliquee lateralement sur son centre de masse. | MEDIUM |
| SYS-012 | Le robot **devrait** rester operationnel pour une inclinaison < +/-30 deg par rapport a la verticale. | MEDIUM |
| SYS-013 | Le robot **doit** detecter une chute irrecuperable et couper toutes les commandes moteur pour eviter les degats. | HIGH |

---

## 2. Hardware Requirements

### 2.1 STM32WB5MMG - Controle temps reel et BLE

**Carte retenue :** MB1292B (STM32WB5MM-DK Discovery kit)  
**Chip :** STM32WB5MMG - Cortex-M4 @ 64 MHz (application) + Cortex-M0+ @ 32 MHz (radio BLE 5.2)

| ID | Requirement | Priorite |
|----|-------------|----------|
| HW-001 | Le STM32 **doit** generer 2 signaux PWM independants pour le controle vitesse des moteurs (>= 1 kHz). | CRITICAL |
| HW-002 | Le STM32 **doit** decoder 2 encodeurs quadrature en mode QEI hardware (TIM encoder mode). | CRITICAL |
| HW-003 | Le STM32 **doit** communiquer avec l'ISM330DHCX onboard via I2C3 (PB13=SCL / PB11=SDA) en Fast Mode (400 kHz), adresse `0x6B`. | CRITICAL |
| HW-004 | Le STM32 **doit** assurer la communication BLE 5.2 avec l'app smartphone sans impact notable sur la boucle RT du M4. | CRITICAL |
| HW-005 | Le STM32 **doit** exposer un canal UART filaire de service via `USART1` sur le ST-Link VCP (`PB6/PB7`). | HIGH |
| HW-006 | La boucle de controle principale **doit** s'executer de facon deterministe a >= 200 Hz sur le core M4. | CRITICAL |
| HW-007 | Le ST-Link embarque sur le MB1292B **doit** etre utilise pour le debogage SWD, la programmation et la communication filaire avec le PC. | HIGH |

### 2.2 IMU - ISM330DHCX (onboard MB1292B)

**Capteur retenu :** ISM330DHCX - integre sur le MB1292B, connecte en interne sur I2C3 (PB13=SCL / PB11=SDA), adresse `0x6B`. Aucun cablage externe requis. Driver BSP : `stm32wb5mm_dk_motion_sensors.c` (`USE_MOTION_SENSOR_ISM330DHCX_0`).

| ID | Requirement | Priorite |
|----|-------------|----------|
| HW-020 | L'IMU **doit** fournir des donnees 3-axes accelerometre et 3-axes gyroscope. | CRITICAL |
| HW-021 | Le gyroscope **doit** etre configure en pleine echelle +/-250 deg/s minimum (ISM330DHCX : +/-125 a +/-4000 deg/s). | HIGH |
| HW-022 | L'accelerometre **doit** etre configure en pleine echelle +/-2 g minimum (ISM330DHCX : +/-2 a +/-16 g). | HIGH |
| HW-023 | L'IMU **doit** etre echantillonnee a >= 200 Hz, synchrone avec la boucle de controle. | HIGH |
| HW-024 | Le MB1292B **doit** etre monte mecaniquement sur le robot de facon a ce que l'axe de tangage de l'ISM330DHCX soit aligne sur l'axe de rotation. | CRITICAL |

### 2.3 Moteurs, encodeurs et driver

| ID | Requirement | Priorite |
|----|-------------|----------|
| HW-030 | Le robot **doit** utiliser 2 motorereducteurs DC 29:1 avec encodeur 64 CPR. | CRITICAL |
| HW-031 | Le driver moteur (L298 - Arduino Motor Shield) **doit** permettre le controle bidirectionnel independant des 2 moteurs. | CRITICAL |
| HW-032 | Le driver **doit** etre cable manuellement au STM32 (le Motor Shield n'est pas en format plug-in avec le MB1292B). | HIGH |
| HW-033 | Les signaux PWM, DIR et BRAKE du L298 **doivent** etre mappes sur des GPIO et timers disponibles du STM32WB5MMG. | HIGH |
| HW-034 | La mesure de courant moteur du L298 (CSA/CSB) **devrait** etre connectee a un ADC du STM32 pour detection de calage. | LOW |

### 2.4 Alimentation

**Architecture retenue :** deux batteries separees

- **Batterie puissance** dediee a l'etage moteur
- **Batterie logique** dediee a la MB1292B et a la logique du shield

**Chaine de distribution :**

```text
Batterie puissance
 └──→ L298 Vs (alimentation moteurs)

Batterie logique
 ├──→ MB1292B (via 5 V ou VIN conforme a la doc carte)
 └──→ L298 Vss (logique 5 V du driver)

GND batterie puissance ---+
                          +--- masse commune de reference signaux
GND batterie logique  ----+
```

| ID | Requirement | Priorite |
|----|-------------|----------|
| HW-040 | Le robot **doit** utiliser une batterie separee pour la puissance moteurs et une batterie separee pour la logique/controle. | DECIDED |
| HW-041 | La batterie puissance **doit** alimenter exclusivement le rail moteur du L298 (`Vs`). | CRITICAL |
| HW-042 | La batterie logique **doit** alimenter la MB1292B selon un mode d'alimentation conforme a UM2825, ainsi que la logique du L298 (`Vss`). | CRITICAL |
| HW-043 | Les deux sous-systemes d'alimentation **doivent** partager une masse commune de reference pour les signaux de commande et mesure. | CRITICAL |
| HW-044 | Le systeme **doit** disposer d'un interrupteur general accessible sans demontage. | HIGH |
| HW-045 | Le firmware **devrait** surveiller la tension de la batterie logique ou d'une batterie critique via un diviseur resistif sur ADC STM32 et notifier un niveau faible. | MEDIUM |
| HW-046 | L'architecture d'alimentation **doit** eviter qu'un appel de courant moteur provoque un reset de la MB1292B. | HIGH |

---

## 3. Firmware STM32 Requirements

### 3.1 Boucle de controle

| ID | Requirement | Priorite |
|----|-------------|----------|
| FW-001 | Le firmware **doit** implementer un PID cascade : boucle interne angle (balance) + boucle externe vitesse (translation). | CRITICAL |
| FW-002 | La boucle de controle **doit** s'executer a periode fixe et deterministe <= 5 ms (>= 200 Hz). | CRITICAL |
| FW-003 | Le firmware **doit** implementer un filtre complementaire ou de Kalman pour fusionner accelerometre et gyroscope en un angle de tangage stable. | CRITICAL |
| FW-004 | Les gains PID (Kp, Ki, Kd) et les setpoints **doivent** etre stockes en memoire non-volatile et survivre a un cycle d'alimentation. | HIGH |
| FW-005 | Le firmware **doit** implementer un anti-windup sur le terme integral du PID. | HIGH |
| FW-006 | Le firmware **doit** implementer le controle de lacet par differentiel de vitesse gauche/droite. | HIGH |

### 3.2 Encodeurs

| ID | Requirement | Priorite |
|----|-------------|----------|
| FW-010 | Le firmware **doit** decoder les 2 encodeurs quadrature via les timers en mode QEI hardware. | HIGH |
| FW-011 | Le firmware **doit** maintenir des compteurs de ticks signes sans overflow sur >= 10 minutes. | HIGH |
| FW-012 | Le firmware **doit** calculer la vitesse de chaque roue a chaque cycle de controle. | HIGH |

### 3.3 Communication BLE - Canal smartphone

| ID | Requirement | Priorite |
|----|-------------|----------|
| FW-020 | Le firmware **doit** exposer un service GATT BLE pour la reception des commandes de conduite (avant, arriere, rotation gauche/droite, stop). | CRITICAL |
| FW-021 | Les commandes BLE **doivent** utiliser Write Without Response pour minimiser la latence. | HIGH |
| FW-022 | Le firmware **doit** emettre des notifications BLE de telemetrie de base a >= 10 Hz vers l'app smartphone. | HIGH |
| FW-023 | La perte de connexion BLE **doit** declencher un arret moteur immediat dans les 200 ms. | CRITICAL |
| FW-024 | Le firmware **doit** advertiser en BLE avec un nom de device unique et fixe. | MEDIUM |

### 3.4 Communication ST-Link VCP - Canal PC de tuning et telemetrie

| ID | Requirement | Priorite |
|----|-------------|----------|
| FW-030 | Le firmware **doit** implementer un protocole de trames binaires avec SOF, type, payload, CRC16 et EOF sur le ST-Link VCP. | HIGH |
| FW-031 | Le firmware **doit** traiter les trames de mise a jour de parametres recues du PC (gains PID, setpoints, coefficients filtre, modes de test). | HIGH |
| FW-032 | La mise a jour d'un parametre recu via ST-Link VCP **doit** etre appliquee au prochain cycle de controle (<= 5 ms) ou accusee en erreur. | HIGH |
| FW-033 | Le firmware **doit** emettre des trames de telemetrie vers le PC a >= 20 Hz avec angle, vitesses, sortie PID, etat et drapeaux de securite. | HIGH |
| FW-034 | Le traitement VCP **ne doit pas** interrompre ni retarder la boucle de controle RT. | CRITICAL |
| FW-035 | Le firmware **doit** supporter un pilotage manuel filaire et des commandes de test via le meme protocole ST-Link VCP. | MEDIUM |

### 3.5 Securite et gestion des defauts

| ID | Requirement | Priorite |
|----|-------------|----------|
| FW-040 | Le firmware **doit** couper les moteurs si l'angle de tangage depasse +/-45 deg. | CRITICAL |
| FW-041 | Le firmware **doit** implementer un watchdog hardware ; un blocage de la boucle de controle doit declencher un reset MCU en <= 50 ms. | HIGH |
| FW-042 | Le firmware **doit** desactiver les moteurs en cas d'echec de communication I2C avec l'ISM330DHCX apres 3 echantillons consecutifs manques. | HIGH |
| FW-043 | La perte de la liaison ST-Link VCP **ne doit pas** perturber la boucle de controle ni les commandes BLE deja actives. | HIGH |

---

## 4. Interface PC filaire Requirements

| ID | Requirement | Priorite |
|----|-------------|----------|
| PC-001 | L'outil PC **doit** se connecter au robot par le ST-Link Virtual COM Port sans materiel intermediaire. | HIGH |
| PC-002 | L'outil PC **doit** permettre la lecture et l'ecriture des gains PID des deux boucles (balance et vitesse). | CRITICAL |
| PC-003 | L'outil PC **doit** permettre le reglage des setpoints, seuils de securite et modes de test. | HIGH |
| PC-004 | L'outil PC **doit** afficher des graphes temps reel de l'angle de tangage, vitesse roues, sortie PID, courant et batterie. | HIGH |
| PC-005 | L'outil PC **devrait** permettre la sauvegarde et le chargement de presets de parametres. | MEDIUM |
| PC-006 | L'outil PC **devrait** permettre l'export CSV de la telemetrie recue. | LOW |

---

## 5. Application Smartphone (BLE) Requirements

| ID | Requirement | Priorite |
|----|-------------|----------|
| APP-001 | L'app smartphone **doit** fonctionner sur Android et iOS. | HIGH |
| APP-002 | L'app **doit** se connecter au robot via BLE et afficher le statut de connexion. | CRITICAL |
| APP-003 | L'app **doit** fournir une interface joystick virtuel pour les commandes de conduite (avant/arriere/rotation). | CRITICAL |
| APP-004 | L'app **doit** afficher la telemetrie de base en temps reel : angle de tangage, etat moteurs, indicateur de chute. | HIGH |
| APP-005 | L'app **doit** afficher un indicateur de niveau batterie si l'information est exposee par le firmware. | MEDIUM |
| APP-006 | La perte de focus de l'app **doit** envoyer une commande STOP avant deconnexion BLE. | HIGH |

---

## 6. Performance Requirements

| ID | Requirement | Priorite |
|----|-------------|----------|
| PERF-001 | Le robot **doit** atteindre l'equilibre stable en < 2 secondes depuis une position de repos verticale. | HIGH |
| PERF-002 | L'erreur d'estimation de l'angle de tangage **doit** etre < 1 deg RMS en conditions normales. | HIGH |
| PERF-003 | La latence de commande BLE (commande envoyee -> reponse moteur) **doit** etre < 100 ms. | HIGH |
| PERF-004 | La latence de commande filaire ST-Link VCP (parametre envoye -> application dans la boucle) **doit** etre < 100 ms. | MEDIUM |
| PERF-005 | La telemetrie affichee sur l'outil PC **doit** etre actualisee avec un delai < 500 ms par rapport a la mesure reelle. | MEDIUM |

---

## 7. Non-Functional Requirements

| ID | Requirement | Priorite |
|----|-------------|----------|
| NFR-001 | Le firmware STM32 **doit** etre ecrit en C ou C++ avec **FreeRTOS** comme OS temps reel. Taches minimales : `task_control`, `task_ble`, `task_vcp`, `task_safety`. | DECIDED |
| NFR-002 | Le firmware **doit** etre structure en modules independants : driver IMU, driver encodeurs, driver moteurs, stack BLE, boucle de controle, driver ST-Link VCP. | HIGH |
| NFR-003 | Toutes les constantes physiques (rayon roue, rapport reducteur, CPR encodeur) **doivent** etre des constantes nommees a la compilation. | HIGH |
| NFR-004 | Les sections critiques partagees entre ISR et tache principale **doivent** etre protegees par masquage d'interruptions ou operations atomiques. | CRITICAL |
| NFR-005 | Le projet **doit** utiliser git avec une structure de dossiers separant firmware STM32, outils PC et application smartphone. | MEDIUM |

---

## 8. Open Questions / TBD

| # | Question | Statut |
|---|----------|--------|
| Q1 | ~~MCU selectionne~~ | ✅ STM32WB5MMG (MB1292B) |
| Q2 | ~~Canal PC~~ | ✅ ST-Link VCP sur `USART1` (`PB6/PB7`) |
| Q3 | ~~Raspberry Pi dans l'architecture~~ | ✅ Retire de l'architecture |
| Q4 | ~~FreeRTOS vs bare-metal~~ | ✅ FreeRTOS retenu |
| Q5 | Plateforme app smartphone ? (Flutter recommande pour iOS + Android en une codebase) | **OUVERT** |
| Q6 | ~~Architecture alimentation~~ | ✅ Deux batteries : puissance + logique |
| Q7 | Boucle de position (maintien d'une position fixe) requise, ou uniquement balance + conduite ? | **OUVERT** |
| Q8 | ~~Mapping GPIO STM32WB5MMG ↔ L298~~ | ✅ Voir `3-gpio-mapping.md` |
| Q9 | ~~IMU onboard vs MPU6050 externe~~ | ✅ ISM330DHCX onboard (I2C3, PB13/PB11, addr `0x6B`) |
