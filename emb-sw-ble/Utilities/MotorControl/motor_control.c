/**
 ******************************************************************************
 * @file    motor_control.c
 * @brief   DC Motor Control — self-contained init (no CubeMX extern handles).
 *          Initializes LPTIM1 (PWM left/PC1), TIM16 (PWM right/PE0),
 *          TIM1/TIM2 (QEI encoders), and DIR/BRAKE GPIOs internally.
 *          ADC current sensing stubbed (step 4c).
 ******************************************************************************
 */

#include "motor_control.h"
#include "pid_controller.h"
#include "main.h"          /* Error_Handler */
#include <stddef.h>

/* ============================================================================
 * Private HAL handles — self-contained, no CubeMX extern references
 * ============================================================================ */
static LPTIM_HandleTypeDef hlptim1;   /* PWM gauche  PC1  */
static TIM_HandleTypeDef   htim16;    /* PWM droit   PE0  */
static TIM_HandleTypeDef   htim1;     /* encodeur gauche  */
static TIM_HandleTypeDef   htim2;     /* encodeur droit   */

/* ============================================================================
 * Contexte interne
 * ============================================================================ */
typedef struct
{
    uint8_t  initialized;
    uint8_t  emergency_active;

    float    deadband[2];
    float    current_limit_A[2];
    float    dz_fwd[2];
    float    dz_rev[2];

    float    tilt_cutoff_deg;

    int32_t  enc_accum[2];
    uint16_t enc_prev_raw[2];

    int32_t  enc_vel_ref[2];
    uint32_t enc_vel_tick[2];

    MTR_ControlMode_t control_mode[2];
    float             vel_setpoint_rpm[2];
    float             vel_rpm_cached[2];
    PID_Controller_t  vel_pid[2];
} MTR_Context_t;

static MTR_Context_t mtr;

/* ADC stubbed — channel values unused but array kept for API compatibility */
static const uint32_t MTR_AdcChannel[2] = { 0U, 0U };

/* ============================================================================
 * Private peripheral init functions
 * ============================================================================ */

static void MTR_GPIO_Motor_Init(void)
{
    GPIO_InitTypeDef gpio = {0};

    /* PC1 → LPTIM1_OUT (AF1) — reconfigure from ANALOG */
    gpio.Pin       = GPIO_PIN_1;
    gpio.Mode      = GPIO_MODE_AF_PP;
    gpio.Pull      = GPIO_NOPULL;
    gpio.Speed     = GPIO_SPEED_FREQ_LOW;
    gpio.Alternate = GPIO_AF1_LPTIM1;
    HAL_GPIO_Init(GPIOC, &gpio);

    /* PD12 (DIR gauche), PD13 (BRAKE gauche) → GPIO Output */
    gpio.Pin       = MTR_DIR_LEFT_PIN | MTR_BRAKE_LEFT_PIN;
    gpio.Mode      = GPIO_MODE_OUTPUT_PP;
    gpio.Pull      = GPIO_NOPULL;
    gpio.Alternate = 0;
    HAL_GPIO_Init(GPIOD, &gpio);
    HAL_GPIO_WritePin(GPIOD, MTR_DIR_LEFT_PIN | MTR_BRAKE_LEFT_PIN, GPIO_PIN_RESET);

    /* PE4 (DIR droit) → GPIO Output */
    gpio.Pin = MTR_DIR_RIGHT_PIN;
    HAL_GPIO_Init(GPIOE, &gpio);
    HAL_GPIO_WritePin(GPIOE, MTR_DIR_RIGHT_PIN, GPIO_PIN_RESET);

    /* PB2 (BRAKE droit) → GPIO Output */
    gpio.Pin = MTR_BRAKE_RIGHT_PIN;
    HAL_GPIO_Init(GPIOB, &gpio);
    HAL_GPIO_WritePin(GPIOB, MTR_BRAKE_RIGHT_PIN, GPIO_PIN_RESET);
}

