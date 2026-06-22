#include "task_control.h"
#include "task_comms.h"
#include "FreeRTOS.h"
#include "task.h"
#include "motor_control.h"
#include "imu.h"
#include "angle_estimator.h"
#include "cascade_balance_controller.h"
#include "pid_controller.h"
#include "vcp_protocol.h"   /* VCP_TRAJ_HOLD / VCP_TRAJ_SINUS */
#include "stm32wb5mm_dk.h"  /* BSP_PB_GetState, BUTTON_USER2 */
#include <math.h>

#define CONTROL_TASK_STACK_SIZE  512U
#define CONTROL_TASK_PRIORITY    (tskIDLE_PRIORITY + 3U)
#define CONTROL_TASK_PERIOD_MS   5U
#define CONTROL_DT_S             0.005f

#define COMPLEMENTARY_ALPHA      0.98f
#define IMU_MAX_MISS             3U
#define CURRENT_ALPHA            0.2f  /* EMA passe-bas courant ADC (τ≈20ms, fc≈6Hz) */

/* Wheel geometry — adjust if actual wheel diameter differs */
#define WHEEL_DIAMETER_CM     6.5f
#define POS_CM_PER_TICK       (WHEEL_DIAMETER_CM * 3.14159265f / (float)MTR_ENC_TICKS_PER_REV)
#define POS_VEL_SP_MAX_RPM    20.0f   /* max velocity the position PID can request */

static AngleEstimator_t           s_angle_est;
static CascadeBalanceController_t s_cbc;
static PID_Controller_t           s_pos_pid;

/* Velocity setpoint (used in velocity mode) */
static volatile float   s_target_vel_rpm  = 0.0f;

/* Direct drive state (Cas 2 — Ident K / Ident Td, bypasses balance loop) */
static volatile float    s_direct_drive       = 0.0f;
static          uint32_t s_direct_drive_ticks = 0U;
static volatile float    s_angle_sp_offset    = 0.0f;
static volatile float    s_target_angle_deg   = 0.0f;  /* mode 4 direct angle setpoint */
#define DIRECT_DRIVE_HOLD_TICKS  60U  /* ~300 ms @ 5 ms loop without a fresh command → drive=0 */

/* Position loop state */
static volatile float   s_pos_sp_cm       = 0.0f;
static volatile uint8_t s_traj_mode       = 0U;   /* VCP_TRAJ_HOLD / VCP_TRAJ_SINUS */
static volatile float   s_traj_amplitude  = 10.0f; /* cm */
static volatile float   s_traj_period_s   = 2.0f;  /* s */
static volatile uint8_t s_ctrl_mode       = 0U;   /* 0=velocity, 1=position */
static volatile uint8_t s_pos_reset_req   = 0U;   /* 1 = reset position origin next cycle */

static float   s_traj_t    = 0.0f;
static float   s_pos_cm    = 0.0f;
static float   s_pos_vel_sp = 0.0f;
static int32_t s_enc_l_prev = 0;
static int32_t s_enc_r_prev = 0;

/* Spin mode state (Cas 4 — auto-spin every N seconds) */
static volatile float   s_spin_interval_s  = 60.0f;  /* s between spins */
static volatile float   s_spin_yaw_force   = 0.4f;   /* normalized differential */
static          float   s_spin_interval_timer = 0.0f; /* elapsed since last spin */
static          uint8_t s_spin_active      = 0U;      /* 1 = spinning now */
static          float   s_spin_angle_deg   = 0.0f;   /* accumulated gyro_y integral */

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
    static const int16_t AMP[10] = {50, 80, 100, 130, 150, 200, 300, 500, 750, 1000};
    uint32_t n = 0U;

