/**
 * @file    main.c
 * @brief   Application entry point — LEFT motor bring-up test sequence.
 *
 * Four sequential tests, designed for step-through debugging:
 *   1. PWM ramp  : 0 % → 100 % in 11 steps of 500 ms each.
 *   2. Encoder   : four sub-tests for full left-encoder functional verification:
 *        2a — TIM1 active   : counter stable at rest (enc_at_rest_ok == 1)
 *        2b — CW rotation   : counter increments while motor runs forward (enc_cw_ok == 1)
 *        2c — CCW rotation  : counter decrements while motor runs reverse (enc_ccw_ok == 1)
 *        2d — Resolution    : ticks accumulated over 5 s at 50 % — compute RPM from enc_ticks_5s
 *   3. Current   : sample ADC1 (IN10 = left, IN4 = right) 10 times at 50 %.
 *   4. Direction : forward (DIR=LOW) 2 s, then reverse (DIR=HIGH) 2 s.
 *   5. Right enc : same four sub-tests as Test 2 but for TIM2 / right motor.
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
 * Motor helpers — RIGHT motor (TIM16 PWM, no CMPOK synchronisation needed)
 * ========================================================================= */

static void Motor_Right_SetDuty(uint32_t duty)
{
    __HAL_TIM_SET_COMPARE(&htim16, TIM_CHANNEL_1, duty);
}

static void Motor_Right_Forward(void)
{
    HAL_GPIO_WritePin(MOTOR_RIGHT_DIR_PORT,   MOTOR_RIGHT_DIR_PIN,   GPIO_PIN_RESET);
    HAL_GPIO_WritePin(MOTOR_RIGHT_BRAKE_PORT, MOTOR_RIGHT_BRAKE_PIN, GPIO_PIN_RESET);
}

static void Motor_Right_Reverse(void)
{
    HAL_GPIO_WritePin(MOTOR_RIGHT_DIR_PORT,   MOTOR_RIGHT_DIR_PIN,   GPIO_PIN_SET);
    HAL_GPIO_WritePin(MOTOR_RIGHT_BRAKE_PORT, MOTOR_RIGHT_BRAKE_PIN, GPIO_PIN_RESET);
}

