#include "host_link_params.h"

#include <string.h>

static HostLinkParamStore_t g_host_link_params;

static const HostLinkParamDescriptor_t g_host_link_param_table[] =
{
    { HOST_PARAM_CONTROL_SAMPLE_MS, HOST_LINK_PARAM_TYPE_F32, HOST_LINK_PARAM_FLAG_PERSISTENT, "control.sample_time_ms", "ms", "control.general", 1.0f, 20.0f, 5.0f },
    { HOST_PARAM_ANGLE_KP, HOST_LINK_PARAM_TYPE_F32, HOST_LINK_PARAM_FLAG_PERSISTENT, "angle.kp", "", "control.angle", 0.0f, 200.0f, 35.0f },
    { HOST_PARAM_ANGLE_KI, HOST_LINK_PARAM_TYPE_F32, HOST_LINK_PARAM_FLAG_PERSISTENT, "angle.ki", "", "control.angle", 0.0f, 200.0f, 0.0f },
    { HOST_PARAM_ANGLE_KD, HOST_LINK_PARAM_TYPE_F32, HOST_LINK_PARAM_FLAG_PERSISTENT, "angle.kd", "", "control.angle", 0.0f, 200.0f, 1.2f },
    { HOST_PARAM_ANGLE_OUTPUT_LIMIT, HOST_LINK_PARAM_TYPE_F32, HOST_LINK_PARAM_FLAG_PERSISTENT, "angle.output_limit", "", "control.angle", 0.1f, 1.0f, 1.0f },
    { HOST_PARAM_VELOCITY_KP, HOST_LINK_PARAM_TYPE_F32, HOST_LINK_PARAM_FLAG_PERSISTENT, "velocity.kp", "", "control.velocity", 0.0f, 50.0f, 0.8f },
    { HOST_PARAM_VELOCITY_KI, HOST_LINK_PARAM_TYPE_F32, HOST_LINK_PARAM_FLAG_PERSISTENT, "velocity.ki", "", "control.velocity", 0.0f, 50.0f, 0.05f },
    { HOST_PARAM_VELOCITY_KD, HOST_LINK_PARAM_TYPE_F32, HOST_LINK_PARAM_FLAG_PERSISTENT, "velocity.kd", "", "control.velocity", 0.0f, 50.0f, 0.0f },
    { HOST_PARAM_SAFETY_TILT_CUTOFF_DEG, HOST_LINK_PARAM_TYPE_F32, HOST_LINK_PARAM_FLAG_PERSISTENT, "safety.tilt_cutoff_deg", "deg", "safety", 5.0f, 80.0f, 45.0f },
    { HOST_PARAM_CONTROL_BALANCE_ENABLE, HOST_LINK_PARAM_TYPE_BOOL, HOST_LINK_PARAM_FLAG_PERSISTENT, "control.balance_enable", "", "control.general", 0.0f, 1.0f, 0.0f },
};

static const HostLinkParamDescriptor_t *HOSTLINK_Params_FindDescriptor(uint16_t id)
{
    uint16_t index;

    for (index = 0; index < (uint16_t)(sizeof(g_host_link_param_table) / sizeof(g_host_link_param_table[0])); ++index)
    {
        if (g_host_link_param_table[index].id == id)
        {
            return &g_host_link_param_table[index];
        }
    }

    return NULL;
}

void HOSTLINK_Params_ResetDefaults(HostLinkParamStore_t *store)
{
    if (store == NULL)
    {
        return;
    }

    store->control_sample_ms = 5.0f;
    store->angle_kp = 35.0f;
    store->angle_ki = 0.0f;
    store->angle_kd = 1.2f;
    store->angle_output_limit = 1.0f;
    store->velocity_kp = 0.8f;
    store->velocity_ki = 0.05f;
    store->velocity_kd = 0.0f;
    store->safety_tilt_cutoff_deg = 45.0f;
    store->control_balance_enable = 0u;
}

uint16_t HOSTLINK_Params_Count(void)
{
    return (uint16_t)(sizeof(g_host_link_param_table) / sizeof(g_host_link_param_table[0]));
}

const HostLinkParamDescriptor_t *HOSTLINK_Params_GetByIndex(uint16_t index)
{
    if (index >= HOSTLINK_Params_Count())
    {
        return NULL;
    }

    return &g_host_link_param_table[index];
}

const HostLinkParamDescriptor_t *HOSTLINK_Params_GetById(uint16_t id)
{
    return HOSTLINK_Params_FindDescriptor(id);
}

const HostLinkParamStore_t *HOSTLINK_Params_Current(void)
{
    return &g_host_link_params;
}

HostLinkParamStore_t *HOSTLINK_Params_CurrentMutable(void)
{
    return &g_host_link_params;
}

static void HOSTLINK_Params_ReadFloat(float value, uint8_t out_value[4])
{
    memcpy(out_value, &value, sizeof(float));
}

static float HOSTLINK_Params_ParseFloat(const uint8_t value[4])
{
    float parsed = 0.0f;

    memcpy(&parsed, value, sizeof(float));
    return parsed;
}

