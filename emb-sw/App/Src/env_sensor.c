#include "env_sensor.h"
#include "stm32wb5mm_dk_env_sensors.h"

void EnvSensor_Init(void)
{
    BSP_ENV_SENSOR_Init(ENV_SENSOR_STTS22H_0, ENV_TEMPERATURE);
}

float EnvSensor_GetTemperatureC(void)
{
    float temp;
    if (BSP_ENV_SENSOR_GetValue(ENV_SENSOR_STTS22H_0, ENV_TEMPERATURE, &temp) != BSP_ERROR_NONE) {
        return -999.0f;
    }
    return temp;
}
