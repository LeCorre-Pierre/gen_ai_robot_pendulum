/**
 * @file    main.c
 * @brief   Application entry point — LEFT motor bring-up test sequence.
 *
 * Four sequential tests, designed for step-through debugging:
 *   1. PWM ramp  : 0 % → 100 % in 11 steps of 500 ms each.
 *   2. Encoder   : read TIM1 counter every 100 ms while motor runs at 50 %.
 *   3. Current   : sample ADC1 (IN10 = left, IN4 = right) 10 times at 50 %.
 *   4. Direction : forward (DIR=LOW) 2 s, then reverse (DIR=HIGH) 2 s.
 *
 * All result variables are volatile — set a breakpoint anywhere and
 * inspect them in the debugger without worrying about optimisation.
 *
 * Copyright (c) 2021 STMicroelectronics.  All rights reserved.
 * Licensed under the terms found in the LICENSE file in the root directory.
 */

#include "main.h"
#include "periph_init.h"

/* -------------------------------------------------------------------------
 * Private function prototypes
 * ------------------------------------------------------------------------- */
static void SystemClock_Config(void);
static void PeriphCommonClock_Config(void);

/* =========================================================================
 * Motor helpers
 * ========================================================================= */

/**
 * @brief Set the LEFT motor PWM duty via the LPTIM1 compare register.
 *
 * Writes the new CMP value and waits for the CMPOK synchronisation flag so
 * the hardware has latched the value before returning.
 *
 * @param duty  Compare value: 0 = 0 %, MOTOR_PWM_PERIOD (~3199) = ~100 %.
 */
static void Motor_Left_SetDuty(uint32_t duty)
{
    __HAL_LPTIM_COMPARE_SET(&hlptim1, duty);
    while (!__HAL_LPTIM_GET_FLAG(&hlptim1, LPTIM_FLAG_CMPOK)) {}
    __HAL_LPTIM_CLEAR_FLAG(&hlptim1, LPTIM_FLAG_CMPOK);
}

/**
 * @brief Release the LEFT motor brake and set direction to forward.
 *
 * DIR pin LOW = forward (as wired on the Arduino Motor Shield).
 */
static void Motor_Left_Forward(void)
{
    HAL_GPIO_WritePin(MOTOR_LEFT_DIR_PORT,   MOTOR_LEFT_DIR_PIN,   GPIO_PIN_RESET);
    HAL_GPIO_WritePin(MOTOR_LEFT_BRAKE_PORT, MOTOR_LEFT_BRAKE_PIN, GPIO_PIN_RESET);
}

/**
 * @brief Release the LEFT motor brake and set direction to reverse.
 *
 * DIR pin HIGH = reverse (as wired on the Arduino Motor Shield).
 */
static void Motor_Left_Reverse(void)
{
    HAL_GPIO_WritePin(MOTOR_LEFT_DIR_PORT,   MOTOR_LEFT_DIR_PIN,   GPIO_PIN_SET);
    HAL_GPIO_WritePin(MOTOR_LEFT_BRAKE_PORT, MOTOR_LEFT_BRAKE_PIN, GPIO_PIN_RESET);
}

/**
 * @brief Set duty to zero and engage the LEFT motor brake.
 */
static void Motor_Left_Brake(void)
{
    Motor_Left_SetDuty(0);
    HAL_GPIO_WritePin(MOTOR_LEFT_BRAKE_PORT, MOTOR_LEFT_BRAKE_PIN, GPIO_PIN_SET);
    HAL_GPIO_WritePin(MOTOR_LEFT_DIR_PORT,   MOTOR_LEFT_DIR_PIN,   GPIO_PIN_RESET); /* restore forward */
}

/* =========================================================================
 * main
 * ========================================================================= */

