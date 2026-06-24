#include "angle_estimator.h"
#include <math.h>

void AngleEstimator_Init(AngleEstimator_t *ae, float alpha)
{
    ae->alpha = alpha;
    ae->angle_deg = 0.0f;
}

float AngleEstimator_Update(AngleEstimator_t *ae,
                             float accel_x_g, float accel_z_g,
                             float gyro_y_dps, float dt_s)
{
    float accel_angle = atan2f(accel_x_g, accel_z_g) * (180.0f / 3.14159265f);
    ae->angle_deg = ae->alpha * (ae->angle_deg + gyro_y_dps * dt_s)
                  + (1.0f - ae->alpha) * accel_angle;
    return ae->angle_deg;
}
