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
    float target_vel_rpm;    /* effective velocity setpoint fed to CBC */
    float target_pitch_deg;  /* outer loop output → inner setpoint */
    float drive_output;      /* inner loop (angle PID) output [-1..+1] */
    float left_output;       /* left motor drive after yaw mix  */
    float right_output;      /* right motor drive after yaw mix */
    float vel_l_rpm;
    float vel_r_rpm;
    float pos_cm;            /* accumulated position from origin (cm) */
    float pos_sp_cm;         /* position setpoint (cm) */
    float pos_vel_sp_rpm;    /* velocity setpoint from position PID (RPM) */
    uint8_t ctrl_mode;       /* 0=velocity, 1=position, 2=direct drive, 3=spin */
    uint8_t traj_mode;       /* 0=hold, 1=sinus */
    uint8_t calib_phase;
    uint8_t calib_active;    /* 1 = calibration sequence running */
    uint8_t spin_active;     /* 1 = spin in progress */
    float   spin_angle_deg;  /* accumulated rotation since spin started */
} ControlState_t;

void Task_control_Init(void);
void Task_control_GetState(ControlState_t *out);
void Task_control_SetBalanceGains(uint8_t loop_id, float kp, float ki, float kd);
void Task_control_SetVelocitySetpoint(float target_rpm);
void Task_control_SetDirectDrive(float drive_norm);
void Task_control_SetPositionSetpoint(float sp_cm);
void Task_control_SetPositionTraj(uint8_t mode, float amplitude_cm, float period_s);
void Task_control_SetSpinMode(uint8_t enable, float interval_s, float yaw_force);
void Task_control_SetAngleOffset(float offset_deg);
void Task_control_StartCalib(void);
void Task_control_AbortCalib(void);

#endif
