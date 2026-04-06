# Pinout projet - MB1292B / STM32WB5MMG

**Version:** 0.2  
**Date:** 2026-04-06  
**Carte:** MB1292B (STM32WB5MM-DK)

Ce fichier centralise les pins STM32 pertinentes pour le projet avec, pour chaque pin, sa fonction native sur la carte, sa fonction dans le projet, et un commentaire utile de cablage ou d'integration.

## Table principale

| Pin STM32 | Fonction native sur la carte | Fonction pour le projet | Commentaire |
|---|---|---|---|
| PA1 | SPI1_SCK vers OLED onboard | Non utilisee | A laisser reservee a l'afficheur OLED |
| PA2 | Libre cote carte | Mesure tension batterie (`ADC1_IN7`) | Accessible via Arduino `A1`, utilisee avec un diviseur resistif |
| PA3 | QSPI flash SCK | Non utilisee | Reservee a la flash onboard |
| PA5 | GPIO / `ADC1_IN10`, exposee Arduino `A2` | Mesure courant moteur A | Lecture courant L298P, usage optionnel |
| PA7 | SPI1_MOSI vers OLED + LED RGB | Non utilisee | Reservee aux peripheriques onboard |
| PA8 | SAI1_CK2 microphone numerique | Non utilisee | A ne pas reutiliser |
| PA9 | SAI1_DI2 microphone numerique | Non utilisee | A ne pas reutiliser |
| PA10 | `I2C1_SDA`, STMod+ `CN5` pin 10, Arduino `D14` | Libre pour extension | Bon candidat pour une future extension I2C |
| PA11 | USB_DM | Non utilisee | Reservee a l'USB |
| PA12 | USB_DP | Non utilisee | Reservee a l'USB |
| PA13 | SWDIO | Debug / programmation | Reservee au debug ST-Link |
| PA14 | SWCLK | Debug / programmation | Reservee au debug ST-Link |
| PA15 | PWM natif sur STMod+ `CN5` pin 14 | Encodeur A phase A (`TIM2_CH1`) | Tres pratique a recuperer via CN5 |
| PB2 | GPIO, Arduino `D7` | Libre pour extension | Peut servir de GPIO ou interruption |
| PB3 | SWO / trace debug | Encodeur A phase B (`TIM2_CH2`) | Point de vigilance: conflit avec SWO en debug |
| PB4 | Pin libre exploitable dans cette config, exposee Arduino `D12` | Encodeur B phase A (`TIM3_CH1`) | Le projet s'appuie dessus pour le QEI |
| PB5 | STMod+ `CN5` multiplexee `LPUART1_TXD` / `INT` | UART STM32 -> Raspberry Pi (`LPUART1_TX`) | A considerer reservee a la liaison RPi dans l'etat actuel |
| PB6 | `USART1_TX` vers ST-Link VCP | UART debug PC | Utilisee pour debug, traces et futur GUI filaire |
| PB7 | `USART1_RX` vers ST-Link VCP | UART debug PC | Reservee au lien PC via ST-Link |
| PB8 | `I2C1_SCL`, STMod+ `CN5` pin 7, Arduino `D15` | Libre pour extension | Avec `PA10`, laisse un bus I2C1 disponible |
| PB9 | QSPI flash IO0 | Non utilisee | Reservee a la flash onboard |
| PB11 | `I2C3_SDA` vers IMU ISM330DHCX onboard | IMU onboard SDA | Utilisee par le projet, aucun cablage externe |
| PB13 | `I2C3_SCL` vers IMU ISM330DHCX onboard | IMU onboard SCL | Utilisee par le projet, adresse IMU `0x6B` |
| PC0 | STMod+ `CN5` multiplexee `LPUART1_RXD` / `SPI2_MISO`, Arduino `D0` | UART Raspberry Pi -> STM32 (`LPUART1_RX`) | Entree RX du lien serie avec le Raspberry Pi |
| PC3 | GPIO / `ADC1_IN4`, exposee Arduino `A0` | Mesure courant moteur B | Lecture courant L298P, usage optionnel |
| PC6 | Touch sensing | Non utilisee | Pas retenue dans le projet |
| PC7 | Pin libre exploitable dans cette config | Encodeur B phase B (`TIM3_CH2`) | Utilisee pour le deuxieme canal QEI |
| PC8 | Reset OLED | Non utilisee | Reservee a l'afficheur onboard |
| PC9 | D/C OLED | Non utilisee | Reservee a l'afficheur onboard |
| PC12 | Bouton utilisateur B1 | Non utilisee | Reservee a l'interface carte |
| PC13 | Bouton utilisateur B2 | Non utilisee | Eviter de la reaffecter sans besoin clair |
| PD3 | QSPI flash NCS | Non utilisee | Reservee a la flash onboard |
| PD12 | GPIO exposee Arduino `D2` | Direction moteur A | Sortie logique vers L298P |
| PD13 | GPIO exposee Arduino `D8` | Frein moteur A | Frein actif L298P |
| PD14 | Arduino `D3`, `TIM1_CH1` | PWM moteur A | Sortie PWM principale du moteur A |
| PD15 | Arduino `D9`, `TIM1_CH2` | PWM moteur B | Sortie PWM principale du moteur B |
| PE0 | GPIO exposee Arduino `D6` | Frein moteur B | Frein actif L298P |
| PE3 | STMod+ `CN5` pin 11 `INT` | Non utilisee | Disponible si une carte fille STMod+ en a besoin |
| PE4 | GPIO exposee Arduino `D4` | Direction moteur B | Sortie logique vers L298P |
| PH0 | SPI1_NSS vers OLED | Non utilisee | Non accessible / a ne pas prevoir au cablage |

