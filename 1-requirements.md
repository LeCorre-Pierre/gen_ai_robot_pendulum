# Requirements — Self-Balancing Inverted Pendulum Robot

**Version:** 0.2
**Date:** 2026-03-16
**Status:** Draft — hardware sélectionné, architecture arrêtée

---

## Glossary

| Term | Definition |
|------|------------|
| MCU  | Microcontroller Unit |
| IMU  | Inertial Measurement Unit |
| BLE  | Bluetooth Low Energy |
| PID  | Proportional-Integral-Derivative controller |
| CPR  | Counts Per Revolution (encoder) |
| RT   | Real-Time |
| QEI  | Quadrature Encoder Interface (hardware) |
| AP   | Access Point (WiFi) |
| WS   | WebSocket |

---

## Architecture matérielle retenue

```
┌─────────────────────────────────────────────────────────┐
│                        ROBOT                            │
│                                                         │
│  ┌──────────────────────┐  UART  ┌───────────────────┐  │
│  │   STM32WB5MMG        │◄──────►│  Raspberry Pi 3B  │  │
│  │   (MB1292B)          │        │                   │  │
│  │                      │        │  • WiFi AP        │  │
│  │  • Balance PID       │        │  • Web server     │  │
│  │  • Moteurs (L298)    │        │  • UART bridge    │  │
│  │  • Encodeurs (QEI)   │        │  • Logging SD     │  │
│  │  • ISM330DHCX (I²C)  │        │                   │  │
│  │  • BLE 5.2           │        │                   │  │
│  └──────────────────────┘        └───────────────────┘  │
│           │ BLE 5.2                      │ WiFi 802.11n  │
└───────────┼──────────────────────────────┼───────────────┘
            │                              │
     📱 Smartphone                   💻 PC / Laptop
     App BLE                         Navigateur Web
     (conduite temps réel)           (tuning paramètres)
```

### Subsystèmes

| # | Subsystème | Support matériel | Rôle |
|---|-----------|-----------------|------|
| 1 | **Firmware STM32** | STM32WB5MMG | Contrôle RT, BLE smartphone |
| 2 | **Logiciel RPi** | Raspberry Pi 3B | Gateway WiFi↔UART, web server |
| 3 | **App smartphone** | iOS / Android | Conduite via BLE |
| 4 | **Web UI PC** | Navigateur (any OS) | Tuning OTA via WiFi |

---

## 1. System-Level Requirements

### 1.1 Mission
| ID | Requirement | Priorité |
|----|-------------|----------|
| SYS-001 | Le robot **doit** maintenir l'équilibre sur deux roues sur surface plane sans intervention humaine. | CRITICAL |
| SYS-002 | Le robot **doit** être télécommandé (translation avant/arrière, rotation) depuis une app smartphone via BLE. | CRITICAL |
| SYS-003 | Le robot **doit** permettre le réglage de ses paramètres de contrôle depuis un PC via WiFi, sans connexion filaire. | HIGH |
| SYS-004 | Les deux canaux de communication (BLE smartphone et WiFi PC) **doivent** fonctionner simultanément et indépendamment. | HIGH |
| SYS-005 | Le STM32WB5MMG **doit** rester le seul maître de la boucle de contrôle ; le RPi ne commande jamais directement les moteurs. | CRITICAL |

### 1.2 Conditions opératoires
| ID | Requirement | Priorité |
|----|-------------|----------|
| SYS-010 | Le robot **doit** s'équilibrer sur surface dure et plane (carrelage, parquet, linoléum). | CRITICAL |
| SYS-011 | Le robot **doit** récupérer l'équilibre après une perturbation impulsionnelle < 5 N·s appliquée latéralement sur son centre de masse. | MEDIUM |
| SYS-012 | Le robot **devrait** rester opérationnel pour une inclinaison < ±30° par rapport à la verticale. | MEDIUM |
| SYS-013 | Le robot **doit** détecter une chute irrécupérable et couper toutes les commandes moteur pour éviter les dégâts. | HIGH |

---

## 2. Hardware Requirements

### 2.1 STM32WB5MMG — Contrôle temps réel et BLE

**Carte retenue :** MB1292B (STM32WB5MM-DK Discovery kit)
**Chip :** STM32WB5MMG — Cortex-M4 @ 64 MHz (application) + Cortex-M0+ @ 32 MHz (radio BLE 5.2)

