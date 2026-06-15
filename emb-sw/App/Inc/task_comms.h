#ifndef TASK_COMMS_H
#define TASK_COMMS_H

#include <stdint.h>

/* ── Lifecycle ─────────────────────────────────────────────────────────────── */
void Task_comms_Init(void);

/* ── Called from HAL_UART_RxCpltCallback (ISR context) ──────────────────── */
void VCP_NotifyRxByte(uint8_t byte);

/* ── Display / telemetry queries (task context, read-only) ──────────────── */
uint8_t  VCP_IsStreamActive(void);
uint32_t VCP_GetLastCmdTick(void);   /* HAL_GetTick() of last received cmd */

/* ── Control from display task ───────────────────────────────────────────── */
void VCP_SetStreamActive(uint8_t enable);

#endif /* TASK_COMMS_H */