#define SEQ(d, t, p) \
    do { s_calib_seq[n].drive_x1000 = (int16_t)(d); \
         s_calib_seq[n].hold_ticks  = (uint16_t)(t); \
         s_calib_seq[n].phase       = (uint8_t)(p);  \
         n++; } while (0)

    SEQ(0, 100, 0);

    { int i; for (i = 1;  i <= 25;  i++)    { SEQ(i * 10,  40, 1); } }
    { int i; for (i = 30; i <= 100; i += 5) { SEQ(i * 10,  40, 2); } }

    SEQ(1000, 100, 3);

    { int i; for (i = 95; i >= 30;  i -= 5) { SEQ(i * 10,  40, 4); } }
    { int i; for (i = 25; i >= 0;   i--)    { SEQ(i * 10,  40, 5); } }

    SEQ(0, 100, 6);

    { int i; for (i = -1;  i >= -25;  i--)    { SEQ(i * 10,  40, 7);  } }
    { int i; for (i = -30; i >= -100; i -= 5) { SEQ(i * 10,  40, 8);  } }
    SEQ(-1000, 100, 9);
    { int i; for (i = -95; i <= -30;  i += 5) { SEQ(i * 10,  40, 10); } }
    { int i; for (i = -25; i <= 0;    i++)    { SEQ(i * 10,  40, 11); } }

    SEQ(0, 80, 12);

    { int k; for (k = 0; k < 10; k++) { SEQ(0, 40, 13); SEQ(AMP[k],  100, 13); SEQ(0, 80, 13); } }
    { int k; for (k = 0; k < 10; k++) { SEQ(0, 40, 14); SEQ(-AMP[k], 100, 14); SEQ(0, 80, 14); } }

    { int r; for (r = 0; r < 4; r++) { SEQ(500, 100, 15); SEQ(-500, 100, 15); } }
    SEQ(0, 60, 15);

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
            s_state.current_l_a  = CURRENT_ALPHA * MTR_GetCurrentA(MTR_LEFT)
                                 + (1.0f - CURRENT_ALPHA) * s_state.current_l_a;
            s_state.current_r_a  = CURRENT_ALPHA * MTR_GetCurrentA(MTR_RIGHT)
                                 + (1.0f - CURRENT_ALPHA) * s_state.current_r_a;
            s_state.calib_phase  = step->phase;
            s_state.calib_active = 1U;

            s_calib_tick++;
            if (s_calib_tick >= (uint32_t)step->hold_ticks) {
                s_calib_tick = 0U;
                s_calib_idx++;
                if (s_calib_idx >= s_calib_len) {
                    s_calib_active       = 0U;
                    s_state.calib_active = 0U;
                    MTR_Coast(MTR_LEFT);
                    MTR_Coast(MTR_RIGHT);
                }
            }

            vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(CONTROL_TASK_PERIOD_MS));
            continue;
        }

        /* ── Normal balance control ────────────────────────────────────────── */
        uint8_t b2_now = (uint8_t)BSP_PB_GetState(BUTTON_USER2);
        if (b2_now == 0U && b2_prev == 1U) {
            MTR_Init();
            CBC_Reset(&s_cbc);
            PID_Reset(&s_pos_pid);
            s_angle_sp_offset    = 0.0f;
            s_target_angle_deg   = 0.0f;
            s_pos_cm             = 0.0f;
            s_pos_sp_cm          = 0.0f;
            s_traj_t             = 0.0f;
            s_ctrl_mode          = 0U;
            s_spin_active        = 0U;
            s_spin_angle_deg     = 0.0f;
            s_spin_interval_timer = 0.0f;
            /* MTR_Init resets encoder counters to 0 */
            s_enc_l_prev  = 0;
            s_enc_r_prev  = 0;
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

        /* Velocity measurement */
        s_state.vel_l_rpm = MTR_GetVelocityRPM(MTR_LEFT);
        s_state.vel_r_rpm = MTR_GetVelocityRPM(MTR_RIGHT);
        float measured_vel = (s_state.vel_l_rpm + s_state.vel_r_rpm) * 0.5f;

        /* Position accumulation from encoder ticks */
        if (s_pos_reset_req) {
            s_pos_reset_req = 0U;
            s_enc_l_prev    = MTR_GetEncoderCount(MTR_LEFT);
            s_enc_r_prev    = MTR_GetEncoderCount(MTR_RIGHT);
            s_pos_cm        = 0.0f;
            s_traj_t        = 0.0f;
            PID_Reset(&s_pos_pid);
        } else {
            int32_t el = MTR_GetEncoderCount(MTR_LEFT);
            int32_t er = MTR_GetEncoderCount(MTR_RIGHT);
            s_pos_cm += (float)((el - s_enc_l_prev) + (er - s_enc_r_prev))
                        * (0.5f * POS_CM_PER_TICK);
            s_enc_l_prev = el;
            s_enc_r_prev = er;
        }

        /* Determine effective velocity setpoint */
        float effective_vel_sp;
        if (s_ctrl_mode == 1U) {
            /* Cas 1/3 — Position/trajectory mode */
            if (s_traj_mode == 1U) {
                s_traj_t += CONTROL_DT_S;
                if (s_traj_t >= s_traj_period_s) { s_traj_t -= s_traj_period_s; }
                s_pos_sp_cm = s_traj_amplitude
                              * sinf(2.0f * 3.14159265f * s_traj_t / s_traj_period_s);
            }
            effective_vel_sp = PID_Update(&s_pos_pid, s_pos_sp_cm, s_pos_cm);
            s_pos_vel_sp = effective_vel_sp;
        } else if (s_ctrl_mode == 3U) {
            /* Cas 4 — Auto-spin: balance at zero velocity */
            effective_vel_sp = 0.0f;
            s_pos_vel_sp     = 0.0f;
        } else {
            /* Cas 0 — Velocity mode: direct RPM setpoint */
            effective_vel_sp = s_target_vel_rpm;
            s_pos_vel_sp     = 0.0f;
        }

        float left_out, right_out, target_pitch_deg_out, drive_output_out;

        if (s_ctrl_mode == 2U) {
            /* Cas 2 — Direct drive (Ident K / Ident Td): both wheels driven
             * identically by the PC command, balance loop fully bypassed so
             * 'u' is a true exogenous input for the θ̈ = K·u + a·θ + c fit. */
            s_direct_drive_ticks++;
            if (s_direct_drive_ticks > DIRECT_DRIVE_HOLD_TICKS) {
                s_direct_drive = 0.0f;
            }
            left_out             = s_direct_drive;
            right_out            = s_direct_drive;
            target_pitch_deg_out = 0.0f;
            drive_output_out     = s_direct_drive;
            CBC_Reset(&s_cbc);   /* keep integrators clean for re-entry into normal mode */
        } else if (s_ctrl_mode == 4U) {
            /* Cas 4 — Angle direct: inner angle PID only, velocity PID bypassed.
             * The user directly sets target_pitch_deg; no outer velocity loop. */
            float pitch_err_meas = pitch_deg - s_angle_sp_offset;
            drive_output_out = PID_Update(&s_cbc.angle_pid,
                                          s_target_angle_deg,
                                          pitch_err_meas);
            if (drive_output_out >  s_cbc.max_drive_output) { drive_output_out =  s_cbc.max_drive_output; }
            if (drive_output_out < -s_cbc.max_drive_output) { drive_output_out = -s_cbc.max_drive_output; }
            target_pitch_deg_out = s_target_angle_deg;
            {
                float yaw4 = PID_Update(&s_cbc.yaw_pid, 0.0f, imu.gyro_y_dps);
                if (yaw4 >  s_cbc.max_yaw_output) { yaw4 =  s_cbc.max_yaw_output; }
                if (yaw4 < -s_cbc.max_yaw_output) { yaw4 = -s_cbc.max_yaw_output; }
                left_out  = drive_output_out + yaw4;
                if (left_out  >  1.0f) { left_out  =  1.0f; }
                if (left_out  < -1.0f) { left_out  = -1.0f; }
                right_out = drive_output_out - yaw4;
                if (right_out >  1.0f) { right_out =  1.0f; }
                if (right_out < -1.0f) { right_out = -1.0f; }
            }
        } else {
            /* Cascade balance: velocity outer loop → angle inner loop */
            CascadeBalanceOutput_t cbc_out = CBC_Update(&s_cbc,
                effective_vel_sp, measured_vel,
                pitch_deg - s_angle_sp_offset,
                0.0f, imu.gyro_y_dps);

            left_out             = cbc_out.left_output;
            right_out            = cbc_out.right_output;
            target_pitch_deg_out = cbc_out.target_pitch_deg;
            drive_output_out     = cbc_out.drive_output;

            /* Cas 4 — Spin management and yaw override */
            if (s_ctrl_mode == 3U) {
                s_spin_interval_timer += CONTROL_DT_S;

                if (s_spin_active) {
                    /* Spinning: override yaw with fixed differential, balance stays active */
                    left_out  = cbc_out.drive_output - s_spin_yaw_force;
                    right_out = cbc_out.drive_output + s_spin_yaw_force;
                    if (left_out  < -1.0f) { left_out  = -1.0f; }
                    if (left_out  >  1.0f) { left_out  =  1.0f; }
                    if (right_out < -1.0f) { right_out = -1.0f; }
                    if (right_out >  1.0f) { right_out =  1.0f; }

                    s_spin_angle_deg += imu.gyro_y_dps * CONTROL_DT_S;
                    if (s_spin_angle_deg >= 360.0f || s_spin_angle_deg <= -360.0f) {
                        s_spin_active    = 0U;
                        s_spin_angle_deg = 0.0f;
                    }
                } else if (s_spin_interval_timer >= s_spin_interval_s) {
                    /* Interval elapsed: start a new spin */
                    s_spin_interval_timer = 0.0f;
                    s_spin_angle_deg      = 0.0f;
                    s_spin_active         = 1U;
                }
            }
        }

        s_state.target_vel_rpm   = effective_vel_sp;
        s_state.target_pitch_deg = target_pitch_deg_out;
        s_state.drive_output     = drive_output_out;
        s_state.left_output      = left_out;
        s_state.right_output     = right_out;
        s_state.pos_cm           = s_pos_cm;
        s_state.pos_sp_cm        = s_pos_sp_cm;
        s_state.pos_vel_sp_rpm   = s_pos_vel_sp;
        s_state.ctrl_mode        = s_ctrl_mode;
        /* traj_mode doubles as spin_active when ctrl_mode == 3 */
        s_state.traj_mode        = (s_ctrl_mode == 3U) ? s_spin_active : s_traj_mode;
        s_state.spin_active      = s_spin_active;
        s_state.spin_angle_deg   = s_spin_angle_deg;

        MTR_SetDifferential(-left_out, -right_out);

        s_state.current_l_a = CURRENT_ALPHA * MTR_GetCurrentA(MTR_LEFT)
                            + (1.0f - CURRENT_ALPHA) * s_state.current_l_a;
        s_state.current_r_a = CURRENT_ALPHA * MTR_GetCurrentA(MTR_RIGHT)
                            + (1.0f - CURRENT_ALPHA) * s_state.current_r_a;

        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(CONTROL_TASK_PERIOD_MS));
    }
}

