/**
 ******************************************************************************
 * @file    motor_control.c
 * @brief   DC Motor Control Library — Niveau Complet (14 fonctions)
 *          Cible : STM32WB5MMG (MB1292B) + Arduino Motor Shield Rev3 (L298P)
 ******************************************************************************
 */

#include "motor_control.h"
#include "pid_controller.h"
#include <stddef.h>

/* ============================================================================
 * Déclarations externes — handles HAL définis dans main.c
 * ============================================================================ */
extern LPTIM_HandleTypeDef MTR_PWM_LPTIM_LEFT;  /* hlptim1 — PWM gauche (PC1) */
extern TIM_HandleTypeDef   MTR_PWM_TIM_RIGHT;   /* htim16  — PWM droit  (PE0) */
extern TIM_HandleTypeDef   MTR_ENC_TIM_LEFT;    /* htim1   — encodeur gauche  */
extern TIM_HandleTypeDef   MTR_ENC_TIM_RIGHT;   /* htim2   — encodeur droit   */
extern ADC_HandleTypeDef   MTR_ADC;             /* hadc1   — courant moteurs  */

/* ============================================================================
 * Contexte interne (privé)
 * ============================================================================ */

/* MTR_LEFT  utilise LPTIM1 (pas de canal TIM_CHANNEL_x).
 * MTR_RIGHT utilise TIM16_CH1 — la constante MTR_PWM_CH_RIGHT suffit. */

/** Table des canaux ADC indexée par MTR_Id_t */
static const uint32_t MTR_AdcChannel[2] =
{
    MTR_ADC_CH_LEFT,    /* MTR_LEFT  = 0 — PA5  ADC1_IN10 */
    MTR_ADC_CH_RIGHT,   /* MTR_RIGHT = 1 — PC3  ADC1_IN4  */
};

/** Structure de contexte runtime */
typedef struct
{
    /* Drapeaux */
    uint8_t  initialized;       /*!< 1 après MTR_Init() réussi        */
    uint8_t  emergency_active;  /*!< 1 après MTR_EmergencyStop()      */

    /* Configuration par moteur */
    float    deadband[2];       /*!< Zone morte [0.0 .. 0.5]          */
    float    current_limit_A[2];/*!< Limite courant en Ampères        */

    /* Sécurité tilt */
    float    tilt_cutoff_deg;   /*!< Seuil coupure tilt (valeur abs.) */

    /* Encodeurs — accumulation 32-bit logicielle */
    int32_t  enc_accum[2];      /*!< Compteur accumulé signé 32-bit   */
    uint16_t enc_prev_raw[2];   /*!< Valeur CNT brute au cycle N-1    */

    /* Calcul de vitesse */
    int32_t  enc_vel_ref[2];    /*!< Compteur au dernier appel GetVel */
    uint32_t enc_vel_tick[2];   /*!< HAL_GetTick() au dernier GetVel  */

    /* PID de vitesse */
    MTR_ControlMode_t control_mode[2];    /*!< DIRECT ou VELOCITY par moteur  */
    float             vel_setpoint_rpm[2];/*!< Consigne RPM (mode VELOCITY)   */
    float             vel_rpm_cached[2]; /*!< Dernier RPM calculé (lecture UI)*/
    PID_Controller_t  vel_pid[2];         /*!< Instances PID gauche / droite  */
} MTR_Context_t;

static MTR_Context_t mtr; /* Instance unique du contexte */

/* ============================================================================
 * Fonctions privées
 * ============================================================================ */

/**
 * @brief  Relit le compteur CNT matériel et accumule dans enc_accum[].
 *         Gère l'overflow 16-bit de TIM3 (moteur droit) par cast int16_t.
 *         Pour TIM2 32-bit (moteur gauche), le même cast reste correct car
 *         le delta entre deux appels est toujours << 32767 ticks à 200 Hz.
 */
static void MTR_AccumulateEncoder(MTR_Id_t motor)
{
    TIM_HandleTypeDef *htim = (motor == MTR_LEFT)
                              ? &MTR_ENC_TIM_LEFT
                              : &MTR_ENC_TIM_RIGHT;

    uint16_t curr  = (uint16_t)__HAL_TIM_GET_COUNTER(htim);
    int16_t  delta = (int16_t)(curr - mtr.enc_prev_raw[motor]);

    /* LEFT encoder is physically wired in reverse — invert its sign */
    if (motor == MTR_LEFT) { delta = -delta; }

    mtr.enc_accum[motor]   += (int32_t)delta;
    mtr.enc_prev_raw[motor] = curr;
}

