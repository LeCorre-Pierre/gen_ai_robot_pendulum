#include "encoder.h"
#include "config.h"

void Encoder_Init(Encoder_t *enc, TIM_HandleTypeDef *htim)
{
    enc->htim = htim;
    enc->count = 0;
    enc->velocity_rads = 0.0f;
    HAL_TIM_Encoder_Start(htim, TIM_CHANNEL_ALL);
}

void Encoder_Update(Encoder_t *enc, float dt_s)
{
    int32_t raw = (int32_t)(int16_t)__HAL_TIM_GET_COUNTER(enc->htim);
    __HAL_TIM_SET_COUNTER(enc->htim, 0);
    enc->count = raw;
    enc->velocity_rads = ((float)raw / ENCODER_TICKS_PER_REV) * (2.0f * 3.14159265f) / dt_s;
}

float Encoder_GetVelocity(const Encoder_t *enc)
{
    return enc->velocity_rads;
}
