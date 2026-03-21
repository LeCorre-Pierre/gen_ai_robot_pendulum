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
#include "stm32wb5mm_dk_motion_sensors.h"
#include "Fusion.h"

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

static FusionAhrs fusionAhrs;

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
  /* Init AHRS Fusion (6-DOF, pas de magnétomètre) */
  FusionAhrsInitialise(&fusionAhrs);
  const FusionAhrsSettings fusionSettings = {
      .convention             = FusionConventionNwu,
      .gain                   = 0.5f,
      .gyroscopeRange         = 500.0f,   /* ISM330DHCX ±500 dps */
      .accelerationRejection  = 10.0f,
      .magneticRejection      = 10.0f,
      .recoveryTriggerPeriod  = 10,       /* 5 s à 2 Hz (1/0.5 s) */
  };
  FusionAhrsSetSettings(&fusionAhrs, &fusionSettings);

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
  MOTION_SENSOR_Axes_t acc, gyro;
  char line[32];

  /* --- Lecture IMU --- */
  BSP_MOTION_SENSOR_GetAxes(MOTION_SENSOR_ISM330DHCX_0, MOTION_ACCELERO, &acc);
  BSP_MOTION_SENSOR_GetAxes(MOTION_SENSOR_ISM330DHCX_0, MOTION_GYRO,     &gyro);

  /* --- Conversion BSP → Fusion : mg→g, mdps→dps --- */
  FusionVector accelerometer;
  accelerometer.axis.x = (float)acc.x  / 1000.0f;
  accelerometer.axis.y = (float)acc.y  / 1000.0f;
  accelerometer.axis.z = (float)acc.z  / 1000.0f;

  FusionVector gyroscope;
  gyroscope.axis.x = (float)gyro.x / 1000.0f;
  gyroscope.axis.y = (float)gyro.y / 1000.0f;
  gyroscope.axis.z = (float)gyro.z / 1000.0f;

  /* --- Mise à jour AHRS (dt = 0.5 s, cadence du timer de démo) --- */
  FusionAhrsUpdateNoMagnetometer(&fusionAhrs, gyroscope, accelerometer, 0.5f);

  /* --- Angles Euler (degrés) --- */
  const FusionEuler euler = FusionQuaternionToEuler(FusionAhrsGetQuaternion(&fusionAhrs));

  /* --- Affichage OLED --- */
  BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);
  UTIL_LCD_SetFont(&Font12);

  /* Titre : indique "INIT" pendant la phase de convergence (3 s) */
  FusionAhrsFlags flags = FusionAhrsGetFlags(&fusionAhrs);
  UTIL_LCD_DisplayStringAt(0, 2,
      (uint8_t *)(flags.initialising ? "-- AHRS  INIT  --" : "-- AHRS Fusion --"),
      CENTER_MODE);

  /* Angles */
  snprintf(line, sizeof(line), "Pitch:%+7.1f deg", euler.angle.pitch);
  UTIL_LCD_DisplayStringAt(0, 16, (uint8_t *)line, LEFT_MODE);

  snprintf(line, sizeof(line), "Roll: %+7.1f deg", euler.angle.roll);
  UTIL_LCD_DisplayStringAt(0, 28, (uint8_t *)line, LEFT_MODE);

  snprintf(line, sizeof(line), "Yaw:  %+7.1f deg", euler.angle.yaw);
  UTIL_LCD_DisplayStringAt(0, 40, (uint8_t *)line, LEFT_MODE);

  /* Barre visuelle pitch ±45° : [--------|---------] */
  char bar[19];
  bar[0]  = '[';
  bar[17] = ']';
  bar[18] = '\0';
  memset(bar + 1, '-', 16);
  int pos = 8 + (int)(euler.angle.pitch / 45.0f * 8.0f);
  if (pos < 0)  pos = 0;
  if (pos > 15) pos = 15;
  bar[1 + pos] = '|';
  UTIL_LCD_DisplayStringAt(0, 52, (uint8_t *)bar, LEFT_MODE);

  BSP_LCD_Refresh(0);
}

