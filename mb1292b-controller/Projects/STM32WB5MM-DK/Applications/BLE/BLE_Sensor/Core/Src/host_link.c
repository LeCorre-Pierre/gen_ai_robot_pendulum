#include "host_link.h"

#include <string.h>

#include "main.h"
#include "app_conf.h"
#include "host_link_protocol.h"
#include "host_link_params.h"
#include "host_link_storage.h"
#include "hw_if.h"
#include "stm32wb5mm_dk_qspi.h"

typedef struct
{
    uint8_t version;
    uint8_t type;
    uint8_t flags;
    uint8_t seq;
    uint16_t length;
    uint8_t payload[HOST_LINK_MAX_PAYLOAD_SIZE];
} HostLinkPacket_t;

typedef struct
{
    uint8_t stream_id;
    uint8_t enabled;
    uint16_t period_ms;
    uint32_t next_due_ms;
} HostLinkStreamConfig_t;

typedef enum
{
    HOST_LINK_RX_WAIT_SOF1 = 0,
    HOST_LINK_RX_WAIT_SOF2,
    HOST_LINK_RX_WAIT_VER,
    HOST_LINK_RX_WAIT_TYPE,
    HOST_LINK_RX_WAIT_FLAGS,
    HOST_LINK_RX_WAIT_SEQ,
    HOST_LINK_RX_WAIT_LEN_L,
    HOST_LINK_RX_WAIT_LEN_H,
    HOST_LINK_RX_WAIT_PAYLOAD,
    HOST_LINK_RX_WAIT_CRC_L,
    HOST_LINK_RX_WAIT_CRC_H,
    HOST_LINK_RX_WAIT_EOF,
} HostLinkRxState_t;

static volatile uint8_t g_host_link_rx_byte;
static volatile uint8_t g_host_link_packet_ready;
static volatile uint8_t g_host_link_tx_busy;
static volatile uint32_t g_host_link_uptime_ms;
static HostLinkPacket_t g_host_link_rx_packet;
static HostLinkPacket_t g_host_link_pending_packet;
static HostLinkRxState_t g_host_link_rx_state = HOST_LINK_RX_WAIT_SOF1;
static uint16_t g_host_link_rx_payload_index;
static uint16_t g_host_link_rx_crc;
static uint16_t g_host_link_received_crc;
static uint8_t g_host_link_tx_buffer[HOST_LINK_MAX_FRAME_SIZE];
static HostLinkStreamConfig_t g_host_link_streams[] =
{
    { HOST_LINK_STREAM_CONTROL_FAST, 0u, 10u, 0u },
    { HOST_LINK_STREAM_SENSORS, 0u, 20u, 0u },
    { HOST_LINK_STREAM_ACTUATORS_POWER, 0u, 20u, 0u },
    { HOST_LINK_STREAM_RUNTIME_HEALTH, 0u, 100u, 0u },
    { HOST_LINK_STREAM_ENCODERS, 0u, 20u, 0u },
    { HOST_LINK_STREAM_FAULT_FOCUS, 0u, 0u, 0u },
};
static HostLinkRuntimeHealth_t g_host_link_health;
static HostLinkMode_t g_host_link_mode = HOST_LINK_MODE_BOOT;
static uint8_t g_host_link_pending_boot_event = 1u;
static uint8_t g_host_link_pending_mode_event = 1u;

static uint16_t HOSTLINK_Crc16Update(uint16_t crc, uint8_t data)
{
    uint8_t bit;

    crc ^= (uint16_t)data << 8;
    for (bit = 0u; bit < 8u; ++bit)
    {
        if ((crc & 0x8000u) != 0u)
        {
            crc = (uint16_t)((crc << 1) ^ 0x1021u);
        }
        else
        {
            crc <<= 1;
        }
    }

    return crc;
}

static uint16_t HOSTLINK_ComputePacketCrc(const HostLinkPacket_t *packet)
{
    uint16_t crc = 0xFFFFu;
    uint16_t index;

    crc = HOSTLINK_Crc16Update(crc, packet->version);
    crc = HOSTLINK_Crc16Update(crc, packet->type);
    crc = HOSTLINK_Crc16Update(crc, packet->flags);
    crc = HOSTLINK_Crc16Update(crc, packet->seq);
    crc = HOSTLINK_Crc16Update(crc, (uint8_t)(packet->length & 0xFFu));
    crc = HOSTLINK_Crc16Update(crc, (uint8_t)(packet->length >> 8));

    for (index = 0u; index < packet->length; ++index)
    {
        crc = HOSTLINK_Crc16Update(crc, packet->payload[index]);
    }

    return crc;
}

static void HOSTLINK_TxDoneCallback(void)
{
    g_host_link_tx_busy = 0u;
}

