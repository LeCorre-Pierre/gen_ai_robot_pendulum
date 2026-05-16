/**
 * @file    main.c
 * @brief   Application entry point — bring-up test sequence.
 *
 * Sequential tests, designed for step-through debugging:
 *   1. Left encoder  : TIM1 (PD14/PD15) — tourner la roue gauche à la main.
 *   2. Right encoder : TIM2 (PA15/PB3)  — tourner la roue droite à la main.
 *   3. PWM ramp      : left motor 0 % → 100 % in 11 steps of 500 ms each.
 *   4. Direction     : forward (DIR=LOW) 2 s, then reverse (DIR=HIGH) 2 s.
 *
 * All result variables are volatile — set a breakpoint anywhere and
 * inspect them in the debugger without worrying about optimisation.
 *
 * Copyright (c) 2021 STMicroelectronics.  All rights reserved.
 * Licensed under the terms found in the LICENSE file in the root directory.
 */

#include "main.h"
#include <stdio.h>


/* -------------------------------------------------------------------------
 * Private function prototypes
 * ------------------------------------------------------------------------- */
static void SystemClock_Config(void);
static void PeriphCommonClock_Config(void);

/* =========================================================================
 * Motor helpers — LEFT (LPTIM1 PWM, CMPOK synchronisation required)
 * ========================================================================= */

static void Motor_Left_SetDuty(uint32_t duty)
{
    __HAL_LPTIM_COMPARE_SET(&hlptim1, duty);
    while (!__HAL_LPTIM_GET_FLAG(&hlptim1, LPTIM_FLAG_CMPOK)) {}
    __HAL_LPTIM_CLEAR_FLAG(&hlptim1, LPTIM_FLAG_CMPOK);
}

static void Motor_Left_Forward(void)
{
    HAL_GPIO_WritePin(MOTOR_LEFT_DIR_PORT,   MOTOR_LEFT_DIR_PIN,   GPIO_PIN_RESET);
    HAL_GPIO_WritePin(MOTOR_LEFT_BRAKE_PORT, MOTOR_LEFT_BRAKE_PIN, GPIO_PIN_RESET);
}

static void Motor_Left_Reverse(void)
{
    HAL_GPIO_WritePin(MOTOR_LEFT_DIR_PORT,   MOTOR_LEFT_DIR_PIN,   GPIO_PIN_SET);
    HAL_GPIO_WritePin(MOTOR_LEFT_BRAKE_PORT, MOTOR_LEFT_BRAKE_PIN, GPIO_PIN_RESET);
}

static void Motor_Left_Brake(void)
{
    Motor_Left_SetDuty(0);
    HAL_GPIO_WritePin(MOTOR_LEFT_BRAKE_PORT, MOTOR_LEFT_BRAKE_PIN, GPIO_PIN_SET);
    HAL_GPIO_WritePin(MOTOR_LEFT_DIR_PORT,   MOTOR_LEFT_DIR_PIN,   GPIO_PIN_RESET);
}

