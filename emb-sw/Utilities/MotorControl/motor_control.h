/**
 ******************************************************************************
 * @file    motor_control.h
 * @brief   DC Motor Control Library — Niveau Complet (14 fonctions)
 *          Cible : STM32WB5MMG (MB1292B) + Arduino Motor Shield Rev3 (L298P)
 *
 * Mapping matériel validé contre 3-gpio-mapping.md (v0.2, 2026-03-16) :
 *   PWM    : TIM1_CH1 / PD14 (moteur gauche)
 *            TIM1_CH2 / PD15 (moteur droit)
 *   DIR    : PD12 (gauche), PE4 (droit)
 *   BRAKE  : PD13 (gauche), PE0 (droit)
 *   ENC    : TIM2 32-bit PA15/PB3 (gauche), TIM3 16-bit PB4/PC7 (droit)
 *   ADC CS : PA5 ADC1_IN10 (gauche), PC3 ADC1_IN4 (droit)
 *
 * Logique de commande L298P (Arduino Motor Shield Rev3) :
 *   Avant       : DIR=HIGH, PWM=duty%, BRAKE=LOW
 *   Arrière     : DIR=LOW,  PWM=duty%, BRAKE=LOW
 *   Roue libre  : DIR=X,    PWM=0,     BRAKE=LOW
 *   Frein actif : DIR=X,    PWM=X,     BRAKE=HIGH
 ******************************************************************************
 */

#ifndef MOTOR_CONTROL_H
#define MOTOR_CONTROL_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32wbxx_hal.h"
#include <stdint.h>

/* ============================================================================
 * Configuration matérielle — à synchroniser avec CubeMX
 * ============================================================================ */

/* --- Handles HAL (noms générés par CubeMX) -------------------------------- */
#define MTR_PWM_TIM             htim1   /* TIM1 : PWM moteurs            */
#define MTR_ENC_TIM_LEFT        htim2   /* TIM2 : encodeur moteur gauche */
#define MTR_ENC_TIM_RIGHT       htim3   /* TIM3 : encodeur moteur droit  */
#define MTR_ADC                 hadc1   /* ADC1 : courant moteurs        */

/* --- Canaux PWM (TIM1) ---------------------------------------------------- */
#define MTR_PWM_CH_LEFT         TIM_CHANNEL_1   /* PD14 — Arduino D3  */
#define MTR_PWM_CH_RIGHT        TIM_CHANNEL_2   /* PD15 — Arduino D9  */

/** Valeur ARR configurée dans CubeMX pour TIM1.
 *  Compare range : [0 .. MTR_PWM_PERIOD].
 *  Exemple : 64 MHz / PSC=63 / ARR=999 → 1 kHz PWM */
#define MTR_PWM_PERIOD          1000U

/* --- GPIOs Direction ------------------------------------------------------- */
#define MTR_DIR_LEFT_PORT       GPIOD
#define MTR_DIR_LEFT_PIN        GPIO_PIN_12     /* PD12 — Arduino D2  */
#define MTR_DIR_RIGHT_PORT      GPIOE
#define MTR_DIR_RIGHT_PIN       GPIO_PIN_4      /* PE4  — Arduino D4  */

/* Niveau logique = "avant" pour chaque moteur (inverser si câblage inversé) */
#define MTR_DIR_FORWARD         GPIO_PIN_SET
#define MTR_DIR_BACKWARD        GPIO_PIN_RESET

/* --- GPIOs Frein ---------------------------------------------------------- */
#define MTR_BRAKE_LEFT_PORT     GPIOD
#define MTR_BRAKE_LEFT_PIN      GPIO_PIN_13     /* PD13 — Arduino D8  */
#define MTR_BRAKE_RIGHT_PORT    GPIOE
#define MTR_BRAKE_RIGHT_PIN     GPIO_PIN_0      /* PE0  — Arduino D6  */

/* --- Encodeurs (TIM_ENCODERMODE_TI12, ×4 quadrature) ---------------------- */
/** 64 CPR × 4 (TI12 ×4) × réduction 29:1 = 7424 ticks/tour de roue.
 *  TIM2 est 32-bit (pas de débordement logiciel nécessaire).
 *  TIM3 est 16-bit (accumulation 32-bit gérée par MTR_GetEncoderCount). */
#define MTR_ENC_TICKS_PER_REV   7424U

/* --- ADC courant (sensing résistances shield, 1.65 V/A, 3.3 V = 2 A) ----- */
#define MTR_ADC_CH_LEFT         ADC_CHANNEL_10  /* PA5  — Arduino A2  */
#define MTR_ADC_CH_RIGHT        ADC_CHANNEL_4   /* PC3  — Arduino A0  */
#define MTR_ADC_RESOLUTION      4095.0f         /* 12 bits            */
#define MTR_ADC_VREF_V          3.3f
#define MTR_ADC_SENSITIVITY_VA  1.65f           /* V/A : 3.3 V = 2 A  */

