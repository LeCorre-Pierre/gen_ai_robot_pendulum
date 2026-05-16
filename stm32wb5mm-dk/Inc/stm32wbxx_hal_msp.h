#ifndef PERIPH_INIT_H
#define PERIPH_INIT_H

#include "main.h"
#include "stm32wb5mm_dk_lcd.h"
#include "stm32_lcd.h"

extern TIM_HandleTypeDef   htim1;    /**< Left encoder  — TIM1,  PD14/PD15 */
extern TIM_HandleTypeDef   htim2;    /**< Right encoder — TIM2,  PA15/PB3  */
extern TIM_HandleTypeDef   htim16;   /**< Right motor PWM — TIM16, PE0     */
extern LPTIM_HandleTypeDef hlptim1;  /**< Left motor PWM — LPTIM1, PC1    */
extern I2C_HandleTypeDef   hi2c3;    /**< IMU ISM330DHCX — PB13=SCL, PB11=SDA */

void Periph_TIM1_Init(void);
void Periph_TIM2_Init(void);
void Periph_TIM16_Init(void);
void Periph_LPTIM1_Init(void);
void Periph_I2C3_Init(void);
void Periph_LCD_Init(void);
void Periph_GPIO_Motor_Init(void);
void Periph_Init_All(void);

#endif
