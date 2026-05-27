#include "main.h"
#include "cmsis_os.h"
#include "task_comms.h"
#include "task_safety.h"
#include "task_control.h"
#include "task_display.h"
#include "tof.h"
#include "env_sensor.h"
#include "imu.h"
#include "stm32wb5mm_dk_motion_sensors.h"
#include "motor_control.h"

Encoder_t g_enc_left;
Encoder_t g_enc_right;
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

    // Initialize the buttons
    BSP_PB_Init(BUTTON_USER1, BUTTON_MODE_GPIO);
    BSP_PB_Init(BUTTON_USER2, BUTTON_MODE_GPIO);

    // Initialize the screen and display the startup logo
    Screen_Init();
    Screen_DisplayStartupLogo();

    // Initialize the encoder structures with their respective TIM handles
    Encoder_Init(&g_enc_left, &htim1);
    Encoder_Init(&g_enc_right, &htim2);

    // Initialize motor control (starts LPTIM1 PWM, TIM16 PWM, encoder snapshots)
    MTR_Init();

    Tof_Init();
    EnvSensor_Init();
    BSP_MOTION_SENSOR_Init(MOTION_SENSOR_ISM330DHCX_0, MOTION_ACCELERO | MOTION_GYRO);
    IMU_Init();

    // Initialize the RTOS kernel
    osKernelInitialize();

    // Initialize RTOS tasks
    Task_control_Init();
    Task_comms_Init();
    Task_safety_Init();
    StartDisplayTask();

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

static void MX_GPIO_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_GPIOD_CLK_ENABLE();
    __HAL_RCC_GPIOE_CLK_ENABLE();

    /* Initial output state: DIR=LOW, BRAKE=LOW (coast) */
    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_12 | GPIO_PIN_13, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(GPIOE, GPIO_PIN_4,                GPIO_PIN_RESET);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_2,                GPIO_PIN_RESET);

    /* PD12=MOTOR_LEFT_DIR, PD13=MOTOR_LEFT_BRAKE */
    GPIO_InitStruct.Pin   = GPIO_PIN_12 | GPIO_PIN_13;
    GPIO_InitStruct.Mode  = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull  = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);

    /* PE4=MOTOR_RIGHT_DIR (PE3 = STMOD+ pin 11, non routé sur Arduino D4) */
    GPIO_InitStruct.Pin = GPIO_PIN_4;
    HAL_GPIO_Init(GPIOE, &GPIO_InitStruct);

    /* PB2=MOTOR_RIGHT_BRAKE */
    GPIO_InitStruct.Pin = GPIO_PIN_2;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
}

static void MX_TIM16_Init(void)
{
    GPIO_InitTypeDef    GPIO_InitStruct = {0};
    TIM_OC_InitTypeDef  sConfigOC       = {0};

    __HAL_RCC_TIM16_CLK_ENABLE();

    /* PE0 = TIM16_CH1 (MOTOR_RIGHT_PWM, Arduino D6) */
    GPIO_InitStruct.Pin       = GPIO_PIN_0;
    GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull      = GPIO_NOPULL;
    GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_LOW;
    GPIO_InitStruct.Alternate = GPIO_AF14_TIM16;
    HAL_GPIO_Init(GPIOE, &GPIO_InitStruct);

    /* TIM16: PSC=0, ARR=3199 → 64 MHz / 3200 = 20 kHz */
    htim16.Instance               = TIM16;
    htim16.Init.Prescaler         = 0;
    htim16.Init.CounterMode       = TIM_COUNTERMODE_UP;
    htim16.Init.Period            = MTR_PWM_PERIOD - 1U;
    htim16.Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    htim16.Init.RepetitionCounter = 0;
    htim16.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
    if (HAL_TIM_PWM_Init(&htim16) != HAL_OK) { Error_Handler(); }

    sConfigOC.OCMode      = TIM_OCMODE_PWM1;
    sConfigOC.Pulse       = 0;
    sConfigOC.OCPolarity  = TIM_OCPOLARITY_HIGH;
    sConfigOC.OCFastMode  = TIM_OCFAST_DISABLE;
    sConfigOC.OCIdleState = TIM_OCIDLESTATE_RESET;
    if (HAL_TIM_PWM_ConfigChannel(&htim16, &sConfigOC, TIM_CHANNEL_1) != HAL_OK) { Error_Handler(); }
    /* MTR_Init() starts the channel via HAL_TIM_PWM_Start */
}