| ID | Requirement | Priorité |
|----|-------------|----------|
| HW-001 | Le STM32 **doit** générer 2 signaux PWM indépendants pour le contrôle vitesse des moteurs (≥ 1 kHz). | CRITICAL |
| HW-002 | Le STM32 **doit** décoder 2 encodeurs quadrature en mode QEI hardware (TIM encoder mode). | CRITICAL |
| HW-003 | Le STM32 **doit** communiquer avec l'ISM330DHCX onboard via I2C3 (PB13=SCL / PB11=SDA) en Fast Mode (400 kHz), adresse `0x6B`. | CRITICAL |
| HW-004 | Le STM32 **doit** assurer la communication BLE 5.2 avec l'app smartphone (stack radio sur le core M0+, sans impact sur la boucle RT du M4). | CRITICAL |
| HW-005 | Le STM32 **doit** disposer d'un UART dédié pour la liaison avec le Raspberry Pi 3B. | HIGH |
| HW-006 | La boucle de contrôle principale **doit** s'exécuter de façon déterministe à ≥ 200 Hz sur le core M4. | CRITICAL |
| HW-007 | Le ST-Link V3 embarqué sur le MB1292B **doit** être utilisé pour le débogage SWD et la programmation. | HIGH |

### 2.2 Raspberry Pi 3B — Gateway et supervision

**Carte retenue :** Raspberry Pi 3 Model B V1.2
**OS :** Raspberry Pi OS Lite (headless, pas de bureau)

| ID | Requirement | Priorité |
|----|-------------|----------|
| HW-010 | Le RPi **doit** être configuré en WiFi Access Point pour créer son propre réseau (`robot-pendulum`). | HIGH |
| HW-011 | Le RPi **doit** communiquer avec le STM32 via un port UART physique (GPIO 14/15 — TX/RX). | HIGH |
| HW-012 | La liaison UART RPi↔STM32 **doit** fonctionner à 115200 baud avec un protocole de trames à CRC. | HIGH |
| HW-013 | Le RPi **ne doit pas** participer à la boucle de contrôle RT ; son rôle est exclusivement la connectivité et la supervision. | CRITICAL |
| HW-014 | Le RPi **devrait** logger les données de télémétrie sur la carte µSD avec horodatage. | MEDIUM |

### 2.3 IMU — ISM330DHCX (onboard MB1292B)

**Capteur retenu :** ISM330DHCX — intégré sur le MB1292B, connecté en interne sur I2C3 (PB13=SCL / PB11=SDA), adresse `0x6B`. Aucun câblage externe requis. Driver BSP : `stm32wb5mm_dk_motion_sensors.c` (`USE_MOTION_SENSOR_ISM330DHCX_0`).

| ID | Requirement | Priorité |
|----|-------------|----------|
| HW-020 | L'IMU **doit** fournir des données 3-axes accéléromètre et 3-axes gyroscope. | CRITICAL |
| HW-021 | Le gyroscope **doit** être configuré en pleine échelle ±250 °/s minimum (ISM330DHCX : ±125 à ±4000 °/s). | HIGH |
| HW-022 | L'accéléromètre **doit** être configuré en pleine échelle ±2 g minimum (ISM330DHCX : ±2 à ±16 g). | HIGH |
| HW-023 | L'IMU **doit** être échantillonnée à ≥ 200 Hz, synchrone avec la boucle de contrôle (ISM330DHCX ODR max 6664 Hz). | HIGH |
| HW-024 | Le MB1292B **doit** être monté mécaniquement sur le robot de façon à ce que l'axe de tangage de l'ISM330DHCX soit aligné sur l'axe de rotation. Le remapping d'axes logiciel est accepté si nécessaire. | CRITICAL |

### 2.4 Moteurs, Encodeurs et Driver

