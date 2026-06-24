#include "imu.h"
#include "stm32wb5mm_dk_motion_sensors.h"

/* BSP_MOTION_SENSOR_Init is already called in main() before this.
 * IMU_Init only sets ODR and full-scale range. */
void IMU_Init(void)
{
    BSP_MOTION_SENSOR_SetOutputDataRate(MOTION_SENSOR_ISM330DHCX_0, MOTION_ACCELERO, 208.0f);
    BSP_MOTION_SENSOR_SetOutputDataRate(MOTION_SENSOR_ISM330DHCX_0, MOTION_GYRO,     208.0f);
    BSP_MOTION_SENSOR_SetFullScale(MOTION_SENSOR_ISM330DHCX_0, MOTION_ACCELERO, 2);   /* ±2 g   */
    BSP_MOTION_SENSOR_SetFullScale(MOTION_SENSOR_ISM330DHCX_0, MOTION_GYRO,     250); /* ±250 dps */
}

/* BSP returns mg for accel, mdps for gyro.
 * Axis mapping — verify with board orientation on robot:
 *   accel_x = forward/tilt axis (≈0 g upright, changes when tilted)
 *   accel_z = vertical axis     (≈1 g upright)
 *   gyro_y  = pitch rate        (positive = tipping forward)
 *   gyro_z  = yaw rate
 * Swap or negate fields here if the angle sign is wrong. */
bool IMU_Read(IMU_Data_t *data)
{
    MOTION_SENSOR_Axes_t accel, gyro;

    if (BSP_MOTION_SENSOR_GetAxes(MOTION_SENSOR_ISM330DHCX_0, MOTION_ACCELERO, &accel) != BSP_ERROR_NONE)
        return false;
    if (BSP_MOTION_SENSOR_GetAxes(MOTION_SENSOR_ISM330DHCX_0, MOTION_GYRO, &gyro) != BSP_ERROR_NONE)
        return false;

    data->accel_x_g  = accel.x * 0.001f;
    data->accel_y_g  = accel.y * 0.001f;
    data->accel_z_g  = accel.z * 0.001f;
    data->gyro_x_dps = gyro.x  * 0.001f;
    data->gyro_y_dps = gyro.y  * 0.001f;
    data->gyro_z_dps = gyro.z  * 0.001f;

    return true;
}
