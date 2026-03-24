#ifndef HOST_LINK_PARAMS_H
#define HOST_LINK_PARAMS_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include "host_link_protocol.h"

typedef enum
{
    HOST_PARAM_CONTROL_SAMPLE_MS = 0x1000,
    HOST_PARAM_ANGLE_KP = 0x1001,
    HOST_PARAM_ANGLE_KI = 0x1002,
    HOST_PARAM_ANGLE_KD = 0x1003,
    HOST_PARAM_ANGLE_OUTPUT_LIMIT = 0x1004,
    HOST_PARAM_VELOCITY_KP = 0x1010,
    HOST_PARAM_VELOCITY_KI = 0x1011,
    HOST_PARAM_VELOCITY_KD = 0x1012,
    HOST_PARAM_SAFETY_TILT_CUTOFF_DEG = 0x1020,
    HOST_PARAM_CONTROL_BALANCE_ENABLE = 0x1030,
} HostLinkParamId_t;

typedef struct
{
    float control_sample_ms;
    float angle_kp;
    float angle_ki;
    float angle_kd;
    float angle_output_limit;
    float velocity_kp;
    float velocity_ki;
    float velocity_kd;
    float safety_tilt_cutoff_deg;
    uint8_t control_balance_enable;
} HostLinkParamStore_t;

typedef struct
{
    uint16_t id;
    uint8_t type;
    uint8_t flags;
    const char *key;
    const char *unit;
    const char *group;
    float min_value;
    float max_value;
    float default_value;
} HostLinkParamDescriptor_t;

void HOSTLINK_Params_ResetDefaults(HostLinkParamStore_t *store);
uint16_t HOSTLINK_Params_Count(void);
const HostLinkParamDescriptor_t *HOSTLINK_Params_GetByIndex(uint16_t index);
const HostLinkParamDescriptor_t *HOSTLINK_Params_GetById(uint16_t id);
const HostLinkParamStore_t *HOSTLINK_Params_Current(void);
HostLinkParamStore_t *HOSTLINK_Params_CurrentMutable(void);
uint8_t HOSTLINK_Params_Read(uint16_t id, uint8_t *type, uint8_t out_value[4]);
HostLinkError_t HOSTLINK_Params_Write(uint16_t id, uint8_t type, const uint8_t value[4]);
void HOSTLINK_Params_ReplaceAll(const HostLinkParamStore_t *store);

#ifdef __cplusplus
}
#endif

#endif /* HOST_LINK_PARAMS_H */
