# System View — Board Architecture

**Version:** 1.0  
**Date:** 2026-04-11  

---

## Vue d'ensemble

La `MB1292B` est l'unique carte de calcul et de decision. Elle execute la boucle de controle, lit les capteurs, commande les moteurs, communique en BLE avec le smartphone et en filaire avec le PC.

```text
                +---------------------+
                |     Smartphone      |
                |   Commande en BLE   |
                +----------+----------+
                           | BLE
                           |
                +----------v----------+
                |       MB1292B       |
                |  Carte de controle  |
                |  IMU / OLED / RGB   |
                |  Boutons / QSPI     |
                +----+----------+-----+
                     |          |
          GPIO/PWM   |          | USB ST-Link VCP
                     |          |
              +------v---+   +--v--------+
              |  Motor   |   |    PC     |
              |  Shield  |   |  Tuning   |
              |  L298P   |   | Telemetry |
              +------+---+   +-----------+
                     |
              +------v------+
              |   Moteurs   |
              |+ Encodeurs  |
              +------+------+
                     |
              Encodeurs -> MB1292B (GPIO direct)

  +--------------------+    +--------------------+
  | Batterie puissance |    | Batterie logique   |
  | -> etage moteur    |    | -> MB1292B + shield|
  +---------+----------+    +---------+----------+
            |                         |
            +----------+  +-----------+
                       |  |
                    Masse commune
```

---

## Boards et connexions

### MB1292B — Carte de controle

- Execute la boucle de controle RT
- Lit l'IMU onboard (ISM330DHCX, I2C3)
- Pilote le Motor Shield (PWM, DIR, BRAKE via GPIO)
- Lit les encodeurs directement (QEI hardware via TIM1/TIM2)
- Communique en BLE avec le smartphone
- Communique avec le PC via ST-Link VCP (USART1)
- Fonctions natives conservees : IMU, OLED, RGB LED, B1, B2, QSPI flash

### Arduino Motor Shield Rev3 — Etage de puissance

- Recoit les ordres de la MB1292B (PWM, DIR, BRAKE)
- Pilote les deux moteurs DC via le L298
- Fournit la mesure de courant moteur (CSA/CSB vers ADC STM32)
- Cable manuellement (pas de plug-in avec la MB1292B)

### Moteurs DC + encodeurs

- 2x motorereducteurs 29:1, encodeur 64 CPR (1856 ticks/revolution effectif)
- Moteurs commandes par le Motor Shield
- Encodeurs lus directement par la MB1292B

### Smartphone

- Client BLE de haut niveau
- Envoi des commandes de conduite (avant/arriere/rotation)
- Affichage de la telemetrie de base

### PC d'ingenierie

- Connexion via ST-Link Virtual COM Port (USB, sans materiel intermediaire)
- Programmation, debug SWD, tuning PID, telemetrie detaillee

### Alimentation

- **Batterie puissance** : alimente exclusivement `Vs` du Motor Shield (rail moteurs)
- **Batterie logique** : alimente la MB1292B et `Vss` du Motor Shield
- **Masse commune** : reference electrique partagee entre les deux rails

---

## Connexions inter-cartes

| De | Vers | Nature |
|----|------|--------|
| MB1292B | Motor Shield | PWM, DIR, BRAKE (GPIO/timer) |
| Motor Shield | MB1292B | Mesure courant (analogique) |
| Moteurs | MB1292B | Signaux encodeurs (QEI) |
| Motor Shield | Moteurs | Puissance DC |
| MB1292B | Smartphone | BLE 5.2 |
| MB1292B | PC | USB via ST-Link (VCP + SWD) |
| Batterie puissance | Motor Shield | Alimentation `Vs` |
| Batterie logique | MB1292B | Alimentation carte |
| Batterie logique | Motor Shield | Alimentation `Vss` logique |

---

## Documents lies

- [1-requirements](1-requirements.md)
- [3-boards-interfaces](3-boards-interfaces.md)
- [4-stm32wb5m-pins-allocations](4-stm32wb5m-pins-allocations.txt)
