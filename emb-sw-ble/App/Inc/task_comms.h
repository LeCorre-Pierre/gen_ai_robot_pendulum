#ifndef TASK_COMMS_H
#define TASK_COMMS_H

#include <stdint.h>

/* ── Lifecycle ─────────────────────────────────────────────────────────────── */
void Task_comms_Init(void);

/* ── USART1 channel selector (ST-Link VCP) ─────────────────────────────────────
 * The ST-Link VCP is a single physical UART (USART1, PB6/PB7) shared between:
 *   - the BLE debug trace console (APP_DBG_MSG), and
 *   - the binary VCP telemetry consumed by app-cbc-tuning.
 * They cannot run at the same time, so a runtime variable selects the owner.
 *   0 = BLE debug trace   (default)
 *   1 = VCP telemetry
 * task_comms auto-switches to VCP on the first valid command received; wire a
 * button to VCP_SetChannel() later to switch back to the trace console. */
void    VCP_SetChannel(uint8_t vcp_active);
uint8_t VCP_IsChannelActive(void);

#endif /* TASK_COMMS_H */
