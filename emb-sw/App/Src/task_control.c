#include "task_control.h"
#include "FreeRTOS.h"
#include "task.h"
#include "motor_control.h"
#include "imu.h"
#include "angle_estimator.h"
#include "cascade_balance_controller.h"
#include "stm32wb5mm_dk.h"   /* BSP_PB_GetState, BUTTON_USER2 */

#define CONTROL_TASK_STACK_SIZE  512U
#define CONTROL_TASK_PRIORITY    (tskIDLE_PRIORITY + 3U)
#define CONTROL_TASK_PERIOD_MS   5U
#define CONTROL_DT_S             0.005f

#define COMPLEMENTARY_ALPHA      0.98f  /* gyro weight in complementary filter */
#define IMU_MAX_MISS             3U     /* consecutive read failures before emergency stop */

static AngleEstimator_t           s_angle_est;
static CascadeBalanceController_t s_cbc;

/* Last estimated state — read by task_comms for telemetry (floats are 32-bit
 * aligned, reads/writes are atomic on Cortex-M4, no mutex needed). */
static volatile ControlState_t s_state;

static void ControlTask(void *pvParameters)
{
    (void)pvParameters;
    TickType_t last_wake = xTaskGetTickCount();
    IMU_Data_t imu;
    uint8_t    imu_miss  = 0U;
    uint8_t    b2_prev   = 1U;   /* 1 = released (active-low button) */

    for (;;) {
        /* B2 short press — reset emergency stop for tuning */
        uint8_t b2_now = (uint8_t)BSP_PB_GetState(BUTTON_USER2);
        if (b2_now == 0U && b2_prev == 1U) {   /* falling edge = pressed */
            MTR_Init();
            CBC_Reset(&s_cbc);
            imu_miss = 0U;
        }
        b2_prev = b2_now;

        /* 1. Read IMU */
        if (!IMU_Read(&imu)) {
            if (++imu_miss >= IMU_MAX_MISS) {
                MTR_EmergencyStop();
            }
            vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(CONTROL_TASK_PERIOD_MS));
            continue;
        }
        imu_miss = 0U;

        /* 2. Estimate pitch angle (complementary filter)
         * Confirmed axis mapping (2026-05-26, imu_viewer.py identification):
         *   Gravity (vertical) = Ay  (+1 g when upright)
         *   Pitch accel        = Az  (0 g upright, changes with tilt)
         *   Pitch rate gyro    = Gx
         *   Yaw rate gyro      = Gy
         */
        float pitch_deg = AngleEstimator_Update(&s_angle_est,
                                                -imu.accel_z_g,  /* pitch accel = Az (sign: forward→+) */
                                                imu.accel_y_g,   /* gravity     = Ay */
                                                -imu.gyro_x_dps, /* pitch rate  = Gx (negated, consistent) */
                                                CONTROL_DT_S);

        s_state.pitch_deg  = pitch_deg;
        s_state.accel_x_g  = imu.accel_x_g;
        s_state.accel_y_g  = imu.accel_y_g;
        s_state.accel_z_g  = imu.accel_z_g;
        s_state.gyro_x_dps = imu.gyro_x_dps;
        s_state.gyro_y_dps = imu.gyro_y_dps;
        s_state.gyro_z_dps = imu.gyro_z_dps;

        /* 3. Safety: cut motors if |tilt| > threshold or overcurrent */
        if (MTR_SafetyUpdate(pitch_deg) != MTR_OK) {
            vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(CONTROL_TASK_PERIOD_MS));
            continue;
        }

        /* 4. Cascade balance controller */
        float vel_avg = (MTR_GetCachedVelocityRPM(MTR_LEFT) + MTR_GetCachedVelocityRPM(MTR_RIGHT)) * 0.5f;

        CascadeBalanceOutput_t out = CBC_Update(&s_cbc,
                                                0.0f,          /* target velocity = stand still */
                                                vel_avg,
                                                pitch_deg,
                                                0.0f,          /* target yaw = straight */
                                                imu.gyro_y_dps); /* yaw rate = Gy */

        s_state.drive_output = out.drive_output;

        /* 5. Apply to motors — output negated: forward tilt → forward drive */
        MTR_SetDifferential(-out.left_output, -out.right_output);
        MTR_VelocityUpdate();

        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(CONTROL_TASK_PERIOD_MS));
    }
}

void Task_control_GetState(ControlState_t *out)
{
    out->pitch_deg  = s_state.pitch_deg;
    out->accel_x_g  = s_state.accel_x_g;
    out->accel_y_g  = s_state.accel_y_g;
    out->accel_z_g  = s_state.accel_z_g;
    out->gyro_x_dps = s_state.gyro_x_dps;
    out->gyro_y_dps = s_state.gyro_y_dps;
    out->gyro_z_dps   = s_state.gyro_z_dps;
    out->drive_output = s_state.drive_output;
}

void Task_control_SetBalanceGains(uint8_t loop_id, float kp, float ki, float kd)
{
    switch (loop_id) {
    case 0U: CBC_SetAngleTunings(&s_cbc,    kp, ki, kd); break;
    case 1U: CBC_SetVelocityTunings(&s_cbc, kp, ki, kd); break;
    case 2U: CBC_SetYawTunings(&s_cbc,      kp, ki, kd); break;
    default: break;
    }
}

void Task_control_Init(void)
{
    AngleEstimator_Init(&s_angle_est, COMPLEMENTARY_ALPHA);
    CBC_Init(&s_cbc, CONTROL_DT_S);

    MTR_SetControlMode(MTR_LEFT,  MTR_MODE_VELOCITY);
    MTR_SetControlMode(MTR_RIGHT, MTR_MODE_VELOCITY);

    xTaskCreate(ControlTask, "Control", CONTROL_TASK_STACK_SIZE, NULL,
                CONTROL_TASK_PRIORITY, NULL);
}
