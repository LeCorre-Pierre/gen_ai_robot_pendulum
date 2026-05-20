#include "tof.h"
#include "stm32wb5mm_dk_bus.h"
#include "vl53l0x_api.h"
#include "vl53l0x_tof.h"

#define TOF_I2C_ADDR  0x53U           /* 8-bit addr (7-bit 0x29, HAL clears R/W bit on write) */
#define TOF_MODEL_ID  ((uint16_t)0xEEAA)

static VL53L0X_Dev_t s_dev = {
    .I2cHandle  = &hbus_i2c3,
    .I2cDevAddr = TOF_I2C_ADDR,
};

void Tof_Init(void)
{
    uint16_t model_id = 0;
    VL53L0X_DeviceInfo_t dev_info;

    BSP_I2C3_Init();

    if (VL53L0X_GetDeviceInfo(&s_dev, &dev_info) != VL53L0X_ERROR_NONE) {
        return;
    }

    if (VL53L0X_RdWord(&s_dev, VL53L0X_REG_IDENTIFICATION_MODEL_ID, &model_id) != VL53L0X_ERROR_NONE) {
        return;
    }

    if (model_id != TOF_MODEL_ID) {
        return;
    }

    if (VL53L0X_DataInit(&s_dev) != VL53L0X_ERROR_NONE) {
        return;
    }

    s_dev.Present = 1;
    SetupSingleShot(&s_dev);
}

int16_t Tof_GetDistanceMm(void)
{
    VL53L0X_RangingMeasurementData_t data;

    if (!s_dev.Present) {
        return -1;
    }

    if (VL53L0X_PerformSingleRangingMeasurement(&s_dev, &data) != VL53L0X_ERROR_NONE) {
        return -1;
    }

    if (data.RangeStatus != 0) {
        return -1;
    }

    return (int16_t)data.RangeMilliMeter;
}
