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
#define VCP_TYPE_TELEMETRY_CALIB 0x12u   /* motor dead-zone calibration stream */
#define VCP_TYPE_TELEMETRY_POS   0x13u   /* position loop telemetry */

/* Downlink  PC → STM32 */
#define VCP_TYPE_CMD_SET_GAINS         0x20u
#define VCP_TYPE_CMD_SET_SP            0x21u
#define VCP_TYPE_CMD_STREAM_CTRL       0x22u
#define VCP_TYPE_CMD_MOTOR_CTRL        0x23u
#define VCP_TYPE_CMD_SET_BALANCE_GAINS 0x24u
#define VCP_TYPE_CMD_MOTOR_CALIB       0x25u   /* start/abort calibration sequence */
#define VCP_TYPE_CMD_SET_POS_SP        0x26u   /* position setpoint (cm, relative to origin) */
#define VCP_TYPE_CMD_SET_POS_TRAJ      0x27u   /* trajectory: mode + amplitude + period */
#define VCP_TYPE_CMD_SPIN_CTRL         0x28u   /* periodic 360° auto-spin */
#define VCP_TYPE_CMD_SET_DRIVE         0x29u   /* direct open-loop drive (Ident K / Ident Td) */
#define VCP_TYPE_CMD_SET_ANGLE_SP      0x2Au   /* angle equilibrium offset [-5..+5] deg */

/* loop_id for SET_BALANCE_GAINS */
#define VCP_LOOP_ANGLE    0u
#define VCP_LOOP_VELOCITY 1u
#define VCP_LOOP_YAW      2u
#define VCP_LOOP_POSITION 3u

/* traj_mode for SET_POS_TRAJ */
#define VCP_TRAJ_HOLD  0u
#define VCP_TRAJ_SINUS 1u

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
    int16_t  gyro_x_x100;     /* gyro  BSP X  dps × 100      */
    int16_t  gyro_y_x100;     /* gyro  BSP Y  dps × 100      */
    int16_t  gyro_z_x100;     /* gyro  BSP Z  dps × 100      */
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

/* VCP_TYPE_TELEMETRY_CALIB — 12 bytes
 * Sent at ~100 Hz during motor calibration sequence.
 * drive_x1000  : normalized drive command × 1000 (e.g. 500 = 0.50)
 * vel_l/r_rpm  : wheel velocities signed (RPM, full-scale ≈ ±85)
 * phase        : sequence phase tag 0–16
 * calib_active : 1 = running, 0 = last packet (done) */
typedef struct __attribute__((packed)) {
    uint32_t timestamp_ms;
    int16_t  drive_x1000;
    int16_t  vel_l_rpm;
    int16_t  vel_r_rpm;
    uint8_t  phase;
    uint8_t  calib_active;
} VcpTelCalib_t;

/* VCP_TYPE_CMD_MOTOR_CALIB — 1 byte */
typedef struct __attribute__((packed)) {
    uint8_t enable;   /* 1 = start sequence, 0 = abort */
} VcpCmdMotorCalib_t;

/* VCP_TYPE_TELEMETRY_POS — 12 bytes */
typedef struct __attribute__((packed)) {
    uint32_t timestamp_ms;
    int16_t  pos_cm_x10;    /* current position × 10 (cm) — range ±3276.7 cm */
    int16_t  sp_cm_x10;     /* position setpoint × 10 (cm) */
    int16_t  vel_sp_rpm;    /* velocity setpoint output from position PID (RPM) */
    uint8_t  ctrl_mode;     /* 0=velocity, 1=position */
    uint8_t  traj_mode;     /* 0=hold, 1=sinus */
} VcpTelPos_t;

/* VCP_TYPE_CMD_SET_POS_SP — 4 bytes */
typedef struct __attribute__((packed)) {
    float sp_cm;            /* target position (cm) relative to current origin */
} VcpCmdSetPosSp_t;

/* VCP_TYPE_CMD_SET_POS_TRAJ — 9 bytes */
typedef struct __attribute__((packed)) {
    uint8_t mode;           /* VCP_TRAJ_HOLD or VCP_TRAJ_SINUS */
    float   amplitude_cm;   /* sinus: amplitude (cm); hold: target position (cm) */
    float   period_s;       /* sinus: period (s); unused for hold */
} VcpCmdSetPosTraj_t;

/* VCP_TYPE_CMD_SPIN_CTRL — 9 bytes */
typedef struct __attribute__((packed)) {
    uint8_t enable;       /* 1 = activate periodic spin, 0 = deactivate */
    float   interval_s;   /* time between spins (s) */
    float   yaw_force;    /* normalized yaw differential [0.1..0.5] */
} VcpCmdSpinCtrl_t;

/* VCP_TYPE_CMD_SET_DRIVE — 2 bytes
 * Direct motor drive command for Ident K / Ident Td : applied to both
 * wheels identically, bypassing the balance loop entirely (ctrl_mode=2).
 * Drive resets to 0 if no new command is received for ~300 ms. */
typedef struct __attribute__((packed)) {
    int16_t drive_x1000;   /* normalized drive × 1000, range [-1000..+1000] */
} VcpCmdSetDrive_t;

/* VCP_TYPE_CMD_SET_ANGLE_SP — 4 bytes */
typedef struct __attribute__((packed)) {
    float offset_deg;   /* equilibrium offset [-5..+5] deg */
} VcpCmdSetAngleSp_t;

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
