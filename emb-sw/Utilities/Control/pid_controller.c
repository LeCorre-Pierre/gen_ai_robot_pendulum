/**
 ******************************************************************************
 * @file    pid_controller.c
 * @brief   Reusable PID controller for fixed-step STM32 control loops.
 ******************************************************************************
 */

#include "pid_controller.h"

static float PID_Clamp(float value, float min_value, float max_value)
{
    if (value < min_value)
    {
        return min_value;
    }
    if (value > max_value)
    {
        return max_value;
    }
    return value;
}

PID_Status_t PID_Init(PID_Controller_t *pid,
                      float kp,
                      float ki,
                      float kd,
                      float sample_time_s,
                      float out_min,
                      float out_max)
{
    if ((pid == 0) || (sample_time_s <= 0.0f) || (out_min >= out_max))
    {
        return PID_ERR_INVALID_PARAM;
    }

    pid->kp = kp;
    pid->ki = ki;
    pid->kd = kd;
    pid->sample_time_s = sample_time_s;
    pid->out_min = out_min;
    pid->out_max = out_max;
    pid->integral_min = out_min;
    pid->integral_max = out_max;
    pid->integrator = 0.0f;
    pid->prev_measurement = 0.0f;
    pid->last_output = 0.0f;
    pid->initialized = 0U;
    pid->mode = PID_MODE_AUTOMATIC;

    return PID_OK;
}

PID_Status_t PID_SetTunings(PID_Controller_t *pid, float kp, float ki, float kd)
{
    if (pid == 0)
    {
        return PID_ERR_INVALID_PARAM;
    }

    pid->kp = kp;
    pid->ki = ki;
    pid->kd = kd;
    return PID_OK;
}

PID_Status_t PID_SetSampleTime(PID_Controller_t *pid, float sample_time_s)
{
    if ((pid == 0) || (sample_time_s <= 0.0f))
    {
        return PID_ERR_INVALID_PARAM;
    }

    pid->sample_time_s = sample_time_s;
    return PID_OK;
}

PID_Status_t PID_SetOutputLimits(PID_Controller_t *pid, float out_min, float out_max)
{
    if ((pid == 0) || (out_min >= out_max))
    {
        return PID_ERR_INVALID_PARAM;
    }

    pid->out_min = out_min;
    pid->out_max = out_max;
    pid->integrator = PID_Clamp(pid->integrator, pid->out_min, pid->out_max);
    pid->last_output = PID_Clamp(pid->last_output, pid->out_min, pid->out_max);
    return PID_OK;
}

PID_Status_t PID_SetIntegralLimits(PID_Controller_t *pid, float integral_min, float integral_max)
{
    if ((pid == 0) || (integral_min > integral_max))
    {
        return PID_ERR_INVALID_PARAM;
    }

    pid->integral_min = integral_min;
    pid->integral_max = integral_max;
    pid->integrator = PID_Clamp(pid->integrator, integral_min, integral_max);
    return PID_OK;
}

PID_Status_t PID_SetMode(PID_Controller_t *pid, PID_Mode_t mode)
{
    if (pid == 0)
    {
        return PID_ERR_INVALID_PARAM;
    }

    pid->mode = mode;
    return PID_OK;
}

void PID_Reset(PID_Controller_t *pid)
{
    if (pid == 0)
    {
        return;
    }

    pid->integrator = 0.0f;
    pid->prev_measurement = 0.0f;
    pid->last_output = 0.0f;
    pid->initialized = 0U;
}

void PID_SetOutput(PID_Controller_t *pid, float output)
{
    if (pid == 0)
    {
        return;
    }

    pid->last_output = PID_Clamp(output, pid->out_min, pid->out_max);
    pid->integrator = PID_Clamp(pid->last_output, pid->integral_min, pid->integral_max);
}

float PID_Update(PID_Controller_t *pid, float setpoint, float measurement)
{
    float error;
    float proportional;
    float derivative;
    float output;

    if (pid == 0)
    {
        return 0.0f;
    }

    if (pid->mode == PID_MODE_MANUAL)
    {
        return pid->last_output;
    }

    error = setpoint - measurement;

    if (pid->initialized == 0U)
    {
        pid->prev_measurement = measurement;
        pid->initialized = 1U;
    }

    proportional = pid->kp * error;

    pid->integrator += pid->ki * error * pid->sample_time_s;
    pid->integrator = PID_Clamp(pid->integrator, pid->integral_min, pid->integral_max);

    derivative = -pid->kd * (measurement - pid->prev_measurement) / pid->sample_time_s;

    output = proportional + pid->integrator + derivative;
    output = PID_Clamp(output, pid->out_min, pid->out_max);

    /*
     * Basic anti-windup:
     * when the output saturates further in the same direction as the error,
     * rewind the last integrator step.
     */
    if (((output >= pid->out_max) && (error > 0.0f)) ||
        ((output <= pid->out_min) && (error < 0.0f)))
    {
        pid->integrator -= pid->ki * error * pid->sample_time_s;
        pid->integrator = PID_Clamp(pid->integrator, pid->integral_min, pid->integral_max);
        output = PID_Clamp(proportional + pid->integrator + derivative, pid->out_min, pid->out_max);
    }

    pid->prev_measurement = measurement;
    pid->last_output = output;
    return output;
}
