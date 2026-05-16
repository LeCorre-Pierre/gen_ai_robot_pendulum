#ifndef PIN_MAPPING_H
#define PIN_MAPPING_H

#include "stm32wbxx_hal.h"

/* Left encoder — TIM1 QEI */
#define ENC_L_PORT      GPIOD
#define ENC_L_CHA_PIN   GPIO_PIN_14   /* PD14 — TIM1_CH1 */
#define ENC_L_CHB_PIN   GPIO_PIN_15   /* PD15 — TIM1_CH2 */

/* Right encoder — TIM2 QEI */
#define ENC_R_CHA_PORT  GPIOA
#define ENC_R_CHA_PIN   GPIO_PIN_15   /* PA15 — TIM2_CH1 */
#define ENC_R_CHB_PORT  GPIOB
#define ENC_R_CHB_PIN   GPIO_PIN_3    /* PB3  — TIM2_CH2 (SWO disabled) */

/* Left motor */
#define MOT_L_PWM_PORT  GPIOC
#define MOT_L_PWM_PIN   GPIO_PIN_1    /* PC1  — LPTIM1_OUT 20 kHz */
#define MOT_L_DIR_PORT  GPIOD
#define MOT_L_DIR_PIN   GPIO_PIN_12   /* PD12 — GPIO out */
#define MOT_L_BRK_PORT  GPIOD
#define MOT_L_BRK_PIN   GPIO_PIN_13   /* PD13 — GPIO out */

/* Right motor */
#define MOT_R_PWM_PORT  GPIOE
#define MOT_R_PWM_PIN   GPIO_PIN_0    /* PE0  — TIM16_CH1 20 kHz */
#define MOT_R_DIR_PORT  GPIOE
#define MOT_R_DIR_PIN   GPIO_PIN_3    /* PE3  — GPIO out */
#define MOT_R_BRK_PORT  GPIOB
#define MOT_R_BRK_PIN   GPIO_PIN_2    /* PB2  — GPIO out */

/* VCP — onboard ST-Link */
#define VCP_PORT        GPIOB
#define VCP_TX_PIN      GPIO_PIN_6    /* PB6  — USART1_TX */
#define VCP_RX_PIN      GPIO_PIN_7    /* PB7  — USART1_RX */

/* IMU ISM330DHCX — I2C3 internal */
#define IMU_SCL_PORT    GPIOB
#define IMU_SCL_PIN     GPIO_PIN_13   /* PB13 — I2C3_SCL */
#define IMU_SDA_PORT    GPIOB
#define IMU_SDA_PIN     GPIO_PIN_11   /* PB11 — I2C3_SDA */
#define IMU_I2C_ADDR    (0x6Bu << 1)  /* 7-bit shifted for HAL */

#endif /* PIN_MAPPING_H */
