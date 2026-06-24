/**
  ******************************************************************************
  * @file    robot_stm.c
  * @brief   Robot Service (Custom STM) — GATT layer
  *          Modelled on STM32CubeWB p2p_stm.c.
  ******************************************************************************
  */

/* Includes ------------------------------------------------------------------*/
#include "common_blesvc.h"
#include "dbg_trace.h"
#include "robot_stm.h"

/* Private typedef -----------------------------------------------------------*/
typedef struct
{
  uint16_t RobotSvcHdle;        /**< Service handle */
  uint16_t CommandCharHdle;     /**< Command characteristic handle  (Write)  */
  uint16_t TelemetryCharHdle;   /**< Telemetry characteristic handle (Notify) */
} RobotContext_t;

/* Private defines -----------------------------------------------------------*/
#define ROBOT_CMD_CHAR_SIZE        8U   /* max command frame length */
#define ROBOT_TELEMETRY_CHAR_SIZE  11U  /* fixed telemetry frame length */

/* Private macros ------------------------------------------------------------*/
#define COPY_UUID_128(uuid_struct, uuid_15, uuid_14, uuid_13, uuid_12, uuid_11, uuid_10, uuid_9, uuid_8, uuid_7, uuid_6, uuid_5, uuid_4, uuid_3, uuid_2, uuid_1, uuid_0) \
do {\
    uuid_struct[0] = uuid_0; uuid_struct[1] = uuid_1; uuid_struct[2] = uuid_2; uuid_struct[3] = uuid_3; \
    uuid_struct[4] = uuid_4; uuid_struct[5] = uuid_5; uuid_struct[6] = uuid_6; uuid_struct[7] = uuid_7; \
    uuid_struct[8] = uuid_8; uuid_struct[9] = uuid_9; uuid_struct[10] = uuid_10; uuid_struct[11] = uuid_11; \
    uuid_struct[12] = uuid_12; uuid_struct[13] = uuid_13; uuid_struct[14] = uuid_14; uuid_struct[15] = uuid_15; \
}while(0)

/* A0B00001-C000-4000-8000-000000000001 (service) */
#define COPY_ROBOT_SERVICE_UUID(uuid)    COPY_UUID_128(uuid,0xA0,0xB0,0x00,0x01,0xC0,0x00,0x40,0x00,0x80,0x00,0x00,0x00,0x00,0x00,0x00,0x01)
/* A0B00002-C000-4000-8000-000000000001 (command, write) */
#define COPY_ROBOT_CMD_UUID(uuid)        COPY_UUID_128(uuid,0xA0,0xB0,0x00,0x02,0xC0,0x00,0x40,0x00,0x80,0x00,0x00,0x00,0x00,0x00,0x00,0x01)
/* A0B00003-C000-4000-8000-000000000001 (telemetry, notify) */
#define COPY_ROBOT_TELEMETRY_UUID(uuid)  COPY_UUID_128(uuid,0xA0,0xB0,0x00,0x03,0xC0,0x00,0x40,0x00,0x80,0x00,0x00,0x00,0x00,0x00,0x00,0x01)

/* Private variables ---------------------------------------------------------*/
PLACE_IN_SECTION("BLE_DRIVER_CONTEXT") static RobotContext_t aRobotContext;

/* Private function prototypes -----------------------------------------------*/
static SVCCTL_EvtAckStatus_t Robot_Event_Handler(void *Event);