void Task_control_GetState(ControlState_t *out)
{
    out->pitch_deg        = s_state.pitch_deg;
    out->accel_x_g        = s_state.accel_x_g;
    out->accel_y_g        = s_state.accel_y_g;
    out->accel_z_g        = s_state.accel_z_g;
    out->gyro_x_dps       = s_state.gyro_x_dps;
    out->gyro_y_dps       = s_state.gyro_y_dps;
    out->gyro_z_dps       = s_state.gyro_z_dps;
    out->target_vel_rpm   = s_state.target_vel_rpm;
    out->target_pitch_deg = s_state.target_pitch_deg;
    out->drive_output     = s_state.drive_output;
    out->left_output      = s_state.left_output;
    out->right_output     = s_state.right_output;
    out->vel_l_rpm        = s_state.vel_l_rpm;
    out->vel_r_rpm        = s_state.vel_r_rpm;
    out->pos_cm           = s_state.pos_cm;
    out->pos_sp_cm        = s_state.pos_sp_cm;
    out->pos_vel_sp_rpm   = s_state.pos_vel_sp_rpm;
    out->ctrl_mode        = s_state.ctrl_mode;
    out->traj_mode        = s_state.traj_mode;
    out->calib_phase      = s_state.calib_phase;
    out->calib_active     = s_state.calib_active;
    out->spin_active      = s_state.spin_active;
    out->spin_angle_deg   = s_state.spin_angle_deg;
    out->current_l_a      = s_state.current_l_a;
    out->current_r_a      = s_state.current_r_a;
}

