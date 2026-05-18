#ifndef ENCODER_H
#define ENCODER_H

#include <stdint.h>
#include "stm32wbxx_hal.h"

// Simple encoder management for the two TIM peripherals configured in QEI mode.

typedef struct {
    TIM_HandleTypeDef *htim;
} Encoder_t;

void  Encoder_Init(Encoder_t *enc, TIM_HandleTypeDef *htim);
void  Encoder_Reset(Encoder_t *enc);
uint16_t Encoder_GetRaw(const Encoder_t *enc);
float Encoder_GetDistanceCm(const Encoder_t *enc);



#endif /* ENCODER_H */
