#ifndef HOST_LINK_H
#define HOST_LINK_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include "host_link_protocol.h"

typedef struct
{
    uint32_t uptime_ms;
    HostLinkMode_t mode;
    uint16_t active_fault_code;
    uint16_t protocol_errors;
    uint16_t uart_rx_overruns;
    uint16_t uart_tx_drops;
    uint16_t last_error;
    uint8_t storage_state;
} HostLinkRuntimeHealth_t;

void HOSTLINK_Init(void);
void HOSTLINK_Process(void);
void HOSTLINK_GetRuntimeHealth(HostLinkRuntimeHealth_t *health);

#ifdef __cplusplus
}
#endif

#endif /* HOST_LINK_H */
