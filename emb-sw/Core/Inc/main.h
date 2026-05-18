#ifndef MAIN_H
#define MAIN_H

#include "stm32wbxx_hal.h"
#include "stm32wb5mm_dk_lcd.h"
#include "stm32_lcd.h"

/* HAL peripheral handles — defined in main.c */
extern TIM_HandleTypeDef  htim1;   /* Left encoder QEI  — TIM1 */
extern TIM_HandleTypeDef  htim2;   /* Right encoder QEI — TIM2 */
extern TIM_HandleTypeDef  htim16;  /* Right motor PWM   — TIM16_CH1 */
extern LPTIM_HandleTypeDef hlptim1; /* Left motor PWM   — LPTIM1 */
extern I2C_HandleTypeDef  hi2c3;   /* IMU ISM330DHCX    — I2C3 */
extern UART_HandleTypeDef huart1;  /* VCP USART1 */
extern ADC_HandleTypeDef  hadc1;   /* Current sense ADC1 */
extern QSPI_HandleTypeDef hqspi;   /* Flash S25FL128S   — QUADSPI */

void Error_Handler(void);

#endif /* MAIN_H */
