#include "stm32wbxx_hal_msp.h"

TIM_HandleTypeDef   htim1;
TIM_HandleTypeDef   htim2;
TIM_HandleTypeDef   htim16;
LPTIM_HandleTypeDef hlptim1;

static void gpio_clocks_enable(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_GPIOD_CLK_ENABLE();
    __HAL_RCC_GPIOE_CLK_ENABLE();
}
void Periph_TIM1_Init(void)
{
    GPIO_InitTypeDef      GPIO_InitStruct = {0};
    TIM_Encoder_InitTypeDef sConfig       = {0};

    /* Peripheral and GPIO clocks */
    __HAL_RCC_TIM1_CLK_ENABLE();

    /* PD14 = TIM1_CH1, PD15 = TIM1_CH2 */
    GPIO_InitStruct.Pin       = GPIO_PIN_14 | GPIO_PIN_15;
    GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull      = GPIO_PULLUP;
    GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_MEDIUM;
    GPIO_InitStruct.Alternate = GPIO_AF1_TIM1;
    HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);

    /* TIM1 base */
    htim1.Instance               = TIM1;
    htim1.Init.Prescaler         = 0;
    htim1.Init.CounterMode       = TIM_COUNTERMODE_UP;
    htim1.Init.Period            = 0xFFFFU;  /* 16-bit wrap */
    htim1.Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    htim1.Init.RepetitionCounter = 0;
    htim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;

    /* Encoder channel config */
    sConfig.EncoderMode  = TIM_ENCODERMODE_TI12;
    sConfig.IC1Polarity  = TIM_ICPOLARITY_RISING;
    sConfig.IC1Selection = TIM_ICSELECTION_DIRECTTI;
    sConfig.IC1Prescaler = TIM_ICPSC_DIV1;
    sConfig.IC1Filter    = 4U;
    sConfig.IC2Polarity  = TIM_ICPOLARITY_RISING;
    sConfig.IC2Selection = TIM_ICSELECTION_DIRECTTI;
    sConfig.IC2Prescaler = TIM_ICPSC_DIV1;
    sConfig.IC2Filter    = 4U;

    if (HAL_TIM_Encoder_Init(&htim1, &sConfig) != HAL_OK)
    {
        Error_Handler();
    }

    HAL_TIM_Encoder_Start(&htim1, TIM_CHANNEL_ALL);
}
void Periph_TIM2_Init(void)
{
    GPIO_InitTypeDef        GPIO_InitStruct = {0};
    TIM_Encoder_InitTypeDef sConfig         = {0};

    __HAL_RCC_TIM2_CLK_ENABLE();

    /* PA15 = TIM2_CH1 */
    GPIO_InitStruct.Pin       = GPIO_PIN_15;
    GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull      = GPIO_PULLUP;
    GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_MEDIUM;
    GPIO_InitStruct.Alternate = GPIO_AF1_TIM2;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

    /* PB3 = TIM2_CH2 (overrides SWO) */
    GPIO_InitStruct.Pin = GPIO_PIN_3;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    /* TIM2 base — 32-bit counter */
    htim2.Instance               = TIM2;
    htim2.Init.Prescaler         = 0;
    htim2.Init.CounterMode       = TIM_COUNTERMODE_UP;
    htim2.Init.Period            = 0xFFFFFFFFU;  /* 32-bit wrap */
    htim2.Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    htim2.Init.RepetitionCounter = 0;
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

    if (HAL_TIM_Encoder_Init(&htim2, &sConfig) != HAL_OK)
    {
        Error_Handler();
    }

    HAL_TIM_Encoder_Start(&htim2, TIM_CHANNEL_ALL);
}
void Periph_TIM16_Init(void)
{
    GPIO_InitTypeDef    GPIO_InitStruct = {0};
    TIM_OC_InitTypeDef  sConfigOC       = {0};

    __HAL_RCC_TIM16_CLK_ENABLE();

    /* PE0 = TIM16_CH1 */
    GPIO_InitStruct.Pin       = GPIO_PIN_0;
    GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull      = GPIO_NOPULL;
    GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_HIGH;
    GPIO_InitStruct.Alternate = GPIO_AF14_TIM16;
    HAL_GPIO_Init(GPIOE, &GPIO_InitStruct);

    /* TIM16 base */
    htim16.Instance               = TIM16;
    htim16.Init.Prescaler         = 0;
    htim16.Init.CounterMode       = TIM_COUNTERMODE_UP;
    htim16.Init.Period            = MOTOR_PWM_PERIOD;   /* 3199 */
    htim16.Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    htim16.Init.RepetitionCounter = 0;
    htim16.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;

    if (HAL_TIM_PWM_Init(&htim16) != HAL_OK)
    {
        Error_Handler();
    }

    /* Channel 1 — PWM mode 1, starts at 0 % duty */
    sConfigOC.OCMode       = TIM_OCMODE_PWM1;
    sConfigOC.Pulse        = 0;
    sConfigOC.OCPolarity   = TIM_OCPOLARITY_HIGH;
    sConfigOC.OCNPolarity  = TIM_OCNPOLARITY_HIGH;
    sConfigOC.OCFastMode   = TIM_OCFAST_DISABLE;
    sConfigOC.OCIdleState  = TIM_OCIDLESTATE_RESET;
    sConfigOC.OCNIdleState = TIM_OCNIDLESTATE_RESET;

    if (HAL_TIM_PWM_ConfigChannel(&htim16, &sConfigOC, TIM_CHANNEL_1) != HAL_OK)
    {
        Error_Handler();
    }

    HAL_TIM_PWM_Start(&htim16, TIM_CHANNEL_1);
}
void Periph_LPTIM1_Init(void)
{
    GPIO_InitTypeDef         GPIO_InitStruct     = {0};
    RCC_PeriphCLKInitTypeDef PeriphClkInitStruct = {0};

    /* Explicitly select PCLK1 as LPTIM1 kernel clock (do not rely on reset
     * defaults: PeriphCommonClock_Config touches RCC_CCIPR for SMPS/RF and
     * could leave LPTIM1SEL in an unexpected state). */
    PeriphClkInitStruct.PeriphClockSelection   = RCC_PERIPHCLK_LPTIM1;
    PeriphClkInitStruct.Lptim1ClockSelection   = RCC_LPTIM1CLKSOURCE_PCLK1;
    if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInitStruct) != HAL_OK)
    {
        Error_Handler();
    }

    __HAL_RCC_LPTIM1_CLK_ENABLE();

    /* PC1 = LPTIM1_OUT */
    GPIO_InitStruct.Pin       = GPIO_PIN_1;
    GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull      = GPIO_NOPULL;
    GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_HIGH;
    GPIO_InitStruct.Alternate = GPIO_AF1_LPTIM1;
    HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

    hlptim1.Instance                    = LPTIM1;
    hlptim1.Init.Clock.Source           = LPTIM_CLOCKSOURCE_APBCLOCK_LPOSC;
    hlptim1.Init.Clock.Prescaler        = LPTIM_PRESCALER_DIV1;
    hlptim1.Init.Trigger.Source         = LPTIM_TRIGSOURCE_SOFTWARE;
    hlptim1.Init.OutputPolarity         = LPTIM_OUTPUTPOLARITY_HIGH;
    hlptim1.Init.UpdateMode             = LPTIM_UPDATE_IMMEDIATE;
    hlptim1.Init.CounterSource          = LPTIM_COUNTERSOURCE_INTERNAL;
    hlptim1.Init.Input1Source           = LPTIM_INPUT1SOURCE_GPIO;
    hlptim1.Init.Input2Source           = LPTIM_INPUT2SOURCE_GPIO;

    if (HAL_LPTIM_Init(&hlptim1) != HAL_OK)
    {
        Error_Handler();
    }

    /* Start continuous PWM: Period = ARR = 3199, Pulse = CMP = 0 (0 %) */
    if (HAL_LPTIM_PWM_Start(&hlptim1, MOTOR_PWM_PERIOD, 0) != HAL_OK)
    {
        Error_Handler();
    }
}