static void MX_LPTIM1_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    __HAL_RCC_LPTIM1_CLK_ENABLE();

    /* PC1 = LPTIM1_OUT (MOTOR_LEFT_PWM, Arduino A3) */
    GPIO_InitStruct.Pin       = GPIO_PIN_1;
    GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull      = GPIO_NOPULL;
    GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_LOW;
    GPIO_InitStruct.Alternate = GPIO_AF1_LPTIM1;
    HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

    /* LPTIM1: PCLK1=64 MHz, DIV1 → ARR=3199 → 20 kHz */
    hlptim1.Instance                              = LPTIM1;
    hlptim1.Init.Clock.Source                     = LPTIM_CLOCKSOURCE_APBCLOCK_LPOSC;
    hlptim1.Init.Clock.Prescaler                  = LPTIM_PRESCALER_DIV1;
    hlptim1.Init.UltraLowPowerClock.Polarity      = LPTIM_CLOCKPOLARITY_RISING;
    hlptim1.Init.UltraLowPowerClock.SampleTime    = LPTIM_CLOCKSAMPLETIME_DIRECTTRANSITION;
    hlptim1.Init.Trigger.Source                   = LPTIM_TRIGSOURCE_SOFTWARE;
    hlptim1.Init.Trigger.ActiveEdge               = LPTIM_ACTIVEEDGE_RISING;
    hlptim1.Init.Trigger.SampleTime               = LPTIM_TRIGSAMPLETIME_DIRECTTRANSITION;
    hlptim1.Init.OutputPolarity                   = LPTIM_OUTPUTPOLARITY_HIGH;
    hlptim1.Init.UpdateMode                       = LPTIM_UPDATE_IMMEDIATE;
    hlptim1.Init.CounterSource                    = LPTIM_COUNTERSOURCE_INTERNAL;
    hlptim1.Init.Input1Source                     = LPTIM_INPUT1SOURCE_GPIO;
    hlptim1.Init.Input2Source                     = LPTIM_INPUT2SOURCE_GPIO;
    if (HAL_LPTIM_Init(&hlptim1) != HAL_OK) { Error_Handler(); }
    /* MTR_Init() starts PWM via HAL_LPTIM_PWM_Start */
}

static void MX_I2C3_Init(void)       { /* TODO: IMU ISM330DHCX */ }

static void MX_USART1_UART_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    __HAL_RCC_USART1_CLK_ENABLE();

    /* PB6 = USART1_TX, PB7 = USART1_RX (ST-Link VCP) */
    GPIO_InitStruct.Pin       = GPIO_PIN_6 | GPIO_PIN_7;
    GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull      = GPIO_NOPULL;
    GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_LOW;
    GPIO_InitStruct.Alternate = GPIO_AF7_USART1;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    huart1.Instance          = USART1;
    huart1.Init.BaudRate     = 115200;
    huart1.Init.WordLength   = UART_WORDLENGTH_8B;
    huart1.Init.StopBits     = UART_STOPBITS_1;
    huart1.Init.Parity       = UART_PARITY_NONE;
    huart1.Init.Mode         = UART_MODE_TX_RX;
    huart1.Init.HwFlowCtl    = UART_HWCONTROL_NONE;
    huart1.Init.OverSampling = UART_OVERSAMPLING_16;
    if (HAL_UART_Init(&huart1) != HAL_OK) { Error_Handler(); }

    /* Priority 5 = safe to call from FreeRTOS ISR API (configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY) */
    HAL_NVIC_SetPriority(USART1_IRQn, 5U, 0U);
    HAL_NVIC_EnableIRQ(USART1_IRQn);
}

static void MX_ADC1_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    __HAL_RCC_ADC_CLK_ENABLE();

    /* PA5=ADC1_IN10 (left current), PC3=ADC1_IN4 (right current) */
    GPIO_InitStruct.Pin  = GPIO_PIN_5;
    GPIO_InitStruct.Mode = GPIO_MODE_ANALOG;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

    GPIO_InitStruct.Pin = GPIO_PIN_3;
    HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

    /* STM32WB5 a un seul ADC — pas de multi-mode */
    hadc1.Instance                   = ADC1;
    hadc1.Init.ClockPrescaler        = ADC_CLOCK_ASYNC_DIV1;
    hadc1.Init.Resolution            = ADC_RESOLUTION_12B;
    hadc1.Init.DataAlign             = ADC_DATAALIGN_RIGHT;
    hadc1.Init.ScanConvMode          = ADC_SCAN_DISABLE;
    hadc1.Init.EOCSelection          = ADC_EOC_SINGLE_CONV;
    hadc1.Init.LowPowerAutoWait      = DISABLE;
    hadc1.Init.ContinuousConvMode    = DISABLE;
    hadc1.Init.NbrOfConversion       = 1;
    hadc1.Init.DiscontinuousConvMode = DISABLE;
    hadc1.Init.ExternalTrigConv      = ADC_SOFTWARE_START;
    hadc1.Init.ExternalTrigConvEdge  = ADC_EXTERNALTRIGCONVEDGE_NONE;
    hadc1.Init.DMAContinuousRequests = DISABLE;
    hadc1.Init.Overrun               = ADC_OVR_DATA_OVERWRITTEN;
    hadc1.Init.OversamplingMode      = DISABLE;
    if (HAL_ADC_Init(&hadc1) != HAL_OK) { Error_Handler(); }

    HAL_ADCEx_Calibration_Start(&hadc1, ADC_SINGLE_ENDED);
}