static uint8_t HOSTLINK_SendPacket(uint8_t type, uint8_t flags, uint8_t seq, const uint8_t *payload, uint16_t length)
{
    HostLinkPacket_t packet;
    uint16_t crc;
    uint16_t frame_length;
    uint16_t offset = 0u;

    if ((length > HOST_LINK_MAX_PAYLOAD_SIZE) || (g_host_link_tx_busy != 0u))
    {
        ++g_host_link_health.uart_tx_drops;
        return 0u;
    }

    packet.version = HOST_LINK_PROTOCOL_VERSION;
    packet.type = type;
    packet.flags = flags;
    packet.seq = seq;
    packet.length = length;

    if ((payload != NULL) && (length > 0u))
    {
        memcpy(packet.payload, payload, length);
    }

    crc = HOSTLINK_ComputePacketCrc(&packet);

    g_host_link_tx_buffer[offset++] = HOST_LINK_SOF1;
    g_host_link_tx_buffer[offset++] = HOST_LINK_SOF2;
    g_host_link_tx_buffer[offset++] = packet.version;
    g_host_link_tx_buffer[offset++] = packet.type;
    g_host_link_tx_buffer[offset++] = packet.flags;
    g_host_link_tx_buffer[offset++] = packet.seq;
    g_host_link_tx_buffer[offset++] = (uint8_t)(packet.length & 0xFFu);
    g_host_link_tx_buffer[offset++] = (uint8_t)(packet.length >> 8);

    if (packet.length > 0u)
    {
        memcpy(&g_host_link_tx_buffer[offset], packet.payload, packet.length);
        offset = (uint16_t)(offset + packet.length);
    }

    g_host_link_tx_buffer[offset++] = (uint8_t)(crc & 0xFFu);
    g_host_link_tx_buffer[offset++] = (uint8_t)(crc >> 8);
    g_host_link_tx_buffer[offset++] = HOST_LINK_EOF;
    frame_length = offset;

    g_host_link_tx_busy = 1u;
    if (HW_UART_Transmit_DMA((hw_uart_id_t)CFG_DEBUG_TRACE_UART, g_host_link_tx_buffer, frame_length, HOSTLINK_TxDoneCallback) != hw_uart_ok)
    {
        g_host_link_tx_busy = 0u;
        ++g_host_link_health.uart_tx_drops;
        return 0u;
    }

    return 1u;
}

static void HOSTLINK_SendAck(uint8_t request_type, uint8_t seq)
{
    uint8_t payload[2];

    payload[0] = request_type;
    payload[1] = seq;
    (void)HOSTLINK_SendPacket(HOST_LINK_TYPE_ACK, HOST_LINK_FLAG_NONE, seq, payload, sizeof(payload));
}

static void HOSTLINK_SendNack(uint8_t request_type, uint8_t seq, uint8_t error_code)
{
    uint8_t payload[3];

    payload[0] = request_type;
    payload[1] = seq;
    payload[2] = error_code;
    (void)HOSTLINK_SendPacket(HOST_LINK_TYPE_NACK, HOST_LINK_FLAG_ERROR, seq, payload, sizeof(payload));
}

static uint16_t HOSTLINK_ParamValueSize(uint8_t type)
{
    switch (type)
    {
        case HOST_LINK_PARAM_TYPE_BOOL:
        case HOST_LINK_PARAM_TYPE_U8:
            return 1u;
        case HOST_LINK_PARAM_TYPE_I32:
        case HOST_LINK_PARAM_TYPE_F32:
            return 4u;
        default:
            return 0u;
    }
}

static void HOSTLINK_WriteVariantValue(uint8_t type, float value, uint8_t *buffer, uint16_t *offset)
{
    uint8_t bool_value;

    if ((buffer == NULL) || (offset == NULL))
    {
        return;
    }

    if (type == HOST_LINK_PARAM_TYPE_BOOL)
    {
        bool_value = (value != 0.0f) ? 1u : 0u;
        buffer[(*offset)++] = bool_value;
    }
    else
    {
        memcpy(&buffer[*offset], &value, sizeof(float));
        *offset = (uint16_t)(*offset + sizeof(float));
    }
}

static HostLinkStreamConfig_t *HOSTLINK_FindStreamConfig(uint8_t stream_id)
{
    uint32_t index;

    for (index = 0u; index < (sizeof(g_host_link_streams) / sizeof(g_host_link_streams[0])); ++index)
    {
        if (g_host_link_streams[index].stream_id == stream_id)
        {
            return &g_host_link_streams[index];
        }
    }

    return NULL;
}

static void HOSTLINK_SetMode(HostLinkMode_t mode)
{
    if (g_host_link_mode != mode)
    {
        g_host_link_mode = mode;
        g_host_link_pending_mode_event = 1u;
    }
}

