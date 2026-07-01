/**
  ******************************************************************************
  * @file    task_sensors.h
  * @brief   IMU sensor task — reads ISM330DHCX, estimates pitch angle.
  ******************************************************************************
  */
#ifndef TASK_SENSORS_H
#define TASK_SENSORS_H

#include "imu.h"

#ifdef __cplusplus
extern "C" {
#endif

void  Sensors_Init(void);            /* creates the sensor task */
float Sensors_GetPitchDeg(void);     /* latest estimated pitch in degrees */
float Sensors_GetYawRateDps(void);   /* latest gyro_y reading (yaw rate) */
void  Sensors_GetImu(IMU_Data_t *out); /* latest raw IMU sample (for telemetry) */

#ifdef __cplusplus
}
#endif

#endif /* TASK_SENSORS_H */
