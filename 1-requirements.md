# Requirements - Self-Balancing Inverted Pendulum Robot

**Version:** 1.0  
**Date:** 2026-04-11  

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

## Architecture

```text
┌─────────────────────────────────────────────────┐
│                     ROBOT                        │
│                                                  │
│   ┌──────────────────────┐   USB ST-LINK VCP     │
│   │ STM32WB5MMG          │◄──────────────────► PC │
│   │ (MB1292B)            │                        │
│   │                      │                        │
│   │ • Balance PID        │                        │
│   │ • Moteurs (L298P)    │                        │
│   │ • Encodeurs (QEI)    │                        │
│   │ • ISM330DHCX (I2C3)  │                        │
│   │ • BLE 5.2            │                        │
│   │ • OLED / RGB / BTN   │                        │
│   │ • QSPI flash         │                        │
│   └──────────────────────┘                        │
│              │ BLE 5.2                            │
└──────────────┼────────────────────────────────────┘
               │
          Smartphone App BLE
```

| # | Sous-systeme | Support | Role |
|---|--------------|---------|------|
| 1 | Firmware STM32 | STM32WB5MMG | Controle RT, BLE smartphone, telemetrie filaire |
| 2 | PC d'ingenierie | PC / laptop | Pilotage filaire, tuning, logs |
| 3 | App smartphone | iOS / Android | Conduite via BLE |

---

## 1. System-Level Requirements

| ID | Requirement | Priorite |
|----|-------------|----------|
| SYS-001 | Le robot **doit** maintenir l'equilibre sur deux roues sur surface plane. | CRITICAL |
| SYS-002 | Le robot **doit** etre telecommande (translation, rotation) via BLE smartphone. | CRITICAL |
| SYS-003 | Le robot **doit** permettre le reglage de parametres depuis un PC via ST-Link VCP. | HIGH |
| SYS-004 | Les echanges PC<->robot **doivent** passer exclusivement par le ST-Link VCP. | HIGH |
| SYS-005 | Le STM32WB5MMG **doit** rester le seul maitre de la boucle de controle. | CRITICAL |
| SYS-010 | Le robot **doit** s'equilibrer sur surface dure et plane. | CRITICAL |
| SYS-011 | Le robot **doit** recuperer l'equilibre apres une perturbation < 5 N.s laterale. | MEDIUM |
| SYS-012 | Le robot **devrait** rester operationnel pour une inclinaison < +/-30 deg. | MEDIUM |
| SYS-013 | Le robot **doit** detecter une chute irrecuperable et couper les moteurs. | HIGH |

---

## 2. Hardware Requirements

### 2.1 STM32WB5MMG — MB1292B

**Chip :** STM32WB5MMG — Cortex-M4 @ 64 MHz + Cortex-M0+ @ 32 MHz (BLE 5.2)

| ID | Requirement | Priorite |
|----|-------------|----------|
| HW-001 | 2 signaux PWM independants pour les moteurs (>= 1 kHz). | CRITICAL |
| HW-002 | 2 encodeurs quadrature en mode QEI hardware (TIM encoder mode). | CRITICAL |
| HW-003 | Communication ISM330DHCX via I2C3 (PB13=SCL / PB11=SDA), Fast Mode 400 kHz, adresse `0x6B`. | CRITICAL |
| HW-004 | BLE 5.2 avec l'app smartphone sans impact sur la boucle RT. | CRITICAL |
| HW-005 | Canal UART de service via `USART1` sur ST-Link VCP (`PB6/PB7`). | HIGH |
| HW-006 | Boucle de controle deterministe >= 200 Hz sur le core M4. | CRITICAL |
| HW-007 | ST-Link embarque MB1292B utilise pour SWD, programmation et VCP. | HIGH |

### 2.2 Fonctions natives MB1292B conservees

| ID | Requirement | Priorite |
|----|-------------|----------|
| HW-010 | LED RGB onboard disponible pour indication d'etat. | MEDIUM |
| HW-011 | Bouton `B1` disponible comme entree locale. | MEDIUM |
| HW-012 | Bouton `B2` disponible comme entree locale. | MEDIUM |
| HW-013 | Afficheur OLED disponible pour informations d'etat et debug. | MEDIUM |
| HW-014 | QSPI flash disponible pour stockage non volatile. | LOW |
| HW-015 | Le mapping GPIO doit preserver les pins des fonctions natives. | HIGH |