static void HOSTLINK_RxCallback(void)
{
    uint8_t byte = g_host_link_rx_byte;

    switch (g_host_link_rx_state)
    {
        case HOST_LINK_RX_WAIT_SOF1:
            if (byte == HOST_LINK_SOF1)
            {
                g_host_link_rx_state = HOST_LINK_RX_WAIT_SOF2;
            }
            break;

        case HOST_LINK_RX_WAIT_SOF2:
            if (byte == HOST_LINK_SOF2)
            {
                g_host_link_rx_state = HOST_LINK_RX_WAIT_VER;
                g_host_link_rx_crc = 0xFFFFu;
            }
            else
            {
                g_host_link_rx_state = HOST_LINK_RX_WAIT_SOF1;
            }
            break;

        case HOST_LINK_RX_WAIT_VER:
            g_host_link_rx_packet.version = byte;
            g_host_link_rx_crc = HOSTLINK_Crc16Update(g_host_link_rx_crc, byte);
            g_host_link_rx_state = HOST_LINK_RX_WAIT_TYPE;
            break;

        case HOST_LINK_RX_WAIT_TYPE:
            g_host_link_rx_packet.type = byte;
            g_host_link_rx_crc = HOSTLINK_Crc16Update(g_host_link_rx_crc, byte);
            g_host_link_rx_state = HOST_LINK_RX_WAIT_FLAGS;
            break;

        case HOST_LINK_RX_WAIT_FLAGS:
            g_host_link_rx_packet.flags = byte;
            g_host_link_rx_crc = HOSTLINK_Crc16Update(g_host_link_rx_crc, byte);
            g_host_link_rx_state = HOST_LINK_RX_WAIT_SEQ;
            break;

        case HOST_LINK_RX_WAIT_SEQ:
            g_host_link_rx_packet.seq = byte;
            g_host_link_rx_crc = HOSTLINK_Crc16Update(g_host_link_rx_crc, byte);
            g_host_link_rx_state = HOST_LINK_RX_WAIT_LEN_L;
            break;

        case HOST_LINK_RX_WAIT_LEN_L:
            g_host_link_rx_packet.length = byte;
            g_host_link_rx_crc = HOSTLINK_Crc16Update(g_host_link_rx_crc, byte);
            g_host_link_rx_state = HOST_LINK_RX_WAIT_LEN_H;
            break;

        case HOST_LINK_RX_WAIT_LEN_H:
            g_host_link_rx_packet.length |= (uint16_t)byte << 8;
            g_host_link_rx_crc = HOSTLINK_Crc16Update(g_host_link_rx_crc, byte);
            g_host_link_rx_payload_index = 0u;
            if (g_host_link_rx_packet.length > HOST_LINK_MAX_PAYLOAD_SIZE)
            {
                ++g_host_link_health.protocol_errors;
                g_host_link_health.last_error = HOST_LINK_ERR_BAD_LENGTH;
                g_host_link_rx_state = HOST_LINK_RX_WAIT_SOF1;
            }
            else if (g_host_link_rx_packet.length == 0u)
            {
                g_host_link_rx_state = HOST_LINK_RX_WAIT_CRC_L;
            }
            else
            {
                g_host_link_rx_state = HOST_LINK_RX_WAIT_PAYLOAD;
            }
            break;

        case HOST_LINK_RX_WAIT_PAYLOAD:
            g_host_link_rx_packet.payload[g_host_link_rx_payload_index++] = byte;
            g_host_link_rx_crc = HOSTLINK_Crc16Update(g_host_link_rx_crc, byte);
            if (g_host_link_rx_payload_index >= g_host_link_rx_packet.length)
            {
                g_host_link_rx_state = HOST_LINK_RX_WAIT_CRC_L;
            }
            break;

        case HOST_LINK_RX_WAIT_CRC_L:
            g_host_link_received_crc = byte;
            g_host_link_rx_state = HOST_LINK_RX_WAIT_CRC_H;
            break;

        case HOST_LINK_RX_WAIT_CRC_H:
            g_host_link_received_crc |= (uint16_t)byte << 8;
            g_host_link_rx_state = HOST_LINK_RX_WAIT_EOF;
            break;

        case HOST_LINK_RX_WAIT_EOF:
            if ((byte == HOST_LINK_EOF) && (g_host_link_received_crc == g_host_link_rx_crc))
            {
                g_host_link_pending_packet = g_host_link_rx_packet;
                g_host_link_packet_ready = 1u;
            }
            else
            {
                ++g_host_link_health.protocol_errors;
                g_host_link_health.last_error = (byte == HOST_LINK_EOF) ? HOST_LINK_ERR_BAD_CRC : HOST_LINK_ERR_BAD_LENGTH;
            }
            g_host_link_rx_state = HOST_LINK_RX_WAIT_SOF1;
            break;

        default:
            g_host_link_rx_state = HOST_LINK_RX_WAIT_SOF1;
            break;
    }

    HW_UART_Receive_IT((hw_uart_id_t)CFG_DEBUG_TRACE_UART, (uint8_t *)&g_host_link_rx_byte, 1u, HOSTLINK_RxCallback);
}

static void HOSTLINK_HandlePing(const HostLinkPacket_t *request)
{
    uint8_t payload[5];
    uint32_t uptime_ms = g_host_link_uptime_ms;

    memcpy(&payload[0], &uptime_ms, sizeof(uint32_t));
    payload[4] = HOST_LINK_PROTOCOL_VERSION;
    (void)HOSTLINK_SendPacket(HOST_LINK_TYPE_PONG, HOST_LINK_FLAG_NONE, request->seq, payload, sizeof(payload));
}

