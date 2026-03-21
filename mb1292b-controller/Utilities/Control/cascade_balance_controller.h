/**
 ******************************************************************************
 * @file    cascade_balance_controller.h
 * @brief   Cascade PID controller for a two-wheel self-balancing robot.
 *
 *          Outer loop: wheel velocity -> target pitch angle
 *          Inner loop: pitch angle -> normalized motor command
 *          Yaw loop  : yaw rate or turn command -> differential term
 ******************************************************************************
 */

#ifndef CASCADE_BALANCE_CONTROLLER_H
#define CASCADE_BALANCE_CONTROLLER_H

#ifdef __cplusplus
extern "C" {
#endif

#include "pid_controller.h"

typedef struct
{
    PID_Controller_t angle_pid;
    PID_Controller_t velocity_pid;
    PID_Controller_t yaw_pid;

    float max_target_angle_deg;
    float max_drive_output;
    float max_yaw_output;
} CascadeBalanceController_t;

typedef struct
{
    float target_velocity_rpm;
    float measured_velocity_rpm;

    float target_pitch_deg;
    float measured_pitch_deg;

    float target_yaw_rate;
    float measured_yaw_rate;

    float left_output;
    float right_output;
    float drive_output;
    float yaw_output;
} CascadeBalanceOutput_t;

PID_Status_t CBC_Init(CascadeBalanceController_t *controller, float sample_time_s);
void CBC_Reset(CascadeBalanceController_t *controller);
PID_Status_t CBC_SetAngleTunings(CascadeBalanceController_t *controller, float kp, float ki, float kd);
PID_Status_t CBC_SetVelocityTunings(CascadeBalanceController_t *controller, float kp, float ki, float kd);
PID_Status_t CBC_SetYawTunings(CascadeBalanceController_t *controller, float kp, float ki, float kd);
PID_Status_t CBC_SetLimits(CascadeBalanceController_t *controller,
                           float max_target_angle_deg,
                           float max_drive_output,
                           float max_yaw_output);
CascadeBalanceOutput_t CBC_Update(CascadeBalanceController_t *controller,
                                  float target_velocity_rpm,
                                  float measured_velocity_rpm,
                                  float measured_pitch_deg,
                                  float target_yaw_rate,
                                  float measured_yaw_rate);

#ifdef __cplusplus
}
#endif

#endif /* CASCADE_BALANCE_CONTROLLER_H */
