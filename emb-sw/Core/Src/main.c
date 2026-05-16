#include "main.h"
#include "cmsis_os.h"
#include "task_control.h"
#include "task_comms.h"
#include "task_safety.h"

TIM_HandleTypeDef   htim1;
TIM_HandleTypeDef   htim2;
TIM_HandleTypeDef   htim16;
LPTIM_HandleTypeDef hlptim1;
I2C_HandleTypeDef   hi2c3;
UART_HandleTypeDef  huart1;
ADC_HandleTypeDef   hadc1;
QSPI_HandleTypeDef  hqspi;

static void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_TIM1_Init(void);
static void MX_TIM2_Init(void);
static void MX_TIM16_Init(void);
static void MX_LPTIM1_Init(void);
static void MX_I2C3_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_ADC1_Init(void);
static void MX_QUADSPI_Init(void);

int main(void)
{
    HAL_Init();
    SystemClock_Config();

    MX_GPIO_Init();
    MX_TIM1_Init();
    MX_TIM2_Init();
    MX_TIM16_Init();
    MX_LPTIM1_Init();
    MX_I2C3_Init();
    MX_USART1_UART_Init();
    MX_ADC1_Init();
    MX_QUADSPI_Init();

    osKernelInitialize();

    TaskControl_Init();
    TaskComms_Init();
    TaskSafety_Init();

    osKernelStart();

    for (;;) {}
}

static void SystemClock_Config(void)
{
    /* TODO: configure PLL to 64 MHz from HSE/HSI */
}

static void MX_GPIO_Init(void)       { /* TODO */ }
static void MX_TIM1_Init(void)       { /* TODO: QEI encoder gauche */ }
static void MX_TIM2_Init(void)       { /* TODO: QEI encoder droit */ }
static void MX_TIM16_Init(void)      { /* TODO: PWM moteur droit 20 kHz */ }
static void MX_LPTIM1_Init(void)     { /* TODO: PWM moteur gauche 20 kHz */ }
static void MX_I2C3_Init(void)       { /* TODO: IMU ISM330DHCX */ }
static void MX_USART1_UART_Init(void){ /* TODO: VCP 115200 */ }
static void MX_ADC1_Init(void)       { /* TODO: current sense IN4/IN10 */ }
static void MX_QUADSPI_Init(void)    { /* TODO: flash S25FL128S */ }

void Error_Handler(void)
{
    __disable_irq();
    for (;;) {}
}
