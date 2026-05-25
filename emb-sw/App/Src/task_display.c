/*
 * task_display.c
 */

#include "FreeRTOS.h"
#include "task.h"
#include "task_display.h"
#include "main.h"
#include "stm32wb5mm_dk.h"
#include "encoder.h"
#include "tof.h"
#include "env_sensor.h"
#include "stm32wb5mm_dk_motion_sensors.h"
#include "cpu_utils.h"
#include <math.h>
#include <stdio.h>
#include "motor_control.h"
#include "task_comms.h"

#define DISPLAY_TASK_STACK_SIZE  384U
#define DISPLAY_TASK_PRIORITY    (tskIDLE_PRIORITY + 1U)
#define DISPLAY_UPDATE_MS        100U

/* Measure wheel circumference and update this value. */
#define WHEEL_CIRCUMFERENCE_CM   22.0f
#define TICKS_PER_REV            1856
#define CM_PER_TICK              (WHEEL_CIRCUMFERENCE_CM / (float)TICKS_PER_REV)

/*
 * ToF graph — 300 samples at 100 ms = 30 s sliding window.
 * The 128-pixel wide area maps evenly across all 300 samples via integer
 * downsampling: pixel x shows the sample whose age is
 *   age = (GRAPH_W-1 - x) * (TOF_GRAPH_SAMPLES-1) / (GRAPH_W-1)  ticks ago.
 */
#define TOF_GRAPH_SAMPLES   300U    /* 300 × 100 ms = 30 s               */
#define GRAPH_W             128U    /* pixels wide (full screen)          */
#define GRAPH_Y_TOP         27U     /* top of the graph area              */
#define GRAPH_H             34U     /* height of the graph in pixels      */
#define GRAPH_BASELINE      (GRAPH_Y_TOP + GRAPH_H)   /* y=61             */
#define GRAPH_MAX_MM        1000U   /* full-scale = 100 cm                */

/* Motor screen: B1 steps STOP → 33/66/100% FWD → 33/66/100% BWD → BRAKE */
#define MOTOR_PRESET_COUNT  8U
#define MOTOR_PRESET_BRAKE  2.0f   /* sentinel — triggers MTR_Brake() */
static const float k_motor_presets[MOTOR_PRESET_COUNT] = {
    0.00f,  0.33f,  0.66f,  1.00f,
   -0.33f, -0.66f, -1.00f,  MOTOR_PRESET_BRAKE
};

/* Motor PWM bar geometry: label is 8 chars × 7 px = 56 px, bar starts at x=62 */
#define MBAR_X   62U
#define MBAR_W   64U
#define MBAR_H    9U

typedef enum {
    SCREEN_VCP_TUNER = 0,
    SCREEN_TOF_MOTOR,
    SCREEN_ENCODER,
    SCREEN_TOF,
    SCREEN_ENV,
    SCREEN_IMU,
    SCREEN_GYRO,
    SCREEN_SYSTEM,
    SCREEN_MOTOR_L,
    SCREEN_MOTOR_R,
    SCREEN_COUNT
} Screen_t;

static Screen_t s_screen        = SCREEN_VCP_TUNER;
static uint8_t  s_btn2_prev     = 1U;
static uint8_t  s_btn1_prev     = 1U;
static uint8_t  s_motor_preset_l = 0U;
static uint8_t  s_motor_preset_r = 0U;

/* ToF Motor screen state */
static uint8_t  s_tof_locked     = 0U;
static float    s_tof_speed_lock = 0.0f;
static int8_t   s_tof_direction  = 1;
static uint8_t  s_b1_hold        = 0U;
static uint8_t  s_b1_long_fired  = 0U;

/* Env sensor: session min/max */
static float s_temp_min =  999.0f;
static float s_temp_max = -999.0f;

/* IMU: normalized accel reference captured when B1 pressed (robot upright) */
static float   s_imu_ref_ax   = 0.0f;
static float   s_imu_ref_ay   = 0.0f;
static float   s_imu_ref_az   = 1.0f;
static uint8_t s_imu_calibrated = 0U;

