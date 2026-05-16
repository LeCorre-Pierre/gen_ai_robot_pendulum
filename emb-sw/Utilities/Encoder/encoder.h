#ifndef ENCODER_H
#define ENCODER_H

#include <stdint.h>
#include "tim.h"

typedef struct {
    TIM_HandleTypeDef *htim;
    int32_t  count;
    float    velocity_rads;
} Encoder_t;

void  Encoder_Init(Encoder_t *enc, TIM_HandleTypeDef *htim);
void  Encoder_Update(Encoder_t *enc, float dt_s);
float Encoder_GetVelocity(const Encoder_t *enc);

#endif /* ENCODER_H */