/**
 * @brief  Applique la consigne PWM + direction sur un moteur.
 *         Ne vérifie PAS l'état emergency (déjà vérifié par l'appelant).
 * @param  motor  MTR_LEFT ou MTR_RIGHT
 * @param  speed  [-1.0 .. +1.0], déjà clampé par l'appelant
 */
static void MTR_ApplyPWM(MTR_Id_t motor, MTR_Speed_t speed)
{
    GPIO_TypeDef *dir_port   = (motor == MTR_LEFT) ? MTR_DIR_LEFT_PORT   : MTR_DIR_RIGHT_PORT;
    uint16_t      dir_pin    = (motor == MTR_LEFT) ? MTR_DIR_LEFT_PIN    : MTR_DIR_RIGHT_PIN;
    GPIO_TypeDef *brake_port = (motor == MTR_LEFT) ? MTR_BRAKE_LEFT_PORT : MTR_BRAKE_RIGHT_PORT;
    uint16_t      brake_pin  = (motor == MTR_LEFT) ? MTR_BRAKE_LEFT_PIN  : MTR_BRAKE_RIGHT_PIN;

    float abs_speed = (speed >= 0.0f) ? speed : -speed;

    /* Zone morte : en dessous du seuil → roue libre */
    if (abs_speed < mtr.deadband[motor])
    {
        if (motor == MTR_LEFT) {
            __HAL_LPTIM_COMPARE_SET(&MTR_PWM_LPTIM_LEFT, MTR_PWM_PERIOD - 1U); /* CMP=ARR → duty≈0% */
        } else {
            __HAL_TIM_SET_COMPARE(&MTR_PWM_TIM_RIGHT, MTR_PWM_CH_RIGHT, 0U);
        }
        HAL_GPIO_WritePin(brake_port, brake_pin, GPIO_PIN_RESET);
        return;
    }

    /* Désactivation du frein avant tout changement de direction */
    HAL_GPIO_WritePin(brake_port, brake_pin, GPIO_PIN_RESET);

    /* Sens de rotation — polarité par moteur (câblage inversé gauche/droite) */
    GPIO_PinState fwd = (motor == MTR_LEFT) ? MTR_DIR_FWD_LEFT : MTR_DIR_FWD_RIGHT;
    GPIO_PinState bwd = (fwd == GPIO_PIN_SET) ? GPIO_PIN_RESET : GPIO_PIN_SET;
    HAL_GPIO_WritePin(dir_port, dir_pin, (speed >= 0.0f) ? fwd : bwd);

    /* Rapport cyclique proportionnel à |speed| — plage [0 .. MTR_PWM_PERIOD-1] */
    uint32_t compare = (uint32_t)(abs_speed * (float)(MTR_PWM_PERIOD - 1U));
    if (compare >= MTR_PWM_PERIOD) { compare = MTR_PWM_PERIOD - 1U; }

    if (motor == MTR_LEFT) {
        /* LPTIM1: duty = (ARR - CMP) / (ARR+1) → inverser compare pour même sens que TIM */
        __HAL_LPTIM_COMPARE_SET(&MTR_PWM_LPTIM_LEFT, (MTR_PWM_PERIOD - 1U) - compare);
    } else {
        __HAL_TIM_SET_COMPARE(&MTR_PWM_TIM_RIGHT, MTR_PWM_CH_RIGHT, compare);
    }
}

/**
 * @brief  Lit un canal ADC unique en mode polling.
 *         Bloquant ~1 µs à 64 MHz — acceptable dans une tâche 200 Hz.
 * @param  channel  Canal ADC (ADC_CHANNEL_x)
 * @retval Tension en Volts, ou -1.0f en cas d'erreur
 */
static float MTR_ReadADC_V(uint32_t channel)
{
    ADC_ChannelConfTypeDef cfg = {0};
    cfg.Channel      = channel;
    cfg.Rank         = ADC_REGULAR_RANK_1;
    cfg.SamplingTime = ADC_SAMPLETIME_92CYCLES_5;
    cfg.SingleDiff   = ADC_SINGLE_ENDED;
    cfg.OffsetNumber = ADC_OFFSET_NONE;
    cfg.Offset       = 0U;

    if (HAL_ADC_ConfigChannel(&MTR_ADC, &cfg) != HAL_OK)    { return -1.0f; }
    if (HAL_ADC_Start(&MTR_ADC)              != HAL_OK)    { return -1.0f; }
    if (HAL_ADC_PollForConversion(&MTR_ADC, 5U) != HAL_OK) { HAL_ADC_Stop(&MTR_ADC); return -1.0f; }

    uint32_t raw = HAL_ADC_GetValue(&MTR_ADC);
    HAL_ADC_Stop(&MTR_ADC);

    return ((float)raw / MTR_ADC_RESOLUTION) * MTR_ADC_VREF_V;
}