static void MTR_LPTIM1_Init(void)
{
    __HAL_RCC_LPTIM1_CLK_ENABLE();

    hlptim1.Instance             = LPTIM1;
    hlptim1.Init.Clock.Source    = LPTIM_CLOCKSOURCE_APBCLOCK_LPOSC;
    hlptim1.Init.Clock.Prescaler = LPTIM_PRESCALER_DIV1;
    hlptim1.Init.Trigger.Source  = LPTIM_TRIGSOURCE_SOFTWARE;
    hlptim1.Init.OutputPolarity  = LPTIM_OUTPUTPOLARITY_HIGH;
    hlptim1.Init.UpdateMode      = LPTIM_UPDATE_IMMEDIATE;
    hlptim1.Init.CounterSource   = LPTIM_COUNTERSOURCE_INTERNAL;
    hlptim1.Init.Input1Source    = LPTIM_INPUT1SOURCE_GPIO;
    hlptim1.Init.Input2Source    = LPTIM_INPUT2SOURCE_GPIO;
    if (HAL_LPTIM_Init(&hlptim1) != HAL_OK) { Error_Handler(); }
}

static void MTR_TIM16_Init(void)
{
    TIM_OC_InitTypeDef              oc  = {0};
    TIM_BreakDeadTimeConfigTypeDef  bdt = {0};

    __HAL_RCC_TIM16_CLK_ENABLE();

    /* PE0 already configured as GPIO_AF14_TIM16 in MX_GPIO_Init */

    htim16.Instance               = TIM16;
    htim16.Init.Prescaler         = 0;
    htim16.Init.CounterMode       = TIM_COUNTERMODE_UP;
    htim16.Init.Period            = MTR_PWM_PERIOD - 1U;
    htim16.Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    htim16.Init.RepetitionCounter = 0;
    htim16.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
    if (HAL_TIM_PWM_Init(&htim16) != HAL_OK) { Error_Handler(); }

    oc.OCMode       = TIM_OCMODE_PWM1;
    oc.Pulse        = 0;
    oc.OCPolarity   = TIM_OCPOLARITY_HIGH;
    oc.OCNPolarity  = TIM_OCNPOLARITY_HIGH;
    oc.OCFastMode   = TIM_OCFAST_DISABLE;
    oc.OCIdleState  = TIM_OCIDLESTATE_RESET;
    oc.OCNIdleState = TIM_OCNIDLESTATE_RESET;
    if (HAL_TIM_PWM_ConfigChannel(&htim16, &oc, MTR_PWM_CH_RIGHT) != HAL_OK) { Error_Handler(); }

    bdt.OffStateRunMode  = TIM_OSSR_DISABLE;
    bdt.OffStateIDLEMode = TIM_OSSI_DISABLE;
    bdt.LockLevel        = TIM_LOCKLEVEL_OFF;
    bdt.DeadTime         = 0;
    bdt.BreakState       = TIM_BREAK_DISABLE;
    bdt.BreakPolarity    = TIM_BREAKPOLARITY_HIGH;
    bdt.AutomaticOutput  = TIM_AUTOMATICOUTPUT_DISABLE;
    if (HAL_TIMEx_ConfigBreakDeadTime(&htim16, &bdt) != HAL_OK) { Error_Handler(); }
}

