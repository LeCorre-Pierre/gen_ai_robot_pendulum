#include "task_control.h"
#include "task_comms.h"
#include "FreeRTOS.h"
#include "task.h"
#include "motor_control.h"
#include "imu.h"
#include "angle_estimator.h"
#include "pid_controller.h"
#include "stm32wb5mm_dk.h"   /* BSP_PB_GetState, BUTTON_USER2 */

#define CONTROL_TASK_STACK_SIZE  512U
#define CONTROL_TASK_PRIORITY    (tskIDLE_PRIORITY + 3U)
#define CONTROL_TASK_PERIOD_MS   5U
#define CONTROL_DT_S             0.005f

#define COMPLEMENTARY_ALPHA      0.98f
#define IMU_MAX_MISS             3U

static AngleEstimator_t  s_angle_est;
static PID_Controller_t  s_angle_pid;

static volatile ControlState_t s_state;

/* ── Motor calibration sequence ─────────────────────────────────────────── */

typedef struct {
    int16_t  drive_x1000;   /* drive × 1000 — range [-1000..+1000] */
    uint16_t hold_ticks;    /* ticks at 200 Hz to hold this drive   */
    uint8_t  phase;         /* phase tag (0–16) for PC-side analysis */
} CalibStep_t;

#define CALIB_MAX_STEPS  260U

static CalibStep_t   s_calib_seq[CALIB_MAX_STEPS];
static uint32_t      s_calib_len   = 0U;
static uint32_t      s_calib_idx   = 0U;
static uint32_t      s_calib_tick  = 0U;
static volatile uint8_t s_calib_active = 0U;

static void Calib_Build(void)
{
    /* Step amplitudes for step-response phase (drive_x1000) */
    static const int16_t AMP[10] = {50, 80, 100, 130, 150, 200, 300, 500, 750, 1000};
    uint32_t n = 0U;

#define SEQ(d, t, p) \
    do { s_calib_seq[n].drive_x1000 = (int16_t)(d); \
         s_calib_seq[n].hold_ticks  = (uint16_t)(t); \
         s_calib_seq[n].phase       = (uint8_t)(p);  \
         n++; } while (0)

    SEQ(0, 100, 0);   /* Ph 0 — baseline zero (0.5 s) */

    /* Ph 1 — fine ramp up:   0.01 → 0.25, step 0.01, 200 ms each */
    { int i; for (i = 1;  i <= 25;  i++)    { SEQ(i * 10,  40, 1); } }
    /* Ph 2 — coarse ramp up: 0.30 → 1.00, step 0.05, 200 ms each */
    { int i; for (i = 30; i <= 100; i += 5) { SEQ(i * 10,  40, 2); } }

    SEQ(1000, 100, 3);   /* Ph 3 — hold +1.0 (0.5 s) */

    /* Ph 4 — coarse ramp down: 0.95 → 0.30, step 0.05 */
    { int i; for (i = 95; i >= 30;  i -= 5) { SEQ(i * 10,  40, 4); } }
    /* Ph 5 — fine ramp down:   0.25 → 0.00, step 0.01 */
    { int i; for (i = 25; i >= 0;   i--)    { SEQ(i * 10,  40, 5); } }

    SEQ(0, 100, 6);   /* Ph 6 — zero pause (0.5 s) */

    /* Ph 7-11 — mirror for negative drive */
    { int i; for (i = -1;  i >= -25;  i--)    { SEQ(i * 10,  40, 7);  } }
    { int i; for (i = -30; i >= -100; i -= 5) { SEQ(i * 10,  40, 8);  } }
    SEQ(-1000, 100, 9);
    { int i; for (i = -95; i <= -30;  i += 5) { SEQ(i * 10,  40, 10); } }
    { int i; for (i = -25; i <= 0;    i++)    { SEQ(i * 10,  40, 11); } }

    SEQ(0, 80, 12);   /* Ph 12 — separator before steps */

    /* Ph 13 — positive step responses: 10 amplitudes × (200+500+400 ms) */
    { int k; for (k = 0; k < 10; k++) { SEQ(0, 40, 13); SEQ(AMP[k],  100, 13); SEQ(0, 80, 13); } }
    /* Ph 14 — negative step responses */
    { int k; for (k = 0; k < 10; k++) { SEQ(0, 40, 14); SEQ(-AMP[k], 100, 14); SEQ(0, 80, 14); } }

    /* Ph 15 — reversal ±0.50 × 4 cycles */
    { int r; for (r = 0; r < 4; r++) { SEQ(500, 100, 15); SEQ(-500, 100, 15); } }
    SEQ(0, 60, 15);

    /* Ph 16 — reversal ±0.75 × 4 cycles */
    { int r; for (r = 0; r < 4; r++) { SEQ(750, 100, 16); SEQ(-750, 100, 16); } }
    SEQ(0, 80, 16);

    s_calib_len = n;

#undef SEQ
}

