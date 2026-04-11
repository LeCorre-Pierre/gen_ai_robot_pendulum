# Boards Interfaces — Signals and Naming

**Version:** 1.0  
**Date:** 2026-04-11  

---

## Convention de nommage

| Prefixe | Scope |
|---------|-------|
| `CTRL_*` | Signaux du point de vue de la MB1292B |
| `MOTOR_LEFT_*` | Moteur et encodeur gauche |
| `MOTOR_RIGHT_*` | Moteur et encodeur droit |
| `ENC_LEFT_*` | Encodeur gauche |
| `ENC_RIGHT_*` | Encodeur droit |
| `SHIELD_*` | Interfaces globales du Motor Shield |

---

## MB1292B — Signaux de commande vers le Motor Shield

| Signal | Direction | Description |
|--------|-----------|-------------|
| `CTRL_MOTOR_LEFT_PWM` | MB1292B → Shield | Commande PWM canal gauche |
| `CTRL_MOTOR_LEFT_DIR` | MB1292B → Shield | Direction canal gauche |
| `CTRL_MOTOR_LEFT_BRAKE` | MB1292B → Shield | Frein actif canal gauche |
| `CTRL_MOTOR_RIGHT_PWM` | MB1292B → Shield | Commande PWM canal droit |
| `CTRL_MOTOR_RIGHT_DIR` | MB1292B → Shield | Direction canal droit |
| `CTRL_MOTOR_RIGHT_BRAKE` | MB1292B → Shield | Frein actif canal droit |

## MB1292B — Retours depuis le Motor Shield

| Signal | Direction | Description |
|--------|-----------|-------------|
| `CTRL_MOTOR_LEFT_CURRENT_SENSE` | Shield → MB1292B | Courant moteur gauche (analogique) |
| `CTRL_MOTOR_RIGHT_CURRENT_SENSE` | Shield → MB1292B | Courant moteur droit (analogique) |

## MB1292B — Retours depuis les encodeurs

| Signal | Direction | Description |
|--------|-----------|-------------|
| `CTRL_ENC_LEFT_CHA` | Encodeur gauche → MB1292B | Voie A encodeur gauche |
| `CTRL_ENC_LEFT_CHB` | Encodeur gauche → MB1292B | Voie B encodeur gauche |
| `CTRL_ENC_RIGHT_CHA` | Encodeur droit → MB1292B | Voie A encodeur droit |
| `CTRL_ENC_RIGHT_CHB` | Encodeur droit → MB1292B | Voie B encodeur droit |

## MB1292B — Communication externe

| Signal | Direction | Description |
|--------|-----------|-------------|
| `CTRL_VCP_TX` | MB1292B → PC | Emission ST-Link VCP |
| `CTRL_VCP_RX` | PC → MB1292B | Reception ST-Link VCP |
| `CTRL_BLE_LINK` | Bidirectionnel | Lien BLE avec le smartphone |

---

## Motor Shield — Signaux complets

### Entrees commande

| Signal | Direction | Description |
|--------|-----------|-------------|
| `MOTOR_LEFT_PWM` | MB1292B → Shield | PWM canal gauche |
| `MOTOR_LEFT_DIR` | MB1292B → Shield | Direction canal gauche |
| `MOTOR_LEFT_BRAKE` | MB1292B → Shield | Frein canal gauche |
| `MOTOR_RIGHT_PWM` | MB1292B → Shield | PWM canal droit |
| `MOTOR_RIGHT_DIR` | MB1292B → Shield | Direction canal droit |
| `MOTOR_RIGHT_BRAKE` | MB1292B → Shield | Frein canal droit |

### Sorties mesure courant

| Signal | Direction | Description |
|--------|-----------|-------------|
| `MOTOR_LEFT_CURRENT_SENSE` | Shield → MB1292B | Mesure courant canal gauche |
| `MOTOR_RIGHT_CURRENT_SENSE` | Shield → MB1292B | Mesure courant canal droit |

