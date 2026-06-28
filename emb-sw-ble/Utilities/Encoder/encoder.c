/**
  ******************************************************************************
  * @file    encoder.c
  * @brief   Quadrature encoder acquisition for the left/right wheels.
  *
  * This module configures TIM1 (left wheel) and TIM2 (right wheel) in QEI mode
  * and derives wheel speed from the change in timer counters over time.
  *
  * Use it from a periodic control or telemetry task:
  *   - Call Encoders_Init() once after the MCU peripherals are initialized.
  *   - Call Encoders_Update(dt_s) on every loop tick with the elapsed time in
  *     seconds.
  *   - Read the latest values with Encoders_GetSpeedL_RPM() and
  *     Encoders_GetSpeedR_RPM().
  *
  * Hardware notes:
  *   - TIM1 uses PD14/PD15 and is configured as a 16-bit encoder.
  *   - TIM2 uses PA15/PB3 and is configured as a 32-bit encoder.
  *   - The conversion uses 7424 ticks/revolution, corresponding to
  *     64 CPR x 29:1 gearbox x4.
  ******************************************************************************
  */
#include "main.h"
#include "encoder.h"

/* Effective ticks per wheel revolution: 64 CPR x 29:1 gearbox x4 (QEI) = 7424.
 * Adjust here if the RPM scaling needs calibration. */
#define ENC_TICKS_PER_REV   7424.0f

static TIM_HandleTypeDef htim1;   /* left,  16-bit */
static TIM_HandleTypeDef htim2;   /* right, 32-bit */

static uint32_t prev_l, prev_r;
static volatile float speed_l_rpm = 0.0f;
static volatile float speed_r_rpm = 0.0f;

static void TIM1_QEI_Init(void)
{
  GPIO_InitTypeDef        gpio    = {0};
  TIM_Encoder_InitTypeDef sConfig = {0};

  __HAL_RCC_TIM1_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();

  /* PD14 = TIM1_CH1, PD15 = TIM1_CH2 */
  gpio.Pin       = GPIO_PIN_14 | GPIO_PIN_15;
  gpio.Mode      = GPIO_MODE_AF_PP;
  gpio.Pull      = GPIO_PULLUP;
  gpio.Speed     = GPIO_SPEED_FREQ_MEDIUM;
  gpio.Alternate = GPIO_AF1_TIM1;
  HAL_GPIO_Init(GPIOD, &gpio);

  htim1.Instance           = TIM1;
  htim1.Init.Prescaler     = 0;
  htim1.Init.CounterMode   = TIM_COUNTERMODE_UP;
  htim1.Init.Period        = 0xFFFFU;
  htim1.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;

  sConfig.EncoderMode  = TIM_ENCODERMODE_TI12;
  sConfig.IC1Polarity  = TIM_ICPOLARITY_RISING;
  sConfig.IC1Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC1Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC1Filter    = 4U;
  sConfig.IC2Polarity  = TIM_ICPOLARITY_RISING;
  sConfig.IC2Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC2Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC2Filter    = 4U;

  if (HAL_TIM_Encoder_Init(&htim1, &sConfig) != HAL_OK) { Error_Handler(); }
  HAL_TIM_Encoder_Start(&htim1, TIM_CHANNEL_ALL);
}

static void TIM2_QEI_Init(void)
{
  GPIO_InitTypeDef        gpio    = {0};
  TIM_Encoder_InitTypeDef sConfig = {0};

  __HAL_RCC_TIM2_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /* PA15 = TIM2_CH1 */
  gpio.Pin       = GPIO_PIN_15;
  gpio.Mode      = GPIO_MODE_AF_PP;
  gpio.Pull      = GPIO_PULLUP;
  gpio.Speed     = GPIO_SPEED_FREQ_MEDIUM;
  gpio.Alternate = GPIO_AF1_TIM2;
  HAL_GPIO_Init(GPIOA, &gpio);

  /* PB3 = TIM2_CH2 (overrides SWO) */
  gpio.Pin = GPIO_PIN_3;
  HAL_GPIO_Init(GPIOB, &gpio);

  htim2.Instance           = TIM2;
  htim2.Init.Prescaler     = 0;
  htim2.Init.CounterMode   = TIM_COUNTERMODE_UP;
  htim2.Init.Period        = 0xFFFFFFFFU;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;

  sConfig.EncoderMode  = TIM_ENCODERMODE_TI12;
  sConfig.IC1Polarity  = TIM_ICPOLARITY_RISING;
  sConfig.IC1Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC1Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC1Filter    = 4U;
  sConfig.IC2Polarity  = TIM_ICPOLARITY_RISING;
  sConfig.IC2Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC2Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC2Filter    = 4U;

  if (HAL_TIM_Encoder_Init(&htim2, &sConfig) != HAL_OK) { Error_Handler(); }
  HAL_TIM_Encoder_Start(&htim2, TIM_CHANNEL_ALL);
}

/* Initialize both encoder timers and capture the initial counter values. */
void Encoders_Init(void)
{
  TIM1_QEI_Init();
  TIM2_QEI_Init();
  prev_l = __HAL_TIM_GET_COUNTER(&htim1);
  prev_r = __HAL_TIM_GET_COUNTER(&htim2);
}

/* Update the measured wheel speed using the elapsed time since the last call. */
void Encoders_Update(float dt_s)
{
  uint32_t cl = __HAL_TIM_GET_COUNTER(&htim1);
  uint32_t cr = __HAL_TIM_GET_COUNTER(&htim2);

  /* signed delta with hardware wrap handling (16-bit TIM1, 32-bit TIM2) */
  int32_t dl = (int16_t)((uint16_t)cl - (uint16_t)prev_l);
  int32_t dr = (int32_t)(cr - prev_r);

  prev_l = cl;
  prev_r = cr;

  if (dt_s > 0.0f)
  {
    speed_l_rpm = ((float)dl / dt_s) / ENC_TICKS_PER_REV * 60.0f;
    speed_r_rpm = ((float)dr / dt_s) / ENC_TICKS_PER_REV * 60.0f;
  }
}

float Encoders_GetSpeedL_RPM(void) { return speed_l_rpm; }
float Encoders_GetSpeedR_RPM(void) { return speed_r_rpm; }
