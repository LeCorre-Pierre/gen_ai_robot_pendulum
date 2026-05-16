/**
 ******************************************************************************
 * @file    pid_controller.h
 * @brief   Reusable PID controller for fixed-step STM32 control loops.
 *
 *          Design goals:
 *          - deterministic update cost for >= 200 Hz loops
 *          - explicit sample time configuration
 *          - output and integrator clamping
 *          - derivative-on-measurement to reduce setpoint kick
 ******************************************************************************
 */

#ifndef PID_CONTROLLER_H
#define PID_CONTROLLER_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>

typedef enum
{
    PID_OK = 0,
    PID_ERR_INVALID_PARAM,
} PID_Status_t;

typedef enum
{
    PID_MODE_MANUAL = 0,
    PID_MODE_AUTOMATIC = 1,
} PID_Mode_t;

typedef struct
{
    float kp;
    float ki;
    float kd;

    float sample_time_s;

    float out_min;
    float out_max;

    float integral_min;
    float integral_max;

    float integrator;
    float prev_measurement;
    float last_output;
    uint8_t initialized;
    PID_Mode_t mode;
} PID_Controller_t;

PID_Status_t PID_Init(PID_Controller_t *pid,
                      float kp,
                      float ki,
                      float kd,
                      float sample_time_s,
                      float out_min,
                      float out_max);

PID_Status_t PID_SetTunings(PID_Controller_t *pid, float kp, float ki, float kd);
PID_Status_t PID_SetSampleTime(PID_Controller_t *pid, float sample_time_s);
PID_Status_t PID_SetOutputLimits(PID_Controller_t *pid, float out_min, float out_max);
PID_Status_t PID_SetIntegralLimits(PID_Controller_t *pid, float integral_min, float integral_max);
PID_Status_t PID_SetMode(PID_Controller_t *pid, PID_Mode_t mode);
void PID_Reset(PID_Controller_t *pid);
void PID_SetOutput(PID_Controller_t *pid, float output);
float PID_Update(PID_Controller_t *pid, float setpoint, float measurement);

#ifdef __cplusplus
}
#endif

#endif /* PID_CONTROLLER_H */
