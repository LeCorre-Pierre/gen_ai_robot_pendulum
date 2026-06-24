/**
  ******************************************************************************
  * @file    robot_stm.h
  * @brief   Robot Service (Custom STM) — GATT layer
  *          Service A0B00001-C000-4000-8000-000000000001
  *            - Command   A0B00002-... : Write Without Response (App -> Robot)
  *            - Telemetry A0B00003-... : Notify               (Robot -> App)
  *          See 10-android-app-architecture.md for the binary protocol.
  ******************************************************************************
  */
#ifndef ROBOT_STM_H
#define ROBOT_STM_H

#ifdef __cplusplus
extern "C" {
#endif

#include "ble_types.h"

/* Events reported by the GATT layer to the application (robot_app.c) */
typedef enum
{
  ROBOT_STM_CMD_WRITE_EVT,
  ROBOT_STM_TELEMETRY_NOTIFY_ENABLED_EVT,
  ROBOT_STM_TELEMETRY_NOTIFY_DISABLED_EVT,
} Robot_STM_Opcode_evt_t;

typedef struct
{
  uint8_t *pPayload;
  uint8_t  Length;
} Robot_STM_Data_t;

typedef struct
{
  Robot_STM_Opcode_evt_t Robot_Evt_Opcode;
  Robot_STM_Data_t       DataTransfered;
} Robot_STM_App_Notification_evt_t;

/* Characteristic selector for Robot_STM_App_Update_Char */
typedef enum
{
  ROBOT_STM_TELEMETRY_CHAR,
} Robot_STM_Char_Opcode_t;

/* GATT layer API */
void       Robot_STM_Init(void);
tBleStatus Robot_STM_App_Update_Char(Robot_STM_Char_Opcode_t CharOpcode,
                                     uint8_t *pPayload, uint8_t Length);

/* Implemented by the application layer (robot_app.c) */
void Robot_STM_App_Notification(Robot_STM_App_Notification_evt_t *pNotification);

#ifdef __cplusplus
}
#endif

#endif /* ROBOT_STM_H */