static void MTR_TIM1_QEI_Init(void)
{
    TIM_Encoder_InitTypeDef enc  = {0};
    GPIO_InitTypeDef        gpio = {0};

    __HAL_RCC_TIM1_CLK_ENABLE();
    __HAL_RCC_GPIOD_CLK_ENABLE();

    /* PD14=TIM1_CH1, PD15=TIM1_CH2 — already AF1 from MX_GPIO_Init, reconfigure to PULLUP */
    gpio.Pin       = GPIO_PIN_14 | GPIO_PIN_15;
    gpio.Mode      = GPIO_MODE_AF_PP;
    gpio.Pull      = GPIO_PULLUP;
    gpio.Speed     = GPIO_SPEED_FREQ_MEDIUM;
    gpio.Alternate = GPIO_AF1_TIM1;
    HAL_GPIO_Init(GPIOD, &gpio);

    htim1.Instance               = TIM1;
    htim1.Init.Prescaler         = 0;
    htim1.Init.CounterMode       = TIM_COUNTERMODE_UP;
    htim1.Init.Period            = 0xFFFFU;
    htim1.Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    htim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;

    enc.EncoderMode  = TIM_ENCODERMODE_TI12;
    enc.IC1Polarity  = TIM_ICPOLARITY_RISING;
    enc.IC1Selection = TIM_ICSELECTION_DIRECTTI;
    enc.IC1Prescaler = TIM_ICPSC_DIV1;
    enc.IC1Filter    = 4U;
    enc.IC2Polarity  = TIM_ICPOLARITY_RISING;
    enc.IC2Selection = TIM_ICSELECTION_DIRECTTI;
    enc.IC2Prescaler = TIM_ICPSC_DIV1;
    enc.IC2Filter    = 4U;

    if (HAL_TIM_Encoder_Init(&htim1, &enc) != HAL_OK) { Error_Handler(); }
    HAL_TIM_Encoder_Start(&htim1, TIM_CHANNEL_ALL);
}

static void MTR_TIM2_QEI_Init(void)
{
    TIM_Encoder_InitTypeDef enc  = {0};
    GPIO_InitTypeDef        gpio = {0};

    __HAL_RCC_TIM2_CLK_ENABLE();
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();

    /* PA15=TIM2_CH1 — already AF1 from MX_GPIO_Init, reconfigure to PULLUP */
    gpio.Pin       = GPIO_PIN_15;
    gpio.Mode      = GPIO_MODE_AF_PP;
    gpio.Pull      = GPIO_PULLUP;
    gpio.Speed     = GPIO_SPEED_FREQ_MEDIUM;
    gpio.Alternate = GPIO_AF1_TIM2;
    HAL_GPIO_Init(GPIOA, &gpio);

    /* PB3=TIM2_CH2 (overrides SWO trace) */
    gpio.Pin = GPIO_PIN_3;
    HAL_GPIO_Init(GPIOB, &gpio);

    htim2.Instance               = TIM2;
    htim2.Init.Prescaler         = 0;
    htim2.Init.CounterMode       = TIM_COUNTERMODE_UP;
    htim2.Init.Period            = 0xFFFFFFFFU;
    htim2.Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;

    enc.EncoderMode  = TIM_ENCODERMODE_TI12;
    enc.IC1Polarity  = TIM_ICPOLARITY_RISING;
    enc.IC1Selection = TIM_ICSELECTION_DIRECTTI;
    enc.IC1Prescaler = TIM_ICPSC_DIV1;
    enc.IC1Filter    = 4U;
    enc.IC2Polarity  = TIM_ICPOLARITY_RISING;
    enc.IC2Selection = TIM_ICSELECTION_DIRECTTI;
    enc.IC2Prescaler = TIM_ICPSC_DIV1;
    enc.IC2Filter    = 4U;

    if (HAL_TIM_Encoder_Init(&htim2, &enc) != HAL_OK) { Error_Handler(); }
    HAL_TIM_Encoder_Start(&htim2, TIM_CHANNEL_ALL);
}

/* ADC current sensing — stubbed until step 4d */
static float MTR_ReadADC_V(uint32_t channel)
{
    (void)channel;
    return 0.0f;
}

/* ============================================================================
 * Private helpers
 * ============================================================================ */

static void MTR_AccumulateEncoder(MTR_Id_t motor)
{
    TIM_HandleTypeDef *htim = (motor == MTR_LEFT) ? &htim1 : &htim2;

    uint16_t curr  = (uint16_t)__HAL_TIM_GET_COUNTER(htim);
    int16_t  delta = (int16_t)(curr - mtr.enc_prev_raw[motor]);

    if (motor == MTR_LEFT) { delta = -delta; }

    mtr.enc_accum[motor]   += (int32_t)delta;
    mtr.enc_prev_raw[motor] = curr;
}