### 2.3 IMU — ISM330DHCX (onboard MB1292B)

Connecte en interne sur I2C3 (PB13=SCL / PB11=SDA), adresse `0x6B`. Driver BSP : `stm32wb5mm_dk_motion_sensors.c`.

| ID | Requirement | Priorite |
|----|-------------|----------|
| HW-020 | IMU : donnees 3-axes accelerometre et 3-axes gyroscope. | CRITICAL |
| HW-021 | Gyroscope : pleine echelle +/-250 deg/s minimum. | HIGH |
| HW-022 | Accelerometre : pleine echelle +/-2 g minimum. | HIGH |
| HW-023 | IMU echantillonnee >= 200 Hz, synchrone avec la boucle de controle. | HIGH |
| HW-024 | MB1292B montee mecaniquement avec l'axe de tangage de l'ISM330DHCX aligne sur l'axe de rotation. | CRITICAL |

### 2.4 Moteurs, encodeurs et driver

| ID | Requirement | Priorite |
|----|-------------|----------|
| HW-030 | 2 motorereducteurs DC 29:1 avec encodeur 64 CPR. | CRITICAL |
| HW-031 | Driver moteur L298 (Arduino Motor Shield) : controle bidirectionnel independant. | CRITICAL |
| HW-032 | Motor Shield cable manuellement au STM32 (pas de plug-in). | HIGH |
| HW-033 | Signaux PWM, DIR et BRAKE mappes sur GPIO et timers disponibles. | HIGH |
| HW-034 | Mesure courant moteur L298 (CSA/CSB) connectee a un ADC STM32. | LOW |

### 2.5 Alimentation

Deux batteries separees : puissance moteur + logique/controle.

```
Batterie puissance --> L298 Vs (moteurs)
Batterie logique   --> MB1292B + L298 Vss (logique)
GND commun aux deux sous-systemes
```

| ID | Requirement | Priorite |
|----|-------------|----------|
| HW-040 | Batterie separee puissance moteurs / logique. | DECIDED |
| HW-041 | Batterie puissance alimente exclusivement `Vs` du L298. | CRITICAL |
| HW-042 | Batterie logique alimente MB1292B et `Vss` du L298. | CRITICAL |
| HW-043 | Masse commune entre les deux sous-systemes. | CRITICAL |
| HW-044 | Interrupteur general accessible sans demontage. | HIGH |
| HW-045 | Surveillance tension batterie via diviseur resistif sur ADC. | MEDIUM |
| HW-046 | Appel de courant moteur ne provoque pas de reset MB1292B. | HIGH |

---

## 3. Firmware Requirements

### 3.1 Boucle de controle

| ID | Requirement | Priorite |
|----|-------------|----------|
| FW-001 | PID cascade : boucle interne angle (balance) + boucle externe vitesse. | CRITICAL |
| FW-002 | Boucle de controle a periode fixe <= 5 ms (>= 200 Hz). | CRITICAL |
| FW-003 | Filtre complementaire ou Kalman pour fusion accelerometre + gyroscope. | CRITICAL |
| FW-004 | Gains PID et setpoints stockes en memoire non-volatile. | HIGH |
| FW-005 | Anti-windup sur le terme integral du PID. | HIGH |
| FW-006 | Controle de lacet par differentiel de vitesse gauche/droite. | HIGH |

### 3.2 Encodeurs

| ID | Requirement | Priorite |
|----|-------------|----------|
| FW-010 | Decodage des 2 encodeurs quadrature via timers en mode QEI hardware. | HIGH |
| FW-011 | Compteurs de ticks signes sans overflow sur >= 10 minutes. | HIGH |
| FW-012 | Calcul de vitesse de chaque roue a chaque cycle de controle. | HIGH |

### 3.3 Communication BLE — Smartphone

| ID | Requirement | Priorite |
|----|-------------|----------|
| FW-020 | Service GATT BLE : reception des commandes de conduite. | CRITICAL |
| FW-021 | Commandes BLE : Write Without Response pour minimiser la latence. | HIGH |
| FW-022 | Notifications BLE de telemetrie >= 10 Hz vers l'app. | HIGH |
| FW-023 | Perte connexion BLE : arret moteur immediat en <= 200 ms. | CRITICAL |
| FW-024 | Advertising BLE avec nom de device unique et fixe. | MEDIUM |