static void HOSTLINK_HandleGetDeviceInfo(const HostLinkPacket_t *request)
{
    uint8_t payload[25];
    uint8_t flash_id[3] = {0u, 0u, 0u};
    uint16_t param_count = HOSTLINK_Params_Count();
    uint32_t capability_bitmap = 0u;
    uint8_t index = 0u;

    capability_bitmap |= (1u << 0);
    capability_bitmap |= (1u << 1);
    capability_bitmap |= (1u << 2);
    capability_bitmap |= (1u << 3);
    capability_bitmap |= (1u << 4);

    memset(payload, 0, sizeof(payload));
    payload[index++] = HOST_LINK_PROTOCOL_VERSION;
    payload[index++] = 0x01u;
    memcpy(&payload[index], &param_count, sizeof(param_count));
    index = (uint8_t)(index + sizeof(param_count));
    memcpy(&payload[index], &capability_bitmap, sizeof(capability_bitmap));
    index = (uint8_t)(index + sizeof(capability_bitmap));
    payload[index++] = (uint8_t)HOSTLINK_Storage_GetState();
    payload[index++] = (uint8_t)g_host_link_mode;
    (void)BSP_QSPI_ReadID(0u, flash_id);
    payload[index++] = flash_id[0];
    payload[index++] = flash_id[1];
    payload[index++] = flash_id[2];
    memcpy(&payload[index], "mb1292b-host", 12u);

    (void)HOSTLINK_SendPacket(HOST_LINK_TYPE_DEVICE_INFO, HOST_LINK_FLAG_NONE, request->seq, payload, sizeof(payload));
}

static void HOSTLINK_HandleGetParameterTable(const HostLinkPacket_t *request)
{
    uint8_t payload[HOST_LINK_MAX_PAYLOAD_SIZE];
    uint16_t offset = 0u;
    uint16_t count = HOSTLINK_Params_Count();
    uint16_t index;

    memcpy(&payload[offset], &count, sizeof(count));
    offset = (uint16_t)(offset + sizeof(count));

    for (index = 0u; index < count; ++index)
    {
        const HostLinkParamDescriptor_t *descriptor = HOSTLINK_Params_GetByIndex(index);
        uint8_t key_length;
        uint8_t unit_length;
        uint8_t group_length;
        uint16_t entry_size;
        uint16_t value_size;

        if (descriptor == NULL)
        {
            continue;
        }

        value_size = HOSTLINK_ParamValueSize(descriptor->type);
        key_length = (uint8_t)strlen(descriptor->key);
        unit_length = (uint8_t)strlen(descriptor->unit);
        group_length = (uint8_t)strlen(descriptor->group);
        entry_size = (uint16_t)(2u + 1u + 1u + (3u * value_size) + 1u + key_length + 1u + unit_length + 1u + group_length);
        if ((offset + entry_size) > HOST_LINK_MAX_PAYLOAD_SIZE)
        {
            break;
        }

        payload[offset++] = (uint8_t)(descriptor->id & 0xFFu);
        payload[offset++] = (uint8_t)(descriptor->id >> 8);
        payload[offset++] = descriptor->type;
        payload[offset++] = descriptor->flags;
        HOSTLINK_WriteVariantValue(descriptor->type, descriptor->min_value, payload, &offset);
        HOSTLINK_WriteVariantValue(descriptor->type, descriptor->max_value, payload, &offset);
        HOSTLINK_WriteVariantValue(descriptor->type, descriptor->default_value, payload, &offset);
        payload[offset++] = key_length;
        memcpy(&payload[offset], descriptor->key, key_length);
        offset = (uint16_t)(offset + key_length);
        payload[offset++] = unit_length;
        memcpy(&payload[offset], descriptor->unit, unit_length);
        offset = (uint16_t)(offset + unit_length);
        payload[offset++] = group_length;
        memcpy(&payload[offset], descriptor->group, group_length);
        offset = (uint16_t)(offset + group_length);
    }

    (void)HOSTLINK_SendPacket(HOST_LINK_TYPE_PARAMETER_TABLE, HOST_LINK_FLAG_NONE, request->seq, payload, offset);
}

static void HOSTLINK_SendParameterValue(uint8_t seq, uint16_t id)
{
    uint8_t payload[7];
    uint8_t type = 0u;

    if (HOSTLINK_Params_Read(id, &type, &payload[3]) == 0u)
    {
        HOSTLINK_SendNack(HOST_LINK_TYPE_READ_PARAMETER, seq, HOST_LINK_ERR_PARAM_NOT_FOUND);
        return;
    }

    payload[0] = (uint8_t)(id & 0xFFu);
    payload[1] = (uint8_t)(id >> 8);
    payload[2] = type;
    (void)HOSTLINK_SendPacket(HOST_LINK_TYPE_PARAMETER_VALUE, HOST_LINK_FLAG_NONE, seq, payload, sizeof(payload));
}

