/**
  ******************************************************************************
  * @file    task_sensors.h
  * @brief   IMU sensor task — reads ISM330DHCX, estimates pitch angle.
  ******************************************************************************
  */
#ifndef TASK_SENSORS_H
#define TASK_SENSORS_H

#ifdef __cplusplus
extern "C" {
#endif

void  Sensors_Init(void);          /* creates the sensor task */
float Sensors_GetPitchDeg(void);   /* latest estimated pitch in degrees */

#ifdef __cplusplus
}
#endif

#endif /* TASK_SENSORS_H */
