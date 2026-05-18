#include "encoder.h"
#include "config.h"

void Encoder_Init(Encoder_t *enc, TIM_HandleTypeDef *htim)
{
    enc->htim = htim;
    HAL_TIM_Encoder_Start(htim, TIM_CHANNEL_ALL);
}

void  Encoder_Reset(Encoder_t *enc)
{
    __HAL_TIM_SET_COUNTER(enc->htim, 0);
}

uint16_t Encoder_GetRaw(const Encoder_t *enc)
{
    return (uint16_t)__HAL_TIM_GET_COUNTER(enc->htim);
}

float Encoder_GetDistanceCm(const Encoder_t *enc)
{
    return (float)(Encoder_GetRaw(enc) * CM_PER_TICK);
}