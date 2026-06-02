/*
 * task_display.c — single balance status screen on the OLED
 *
 *  B1 short press : toggle VCP stream on/off
 *  B2             : emergency-stop reset (handled in task_control.c)
 */

#include "FreeRTOS.h"
#include "task.h"
#include "task_display.h"
#include "main.h"
#include "stm32wb5mm_dk.h"
#include <stdio.h>
#include "motor_control.h"
#include "task_comms.h"
#include "task_control.h"

#define DISPLAY_TASK_STACK_SIZE  384U
#define DISPLAY_TASK_PRIORITY    (tskIDLE_PRIORITY + 1U)
#define DISPLAY_UPDATE_MS        100U

static void DisplayTask(void *pvParameters);
static void Screen_DrawBalance(void);

void StartDisplayTask(void)
{
    xTaskCreate(DisplayTask, "Display", DISPLAY_TASK_STACK_SIZE, NULL,
                DISPLAY_TASK_PRIORITY, NULL);
}

static void Screen_DrawBalance(void)
{
    char buf[22];
    ControlState_t cs;
    Task_control_GetState(&cs);

    BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);
    UTIL_LCD_SetFont(&Font12);

    /* Line 1 y=2 : stream status + pitch angle */
    uint8_t     streaming = VCP_IsStreamActive();
    const char *sym       = streaming ? ">>" : "==";
    snprintf(buf, sizeof(buf), "VCP %s %+6.1f deg", sym, (double)cs.pitch_deg);
    UTIL_LCD_DisplayStringAt(2, 2, (uint8_t *)buf, LEFT_MODE);

    /* Line 2 y=14 : drive output */
    snprintf(buf, sizeof(buf), "Drive:   %+5.1f %%",
             (double)(cs.drive_output * 100.0f));
    UTIL_LCD_DisplayStringAt(2, 14, (uint8_t *)buf, LEFT_MODE);

    /* Line 3 y=27 : left / right motor velocities */
    int pv_l = (int)MTR_GetCachedVelocityRPM(MTR_LEFT);
    int pv_r = (int)MTR_GetCachedVelocityRPM(MTR_RIGHT);
    snprintf(buf, sizeof(buf), "L:%+4d R:%+4d rpm", pv_l, pv_r);
    UTIL_LCD_DisplayStringAt(2, 27, (uint8_t *)buf, LEFT_MODE);

    /* Line 4 y=40 : last-command flash + mode label */
    uint32_t    age_ms = HAL_GetTick() - VCP_GetLastCmdTick();
    const char *ok     = (VCP_GetLastCmdTick() > 0U && age_ms < 500U)
                         ? "[CMD]  " : "       ";
    snprintf(buf, sizeof(buf), "%sBALANCE", ok);
    UTIL_LCD_DisplayStringAt(2, 40, (uint8_t *)buf, LEFT_MODE);

    /* Line 5 y=52 : button hints */
    snprintf(buf, sizeof(buf), "B1:%s  B2:emg-rst",
             streaming ? "stop" : "strm");
    UTIL_LCD_DisplayStringAt(2, 52, (uint8_t *)buf, LEFT_MODE);

    BSP_LCD_Refresh(0);
}

static void DisplayTask(void *pvParameters)
{
    (void)pvParameters;

    TickType_t last_wake = xTaskGetTickCount();
    uint8_t    btn1_prev = 1U;

    for (;;) {
        /* B1 short press (rising edge on active-low): toggle stream */
        uint8_t b1_now = (uint8_t)BSP_PB_GetState(BUTTON_USER1);
        if (b1_now != GPIO_PIN_RESET && btn1_prev == 0U) {
            VCP_SetStreamActive(VCP_IsStreamActive() ? 0U : 1U);
        }
        btn1_prev = (b1_now == GPIO_PIN_RESET) ? 0U : 1U;

        Screen_DrawBalance();
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(DISPLAY_UPDATE_MS));
    }
}
