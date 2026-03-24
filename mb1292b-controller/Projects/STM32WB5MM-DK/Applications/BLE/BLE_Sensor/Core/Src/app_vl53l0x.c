/* USER CODE BEGIN Header */
/**
  ******************************************************************************
 * @file    app_vl53l0x.c
 * @author  MCD Application Team
 * @brief   Proximity Application — multi-screen display (distance / IMU / AHRS)
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
#include "app_entry.h"

/* Private defines -----------------------------------------------------------*/
#define PROXIMITY_UPDATE_PERIOD  (uint32_t)(0.5*1000*1000/CFG_TS_TICK_VAL) /* 500 ms */
#define DISTANCE_MAX_PROXIMITY   2000   /* mm */
#define PROXIMITY_I2C_ADDRESS    0x53U
#define SCREEN_COUNT             3      /* 0=distance, 1=IMU brut, 2=AHRS fusion */

/* Private variables ---------------------------------------------------------*/
VL53L0X_Dev_t UserDev =
{
  .I2cHandle = &hbus_i2c3,
  .I2cDevAddr = PROXIMITY_I2C_ADDRESS
};

uint8_t VL53L0X_PROXIMITY_Update_Timer_Id;

static uint8_t    screen_mode = 0;
static FusionAhrs fusionAhrs;

/* Private function prototypes -----------------------------------------------*/
static void VL53L0X_PROXIMITY_Update_Timer_Callback(void);
static void Screen_Distance(void);
static void Screen_IMURaw(const MOTION_SENSOR_Axes_t *acc, const MOTION_SENSOR_Axes_t *gyro);
static void Screen_AHRSFusion(void);

/* ---------------------------------------------------------------------------*/

/**
  * @brief  VL53L0X proximity sensor + AHRS Initialization.
  */
void VL53L0X_PROXIMITY_Init(void)
{
  uint16_t vl53l0x_id = 0;
  VL53L0X_DeviceInfo_t VL53L0X_DeviceInfo;

  STM32WB5MM_DK_I2C_Init();

  memset(&VL53L0X_DeviceInfo, 0, sizeof(VL53L0X_DeviceInfo_t));

  if (VL53L0X_ERROR_NONE == VL53L0X_GetDeviceInfo(&UserDev, &VL53L0X_DeviceInfo))
  {
    if (VL53L0X_ERROR_NONE == VL53L0X_RdWord(&UserDev, VL53L0X_REG_IDENTIFICATION_MODEL_ID, (uint16_t *)&vl53l0x_id))
    {
      if (vl53l0x_id == VL53L0X_ID)
      {
        if (VL53L0X_ERROR_NONE == VL53L0X_DataInit(&UserDev))
        {
          UserDev.Present = 1;
          SetupSingleShot(&UserDev);
        }
        else { while(1){} }
      }
    }
    else { while(1){} }
  }
  else { while(1){} }

  /* Init AHRS Fusion (6-DOF : accel + gyro, pas de magnétomètre) */
  FusionAhrsInitialise(&fusionAhrs);
  const FusionAhrsSettings fusionSettings = {
      .convention            = FusionConventionNwu,
      .gain                  = 0.5f,
      .gyroscopeRange        = 500.0f,  /* ISM330DHCX ±500 dps */
      .accelerationRejection = 10.0f,
      .magneticRejection     = 10.0f,
      .recoveryTriggerPeriod = 10,      /* 5 s à 2 Hz */
  };
  FusionAhrsSetSettings(&fusionAhrs, &fusionSettings);

  UTIL_SEQ_RegTask(1<<CFG_TASK_GET_MEASURE_TOF_ID, UTIL_SEQ_RFU, VL53L0X_PROXIMITY_PrintValue);
  HW_TS_Create(CFG_TIM_PROC_ID_ISR,
               &VL53L0X_PROXIMITY_Update_Timer_Id,
               hw_ts_Repeated,
               VL53L0X_PROXIMITY_Update_Timer_Callback);
}

void VL53L0X_Start_Measure(void)
{
  HW_TS_Start(VL53L0X_PROXIMITY_Update_Timer_Id, PROXIMITY_UPDATE_PERIOD);
}

