#ifndef ANGLE_ESTIMATOR_H
#define ANGLE_ESTIMATOR_H

typedef struct {
    float angle_deg;
    float alpha;   /* gyro weight (0..1), typically 0.98 */
} AngleEstimator_t;

void  AngleEstimator_Init(AngleEstimator_t *ae, float alpha);
float AngleEstimator_Update(AngleEstimator_t *ae,
                             float accel_x_g, float accel_z_g,
                             float gyro_y_dps, float dt_s);

#endif /* ANGLE_ESTIMATOR_H */