static void ControlTask(void *pvParameters)
{
    (void)pvParameters;
    TickType_t last_wake = xTaskGetTickCount();
    IMU_Data_t imu;
    uint8_t    b2_prev   = 1U;

    for (;;) {
        /* ── Motor calibration sequence (takes priority over normal control) ── */
        if (s_calib_active) {
            const CalibStep_t *step = &s_calib_seq[s_calib_idx];
            float drive = (float)step->drive_x1000 * 0.001f;

            MTR_SetDifferential(drive, drive);

            s_state.drive_output = drive;
            s_state.vel_l_rpm    = MTR_GetVelocityRPM(MTR_LEFT);
            s_state.vel_r_rpm    = MTR_GetVelocityRPM(MTR_RIGHT);
            s_state.calib_phase  = step->phase;
            s_state.calib_active = 1U;

            s_calib_tick++;
            if (s_calib_tick >= (uint32_t)step->hold_ticks) {
                s_calib_tick = 0U;
                s_calib_idx++;
                if (s_calib_idx >= s_calib_len) {
                    s_calib_active       = 0U;
                    s_state.calib_active = 0U;   /* last-packet marker */
                    MTR_Coast(MTR_LEFT);   /* MTR_Coast resets to DIRECT mode */
                    MTR_Coast(MTR_RIGHT);
                }
            }

            vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(CONTROL_TASK_PERIOD_MS));
            continue;
        }

        /* ── Normal balance control ────────────────────────────────────────── */
        uint8_t b2_now = (uint8_t)BSP_PB_GetState(BUTTON_USER2);
        if (b2_now == 0U && b2_prev == 1U) {
            MTR_Init();   /* resets to DIRECT mode */
            PID_Reset(&s_angle_pid);
        }
        b2_prev = b2_now;

        IMU_Read(&imu);

        /* Az négé (convention forward=+), Gx non négé (confirmé 2026-06-09) */
        float pitch_deg = AngleEstimator_Update(&s_angle_est,
                                                -imu.accel_z_g,
                                                imu.accel_y_g,
                                                imu.gyro_x_dps,
                                                CONTROL_DT_S);

        s_state.pitch_deg  = pitch_deg;
        s_state.accel_x_g  = imu.accel_x_g;
        s_state.accel_y_g  = imu.accel_y_g;
        s_state.accel_z_g  = imu.accel_z_g;
        s_state.gyro_x_dps = imu.gyro_x_dps;
        s_state.gyro_y_dps = imu.gyro_y_dps;
        s_state.gyro_z_dps = imu.gyro_z_dps;

        /* Single angle PID → direct PWM (dead-zone compensation in MTR_ApplyPWM) */
        {
            s_state.vel_l_rpm = MTR_GetVelocityRPM(MTR_LEFT);
            s_state.vel_r_rpm = MTR_GetVelocityRPM(MTR_RIGHT);
            float drive = PID_Update(&s_angle_pid, 0.0f, pitch_deg);
            s_state.drive_output = drive;
            MTR_SetDifferential(-drive, -drive);
        }

        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(CONTROL_TASK_PERIOD_MS));
    }
}

void Task_control_GetState(ControlState_t *out)
{
    out->pitch_deg    = s_state.pitch_deg;
    out->accel_x_g    = s_state.accel_x_g;
    out->accel_y_g    = s_state.accel_y_g;
    out->accel_z_g    = s_state.accel_z_g;
    out->gyro_x_dps   = s_state.gyro_x_dps;
    out->gyro_y_dps   = s_state.gyro_y_dps;
    out->gyro_z_dps   = s_state.gyro_z_dps;
    out->drive_output = s_state.drive_output;
    out->vel_l_rpm    = s_state.vel_l_rpm;
    out->vel_r_rpm    = s_state.vel_r_rpm;
    out->calib_phase  = s_state.calib_phase;
    out->calib_active = s_state.calib_active;
}

void Task_control_StartCalib(void)
{
    Calib_Build();
    s_calib_idx  = 0U;
    s_calib_tick = 0U;
    MTR_SetControlMode(MTR_LEFT,  MTR_MODE_DIRECT);
    MTR_SetControlMode(MTR_RIGHT, MTR_MODE_DIRECT);
    s_state.calib_active = 1U;
    s_calib_active       = 1U;   /* arm — control task picks it up next tick */
}

void Task_control_AbortCalib(void)
{
    s_calib_active       = 0U;
    s_state.calib_active = 0U;
    MTR_Coast(MTR_LEFT);
    MTR_Coast(MTR_RIGHT);
}

void Task_control_SetBalanceGains(uint8_t loop_id, float kp, float ki, float kd)
{
    if (loop_id == 0U) {
        PID_SetTunings(&s_angle_pid, kp, ki, kd);
    }
}

void Task_control_Init(void)
{
    AngleEstimator_Init(&s_angle_est, COMPLEMENTARY_ALPHA);
    PID_Init(&s_angle_pid, 0.15f, 0.00f, 0.030f, CONTROL_DT_S, -1.0f, 1.0f);
    PID_SetIntegralLimits(&s_angle_pid, -0.3f, 0.3f);
    s_state.calib_active = 0U;
    xTaskCreate(ControlTask, "Control", CONTROL_TASK_STACK_SIZE, NULL,
                CONTROL_TASK_PRIORITY, NULL);
}
