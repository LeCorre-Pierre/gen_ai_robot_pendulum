#ifndef ROBOT_TYPES_H
#define ROBOT_TYPES_H

#include <stdint.h>

typedef enum {
    ROBOT_IDLE,
    ROBOT_BALANCING,
    ROBOT_FALLEN,
    ROBOT_ERROR
} RobotState_t;

typedef struct {
    float pitch_deg;
    float pitch_rate_dps;
} ImuSample_t;

typedef struct {
    float left;    /* -1.0 … +1.0 */
    float right;
} MotorCmd_t;

typedef struct {
    float wheel_left_rads;
    float wheel_right_rads;
} EncoderSample_t;

Encoder_t g_enc_left;
Encoder_t g_enc_right;

#endif /* ROBOT_TYPES_H */