void VL53L0X_Stop_Measure(void)
{
  HW_TS_Stop(VL53L0X_PROXIMITY_Update_Timer_Id);
}

/**
  * @brief  Cycle to the next display screen (appelé par le bouton B1).
  */
void VL53L0X_NextScreen(void)
{
  screen_mode = (screen_mode + 1) % SCREEN_COUNT;
  /* Redessine immédiatement pour feedback visuel instantané */
  UTIL_SEQ_SetTask(1<<CFG_TASK_GET_MEASURE_TOF_ID, CFG_SCH_PRIO_0);
}

static void VL53L0X_PROXIMITY_Update_Timer_Callback(void)
{
  UTIL_SEQ_SetTask(1<<CFG_TASK_GET_MEASURE_TOF_ID, CFG_SCH_PRIO_0);
}

/**
  * @brief  Get distance from VL53L0X proximity sensor.
  * @retval Distance in mm
  */
uint16_t VL53L0X_PROXIMITY_GetDistance(void)
{
  VL53L0X_RangingMeasurementData_t RangingMeasurementData;
  VL53L0X_PerformSingleRangingMeasurement(&UserDev, &RangingMeasurementData);
  return RangingMeasurementData.RangeMilliMeter;
}

/**
  * @brief  Tâche principale : met à jour l'AHRS et affiche l'écran actif.
  */
void VL53L0X_PROXIMITY_PrintValue(void)
{
  MOTION_SENSOR_Axes_t acc, gyro;

  /* Lecture IMU — toujours, pour garder le filtre AHRS à jour */
  BSP_MOTION_SENSOR_GetAxes(MOTION_SENSOR_ISM330DHCX_0, MOTION_ACCELERO, &acc);
  BSP_MOTION_SENSOR_GetAxes(MOTION_SENSOR_ISM330DHCX_0, MOTION_GYRO,     &gyro);

  FusionVector accelerometer;
  accelerometer.axis.x = (float)acc.x  / 1000.0f;   /* mg → g   */
  accelerometer.axis.y = (float)acc.y  / 1000.0f;
  accelerometer.axis.z = (float)acc.z  / 1000.0f;

  FusionVector gyroscope;
  gyroscope.axis.x = (float)gyro.x / 1000.0f;        /* mdps → dps */
  gyroscope.axis.y = (float)gyro.y / 1000.0f;
  gyroscope.axis.z = (float)gyro.z / 1000.0f;

  FusionAhrsUpdateNoMagnetometer(&fusionAhrs, gyroscope, accelerometer, 0.5f);

  /* Affichage */
  BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);
  UTIL_LCD_SetFont(&Font12);

  switch (screen_mode)
  {
    case 0: Screen_Distance();            break;
    case 1: Screen_IMURaw(&acc, &gyro);  break;
    case 2: Screen_AHRSFusion();          break;
    default: break;
  }

  BSP_LCD_Refresh(0);

  /* LED RGB — indicateur tilt AHRS (luminosité minimale 0.02%)
   * BLUE  : convergence initiale  GREEN : |pitch| ≤ 15°
   * ORANGE: 15–30°                RED   : > 30°
   */
  {
    const FusionAhrsFlags flags = FusionAhrsGetFlags(&fusionAhrs);
    const float pitch    = FusionQuaternionToEuler(FusionAhrsGetQuaternion(&fusionAhrs)).angle.pitch;
    const float absPitch = (pitch < 0.0f) ? -pitch : pitch;

    aPwmLedGsData_TypeDef gs = {PWM_LED_GSDATA_OFF, PWM_LED_GSDATA_OFF, PWM_LED_GSDATA_OFF};

    if (flags.initialising)
    {
      gs[PWM_LED_BLUE]  = PWM_LED_GSDATA_0_02;
    }
    else if (absPitch <= 15.0f)
    {
      gs[PWM_LED_GREEN] = PWM_LED_GSDATA_0_02;
    }
    else if (absPitch <= 30.0f)
    {
      gs[PWM_LED_RED]   = PWM_LED_GSDATA_0_02;
      gs[PWM_LED_GREEN] = PWM_LED_GSDATA_0_02;
    }
    else
    {
      gs[PWM_LED_RED]   = PWM_LED_GSDATA_0_02;
    }

    LED_On(gs);
  }
}