/* ToF history ring buffer (stored in .bss, not on the task stack) */
static int16_t  s_graph[TOF_GRAPH_SAMPLES];
static uint16_t s_graph_head  = 0;   /* next write slot                  */
static uint16_t s_graph_count = 0;   /* samples stored so far (≤ 300)    */

static void DisplayTask(void *pvParameters);
static void Screen_DrawVcpTuner(void);
static void Screen_DrawEncoder(void);
static void Screen_DrawTof(int16_t dist_mm);
static void Screen_DrawEnv(float temp);
static void Screen_DrawImu(MOTION_SENSOR_Axes_t accel, uint8_t calibrated, float tilt_deg);
static void Screen_DrawGyro(MOTION_SENSOR_Axes_t gyro);
static void Screen_DrawSystem(void);
static void Screen_DrawMotorSingle(const char *title, float speed, float current_A);
static void Screen_DrawTofMotor(int16_t dist_mm, float speed, float current_A,
                                uint8_t locked, uint8_t hold_ticks);


void StartDisplayTask(void)
{
    xTaskCreate(DisplayTask, "Display", DISPLAY_TASK_STACK_SIZE, NULL,
                DISPLAY_TASK_PRIORITY, NULL);
}


static void Screen_DrawVcpTuner(void)
{
    char buf[22];
    BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);
    UTIL_LCD_SetFont(&Font12);

    /* Line 1 y=2 : stream status + shared setpoint */
    uint8_t  streaming = VCP_IsStreamActive();
    int16_t  sp        = VCP_GetSetpointRpm();
    const char *sym    = streaming ? ">>" : "==";
    snprintf(buf, sizeof(buf), "VCP %s Sp:%+5d", sym, (int)sp);
    UTIL_LCD_DisplayStringAt(2, 2, (uint8_t *)buf, LEFT_MODE);

    /* Line 2 y=14 : Kp / Ki of left motor (reference) */
    float kp = 0.0f, ki = 0.0f, kd = 0.0f;
    MTR_GetVelocityGains(MTR_LEFT, &kp, &ki, &kd);
    snprintf(buf, sizeof(buf), "Kp:%5.3f Ki:%5.3f", (double)kp, (double)ki);
    UTIL_LCD_DisplayStringAt(2, 14, (uint8_t *)buf, LEFT_MODE);

    /* Line 3 y=27 : left motor Pv + error */
    int pv_l = (int)MTR_GetCachedVelocityRPM(MTR_LEFT);
    int er_l = (int)sp - pv_l;
    snprintf(buf, sizeof(buf), "L Pv:%+4d Er:%+4d", pv_l, er_l);
    UTIL_LCD_DisplayStringAt(2, 27, (uint8_t *)buf, LEFT_MODE);

    /* Line 4 y=40 : right motor Pv + error */
    int pv_r = (int)MTR_GetCachedVelocityRPM(MTR_RIGHT);
    int er_r = (int)sp - pv_r;
    snprintf(buf, sizeof(buf), "R Pv:%+4d Er:%+4d", pv_r, er_r);
    UTIL_LCD_DisplayStringAt(2, 40, (uint8_t *)buf, LEFT_MODE);

    /* Line 5 y=52 : [OK] flash 500 ms after last cmd, B1=stream toggle */
    uint32_t age_ms = HAL_GetTick() - VCP_GetLastCmdTick();
    const char *ok  = (VCP_GetLastCmdTick() > 0U && age_ms < 500U) ? "[OK]" : "    ";
    snprintf(buf, sizeof(buf), "%sB1:%s B2:nxt",
             ok, streaming ? "stop" : "strm");
    UTIL_LCD_DisplayStringAt(2, 52, (uint8_t *)buf, LEFT_MODE);

    BSP_LCD_Refresh(0);
}

static void Screen_DrawEncoder(void)
{
    char buf[22];
    float right_cm = Encoder_GetDistanceCm(&g_enc_right);
    float left_cm  = Encoder_GetDistanceCm(&g_enc_left);

    BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);
    UTIL_LCD_SetFont(&Font12);

    UTIL_LCD_DisplayStringAt(0, 2, (uint8_t *)"Encoders", CENTER_MODE);

    snprintf(buf, sizeof(buf), "Right: %6.2f cm", right_cm);
    UTIL_LCD_DisplayStringAt(2, 18, (uint8_t *)buf, LEFT_MODE);

    snprintf(buf, sizeof(buf), "Left:  %6.2f cm", left_cm);
    UTIL_LCD_DisplayStringAt(2, 32, (uint8_t *)buf, LEFT_MODE);

    BSP_LCD_Refresh(0);
}

