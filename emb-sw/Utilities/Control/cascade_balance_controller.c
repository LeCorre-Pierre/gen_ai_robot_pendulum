/**
 ******************************************************************************
 * @file    cascade_balance_controller.c
 * @brief   Cascade PID controller for a two-wheel self-balancing robot.
 ******************************************************************************
 */

#include "cascade_balance_controller.h"

static float CBC_Clamp(float value, float min_value, float max_value)
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

PID_Status_t CBC_Init(CascadeBalanceController_t *controller, float sample_time_s)
{
    PID_Status_t status;

    if (controller == 0)
    {
        return PID_ERR_INVALID_PARAM;
    }

    status = PID_Init(&controller->angle_pid, 0.0f, 0.0f, 0.0f, sample_time_s, -1.0f, 1.0f);
    if (status != PID_OK)
    {
        return status;
    }

    status = PID_Init(&controller->velocity_pid, 0.0f, 0.0f, 0.0f, sample_time_s, -10.0f, 10.0f);
    if (status != PID_OK)
    {
        return status;
    }

    status = PID_Init(&controller->yaw_pid, 0.0f, 0.0f, 0.0f, sample_time_s, -0.3f, 0.3f);
    if (status != PID_OK)
    {
        return status;
    }

    controller->max_target_angle_deg = 10.0f;
    controller->max_drive_output = 1.0f;
    controller->max_yaw_output = 0.3f;

    (void)PID_SetIntegralLimits(&controller->angle_pid, -0.5f, 0.5f);
    (void)PID_SetIntegralLimits(&controller->velocity_pid, -5.0f, 5.0f);
    (void)PID_SetIntegralLimits(&controller->yaw_pid, -0.2f, 0.2f);
    return PID_OK;
}

void CBC_Reset(CascadeBalanceController_t *controller)
{
    if (controller == 0)
    {
        return;
    }

    PID_Reset(&controller->angle_pid);
    PID_Reset(&controller->velocity_pid);
    PID_Reset(&controller->yaw_pid);
}

PID_Status_t CBC_SetAngleTunings(CascadeBalanceController_t *controller, float kp, float ki, float kd)
{
    if (controller == 0)
    {
        return PID_ERR_INVALID_PARAM;
    }
    return PID_SetTunings(&controller->angle_pid, kp, ki, kd);
}

PID_Status_t CBC_SetVelocityTunings(CascadeBalanceController_t *controller, float kp, float ki, float kd)
{
    if (controller == 0)
    {
        return PID_ERR_INVALID_PARAM;
    }
    return PID_SetTunings(&controller->velocity_pid, kp, ki, kd);
}

PID_Status_t CBC_SetYawTunings(CascadeBalanceController_t *controller, float kp, float ki, float kd)
{
    if (controller == 0)
    {
        return PID_ERR_INVALID_PARAM;
    }
    return PID_SetTunings(&controller->yaw_pid, kp, ki, kd);
}

PID_Status_t CBC_SetLimits(CascadeBalanceController_t *controller,
                           float max_target_angle_deg,
                           float max_drive_output,
                           float max_yaw_output)
{
    if ((controller == 0) ||
        (max_target_angle_deg <= 0.0f) ||
        (max_drive_output <= 0.0f) ||
        (max_yaw_output < 0.0f))
    {
        return PID_ERR_INVALID_PARAM;
    }

    controller->max_target_angle_deg = max_target_angle_deg;
    controller->max_drive_output = max_drive_output;
    controller->max_yaw_output = max_yaw_output;

    (void)PID_SetOutputLimits(&controller->velocity_pid, -max_target_angle_deg, max_target_angle_deg);
    (void)PID_SetOutputLimits(&controller->angle_pid, -max_drive_output, max_drive_output);
    (void)PID_SetOutputLimits(&controller->yaw_pid, -max_yaw_output, max_yaw_output);
    return PID_OK;
}

CascadeBalanceOutput_t CBC_Update(CascadeBalanceController_t *controller,
                                  float target_velocity_rpm,
                                  float measured_velocity_rpm,
                                  float measured_pitch_deg,
                                  float target_yaw_rate,
                                  float measured_yaw_rate)
{
    CascadeBalanceOutput_t output;

    output.target_velocity_rpm = target_velocity_rpm;
    output.measured_velocity_rpm = measured_velocity_rpm;
    output.measured_pitch_deg = measured_pitch_deg;
    output.target_yaw_rate = target_yaw_rate;
    output.measured_yaw_rate = measured_yaw_rate;
    output.target_pitch_deg = 0.0f;
    output.drive_output = 0.0f;
    output.yaw_output = 0.0f;
    output.left_output = 0.0f;
    output.right_output = 0.0f;

    if (controller == 0)
    {
        return output;
    }

    output.target_pitch_deg = PID_Update(&controller->velocity_pid,
                                         target_velocity_rpm,
                                         measured_velocity_rpm);
    output.target_pitch_deg = CBC_Clamp(output.target_pitch_deg,
                                        -controller->max_target_angle_deg,
                                        controller->max_target_angle_deg);

    output.drive_output = PID_Update(&controller->angle_pid,
                                     output.target_pitch_deg,
                                     measured_pitch_deg);
    output.drive_output = CBC_Clamp(output.drive_output,
                                    -controller->max_drive_output,
                                    controller->max_drive_output);

    output.yaw_output = PID_Update(&controller->yaw_pid,
                                   target_yaw_rate,
                                   measured_yaw_rate);
    output.yaw_output = CBC_Clamp(output.yaw_output,
                                  -controller->max_yaw_output,
                                  controller->max_yaw_output);

    output.left_output = CBC_Clamp(output.drive_output + output.yaw_output, -1.0f, 1.0f);
    output.right_output = CBC_Clamp(output.drive_output - output.yaw_output, -1.0f, 1.0f);

    return output;
}
