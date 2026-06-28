/**
  ******************************************************************************
  * @file    task_sensors.c
  * @brief   IMU sensor task. Reads ISM330DHCX at 100 Hz and runs a
  *          complementary filter to estimate the pitch angle.
  *
  *          Axis mapping confirmed in CLAUDE.md (2026-05-26):
  *            pitch = AngleEstimator_Update(-accel_z_g, accel_y_g, -gyro_x_dps, dt)
  ******************************************************************************
  */
#include "main.h"
#include "cmsis_os.h"
#include "imu.h"
#include "angle_estimator.h"
#include "stm32wb5mm_dk_motion_sensors.h"
#include "task_sensors.h"

#define SENSOR_PERIOD_MS   10U          /* 100 Hz */
#define SENSOR_DT_S        0.010f

static volatile float    g_pitch_deg   = 0.0f;
static volatile float    g_yaw_dps     = 0.0f;
static AngleEstimator_t  ae;

static osThreadId_t SensorThreadId;
static const osThreadAttr_t SensorProcess_attr =
{
  .name       = "Sensors",
  .priority   = osPriorityAboveNormal,
  .stack_size = 1024U,
};

float Sensors_GetPitchDeg(void)    { return g_pitch_deg; }
float Sensors_GetYawRateDps(void)  { return g_yaw_dps;   }

static void SensorProcess(void *argument)
{
  IMU_Data_t imu;
  uint32_t   tick;
  UNUSED(argument);

  /* Bring up the IMU (BSP init configures the I2C3 bus) */
  BSP_MOTION_SENSOR_Init(MOTION_SENSOR_ISM330DHCX_0, MOTION_ACCELERO | MOTION_GYRO);
  IMU_Init();
  AngleEstimator_Init(&ae, 0.98f);

  tick = osKernelGetTickCount();
  for (;;)
  {
    tick += SENSOR_PERIOD_MS;
    osDelayUntil(tick);

    if (IMU_Read(&imu))
    {
      g_pitch_deg = AngleEstimator_Update(&ae,
                                          -imu.accel_z_g,   /* tilt axis  */
                                           imu.accel_y_g,   /* vertical   */
                                          -imu.gyro_x_dps,  /* pitch rate */
                                           SENSOR_DT_S);
      g_yaw_dps = imu.gyro_y_dps;
    }
  }
}

void Sensors_Init(void)
{
  SensorThreadId = osThreadNew(SensorProcess, NULL, &SensorProcess_attr);
}
