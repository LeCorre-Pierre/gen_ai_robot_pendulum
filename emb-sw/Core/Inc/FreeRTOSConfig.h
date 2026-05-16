#ifndef FREERTOS_CONFIG_H
#define FREERTOS_CONFIG_H

#include "stm32wbxx_hal.h"

#define configUSE_PREEMPTION                    1
#define configUSE_IDLE_HOOK                     0
#define configUSE_TICK_HOOK                     0
#define configCPU_CLOCK_HZ                      64000000UL
#define configTICK_RATE_HZ                      1000
#define configMAX_PRIORITIES                    7
#define configMINIMAL_STACK_SIZE                128
#define configTOTAL_HEAP_SIZE                   (8 * 1024)
#define configMAX_TASK_NAME_LEN                 16
#define configUSE_TRACE_FACILITY                0
#define configUSE_16_BIT_TICKS                  0
#define configIDLE_SHOULD_YIELD                 1
#define configUSE_MUTEXES                       1
#define configQUEUE_REGISTRY_SIZE               8
#define configUSE_RECURSIVE_MUTEXES             1
#define configUSE_COUNTING_SEMAPHORES           1
#define configUSE_PORT_OPTIMISED_TASK_SELECTION 0

#define INCLUDE_vTaskDelay                      1
#define INCLUDE_vTaskDelete                     1
#define INCLUDE_xTaskGetCurrentTaskHandle       1

#define configASSERT(x) if ((x) == 0) { taskDISABLE_INTERRUPTS(); for(;;); }

#define configLIBRARY_LOWEST_INTERRUPT_PRIORITY     15
#define configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY 5
#define configKERNEL_INTERRUPT_PRIORITY     (configLIBRARY_LOWEST_INTERRUPT_PRIORITY << (8 - 4))
#define configMAX_SYSCALL_INTERRUPT_PRIORITY (configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY << (8 - 4))

#endif /* FREERTOS_CONFIG_H */
