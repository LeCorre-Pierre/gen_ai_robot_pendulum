#ifndef TASK_CONTROL_H
#define TASK_CONTROL_H

#include <stdint.h>

/* Snapshot of the control loop, published each cycle for VCP telemetry.
 * Light scope: only the fields consumed by the IMU/PID telemetry senders. */
typedef struct {
    float pitch_deg;
    float accel_x_g;
    float accel_y_g;
    float accel_z_g;
    float gyro_x_dps;
    float gyro_y_dps;
    float gyro_z_dps;
    float target_vel_rpm;    /* effective velocity setpoint fed to CBC   */
    float target_pitch_deg;  /* outer loop output → inner setpoint (°)    */
    float drive_output;      /* inner loop (angle PID) output [-1..+1]    */
    float left_output;       /* left motor drive after yaw mix            */
    float right_output;      /* right motor drive after yaw mix           */
    float vel_l_rpm;
    float vel_r_rpm;
} ControlState_t;

void Task_control_Init(void);

/* BLE drive command: speed/turn in [-1..+1] (from CMD_DRIVE bytes / 100) */
void Task_control_SetDrive(float speed_norm, float turn_norm);

/* Balance gains: loop_id 0=angle, 1=velocity, 2=yaw */
void Task_control_SetBalanceGains(uint8_t loop_id, float kp, float ki, float kd);

/* VCP tuning helpers */
void Task_control_GetState(ControlState_t *out);
void Task_control_SetVelocitySetpoint(float target_rpm);  /* RPM, from VCP SET_SP  */
void Task_control_SetAngleOffset(float offset_deg);       /* equilibrium trim [-5..+5] */

/* Emergency stop / resume — delegate to MTR layer */
void Task_control_EmergencyStop(void);
void Task_control_Resume(void);

#endif /* TASK_CONTROL_H */
