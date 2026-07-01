/**
 ******************************************************************************
 * @file    task_control.c
 * @brief   200 Hz balance control loop (step 4d).
 *
 *          - Reads pitch from task_sensors (Sensors_GetPitchDeg)
 *          - Reads wheel velocity from MTR_GetCachedVelocityRPM
 *          - Runs cascade PID (velocity → angle → drive)
 *          - Commands motors via MTR_SetDifferential
 *          - Safety cut at |pitch| > 45°
 *
 *          Axis convention (confirmed CLAUDE.md 2026-05-26):
 *            pitch > 0 = robot penché vers l'avant
 ******************************************************************************
 */
#include "main.h"
#include "cmsis_os.h"
#include "task_control.h"
#include "task_sensors.h"
#include "motor_control.h"
#include "cascade_balance_controller.h"

#define CONTROL_PERIOD_MS   5U      /* 200 Hz — matches proven emb-sw loop */
#define CONTROL_DT_S        0.005f

#define TILT_CUTOFF_DEG     45.0f
#define MAX_VEL_RPM         30.0f   /* max wheel speed the BLE drive command maps to */
#define MAX_YAW_DPS         90.0f   /* max yaw rate the BLE turn command maps to */

/* Best angle gains from emb-sw tuning sessions */
#define KP_ANGLE_DEFAULT    0.241f
#define KI_ANGLE_DEFAULT    0.000f
#define KD_ANGLE_DEFAULT    0.00041f

#define KP_VEL_DEFAULT      0.050f
#define KI_VEL_DEFAULT      0.005f
#define KD_VEL_DEFAULT      0.000f

static CascadeBalanceController_t s_cbc;

static volatile float s_target_vel_rpm = 0.0f;
static volatile float s_target_yaw_dps = 0.0f;
static volatile float s_angle_sp_offset = 0.0f;   /* equilibrium trim (°), from VCP */
static volatile uint8_t s_balance_active = 0U;

static volatile ControlState_t s_state;           /* published each cycle for VCP */

static osThreadId_t ControlThreadId;
static const osThreadAttr_t ControlProcess_attr =
{
    .name       = "Control",
    .priority   = osPriorityAboveNormal,   /* consumer: runs just after Sensors */
    .stack_size = 1024U,
};

static void ControlProcess(void *argument)
{
    uint32_t tick;
    UNUSED(argument);

    MTR_Init();
    s_balance_active = 1U;
    tick = osKernelGetTickCount();

    for (;;)
    {
        tick += CONTROL_PERIOD_MS;
        osDelayUntil(tick);

        /* Refresh the cached wheel speed first, then read it, so the outer
         * velocity loop uses the current measurement (not a cycle-old value). */
        MTR_VelocityUpdate();

        float pitch_deg  = Sensors_GetPitchDeg();
        float yaw_dps    = Sensors_GetYawRateDps();
        float vel_l      = MTR_GetCachedVelocityRPM(MTR_LEFT);
        float vel_r      = MTR_GetCachedVelocityRPM(MTR_RIGHT);
        float vel_avg    = (vel_l + vel_r) * 0.5f;

        /* Publish IMU + velocity part of the telemetry snapshot */
        IMU_Data_t imu;
        Sensors_GetImu(&imu);
        s_state.pitch_deg  = pitch_deg;
        s_state.accel_x_g  = imu.accel_x_g;
        s_state.accel_y_g  = imu.accel_y_g;
        s_state.accel_z_g  = imu.accel_z_g;
        s_state.gyro_x_dps = imu.gyro_x_dps;
        s_state.gyro_y_dps = imu.gyro_y_dps;
        s_state.gyro_z_dps = imu.gyro_z_dps;
        s_state.vel_l_rpm  = vel_l;
        s_state.vel_r_rpm  = vel_r;

        /* Safety cut */
        float abs_pitch = pitch_deg >= 0.0f ? pitch_deg : -pitch_deg;
        if (abs_pitch > TILT_CUTOFF_DEG)
        {
            MTR_EmergencyStop();
            s_balance_active = 0U;

            /* Wait for robot to be uprighted before resuming */
            while (abs_pitch > TILT_CUTOFF_DEG)
            {
                osDelay(50U);
                pitch_deg = Sensors_GetPitchDeg();
                abs_pitch = pitch_deg >= 0.0f ? pitch_deg : -pitch_deg;
            }
            MTR_ClearEmergency();
            CBC_Reset(&s_cbc);
            s_target_vel_rpm = 0.0f;
            s_target_yaw_dps = 0.0f;
            s_balance_active = 1U;
            tick = osKernelGetTickCount();
            continue;
        }

        CascadeBalanceOutput_t out = CBC_Update(&s_cbc,
                                                s_target_vel_rpm,
                                                vel_avg,
                                                pitch_deg - s_angle_sp_offset,
                                                s_target_yaw_dps,
                                                yaw_dps);

        MTR_SetDifferential(-out.left_output, -out.right_output);

        /* Publish control outputs for VCP telemetry */
        s_state.target_vel_rpm   = s_target_vel_rpm;
        s_state.target_pitch_deg = out.target_pitch_deg;
        s_state.drive_output     = out.drive_output;
        s_state.left_output      = out.left_output;
        s_state.right_output     = out.right_output;
    }
}