static void HOSTLINK_HandleReadParameter(const HostLinkPacket_t *request)
{
    uint16_t id;

    if (request->length != 2u)
    {
        HOSTLINK_SendNack(request->type, request->seq, HOST_LINK_ERR_BAD_LENGTH);
        return;
    }

    id = (uint16_t)request->payload[0] | ((uint16_t)request->payload[1] << 8);
    HOSTLINK_SendParameterValue(request->seq, id);
}

static void HOSTLINK_HandleWriteParameter(const HostLinkPacket_t *request)
{
    uint16_t id;
    HostLinkError_t error;

    if (request->length != 7u)
    {
        HOSTLINK_SendNack(request->type, request->seq, HOST_LINK_ERR_BAD_LENGTH);
        return;
    }

    id = (uint16_t)request->payload[0] | ((uint16_t)request->payload[1] << 8);
    error = HOSTLINK_Params_Write(id, request->payload[2], &request->payload[3]);
    if (error != HOST_LINK_ERR_NONE)
    {
        HOSTLINK_SendNack(request->type, request->seq, (uint8_t)error);
        return;
    }

    HOSTLINK_SendAck(request->type, request->seq);
}

static void HOSTLINK_HandleSaveParameters(const HostLinkPacket_t *request)
{
    if (HOSTLINK_Storage_Save(HOSTLINK_Params_Current()) != BSP_ERROR_NONE)
    {
        HOSTLINK_SendNack(request->type, request->seq, HOST_LINK_ERR_STORAGE);
        return;
    }

    HOSTLINK_SendAck(request->type, request->seq);
}

static void HOSTLINK_HandleLoadParameters(const HostLinkPacket_t *request)
{
    HostLinkParamStore_t store;

    HOSTLINK_Params_ResetDefaults(&store);
    if ((request->length == 0u) || (request->payload[0] == 0u))
    {
        if (HOSTLINK_Storage_Load(&store) != BSP_ERROR_NONE)
        {
            HOSTLINK_Params_ResetDefaults(&store);
        }
    }

    HOSTLINK_Params_ReplaceAll(&store);
    HOSTLINK_SendAck(request->type, request->seq);
}

static void HOSTLINK_SendStreamConfigPacket(uint8_t seq, const HostLinkStreamConfig_t *stream)
{
    uint8_t payload[4];

    if (stream == NULL)
    {
        return;
    }

    payload[0] = stream->stream_id;
    payload[1] = stream->enabled;
    payload[2] = (uint8_t)(stream->period_ms & 0xFFu);
    payload[3] = (uint8_t)(stream->period_ms >> 8);
    (void)HOSTLINK_SendPacket(HOST_LINK_TYPE_STREAM_CONFIG, HOST_LINK_FLAG_NONE, seq, payload, sizeof(payload));
}

static void HOSTLINK_HandleSetStreamConfig(const HostLinkPacket_t *request)
{
    HostLinkStreamConfig_t *stream;
    uint16_t period;

    if (request->length != 4u)
    {
        HOSTLINK_SendNack(request->type, request->seq, HOST_LINK_ERR_BAD_LENGTH);
        return;
    }

    stream = HOSTLINK_FindStreamConfig(request->payload[0]);
    if (stream == NULL)
    {
        HOSTLINK_SendNack(request->type, request->seq, HOST_LINK_ERR_UNKNOWN_TYPE);
        return;
    }

    period = (uint16_t)request->payload[2] | ((uint16_t)request->payload[3] << 8);
    stream->enabled = request->payload[1] ? 1u : 0u;
    if (stream->stream_id == HOST_LINK_STREAM_FAULT_FOCUS)
    {
        stream->period_ms = period;
    }
    else if (period != 0u)
    {
        stream->period_ms = period;
    }
    stream->next_due_ms = g_host_link_uptime_ms + stream->period_ms;
    HOSTLINK_SendStreamConfigPacket(request->seq, stream);
}

static void HOSTLINK_HandleGetStreamConfig(const HostLinkPacket_t *request)
{
    HostLinkStreamConfig_t *stream;

    if (request->length != 1u)
    {
        HOSTLINK_SendNack(request->type, request->seq, HOST_LINK_ERR_BAD_LENGTH);
        return;
    }

    stream = HOSTLINK_FindStreamConfig(request->payload[0]);
    if (stream == NULL)
    {
        HOSTLINK_SendNack(request->type, request->seq, HOST_LINK_ERR_UNKNOWN_TYPE);
        return;
    }

    HOSTLINK_SendStreamConfigPacket(request->seq, stream);
}