static void MTR_ApplyPWM(MTR_Id_t motor, MTR_Speed_t speed)
{
    GPIO_TypeDef *dir_port   = (motor == MTR_LEFT) ? MTR_DIR_LEFT_PORT   : MTR_DIR_RIGHT_PORT;
    uint16_t      dir_pin    = (motor == MTR_LEFT) ? MTR_DIR_LEFT_PIN    : MTR_DIR_RIGHT_PIN;
    GPIO_TypeDef *brake_port = (motor == MTR_LEFT) ? MTR_BRAKE_LEFT_PORT : MTR_BRAKE_RIGHT_PORT;
    uint16_t      brake_pin  = (motor == MTR_LEFT) ? MTR_BRAKE_LEFT_PIN  : MTR_BRAKE_RIGHT_PIN;

    if (speed > -0.01f && speed < 0.01f)
    {
        if (motor == MTR_LEFT) {
            __HAL_LPTIM_COMPARE_SET(&hlptim1, MTR_PWM_PERIOD - 1U);
        } else {
            __HAL_TIM_SET_COMPARE(&htim16, MTR_PWM_CH_RIGHT, 0U);
        }
        HAL_GPIO_WritePin(brake_port, brake_pin, GPIO_PIN_RESET);
        return;
    }

    float abs_speed = (speed >= 0.0f) ? speed : -speed;
    float comp;
    if (speed > 0.0f) {
        comp = mtr.dz_fwd[motor] + (1.0f - mtr.dz_fwd[motor]) * speed;
    } else {
        comp = -(mtr.dz_rev[motor] + (1.0f - mtr.dz_rev[motor]) * abs_speed);
    }
    if (comp >  1.0f) { comp =  1.0f; }
    if (comp < -1.0f) { comp = -1.0f; }
    abs_speed = (comp >= 0.0f) ? comp : -comp;

    HAL_GPIO_WritePin(brake_port, brake_pin, GPIO_PIN_RESET);

    GPIO_PinState fwd = (motor == MTR_LEFT) ? MTR_DIR_FWD_LEFT : MTR_DIR_FWD_RIGHT;
    GPIO_PinState bwd = (fwd == GPIO_PIN_SET) ? GPIO_PIN_RESET : GPIO_PIN_SET;
    HAL_GPIO_WritePin(dir_port, dir_pin, (comp >= 0.0f) ? fwd : bwd);

    uint32_t compare = (uint32_t)(abs_speed * (float)(MTR_PWM_PERIOD - 1U));
    if (compare >= MTR_PWM_PERIOD) { compare = MTR_PWM_PERIOD - 1U; }

    if (motor == MTR_LEFT) {
        __HAL_LPTIM_COMPARE_SET(&hlptim1, (MTR_PWM_PERIOD - 1U) - compare);
    } else {
        __HAL_TIM_SET_COMPARE(&htim16, MTR_PWM_CH_RIGHT, compare);
    }
}

/* ============================================================================
 * Groupe 1 — Init & commande de base
 * ============================================================================ */