## Synthese des pins vraiment actives dans le projet

| Pin STM32 | Fonction native sur la carte | Fonction pour le projet | Commentaire |
|---|---|---|---|
| PA2 | Libre cote carte | Mesure tension batterie | `ADC1_IN7`, Arduino `A1` |
| PA5 | `ADC1_IN10`, Arduino `A2` | Mesure courant moteur A | Optionnel |
| PA15 | STMod+ `CN5` pin 14 | Encodeur A phase A | `TIM2_CH1` |
| PB3 | SWO | Encodeur A phase B | `TIM2_CH2`, conflit debug possible |
| PB4 | Arduino `D12` | Encodeur B phase A | `TIM3_CH1` |
| PB5 | `LPUART1_TXD` / `INT` | UART STM32 -> Raspberry Pi | Arduino `D1` |
| PB6 | ST-Link VCP TX | UART debug PC | `USART1_TX` |
| PB7 | ST-Link VCP RX | UART debug PC | `USART1_RX` |
| PB11 | IMU onboard SDA | IMU ISM330DHCX SDA | `I2C3_SDA` |
| PB13 | IMU onboard SCL | IMU ISM330DHCX SCL | `I2C3_SCL` |
| PC0 | `LPUART1_RXD` / `SPI2_MISO` | UART Raspberry Pi -> STM32 | Arduino `D0` |
| PC3 | `ADC1_IN4`, Arduino `A0` | Mesure courant moteur B | Optionnel |
| PC7 | Libre dans cette config | Encodeur B phase B | `TIM3_CH2` |
| PD12 | Arduino `D2` | Direction moteur A | GPIO sortie |
| PD13 | Arduino `D8` | Frein moteur A | GPIO sortie |
| PD14 | Arduino `D3` | PWM moteur A | `TIM1_CH1` |
| PD15 | Arduino `D9` | PWM moteur B | `TIM1_CH2` |
| PE0 | Arduino `D6` | Frein moteur B | GPIO sortie |
| PE4 | Arduino `D4` | Direction moteur B | GPIO sortie |

## Pins libres interessantes

| Pin STM32 | Fonction native sur la carte | Fonction pour le projet | Commentaire |
|---|---|---|---|
| PA10 | `I2C1_SDA`, STMod+ `CN5` pin 10 | Libre | A associer a `PB8` pour une extension I2C |
| PB2 | GPIO, Arduino `D7` | Libre | Bon choix pour interruption ou entree/sortie simple |
| PB8 | `I2C1_SCL`, STMod+ `CN5` pin 7 | Libre | Complete le bus I2C1 sur CN5 |
| PE3 | STMod+ `CN5` pin 11 `INT` | Libre | Utile pour une carte fille STMod+ |

## Points d'attention

- `PB3` ne doit pas etre utilise a la fois pour le trace `SWO` et pour l'encodeur A phase B.
- `PB5` est documentee comme ligne possible d'interruption capteur, mais dans le projet elle est affectee a `LPUART1_TX` vers le Raspberry Pi.
- `PB11` et `PB13` sont deja prises par l'IMU onboard, donc a ne pas reaffecter.
- `PA15`, `PB8`, `PA10` et `PE3` sont particulierement interessantes si tu veux sortir des signaux par le connecteur `CN5` STMod+.

## Sources internes du depot

- `3-gpio-mapping.md`
- `4-stlink-vcp-interface.md`
- `mb1292b-controller/Utilities/MotorControl/motor_control.h`
- `parts/mb1292b.md`
