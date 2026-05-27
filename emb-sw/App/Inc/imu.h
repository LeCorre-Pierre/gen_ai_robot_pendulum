#ifndef IMU_H
#define IMU_H

#include <stdbool.h>

typedef struct {
    float accel_x_g;   /* BSP axis X  (g)   */
    float accel_y_g;   /* BSP axis Y  (g)   */
    float accel_z_g;   /* BSP axis Z  (g)   */
    float gyro_x_dps;  /* BSP axis X  (dps) */
    float gyro_y_dps;  /* BSP axis Y  (dps) */
    float gyro_z_dps;  /* BSP axis Z  (dps) */
} IMU_Data_t;

/* Call after BSP_MOTION_SENSOR_Init to configure ODR and full-scale. */
void IMU_Init(void);
bool IMU_Read(IMU_Data_t *data);

#endif /* IMU_H */
