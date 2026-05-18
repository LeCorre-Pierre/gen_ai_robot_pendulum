/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    stm32wbxx_hal_timebase_tim.c
  * @brief   HAL time base sourced from TIM17 (1 ms).
  *
  *          TIM2 is reserved for the right encoder (QEI).
  *          TIM17 is the only remaining 16-bit timer not used by encoders or
  *          motor PWM, so it is used here as the HAL tick source when FreeRTOS
  *          owns the SysTick.
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2025 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */

/* Includes ------------------------------------------------------------------*/
#include "stm32wbxx_hal.h"

/* Private variables ---------------------------------------------------------*/
TIM_HandleTypeDef htim17;

/**
  * @brief  Configures TIM17 as the HAL time base (1 ms tick).
  * @note   TIM17 is on APB2. IRQ vector is TIM1_TRG_COM_TIM17_IRQn (shared
  *         with TIM1 trigger/commutation on STM32WB).
  * @param  TickPriority  NVIC priority for the TIM17 update interrupt.
  * @retval HAL status
  */
HAL_StatusTypeDef HAL_InitTick(uint32_t TickPriority)
{
  uint32_t          uwTimclock;
  uint32_t          uwPrescalerValue;
  HAL_StatusTypeDef status;

  /* TIM17 is clocked from APB2 */
  uwTimclock = HAL_RCC_GetPCLK2Freq();

  /* Prescaler: counter runs at 1 MHz */
  uwPrescalerValue = (uwTimclock / 1000000U) - 1U;

  __HAL_RCC_TIM17_CLK_ENABLE();

  htim17.Instance               = TIM17;
  htim17.Init.Period            = (1000000U / 1000U) - 1U; /* 1 ms */
  htim17.Init.Prescaler         = uwPrescalerValue;
  htim17.Init.ClockDivision     = 0U;
  htim17.Init.CounterMode       = TIM_COUNTERMODE_UP;
  htim17.Init.RepetitionCounter = 0U;

  status = HAL_TIM_Base_Init(&htim17);
  if (status != HAL_OK)
    return status;

  status = HAL_TIM_Base_Start_IT(&htim17);
  if (status != HAL_OK)
    return status;

  if (TickPriority < (1UL << __NVIC_PRIO_BITS))
  {
    HAL_NVIC_SetPriority(TIM1_TRG_COM_TIM17_IRQn, TickPriority, 0U);
    HAL_NVIC_EnableIRQ(TIM1_TRG_COM_TIM17_IRQn);
    uwTickPrio = TickPriority;
  }
  else
  {
    status = HAL_ERROR;
  }

  return status;
}

/**
  * @brief  Suspend HAL tick by disabling the TIM17 update interrupt.
  */
void HAL_SuspendTick(void)
{
  __HAL_TIM_DISABLE_IT(&htim17, TIM_IT_UPDATE);
}

/**
  * @brief  Resume HAL tick by re-enabling the TIM17 update interrupt.
  */
void HAL_ResumeTick(void)
{
  __HAL_TIM_ENABLE_IT(&htim17, TIM_IT_UPDATE);
}

/**
  * @brief  Period elapsed callback — drives HAL_IncTick().
  */
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
  if (htim->Instance == TIM17)
    HAL_IncTick();
}