/* ============================================================================
 * Groupe 1 — Initialisation & commande de base
 * ============================================================================ */

MTR_Status_t MTR_Init(void)
{
    /* Initialisation du contexte */
    mtr.initialized        = 0U;
    mtr.emergency_active   = 0U;
    mtr.tilt_cutoff_deg    = MTR_DEFAULT_TILT_CUTOFF_DEG;

    for (int i = 0; i < 2; i++)
    {
        mtr.deadband[i]           = MTR_DEFAULT_DEADBAND;
        mtr.current_limit_A[i]    = MTR_DEFAULT_CURRENT_LIMIT_A;
        mtr.enc_accum[i]          = 0;
        mtr.enc_prev_raw[i]       = 0U;
        mtr.enc_vel_ref[i]        = 0;
        mtr.enc_vel_tick[i]       = 0U;
        mtr.control_mode[i]       = MTR_MODE_DIRECT;
        mtr.vel_setpoint_rpm[i]   = 0.0f;
        mtr.vel_rpm_cached[i]     = 0.0f;

        PID_Init(&mtr.vel_pid[i],
                 MTR_VEL_KP_DEFAULT, MTR_VEL_KI_DEFAULT, MTR_VEL_KD_DEFAULT,
                 MTR_VEL_SAMPLE_TIME_S,
                 -1.0f, 1.0f);
        PID_SetIntegralLimits(&mtr.vel_pid[i], -0.5f, 0.5f);
    }

    /* Démarrage PWM gauche : LPTIM1 (PC1, 20 kHz, ARR=3199).
     * LPTIM1 duty = (ARR - CMP) / (ARR+1), donc CMP=ARR-1 → duty≈0% (moteur arrêté). */
    if (HAL_LPTIM_PWM_Start(&MTR_PWM_LPTIM_LEFT,
                             MTR_PWM_PERIOD - 1U, MTR_PWM_PERIOD - 1U) != HAL_OK) { return MTR_ERR_FAULT; }

    /* Démarrage PWM droit : TIM16_CH1 (PE0, 20 kHz) */
    if (HAL_TIM_PWM_Start(&MTR_PWM_TIM_RIGHT,
                           MTR_PWM_CH_RIGHT) != HAL_OK) { return MTR_ERR_FAULT; }

    /* Snapshot des compteurs encodeur (TIM1/TIM2 déjà démarrés par MX_TIM1/2_Init) */
    mtr.enc_prev_raw[MTR_LEFT]  = (uint16_t)__HAL_TIM_GET_COUNTER(&MTR_ENC_TIM_LEFT);
    mtr.enc_prev_raw[MTR_RIGHT] = (uint16_t)__HAL_TIM_GET_COUNTER(&MTR_ENC_TIM_RIGHT);

    /* Mettre les moteurs en roue libre (BRAKE=0, CMP → duty 0%) */
    HAL_GPIO_WritePin(MTR_BRAKE_LEFT_PORT,  MTR_BRAKE_LEFT_PIN,  GPIO_PIN_RESET);
    HAL_GPIO_WritePin(MTR_BRAKE_RIGHT_PORT, MTR_BRAKE_RIGHT_PIN, GPIO_PIN_RESET);
    __HAL_LPTIM_COMPARE_SET(&MTR_PWM_LPTIM_LEFT, MTR_PWM_PERIOD - 1U); /* LPTIM: CMP=ARR → duty≈0% */
    __HAL_TIM_SET_COMPARE(&MTR_PWM_TIM_RIGHT, MTR_PWM_CH_RIGHT, 0U);

    mtr.initialized = 1U;
    return MTR_OK;
}

MTR_Status_t MTR_SetSpeed(MTR_Id_t motor, MTR_Speed_t speed)
{
    if (!mtr.initialized)     { return MTR_ERR_NOT_INIT; }
    if (mtr.emergency_active) { return MTR_ERR_FAULT;    }
    if (motor > MTR_RIGHT)    { return MTR_ERR_INVALID_PARAM; }

    /* Clampage */
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

    /* Repasse en DIRECT pour éviter que le PID ne se batte contre le frein */
    mtr.control_mode[motor]     = MTR_MODE_DIRECT;
    mtr.vel_setpoint_rpm[motor] = 0.0f;
    PID_Reset(&mtr.vel_pid[motor]);

    /* PWM → duty 0%, BRAKE = HIGH → court-circuit induit moteur */
    if (motor == MTR_LEFT) {
        __HAL_LPTIM_COMPARE_SET(&MTR_PWM_LPTIM_LEFT, MTR_PWM_PERIOD - 1U);
        HAL_GPIO_WritePin(MTR_BRAKE_LEFT_PORT,  MTR_BRAKE_LEFT_PIN,  GPIO_PIN_SET);
    } else {
        __HAL_TIM_SET_COMPARE(&MTR_PWM_TIM_RIGHT, MTR_PWM_CH_RIGHT, 0U);
        HAL_GPIO_WritePin(MTR_BRAKE_RIGHT_PORT, MTR_BRAKE_RIGHT_PIN, GPIO_PIN_SET);
    }
    return MTR_OK;
}

