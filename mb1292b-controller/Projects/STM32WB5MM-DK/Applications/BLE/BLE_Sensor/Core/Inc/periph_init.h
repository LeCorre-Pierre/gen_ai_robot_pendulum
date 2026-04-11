/**
 * @file    periph_init.h
 * @brief   Peripheral initialisation declarations for the MB1292B robot controller.
 *
 * Covers all robot-specific peripherals:
 *   - TIM1  : left-wheel quadrature encoder (QEI)
 *   - TIM2  : right-wheel quadrature encoder (QEI)
 *   - TIM16 : right-motor PWM (20 kHz, 11.6-bit resolution)
 *   - LPTIM1: left-motor PWM  (20 kHz, 11.6-bit resolution)
 *   - USART1: ST-Link virtual COM port (PC interface, 115200 baud, DMA TX)
 *   - ADC1  : motor current sensing (IN10=PA5 left, IN4=PC3 right)
 *   - GPIO  : motor direction and brake outputs
 *
 * Native MB1292B peripherals (SPI1/OLED, QUADSPI/flash, I2C1/board-sensors,
 * I2C3/IMU) are initialised through the BSP layer and are therefore not
 * declared here.
 */

#ifndef PERIPH_INIT_H
#define PERIPH_INIT_H

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"

/* =========================================================================
 * HAL handle exports
 * ========================================================================= */

extern TIM_HandleTypeDef  htim1;   /**< Left encoder  — TIM1,  PD14/PD15 */
extern TIM_HandleTypeDef  htim2;   /**< Right encoder — TIM2,  PA15/PB3  */
extern TIM_HandleTypeDef  htim16;  /**< Right motor PWM — TIM16, PE0     */
extern LPTIM_HandleTypeDef hlptim1; /**< Left motor PWM — LPTIM1, PC1    */
extern UART_HandleTypeDef huart1;  /**< VCP — USART1, PB6 TX / PB7 RX   */
extern DMA_HandleTypeDef  hdma_usart1_tx; /**< USART1 TX DMA channel     */
extern ADC_HandleTypeDef  hadc1;   /**< Current sensing — ADC1           */

/* =========================================================================
 * Motor GPIO pin helpers
 * ========================================================================= */

#define MOTOR_LEFT_DIR_PIN      GPIO_PIN_12
#define MOTOR_LEFT_DIR_PORT     GPIOD

#define MOTOR_LEFT_BRAKE_PIN    GPIO_PIN_13
#define MOTOR_LEFT_BRAKE_PORT   GPIOD

#define MOTOR_RIGHT_DIR_PIN     GPIO_PIN_3
#define MOTOR_RIGHT_DIR_PORT    GPIOE

#define MOTOR_RIGHT_BRAKE_PIN   GPIO_PIN_2
#define MOTOR_RIGHT_BRAKE_PORT  GPIOB

/* =========================================================================
 * PWM resolution constants
 *   PCLK1 = 64 MHz, prescaler = DIV1, ARR = 3200 → 20 kHz
 * ========================================================================= */

#define MOTOR_PWM_PERIOD        3199U   /**< ARR value (period − 1)          */
#define MOTOR_PWM_MAX_DUTY      3200U   /**< Full-scale compare value (100%) */

/* =========================================================================
 * Init function prototypes
 * ========================================================================= */

/**
 * @brief Initialise TIM1 in quadrature encoder interface mode.
 *        Pins: PD14 = CH1, PD15 = CH2.
 */
void Periph_TIM1_Init(void);

/**
 * @brief Initialise TIM2 in quadrature encoder interface mode.
 *        Pins: PA15 = CH1, PB3 = CH2.
 *        PB3 reuses the SWO pin; trace output is disabled by this assignment.
 */
void Periph_TIM2_Init(void);

/**
 * @brief Initialise TIM16 for 20 kHz PWM on the right motor.
 *        Pin: PE0 = CH1.
 */
void Periph_TIM16_Init(void);

/**
 * @brief Initialise LPTIM1 for 20 kHz PWM on the left motor.
 *        Pin: PC1 = OUT. Clock source: PCLK1 = 64 MHz, prescaler DIV1.
 */
void Periph_LPTIM1_Init(void);

/**
 * @brief Initialise USART1 as a 115200-baud virtual COM port (ST-Link).
 *        Pins: PB6 = TX, PB7 = RX.  TX is DMA-backed (DMA2 channel 4).
 */
void Periph_USART1_Init(void);

/**
 * @brief Initialise ADC1 for dual-channel motor current sensing.
 *        Channels: IN10 (PA5) = left motor, IN4 (PC3) = right motor.
 *        Triggered by software; 12-bit right-aligned, single conversion.
 */
void Periph_ADC1_Init(void);

/**
 * @brief Configure motor direction and brake GPIO outputs.
 *        PD12 = left dir, PD13 = left brake,
 *        PE3  = right dir, PB2  = right brake.
 *        Brake outputs are driven high (active) on startup for safety.
 */
void Periph_GPIO_Motor_Init(void);

/**
 * @brief Call all robot peripheral init functions in the correct order.
 *        Must be called after SystemClock_Config() and
 *        PeriphCommonClock_Config().
 */
void Periph_Init_All(void);

#ifdef __cplusplus
}
#endif

#endif /* PERIPH_INIT_H */