/* --- Valeurs par défaut ---------------------------------------------------- */
#define MTR_DEFAULT_DEADBAND        0.15f   /* 15 % pleine échelle (L298) */
#define MTR_DEFAULT_CURRENT_LIMIT_A 1.8f   /* A par canal, seuil sécu   */
#define MTR_DEFAULT_TILT_CUTOFF_DEG 45.0f  /* ° — coupure si |tilt| > X */

/* ============================================================================
 * Types
 * ============================================================================ */

/** Code de retour, style HAL */
typedef enum
{
    MTR_OK               = 0,
    MTR_ERR_INVALID_PARAM,      /*!< Paramètre hors plage              */
    MTR_ERR_NOT_INIT,           /*!< MTR_Init() non appelé             */
    MTR_ERR_OVERCURRENT,        /*!< Courant moteur > limite configurée */
    MTR_ERR_FAULT,              /*!< Coupure sécurité active            */
} MTR_Status_t;

/** Identifiant moteur */
typedef enum
{
    MTR_LEFT  = 0,  /*!< Moteur gauche — TIM1_CH1 / PD14 */
    MTR_RIGHT = 1,  /*!< Moteur droit  — TIM1_CH2 / PD15 */
} MTR_Id_t;

/** Consigne vitesse normalisée.
 *  -1.0 = plein arrière | 0.0 = arrêt | +1.0 = plein avant.
 *  Correspond directement à la sortie d'un contrôleur PID [-1.0 .. +1.0]. */
typedef float MTR_Speed_t;

/* ============================================================================
 * API publique — 14 fonctions (niveau Complet)
 * ============================================================================ */

/* --- Groupe 1 : Initialisation & commande de base (5 fonctions) ----------- */

/**
 * @brief  Initialise les timers PWM, les GPIOs direction/frein et les
 *         timers encodeur. Remet les deux moteurs en roue libre.
 *         À appeler une fois avant le démarrage de FreeRTOS.
 * @retval MTR_OK si succès, MTR_ERR_FAULT si un handle HAL est nul.
 */
MTR_Status_t MTR_Init(void);

/**
 * @brief  Applique une consigne de vitesse normalisée sur un moteur.
 *         Gère automatiquement le sens (DIR), le rapport cyclique (PWM)
 *         et la zone morte (deadband).
 * @param  motor  MTR_LEFT ou MTR_RIGHT
 * @param  speed  Consigne [-1.0 .. +1.0]
 * @retval MTR_OK, MTR_ERR_NOT_INIT, MTR_ERR_FAULT (si coupure urgence active)
 */
MTR_Status_t MTR_SetSpeed(MTR_Id_t motor, MTR_Speed_t speed);

/**
 * @brief  Frein actif : active la broche BRAKE du L298.
 *         Le moteur freine électriquement (court-circuit de l'induit).
 *         Couple de maintien, arrêt rapide.
 * @param  motor  MTR_LEFT ou MTR_RIGHT
 */
MTR_Status_t MTR_Brake(MTR_Id_t motor);

/**
 * @brief  Roue libre : coupe le PWM, BRAKE=LOW.
 *         Le moteur décélère librement par frottement.
 * @param  motor  MTR_LEFT ou MTR_RIGHT
 */
MTR_Status_t MTR_Coast(MTR_Id_t motor);

/**
 * @brief  Arrêt d'urgence immédiat et irrévocable.
 *         Coupe le PWM ET active BRAKE sur les deux moteurs.
 *         Positionne un flag interne bloquant tout MTR_SetSpeed() ultérieur.
 *         Appelable depuis n'importe quel contexte (tâche, ISR, callback BLE).
 * @note   Pour reprendre le contrôle après urgence, appeler MTR_Init().
 */
void MTR_EmergencyStop(void);

/* --- Groupe 2 : Encodeurs (3 fonctions) ----------------------------------- */

/**
 * @brief  Lit le compteur encodeur 32-bit accumulé (logiciel).
 *         Valeur signée croissante en avant, décroissante en arrière.
 *         Résolution : MTR_ENC_TICKS_PER_REV (7424) ticks/tour de roue.
 * @note   Doit être appelé à intervalle régulier (≤ période de contrôle)
 *         pour éviter la perte de ticks sur TIM3 (16-bit).
 * @param  motor  MTR_LEFT (TIM2, 32-bit) ou MTR_RIGHT (TIM3, 16-bit accumulé)
 * @retval Compteur signé 32 bits
 */
int32_t MTR_GetEncoderCount(MTR_Id_t motor);

/**
 * @brief  Remet le compteur encodeur logiciel à zéro.
 *         Remet également le registre CNT du timer matériel à 0.
 * @param  motor  MTR_LEFT ou MTR_RIGHT
 */
void MTR_ResetEncoder(MTR_Id_t motor);