MTR_Status_t MTR_Coast(MTR_Id_t motor)
{
    if (!mtr.initialized)  { return MTR_ERR_NOT_INIT; }
    if (motor > MTR_RIGHT) { return MTR_ERR_INVALID_PARAM; }

    /* Repasse en DIRECT pour éviter que le PID ne continue de pousser */
    mtr.control_mode[motor]     = MTR_MODE_DIRECT;
    mtr.vel_setpoint_rpm[motor] = 0.0f;
    PID_Reset(&mtr.vel_pid[motor]);

    /* PWM → duty 0%, BRAKE = LOW → roue libre */
    if (motor == MTR_LEFT) {
        __HAL_LPTIM_COMPARE_SET(&MTR_PWM_LPTIM_LEFT, MTR_PWM_PERIOD - 1U);
        HAL_GPIO_WritePin(MTR_BRAKE_LEFT_PORT,  MTR_BRAKE_LEFT_PIN,  GPIO_PIN_RESET);
    } else {
        __HAL_TIM_SET_COMPARE(&MTR_PWM_TIM_RIGHT, MTR_PWM_CH_RIGHT, 0U);
        HAL_GPIO_WritePin(MTR_BRAKE_RIGHT_PORT, MTR_BRAKE_RIGHT_PIN, GPIO_PIN_RESET);
    }
    return MTR_OK;
}

void MTR_EmergencyStop(void)
{
    /*
     * Opérations sur registres uniquement — callable depuis une ISR.
     * Aucun appel HAL bloquant.
     */

    /* Coupe PWM — accès direct registre (safe depuis ISR).
     * LPTIM1: CMP = ARR → duty≈0%. TIM16: CMP = 0 → duty = 0%. */
    MTR_PWM_LPTIM_LEFT.Instance->CMP = MTR_PWM_PERIOD - 1U;
    __HAL_TIM_SET_COMPARE(&MTR_PWM_TIM_RIGHT, MTR_PWM_CH_RIGHT, 0U);

    /* Active le frein sur les deux moteurs */
    HAL_GPIO_WritePin(MTR_BRAKE_LEFT_PORT,  MTR_BRAKE_LEFT_PIN,  GPIO_PIN_SET);
    HAL_GPIO_WritePin(MTR_BRAKE_RIGHT_PORT, MTR_BRAKE_RIGHT_PIN, GPIO_PIN_SET);

    /* Verrouille tout MTR_SetSpeed() ultérieur */
    mtr.emergency_active = 1U;
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

    /* Remise à zéro logicielle */
    mtr.enc_accum[motor]    = 0;
    mtr.enc_vel_ref[motor]  = 0;
    mtr.enc_vel_tick[motor] = HAL_GetTick();

    /* Remise à zéro du registre CNT matériel */
    TIM_HandleTypeDef *htim = (motor == MTR_LEFT)
                              ? &MTR_ENC_TIM_LEFT
                              : &MTR_ENC_TIM_RIGHT;
    __HAL_TIM_SET_COUNTER(htim, 0U);
    mtr.enc_prev_raw[motor] = 0U;
}

float MTR_GetVelocityRPM(MTR_Id_t motor)
{
    if (motor > MTR_RIGHT) { return 0.0f; }

    /* Mise à jour de l'accumulateur */
    MTR_AccumulateEncoder(motor);

    uint32_t now    = HAL_GetTick();  /* ms */
    uint32_t dt_ms  = now - mtr.enc_vel_tick[motor];

    if (dt_ms == 0U) { return 0.0f; } /* Protection division par zéro */

    int32_t delta_ticks = mtr.enc_accum[motor] - mtr.enc_vel_ref[motor];

    /* Sauvegarde pour le prochain appel */
    mtr.enc_vel_ref[motor]  = mtr.enc_accum[motor];
    mtr.enc_vel_tick[motor] = now;

    /*
     * Conversion :
     *   (ticks / ms) × 1000 ms/s × (1 tour / 7424 ticks) × 60 s/min = RPM
     */
    return ((float)delta_ticks / (float)dt_ms)
           * 1000.0f
           / (float)MTR_ENC_TICKS_PER_REV
           * 60.0f;
}

