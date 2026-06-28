#ifndef TASK_CONTROL_H
#define TASK_CONTROL_H

#include <stdint.h>

void Task_control_Init(void);

/* BLE drive command: speed/turn in [-1..+1] (from CMD_DRIVE bytes / 100) */
void Task_control_SetDrive(float speed_norm, float turn_norm);

/* Balance gains: loop_id 0=angle, 1=velocity, 2=yaw */
void Task_control_SetBalanceGains(uint8_t loop_id, float kp, float ki, float kd);

/* Emergency stop / resume — delegate to MTR layer */
void Task_control_EmergencyStop(void);
void Task_control_Resume(void);

#endif /* TASK_CONTROL_H */
