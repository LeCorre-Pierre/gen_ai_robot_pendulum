/**
  ******************************************************************************
  * @file    task_display.c
  * @brief   OLED display task — shows BLE connection state and the number of
  *          telemetry frames sent. Refreshes at ~5 Hz.
  ******************************************************************************
  */
#include "main.h"
#include "cmsis_os.h"
#include "stm32wb5mm_dk.h"
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

/* ------------------------------------------------------------------------- */
/* Animated boot splash — a little robot wakes up and finds its balance.      */
/* Shown once at startup, then the screen falls back to the debug view.       */
/* ------------------------------------------------------------------------- */

#define SPLASH_NAME    "ROBOTIX"
#define SPLASH_FRAMES  18

/* Decaying side-to-side wobble: the robot "searches" then settles upright. */
static const int8_t Splash_Tilt[SPLASH_FRAMES] =
{
  0, 6, 9, 6, 0, -5, -8, -5, 0, 4, 6, 4, 0, -3, -4, -2, 0, 0
};

/* eye state: 0 = open, 1 = closed (asleep/blink), 2 = wink (left eye closed) */
static void Splash_DrawRobot(int tilt, int eye_state)
{
  const int cx    = 64;   /* horizontal centre               */
  const int axleY = 56;   /* wheel axle height               */
  const int hcx   = cx + tilt;       /* head centre (leans)  */
  const int headTop = 18, headBot = 38;
  const int eyeY  = 26;
  const int mY    = 32;

  /* Wheels with hub holes */
  UTIL_LCD_FillCircle(cx - 14, axleY, 6, SSD1315_COLOR_WHITE);
  UTIL_LCD_FillCircle(cx + 14, axleY, 6, SSD1315_COLOR_WHITE);
  UTIL_LCD_FillCircle(cx - 14, axleY, 2, SSD1315_COLOR_BLACK);
  UTIL_LCD_FillCircle(cx + 14, axleY, 2, SSD1315_COLOR_BLACK);

  /* Legs from axle up to the leaning head */
  UTIL_LCD_DrawLine(cx - 6, axleY - 2, hcx - 8, headBot, SSD1315_COLOR_WHITE);
  UTIL_LCD_DrawLine(cx + 6, axleY - 2, hcx + 8, headBot, SSD1315_COLOR_WHITE);

  /* Head (white body, features carved in black) */
  UTIL_LCD_FillRect(hcx - 15, headTop, 30, headBot - headTop, SSD1315_COLOR_WHITE);

  /* Antenna with a blinking tip */
  UTIL_LCD_DrawLine(hcx, headTop, hcx, headTop - 5, SSD1315_COLOR_WHITE);
  UTIL_LCD_FillCircle(hcx, headTop - 6, 2, SSD1315_COLOR_WHITE);

  /* Eyes */
  if (eye_state == 1)
  {
    UTIL_LCD_DrawLine(hcx - 9, eyeY, hcx - 3, eyeY, SSD1315_COLOR_BLACK);
    UTIL_LCD_DrawLine(hcx + 3, eyeY, hcx + 9, eyeY, SSD1315_COLOR_BLACK);
  }
  else
  {
    /* Right eye always open */
    UTIL_LCD_FillCircle(hcx + 6, eyeY, 2, SSD1315_COLOR_BLACK);
    if (eye_state == 2)   /* wink: left eye closed */
      UTIL_LCD_DrawLine(hcx - 9, eyeY, hcx - 3, eyeY, SSD1315_COLOR_BLACK);
    else
      UTIL_LCD_FillCircle(hcx - 6, eyeY, 2, SSD1315_COLOR_BLACK);
  }

  /* Smiling mouth */
  UTIL_LCD_DrawLine(hcx - 5, mY,     hcx - 2, mY + 2, SSD1315_COLOR_BLACK);
  UTIL_LCD_DrawLine(hcx - 2, mY + 2, hcx + 2, mY + 2, SSD1315_COLOR_BLACK);
  UTIL_LCD_DrawLine(hcx + 2, mY + 2, hcx + 5, mY,     SSD1315_COLOR_BLACK);
}

static void Splash_Run(void)
{
  for (int f = 0; f < SPLASH_FRAMES; f++)
  {
    BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);

    /* Title + growing progress underline */
    UTIL_LCD_SetFont(&Font12);
    UTIL_LCD_DisplayStringAt(0, 0, (uint8_t *)SPLASH_NAME, CENTER_MODE);
    UTIL_LCD_DrawHLine(0, 14, (128 * (f + 1)) / SPLASH_FRAMES, SSD1315_COLOR_WHITE);

    int eye = 0;
    if (f <= 1)                eye = 1;   /* still waking up */
    else if (f == 8 || f == 9) eye = 1;   /* blink          */
    else if (f >= 16)          eye = 2;   /* friendly wink   */

    Splash_DrawRobot(Splash_Tilt[f], eye);

    BSP_LCD_Refresh(0);
    osDelay(110);
  }
  osDelay(400);   /* hold the final upright smile a moment */
}

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
  int prev_pressed = 0;
  UNUSED(argument);

  /* USER1 button (PC12) as polled input — press replays the welcome screen */
  BSP_PB_Init(BUTTON_USER1, BUTTON_MODE_GPIO);

  /* Animated welcome screen, shown once at power-up */
  Splash_Run();

  for (;;)
  {
    /* Replay the splash on a button press (active-low, pull-up) */
    int pressed = (BSP_PB_GetState(BUTTON_USER1) == 0);
    if (pressed && !prev_pressed)
    {
      Splash_Run();
    }
    prev_pressed = pressed;

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