static void Motor_Right_Brake(void)
{
    Motor_Right_SetDuty(0);
    HAL_GPIO_WritePin(MOTOR_RIGHT_BRAKE_PORT, MOTOR_RIGHT_BRAKE_PIN, GPIO_PIN_SET);
    HAL_GPIO_WritePin(MOTOR_RIGHT_DIR_PORT,   MOTOR_RIGHT_DIR_PIN,   GPIO_PIN_RESET);
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
    volatile uint8_t  enc_at_rest_ok = 0;   /* 2a pass: counter stable at rest  */
    volatile uint8_t  enc_cw_ok      = 0;   /* 2b pass: counter advances CW     */
    volatile uint8_t  enc_ccw_ok     = 0;   /* 2c pass: counter retreats CCW    */
    volatile int32_t  enc_ticks_5s   = 0;   /* 2d: ticks in 5 s @ 50 % duty    */

    /* --- Test 3: ADC current sensor ------------------------------------ */
    volatile uint16_t adc_left_raw   = 0;   /* IN10/PA5 — left motor       */
    volatile uint16_t adc_right_raw  = 0;   /* IN4/PC3  — right motor      */

    /* --- Test 4: Direction -------------------------------------------- */
    volatile uint8_t  dir_forward    = 0;   /* 1 while running forward     */
    volatile uint8_t  dir_reverse    = 0;   /* 1 while running reverse     */

    /* --- Test 5: Right encoder (TIM2 / PA15 + PB3) -------------------- */
    volatile uint16_t enc_r_raw        = 0;
    volatile int16_t  enc_r_delta      = 0;
    volatile uint8_t  enc_r_at_rest_ok = 0;
    volatile uint8_t  enc_r_cw_ok      = 0;
    volatile uint8_t  enc_r_ccw_ok     = 0;
    volatile int32_t  enc_r_ticks_5s   = 0;

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
    /*  TEST 2 — LEFT encoder functional verification (4 sub-tests)      */
    /*                                                                     */
    /*  Watch: enc_raw, enc_delta, enc_at_rest_ok, enc_cw_ok,            */
    /*         enc_ccw_ok, enc_ticks_5s                                   */
    /* ================================================================== */
    test_step = 2;

    /* ----- 2a: TIM1 active — counter must be stable at rest ----------- */
    /*                                                                      */
    /*  Motor fully braked. 5 samples over 500 ms.                        */
    /*  Expected: enc_at_rest_ok == 1  (enc_delta == 0 every sample)      */
    {
        Motor_Left_Brake();
        HAL_Delay(200);

        uint16_t enc_prev_a = (uint16_t)__HAL_TIM_GET_COUNTER(&htim1);
        uint8_t  stable     = 1;

        for (uint32_t i = 0; i < 5U; ++i)
        {
            HAL_Delay(100);
            enc_raw   = (uint16_t)__HAL_TIM_GET_COUNTER(&htim1);
            enc_delta = (int16_t)(enc_raw - enc_prev_a);
            enc_prev_a = enc_raw;
            if (enc_delta != 0)
                stable = 0;
            /* Breakpoint here: enc_delta must equal 0 */
        }
        enc_at_rest_ok = stable;
        /* PASS criterion: enc_at_rest_ok == 1 */
    }

    /* ----- 2b: CW rotation — motor forward, counter must increment ----- */
    /*                                                                       */
    /*  Motor forward at 50 % for 2 s (20 samples × 100 ms).              */
    /*  Expected: enc_cw_ok == 1  (enc_delta > 0 every sample)             */
    {
        uint16_t enc_prev_b = (uint16_t)__HAL_TIM_GET_COUNTER(&htim1);
        uint8_t  advancing  = 1;

        Motor_Left_Forward();
        Motor_Left_SetDuty(MOTOR_PWM_PERIOD / 2U);   /* 50 % */

        for (uint32_t i = 0; i < 20U; ++i)
        {
            HAL_Delay(100);
            enc_raw   = (uint16_t)__HAL_TIM_GET_COUNTER(&htim1);
            enc_delta = (int16_t)(enc_raw - enc_prev_b);
            enc_prev_b = enc_raw;
            if (enc_delta <= 0)
                advancing = 0;
            /* Breakpoint here: enc_delta must be > 0 */
        }

        Motor_Left_Brake();
        HAL_Delay(500);
        enc_cw_ok = advancing;
        /* PASS criterion: enc_cw_ok == 1
         * If enc_cw_ok == 0: check DIR/BRAKE wiring or swap CHA/CHB. */
    }

    /* ----- 2c: CCW rotation — motor reverse, counter must decrement ---- */
    /*                                                                       */
    /*  Motor reverse at 50 % for 2 s (20 samples × 100 ms).              */
    /*  Expected: enc_ccw_ok == 1  (enc_delta < 0 every sample)            */
    {
        uint16_t enc_prev_c = (uint16_t)__HAL_TIM_GET_COUNTER(&htim1);
        uint8_t  retreating = 1;

        Motor_Left_Reverse();
        Motor_Left_SetDuty(MOTOR_PWM_PERIOD / 2U);   /* 50 % */

        for (uint32_t i = 0; i < 20U; ++i)
        {
            HAL_Delay(100);
            enc_raw   = (uint16_t)__HAL_TIM_GET_COUNTER(&htim1);
            enc_delta = (int16_t)(enc_raw - enc_prev_c);
            enc_prev_c = enc_raw;
            if (enc_delta >= 0)
                retreating = 0;
            /* Breakpoint here: enc_delta must be < 0 */
        }

        Motor_Left_Brake();
        HAL_Delay(500);
        enc_ccw_ok = retreating;
        /* PASS criterion: enc_ccw_ok == 1
         * If enc_ccw_ok == 0 but enc_cw_ok == 1: check CHB polarity (PD15). */
    }

    /* ----- 2d: Resolution — ticks accumulated over 5 s at 50 % -------- */
    /*                                                                       */
    /*  Motor forward at 50 % for exactly 5 s.                             */
    /*  Expected: enc_ticks_5s ≈ 2 300 ticks  (rough; depends on supply)  */
    /*                                                                       */
    /*  To compute RPM from the result:                                     */
    /*    ticks_per_s  = enc_ticks_5s / 5                                  */
    /*    rev_per_s    = ticks_per_s  / 1856                               */
    /*    RPM          = rev_per_s   * 60                                  */
    /*  Plausible range at 50 % duty: 10–25 RPM at the wheel output.      */
    {
        uint16_t enc_start_d = (uint16_t)__HAL_TIM_GET_COUNTER(&htim1);

        Motor_Left_Forward();
        Motor_Left_SetDuty(MOTOR_PWM_PERIOD / 2U);   /* 50 % */
        HAL_Delay(5000);

        Motor_Left_Brake();
        uint16_t enc_end_d = (uint16_t)__HAL_TIM_GET_COUNTER(&htim1);

        /* Signed 32-bit delta — safe as long as wheel doesn't do >17 turns in 5 s */
        enc_ticks_5s = (int32_t)enc_end_d - (int32_t)enc_start_d;
        /* Breakpoint here: inspect enc_ticks_5s and compute RPM manually. */

        HAL_Delay(1000);
    }

    /* All encoder sub-tests complete. enc_at_rest_ok, enc_cw_ok, enc_ccw_ok
     * should all be 1. enc_ticks_5s should be positive and in the range
     * expected for the motor at 50 % duty. */

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
    /*  TEST 5 — RIGHT encoder functional verification (4 sub-tests)     */
    /*                                                                     */
    /*  Mirror of Test 2 but for TIM2 (PA15=CH1, PB3=CH2) and the right  */
    /*  motor (TIM16 PWM on PE0, DIR=PE3, BRAKE=PB2).                    */
    /*                                                                     */
    /*  Watch: enc_r_raw, enc_r_delta, enc_r_at_rest_ok, enc_r_cw_ok,   */
    /*         enc_r_ccw_ok, enc_r_ticks_5s                              */
    /* ================================================================== */
    test_step = 5;

    /* ----- 5a: TIM2 active — counter must be stable at rest ----------- */
    {
        Motor_Right_Brake();
        HAL_Delay(200);

        uint16_t enc_r_prev_a = (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);
        uint8_t  stable_r     = 1;

        for (uint32_t i = 0; i < 5U; ++i)
        {
            HAL_Delay(100);
            enc_r_raw   = (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);
            enc_r_delta = (int16_t)(enc_r_raw - enc_r_prev_a);
            enc_r_prev_a = enc_r_raw;
            if (enc_r_delta != 0)
                stable_r = 0;
            /* Breakpoint here: enc_r_delta must equal 0 */
        }
        enc_r_at_rest_ok = stable_r;
        /* PASS criterion: enc_r_at_rest_ok == 1
         * If it fails: check TIM2 is started in encoder mode (Periph_TIM2_Init). */
    }

    /* ----- 5b: CW rotation — motor forward, counter must increment ----- */
    {
        uint16_t enc_r_prev_b = (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);
        uint8_t  advancing_r  = 1;

        Motor_Right_Forward();
        Motor_Right_SetDuty(MOTOR_PWM_PERIOD / 2U);   /* 50 % */

        for (uint32_t i = 0; i < 20U; ++i)
        {
            HAL_Delay(100);
            enc_r_raw   = (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);
            enc_r_delta = (int16_t)(enc_r_raw - enc_r_prev_b);
            enc_r_prev_b = enc_r_raw;
            if (enc_r_delta <= 0)
                advancing_r = 0;
            /* Breakpoint here: enc_r_delta must be > 0 */
        }

        Motor_Right_Brake();
        HAL_Delay(500);
        enc_r_cw_ok = advancing_r;
        /* PASS criterion: enc_r_cw_ok == 1
         * If enc_r_delta is consistently < 0: swap CHA/CHB (PA15 ↔ PB3). */
    }

    /* ----- 5c: CCW rotation — motor reverse, counter must decrement ---- */
    {
        uint16_t enc_r_prev_c = (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);
        uint8_t  retreating_r = 1;

        Motor_Right_Reverse();
        Motor_Right_SetDuty(MOTOR_PWM_PERIOD / 2U);   /* 50 % */

        for (uint32_t i = 0; i < 20U; ++i)
        {
            HAL_Delay(100);
            enc_r_raw   = (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);
            enc_r_delta = (int16_t)(enc_r_raw - enc_r_prev_c);
            enc_r_prev_c = enc_r_raw;
            if (enc_r_delta >= 0)
                retreating_r = 0;
            /* Breakpoint here: enc_r_delta must be < 0 */
        }

        Motor_Right_Brake();
        HAL_Delay(500);
        enc_r_ccw_ok = retreating_r;
        /* PASS criterion: enc_r_ccw_ok == 1
         * If enc_r_ccw_ok == 0 but enc_r_cw_ok == 1: check CHB polarity (PB3). */
    }

    /* ----- 5d: Resolution — ticks accumulated over 5 s at 50 % -------- */
    /*                                                                       */
    /*  Same formula as Test 2d:                                            */
    /*    RPM = (enc_r_ticks_5s / 5) / 1856 * 60                          */
    /*  Expected: same plausible range as left motor (10–25 RPM).          */
    {
        uint16_t enc_r_start_d = (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);

        Motor_Right_Forward();
        Motor_Right_SetDuty(MOTOR_PWM_PERIOD / 2U);   /* 50 % */
        HAL_Delay(5000);

        Motor_Right_Brake();
        uint16_t enc_r_end_d = (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);

        enc_r_ticks_5s = (int32_t)enc_r_end_d - (int32_t)enc_r_start_d;
        /* Breakpoint here: compare enc_r_ticks_5s with enc_ticks_5s (Test 2d).
         * Both motors at 50 % duty should yield similar tick counts (±15 %). */

        HAL_Delay(1000);
    }

    /* All encoder sub-tests complete.
     * enc_r_at_rest_ok, enc_r_cw_ok, enc_r_ccw_ok should all be 1.
     * enc_r_ticks_5s should be close to enc_ticks_5s from Test 2d. */

    /* ================================================================== */
    /*  All tests complete — both motors braked, safe state               */
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