static void Screen_DrawTof(int16_t dist_mm)
{
    char buf[20];

    BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);
    UTIL_LCD_SetFont(&Font12);

    /* Title */
    UTIL_LCD_DisplayStringAt(0, 2, (uint8_t *)"ToF Distance", CENTER_MODE);

    /* Distance in cm with one decimal: 123 mm → "12.3 cm" */
    if (dist_mm < 0) {
        snprintf(buf, sizeof(buf), "Dist:  --.- cm");
    } else {
        snprintf(buf, sizeof(buf), "Dist: %2d.%1d cm",
                 dist_mm / 10, dist_mm % 10);
    }
    UTIL_LCD_DisplayStringAt(2, 14, (uint8_t *)buf, LEFT_MODE);

    /* Baseline */
    UTIL_LCD_DrawHLine(0, GRAPH_BASELINE, GRAPH_W, SSD1315_COLOR_WHITE);

    /* Graph bars — left=oldest, right=newest */
    for (uint32_t x = 0; x < GRAPH_W; x++) {
        /*
         * Map pixel column x to sample age in ticks:
         *   x=GRAPH_W-1 → age=0 (newest)
         *   x=0         → age=TOF_GRAPH_SAMPLES-1 (30 s ago)
         */
        uint32_t age = (GRAPH_W - 1U - x) * (TOF_GRAPH_SAMPLES - 1U)
                       / (GRAPH_W - 1U);

        if (age >= (uint32_t)s_graph_count) {
            continue;  /* this slot is in the future — not yet recorded */
        }

        uint32_t idx = (s_graph_head + TOF_GRAPH_SAMPLES - 1U - age)
                       % TOF_GRAPH_SAMPLES;
        int16_t val = s_graph[idx];

        if (val < 0) {
            continue;  /* invalid measurement */
        }

        uint32_t mm = (uint32_t)val;
        if (mm > GRAPH_MAX_MM) mm = GRAPH_MAX_MM;

        /* Scale to bar height; guarantee at least 1 px for any valid reading */
        uint32_t bar_h = mm * GRAPH_H / GRAPH_MAX_MM;
        if (bar_h == 0U) bar_h = 1U;

        UTIL_LCD_DrawVLine(x, GRAPH_BASELINE - bar_h, bar_h,
                           SSD1315_COLOR_WHITE);
    }

    BSP_LCD_Refresh(0);
}

static void Screen_DrawEnv(float temp)
{
    char buf[22];

    BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);
    UTIL_LCD_SetFont(&Font12);

    UTIL_LCD_DisplayStringAt(0, 2, (uint8_t *)"Environment", CENTER_MODE);

    if (temp <= -999.0f) {
        snprintf(buf, sizeof(buf), "Temp:    --- C");
    } else {
        snprintf(buf, sizeof(buf), "Temp:  %5.1f C", (double)temp);
    }
    UTIL_LCD_DisplayStringAt(2, 18, (uint8_t *)buf, LEFT_MODE);

    if (s_temp_min > 900.0f) {
        snprintf(buf, sizeof(buf), "Min: ---  Max: ---");
    } else {
        snprintf(buf, sizeof(buf), "Min:%4.1f Max:%4.1f",
                 (double)s_temp_min, (double)s_temp_max);
    }
    UTIL_LCD_DisplayStringAt(2, 32, (uint8_t *)buf, LEFT_MODE);

    BSP_LCD_Refresh(0);
}