MTR_Status_t MTR_Init(void)
{
    mtr.initialized      = 0U;
    mtr.emergency_active = 0U;
    mtr.tilt_cutoff_deg  = MTR_DEFAULT_TILT_CUTOFF_DEG;

    for (int i = 0; i < 2; i++)
    {
        mtr.deadband[i]         = MTR_DEFAULT_DEADBAND;
        mtr.current_limit_A[i]  = MTR_DEFAULT_CURRENT_LIMIT_A;
        mtr.dz_fwd[i]           = MTR_DEFAULT_DZ_FWD;
        mtr.dz_rev[i]           = MTR_DEFAULT_DZ_REV;
        mtr.enc_accum[i]        = 0;
        mtr.enc_prev_raw[i]     = 0U;
        mtr.enc_vel_ref[i]      = 0;
        mtr.enc_vel_tick[i]     = 0U;
        mtr.control_mode[i]     = MTR_MODE_DIRECT;
        mtr.vel_setpoint_rpm[i] = 0.0f;
        mtr.vel_rpm_cached[i]   = 0.0f;

        PID_Init(&mtr.vel_pid[i],
                 MTR_VEL_KP_DEFAULT, MTR_VEL_KI_DEFAULT, MTR_VEL_KD_DEFAULT,
                 MTR_VEL_SAMPLE_TIME_S, -1.0f, 1.0f);
        PID_SetIntegralLimits(&mtr.vel_pid[i], -0.9f, 0.9f);
    }

    /* Init peripherals */
    MTR_GPIO_Motor_Init();
    MTR_LPTIM1_Init();
    MTR_TIM16_Init();
    MTR_TIM1_QEI_Init();
    MTR_TIM2_QEI_Init();

    /* Start PWM outputs */
    if (HAL_LPTIM_PWM_Start(&hlptim1,
                             MTR_PWM_PERIOD - 1U,
                             MTR_PWM_PERIOD - 1U) != HAL_OK) { return MTR_ERR_FAULT; }

    if (HAL_TIM_PWM_Start(&htim16, MTR_PWM_CH_RIGHT) != HAL_OK) { return MTR_ERR_FAULT; }

    /* Encoder snapshots */
    mtr.enc_prev_raw[MTR_LEFT]  = (uint16_t)__HAL_TIM_GET_COUNTER(&htim1);
    mtr.enc_prev_raw[MTR_RIGHT] = (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);

    /* Motors to coast */
    HAL_GPIO_WritePin(MTR_BRAKE_LEFT_PORT,  MTR_BRAKE_LEFT_PIN,  GPIO_PIN_RESET);
    HAL_GPIO_WritePin(MTR_BRAKE_RIGHT_PORT, MTR_BRAKE_RIGHT_PIN, GPIO_PIN_RESET);
    __HAL_LPTIM_COMPARE_SET(&hlptim1, MTR_PWM_PERIOD - 1U);
    __HAL_TIM_SET_COMPARE(&htim16, MTR_PWM_CH_RIGHT, 0U);

    mtr.initialized = 1U;
    return MTR_OK;
}

MTR_Status_t MTR_SetSpeed(MTR_Id_t motor, MTR_Speed_t speed)
{
    if (!mtr.initialized)     { return MTR_ERR_NOT_INIT; }
    if (mtr.emergency_active) { return MTR_ERR_FAULT;    }
    if (motor > MTR_RIGHT)    { return MTR_ERR_INVALID_PARAM; }

    if (speed >  1.0f) { speed =  1.0f; }
    if (speed < -1.0f) { speed = -1.0f; }

    if (mtr.control_mode[motor] == MTR_MODE_VELOCITY) {
        mtr.vel_setpoint_rpm[motor] = speed * MTR_MAX_RPM;
    } else {
        MTR_ApplyPWM(motor, speed);
    }
    return MTR_OK;
}

MTR_Status_t MTR_Brake(MTR_Id_t motor)
{
    if (!mtr.initialized)  { return MTR_ERR_NOT_INIT; }
    if (motor > MTR_RIGHT) { return MTR_ERR_INVALID_PARAM; }

    mtr.control_mode[motor]     = MTR_MODE_DIRECT;
    mtr.vel_setpoint_rpm[motor] = 0.0f;
    PID_Reset(&mtr.vel_pid[motor]);

    if (motor == MTR_LEFT) {
        __HAL_LPTIM_COMPARE_SET(&hlptim1, MTR_PWM_PERIOD - 1U);
        HAL_GPIO_WritePin(MTR_BRAKE_LEFT_PORT,  MTR_BRAKE_LEFT_PIN,  GPIO_PIN_SET);
    } else {
        __HAL_TIM_SET_COMPARE(&htim16, MTR_PWM_CH_RIGHT, 0U);
        HAL_GPIO_WritePin(MTR_BRAKE_RIGHT_PORT, MTR_BRAKE_RIGHT_PIN, GPIO_PIN_SET);
    }
    return MTR_OK;
}

