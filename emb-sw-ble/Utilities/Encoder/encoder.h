/**
  ******************************************************************************
  * @file    encoder.h
  * @brief   Encoder acquisition and wheel-speed estimation interface.
  *
  * This module initializes TIM1 (left wheel) and TIM2 (right wheel) in
  * quadrature encoder mode and exposes a small API to estimate wheel speed
  * in revolutions per minute (RPM).
  *
  * Typical usage:
  *   1. Call Encoders_Init() once during board initialization.
  *   2. Call Encoders_Update(dt_s) at each control or telemetry period, where
  *      dt_s is the elapsed time in seconds since the previous update.
  *   3. Read the latest values with Encoders_GetSpeedL_RPM() and
  *      Encoders_GetSpeedR_RPM().
  *
  * Notes:
  *   - Conversion uses 7424 ticks/revolution, corresponding to
  *     64 CPR x 29:1 gearbox x4.
  *   - The implementation assumes the timers are configured in QEI mode TI12.
  ******************************************************************************
  */
#ifndef ENCODER_H
#define ENCODER_H

#ifdef __cplusplus
extern "C" {
#endif

/* Initialize TIM1/TIM2 in quadrature encoder mode. Call once at startup. */
void Encoders_Init(void);

/* Compute wheel speed from the elapsed time since the last call. */
void Encoders_Update(float dt_s);

/* Return the latest left/right wheel speed in RPM. */
float Encoders_GetSpeedL_RPM(void);
float Encoders_GetSpeedR_RPM(void);

#ifdef __cplusplus
}
#endif

#endif /* ENCODER_H */