int main(void)
{
    /* ------------------------------------------------------------------ */
    /*  System and peripheral init                                         */
    /* ------------------------------------------------------------------ */
    HAL_Init();
    SystemClock_Config();
    PeriphCommonClock_Config();
    Periph_Init_All();

    /* ================================================================== */
    /*  Bring-up state — pause the debugger at any time and inspect.      */
    /*                                                                     */
    /*  test_step: 0 = idle, 1 = ramp, 2 = encoder, 3 = ADC, 4 = dir     */
    /* ================================================================== */

    /* --- shared state ------------------------------------------------- */
    volatile uint8_t  test_step      = 0;

    /* --- Test 1: PWM ramp --------------------------------------------- */
    volatile uint32_t ramp_duty_cmp  = 0;   /* CMP value applied each step */

    /* --- Test 2: Encoder ---------------------------------------------- */
    volatile uint16_t enc_raw        = 0;   /* TIM1 CNT register (16-bit)  */
    volatile int16_t  enc_delta      = 0;   /* ticks between two samples   */

    /* --- Test 3: ADC current sensor ------------------------------------ */
    volatile uint16_t adc_left_raw   = 0;   /* IN10/PA5 — left motor       */
    volatile uint16_t adc_right_raw  = 0;   /* IN4/PC3  — right motor      */

    /* --- Test 4: Direction -------------------------------------------- */
    volatile uint8_t  dir_forward    = 0;   /* 1 while running forward     */
    volatile uint8_t  dir_reverse    = 0;   /* 1 while running reverse     */

    /* ================================================================== */
    /*  TEST 1 — PWM ramp: 0 % → 100 % in 11 steps of 500 ms            */
    /*                                                                     */
    /*  Watch: ramp_duty_cmp                                              */
    /*  Expected: motor spins up progressively over ~5.5 s               */
    /* ================================================================== */
    test_step = 1;

    Motor_Left_Forward();

    for (uint32_t step = 0; step <= 10U; ++step)
    {
        ramp_duty_cmp = (step * MOTOR_PWM_PERIOD) / 10U;   /* 0, 320, 640 … 3199 */
        Motor_Left_SetDuty(ramp_duty_cmp);
        HAL_Delay(500);
    }

    HAL_Delay(2000);    /* hold at 100 % for 2 s */

    Motor_Left_Brake();
    HAL_Delay(1000);    /* coast to rest before next test */

    /* ================================================================== */
    /*  TEST 2 — LEFT encoder                                             */
    /*                                                                     */
    /*  Watch: enc_raw, enc_delta                                         */
    /*  Expected: enc_raw advances; enc_delta > 0 for forward rotation    */
    /* ================================================================== */
    test_step = 2;

    Motor_Left_Forward();
    Motor_Left_SetDuty(MOTOR_PWM_PERIOD / 2U);   /* 50 % */

    uint16_t enc_prev = 0;

    for (uint32_t i = 0; i < 20U; ++i)
    {
        HAL_Delay(100);
        enc_raw   = (uint16_t)__HAL_TIM_GET_COUNTER(&htim1);
        enc_delta = (int16_t)(enc_raw - enc_prev);
        enc_prev  = enc_raw;
        /* Breakpoint here to inspect enc_raw and enc_delta each iteration */
    }

    Motor_Left_Brake();
    HAL_Delay(1000);

    /* ================================================================== */
    /*  TEST 3 — Motor current sensor (ADC1)                             */
    /*                                                                     */
    /*  Watch: adc_left_raw (0–4095), adc_right_raw (0–4095)             */
    /*  Expected: adc_left_raw > 0 with motor loaded; adc_right_raw ≈ 0  */
    /*  Note: ADC_EOC_SINGLE_CONV is used temporarily so both ranks can   */
    /*        be read individually without DMA.                           */
    /* ================================================================== */
    test_step = 3;

    Motor_Left_Forward();
    Motor_Left_SetDuty(MOTOR_PWM_PERIOD / 2U);   /* 50 % — produce measurable current */
    HAL_Delay(200);   /* let current settle */

    hadc1.Init.EOCSelection = ADC_EOC_SINGLE_CONV;   /* poll per-channel, not per-sequence */

    for (uint32_t i = 0; i < 10U; ++i)
    {
        HAL_ADC_Start(&hadc1);

        if (HAL_ADC_PollForConversion(&hadc1, 10U) == HAL_OK)
        {
            adc_left_raw  = (uint16_t)HAL_ADC_GetValue(&hadc1);   /* rank 1 — left motor */
        }

        if (HAL_ADC_PollForConversion(&hadc1, 10U) == HAL_OK)
        {
            adc_right_raw = (uint16_t)HAL_ADC_GetValue(&hadc1);   /* rank 2 — right motor */
        }

        HAL_ADC_Stop(&hadc1);
        HAL_Delay(100);
        /* Breakpoint here to read adc_left_raw and adc_right_raw */
    }

    hadc1.Init.EOCSelection = ADC_EOC_SEQ_CONV;   /* restore original mode */

    Motor_Left_Brake();
    HAL_Delay(1000);

    /* ================================================================== */
    /*  TEST 4 — Motor direction                                          */
    /*                                                                     */
    /*  Watch: dir_forward, dir_reverse, enc_raw                         */
    /*  Expected: encoder increments with dir_forward=1,                 */
    /*            encoder decrements with dir_reverse=1                  */
    /* ================================================================== */
    test_step = 4;

    /* --- Forward (DIR = LOW) ----------------------------------------- */
    dir_forward = 1;
    Motor_Left_Forward();
    Motor_Left_SetDuty(MOTOR_PWM_PERIOD / 2U);
    HAL_Delay(2000);

    Motor_Left_Brake();
    dir_forward = 0;
    HAL_Delay(1000);

    /* --- Reverse (DIR = HIGH) ---------------------------------------- */
    dir_reverse = 1;
    Motor_Left_Reverse();
    Motor_Left_SetDuty(MOTOR_PWM_PERIOD / 2U);
    HAL_Delay(2000);

    Motor_Left_Brake();
    dir_reverse = 0;
    HAL_Delay(500);

    /* ================================================================== */
    /*  All tests complete — motor is braked, safe state                  */
    /*  Set test_step = 0 and enter idle loop.                            */
    /* ================================================================== */
    test_step = 0;

    while (1)
    {
        /* Breakpoint here to confirm all tests finished. */
    }
}

