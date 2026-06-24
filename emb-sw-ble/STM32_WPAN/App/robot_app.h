/**
  ******************************************************************************
  * @file    robot_app.h
  * @brief   Robot Service application layer
  ******************************************************************************
  */
#ifndef ROBOT_APP_H
#define ROBOT_APP_H

#ifdef __cplusplus
extern "C" {
#endif

void Robot_App_Init(void);
uint32_t Robot_App_GetTxCount(void);

#ifdef __cplusplus
}
#endif

#endif /* ROBOT_APP_H */
