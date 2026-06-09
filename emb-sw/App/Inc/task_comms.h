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
int16_t  VCP_GetSetpointRpm(void);   /* last setpoint from PC (0 if none)  */

/* ── Control from display task ───────────────────────────────────────────── */
void VCP_SetStreamActive(uint8_t enable);

/* ── RPM override (SET_SP command bypasses CBC in control task) ──────────── */
/* Returns 1 if a SET_SP command was received within the last 500 ms.
 * The control task checks this to skip the CBC output and use the PC setpoint.
 * Automatically clears after RPM_OVERRIDE_TIMEOUT_MS without a new SET_SP. */
uint8_t VCP_IsRpmOverrideActive(void);

#endif /* TASK_COMMS_H */
