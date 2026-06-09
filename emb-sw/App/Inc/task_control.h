#ifndef TASK_CONTROL_H
#define TASK_CONTROL_H

#include <stdint.h>

typedef struct {
    float pitch_deg;
    float accel_x_g;
    float accel_y_g;
    float accel_z_g;
    float gyro_x_dps;
    float gyro_y_dps;
    float gyro_z_dps;
    float drive_output;    /* CBC angle PID output [-1..+1] */
    /* Calibration fields — valid only when calib_active == 1 */
    float   vel_l_rpm;
    float   vel_r_rpm;
    uint8_t calib_phase;
    uint8_t calib_active;  /* 1 = calibration sequence running */
} ControlState_t;

void Task_control_Init(void);
void Task_control_GetState(ControlState_t *out);
void Task_control_SetBalanceGains(uint8_t loop_id, float kp, float ki, float kd);
void Task_control_StartCalib(void);
void Task_control_AbortCalib(void);

#endif
