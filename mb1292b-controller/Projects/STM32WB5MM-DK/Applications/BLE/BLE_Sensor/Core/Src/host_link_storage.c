#include "host_link_storage.h"

#include <string.h>

#include "stm32wb5mm_dk_qspi.h"

#define HOST_LINK_STORAGE_MAGIC            0x484C5043u
#define HOST_LINK_STORAGE_VERSION          0x0001u
#define HOST_LINK_STORAGE_ADDRESS          0x00FF0000u
#define HOST_LINK_STORAGE_ERASE_SIZE       BSP_QSPI_ERASE_64K

typedef struct
{
    uint32_t magic;
    uint16_t version;
    uint16_t length;
    uint32_t crc32;
    HostLinkParamStore_t params;
} HostLinkStorageImage_t;

static HostLinkStorageState_t g_host_link_storage_state = HOST_LINK_STORAGE_STATE_UNINITIALIZED;
static uint8_t g_host_link_storage_ready = 0u;

static uint32_t HOSTLINK_Storage_Crc32(const uint8_t *data, uint32_t length)
{
    uint32_t crc = 0xFFFFFFFFu;
    uint32_t index;
    uint8_t bit;

    for (index = 0u; index < length; ++index)
    {
        crc ^= data[index];
        for (bit = 0u; bit < 8u; ++bit)
        {
            if ((crc & 1u) != 0u)
            {
                crc = (crc >> 1) ^ 0xEDB88320u;
            }
            else
            {
                crc >>= 1;
            }
        }
    }

    return ~crc;
}

int32_t HOSTLINK_Storage_Init(void)
{
    BSP_QSPI_Init_t init;
    int32_t status;

    if (g_host_link_storage_ready != 0u)
    {
        return 0;
    }

    init.InterfaceMode = BSP_QSPI_SPI_MODE;
    init.TransferRate = BSP_QSPI_STR_TRANSFER;
    init.DualFlashMode = BSP_QSPI_DUALFLASH_DISABLE;

    status = BSP_QSPI_Init(0u, &init);
    if (status != BSP_ERROR_NONE)
    {
        g_host_link_storage_state = HOST_LINK_STORAGE_STATE_ERROR;
        return status;
    }

    g_host_link_storage_ready = 1u;
    g_host_link_storage_state = HOST_LINK_STORAGE_STATE_READY;
    return BSP_ERROR_NONE;
}

int32_t HOSTLINK_Storage_Load(HostLinkParamStore_t *store)
{
    HostLinkStorageImage_t image;
    uint32_t crc;
    int32_t status;

    if (store == NULL)
    {
        return BSP_ERROR_WRONG_PARAM;
    }

    status = HOSTLINK_Storage_Init();
    if (status != BSP_ERROR_NONE)
    {
        HOSTLINK_Params_ResetDefaults(store);
        g_host_link_storage_state = HOST_LINK_STORAGE_STATE_ERROR;
        return status;
    }

    memset(&image, 0, sizeof(image));
    status = BSP_QSPI_Read(0u, (uint8_t *)&image, HOST_LINK_STORAGE_ADDRESS, sizeof(image));
    if (status != BSP_ERROR_NONE)
    {
        HOSTLINK_Params_ResetDefaults(store);
        g_host_link_storage_state = HOST_LINK_STORAGE_STATE_FALLBACK_DEFAULTS;
        return status;
    }

    crc = HOSTLINK_Storage_Crc32((const uint8_t *)&image.params, sizeof(image.params));
    if ((image.magic != HOST_LINK_STORAGE_MAGIC) ||
        (image.version != HOST_LINK_STORAGE_VERSION) ||
        (image.length != sizeof(image.params)) ||
        (image.crc32 != crc))
    {
        HOSTLINK_Params_ResetDefaults(store);
        g_host_link_storage_state = HOST_LINK_STORAGE_STATE_FALLBACK_DEFAULTS;
        return BSP_ERROR_COMPONENT_FAILURE;
    }

    *store = image.params;
    g_host_link_storage_state = HOST_LINK_STORAGE_STATE_READY;
    return BSP_ERROR_NONE;
}

int32_t HOSTLINK_Storage_Save(const HostLinkParamStore_t *store)
{
    HostLinkStorageImage_t image;
    int32_t status;

    if (store == NULL)
    {
        return BSP_ERROR_WRONG_PARAM;
    }

    status = HOSTLINK_Storage_Init();
    if (status != BSP_ERROR_NONE)
    {
        g_host_link_storage_state = HOST_LINK_STORAGE_STATE_ERROR;
        return status;
    }

    image.magic = HOST_LINK_STORAGE_MAGIC;
    image.version = HOST_LINK_STORAGE_VERSION;
    image.length = sizeof(image.params);
    image.params = *store;
    image.crc32 = HOSTLINK_Storage_Crc32((const uint8_t *)&image.params, sizeof(image.params));

    status = BSP_QSPI_EraseBlock(0u, HOST_LINK_STORAGE_ADDRESS, HOST_LINK_STORAGE_ERASE_SIZE);
    if (status != BSP_ERROR_NONE)
    {
        g_host_link_storage_state = HOST_LINK_STORAGE_STATE_ERROR;
        return status;
    }

    status = BSP_QSPI_Write(0u, (uint8_t *)&image, HOST_LINK_STORAGE_ADDRESS, sizeof(image));
    if (status != BSP_ERROR_NONE)
    {
        g_host_link_storage_state = HOST_LINK_STORAGE_STATE_ERROR;
        return status;
    }

    g_host_link_storage_state = HOST_LINK_STORAGE_STATE_READY;
    return BSP_ERROR_NONE;
}

HostLinkStorageState_t HOSTLINK_Storage_GetState(void)
{
    return g_host_link_storage_state;
}