/* =========================================================================
 * Motor helpers — RIGHT (TIM16 PWM, no CMPOK synchronisation needed)
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
    HAL_Init();
    SystemClock_Config();
    PeriphCommonClock_Config();
    Periph_Init_All();

    /* test_step tracks the active test for live debugger inspection. */
    volatile uint8_t test_step = 0;

    /* --- Test 1: Left encoder ----------------------------------------- */
    volatile uint16_t enc_raw   = 0;   /* TIM1_CNT — position absolue     */
    volatile int16_t  enc_delta = 0;   /* ticks depuis le dernier sample  */

    /* --- Test 2: Right encoder ---------------------------------------- */
    volatile uint16_t enc_r_raw   = 0;
    volatile int16_t  enc_r_delta = 0;

    /* --- Test 3: IMU -------------------------------------------------- */
    volatile uint8_t  imu_i2c_ok   = 0;   /* 1 si I2C3 répond à 0x6B     */
    volatile uint8_t  imu_who_am_i = 0;   /* registre WHO_AM_I (attendu 0x6B) */
    volatile int16_t  imu_ax = 0, imu_ay = 0, imu_az = 0;  /* accél (LSB) */
    volatile int16_t  imu_gx = 0, imu_gy = 0, imu_gz = 0;  /* gyro  (LSB) */

    /* --- Test 4: PWM ramp --------------------------------------------- */
    volatile uint32_t ramp_duty_cmp = 0;

    /* --- Test 5: Direction -------------------------------------------- */
    volatile uint8_t dir_forward = 0;
    volatile uint8_t dir_reverse = 0;

    /* ================================================================== */
    /*  TEST 1 — LEFT encoder (TIM1 · PD14=CHA · PD15=CHB)               */
    /*                                                                     */
    /*  Tourner la roue gauche à la main pendant l'exécution.            */
    /*  Poser un breakpoint dans la boucle et observer :                  */
    /*    enc_raw   : position absolue (0–65535, overflow normal)         */
    /*    enc_delta : ticks depuis le sample précédent                    */
    /*       > 0 → sens CW    < 0 → sens CCW    = 0 → roue immobile      */
    /*  Un tour complet doit donner |delta cumulé| ≈ 1856 ticks.         */
    /* ================================================================== */


    /* ================================================================== */
    /*  TEST 2 — RIGHT encoder (TIM2 · PA15=CHA · PB3=CHB ⚠ SWO off)    */
    /*                                                                     */
    /*  Même principe que Test 1 — tourner la roue droite à la main.     */
    /* ================================================================== */


    /* ================================================================== */
    /*  TEST 3 — IMU ISM330DHCX (I2C3 · PB13=SCL · PB11=SDA · 0x6B)    */
    /*                                                                     */
    /*  Watch: imu_i2c_ok, imu_who_am_i, imu_ax/ay/az, imu_gx/gy/gz    */
    /*  Robot posé à plat : az ≈ ±16000 LSB, ax ≈ ay ≈ 0               */
    /*  Incliner le robot : az change, ax/ay varient selon l'axe         */
    /*  Gyro immobile     : gx/gy/gz ≈ 0 (bruit < ±100 LSB)            */
    /* ================================================================== */
    test_step = 3;