/**
 * @brief  Calcule et retourne la vitesse instantanée en tr/min.
 *         Basé sur le delta de ticks entre deux appels successifs.
 *         Signe positif = sens avant.
 * @note   Appeler à fréquence constante (idéalement 200 Hz) pour un résultat
 *         stable. Pas thread-safe si appelé depuis plusieurs tâches FreeRTOS.
 * @param  motor  MTR_LEFT ou MTR_RIGHT
 * @retval Vitesse en tr/min (roue sortie de réducteur), signée
 */
float MTR_GetVelocityRPM(MTR_Id_t motor);

/* --- Groupe 3 : Courant ADC (2 fonctions) --------------------------------- */

/**
 * @brief  Lit le courant instantané d'un moteur via l'ADC.
 *         Utilise la résistance de sensing du Motor Shield :
 *         1.65 V/A, 3.3 V = 2 A (parfaitement aligné sur Vref STM32 3.3 V).
 * @note   Implémentation par polling ADC (bloquant ~1 µs, acceptable à 200 Hz).
 *         Pour une production haute performance, migrer vers DMA continu.
 *         Requiert que hadc1 soit initialisé par CubeMX.
 * @param  motor  MTR_LEFT (PA5/ADC1_IN10) ou MTR_RIGHT (PC3/ADC1_IN4)
 * @retval Courant en Ampères (0.0 en cas d'erreur ADC)
 */
float MTR_GetCurrentA(MTR_Id_t motor);

/**
 * @brief  Configure la limite de courant par canal.
 *         Si MTR_SafetyUpdate() détecte un dépassement, MTR_EmergencyStop()
 *         est déclenché automatiquement.
 * @param  motor    MTR_LEFT ou MTR_RIGHT
 * @param  limit_A  Seuil en Ampères (max shield = 2.0 A par canal)
 * @retval MTR_OK ou MTR_ERR_INVALID_PARAM si limit_A > 2.0
 */
MTR_Status_t MTR_SetCurrentLimit(MTR_Id_t motor, float limit_A);

/* --- Groupe 4 : Sécurité (2 fonctions) ------------------------------------ */

/**
 * @brief  Configure l'angle de basculement déclenchant la coupure moteur.
 *         Valeur projet : 45°. En dessous, le robot peut encore se rattraper.
 * @param  tilt_threshold_deg  Angle en degrés (valeur absolue)
 * @retval MTR_OK ou MTR_ERR_INVALID_PARAM
 */
MTR_Status_t MTR_SetTiltCutoff(float tilt_threshold_deg);

/**
 * @brief  Vérifie les conditions de sécurité et déclenche MTR_EmergencyStop()
 *         si nécessaire. À appeler à chaque itération de la tâche de contrôle
 *         (200 Hz), AVANT d'appliquer la consigne PID.
 *
 *         Conditions vérifiées :
 *           1. |tilt_angle_deg| > seuil configuré (MTR_SetTiltCutoff)
 *           2. Courant moteur gauche > limite (MTR_SetCurrentLimit)
 *           3. Courant moteur droit  > limite
 *
 * @param  tilt_angle_deg  Angle de tilt courant en degrés (signé, issu de l'IMU)
 * @retval MTR_OK si tout va bien, MTR_ERR_FAULT si une coupure a été déclenchée
 */
MTR_Status_t MTR_SafetyUpdate(float tilt_angle_deg);

/* --- Groupe 5 : Commande différentielle & configuration (2 fonctions) ----- */

/**
 * @brief  Applique une consigne sur les deux moteurs en un appel atomique.
 *         Évite le décalage temporel entre deux MTR_SetSpeed() séparés.
 *         Utilisé par la boucle de contrôle : sortie balance (commun) +
 *         sortie yaw (différentiel) → speed_left = v+yaw, speed_right = v-yaw.
 * @param  speed_left   Consigne moteur gauche [-1.0 .. +1.0]
 * @param  speed_right  Consigne moteur droit  [-1.0 .. +1.0]
 * @retval MTR_OK, MTR_ERR_NOT_INIT, ou MTR_ERR_FAULT
 */
MTR_Status_t MTR_SetDifferential(MTR_Speed_t speed_left, MTR_Speed_t speed_right);

/**
 * @brief  Configure la zone morte PWM en dessous de laquelle le duty cycle
 *         est forcé à 0 (le L298 ne génère pas de couple utile sous ~15%).
 *         Valeur recommandée pour L298 : 0.10 à 0.20.
 * @param  motor         MTR_LEFT ou MTR_RIGHT
 * @param  deadband_frac Fraction [0.0 .. 0.5] de la pleine échelle
 * @retval MTR_OK ou MTR_ERR_INVALID_PARAM
 */
MTR_Status_t MTR_SetDeadband(MTR_Id_t motor, float deadband_frac);

#ifdef __cplusplus
}
#endif

#endif /* MOTOR_CONTROL_H */