### 3.4 Communication ST-Link VCP — PC

| ID | Requirement | Priorite |
|----|-------------|----------|
| FW-030 | Protocole de trames binaires SOF/type/payload/CRC16/EOF sur VCP. | HIGH |
| FW-031 | Traitement des trames de mise a jour parametres (gains PID, setpoints, modes). | HIGH |
| FW-032 | Mise a jour parametre appliquee au prochain cycle (<= 5 ms) ou accusee en erreur. | HIGH |
| FW-033 | Telemetrie vers le PC >= 20 Hz : angle, vitesses, sortie PID, etat, securite. | HIGH |
| FW-034 | Traitement VCP n'interrompt pas la boucle RT. | CRITICAL |
| FW-035 | Pilotage manuel filaire et commandes de test via VCP. | MEDIUM |

### 3.5 Securite

| ID | Requirement | Priorite |
|----|-------------|----------|
| FW-040 | Coupure moteurs si angle de tangage > +/-45 deg. | CRITICAL |
| FW-041 | Watchdog hardware : blocage boucle de controle => reset MCU en <= 50 ms. | HIGH |
| FW-042 | Desactivation moteurs apres 3 echantillons I2C manques consecutifs. | HIGH |
| FW-043 | Perte ST-Link VCP ne perturbe pas la boucle RT ni les commandes BLE. | HIGH |

---

## 4. Interface PC

| ID | Requirement | Priorite |
|----|-------------|----------|
| PC-001 | Connexion via ST-Link VCP, sans materiel intermediaire. | HIGH |
| PC-002 | Lecture et ecriture des gains PID des deux boucles. | CRITICAL |
| PC-003 | Reglage setpoints, seuils de securite et modes de test. | HIGH |
| PC-004 | Graphes temps reel : angle, vitesse, sortie PID, courant, batterie. | HIGH |
| PC-005 | Sauvegarde et chargement de presets de parametres. | MEDIUM |
| PC-006 | Export CSV de la telemetrie. | LOW |

---

## 5. Application Smartphone (BLE)

| ID | Requirement | Priorite |
|----|-------------|----------|
| APP-001 | Fonctionne sur Android et iOS. | HIGH |
| APP-002 | Connexion BLE avec affichage du statut. | CRITICAL |
| APP-003 | Interface joystick virtuel (avant/arriere/rotation). | CRITICAL |
| APP-004 | Telemetrie temps reel : angle, etat moteurs, indicateur de chute. | HIGH |
| APP-005 | Indicateur de niveau batterie. | MEDIUM |
| APP-006 | Perte de focus de l'app : commande STOP avant deconnexion. | HIGH |

---

## 6. Performance

| ID | Requirement | Priorite |
|----|-------------|----------|
| PERF-001 | Equilibre stable en < 2 s depuis position de repos verticale. | HIGH |
| PERF-002 | Erreur d'estimation angle < 1 deg RMS en conditions normales. | HIGH |
| PERF-003 | Latence commande BLE (commande -> reponse moteur) < 100 ms. | HIGH |
| PERF-004 | Latence commande VCP (parametre -> application) < 100 ms. | MEDIUM |
| PERF-005 | Telemetrie PC actualisee avec delai < 500 ms. | MEDIUM |

---

## 7. Non-Functional Requirements

| ID | Requirement | Priorite |
|----|-------------|----------|
| NFR-001 | Firmware en C/C++ avec **FreeRTOS**. Taches : `task_control`, `task_ble`, `task_vcp`, `task_safety`. | DECIDED |
| NFR-002 | Structure en modules independants : IMU, encodeurs, moteurs, BLE, controle, VCP. | HIGH |
| NFR-003 | Constantes physiques (rayon roue, rapport reducteur, CPR) : constantes nommees a la compilation. | HIGH |
| NFR-004 | Sections critiques partagees ISR/tache protegees par masquage ou operations atomiques. | CRITICAL |
| NFR-005 | Git avec structure de dossiers : firmware STM32 / outils PC / app smartphone. | MEDIUM |

---

## 8. Open Questions

| # | Question |
|---|----------|
| Q5 | Plateforme app smartphone ? Flutter recommande pour iOS + Android. |
| Q7 | Boucle de position (maintien position fixe) requise, ou uniquement balance + conduite ? |
| Q10 | Informations exactes a afficher sur l'OLED et exposees via LED RGB / boutons ? |