void Error_Handler(void)
{
    __disable_irq();
    for (;;) {}
}

// QEI Init function (LEFT encoder TIM1 · PD14=CHA · PD15=CHB)
void MX_TIM1_Init(void)
{
    GPIO_InitTypeDef      GPIO_InitStruct = {0};
    TIM_Encoder_InitTypeDef sConfig       = {0};

    /* Peripheral and GPIO clocks */
    __HAL_RCC_TIM1_CLK_ENABLE();

    /* PD14 = TIM1_CH1, PD15 = TIM1_CH2 */
    GPIO_InitStruct.Pin       = GPIO_PIN_14 | GPIO_PIN_15;
    GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull      = GPIO_PULLUP;
    GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_MEDIUM;
    GPIO_InitStruct.Alternate = GPIO_AF1_TIM1;
    HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);

    /* TIM1 base */
    htim1.Instance               = TIM1;
    htim1.Init.Prescaler         = 0;
    htim1.Init.CounterMode       = TIM_COUNTERMODE_UP;
    htim1.Init.Period            = 0xFFFFU;  /* 16-bit wrap */
    htim1.Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    htim1.Init.RepetitionCounter = 0;
    htim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;

    /* Encoder channel config */
    sConfig.EncoderMode  = TIM_ENCODERMODE_TI12;
    sConfig.IC1Polarity  = TIM_ICPOLARITY_RISING;
    sConfig.IC1Selection = TIM_ICSELECTION_DIRECTTI;
    sConfig.IC1Prescaler = TIM_ICPSC_DIV1;
    sConfig.IC1Filter    = 4U;
    sConfig.IC2Polarity  = TIM_ICPOLARITY_RISING;
    sConfig.IC2Selection = TIM_ICSELECTION_DIRECTTI;
    sConfig.IC2Prescaler = TIM_ICPSC_DIV1;
    sConfig.IC2Filter    = 4U;

    if (HAL_TIM_Encoder_Init(&htim1, &sConfig) != HAL_OK)
    {
        Error_Handler();
    }

    HAL_TIM_Encoder_Start(&htim1, TIM_CHANNEL_ALL);
}

// QEI Init function (RIGHT encoder TIM2 · PA15=CHA · PB3=CHB)
void MX_TIM2_Init(void)
{
    GPIO_InitTypeDef        GPIO_InitStruct = {0};
    TIM_Encoder_InitTypeDef sConfig         = {0};

    __HAL_RCC_TIM2_CLK_ENABLE();

    /* PA15 = TIM2_CH1 */
    GPIO_InitStruct.Pin       = GPIO_PIN_15;
    GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull      = GPIO_PULLUP;
    GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_MEDIUM;
    GPIO_InitStruct.Alternate = GPIO_AF1_TIM2;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

    /* PB3 = TIM2_CH2 (overrides SWO) */
    GPIO_InitStruct.Pin = GPIO_PIN_3;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    /* TIM2 base — 32-bit counter */
    htim2.Instance               = TIM2;
    htim2.Init.Prescaler         = 0;
    htim2.Init.CounterMode       = TIM_COUNTERMODE_UP;
    htim2.Init.Period            = 0xFFFFFFFFU;  /* 32-bit wrap */
    htim2.Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    htim2.Init.RepetitionCounter = 0;
    htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;

    sConfig.EncoderMode  = TIM_ENCODERMODE_TI12;
    sConfig.IC1Polarity  = TIM_ICPOLARITY_RISING;
    sConfig.IC1Selection = TIM_ICSELECTION_DIRECTTI;
    sConfig.IC1Prescaler = TIM_ICPSC_DIV1;
    sConfig.IC1Filter    = 4U;
    sConfig.IC2Polarity  = TIM_ICPOLARITY_RISING;
    sConfig.IC2Selection = TIM_ICSELECTION_DIRECTTI;
    sConfig.IC2Prescaler = TIM_ICPSC_DIV1;
    sConfig.IC2Filter    = 4U;

    if (HAL_TIM_Encoder_Init(&htim2, &sConfig) != HAL_OK)
    {
        Error_Handler();
    }

    HAL_TIM_Encoder_Start(&htim2, TIM_CHANNEL_ALL);
}