/* Functions Definition ------------------------------------------------------*/
static SVCCTL_EvtAckStatus_t Robot_Event_Handler(void *Event)
{
  SVCCTL_EvtAckStatus_t return_value;
  hci_event_pckt *event_pckt;
  evt_blecore_aci *blecore_evt;
  aci_gatt_attribute_modified_event_rp0 *attribute_modified;
  Robot_STM_App_Notification_evt_t Notification;

  return_value = SVCCTL_EvtNotAck;
  event_pckt = (hci_event_pckt *)(((hci_uart_pckt *)Event)->data);

  switch (event_pckt->evt)
  {
    case HCI_VENDOR_SPECIFIC_DEBUG_EVT_CODE:
    {
      blecore_evt = (evt_blecore_aci *)event_pckt->data;
      switch (blecore_evt->ecode)
      {
        case ACI_GATT_ATTRIBUTE_MODIFIED_VSEVT_CODE:
        {
          attribute_modified = (aci_gatt_attribute_modified_event_rp0 *)blecore_evt->data;

          /* CCCD of the Telemetry characteristic (handle + 2) */
          if (attribute_modified->Attr_Handle == (aRobotContext.TelemetryCharHdle + 2))
          {
            return_value = SVCCTL_EvtAckFlowEnable;
            if (attribute_modified->Attr_Data[0] & COMSVC_Notification)
            {
              Notification.Robot_Evt_Opcode = ROBOT_STM_TELEMETRY_NOTIFY_ENABLED_EVT;
            }
            else
            {
              Notification.Robot_Evt_Opcode = ROBOT_STM_TELEMETRY_NOTIFY_DISABLED_EVT;
            }
            Robot_STM_App_Notification(&Notification);
          }
          /* Value of the Command characteristic (handle + 1) */
          else if (attribute_modified->Attr_Handle == (aRobotContext.CommandCharHdle + 1))
          {
            return_value = SVCCTL_EvtAckFlowEnable;
            Notification.Robot_Evt_Opcode        = ROBOT_STM_CMD_WRITE_EVT;
            Notification.DataTransfered.Length   = attribute_modified->Attr_Data_Length;
            Notification.DataTransfered.pPayload = attribute_modified->Attr_Data;
            Robot_STM_App_Notification(&Notification);
          }
        }
        break;

        default:
          break;
      }
    }
    break;

    default:
      break;
  }

  return (return_value);
}

void Robot_STM_Init(void)
{
  Char_UUID_t uuid;
  tBleStatus st;

  /* Register the event handler with the BLE controller */
  SVCCTL_RegisterSvcHandler(Robot_Event_Handler);

  /**
   * Robot Service
   * Max_Attribute_Records = 1 (service)
   *                       + 2 (Command characteristic)
   *                       + 2 (Telemetry characteristic)
   *                       + 1 (Telemetry client char config descriptor)
   *                       = 6
   */
  COPY_ROBOT_SERVICE_UUID(uuid.Char_UUID_128);
  st = aci_gatt_add_service(UUID_TYPE_128,
                       (Service_UUID_t *)&uuid,
                       PRIMARY_SERVICE,
                       6,
                       &(aRobotContext.RobotSvcHdle));
  APP_DBG_MSG("-- ROBOT STM : add_service status=0x%02x hdle=0x%04x\n\r", st, aRobotContext.RobotSvcHdle);

  /* Command characteristic — Write Without Response (App -> Robot) */
  COPY_ROBOT_CMD_UUID(uuid.Char_UUID_128);
  st = aci_gatt_add_char(aRobotContext.RobotSvcHdle,
                    UUID_TYPE_128, &uuid,
                    ROBOT_CMD_CHAR_SIZE,
                    CHAR_PROP_WRITE_WITHOUT_RESP | CHAR_PROP_WRITE,
                    ATTR_PERMISSION_NONE,
                    GATT_NOTIFY_ATTRIBUTE_WRITE,
                    10,  /* encryKeySize */
                    1,   /* isVariable */
                    &(aRobotContext.CommandCharHdle));
  APP_DBG_MSG("-- ROBOT STM : add_char Command  status=0x%02x hdle=0x%04x\n\r", st, aRobotContext.CommandCharHdle);

  /* Telemetry characteristic — Notify (Robot -> App) */
  COPY_ROBOT_TELEMETRY_UUID(uuid.Char_UUID_128);
  st = aci_gatt_add_char(aRobotContext.RobotSvcHdle,
                    UUID_TYPE_128, &uuid,
                    ROBOT_TELEMETRY_CHAR_SIZE,
                    CHAR_PROP_NOTIFY,
                    ATTR_PERMISSION_NONE,
                    GATT_NOTIFY_ATTRIBUTE_WRITE,
                    10,  /* encryKeySize */
                    0,   /* isVariable: fixed 11 bytes */
                    &(aRobotContext.TelemetryCharHdle));
  APP_DBG_MSG("-- ROBOT STM : add_char Telemetry status=0x%02x hdle=0x%04x\n\r", st, aRobotContext.TelemetryCharHdle);

  return;
}

tBleStatus Robot_STM_App_Update_Char(Robot_STM_Char_Opcode_t CharOpcode,
                                     uint8_t *pPayload, uint8_t Length)
{
  tBleStatus result = BLE_STATUS_INVALID_PARAMS;

  switch (CharOpcode)
  {
    case ROBOT_STM_TELEMETRY_CHAR:
      result = aci_gatt_update_char_value(aRobotContext.RobotSvcHdle,
                                          aRobotContext.TelemetryCharHdle,
                                          0,        /* charValOffset */
                                          Length,   /* charValueLen */
                                          pPayload);
      break;

    default:
      break;
  }

  return result;
}
