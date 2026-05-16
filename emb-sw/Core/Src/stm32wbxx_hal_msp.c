/**
 * @file    stm32wbxx_hal_msp.c
 * @brief   MSP callbacks for system-level and BLE-stack peripherals.
 *
 * Contains only the MSP callbacks needed by the STM32WB BLE stack and
 * HAL system layer (HSEM, IPCC, RTC).
 *
 * Robot-peripheral MSP initialisation (USART1, TIM1/2/16, LPTIM1, ADC1)
 * is performed inline inside each Periph_xxx_Init() function in
 * periph_init.c so that all hardware setup remains in one place.
 *
 * Copyright (c) 2021 STMicroelectronics.  All rights reserved.
 * Licensed under the terms found in the LICENSE file in the root directory.
 */

#include "main.h"

/**
 * @brief Global MSP initialisation.
 *        Enables the hardware semaphore clock and its IRQ for the BLE
 *        dual-core synchronisation mechanism.
 */
void HAL_MspInit(void)
{
    __HAL_RCC_HSEM_CLK_ENABLE();

    HAL_NVIC_SetPriority(HSEM_IRQn, 0, 0);
    HAL_NVIC_EnableIRQ(HSEM_IRQn);
}

/**
 * @brief IPCC MSP initialisation.
 *        Enables the inter-processor communication controller clock used
 *        by the BLE transport layer.
 * @param hipcc  IPCC handle pointer (unused beyond instance check).
 */
void HAL_IPCC_MspInit(IPCC_HandleTypeDef *hipcc)
{
    if (hipcc->Instance == IPCC)
    {
        __HAL_RCC_IPCC_CLK_ENABLE();
    }
}

/**
 * @brief IPCC MSP de-initialisation.
 * @param hipcc  IPCC handle pointer.
 */
void HAL_IPCC_MspDeInit(IPCC_HandleTypeDef *hipcc)
{
    if (hipcc->Instance == IPCC)
    {
        __HAL_RCC_IPCC_CLK_DISABLE();
    }
}

/**
 * @brief RTC MSP initialisation.
 *        Selects LSE as the RTC kernel clock and enables the RTC peripheral
 *        and APB clocks.  Called by the BLE stack to maintain the RTC
 *        time-base used for connection event scheduling.
 * @param hrtc  RTC handle pointer.
 */
void HAL_RTC_MspInit(RTC_HandleTypeDef *hrtc)
{
    RCC_PeriphCLKInitTypeDef PeriphClkInitStruct = {0};

    if (hrtc->Instance == RTC)
    {
        PeriphClkInitStruct.PeriphClockSelection = RCC_PERIPHCLK_RTC;
        PeriphClkInitStruct.RTCClockSelection    = RCC_RTCCLKSOURCE_LSE;
        if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInitStruct) != HAL_OK)
        {
            Error_Handler();
        }

        __HAL_RCC_RTC_ENABLE();
        __HAL_RCC_RTCAPB_CLK_ENABLE();
    }
}

/**
 * @brief RTC MSP de-initialisation.
 * @param hrtc  RTC handle pointer.
 */
void HAL_RTC_MspDeInit(RTC_HandleTypeDef *hrtc)
{
    if (hrtc->Instance == RTC)
    {
        __HAL_RCC_RTC_DISABLE();
        __HAL_RCC_RTCAPB_CLK_DISABLE();
    }
}