/* =========================================================================
 * Clock configuration
 * ========================================================================= */

/**
 * @brief Configure system clocks.
 *
 * HSE (32 MHz) → PLL (PLLM=8, PLLN=32, PLLR=2) → SYSCLK = 64 MHz.
 * HCLK = 64 MHz, PCLK1 = PCLK2 = 64 MHz.
 * LSE enabled for BLE RF wake-up.
 */
static void SystemClock_Config(void)
{
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

    HAL_PWR_EnableBkUpAccess();
    __HAL_RCC_LSEDRIVE_CONFIG(RCC_LSEDRIVE_MEDIUMHIGH);

    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

    RCC_OscInitStruct.OscillatorType      = RCC_OSCILLATORTYPE_HSI
                                          | RCC_OSCILLATORTYPE_HSE
                                          | RCC_OSCILLATORTYPE_LSE;
    RCC_OscInitStruct.HSEState            = RCC_HSE_ON;
    RCC_OscInitStruct.LSEState            = RCC_LSE_ON;
    RCC_OscInitStruct.HSIState            = RCC_HSI_ON;
    RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    RCC_OscInitStruct.PLL.PLLState        = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource       = RCC_PLLSOURCE_HSE;
    RCC_OscInitStruct.PLL.PLLM            = RCC_PLLM_DIV8;
    RCC_OscInitStruct.PLL.PLLN            = 32;
    RCC_OscInitStruct.PLL.PLLP            = RCC_PLLP_DIV2;
    RCC_OscInitStruct.PLL.PLLR            = RCC_PLLR_DIV2;
    RCC_OscInitStruct.PLL.PLLQ            = RCC_PLLQ_DIV2;

    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
    {
        Error_Handler();
    }

    RCC_ClkInitStruct.ClockType      = RCC_CLOCKTYPE_HCLK4 | RCC_CLOCKTYPE_HCLK2
                                     | RCC_CLOCKTYPE_HCLK  | RCC_CLOCKTYPE_SYSCLK
                                     | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource   = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider  = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
    RCC_ClkInitStruct.AHBCLK2Divider = RCC_SYSCLK_DIV2;
    RCC_ClkInitStruct.AHBCLK4Divider = RCC_SYSCLK_DIV1;

    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_3) != HAL_OK)
    {
        Error_Handler();
    }
}

/**
 * @brief Configure peripheral-specific clocks shared across subsystems.
 *
 * - RF wake-up clock: LSE
 * - SMPS clock: HSI, range 1
 * - SMPS output: 1.4 V (enabled when CFG_USE_SMPS != 0)
 */
static void PeriphCommonClock_Config(void)
{
    RCC_PeriphCLKInitTypeDef PeriphClkInitStruct = {0};

    PeriphClkInitStruct.PeriphClockSelection    = RCC_PERIPHCLK_SMPS | RCC_PERIPHCLK_RFWAKEUP;
    PeriphClkInitStruct.RFWakeUpClockSelection  = RCC_RFWKPCLKSOURCE_LSE;
    PeriphClkInitStruct.SmpsClockSelection      = RCC_SMPSCLKSOURCE_HSI;
    PeriphClkInitStruct.SmpsDivSelection        = RCC_SMPSCLKDIV_RANGE1;

    if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInitStruct) != HAL_OK)
    {
        Error_Handler();
    }

#if (CFG_USE_SMPS != 0)
    LL_PWR_SMPS_SetStartupCurrent(LL_PWR_SMPS_STARTUP_CURRENT_80MA);
    LL_PWR_SMPS_SetOutputVoltageLevel(LL_PWR_SMPS_OUTPUT_VOLTAGE_1V40);
    LL_PWR_SMPS_Enable();
#endif
}

/* =========================================================================
 * Error handler
 * ========================================================================= */

/**
 * @brief Error handler — disables interrupts and halts.
 */
void Error_Handler(void)
{
    __disable_irq();
    while (1)
    {
    }
}

#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line)
{
    (void)file;
    (void)line;
}
#endif