void Task_control_StartCalib(void)
{
    Calib_Build();
    s_calib_idx  = 0U;
    s_calib_tick = 0U;
    MTR_SetControlMode(MTR_LEFT,  MTR_MODE_DIRECT);
    MTR_SetControlMode(MTR_RIGHT, MTR_MODE_DIRECT);
    s_state.calib_active = 1U;
    s_calib_active       = 1U;
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
    switch (loop_id) {
    case 0U: CBC_SetAngleTunings(&s_cbc, kp, ki, kd);    break;
    case 1U: CBC_SetVelocityTunings(&s_cbc, kp, ki, kd); break;
    case 2U: CBC_SetYawTunings(&s_cbc, kp, ki, kd);      break;
    case 3U: PID_SetTunings(&s_pos_pid, kp, ki, kd);     break;
    default: break;
    }
}

void Task_control_SetVelocitySetpoint(float target_rpm)
{
    s_target_vel_rpm = target_rpm;
    s_ctrl_mode = 0U;  /* back to velocity mode */
}

void Task_control_SetDirectDrive(float drive_norm)
{
    if (drive_norm >  1.0f) { drive_norm =  1.0f; }
    if (drive_norm < -1.0f) { drive_norm = -1.0f; }
    s_direct_drive       = drive_norm;
    s_direct_drive_ticks = 0U;
    s_ctrl_mode          = 2U;
}