static void HOSTLINK_SendEvent(uint16_t event_code)
{
    uint8_t payload[7];
    uint16_t offset = 0u;
    uint32_t timestamp_ms = g_host_link_uptime_ms;

    memcpy(&payload[offset], &timestamp_ms, sizeof(timestamp_ms));
    offset = (uint16_t)(offset + sizeof(timestamp_ms));
    memcpy(&payload[offset], &event_code, sizeof(event_code));
    offset = (uint16_t)(offset + sizeof(event_code));
    payload[offset++] = (uint8_t)g_host_link_mode;
    (void)HOSTLINK_SendPacket(HOST_LINK_TYPE_EVENT, HOST_LINK_FLAG_NONE, 0u, payload, offset);
}

static void HOSTLINK_SendControlFast(void)
{
    uint8_t payload[64];
    uint16_t offset = 0u;
    uint32_t timestamp_ms = g_host_link_uptime_ms;
    uint32_t control_cycle = g_host_link_uptime_ms;
    float zero = 0.0f;
    uint8_t index;

    payload[offset++] = HOST_LINK_STREAM_CONTROL_FAST;
    memcpy(&payload[offset], &timestamp_ms, sizeof(timestamp_ms));
    offset = (uint16_t)(offset + sizeof(timestamp_ms));
    memcpy(&payload[offset], &control_cycle, sizeof(control_cycle));
    offset = (uint16_t)(offset + sizeof(control_cycle));
    payload[offset++] = (uint8_t)g_host_link_mode;
    for (index = 0u; index < 11u; ++index)
    {
        memcpy(&payload[offset], &zero, sizeof(float));
        offset = (uint16_t)(offset + sizeof(float));
    }
    (void)HOSTLINK_SendPacket(HOST_LINK_TYPE_TELEMETRY_SAMPLE, HOST_LINK_FLAG_STREAM, 0u, payload, offset);
}

static void HOSTLINK_SendSensors(void)
{
    uint8_t payload[48];
    uint16_t offset = 0u;
    uint32_t timestamp_ms = g_host_link_uptime_ms;
    uint16_t flags = 0u;
    uint16_t age_ms = 0u;
    float zero = 0.0f;
    uint8_t index;

    payload[offset++] = HOST_LINK_STREAM_SENSORS;
    memcpy(&payload[offset], &timestamp_ms, sizeof(timestamp_ms));
    offset = (uint16_t)(offset + sizeof(timestamp_ms));
    for (index = 0u; index < 9u; ++index)
    {
        memcpy(&payload[offset], &zero, sizeof(float));
        offset = (uint16_t)(offset + sizeof(float));
    }
    memcpy(&payload[offset], &flags, sizeof(flags));
    offset = (uint16_t)(offset + sizeof(flags));
    memcpy(&payload[offset], &age_ms, sizeof(age_ms));
    offset = (uint16_t)(offset + sizeof(age_ms));
    (void)HOSTLINK_SendPacket(HOST_LINK_TYPE_TELEMETRY_SAMPLE, HOST_LINK_FLAG_STREAM, 0u, payload, offset);
}

static void HOSTLINK_SendActuatorsPower(void)
{
    uint8_t payload[32];
    uint16_t offset = 0u;
    uint32_t timestamp_ms = g_host_link_uptime_ms;
    float zero = 0.0f;
    uint16_t pwm = 0u;
    uint8_t brake = 0u;
    uint16_t safety_flags = 0u;

    payload[offset++] = HOST_LINK_STREAM_ACTUATORS_POWER;
    memcpy(&payload[offset], &timestamp_ms, sizeof(timestamp_ms));
    offset = (uint16_t)(offset + sizeof(timestamp_ms));
    memcpy(&payload[offset], &zero, sizeof(float)); offset = (uint16_t)(offset + sizeof(float));
    memcpy(&payload[offset], &zero, sizeof(float)); offset = (uint16_t)(offset + sizeof(float));
    memcpy(&payload[offset], &zero, sizeof(float)); offset = (uint16_t)(offset + sizeof(float));
    memcpy(&payload[offset], &pwm, sizeof(pwm)); offset = (uint16_t)(offset + sizeof(pwm));
    memcpy(&payload[offset], &pwm, sizeof(pwm)); offset = (uint16_t)(offset + sizeof(pwm));
    payload[offset++] = brake;
    payload[offset++] = brake;
    memcpy(&payload[offset], &safety_flags, sizeof(safety_flags));
    offset = (uint16_t)(offset + sizeof(safety_flags));
    (void)HOSTLINK_SendPacket(HOST_LINK_TYPE_TELEMETRY_SAMPLE, HOST_LINK_FLAG_STREAM, 0u, payload, offset);
}