MTR_Status_t MTR_Coast(MTR_Id_t motor)
{
    if (!mtr.initialized)  { return MTR_ERR_NOT_INIT; }
    if (motor > MTR_RIGHT) { return MTR_ERR_INVALID_PARAM; }

    mtr.control_mode[motor]     = MTR_MODE_DIRECT;
    mtr.vel_setpoint_rpm[motor] = 0.0f;
    PID_Reset(&mtr.vel_pid[motor]);

    if (motor == MTR_LEFT) {
        __HAL_LPTIM_COMPARE_SET(&hlptim1, MTR_PWM_PERIOD - 1U);
        HAL_GPIO_WritePin(MTR_BRAKE_LEFT_PORT,  MTR_BRAKE_LEFT_PIN,  GPIO_PIN_RESET);
    } else {
        __HAL_TIM_SET_COMPARE(&htim16, MTR_PWM_CH_RIGHT, 0U);
        HAL_GPIO_WritePin(MTR_BRAKE_RIGHT_PORT, MTR_BRAKE_RIGHT_PIN, GPIO_PIN_RESET);
    }
    return MTR_OK;
}

void MTR_EmergencyStop(void)
{
    hlptim1.Instance->CMP = MTR_PWM_PERIOD - 1U;
    __HAL_TIM_SET_COMPARE(&htim16, MTR_PWM_CH_RIGHT, 0U);
    HAL_GPIO_WritePin(MTR_BRAKE_LEFT_PORT,  MTR_BRAKE_LEFT_PIN,  GPIO_PIN_SET);
    HAL_GPIO_WritePin(MTR_BRAKE_RIGHT_PORT, MTR_BRAKE_RIGHT_PIN, GPIO_PIN_SET);
    mtr.emergency_active = 1U;
}

void MTR_ClearEmergency(void)
{
    mtr.emergency_active = 0U;
    PID_Reset(&mtr.vel_pid[MTR_LEFT]);
    PID_Reset(&mtr.vel_pid[MTR_RIGHT]);
    MTR_Coast(MTR_LEFT);
    MTR_Coast(MTR_RIGHT);
}

/* ============================================================================
 * Groupe 2 — Encodeurs
 * ============================================================================ */

int32_t MTR_GetEncoderCount(MTR_Id_t motor)
{
    if (motor > MTR_RIGHT) { return 0; }
    MTR_AccumulateEncoder(motor);
    return mtr.enc_accum[motor];
}

void MTR_ResetEncoder(MTR_Id_t motor)
{
    if (motor > MTR_RIGHT) { return; }
    mtr.enc_accum[motor]    = 0;
    mtr.enc_vel_ref[motor]  = 0;
    mtr.enc_vel_tick[motor] = HAL_GetTick();
    TIM_HandleTypeDef *htim = (motor == MTR_LEFT) ? &htim1 : &htim2;
    __HAL_TIM_SET_COUNTER(htim, 0U);
    mtr.enc_prev_raw[motor] = 0U;
}

float MTR_GetVelocityRPM(MTR_Id_t motor)
{
    if (motor > MTR_RIGHT) { return 0.0f; }
    MTR_AccumulateEncoder(motor);
    uint32_t now   = HAL_GetTick();
    uint32_t dt_ms = now - mtr.enc_vel_tick[motor];
    if (dt_ms == 0U) { return 0.0f; }
    int32_t delta = mtr.enc_accum[motor] - mtr.enc_vel_ref[motor];
    mtr.enc_vel_ref[motor]  = mtr.enc_accum[motor];
    mtr.enc_vel_tick[motor] = now;
    return ((float)delta / (float)dt_ms) * 1000.0f / (float)MTR_ENC_TICKS_PER_REV * 60.0f;
}