/* ---------------------------------------------------------------------------
 * Écran 0 — Distance VL53L0X
 * ---------------------------------------------------------------------------*/
static void Screen_Distance(void)
{
  char distLine[22];
  char statusLine[22];
  uint16_t prox_value = VL53L0X_PROXIMITY_GetDistance();

  UTIL_LCD_DisplayStringAt(0, 2, (uint8_t *)"-- Distance --", CENTER_MODE);

  if (prox_value < DISTANCE_MAX_PROXIMITY)
  {
    uint16_t distance = prox_value / 10;
    snprintf(distLine,   sizeof(distLine),   "  Distance: %3d cm", distance);
    if (distance <= 30)
      snprintf(statusLine, sizeof(statusLine), " !! TRES PROCHE !!");
    else
      snprintf(statusLine, sizeof(statusLine), "    -- OK :) --   ");
  }
  else
  {
    snprintf(distLine,   sizeof(distLine),   "  Distance > 200cm");
    snprintf(statusLine, sizeof(statusLine), "  ...Trop loin... ");
  }

  UTIL_LCD_DisplayStringAt(0, 28, (uint8_t *)distLine,   LEFT_MODE);
  UTIL_LCD_DisplayStringAt(0, 46, (uint8_t *)statusLine, LEFT_MODE);
}

/* ---------------------------------------------------------------------------
 * Écran 1 — IMU brut (valeurs mg et dps)
 * ---------------------------------------------------------------------------*/
static void Screen_IMURaw(const MOTION_SENSOR_Axes_t *acc, const MOTION_SENSOR_Axes_t *gyro)
{
  char line[32];

  UTIL_LCD_DisplayStringAt(0, 2,  (uint8_t *)"-- IMU Monitor --", CENTER_MODE);
  UTIL_LCD_DisplayStringAt(0, 16, (uint8_t *)"Acc (mg):",         LEFT_MODE);
  snprintf(line, sizeof(line), "%5d|%5d|%5d",
           (int)acc->x, (int)acc->y, (int)acc->z);
  UTIL_LCD_DisplayStringAt(0, 28, (uint8_t *)line, LEFT_MODE);

  UTIL_LCD_DisplayStringAt(0, 40, (uint8_t *)"Gyro (dps):",       LEFT_MODE);
  snprintf(line, sizeof(line), "%5d|%5d|%5d",
           (int)(gyro->x / 1000), (int)(gyro->y / 1000), (int)(gyro->z / 1000));
  UTIL_LCD_DisplayStringAt(0, 52, (uint8_t *)line, LEFT_MODE);
}

/* ---------------------------------------------------------------------------
 * Écran 2 — Fusion de capteur AHRS (angles Euler + barre pitch)
 * ---------------------------------------------------------------------------*/
static void Screen_AHRSFusion(void)
{
  char line[32];

  const FusionEuler  euler = FusionQuaternionToEuler(FusionAhrsGetQuaternion(&fusionAhrs));
  const FusionAhrsFlags flags = FusionAhrsGetFlags(&fusionAhrs);

  UTIL_LCD_DisplayStringAt(0, 2,
      (uint8_t *)(flags.initialising ? "-- AHRS  INIT  --" : "-- AHRS Fusion --"),
      CENTER_MODE);

  snprintf(line, sizeof(line), "Pitch:%+7.1f deg", euler.angle.pitch);
  UTIL_LCD_DisplayStringAt(0, 16, (uint8_t *)line, LEFT_MODE);

  snprintf(line, sizeof(line), "Roll: %+7.1f deg", euler.angle.roll);
  UTIL_LCD_DisplayStringAt(0, 28, (uint8_t *)line, LEFT_MODE);

  snprintf(line, sizeof(line), "Yaw:  %+7.1f deg", euler.angle.yaw);
  UTIL_LCD_DisplayStringAt(0, 40, (uint8_t *)line, LEFT_MODE);

  /* Barre visuelle pitch ±45° */
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
}