### Sorties vers moteurs

| Signal | Direction | Description |
|--------|-----------|-------------|
| `MOTOR_LEFT_OUT_POS` | Shield → moteur gauche | Borne + canal gauche |
| `MOTOR_LEFT_OUT_NEG` | Shield → moteur gauche | Borne - canal gauche |
| `MOTOR_RIGHT_OUT_POS` | Shield → moteur droit | Borne + canal droit |
| `MOTOR_RIGHT_OUT_NEG` | Shield → moteur droit | Borne - canal droit |

### Alimentation

| Signal | Description |
|--------|-------------|
| `SHIELD_VS_MOTOR` | Batterie puissance → rail moteurs |
| `SHIELD_VSS_LOGIC` | Batterie logique → logique shield |
| `SHIELD_GND` | Masse commune |

---

## Encodeurs — Signaux

| Signal | Direction | Description |
|--------|-----------|-------------|
| `ENC_LEFT_CHA` | Encodeur gauche → MB1292B | Voie quadrature A |
| `ENC_LEFT_CHB` | Encodeur gauche → MB1292B | Voie quadrature B |
| `ENC_RIGHT_CHA` | Encodeur droit → MB1292B | Voie quadrature A |
| `ENC_RIGHT_CHB` | Encodeur droit → MB1292B | Voie quadrature B |

Le sens du comptage depend du sens mecanique retenu comme positif. La convention doit etre coherente entre encodeur, moteur et firmware.

---

## Correspondance documentation / code

| Documentation | Code |
|---------------|------|
| `CTRL_MOTOR_LEFT_PWM` | `ctrl_motor_left_pwm` |
| `CTRL_MOTOR_LEFT_DIR` | `ctrl_motor_left_dir` |
| `CTRL_MOTOR_LEFT_BRAKE` | `ctrl_motor_left_brake` |
| `CTRL_MOTOR_RIGHT_PWM` | `ctrl_motor_right_pwm` |
| `CTRL_MOTOR_RIGHT_DIR` | `ctrl_motor_right_dir` |
| `CTRL_MOTOR_RIGHT_BRAKE` | `ctrl_motor_right_brake` |
| `CTRL_MOTOR_LEFT_CURRENT_SENSE` | `ctrl_motor_left_current_sense` |
| `CTRL_MOTOR_RIGHT_CURRENT_SENSE` | `ctrl_motor_right_current_sense` |
| `CTRL_ENC_LEFT_CHA` | `ctrl_enc_left_cha` |
| `CTRL_ENC_LEFT_CHB` | `ctrl_enc_left_chb` |
| `CTRL_ENC_RIGHT_CHA` | `ctrl_enc_right_cha` |
| `CTRL_ENC_RIGHT_CHB` | `ctrl_enc_right_chb` |
| `ENC_LEFT_CHA` | `enc_left_cha` |
| `ENC_LEFT_CHB` | `enc_left_chb` |
| `ENC_RIGHT_CHA` | `enc_right_cha` |
| `ENC_RIGHT_CHB` | `enc_right_chb` |
| `MOTOR_LEFT_PWM` | `motor_left_pwm` |
| `MOTOR_LEFT_DIR` | `motor_left_dir` |
| `MOTOR_LEFT_BRAKE` | `motor_left_brake` |
| `MOTOR_LEFT_CURRENT_SENSE` | `motor_left_current_sense` |
| `MOTOR_RIGHT_PWM` | `motor_right_pwm` |
| `MOTOR_RIGHT_DIR` | `motor_right_dir` |
| `MOTOR_RIGHT_BRAKE` | `motor_right_brake` |
| `MOTOR_RIGHT_CURRENT_SENSE` | `motor_right_current_sense` |

---

## Documents lies

- [1-requirements](1-requirements.md)
- [2-system](2-system.md)
- [4-stm32wb5m-pins-allocations](4-stm32wb5m-pins-allocations.txt)