static void HOSTLINK_SendRuntimeHealth(void)
{
    uint8_t payload[32];
    uint16_t offset = 0u;
    uint32_t timestamp_ms = g_host_link_uptime_ms;
    uint32_t uptime_ms = g_host_link_uptime_ms;
    uint16_t zero16 = 0u;
    uint16_t uart_rx_overruns = g_host_link_health.uart_rx_overruns;
    uint16_t uart_tx_drops = g_host_link_health.uart_tx_drops;
    uint16_t active_fault = g_host_link_health.active_fault_code;

    payload[offset++] = HOST_LINK_STREAM_RUNTIME_HEALTH;
    memcpy(&payload[offset], &timestamp_ms, sizeof(timestamp_ms));
    offset = (uint16_t)(offset + sizeof(timestamp_ms));
    memcpy(&payload[offset], &uptime_ms, sizeof(uptime_ms));
    offset = (uint16_t)(offset + sizeof(uptime_ms));
    memcpy(&payload[offset], &zero16, sizeof(zero16)); offset = (uint16_t)(offset + sizeof(zero16));
    memcpy(&payload[offset], &zero16, sizeof(zero16)); offset = (uint16_t)(offset + sizeof(zero16));
    memcpy(&payload[offset], &zero16, sizeof(zero16)); offset = (uint16_t)(offset + sizeof(zero16));
    memcpy(&payload[offset], &zero16, sizeof(zero16)); offset = (uint16_t)(offset + sizeof(zero16));
    memcpy(&payload[offset], &uart_rx_overruns, sizeof(uart_rx_overruns)); offset = (uint16_t)(offset + sizeof(uart_rx_overruns));
    memcpy(&payload[offset], &uart_tx_drops, sizeof(uart_tx_drops)); offset = (uint16_t)(offset + sizeof(uart_tx_drops));
    memcpy(&payload[offset], &zero16, sizeof(zero16)); offset = (uint16_t)(offset + sizeof(zero16));
    memcpy(&payload[offset], &active_fault, sizeof(active_fault)); offset = (uint16_t)(offset + sizeof(active_fault));
    (void)HOSTLINK_SendPacket(HOST_LINK_TYPE_TELEMETRY_SAMPLE, HOST_LINK_FLAG_STREAM, 0u, payload, offset);
}

static void HOSTLINK_SendEncoders(void)
{
    uint8_t payload[32];
    uint16_t offset = 0u;
    uint32_t timestamp_ms = g_host_link_uptime_ms;
    int32_t count = 0;
    int16_t delta = 0;
    float rpm = 0.0f;

    payload[offset++] = HOST_LINK_STREAM_ENCODERS;
    memcpy(&payload[offset], &timestamp_ms, sizeof(timestamp_ms));
    offset = (uint16_t)(offset + sizeof(timestamp_ms));
    memcpy(&payload[offset], &count, sizeof(count)); offset = (uint16_t)(offset + sizeof(count));
    memcpy(&payload[offset], &count, sizeof(count)); offset = (uint16_t)(offset + sizeof(count));
    memcpy(&payload[offset], &delta, sizeof(delta)); offset = (uint16_t)(offset + sizeof(delta));
    memcpy(&payload[offset], &delta, sizeof(delta)); offset = (uint16_t)(offset + sizeof(delta));
    memcpy(&payload[offset], &rpm, sizeof(rpm)); offset = (uint16_t)(offset + sizeof(rpm));
    memcpy(&payload[offset], &rpm, sizeof(rpm)); offset = (uint16_t)(offset + sizeof(rpm));
    (void)HOSTLINK_SendPacket(HOST_LINK_TYPE_TELEMETRY_SAMPLE, HOST_LINK_FLAG_STREAM, 0u, payload, offset);
}

static void HOSTLINK_SendFaultFocus(void)
{
    uint8_t payload[12];
    uint16_t offset = 0u;
    uint32_t timestamp_ms = g_host_link_uptime_ms;

    payload[offset++] = HOST_LINK_STREAM_FAULT_FOCUS;
    memcpy(&payload[offset], &timestamp_ms, sizeof(timestamp_ms));
    offset = (uint16_t)(offset + sizeof(timestamp_ms));
    payload[offset++] = (uint8_t)g_host_link_mode;
    memcpy(&payload[offset], &g_host_link_health.active_fault_code, sizeof(uint16_t));
    offset = (uint16_t)(offset + sizeof(uint16_t));
    memset(&payload[offset], 0, 4u);
    offset = (uint16_t)(offset + 4u);
    (void)HOSTLINK_SendPacket(HOST_LINK_TYPE_TELEMETRY_SAMPLE, HOST_LINK_FLAG_STREAM, 0u, payload, offset);
}

static void HOSTLINK_SendTelemetrySample(const HostLinkStreamConfig_t *stream)
{
    if (stream == NULL)
    {
        return;
    }

    switch (stream->stream_id)
    {
        case HOST_LINK_STREAM_CONTROL_FAST:
            HOSTLINK_SendControlFast();
            break;
        case HOST_LINK_STREAM_SENSORS:
            HOSTLINK_SendSensors();
            break;
        case HOST_LINK_STREAM_ACTUATORS_POWER:
            HOSTLINK_SendActuatorsPower();
            break;
        case HOST_LINK_STREAM_RUNTIME_HEALTH:
            HOSTLINK_SendRuntimeHealth();
            break;
        case HOST_LINK_STREAM_ENCODERS:
            HOSTLINK_SendEncoders();
            break;
        case HOST_LINK_STREAM_FAULT_FOCUS:
            HOSTLINK_SendFaultFocus();
            break;
        default:
            break;
    }
}