void Periph_GPIO_Motor_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    /* Left motor: direction (PD12) — output low */
    HAL_GPIO_WritePin(MOTOR_LEFT_DIR_PORT, MOTOR_LEFT_DIR_PIN, GPIO_PIN_RESET);

    /* Left motor: brake (PD13) — output high → brake engaged */
    HAL_GPIO_WritePin(MOTOR_LEFT_BRAKE_PORT, MOTOR_LEFT_BRAKE_PIN, GPIO_PIN_SET);

    /* Right motor: direction (PE3) — output low */
    HAL_GPIO_WritePin(MOTOR_RIGHT_DIR_PORT, MOTOR_RIGHT_DIR_PIN, GPIO_PIN_RESET);

    /* Right motor: brake (PB2) — output high → brake engaged */
    HAL_GPIO_WritePin(MOTOR_RIGHT_BRAKE_PORT, MOTOR_RIGHT_BRAKE_PIN, GPIO_PIN_SET);

    /* PD12, PD13 */
    GPIO_InitStruct.Pin   = MOTOR_LEFT_DIR_PIN | MOTOR_LEFT_BRAKE_PIN;
    GPIO_InitStruct.Mode  = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull  = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);

    /* PE3 */
    GPIO_InitStruct.Pin = MOTOR_RIGHT_DIR_PIN;
    HAL_GPIO_Init(MOTOR_RIGHT_DIR_PORT, &GPIO_InitStruct);

    /* PB2 */
    GPIO_InitStruct.Pin = MOTOR_RIGHT_BRAKE_PIN;
    HAL_GPIO_Init(MOTOR_RIGHT_BRAKE_PORT, &GPIO_InitStruct);
}

void Periph_Init_All(void)
{
    /* Enable all GPIO port clocks first */
    gpio_clocks_enable();

    /* Motor GPIOs first so brake lines are asserted before any PWM starts */
    Periph_GPIO_Motor_Init();

    /* Encoders */
    Periph_TIM1_Init();
    Periph_TIM2_Init();

    /* Motor PWM */
    Periph_TIM16_Init();
    Periph_LPTIM1_Init();
}
