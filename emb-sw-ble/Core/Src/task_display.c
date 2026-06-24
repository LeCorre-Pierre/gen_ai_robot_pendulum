/**
  ******************************************************************************
  * @file    task_display.c
  * @brief   OLED display task — shows BLE connection state and the number of
  *          telemetry frames sent. Refreshes at ~5 Hz.
  ******************************************************************************
  */
#include "main.h"
#include "cmsis_os.h"
#include "stm32wb5mm_dk_lcd.h"
#include "stm32_lcd.h"
#include "fonts.h"
#include "app_ble.h"
#include "robot_app.h"
#include "task_sensors.h"
#include "task_display.h"
#include <stdio.h>

static osThreadId_t DisplayThreadId;
static const osThreadAttr_t DisplayProcess_attr =
{
  .name       = "Display",
  .priority   = osPriorityLow,
  .stack_size = 2048U,
};

static const char *Conn_Str(APP_BLE_ConnStatus_t status)
{
  switch (status)
  {
    case APP_BLE_CONNECTED_SERVER:
    case APP_BLE_CONNECTED_CLIENT:
      return "Connected";
    case APP_BLE_FAST_ADV:
    case APP_BLE_LP_ADV:
      return "Advertising";
    default:
      return "Idle";
  }
}

static void DisplayProcess(void *argument)
{
  char buf[24];
  UNUSED(argument);

  for (;;)
  {
    APP_BLE_ConnStatus_t status = APP_BLE_Get_Server_Connection_Status();

    BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);
    UTIL_LCD_SetFont(&Font12);

    snprintf(buf, sizeof(buf), "St:%s", Conn_Str(status));
    UTIL_LCD_DisplayStringAt(0, 0, (uint8_t *)buf, LEFT_MODE);

    snprintf(buf, sizeof(buf), "Cnx:%lu Dcx:%lu",
             (unsigned long)APP_BLE_GetConnCount(),
             (unsigned long)APP_BLE_GetDiscCount());
    UTIL_LCD_DisplayStringAt(0, 16, (uint8_t *)buf, LEFT_MODE);

    snprintf(buf, sizeof(buf), "TX:%lu", (unsigned long)Robot_App_GetTxCount());
    UTIL_LCD_DisplayStringAt(0, 32, (uint8_t *)buf, LEFT_MODE);

    /* Pitch in tenths of a degree (avoids %f) */
    int p10  = (int)(Sensors_GetPitchDeg() * 10.0f);
    int neg  = (p10 < 0);
    int ap10 = neg ? -p10 : p10;
    snprintf(buf, sizeof(buf), "Pitch:%s%d.%d", neg ? "-" : "", ap10 / 10, ap10 % 10);
    UTIL_LCD_DisplayStringAt(0, 48, (uint8_t *)buf, LEFT_MODE);

    BSP_LCD_Refresh(0);

    osDelay(200);
  }
}

void Task_Display_Init(void)
{
  DisplayThreadId = osThreadNew(DisplayProcess, NULL, &DisplayProcess_attr);
}
