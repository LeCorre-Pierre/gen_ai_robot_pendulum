/*
 * task_display.c
 */

#include "FreeRTOS.h"
#include "task.h"
#include "task_display.h"
#include "main.h"
#include "stm32wb5mm_dk.h"
#include "encoder.h"
#include <stdio.h>

#define DISPLAY_TASK_STACK_SIZE  256U
#define DISPLAY_TASK_PRIORITY    (tskIDLE_PRIORITY + 1U)
#define DISPLAY_UPDATE_MS        100U

/* Measure wheel circumference and update this value. */
#define WHEEL_CIRCUMFERENCE_CM   22.0f
#define TICKS_PER_REV            1856
#define CM_PER_TICK              (WHEEL_CIRCUMFERENCE_CM / (float)TICKS_PER_REV)

typedef enum {
    SCREEN_ENCODER = 0,
    SCREEN_COUNT
} Screen_t;

/* Defined in the sensor/control task once encoder management is implemented. */

static Screen_t s_screen    = SCREEN_ENCODER;
static uint8_t  s_btn2_prev = 1U;

static void DisplayTask(void *pvParameters);
static void Screen_DrawEncoder(void);


void StartDisplayTask(void)
{
    
    xTaskCreate(DisplayTask, "Display", DISPLAY_TASK_STACK_SIZE, NULL,
                DISPLAY_TASK_PRIORITY, NULL);
}


static void Screen_DrawEncoder(void)
{
    char buf[22];
    float right_cm = Encoder_GetDistanceCm(&g_enc_right);
    float left_cm  = Encoder_GetDistanceCm(&g_enc_left);

    BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);
    UTIL_LCD_SetFont(&Font12);

    UTIL_LCD_DisplayStringAt(0, 2, (uint8_t *)"Encoders", CENTER_MODE);

    snprintf(buf, sizeof(buf), "Right: %6.2f cm", right_cm);
    UTIL_LCD_DisplayStringAt(2, 18, (uint8_t *)buf, LEFT_MODE);

    snprintf(buf, sizeof(buf), "Left:  %6.2f cm", left_cm);
    UTIL_LCD_DisplayStringAt(2, 32, (uint8_t *)buf, LEFT_MODE);

    BSP_LCD_Refresh(0);
}

static void DisplayTask(void *pvParameters)
{
    (void)pvParameters;

    TickType_t last_wake   = xTaskGetTickCount();
    Screen_t   last_screen = SCREEN_COUNT;  /* force first draw */
    int32_t    last_right  = 0;
    int32_t    last_left   = 0;

    for (;;) {
        /* B2: advance to the next screen. */
        if(BSP_PB_GetState(BUTTON_USER2) == GPIO_PIN_RESET) {
            if (s_btn2_prev == 1U) {
                s_screen = (s_screen + 1U) % SCREEN_COUNT;
            }
            s_btn2_prev = 0U;
        } else {
            s_btn2_prev = 1U;
        }

        switch (s_screen) {
            case SCREEN_ENCODER: {
                /* If B1 is pressed, reset both encoder counts to zero. */
                if (BSP_PB_GetState(BUTTON_USER1) == GPIO_PIN_RESET) {
                    Encoder_Reset(&g_enc_right);
                    Encoder_Reset(&g_enc_left);
                }

                int32_t r = Encoder_GetRaw(&g_enc_right);
                int32_t l = Encoder_GetRaw(&g_enc_left);
                if (s_screen != last_screen || r != last_right || l != last_left) {
                    Screen_DrawEncoder();
                    last_right = r;
                    last_left  = l;
                }
                break;
            }

            default:
                break;
        }

        last_screen = s_screen;
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(DISPLAY_UPDATE_MS));
    }
}
