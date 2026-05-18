#ifndef CONFIG_H
#define CONFIG_H

#define CONTROL_LOOP_HZ          200u
#define CONTROL_LOOP_MS          (1000u / CONTROL_LOOP_HZ)

#define SAFETY_TILT_MAX_DEG      45.0f
#define SAFETY_BLE_TIMEOUT_MS    200u
#define SAFETY_WATCHDOG_MS       50u

#define ENCODER_TICKS_PER_REV    1856u   /* 29:1 gearbox × 64 CPR */
#define MOTOR_PWM_FREQ_HZ        20000u

#define COMPL_FILTER_ALPHA       0.98f   /* gyro weight in complementary filter */

#define WHEEL_CIRCUMFERENCE_CM   22.0f /* */
#define CM_PER_TICK              (WHEEL_CIRCUMFERENCE_CM / (float)ENCODER_TICKS_PER_REV)

#define ENCODER_TICKS_PER_REV    1856u   /* 29:1 gearbox × 64 CPR */

#endif /* CONFIG_H */