void Task_control_Init(void)
{
    CBC_Init(&s_cbc, CONTROL_DT_S);
    CBC_SetAngleTunings(&s_cbc, KP_ANGLE_DEFAULT, KI_ANGLE_DEFAULT, KD_ANGLE_DEFAULT);
    CBC_SetLimits(&s_cbc, 8.0f, 1.0f, 0.3f);
    PID_SetIntegralLimits(&s_cbc.angle_pid, -0.3f, 0.3f);

    CBC_SetVelocityTunings(&s_cbc, KP_VEL_DEFAULT, KI_VEL_DEFAULT, KD_VEL_DEFAULT);
    PID_SetIntegralLimits(&s_cbc.velocity_pid, -3.0f, 3.0f);

    CBC_SetYawTunings(&s_cbc, 0.002f, 0.0f, 0.0f);

    ControlThreadId = osThreadNew(ControlProcess, NULL, &ControlProcess_attr);
}

void Task_control_SetDrive(float speed_norm, float turn_norm)
{
    s_target_vel_rpm = speed_norm * MAX_VEL_RPM;
    s_target_yaw_dps = turn_norm * MAX_YAW_DPS;
}

void Task_control_SetBalanceGains(uint8_t loop_id, float kp, float ki, float kd)
{
    switch (loop_id)
    {
    case 0U: CBC_SetAngleTunings(&s_cbc, kp, ki, kd);    break;
    case 1U: CBC_SetVelocityTunings(&s_cbc, kp, ki, kd); break;
    case 2U: CBC_SetYawTunings(&s_cbc, kp, ki, kd);      break;
    default: break;
    }
}

void Task_control_GetState(ControlState_t *out)
{
    if (out) { *out = s_state; }
}

void Task_control_SetVelocitySetpoint(float target_rpm)
{
    s_target_vel_rpm = target_rpm;
    s_target_yaw_dps = 0.0f;
}

void Task_control_SetAngleOffset(float offset_deg)
{
    if (offset_deg >  5.0f) { offset_deg =  5.0f; }
    if (offset_deg < -5.0f) { offset_deg = -5.0f; }
    s_angle_sp_offset = offset_deg;
}

void Task_control_EmergencyStop(void)
{
    MTR_EmergencyStop();
    s_balance_active = 0U;
}

void Task_control_Resume(void)
{
    MTR_ClearEmergency();
    CBC_Reset(&s_cbc);
    s_target_vel_rpm = 0.0f;
    s_target_yaw_dps = 0.0f;
    s_balance_active = 1U;
}
