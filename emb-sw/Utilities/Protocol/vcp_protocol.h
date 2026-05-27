#ifndef VCP_PROTOCOL_H
#define VCP_PROTOCOL_H

#include <stdint.h>
#include <stddef.h>

#define VCP_SOF1   0xAAu
#define VCP_SOF2   0x55u
#define VCP_EOF    0x33u
#define VCP_VER    0x01u

/* ── Packet type codes ─────────────────────────────────────────────────────── */
/* Uplink  STM32 → PC */
#define VCP_TYPE_TELEMETRY_PID   0x10u
#define VCP_TYPE_TELEMETRY_IMU   0x11u

/* Downlink  PC → STM32 */
#define VCP_TYPE_CMD_SET_GAINS   0x20u
#define VCP_TYPE_CMD_SET_SP      0x21u
#define VCP_TYPE_CMD_STREAM_CTRL 0x22u
#define VCP_TYPE_CMD_MOTOR_CTRL  0x23u
#define VCP_TYPE_CMD_SET_BALANCE_GAINS 0x24u

/* loop_id for SET_BALANCE_GAINS */
#define VCP_LOOP_ANGLE    0u
#define VCP_LOOP_VELOCITY 1u
#define VCP_LOOP_YAW      2u

/* Uplink  STM32 → PC  (ack of a command) */
#define VCP_TYPE_ACK             0x30u

/* Motor action codes (CMD_MOTOR_CTRL) */
#define VCP_MOTOR_COAST  0u
#define VCP_MOTOR_BRAKE  1u
#define VCP_MOTOR_ENABLE 2u

/* ── Payload structs (packed to match wire layout) ─────────────────────────── */

/* VCP_TYPE_TELEMETRY_PID — 18 bytes */
typedef struct __attribute__((packed)) {
    uint32_t timestamp_ms;
    int16_t  sp_rpm;
    int16_t  pv_l_rpm;
    int16_t  pv_r_rpm;
    int16_t  err_l;
    int16_t  err_r;
    int16_t  pwm_l_x100;   /* PID output × 100, e.g. 45 = 0.45 */
    int16_t  pwm_r_x100;
} VcpTelPid_t;

/* VCP_TYPE_TELEMETRY_IMU — 20 bytes (6 axes bruts + pitch estimé + CBC drive output) */
typedef struct __attribute__((packed)) {
    uint32_t timestamp_ms;
    int16_t  accel_x_mg;      /* accel BSP X  in mg          */
    int16_t  accel_y_mg;      /* accel BSP Y  in mg          */
    int16_t  accel_z_mg;      /* accel BSP Z  in mg          */
    int16_t  gyro_x_x10;      /* gyro  BSP X  dps × 10       */
    int16_t  gyro_y_x10;      /* gyro  BSP Y  dps × 10       */
    int16_t  gyro_z_x10;      /* gyro  BSP Z  dps × 10       */
    int16_t  pitch_x100;      /* pitch estimé × 100          */
    int16_t  drive_x100;      /* CBC drive output × 100      */
} VcpTelImu_t;

/* VCP_TYPE_CMD_SET_GAINS — 13 bytes */
typedef struct __attribute__((packed)) {
    uint8_t motor_id;       /* 0=LEFT, 1=RIGHT, 2=BOTH */
    float   kp;
    float   ki;
    float   kd;
} VcpCmdSetGains_t;

/* VCP_TYPE_CMD_SET_SP — 2 bytes */
typedef struct __attribute__((packed)) {
    int16_t sp_rpm;
} VcpCmdSetSp_t;

/* VCP_TYPE_CMD_STREAM_CTRL — 3 bytes */
typedef struct __attribute__((packed)) {
    uint8_t  enable;        /* 1=start, 0=stop */
    uint16_t rate_hz;       /* 1–100 Hz */
} VcpCmdStreamCtrl_t;

/* VCP_TYPE_CMD_MOTOR_CTRL — 1 byte */
typedef struct __attribute__((packed)) {
    uint8_t action;         /* VCP_MOTOR_COAST / BRAKE / ENABLE */
} VcpCmdMotorCtrl_t;

/* VCP_TYPE_CMD_SET_BALANCE_GAINS — 13 bytes */
typedef struct __attribute__((packed)) {
    uint8_t loop_id;   /* VCP_LOOP_ANGLE / VCP_LOOP_VELOCITY / VCP_LOOP_YAW */
    float   kp;
    float   ki;
    float   kd;
} VcpCmdSetBalanceGains_t;

/* VCP_TYPE_ACK — 2 bytes */
typedef struct __attribute__((packed)) {
    uint8_t cmd_type;
    uint8_t status;         /* 0=OK, 1=ERROR */
} VcpAck_t;

/* ── Core packet struct ─────────────────────────────────────────────────────── */
typedef struct {
    uint8_t  type;
    uint8_t  flags;
    uint8_t  seq;
    uint16_t len;
    uint8_t *payload;
} VcpPacket_t;

uint16_t VcpProtocol_Crc16(const uint8_t *data, size_t len);
int      VcpProtocol_Frame(const VcpPacket_t *pkt, uint8_t *buf, size_t buf_size);
int      VcpProtocol_Parse(const uint8_t *buf, size_t len, VcpPacket_t *pkt_out);

#endif /* VCP_PROTOCOL_H */
