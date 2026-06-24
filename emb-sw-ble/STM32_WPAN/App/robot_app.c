/**
  ******************************************************************************
  * @file    robot_app.c
  * @brief   Robot Service application layer.
  *          Step 3: parse commands (log only) and stream SYNTHETIC telemetry
  *          (sine sweep) at 20 Hz. Real robot data is wired in at step 4.
  ******************************************************************************
  */

/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "app_common.h"
#include "dbg_trace.h"
#include "ble.h"
#include "cmsis_os.h"
#include <math.h>

#include "robot_stm.h"
#include "robot_app.h"
#include "task_sensors.h"

/* Telemetry FLAGS bitfield (see 10-android-app-architecture.md) */
#define FLAG_BALANCE_ACTIVE   (1U << 0)
#define FLAG_SAFETY_CUTOFF    (1U << 1)
#define FLAG_DEMO_RUNNING     (1U << 2)
#define FLAG_ESTOP_ACTIVE     (1U << 3)

/* Command IDs (App -> Robot) */
#define CMD_DRIVE             0x01
#define CMD_EMERGENCY_STOP    0x02
#define CMD_RESUME            0x03
#define CMD_DEMO_AUTO_SPIN    0x04
#define CMD_DEMO_BACK_FORTH   0x05
#define CMD_DEMO_SINUS_SWEEP  0x06
#define CMD_DEMO_STOP         0x07

#define TELEMETRY_PERIOD_MS   50U   /* 20 Hz */

/* Private variables ---------------------------------------------------------*/
typedef struct
{
  volatile uint8_t Notification_Status; /* 1 when client enabled telemetry notify */
  uint8_t          seq;
  uint32_t         tick;                /* counts telemetry periods, for synth sine */
  volatile uint32_t tx_count;           /* telemetry frames actually sent */
} Robot_App_Context_t;

static Robot_App_Context_t Robot_App_Context;

static osThreadId_t TelemetryThreadId;
static const osThreadAttr_t TelemetryProcess_attr =
{
  .name       = "RobotTelemetry",
  .priority   = osPriorityNormal,
  .stack_size = 1024U,
};

/* Private function prototypes -----------------------------------------------*/
static void TelemetryProcess(void *argument);
static void Build_Synthetic_Frame(uint8_t buf[11]);

/* Functions Definition ------------------------------------------------------*/
uint32_t Robot_App_GetTxCount(void)
{
  return Robot_App_Context.tx_count;
}

void Robot_App_Init(void)
{
  Robot_App_Context.Notification_Status = 0;
  Robot_App_Context.seq  = 0;
  Robot_App_Context.tick = 0;
  Robot_App_Context.tx_count = 0;

  TelemetryThreadId = osThreadNew(TelemetryProcess, NULL, &TelemetryProcess_attr);

  APP_DBG_MSG("-- ROBOT APP : initialized (synthetic telemetry @20Hz)\n\r");

  return;
}

/* Called by the GATT layer (robot_stm.c) on client events */
void Robot_STM_App_Notification(Robot_STM_App_Notification_evt_t *pNotification)
{
  switch (pNotification->Robot_Evt_Opcode)
  {
    case ROBOT_STM_TELEMETRY_NOTIFY_ENABLED_EVT:
      Robot_App_Context.Notification_Status = 1;
      APP_DBG_MSG("-- ROBOT APP : telemetry notifications ENABLED\n\r");
      break;

    case ROBOT_STM_TELEMETRY_NOTIFY_DISABLED_EVT:
      Robot_App_Context.Notification_Status = 0;
      APP_DBG_MSG("-- ROBOT APP : telemetry notifications DISABLED\n\r");
      break;

    case ROBOT_STM_CMD_WRITE_EVT:
    {
      uint8_t *p   = pNotification->DataTransfered.pPayload;
      uint8_t  len = pNotification->DataTransfered.Length;
      if (len == 0)
      {
        break;
      }
      switch (p[0])
      {
        case CMD_DRIVE:
          APP_DBG_MSG("-- ROBOT APP : DRIVE speed=%d turn=%d\n\r",
                      (len > 1) ? (int8_t)p[1] : 0,
                      (len > 2) ? (int8_t)p[2] : 0);
          break;
        case CMD_EMERGENCY_STOP:
          APP_DBG_MSG("-- ROBOT APP : EMERGENCY_STOP\n\r");
          break;
        case CMD_RESUME:
          APP_DBG_MSG("-- ROBOT APP : RESUME\n\r");
          break;
        case CMD_DEMO_AUTO_SPIN:
          APP_DBG_MSG("-- ROBOT APP : DEMO_AUTO_SPIN\n\r");
          break;
        case CMD_DEMO_BACK_FORTH:
          APP_DBG_MSG("-- ROBOT APP : DEMO_BACK_FORTH\n\r");
          break;
        case CMD_DEMO_SINUS_SWEEP:
          APP_DBG_MSG("-- ROBOT APP : DEMO_SINUS_SWEEP\n\r");
          break;
        case CMD_DEMO_STOP:
          APP_DBG_MSG("-- ROBOT APP : DEMO_STOP\n\r");
          break;
        default:
          APP_DBG_MSG("-- ROBOT APP : unknown CMD 0x%02x (len=%d)\n\r", p[0], len);
          break;
      }
    }
    break;

    default:
      break;
  }

  return;
}

/*************************************************************
 * LOCAL FUNCTIONS
 *************************************************************/
static void Build_Synthetic_Frame(uint8_t buf[11])
{
  /* Step 4a: real pitch from the IMU; speeds/drive/battery wired in later steps. */
  int16_t  pitch   = (int16_t)(Sensors_GetPitchDeg() * 100.0f); /* deg x100, real   */
  int16_t  speed_l = 0;                                         /* encoders: step 4b */
  int16_t  speed_r = 0;
  int8_t   drive   = 0;
  uint16_t batt_mv = 7400U;                                     /* ADC: later        */

  buf[0]  = Robot_App_Context.seq++;
  buf[1]  = FLAG_BALANCE_ACTIVE;
  buf[2]  = (uint8_t)(pitch & 0xFF);
  buf[3]  = (uint8_t)((pitch >> 8) & 0xFF);
  buf[4]  = (uint8_t)(speed_l & 0xFF);
  buf[5]  = (uint8_t)((speed_l >> 8) & 0xFF);
  buf[6]  = (uint8_t)(speed_r & 0xFF);
  buf[7]  = (uint8_t)((speed_r >> 8) & 0xFF);
  buf[8]  = (uint8_t)drive;
  buf[9]  = (uint8_t)(batt_mv & 0xFF);
  buf[10] = (uint8_t)((batt_mv >> 8) & 0xFF);
}

static void TelemetryProcess(void *argument)
{
  uint8_t frame[11];
  UNUSED(argument);

  for (;;)
  {
    osDelay(TELEMETRY_PERIOD_MS);
    Robot_App_Context.tick++;

    if (Robot_App_Context.Notification_Status)
    {
      Build_Synthetic_Frame(frame);
      if (Robot_STM_App_Update_Char(ROBOT_STM_TELEMETRY_CHAR, frame, sizeof(frame)) == BLE_STATUS_SUCCESS)
      {
        Robot_App_Context.tx_count++;
      }
    }
  }
}