void Task_control_SetPositionSetpoint(float sp_cm)
{
    s_pos_sp_cm      = sp_cm;
    s_traj_mode      = 0U;   /* hold */
    s_pos_reset_req  = 1U;   /* reset origin at next cycle */
    s_ctrl_mode      = 1U;   /* switch to position mode */
}

void Task_control_SetSpinMode(uint8_t enable, float interval_s, float yaw_force)
{
    if (!enable) {
        s_ctrl_mode          = 0U;
        s_spin_active        = 0U;
        s_spin_angle_deg     = 0.0f;
        s_spin_interval_timer = 0.0f;
        return;
    }
    if (interval_s > 1.0f)  { s_spin_interval_s  = interval_s; }
    if (yaw_force  > 0.05f) { s_spin_yaw_force   = yaw_force;  }
    s_spin_active         = 0U;
    s_spin_angle_deg      = 0.0f;
    s_spin_interval_timer = 0.0f;  /* first spin after full interval */
    s_ctrl_mode           = 3U;
}

void Task_control_SetPositionTraj(uint8_t mode, float amplitude_cm, float period_s)
{
    s_traj_mode      = mode;
    s_traj_amplitude = amplitude_cm;
    s_traj_period_s  = (period_s > 0.1f) ? period_s : 0.1f;
    if (mode == VCP_TRAJ_HOLD) {
        s_pos_sp_cm = amplitude_cm;  /* amplitude_cm = target position for hold */
    }
    s_pos_reset_req = 1U;
    s_ctrl_mode     = 1U;
}

void Task_control_SetAngleOffset(float offset_deg)
{
    if (offset_deg >  5.0f) { offset_deg =  5.0f; }
    if (offset_deg < -5.0f) { offset_deg = -5.0f; }
    s_angle_sp_offset = offset_deg;
}

void Task_control_SetAngleDirect(float angle_deg)
{
    if (angle_deg >  8.0f) { angle_deg =  8.0f; }
    if (angle_deg < -8.0f) { angle_deg = -8.0f; }
    s_target_angle_deg = angle_deg;
    PID_Reset(&s_cbc.velocity_pid);
    PID_Reset(&s_pos_pid);
    s_ctrl_mode = 4U;
}

void Task_control_Init(void)
{
    AngleEstimator_Init(&s_angle_est, COMPLEMENTARY_ALPHA);

    CBC_Init(&s_cbc, CONTROL_DT_S);
    CBC_SetAngleTunings(&s_cbc, 0.241f, 0.00f, 0.00041f);
    CBC_SetLimits(&s_cbc, 8.0f, 1.0f, 0.3f);   /* max_angle=8°, max_drive=1.0, max_yaw=0.3 */
    PID_SetIntegralLimits(&s_cbc.angle_pid,    -0.3f, 0.3f);

    /* Velocity loop: enough gain to propagate position corrections through the cascade */
    CBC_SetVelocityTunings(&s_cbc, 0.05f, 0.005f, 0.0f);
    PID_SetIntegralLimits(&s_cbc.velocity_pid, -3.0f, 3.0f);

    /* Position loop: gentle start, output clamped to ±POS_VEL_SP_MAX_RPM */
    PID_Init(&s_pos_pid, 0.5f, 0.0f, 0.0f, CONTROL_DT_S,
             -POS_VEL_SP_MAX_RPM, POS_VEL_SP_MAX_RPM);
    PID_SetIntegralLimits(&s_pos_pid, -5.0f, 5.0f);

    s_state.calib_active = 0U;
    xTaskCreate(ControlTask, "Control", CONTROL_TASK_STACK_SIZE, NULL,
                CONTROL_TASK_PRIORITY, NULL);
}