uint8_t HOSTLINK_Params_Read(uint16_t id, uint8_t *type, uint8_t out_value[4])
{
    const HostLinkParamDescriptor_t *descriptor = HOSTLINK_Params_FindDescriptor(id);

    if ((descriptor == NULL) || (type == NULL) || (out_value == NULL))
    {
        return 0u;
    }

    *type = descriptor->type;
    memset(out_value, 0, 4u);

    switch (id)
    {
        case HOST_PARAM_CONTROL_SAMPLE_MS:
            HOSTLINK_Params_ReadFloat(g_host_link_params.control_sample_ms, out_value);
            break;
        case HOST_PARAM_ANGLE_KP:
            HOSTLINK_Params_ReadFloat(g_host_link_params.angle_kp, out_value);
            break;
        case HOST_PARAM_ANGLE_KI:
            HOSTLINK_Params_ReadFloat(g_host_link_params.angle_ki, out_value);
            break;
        case HOST_PARAM_ANGLE_KD:
            HOSTLINK_Params_ReadFloat(g_host_link_params.angle_kd, out_value);
            break;
        case HOST_PARAM_ANGLE_OUTPUT_LIMIT:
            HOSTLINK_Params_ReadFloat(g_host_link_params.angle_output_limit, out_value);
            break;
        case HOST_PARAM_VELOCITY_KP:
            HOSTLINK_Params_ReadFloat(g_host_link_params.velocity_kp, out_value);
            break;
        case HOST_PARAM_VELOCITY_KI:
            HOSTLINK_Params_ReadFloat(g_host_link_params.velocity_ki, out_value);
            break;
        case HOST_PARAM_VELOCITY_KD:
            HOSTLINK_Params_ReadFloat(g_host_link_params.velocity_kd, out_value);
            break;
        case HOST_PARAM_SAFETY_TILT_CUTOFF_DEG:
            HOSTLINK_Params_ReadFloat(g_host_link_params.safety_tilt_cutoff_deg, out_value);
            break;
        case HOST_PARAM_CONTROL_BALANCE_ENABLE:
            out_value[0] = g_host_link_params.control_balance_enable;
            break;
        default:
            return 0u;
    }

    return 1u;
}

HostLinkError_t HOSTLINK_Params_Write(uint16_t id, uint8_t type, const uint8_t value[4])
{
    const HostLinkParamDescriptor_t *descriptor = HOSTLINK_Params_FindDescriptor(id);
    float float_value;

    if ((descriptor == NULL) || (value == NULL))
    {
        return HOST_LINK_ERR_PARAM_NOT_FOUND;
    }

    if (descriptor->type != type)
    {
        return HOST_LINK_ERR_PARAM_OUT_OF_RANGE;
    }

    if (type == HOST_LINK_PARAM_TYPE_BOOL)
    {
        if (value[0] > 1u)
        {
            return HOST_LINK_ERR_PARAM_OUT_OF_RANGE;
        }
    }
    else
    {
        float_value = HOSTLINK_Params_ParseFloat(value);
        if ((float_value < descriptor->min_value) || (float_value > descriptor->max_value))
        {
            return HOST_LINK_ERR_PARAM_OUT_OF_RANGE;
        }
    }

    switch (id)
    {
        case HOST_PARAM_CONTROL_SAMPLE_MS:
            g_host_link_params.control_sample_ms = HOSTLINK_Params_ParseFloat(value);
            break;
        case HOST_PARAM_ANGLE_KP:
            g_host_link_params.angle_kp = HOSTLINK_Params_ParseFloat(value);
            break;
        case HOST_PARAM_ANGLE_KI:
            g_host_link_params.angle_ki = HOSTLINK_Params_ParseFloat(value);
            break;
        case HOST_PARAM_ANGLE_KD:
            g_host_link_params.angle_kd = HOSTLINK_Params_ParseFloat(value);
            break;
        case HOST_PARAM_ANGLE_OUTPUT_LIMIT:
            g_host_link_params.angle_output_limit = HOSTLINK_Params_ParseFloat(value);
            break;
        case HOST_PARAM_VELOCITY_KP:
            g_host_link_params.velocity_kp = HOSTLINK_Params_ParseFloat(value);
            break;
        case HOST_PARAM_VELOCITY_KI:
            g_host_link_params.velocity_ki = HOSTLINK_Params_ParseFloat(value);
            break;
        case HOST_PARAM_VELOCITY_KD:
            g_host_link_params.velocity_kd = HOSTLINK_Params_ParseFloat(value);
            break;
        case HOST_PARAM_SAFETY_TILT_CUTOFF_DEG:
            g_host_link_params.safety_tilt_cutoff_deg = HOSTLINK_Params_ParseFloat(value);
            break;
        case HOST_PARAM_CONTROL_BALANCE_ENABLE:
            g_host_link_params.control_balance_enable = value[0];
            break;
        default:
            return HOST_LINK_ERR_PARAM_NOT_FOUND;
    }

    return HOST_LINK_ERR_NONE;
}

void HOSTLINK_Params_ReplaceAll(const HostLinkParamStore_t *store)
{
    if (store == NULL)
    {
        return;
    }

    g_host_link_params = *store;
}