static void Screen_DrawImu(MOTION_SENSOR_Axes_t accel, uint8_t calibrated, float tilt_deg)
{
    char buf[22];
    float ax = (float)accel.x / 1000.0f;
    float ay = (float)accel.y / 1000.0f;
    float az = (float)accel.z / 1000.0f;

    BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);
    UTIL_LCD_SetFont(&Font12);

    UTIL_LCD_DisplayStringAt(0, 2, (uint8_t *)"IMU", CENTER_MODE);

    snprintf(buf, sizeof(buf), "Ax: %+6.3f g", (double)ax);
    UTIL_LCD_DisplayStringAt(2, 14, (uint8_t *)buf, LEFT_MODE);

    snprintf(buf, sizeof(buf), "Ay: %+6.3f g", (double)ay);
    UTIL_LCD_DisplayStringAt(2, 26, (uint8_t *)buf, LEFT_MODE);

    snprintf(buf, sizeof(buf), "Az: %+6.3f g", (double)az);
    UTIL_LCD_DisplayStringAt(2, 38, (uint8_t *)buf, LEFT_MODE);

    if (!calibrated) {
        snprintf(buf, sizeof(buf), "Tilt: ---.- deg");
    } else {
        snprintf(buf, sizeof(buf), "Tilt: %5.1f deg", (double)tilt_deg);
    }
    UTIL_LCD_DisplayStringAt(2, 50, (uint8_t *)buf, LEFT_MODE);

    BSP_LCD_Refresh(0);
}

static void Screen_DrawGyro(MOTION_SENSOR_Axes_t gyro)
{
    char buf[22];
    float gx = (float)gyro.x / 1000.0f;
    float gy = (float)gyro.y / 1000.0f;
    float gz = (float)gyro.z / 1000.0f;
    float mag = sqrtf(gx*gx + gy*gy + gz*gz);

    BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);
    UTIL_LCD_SetFont(&Font12);

    UTIL_LCD_DisplayStringAt(0, 2, (uint8_t *)"Gyroscope", CENTER_MODE);

    snprintf(buf, sizeof(buf), "Gx: %+6.1f dps", (double)gx);
    UTIL_LCD_DisplayStringAt(2, 14, (uint8_t *)buf, LEFT_MODE);

    snprintf(buf, sizeof(buf), "Gy: %+6.1f dps", (double)gy);
    UTIL_LCD_DisplayStringAt(2, 26, (uint8_t *)buf, LEFT_MODE);

    snprintf(buf, sizeof(buf), "Gz: %+6.1f dps", (double)gz);
    UTIL_LCD_DisplayStringAt(2, 38, (uint8_t *)buf, LEFT_MODE);

    snprintf(buf, sizeof(buf), "|G|:%6.1f dps", (double)mag);
    UTIL_LCD_DisplayStringAt(2, 50, (uint8_t *)buf, LEFT_MODE);

    BSP_LCD_Refresh(0);
}

static void Screen_DrawSystem(void)
{
    char buf[22];
    size_t   heap_free = xPortGetFreeHeapSize();
    size_t   heap_min  = xPortGetMinimumEverFreeHeapSize();
    uint16_t cpu       = osGetCPUUsage();
    uint32_t secs      = xTaskGetTickCount() / configTICK_RATE_HZ;
    uint32_t mm        = secs / 60U;
    uint32_t ss        = secs % 60U;

    BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);
    UTIL_LCD_SetFont(&Font12);

    UTIL_LCD_DisplayStringAt(0, 2, (uint8_t *)"System", CENTER_MODE);

    snprintf(buf, sizeof(buf), "Heap: %5u B", (unsigned)heap_free);
    UTIL_LCD_DisplayStringAt(2, 14, (uint8_t *)buf, LEFT_MODE);

    snprintf(buf, sizeof(buf), "Min:  %5u B", (unsigned)heap_min);
    UTIL_LCD_DisplayStringAt(2, 26, (uint8_t *)buf, LEFT_MODE);

    snprintf(buf, sizeof(buf), "CPU:    %3u %%", (unsigned)cpu);
    UTIL_LCD_DisplayStringAt(2, 38, (uint8_t *)buf, LEFT_MODE);

    snprintf(buf, sizeof(buf), "Up:  %4u:%02u", (unsigned)mm, (unsigned)ss);
    UTIL_LCD_DisplayStringAt(2, 50, (uint8_t *)buf, LEFT_MODE);

    BSP_LCD_Refresh(0);
}

