/* USER CODE BEGIN Header */
/**
  ******************************************************************************
 * @file    app_vl53l0x.c
 * @author  MCD Application Team
 * @brief   Proximity Application
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2019-2021 STMicroelectronics.
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
#include "app_vl53l0x.h"
#include "stm32_seq.h"
#include "stm32wb5mm_dk.h"
#include "stm32wb5mm_dk_lcd.h"
#include "stm32_lcd.h"
#include "stm32wb5mm_dk_bus.h"

/* Private defines -----------------------------------------------------------*/ 
#define PROXIMITY_UPDATE_PERIOD       (uint32_t)(0.5*1000*1000/CFG_TS_TICK_VAL) /*500ms*/
#define DISTANCE_MAX_PROXIMITY        2000  /* 2m */

#define PROXIMITY_I2C_ADDRESS            0x53U

/* Private variables ---------------------------------------------------------*/   

/* Proximity */ 
VL53L0X_Dev_t UserDev =
{
  .I2cHandle = &hbus_i2c3,
  .I2cDevAddr = PROXIMITY_I2C_ADDRESS
};

uint8_t VL53L0X_PROXIMITY_Update_Timer_Id;

/* Private function prototypes -----------------------------------------------*/
static void VL53L0X_PROXIMITY_Update_Timer_Callback(void);

/**
  * @brief  VL53L0X proximity sensor Initialization.
  */
void VL53L0X_PROXIMITY_Init(void)
{
  uint16_t vl53l0x_id = 0; 
  VL53L0X_DeviceInfo_t VL53L0X_DeviceInfo;
  
  /* Initialize IO interface */
  STM32WB5MM_DK_I2C_Init();
  
  memset(&VL53L0X_DeviceInfo, 0, sizeof(VL53L0X_DeviceInfo_t));
  
  if (VL53L0X_ERROR_NONE == VL53L0X_GetDeviceInfo(&UserDev, &VL53L0X_DeviceInfo))
  {  
    if (VL53L0X_ERROR_NONE == VL53L0X_RdWord(&UserDev, VL53L0X_REG_IDENTIFICATION_MODEL_ID, (uint16_t *) &vl53l0x_id))
    {
      if (vl53l0x_id == VL53L0X_ID)
      {
        if (VL53L0X_ERROR_NONE == VL53L0X_DataInit(&UserDev))
        {
          UserDev.Present = 1;
          SetupSingleShot(&UserDev);
        }
        else
        { 
          while(1){}  // VL53L0X Time of Flight Failed to send its ID!
        }
      }
    }
    else
    {
      while(1){} // VL53L0X Time of Flight Failed to Initialize!
    }
  }
  else
  {
    while(1){} // VL53L0X Time of Flight Failed to get infos!
  } 
  UTIL_SEQ_RegTask( 1<<CFG_TASK_GET_MEASURE_TOF_ID, UTIL_SEQ_RFU, VL53L0X_PROXIMITY_PrintValue);
  /* Create timer to get the measure of TOF */
  HW_TS_Create(CFG_TIM_PROC_ID_ISR,
        &VL53L0X_PROXIMITY_Update_Timer_Id,
        hw_ts_Repeated,
        VL53L0X_PROXIMITY_Update_Timer_Callback);
}

               
void VL53L0X_Start_Measure(void)
{
  /* Start the timer used to update the proximity value */
  HW_TS_Start(VL53L0X_PROXIMITY_Update_Timer_Id, PROXIMITY_UPDATE_PERIOD);
}
  
void VL53L0X_Stop_Measure(void)
{
  /* Stop the timer used to update the proximity value */
  HW_TS_Stop(VL53L0X_PROXIMITY_Update_Timer_Id);
}  
        
/**
 * @brief  On timeout, trigger the task
 *         to update the proximity value
 * @param  None
 * @retval None
 */
static void VL53L0X_PROXIMITY_Update_Timer_Callback(void)
{
  UTIL_SEQ_SetTask(1<<CFG_TASK_GET_MEASURE_TOF_ID, CFG_SCH_PRIO_0);
}

/**
  * @brief  Get distance from VL53L0X proximity sensor.
  * @param  None
  * @retval Distance in mm
  */
uint16_t VL53L0X_PROXIMITY_GetDistance(void)
{
  VL53L0X_RangingMeasurementData_t RangingMeasurementData;
  
  VL53L0X_PerformSingleRangingMeasurement(&UserDev, &RangingMeasurementData);
  
  return RangingMeasurementData.RangeMilliMeter;  
}

/**
  * @brief  Print distance measure from VL53L0X proximity sensor on the OLED screen.
  * @param  None
  * @retval None
  */
void VL53L0X_PROXIMITY_PrintValue(void){
  char distLine[20];
  char statusLine[20];
  uint16_t prox_value = VL53L0X_PROXIMITY_GetDistance();

  /* Effacement de la zone dynamique (sous l'entete fixe) */
  BSP_LCD_FillRect(0, 0, 32, 128, 32, SSD1315_COLOR_BLACK);

  UTIL_LCD_SetFont(&Font12);

  if(prox_value < DISTANCE_MAX_PROXIMITY){
    uint16_t distance = prox_value / 10;
    sprintf(distLine, "  Distance: %3d cm", distance);

    if(distance <= 30){
      /* Zone 0-30 cm : tres proche, attention */
      strcpy(statusLine, " !! TRES PROCHE !!");
    } else {
      /* Zone 31-199 cm : distance normale */
      strcpy(statusLine, "    -- OK :) --   ");
    }
  } else {
    /* Zone > 200 cm : hors de portee */
    strcpy(distLine,   "  Distance > 200cm");
    strcpy(statusLine, "  ...Trop loin... ");
  }

  UTIL_LCD_DisplayStringAt(0, 32, (uint8_t *)distLine,   LEFT_MODE);
  UTIL_LCD_DisplayStringAt(0, 47, (uint8_t *)statusLine, LEFT_MODE);
  BSP_LCD_Refresh(0);
}

