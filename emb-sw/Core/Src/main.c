#include "main.h"
#include "cmsis_os.h"
#include "task_comms.h"
#include "task_safety.h"
#include "task_control.h"

TIM_HandleTypeDef   htim1;
TIM_HandleTypeDef   htim2;
TIM_HandleTypeDef   htim16;
LPTIM_HandleTypeDef hlptim1;
I2C_HandleTypeDef   hi2c3;
UART_HandleTypeDef  huart1;
ADC_HandleTypeDef   hadc1;
void Screen_Init(void);
void Screen_DisplayStartupLogo(void);
static void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_TIM1_Init(void);
static void MX_TIM2_Init(void);
static void MX_TIM16_Init(void);
static void MX_LPTIM1_Init(void);
static void MX_I2C3_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_ADC1_Init(void);

int main(void)
{
    // Initialize the HAL library and the system clock
    HAL_Init();
    SystemClock_Config();

    // Initialize all configured peripherals
    MX_GPIO_Init();
    MX_TIM1_Init();
    MX_TIM2_Init();
    MX_TIM16_Init();
    MX_LPTIM1_Init();
    MX_I2C3_Init();
    MX_USART1_UART_Init();
    MX_ADC1_Init();

    // Initialize the screen and display the startup logo
    Screen_Init();
    Screen_DisplayStartupLogo();

    // Initialize the RTOS kernel
    osKernelInitialize();

    // Initialize RTOS tasks
    Task_control_Init();
    Task_comms_Init();
    Task_safety_Init();

    osKernelStart();

    for (;;) {}
}

static void SystemClock_Config(void)
{
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

    HAL_PWR_EnableBkUpAccess();
    __HAL_RCC_LSEDRIVE_CONFIG(RCC_LSEDRIVE_MEDIUMHIGH);

    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

    RCC_OscInitStruct.OscillatorType      = RCC_OSCILLATORTYPE_HSI
                                          | RCC_OSCILLATORTYPE_HSE
                                          | RCC_OSCILLATORTYPE_LSE;
    RCC_OscInitStruct.HSEState            = RCC_HSE_ON;
    RCC_OscInitStruct.LSEState            = RCC_LSE_ON;
    RCC_OscInitStruct.HSIState            = RCC_HSI_ON;
    RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    RCC_OscInitStruct.PLL.PLLState        = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource       = RCC_PLLSOURCE_HSE;
    RCC_OscInitStruct.PLL.PLLM            = RCC_PLLM_DIV8;
    RCC_OscInitStruct.PLL.PLLN            = 32;
    RCC_OscInitStruct.PLL.PLLP            = RCC_PLLP_DIV2;
    RCC_OscInitStruct.PLL.PLLR            = RCC_PLLR_DIV2;
    RCC_OscInitStruct.PLL.PLLQ            = RCC_PLLQ_DIV2;

    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
    {
        Error_Handler();
    }

    RCC_ClkInitStruct.ClockType      = RCC_CLOCKTYPE_HCLK4 | RCC_CLOCKTYPE_HCLK2
                                     | RCC_CLOCKTYPE_HCLK  | RCC_CLOCKTYPE_SYSCLK
                                     | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource   = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider  = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
    RCC_ClkInitStruct.AHBCLK2Divider = RCC_SYSCLK_DIV2;
    RCC_ClkInitStruct.AHBCLK4Divider = RCC_SYSCLK_DIV1;

    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_3) != HAL_OK)
    {
        Error_Handler();
    }
}

void Screen_Init(void)
{
    BSP_LCD_Init(0, LCD_ORIENTATION_LANDSCAPE);
    /* Set LCD Foreground Layer  */
    UTIL_LCD_SetFuncDriver(&LCD_Driver); /* SetFunc before setting device */
    UTIL_LCD_SetDevice(0);            /* SetDevice after funcDriver is set */
    BSP_LCD_Clear(0,SSD1315_COLOR_BLACK);
    BSP_LCD_DisplayOn(0);
    BSP_LCD_Refresh(0);
    UTIL_LCD_SetFont(&Font12);
    /* Set the LCD Text Color */
    UTIL_LCD_SetTextColor(SSD1315_COLOR_WHITE);
    UTIL_LCD_SetBackColor(SSD1315_COLOR_BLACK);
    BSP_LCD_Clear(0,SSD1315_COLOR_BLACK);
    BSP_LCD_Refresh(0);
    
}

void Screen_DisplayStartupLogo(void)
{
    // display robot as text for now, replace with actual logo later
    BSP_LCD_Clear(0, SSD1315_COLOR_BLACK);
    UTIL_LCD_SetFont(&Font12);
    UTIL_LCD_DisplayStringAt(0, 2, (uint8_t *)"-- Robot --", CENTER_MODE);
    BSP_LCD_Refresh(0);    
}

static void MX_GPIO_Init(void)       { /* TODO */ }
static void MX_TIM1_Init(void)       { /* TODO: QEI encoder gauche */ }
static void MX_TIM2_Init(void)       { /* TODO: QEI encoder droit */ }
static void MX_TIM16_Init(void)      { /* TODO: PWM moteur droit 20 kHz */ }
static void MX_LPTIM1_Init(void)     { /* TODO: PWM moteur gauche 20 kHz */ }
static void MX_I2C3_Init(void)       { /* TODO: IMU ISM330DHCX */ }
static void MX_USART1_UART_Init(void){ /* TODO: VCP 115200 */ }
static void MX_ADC1_Init(void)       { /* TODO: current sense IN4/IN10 */ }

void Error_Handler(void)
{
    __disable_irq();
    for (;;) {}
}