static void Screen_DrawMotorSingle(const char *title, float speed, float current_A)
{
    char buf[22];

    BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);
    UTIL_LCD_SetFont(&Font12);

    UTIL_LCD_DisplayStringAt(0, 2, (uint8_t *)title, CENTER_MODE);

    if (speed >= MOTOR_PRESET_BRAKE) {
        UTIL_LCD_DisplayStringAt(0, 16, (uint8_t *)"[ BRAKE ]", CENTER_MODE);
    } else {
        int pct = (int)(speed * 100.0f);
        if (speed > 0.01f) {
            snprintf(buf, sizeof(buf), "FWD%4d%%", pct);
        } else if (speed < -0.01f) {
            snprintf(buf, sizeof(buf), "BWD%4d%%", -pct);
        } else {
            snprintf(buf, sizeof(buf), "STOP");
        }
        UTIL_LCD_DisplayStringAt(2, 16, (uint8_t *)buf, LEFT_MODE);

        uint32_t fill = (uint32_t)((float)(MBAR_W - 2U) * fabsf(speed));
        UTIL_LCD_DrawRect(MBAR_X, 17U, MBAR_W, MBAR_H, SSD1315_COLOR_WHITE);
        if (fill > 0U) {
            UTIL_LCD_FillRect(MBAR_X + 1U, 18U, fill, MBAR_H - 2U, SSD1315_COLOR_WHITE);
        }
    }

    snprintf(buf, sizeof(buf), "Curr: %5.3f A", (double)current_A);
    UTIL_LCD_DisplayStringAt(2, 32, (uint8_t *)buf, LEFT_MODE);

    UTIL_LCD_DisplayStringAt(2, 52, (uint8_t *)"B1:step  B2:next", LEFT_MODE);

    BSP_LCD_Refresh(0);
}

/* Maps ToF distance to a proximity speed magnitude [0.0 .. 1.0].
 * < 50 mm → 1.0 (clamp), 50–500 mm → linear, > 500 mm → 0.0. */
static float Tof_ToSpeed(int16_t dist_mm)
{
    if (dist_mm < 0)    return 0.0f;
    if (dist_mm < 50)   return 1.0f;
    if (dist_mm > 500)  return 0.0f;
    return 1.0f - (float)(dist_mm - 50) / 450.0f;
}

static void Screen_DrawTofMotor(int16_t dist_mm, float speed, float current_A,
                                uint8_t locked, uint8_t hold_ticks)
{
    char buf[22];

    BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);
    UTIL_LCD_SetFont(&Font12);

    /* Line 1 y=2 : distance ToF + consigne RPM commune */
    int sp_rpm = (int)(speed * (float)MTR_MAX_RPM);
    if (dist_mm < 0 || dist_mm > 9999) {
        snprintf(buf, sizeof(buf), "ToF ---mm Sp:%+4d", sp_rpm);
    } else {
        uint16_t d = (dist_mm > 999) ? 999U : (uint16_t)dist_mm;
        snprintf(buf, sizeof(buf), "ToF %3umm Sp:%+4d", (unsigned)d, sp_rpm);
    }
    UTIL_LCD_DisplayStringAt(2, 2, (uint8_t *)buf, LEFT_MODE);

    /* Line 2 y=14 : moteur gauche — Pv et erreur */
    int pv_l = (int)MTR_GetCachedVelocityRPM(MTR_LEFT);
    int er_l  = sp_rpm - pv_l;
    snprintf(buf, sizeof(buf), "L Pv:%+4d Er:%+4d", pv_l, er_l);
    UTIL_LCD_DisplayStringAt(2, 14, (uint8_t *)buf, LEFT_MODE);

    /* Line 3 y=27 : moteur droit — Pv et erreur */
    int pv_r = (int)MTR_GetCachedVelocityRPM(MTR_RIGHT);
    int er_r  = sp_rpm - pv_r;
    snprintf(buf, sizeof(buf), "R Pv:%+4d Er:%+4d", pv_r, er_r);
    UTIL_LCD_DisplayStringAt(2, 27, (uint8_t *)buf, LEFT_MODE);

    /* Line 4 y=40 : bargraph de la commande (centre=0, FWD→droite, BWD→gauche) */
    float abs_speed = fabsf(speed);
    UTIL_LCD_DrawRect(0U, 40U, 128U, 9U, SSD1315_COLOR_WHITE);
    UTIL_LCD_DrawVLine(63U, 41U, 7U, SSD1315_COLOR_WHITE);
    if (abs_speed > 0.01f) {
        uint32_t fill = (uint32_t)(abs_speed * 62.0f);
        if (fill > 62U) fill = 62U;
        if (speed > 0.0f) {
            UTIL_LCD_FillRect(64U, 41U, fill, 7U, SSD1315_COLOR_WHITE);
        } else {
            UTIL_LCD_FillRect(63U - fill, 41U, fill, 7U, SSD1315_COLOR_WHITE);
        }
    }

    /* Line 5 y=52 : courant + indicateur LIVE/LOCK + action B1
     * >> = LIVE (données qui coulent)   == = LOCK (figé) */
    const char *mode_sym = locked ? "==" : ">>";
    if (hold_ticks > 0U && hold_ticks < 5U) {
        char prog[6];
        for (uint8_t i = 0U; i < 5U; i++) {
            prog[i] = (i < hold_ticks) ? '#' : '-';
        }
        prog[5] = '\0';
        snprintf(buf, sizeof(buf), "%4.2fA %s[%s]",
                 (double)current_A, mode_sym, prog);
    } else if (hold_ticks >= 5U) {
        snprintf(buf, sizeof(buf), "%4.2fA %s[DIR!]",
                 (double)current_A, mode_sym);
    } else {
        snprintf(buf, sizeof(buf), "%4.2fA %sB1:%s",
                 (double)current_A, mode_sym,
                 locked ? "unlk" : "lock");
    }
    UTIL_LCD_DisplayStringAt(2, 52, (uint8_t *)buf, LEFT_MODE);

    BSP_LCD_Refresh(0);
}

