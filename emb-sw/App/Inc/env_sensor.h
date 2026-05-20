#ifndef ENV_SENSOR_H
#define ENV_SENSOR_H

void  EnvSensor_Init(void);
float EnvSensor_GetTemperatureC(void);  /* returns -999.f on error */

#endif /* ENV_SENSOR_H */