static void HOSTLINK_HandleRequest(const HostLinkPacket_t *request)
{
    if (request->version != HOST_LINK_PROTOCOL_VERSION)
    {
        HOSTLINK_SendNack(request->type, request->seq, HOST_LINK_ERR_BAD_VERSION);
        return;
    }

    switch (request->type)
    {
        case HOST_LINK_TYPE_PING:
            HOSTLINK_HandlePing(request);
            break;
        case HOST_LINK_TYPE_GET_DEVICE_INFO:
            HOSTLINK_HandleGetDeviceInfo(request);
            break;
        case HOST_LINK_TYPE_GET_PARAMETER_TABLE:
            HOSTLINK_HandleGetParameterTable(request);
            break;
        case HOST_LINK_TYPE_READ_PARAMETER:
            HOSTLINK_HandleReadParameter(request);
            break;
        case HOST_LINK_TYPE_WRITE_PARAMETER:
            HOSTLINK_HandleWriteParameter(request);
            break;
        case HOST_LINK_TYPE_SAVE_PARAMETERS:
            HOSTLINK_HandleSaveParameters(request);
            break;
        case HOST_LINK_TYPE_LOAD_PARAMETERS:
            HOSTLINK_HandleLoadParameters(request);
            break;
        case HOST_LINK_TYPE_SET_STREAM_CONFIG:
            HOSTLINK_HandleSetStreamConfig(request);
            break;
        case HOST_LINK_TYPE_GET_STREAM_CONFIG:
            HOSTLINK_HandleGetStreamConfig(request);
            break;
        default:
            HOSTLINK_SendNack(request->type, request->seq, HOST_LINK_ERR_UNKNOWN_TYPE);
            break;
    }
}

void HOSTLINK_Init(void)
{
    HostLinkParamStore_t persisted;
    uint32_t index;

    memset(&g_host_link_health, 0, sizeof(g_host_link_health));
    MX_USART1_UART_Init();

    HOSTLINK_Params_ResetDefaults(HOSTLINK_Params_CurrentMutable());
    if (HOSTLINK_Storage_Load(&persisted) == BSP_ERROR_NONE)
    {
        HOSTLINK_Params_ReplaceAll(&persisted);
    }

    for (index = 0u; index < (sizeof(g_host_link_streams) / sizeof(g_host_link_streams[0])); ++index)
    {
        g_host_link_streams[index].next_due_ms = g_host_link_streams[index].period_ms;
    }

    HOSTLINK_SetMode(HOST_LINK_MODE_IDLE);
    HW_UART_Receive_IT((hw_uart_id_t)CFG_DEBUG_TRACE_UART, (uint8_t *)&g_host_link_rx_byte, 1u, HOSTLINK_RxCallback);
}

void HOSTLINK_Process(void)
{
    static uint32_t last_tick_ms = 0u;
    uint32_t current_tick_ms = HAL_GetTick();
    uint32_t index;

    if (current_tick_ms != last_tick_ms)
    {
        g_host_link_uptime_ms = current_tick_ms;
        last_tick_ms = current_tick_ms;
    }

    if ((g_host_link_packet_ready != 0u) && (g_host_link_tx_busy == 0u))
    {
        HostLinkPacket_t packet = g_host_link_pending_packet;
        g_host_link_packet_ready = 0u;
        HOSTLINK_HandleRequest(&packet);
        return;
    }

    if ((g_host_link_pending_boot_event != 0u) && (g_host_link_tx_busy == 0u))
    {
        g_host_link_pending_boot_event = 0u;
        HOSTLINK_SendEvent(HOST_LINK_EVENT_BOOT_COMPLETE);
        return;
    }

    if ((g_host_link_pending_mode_event != 0u) && (g_host_link_tx_busy == 0u))
    {
        g_host_link_pending_mode_event = 0u;
        HOSTLINK_SendEvent(HOST_LINK_EVENT_MODE_CHANGED);
        return;
    }

    if (g_host_link_tx_busy != 0u)
    {
        return;
    }

    for (index = 0u; index < (sizeof(g_host_link_streams) / sizeof(g_host_link_streams[0])); ++index)
    {
        HostLinkStreamConfig_t *stream = &g_host_link_streams[index];

        if ((stream->enabled != 0u) &&
            (stream->period_ms != 0u) &&
            (g_host_link_uptime_ms >= stream->next_due_ms))
        {
            stream->next_due_ms = g_host_link_uptime_ms + stream->period_ms;
            HOSTLINK_SendTelemetrySample(stream);
            break;
        }
    }
}

void HOSTLINK_GetRuntimeHealth(HostLinkRuntimeHealth_t *health)
{
    if (health == NULL)
    {
        return;
    }

    *health = g_host_link_health;
    health->uptime_ms = g_host_link_uptime_ms;
    health->storage_state = (uint8_t)HOSTLINK_Storage_GetState();
    health->mode = g_host_link_mode;
}