static void DisplayTask(void *pvParameters)
{
    (void)pvParameters;

    TickType_t last_wake   = xTaskGetTickCount();
    Screen_t   last_screen = SCREEN_COUNT;  /* force first draw */
    int32_t    last_right  = 0;
    int32_t    last_left   = 0;

    for (;;) {
        /* B2: advance to the next screen (edge-triggered). */
        if (BSP_PB_GetState(BUTTON_USER2) == GPIO_PIN_RESET) {
            if (s_btn2_prev == 1U) {
                s_screen = (s_screen + 1U) % SCREEN_COUNT;
            }
            s_btn2_prev = 0U;
        } else {
            s_btn2_prev = 1U;
        }

        /* Coast the motor and reset its preset when leaving a motor screen. */
        if (s_screen != last_screen) {
            if (last_screen == SCREEN_MOTOR_L) {
                MTR_Coast(MTR_LEFT);
                s_motor_preset_l = 0U;
            } else if (last_screen == SCREEN_MOTOR_R) {
                MTR_Coast(MTR_RIGHT);
                s_motor_preset_r = 0U;
            } else if (last_screen == SCREEN_TOF_MOTOR) {
                MTR_Coast(MTR_LEFT);
                MTR_Coast(MTR_RIGHT);
                s_tof_locked    = 0U;
                s_tof_direction = 1;
                s_b1_hold       = 0U;
                s_b1_long_fired = 0U;
            } else if (last_screen == SCREEN_VCP_TUNER) {
                VCP_SetStreamActive(0U);
                MTR_Coast(MTR_LEFT);
                MTR_Coast(MTR_RIGHT);
            }
        }

        switch (s_screen) {
            case SCREEN_VCP_TUNER: {
                uint8_t b1_now = BSP_PB_GetState(BUTTON_USER1);

                /* On entry: enable velocity mode on both motors */
                if (s_screen != last_screen) {
                    s_btn1_prev = (b1_now == GPIO_PIN_RESET) ? 0U : 1U;
                    MTR_SetControlMode(MTR_LEFT,  MTR_MODE_VELOCITY);
                    MTR_SetControlMode(MTR_RIGHT, MTR_MODE_VELOCITY);
                }

                /* B1 short press: toggle streaming */
                if (b1_now != GPIO_PIN_RESET && s_btn1_prev == 0U) {
                    VCP_SetStreamActive(VCP_IsStreamActive() ? 0U : 1U);
                }
                s_btn1_prev = (b1_now == GPIO_PIN_RESET) ? 0U : 1U;

                Screen_DrawVcpTuner();
                break;
            }

            case SCREEN_ENCODER: {
                if (BSP_PB_GetState(BUTTON_USER1) == GPIO_PIN_RESET) {
                    Encoder_Reset(&g_enc_right);
                    Encoder_Reset(&g_enc_left);
                }
                int32_t r = Encoder_GetRaw(&g_enc_right);
                int32_t l = Encoder_GetRaw(&g_enc_left);
                if (s_screen != last_screen || r != last_right || l != last_left) {
                    Screen_DrawEncoder();
                    last_right = r;
                    last_left  = l;
                }
                break;
            }

            case SCREEN_TOF: {
                int16_t dist = Tof_GetDistanceMm();

                /* Append to ring buffer */
                s_graph[s_graph_head] = dist;
                s_graph_head = (s_graph_head + 1U) % TOF_GRAPH_SAMPLES;
                if (s_graph_count < TOF_GRAPH_SAMPLES) s_graph_count++;

                /* Always redraw — graph changes every tick */
                Screen_DrawTof(dist);
                break;
            }

            case SCREEN_ENV: {
                float temp = EnvSensor_GetTemperatureC();
                if (temp > -999.0f) {
                    if (temp < s_temp_min) s_temp_min = temp;
                    if (temp > s_temp_max) s_temp_max = temp;
                }
                /* B1: reset session min/max */
                if (BSP_PB_GetState(BUTTON_USER1) == GPIO_PIN_RESET) {
                    s_temp_min =  999.0f;
                    s_temp_max = -999.0f;
                }
                Screen_DrawEnv(temp);
                break;
            }

            case SCREEN_IMU: {
                MOTION_SENSOR_Axes_t accel = {0};
                BSP_MOTION_SENSOR_GetAxes(MOTION_SENSOR_ISM330DHCX_0,
                                          MOTION_ACCELERO, &accel);

                float ax = (float)accel.x / 1000.0f;
                float ay = (float)accel.y / 1000.0f;
                float az = (float)accel.z / 1000.0f;

                /* B1: capture current accel vector as the vertical reference */
                if (BSP_PB_GetState(BUTTON_USER1) == GPIO_PIN_RESET) {
                    float mag = sqrtf(ax*ax + ay*ay + az*az);
                    if (mag > 0.1f) {
                        s_imu_ref_ax = ax / mag;
                        s_imu_ref_ay = ay / mag;
                        s_imu_ref_az = az / mag;
                        s_imu_calibrated = 1U;
                    }
                }

                float tilt_deg = 0.0f;
                if (s_imu_calibrated) {
                    float mag = sqrtf(ax*ax + ay*ay + az*az);
                    if (mag > 0.1f) {
                        float dot = (ax/mag)*s_imu_ref_ax
                                  + (ay/mag)*s_imu_ref_ay
                                  + (az/mag)*s_imu_ref_az;
                        if (dot >  1.0f) dot =  1.0f;
                        if (dot < -1.0f) dot = -1.0f;
                        tilt_deg = acosf(dot) * (180.0f / 3.14159265f);
                    }
                }

                Screen_DrawImu(accel, s_imu_calibrated, tilt_deg);
                break;
            }

            case SCREEN_GYRO: {
                MOTION_SENSOR_Axes_t gyro = {0};
                BSP_MOTION_SENSOR_GetAxes(MOTION_SENSOR_ISM330DHCX_0,
                                          MOTION_GYRO, &gyro);
                Screen_DrawGyro(gyro);
                break;
            }

            case SCREEN_SYSTEM: {
                Screen_DrawSystem();
                break;
            }

            case SCREEN_MOTOR_L: {
                uint8_t b1_now = BSP_PB_GetState(BUTTON_USER1);
                if (s_screen != last_screen) {
                    s_btn1_prev = (b1_now == GPIO_PIN_RESET) ? 0U : 1U;
                }
                if (b1_now == GPIO_PIN_RESET && s_btn1_prev == 1U) {
                    s_motor_preset_l = (s_motor_preset_l + 1U) % MOTOR_PRESET_COUNT;
                    float spd = k_motor_presets[s_motor_preset_l];
                    if (spd >= MOTOR_PRESET_BRAKE) {
                        MTR_Brake(MTR_LEFT);
                    } else {
                        MTR_SetSpeed(MTR_LEFT, spd);
                    }
                }
                s_btn1_prev = (b1_now == GPIO_PIN_RESET) ? 0U : 1U;
                Screen_DrawMotorSingle("Motor Left",
                                       k_motor_presets[s_motor_preset_l],
                                       MTR_GetCurrentA(MTR_LEFT));
                break;
            }

            case SCREEN_MOTOR_R: {
                uint8_t b1_now = BSP_PB_GetState(BUTTON_USER1);
                if (s_screen != last_screen) {
                    s_btn1_prev = (b1_now == GPIO_PIN_RESET) ? 0U : 1U;
                }
                if (b1_now == GPIO_PIN_RESET && s_btn1_prev == 1U) {
                    s_motor_preset_r = (s_motor_preset_r + 1U) % MOTOR_PRESET_COUNT;
                    float spd = k_motor_presets[s_motor_preset_r];
                    if (spd >= MOTOR_PRESET_BRAKE) {
                        MTR_Brake(MTR_RIGHT);
                    } else {
                        MTR_SetSpeed(MTR_RIGHT, spd);
                    }
                }
                s_btn1_prev = (b1_now == GPIO_PIN_RESET) ? 0U : 1U;
                Screen_DrawMotorSingle("Motor Right",
                                       k_motor_presets[s_motor_preset_r],
                                       MTR_GetCurrentA(MTR_RIGHT));
                break;
            }

            case SCREEN_TOF_MOTOR: {
                uint8_t b1_now = BSP_PB_GetState(BUTTON_USER1);

                /* Reset state on screen entry */
                if (s_screen != last_screen) {
                    s_tof_locked    = 0U;
                    s_tof_direction = 1;
                    s_b1_hold       = 0U;
                    s_b1_long_fired = 0U;
                    s_btn1_prev = (b1_now == GPIO_PIN_RESET) ? 0U : 1U;
                    MTR_SetControlMode(MTR_LEFT,  MTR_MODE_VELOCITY);
                    MTR_SetControlMode(MTR_RIGHT, MTR_MODE_VELOCITY);
                }

                /* Long / short press detection */
                if (b1_now == GPIO_PIN_RESET) {
                    if (s_b1_hold < 255U) {
                        s_b1_hold++;
                    }
                    /* Long press at 500 ms (5 ticks × 100 ms): flip direction */
                    if (s_b1_hold == 5U && !s_b1_long_fired) {
                        s_tof_direction = -s_tof_direction;
                        if (s_tof_locked) {
                            s_tof_speed_lock = -s_tof_speed_lock;
                        }
                        s_b1_long_fired = 1U;
                    }
                } else {
                    /* Released — short press toggles lock */
                    if (s_b1_hold > 0U && s_b1_hold < 5U) {
                        if (s_tof_locked) {
                            s_tof_locked = 0U;
                        } else {
                            int16_t d        = Tof_GetDistanceMm();
                            s_tof_speed_lock = (float)s_tof_direction * Tof_ToSpeed(d);
                            s_tof_locked     = 1U;
                        }
                    }
                    s_b1_hold       = 0U;
                    s_b1_long_fired = 0U;
                }
                s_btn1_prev = (b1_now == GPIO_PIN_RESET) ? 0U : 1U;

                /* Compute speed from ToF or frozen lock */
                int16_t dist = Tof_GetDistanceMm();
                float   speed_tof = s_tof_locked
                                  ? s_tof_speed_lock
                                  : (float)s_tof_direction * Tof_ToSpeed(dist);

                MTR_SetDifferential(speed_tof, speed_tof);

                float i_avg = (MTR_GetCurrentA(MTR_LEFT) + MTR_GetCurrentA(MTR_RIGHT)) * 0.5f;
                Screen_DrawTofMotor(dist, speed_tof, i_avg, s_tof_locked, s_b1_hold);
                break;
            }

            default:
                break;
        }

        last_screen = s_screen;
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(DISPLAY_UPDATE_MS));
    }
}