/* ============================================================================
 * Groupe 3 — Courant ADC
 * ============================================================================ */

float MTR_GetCurrentA(MTR_Id_t motor)
{
    if (motor > MTR_RIGHT) { return 0.0f; }

    float voltage = MTR_ReadADC_V(MTR_AdcChannel[motor]);

    if (voltage < 0.0f) { return 0.0f; } /* Erreur ADC */

    /*
     * Conversion tension → courant :
     *   I [A] = V_adc [V] / sensibilité [V/A]
     *   Exemple : 1.65 V / 1.65 V/A = 1.0 A
     *             3.30 V / 1.65 V/A = 2.0 A (max shield)
     */
    return voltage / MTR_ADC_SENSITIVITY_VA;
}

MTR_Status_t MTR_SetCurrentLimit(MTR_Id_t motor, float limit_A)
{
    if (motor > MTR_RIGHT) { return MTR_ERR_INVALID_PARAM; }
    if (limit_A <= 0.0f || limit_A > 2.0f) { return MTR_ERR_INVALID_PARAM; }

    mtr.current_limit_A[motor] = limit_A;
    return MTR_OK;
}

/* ============================================================================
 * Groupe 4 — Sécurité
 * ============================================================================ */

MTR_Status_t MTR_SetTiltCutoff(float tilt_threshold_deg)
{
    if (tilt_threshold_deg <= 0.0f || tilt_threshold_deg > 90.0f)
    {
        return MTR_ERR_INVALID_PARAM;
    }
    mtr.tilt_cutoff_deg = tilt_threshold_deg;
    return MTR_OK;
}

MTR_Status_t MTR_SafetyUpdate(float tilt_angle_deg)
{
    if (!mtr.initialized) { return MTR_ERR_NOT_INIT; }

    /* --- Vérification angle de tilt --- */
    float abs_tilt = (tilt_angle_deg >= 0.0f) ? tilt_angle_deg : -tilt_angle_deg;
    if (abs_tilt > mtr.tilt_cutoff_deg)
    {
        MTR_EmergencyStop();
        return MTR_ERR_FAULT;
    }

    /* --- Vérification courant moteur gauche --- */
    float i_left = MTR_GetCurrentA(MTR_LEFT);
    if (i_left > mtr.current_limit_A[MTR_LEFT])
    {
        MTR_EmergencyStop();
        return MTR_ERR_OVERCURRENT;
    }

    /* --- Vérification courant moteur droit --- */
    float i_right = MTR_GetCurrentA(MTR_RIGHT);
    if (i_right > mtr.current_limit_A[MTR_RIGHT])
    {
        MTR_EmergencyStop();
        return MTR_ERR_OVERCURRENT;
    }

    return MTR_OK;
}

/* ============================================================================
 * Groupe 5 — Commande différentielle & configuration
 * ============================================================================ */

MTR_Status_t MTR_SetDifferential(MTR_Speed_t speed_left, MTR_Speed_t speed_right)
{
    if (!mtr.initialized)     { return MTR_ERR_NOT_INIT; }
    if (mtr.emergency_active) { return MTR_ERR_FAULT;    }

    /* Clampage */
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
    if (motor > MTR_RIGHT)                          { return MTR_ERR_INVALID_PARAM; }
    if (deadband_frac < 0.0f || deadband_frac > 0.5f) { return MTR_ERR_INVALID_PARAM; }

    mtr.deadband[motor] = deadband_frac;
    return MTR_OK;
}

/* ============================================================================
 * Groupe 6 — PID de vitesse (boucle fermée encodeur)
 * ============================================================================ */

MTR_Status_t MTR_SetControlMode(MTR_Id_t motor, MTR_ControlMode_t mode)
{
    if (motor > MTR_RIGHT) { return MTR_ERR_INVALID_PARAM; }
    if (mtr.control_mode[motor] == mode) { return MTR_OK; }

    mtr.control_mode[motor] = mode;

    if (mode == MTR_MODE_DIRECT) {
        /* Arrêt immédiat — le PID ne doit plus piloter le PWM */
        PID_Reset(&mtr.vel_pid[motor]);
        mtr.vel_setpoint_rpm[motor] = 0.0f;
        MTR_Coast(motor);
    } else {
        /* Initialise la fenêtre de vitesse avant le premier PID_Update */
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
        if (mtr.control_mode[m] != MTR_MODE_VELOCITY) { continue; }

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