| ID | Requirement | Priorité |
|----|-------------|----------|
| HW-030 | Le robot **doit** utiliser 2 motoréducteurs DC 29:1 avec encodeur 64 CPR (1856 ticks/tour effectifs). | CRITICAL |
| HW-031 | Le driver moteur (L298 — Arduino Motor Shield) **doit** permettre le contrôle bidirectionnel indépendant des 2 moteurs. | CRITICAL |
| HW-032 | Le driver **doit** être câblé manuellement au STM32 (le Motor Shield n'est pas en format plug-in avec le MB1292B). | HIGH |
| HW-033 | Les signaux PWM, DIR et ENABLE du L298 **doivent** être mappés sur des GPIO et timers disponibles du STM32WB5MMG. | HIGH |
| HW-034 | La mesure de courant moteur du L298 (pin CSA/CSB) **devrait** être connectée à un ADC du STM32 pour détection de calage. | LOW |

### 2.5 Alimentation

**Batterie retenue :** 12 V — 3800 mAh — Ni-MH (10 cellules × 1,2 V nominal)
Tension nominale : 12 V | Min déchargée : ~10 V | Max chargée : ~14 V | Positionnée en **haut du robot** (centre de masse élevé → pendule plus lent à tomber, plus facile à corriger).

**Chaîne de distribution :**
```
Batterie 12V Ni-MH
 ├─── Direct 12V ──────────────→ L298 Vs (alimentation moteurs)
 ├─── Buck DC/DC 5V / 3A ──────→ Raspberry Pi 3B (5V)
 │                         └──→ L298 Vss (logique 5V du driver)
 └─── Buck DC/DC 3,3V / 500mA → STM32WB5MMG + MPU6050
```

| ID | Requirement | Priorité |
|----|-------------|----------|
| HW-040 | La batterie **doit** être une cellule Ni-MH 12 V / 3800 mAh montée en haut du robot. | DÉCIDÉ |
| HW-041 | Le rail 5 V **doit** être fourni par un convertisseur buck DC/DC (≥ 3 A) pour alimenter le RPi 3B et la logique L298 sans surchauffe. | CRITICAL |
| HW-042 | Le rail 3,3 V **doit** être fourni par un convertisseur buck DC/DC séparé pour alimenter le STM32 et l'IMU. | CRITICAL |
| HW-043 | L'alimentation moteurs (12 V) **doit** être découplée des rails logiques (condensateurs) pour éviter que les pics moteur perturbent le STM32 et le RPi. | HIGH |
| HW-044 | Le système **doit** disposer d'un interrupteur général accessible sans démontage. | HIGH |
| HW-045 | Le firmware **devrait** surveiller la tension batterie via un diviseur résistif sur ADC STM32 et notifier un niveau faible par BLE (< 10 V). | MEDIUM |

---

## 3. Firmware STM32 Requirements

### 3.1 Boucle de contrôle

| ID | Requirement | Priorité |
|----|-------------|----------|
| FW-001 | Le firmware **doit** implémenter un PID cascade : boucle interne angle (balance) + boucle externe vitesse (translation). | CRITICAL |
| FW-002 | La boucle de contrôle **doit** s'exécuter à période fixe et déterministe ≤ 5 ms (≥ 200 Hz). | CRITICAL |
| FW-003 | Le firmware **doit** implémenter un filtre complémentaire ou de Kalman pour fusionner accéléromètre et gyroscope en un angle de tangage stable. | CRITICAL |
| FW-004 | Les gains PID (Kp, Ki, Kd) et les setpoints **doivent** être stockés en mémoire non-volatile (Flash) et survivre à un cycle d'alimentation. | HIGH |
| FW-005 | Le firmware **doit** implémenter un anti-windup sur le terme intégral du PID. | HIGH |
| FW-006 | Le firmware **doit** implémenter le contrôle de lacet par différentiel de vitesse gauche/droite. | HIGH |

### 3.2 Encodeurs

| ID | Requirement | Priorité |
|----|-------------|----------|
| FW-010 | Le firmware **doit** décoder les 2 encodeurs quadrature via les timers en mode QEI hardware. | HIGH |
| FW-011 | Le firmware **doit** maintenir des compteurs de ticks signés sans overflow sur ≥ 10 minutes. | HIGH |
| FW-012 | Le firmware **doit** calculer la vitesse de chaque roue en rad/s à chaque cycle de contrôle. | HIGH |

### 3.3 Communication BLE — Canal smartphone

| ID | Requirement | Priorité |
|----|-------------|----------|
| FW-020 | Le firmware **doit** exposer un service GATT BLE pour la réception des commandes de conduite (avant, arrière, rotation gauche/droite, stop). | CRITICAL |
| FW-021 | Les commandes BLE **doivent** utiliser Write Without Response pour minimiser la latence (pas d'ACK applicatif). | HIGH |
| FW-022 | Le firmware **doit** émettre des notifications BLE de télémétrie (angle, vitesses, sortie PID) à ≥ 10 Hz vers l'app smartphone. | HIGH |
| FW-023 | La perte de connexion BLE **doit** déclencher un arrêt moteur immédiat dans les 200 ms. | CRITICAL |
| FW-024 | Le firmware **doit** advertiser en BLE avec un nom de device unique et fixe. | MEDIUM |

### 3.4 Communication UART — Canal RPi (tuning et supervision)

| ID | Requirement | Priorité |
|----|-------------|----------|
| FW-030 | Le firmware **doit** implémenter un protocole de trames UART binaires avec STX, type, payload, CRC16, ETX. | HIGH |
| FW-031 | Le firmware **doit** traiter les trames de mise à jour de paramètres reçues du RPi (gains PID, setpoints, coefficients filtre). | HIGH |
| FW-032 | La mise à jour d'un paramètre reçu via UART **doit** être appliquée au prochain cycle de contrôle (≤ 5 ms). | HIGH |
| FW-033 | Le firmware **doit** émettre des trames de télémétrie vers le RPi à ≥ 20 Hz (angle, vitesses, PID output, état). | HIGH |
| FW-034 | Le traitement UART **ne doit pas** interrompre ni retarder la boucle de contrôle RT (traitement en tâche de fond ou IRQ basse priorité). | CRITICAL |

### 3.5 Sécurité et gestion des défauts

| ID | Requirement | Priorité |
|----|-------------|----------|
| FW-040 | Le firmware **doit** couper les moteurs si l'angle de tangage dépasse ±45° (chute irrécupérable). | CRITICAL |
| FW-041 | Le firmware **doit** implémenter un watchdog hardware ; un blocage de la boucle de contrôle doit déclencher un reset MCU en ≤ 50 ms. | HIGH |
| FW-042 | Le firmware **doit** désactiver les moteurs en cas d'échec de communication I²C avec l'ISM330DHCX après 3 échantillons consécutifs manqués. | HIGH |
| FW-043 | La perte de la liaison UART avec le RPi **ne doit pas** perturber la boucle de contrôle ni les commandes BLE. | HIGH |

---

## 4. Logiciel Raspberry Pi Requirements

| ID | Requirement | Priorité |
|----|-------------|----------|
| RPI-001 | Le RPi **doit** fonctionner en mode WiFi Access Point avec SSID `robot-pendulum` et mot de passe configurable. | HIGH |
| RPI-002 | Le RPi **doit** exécuter un serveur web exposant l'interface de tuning sur le port 80 (HTTP) ou 443 (HTTPS). | HIGH |
| RPI-003 | Le serveur **doit** exposer un endpoint WebSocket pour la télémétrie temps réel vers le navigateur PC. | HIGH |
| RPI-004 | Le logiciel RPi **doit** implémenter un pont bidirectionnel entre le WebSocket PC et le bus UART STM32. | HIGH |
| RPI-005 | Le RPi **doit** logger la télémétrie reçue du STM32 dans des fichiers CSV horodatés sur la µSD. | MEDIUM |
| RPI-006 | Le RPi **doit** être accessible en SSH depuis le réseau WiFi robot pour le développement et la maintenance. | MEDIUM |
| RPI-007 | Le logiciel RPi **doit** démarrer automatiquement au boot sans intervention (service systemd). | HIGH |

---

## 5. Application Smartphone (BLE) Requirements

| ID | Requirement | Priorité |
|----|-------------|----------|
| APP-001 | L'app smartphone **doit** fonctionner sur Android et iOS. | HIGH |
| APP-002 | L'app **doit** se connecter au robot via BLE et afficher le statut de connexion. | CRITICAL |
| APP-003 | L'app **doit** fournir une interface joystick virtuel pour les commandes de conduite (avant/arrière/rotation). | CRITICAL |
| APP-004 | L'app **doit** afficher la télémétrie de base en temps réel : angle de tangage, état moteurs, indicateur de chute. | HIGH |
| APP-005 | L'app **doit** afficher un indicateur de niveau batterie. | MEDIUM |
| APP-006 | La perte de focus de l'app (mise en arrière-plan) **doit** envoyer une commande STOP avant déconnexion BLE. | HIGH |

---

## 6. Interface Web PC (WiFi) Requirements

| ID | Requirement | Priorité |
|----|-------------|----------|
| WEB-001 | L'interface **doit** être accessible depuis n'importe quel navigateur moderne connecté au réseau WiFi du robot, sans installation. | HIGH |
| WEB-002 | L'interface **doit** permettre la lecture et l'écriture des gains PID (Kp, Ki, Kd) des deux boucles (balance et vitesse). | CRITICAL |
| WEB-003 | L'interface **doit** permettre le réglage des setpoints (angle d'équilibre, vitesse cible). | HIGH |
| WEB-004 | L'interface **doit** afficher des graphes temps réel (fenêtre glissante) de : angle de tangage, vitesse roues, sortie PID. | HIGH |
| WEB-005 | L'interface **devrait** permettre la sauvegarde et le chargement de presets de paramètres (fichiers JSON). | MEDIUM |
| WEB-006 | L'interface **devrait** afficher les logs de télémétrie avec possibilité d'export CSV. | LOW |

---

## 7. Performance Requirements

| ID | Requirement | Priorité |
|----|-------------|----------|
| PERF-001 | Le robot **doit** atteindre l'équilibre stable en < 2 secondes depuis une position de repos verticale. | HIGH |
| PERF-002 | L'erreur d'estimation de l'angle de tangage **doit** être < 1° RMS en conditions normales. | HIGH |
| PERF-003 | La latence de commande BLE (commande envoyée → réponse moteur) **doit** être < 100 ms. | HIGH |
| PERF-004 | La latence de commande WiFi (paramètre envoyé → application dans la boucle) **doit** être < 200 ms. | MEDIUM |
| PERF-005 | La télémétrie affichée sur l'interface web **doit** être actualisée avec un délai < 500 ms par rapport à la mesure réelle. | MEDIUM |

---

## 8. Non-Functional Requirements

| ID | Requirement | Priorité |
|----|-------------|----------|
| NFR-001 | Le firmware STM32 **doit** être écrit en C ou C++ avec **FreeRTOS** comme OS temps réel. Tâches minimales : `task_control` (highest priority, 200 Hz, déclenchée par timer HW), `task_ble` (medium), `task_uart_rpi` (medium), `task_safety` (high). | DÉCIDÉ |
| NFR-002 | Le firmware **doit** être structuré en modules indépendants : driver IMU, driver encodeurs, driver moteurs, stack BLE, boucle de contrôle, driver UART-RPi. | HIGH |
| NFR-003 | Toutes les constantes physiques (rayon roue, rapport réducteur, CPR encodeur) **doivent** être des constantes nommées au moment de la compilation. | HIGH |
| NFR-004 | Les sections critiques partagées entre ISR et tâche principale **doivent** être protégées par masquage d'interruptions ou opérations atomiques. | CRITICAL |
| NFR-005 | Le logiciel RPi **doit** être écrit en Python 3 avec des dépendances minimales (pas de framework lourd). | MEDIUM |
| NFR-006 | Le projet **doit** utiliser git avec une structure de dossiers séparant firmware STM32, logiciel RPi et application smartphone. | MEDIUM |

---

## 9. Open Questions / TBD

| # | Question | Statut |
|---|----------|--------|
| Q1 | ~~MCU sélectionné~~ | ✅ STM32WB5MMG (MB1292B) |
| Q2 | ~~Plateforme app PC~~ | ✅ Web UI dans navigateur, servie par RPi |
| Q3 | ~~Protocole PC~~ | ✅ WiFi AP RPi + WebSocket |
| Q4 | ~~FreeRTOS vs bare-metal~~ | ✅ FreeRTOS retenu |
| Q5 | Plateforme app smartphone ? (Flutter recommandé pour iOS + Android en une codebase) | **OUVERT** |
| Q6 | ~~Batterie~~ | ✅ 12 V / 3800 mAh Ni-MH, montée en haut du robot |
| Q7 | Boucle de position (maintien d'une position fixe) requise, ou uniquement balance + conduite ? | **OUVERT** |
| Q8 | ~~Mapping GPIO STM32WB5MMG ↔ L298~~ | ✅ Voir `3-gpio-mapping.md` |
| Q9 | ~~IMU onboard vs MPU6050 externe~~ | ✅ ISM330DHCX onboard (I2C3, PB13/PB11, addr `0x6B`) — zéro câblage externe, drivers ST BSP |