/* ============================================================================
 * Groupe 3 — Courant ADC
 * ============================================================================ */

float MTR_GetCurrentA(MTR_Id_t motor)
{
    if (motor > MTR_RIGHT) { return 0.0f; }
    float voltage = MTR_ReadADC_V(MTR_AdcChannel[motor]);
    if (voltage < 0.0f) { return 0.0f; }
    return voltage / MTR_ADC_SENSITIVITY_VA;
}

MTR_Status_t MTR_SetCurrentLimit(MTR_Id_t motor, float limit_A)
{
    if (motor > MTR_RIGHT)                        { return MTR_ERR_INVALID_PARAM; }
    if (limit_A <= 0.0f || limit_A > 2.0f)        { return MTR_ERR_INVALID_PARAM; }
    mtr.current_limit_A[motor] = limit_A;
    return MTR_OK;
}

/* ============================================================================
 * Groupe 4 — Sécurité
 * ============================================================================ */

MTR_Status_t MTR_SetTiltCutoff(float tilt_threshold_deg)
{
    if (tilt_threshold_deg <= 0.0f || tilt_threshold_deg > 90.0f) { return MTR_ERR_INVALID_PARAM; }
    mtr.tilt_cutoff_deg = tilt_threshold_deg;
    return MTR_OK;
}

MTR_Status_t MTR_SafetyUpdate(float tilt_angle_deg)
{
    if (!mtr.initialized) { return MTR_ERR_NOT_INIT; }
    float abs_tilt = (tilt_angle_deg >= 0.0f) ? tilt_angle_deg : -tilt_angle_deg;
    if (abs_tilt > mtr.tilt_cutoff_deg) { MTR_EmergencyStop(); return MTR_ERR_FAULT; }
    /* Current sensing stubbed (ADC not init) — skip overcurrent check */
    return MTR_OK;
}

/* ============================================================================
 * Groupe 5 — Commande différentielle & configuration
 * ============================================================================ */

MTR_Status_t MTR_SetDifferential(MTR_Speed_t speed_left, MTR_Speed_t speed_right)
{
    if (!mtr.initialized)     { return MTR_ERR_NOT_INIT; }
    if (mtr.emergency_active) { return MTR_ERR_FAULT;    }

    if (speed_left  >  1.0f) { speed_left  =  1.0f; }
    if (speed_left  < -1.0f) { speed_left  = -1.0f; }
    if (speed_right >  1.0f) { speed_right =  1.0f; }
    if (speed_right < -1.0f) { speed_right = -1.0f; }

    if (mtr.control_mode[MTR_LEFT] == MTR_MODE_VELOCITY) {
        mtr.vel_setpoint_rpm[MTR_LEFT]  = speed_left  * MTR_MAX_RPM;
    } else {
        MTR_ApplyPWM(MTR_LEFT,  speed_left);
    }

    if (mtr.control_mode[MTR_RIGHT] == MTR_MODE_VELOCITY) {
        mtr.vel_setpoint_rpm[MTR_RIGHT] = speed_right * MTR_MAX_RPM;
    } else {
        MTR_ApplyPWM(MTR_RIGHT, speed_right);
    }
    return MTR_OK;
}

MTR_Status_t MTR_SetDeadband(MTR_Id_t motor, float deadband_frac)
{
    if (motor > MTR_RIGHT)                             { return MTR_ERR_INVALID_PARAM; }
    if (deadband_frac < 0.0f || deadband_frac > 0.5f) { return MTR_ERR_INVALID_PARAM; }
    mtr.deadband[motor] = deadband_frac;
    return MTR_OK;
}

