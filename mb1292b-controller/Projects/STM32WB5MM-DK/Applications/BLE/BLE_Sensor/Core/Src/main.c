/**
 * @file    main.c
 * @brief   Application entry point for the MB1292B robot controller.
 *
 * Copyright (c) 2021 STMicroelectronics.  All rights reserved.
 * Licensed under the terms found in the LICENSE file in the root directory.
 */

#include "main.h"
#include "periph_init.h"

static void SystemClock_Config(void);
static void PeriphCommonClock_Config(void);

int main(void)
{
    HAL_Init();

    SystemClock_Config();
    PeriphCommonClock_Config();

    Periph_Init_All();

    while (1)
    {
    }
}

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
