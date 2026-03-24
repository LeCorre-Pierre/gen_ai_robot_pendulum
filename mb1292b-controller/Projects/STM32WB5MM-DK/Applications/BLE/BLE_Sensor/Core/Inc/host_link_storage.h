#ifndef HOST_LINK_STORAGE_H
#define HOST_LINK_STORAGE_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include "host_link_params.h"

typedef enum
{
    HOST_LINK_STORAGE_STATE_UNINITIALIZED = 0,
    HOST_LINK_STORAGE_STATE_READY = 1,
    HOST_LINK_STORAGE_STATE_FALLBACK_DEFAULTS = 2,
    HOST_LINK_STORAGE_STATE_ERROR = 3,
} HostLinkStorageState_t;

int32_t HOSTLINK_Storage_Init(void);
int32_t HOSTLINK_Storage_Load(HostLinkParamStore_t *store);
int32_t HOSTLINK_Storage_Save(const HostLinkParamStore_t *store);
HostLinkStorageState_t HOSTLINK_Storage_GetState(void);

#ifdef __cplusplus
}
#endif

#endif /* HOST_LINK_STORAGE_H */