#define ISM330DHCX_ADDR     (0x6BU << 1)
#define ISM330DHCX_WHO_AM_I  0x0FU
#define ISM330DHCX_CTRL1_XL  0x10U   /* accel config */
#define ISM330DHCX_CTRL2_G   0x11U   /* gyro  config */
#define ISM330DHCX_OUTX_L_G  0x22U   /* gyro  output, 6 bytes */
#define ISM330DHCX_OUTX_L_A  0x28U   /* accel output, 6 bytes */

    /* --- 3a: vérifier présence I2C ------------------------------------ */
    imu_i2c_ok = (HAL_I2C_IsDeviceReady(&hi2c3, ISM330DHCX_ADDR, 3, 100) == HAL_OK)
                 ? 1U : 0U;
    /* PASS: imu_i2c_ok == 1 — sinon vérifier PB13/PB11 et pull-ups */

    /* --- 3b: lire WHO_AM_I -------------------------------------------- */
    {
        uint8_t reg = 0;
        HAL_I2C_Mem_Read(&hi2c3, ISM330DHCX_ADDR,
                         ISM330DHCX_WHO_AM_I, I2C_MEMADD_SIZE_8BIT,
                         &reg, 1, 100);
        imu_who_am_i = reg;
        /* PASS: imu_who_am_i == 0x6B */
    }

    /* --- 3c: configurer et lire en boucle ----------------------------- */
    if (imu_i2c_ok)
    {
        uint8_t cfg;

        /* Accel: ODR = 208 Hz, FS = ±2 g */
        cfg = 0x50U;
        HAL_I2C_Mem_Write(&hi2c3, ISM330DHCX_ADDR,
                          ISM330DHCX_CTRL1_XL, I2C_MEMADD_SIZE_8BIT,
                          &cfg, 1, 100);

        /* Gyro: ODR = 208 Hz, FS = ±250 dps */
        cfg = 0x50U;
        HAL_I2C_Mem_Write(&hi2c3, ISM330DHCX_ADDR,
                          ISM330DHCX_CTRL2_G, I2C_MEMADD_SIZE_8BIT,
                          &cfg, 1, 100);

        HAL_Delay(10);   /* attendre le premier sample */

        while (1)
        {
            uint8_t buf[6];
            char    disp[22];

            HAL_I2C_Mem_Read(&hi2c3, ISM330DHCX_ADDR,
                             ISM330DHCX_OUTX_L_G, I2C_MEMADD_SIZE_8BIT,
                             buf, 6, 10);
            imu_gx = (int16_t)((uint16_t)buf[1] << 8 | buf[0]);
            imu_gy = (int16_t)((uint16_t)buf[3] << 8 | buf[2]);
            imu_gz = (int16_t)((uint16_t)buf[5] << 8 | buf[4]);

            HAL_I2C_Mem_Read(&hi2c3, ISM330DHCX_ADDR,
                             ISM330DHCX_OUTX_L_A, I2C_MEMADD_SIZE_8BIT,
                             buf, 6, 10);
            imu_ax = (int16_t)((uint16_t)buf[1] << 8 | buf[0]);
            imu_ay = (int16_t)((uint16_t)buf[3] << 8 | buf[2]);
            imu_az = (int16_t)((uint16_t)buf[5] << 8 | buf[4]);

            /* Update OLED — Font8: 6px wide × 8px tall, 21 chars × 8 lines */
            snprintf(disp, sizeof(disp), "Ax: %6d", (int)imu_ax);
            UTIL_LCD_DisplayStringAt(0, LINE(1), (uint8_t *)disp, LEFT_MODE);
            snprintf(disp, sizeof(disp), "Ay: %6d", (int)imu_ay);
            UTIL_LCD_DisplayStringAt(0, LINE(2), (uint8_t *)disp, LEFT_MODE);
            snprintf(disp, sizeof(disp), "Az: %6d", (int)imu_az);
            UTIL_LCD_DisplayStringAt(0, LINE(3), (uint8_t *)disp, LEFT_MODE);
            snprintf(disp, sizeof(disp), "Gx: %6d", (int)imu_gx);
            UTIL_LCD_DisplayStringAt(0, LINE(4), (uint8_t *)disp, LEFT_MODE);
            snprintf(disp, sizeof(disp), "Gy: %6d", (int)imu_gy);
            UTIL_LCD_DisplayStringAt(0, LINE(5), (uint8_t *)disp, LEFT_MODE);
            snprintf(disp, sizeof(disp), "Gz: %6d", (int)imu_gz);
            UTIL_LCD_DisplayStringAt(0, LINE(6), (uint8_t *)disp, LEFT_MODE);
            BSP_LCD_Refresh(0);

            HAL_Delay(10);
            /* <<< BREAKPOINT ICI — bouger la carte et observer imu_ax/ay/az >>> */
        }
    }

    /* ================================================================== */
    /*  TEST 4 — PWM ramp: 0 % → 100 % in 11 steps of 500 ms            */
    /*                                                                     */
    /*  Watch: ramp_duty_cmp                                              */
    /*  Expected: left motor spins up progressively over ~5.5 s          */
    /* ================================================================== */
    test_step = 4;

    Motor_Left_Forward();

    for (uint32_t step = 0; step <= 10U; ++step)
    {
        ramp_duty_cmp = (step * MOTOR_PWM_PERIOD) / 10U;
        Motor_Left_SetDuty(ramp_duty_cmp);
        HAL_Delay(500);
    }

    HAL_Delay(2000);
    Motor_Left_Brake();
    HAL_Delay(1000);

    /* ================================================================== */
    /*  TEST 4 — Motor direction                                          */
    /*                                                                     */
    /*  Watch: dir_forward, dir_reverse, enc_raw                         */
    /*  Expected: encoder increments forward, decrements reverse          */
    /* ================================================================== */
    test_step = 5;

    dir_forward = 1;
    Motor_Left_Forward();
    Motor_Left_SetDuty(MOTOR_PWM_PERIOD / 2U);
    HAL_Delay(2000);

    Motor_Left_Brake();
    dir_forward = 0;
    HAL_Delay(1000);

    dir_reverse = 1;
    Motor_Left_Reverse();
    Motor_Left_SetDuty(MOTOR_PWM_PERIOD / 2U);
    HAL_Delay(2000);

    Motor_Left_Brake();
    dir_reverse = 0;
    HAL_Delay(500);

    /* ================================================================== */
    /*  All tests complete — both motors braked, safe state               */
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
        Error_Handler();

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
        Error_Handler();
}

static void PeriphCommonClock_Config(void)
{
    /* No shared peripheral clocks required for this bring-up. */
}

/* =========================================================================
 * Error handler
 * ========================================================================= */

void Error_Handler(void)
{
    __disable_irq();
    while (1) {}
}