MTR_Status_t MTR_SetDeadZone(MTR_Id_t motor, float dz_fwd, float dz_rev)
{
    if (motor > MTR_RIGHT)               { return MTR_ERR_INVALID_PARAM; }
    if (dz_fwd < 0.0f || dz_fwd > 0.7f) { return MTR_ERR_INVALID_PARAM; }
    if (dz_rev < 0.0f || dz_rev > 0.7f) { return MTR_ERR_INVALID_PARAM; }
    mtr.dz_fwd[motor] = dz_fwd;
    mtr.dz_rev[motor] = dz_rev;
    return MTR_OK;
}

/* ============================================================================
 * Groupe 6 — PID de vitesse
 * ============================================================================ */

MTR_Status_t MTR_SetControlMode(MTR_Id_t motor, MTR_ControlMode_t mode)
{
    if (motor > MTR_RIGHT) { return MTR_ERR_INVALID_PARAM; }
    if (mtr.control_mode[motor] == mode) { return MTR_OK; }
    mtr.control_mode[motor] = mode;
    if (mode == MTR_MODE_DIRECT) {
        PID_Reset(&mtr.vel_pid[motor]);
        mtr.vel_setpoint_rpm[motor] = 0.0f;
        MTR_Coast(motor);
    } else {
        MTR_AccumulateEncoder(motor);
        mtr.enc_vel_ref[motor]  = mtr.enc_accum[motor];
        mtr.enc_vel_tick[motor] = HAL_GetTick();
        PID_Reset(&mtr.vel_pid[motor]);
        mtr.vel_setpoint_rpm[motor] = 0.0f;
    }
    return MTR_OK;
}

void MTR_VelocityUpdate(void)
{
    if (!mtr.initialized || mtr.emergency_active) { return; }
    for (int m = 0; m < 2; m++) {
        if (mtr.control_mode[m] != MTR_MODE_VELOCITY) {
            /* In DIRECT mode: just cache the current speed for telemetry */
            MTR_AccumulateEncoder((MTR_Id_t)m);
            uint32_t now   = HAL_GetTick();
            uint32_t dt_ms = now - mtr.enc_vel_tick[m];
            if (dt_ms > 0U) {
                int32_t delta = mtr.enc_accum[m] - mtr.enc_vel_ref[m];
                mtr.vel_rpm_cached[m]  = ((float)delta / (float)dt_ms)
                                         * 1000.0f / (float)MTR_ENC_TICKS_PER_REV * 60.0f;
                mtr.enc_vel_ref[m]     = mtr.enc_accum[m];
                mtr.enc_vel_tick[m]    = now;
            }
            continue;
        }
        float rpm = MTR_GetVelocityRPM((MTR_Id_t)m);
        mtr.vel_rpm_cached[m] = rpm;
        float pwm = PID_Update(&mtr.vel_pid[m], mtr.vel_setpoint_rpm[m], rpm);
        MTR_ApplyPWM((MTR_Id_t)m, pwm);
    }
}

MTR_Status_t MTR_SetVelocityGains(MTR_Id_t motor, float kp, float ki, float kd)
{
    if (motor > MTR_RIGHT) { return MTR_ERR_INVALID_PARAM; }
    return (PID_SetTunings(&mtr.vel_pid[motor], kp, ki, kd) == PID_OK)
           ? MTR_OK : MTR_ERR_INVALID_PARAM;
}

float MTR_GetCachedVelocityRPM(MTR_Id_t motor)
{
    if (motor > MTR_RIGHT) { return 0.0f; }
    return mtr.vel_rpm_cached[motor];
}

void MTR_GetVelocityGains(MTR_Id_t motor, float *kp, float *ki, float *kd)
{
    if (motor > MTR_RIGHT) { return; }
    if (kp) { *kp = mtr.vel_pid[motor].kp; }
    if (ki) { *ki = mtr.vel_pid[motor].ki; }
    if (kd) { *kd = mtr.vel_pid[motor].kd; }
}

float MTR_GetLastPwmOutput(MTR_Id_t motor)
{
    if (motor > MTR_RIGHT) { return 0.0f; }
    return mtr.vel_pid[motor].last_output;
}

