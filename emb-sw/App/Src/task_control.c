#include "task_control.h"
#include "FreeRTOS.h"
#include "task.h"
#include "motor_control.h"

#define CONTROL_TASK_STACK_SIZE  256U
#define CONTROL_TASK_PRIORITY    (tskIDLE_PRIORITY + 3U)  /* > display (1) */
#define CONTROL_TASK_PERIOD_MS   5U                        /* 200 Hz */

static void ControlTask(void *pvParameters)
{
    (void)pvParameters;
    TickType_t last_wake = xTaskGetTickCount();

    for (;;) {
        MTR_VelocityUpdate();
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(CONTROL_TASK_PERIOD_MS));
    }
}

void Task_control_Init(void)
{
    xTaskCreate(ControlTask, "Control", CONTROL_TASK_STACK_SIZE, NULL,
                CONTROL_TASK_PRIORITY, NULL);
}
