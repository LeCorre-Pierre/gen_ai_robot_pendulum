/*
 * task_comms.c — VCP telemetry + tuning command handler (emb-sw-ble, light scope)
 *
 * Uplink  (STM32 → PC) :
 *   VCP_TYPE_TELEMETRY_IMU (0x11) : pitch, drive, raw IMU
 *   VCP_TYPE_TELEMETRY_PID (0x10) : vel setpoint/measured, target_pitch, motor outputs
 *
 * Downlink (PC → STM32) :
 *   SET_BALANCE_GAINS (0x24) : loop_id=0 angle / 1 velocity / 2 yaw
 *   SET_GAINS         (0x20) : motor velocity PID gains
 *   SET_SP            (0x21) : velocity setpoint (RPM)
 *   STREAM_CTRL       (0x22) : enable/disable telemetry, set rate
 *   MOTOR_CTRL        (0x23) : coast / brake / enable
 *   SET_ANGLE_SP      (0x2A) : equilibrium angle trim [-5..+5] deg
 *   (position / spin / calib / direct-drive commands are out of scope here)
 *
 * The ST-Link VCP (USART1) is shared with the BLE debug trace, so this module
 * uses the ST hw_uart layer (HW_UART_*) — NOT raw HAL — to avoid clashing with
 * hw_uart.c's HAL_UART_RxCpltCallback. The physical channel owner is selected at
 * runtime (see VCP_SetChannel / VCP_IsChannelActive).
 */

#include "task_comms.h"
#include "task_control.h"
#include "vcp_protocol.h"
#include "motor_control.h"
#include "FreeRTOS.h"
#include "task.h"
#include "hw_if.h"          /* HW_UART_* + hw_uart1 */
#include "hw_conf.h"
#include <string.h>

/* ── Constants ──────────────────────────────────────────────────────────── */
#define COMMS_TASK_STACK_SIZE  384U
#define COMMS_TASK_PRIORITY    (tskIDLE_PRIORITY + 2U)

#define RX_RING_SIZE    256U   /* must be power-of-2 */
#define FRAME_BUF_SIZE   64U   /* max frame bytes we handle */
#define TX_BUF_SIZE      64U

#define STREAM_RATE_DEFAULT_HZ  50U
#define STREAM_RATE_MAX_HZ     100U

/* ── Shared state ────────────────────────────────────────────────────────── */
static volatile uint8_t  s_stream_active  = 0U;
static volatile uint16_t s_stream_rate_hz = STREAM_RATE_DEFAULT_HZ;
static volatile uint8_t  s_channel_vcp    = 0U;  /* 0=trace owns USART1, 1=VCP */

/* ── UART RX ring buffer (ISR → task) ───────────────────────────────────── */
static volatile uint8_t  s_rx_ring[RX_RING_SIZE];
static volatile uint16_t s_rx_head = 0U;
static volatile uint16_t s_rx_tail = 0U;
static          uint8_t  s_rx_byte;

/* ── TX sequence counter ────────────────────────────────────────────────── */
static uint8_t s_tx_seq = 0U;

/* ── Forward declarations ───────────────────────────────────────────────── */
static void CommsTask(void *pvParameters);
static void Comms_RxByteCb(void);
static void Comms_ProcessRx(void);
static void Comms_Dispatch(const VcpPacket_t *pkt);
static void Comms_SendPidTelemetry(const ControlState_t *cs);
static void Comms_SendImuTelemetry(const ControlState_t *cs);
static void Comms_SendAck(uint8_t cmd_type, uint8_t status);
static void Comms_Tx(const uint8_t *buf, uint16_t n);

/* ── Public API ─────────────────────────────────────────────────────────── */

void Task_comms_Init(void)
{
    xTaskCreate(CommsTask, "Comms", COMMS_TASK_STACK_SIZE, NULL,
                COMMS_TASK_PRIORITY, NULL);
}

void    VCP_SetChannel(uint8_t vcp_active) { s_channel_vcp = vcp_active ? 1U : 0U; }
uint8_t VCP_IsChannelActive(void)          { return s_channel_vcp; }

/* ── UART RX byte callback — called from hw_uart's HAL_UART_RxCpltCallback ── */

static void Comms_RxByteCb(void)
{
    uint16_t next = (s_rx_head + 1U) & (RX_RING_SIZE - 1U);
    if (next != s_rx_tail) {
        s_rx_ring[s_rx_head] = s_rx_byte;
        s_rx_head = next;
    }
    /* re-arm single-byte reception */
    HW_UART_Receive_IT(hw_uart1, &s_rx_byte, 1U, Comms_RxByteCb);
}

/* ── TX helper — only writes when VCP owns the channel ──────────────────── */

static void Comms_Tx(const uint8_t *buf, uint16_t n)
{
    if (!s_channel_vcp) { return; }
    (void)HW_UART_Transmit(hw_uart1, (uint8_t *)buf, n, 10U);
}

/* ── RX frame parser ────────────────────────────────────────────────────── */

typedef enum { P_SOF1, P_SOF2, P_BODY } ParseState_t;

static void Comms_ProcessRx(void)
{
    static uint8_t      frame_buf[FRAME_BUF_SIZE];
    static uint16_t     frame_pos   = 0U;
    static uint16_t     frame_total = 0U;
    static ParseState_t state       = P_SOF1;

    while (s_rx_tail != s_rx_head) {
        uint8_t b = (uint8_t)s_rx_ring[s_rx_tail];
        s_rx_tail = (s_rx_tail + 1U) & (RX_RING_SIZE - 1U);

        switch (state) {
        case P_SOF1:
            if (b == VCP_SOF1) {
                frame_buf[0] = b;
                frame_pos    = 1U;
                state        = P_SOF2;
            }
            break;

        case P_SOF2:
            if (b == VCP_SOF2) {
                frame_buf[1] = b;
                frame_pos    = 2U;
                frame_total  = 0U;
                state        = P_BODY;
            } else {
                state     = P_SOF1;
                frame_pos = 0U;
            }
            break;

        case P_BODY:
            if (frame_pos < FRAME_BUF_SIZE) {
                frame_buf[frame_pos++] = b;
            } else {
                state       = P_SOF1;
                frame_pos   = 0U;
                frame_total = 0U;
                break;
            }
            if (frame_pos == 8U && frame_total == 0U) {
                uint16_t plen = (uint16_t)frame_buf[6]
                              | ((uint16_t)frame_buf[7] << 8);
                if (plen > (uint16_t)(FRAME_BUF_SIZE - 11U)) {
                    state       = P_SOF1;
                    frame_pos   = 0U;
                    frame_total = 0U;
                } else {
                    frame_total = 11U + plen;
                }
            }
            if (frame_total > 0U && frame_pos == frame_total) {
                VcpPacket_t pkt;
                if (VcpProtocol_Parse(frame_buf, frame_pos, &pkt) == 0) {
                    Comms_Dispatch(&pkt);
                }
                state       = P_SOF1;
                frame_pos   = 0U;
                frame_total = 0U;
            }
            break;
        }
    }
}

/* ── Command dispatcher ─────────────────────────────────────────────────── */

static void Comms_Dispatch(const VcpPacket_t *pkt)
{
    /* Any valid command means app-cbc-tuning is talking → take the channel. */
    s_channel_vcp = 1U;

    switch (pkt->type) {

    case VCP_TYPE_CMD_SET_GAINS: {
        if (pkt->len < (uint16_t)sizeof(VcpCmdSetGains_t)) { break; }
        VcpCmdSetGains_t cmd;
        memcpy(&cmd, pkt->payload, sizeof(cmd));
        if (cmd.motor_id == 0U || cmd.motor_id == 2U) {
            MTR_SetVelocityGains(MTR_LEFT,  cmd.kp, cmd.ki, cmd.kd);
        }
        if (cmd.motor_id == 1U || cmd.motor_id == 2U) {
            MTR_SetVelocityGains(MTR_RIGHT, cmd.kp, cmd.ki, cmd.kd);
        }
        Comms_SendAck(VCP_TYPE_CMD_SET_GAINS, 0U);
        break;
    }

    case VCP_TYPE_CMD_SET_SP: {
        if (pkt->len < (uint16_t)sizeof(VcpCmdSetSp_t)) { break; }
        VcpCmdSetSp_t cmd;
        memcpy(&cmd, pkt->payload, sizeof(cmd));
        Task_control_SetVelocitySetpoint((float)cmd.sp_rpm);
        Comms_SendAck(VCP_TYPE_CMD_SET_SP, 0U);
        break;
    }

    case VCP_TYPE_CMD_STREAM_CTRL: {
        if (pkt->len < (uint16_t)sizeof(VcpCmdStreamCtrl_t)) { break; }
        VcpCmdStreamCtrl_t cmd;
        memcpy(&cmd, pkt->payload, sizeof(cmd));
        s_stream_active = cmd.enable ? 1U : 0U;
        if (cmd.rate_hz > 0U && cmd.rate_hz <= STREAM_RATE_MAX_HZ) {
            s_stream_rate_hz = cmd.rate_hz;
        } else {
            s_stream_rate_hz = STREAM_RATE_DEFAULT_HZ;
        }
        Comms_SendAck(VCP_TYPE_CMD_STREAM_CTRL, 0U);
        break;
    }

    case VCP_TYPE_CMD_SET_BALANCE_GAINS: {
        if (pkt->len < (uint16_t)sizeof(VcpCmdSetBalanceGains_t)) { break; }
        VcpCmdSetBalanceGains_t cmd;
        memcpy(&cmd, pkt->payload, sizeof(cmd));
        Task_control_SetBalanceGains(cmd.loop_id, cmd.kp, cmd.ki, cmd.kd);
        Comms_SendAck(VCP_TYPE_CMD_SET_BALANCE_GAINS, 0U);
        break;
    }

    case VCP_TYPE_CMD_MOTOR_CTRL: {
        if (pkt->len < (uint16_t)sizeof(VcpCmdMotorCtrl_t)) { break; }
        VcpCmdMotorCtrl_t cmd;
        memcpy(&cmd, pkt->payload, sizeof(cmd));
        switch (cmd.action) {
        case VCP_MOTOR_COAST:
            MTR_Coast(MTR_LEFT);
            MTR_Coast(MTR_RIGHT);
            break;
        case VCP_MOTOR_BRAKE:
            MTR_Brake(MTR_LEFT);
            MTR_Brake(MTR_RIGHT);
            break;
        case VCP_MOTOR_ENABLE:
            MTR_SetControlMode(MTR_LEFT,  MTR_MODE_VELOCITY);
            MTR_SetControlMode(MTR_RIGHT, MTR_MODE_VELOCITY);
            break;
        default:
            break;
        }
        Comms_SendAck(VCP_TYPE_CMD_MOTOR_CTRL, 0U);
        break;
    }

    case VCP_TYPE_CMD_SET_ANGLE_SP: {
        if (pkt->len < (uint16_t)sizeof(VcpCmdSetAngleSp_t)) { break; }
        VcpCmdSetAngleSp_t cmd;
        memcpy(&cmd, pkt->payload, sizeof(cmd));
        Task_control_SetAngleOffset(cmd.offset_deg);
        Comms_SendAck(VCP_TYPE_CMD_SET_ANGLE_SP, 0U);
        break;
    }

    default:
        /* Unsupported in the light scope (pos / spin / calib / direct drive) */
        break;
    }
}

/* ── Telemetry senders ──────────────────────────────────────────────────── */

/* VcpTelPid_t mapping (cascade mode):
 *   sp_rpm : velocity setpoint | pv_l/r : wheel RPM
 *   err_l  : target_pitch_deg × 100 (outer → inner) | err_r : 0
 *   pwm_l/r: motor drive output × 100 */
static void Comms_SendPidTelemetry(const ControlState_t *cs)
{
    VcpTelPid_t tel;
    tel.timestamp_ms = xTaskGetTickCount();
    tel.sp_rpm       = (int16_t)cs->target_vel_rpm;
    tel.pv_l_rpm     = (int16_t)cs->vel_l_rpm;
    tel.pv_r_rpm     = (int16_t)cs->vel_r_rpm;
    tel.err_l        = (int16_t)(cs->target_pitch_deg * 100.0f);
    tel.err_r        = 0;
    tel.pwm_l_x100   = (int16_t)(cs->left_output  * 100.0f);
    tel.pwm_r_x100   = (int16_t)(cs->right_output * 100.0f);

    uint8_t tx_buf[TX_BUF_SIZE];
    VcpPacket_t pkt = { VCP_TYPE_TELEMETRY_PID, 0U, s_tx_seq++,
                        (uint16_t)sizeof(tel), (uint8_t *)&tel };
    int n = VcpProtocol_Frame(&pkt, tx_buf, sizeof(tx_buf));
    if (n > 0) { Comms_Tx(tx_buf, (uint16_t)n); }
}

static void Comms_SendImuTelemetry(const ControlState_t *cs)
{
    VcpTelImu_t tel;
    tel.timestamp_ms = xTaskGetTickCount();
    tel.accel_x_mg   = (int16_t)(cs->accel_x_g  * 1000.0f);
    tel.accel_y_mg   = (int16_t)(cs->accel_y_g  * 1000.0f);
    tel.accel_z_mg   = (int16_t)(cs->accel_z_g  * 1000.0f);
    tel.gyro_x_x100  = (int16_t)(cs->gyro_x_dps * 100.0f);
    tel.gyro_y_x100  = (int16_t)(cs->gyro_y_dps * 100.0f);
    tel.gyro_z_x100  = (int16_t)(cs->gyro_z_dps * 100.0f);
    tel.pitch_x100   = (int16_t)(cs->pitch_deg    * 100.0f);
    tel.drive_x100   = (int16_t)(cs->drive_output * 100.0f);

    uint8_t tx_buf[TX_BUF_SIZE];
    VcpPacket_t pkt = { VCP_TYPE_TELEMETRY_IMU, 0U, s_tx_seq++,
                        (uint16_t)sizeof(tel), (uint8_t *)&tel };
    int n = VcpProtocol_Frame(&pkt, tx_buf, sizeof(tx_buf));
    if (n > 0) { Comms_Tx(tx_buf, (uint16_t)n); }
}

static void Comms_SendAck(uint8_t cmd_type, uint8_t status)
{
    VcpAck_t ack = { cmd_type, status };
    uint8_t  tx_buf[TX_BUF_SIZE];
    VcpPacket_t pkt = { VCP_TYPE_ACK, 0U, s_tx_seq++,
                        (uint16_t)sizeof(ack), (uint8_t *)&ack };
    int n = VcpProtocol_Frame(&pkt, tx_buf, sizeof(tx_buf));
    if (n > 0) { Comms_Tx(tx_buf, (uint16_t)n); }
}

/* ── FreeRTOS task ──────────────────────────────────────────────────────── */

static void CommsTask(void *pvParameters)
{
    (void)pvParameters;

    /* Arm single-byte RX through the ST hw_uart layer */
    HW_UART_Receive_IT(hw_uart1, &s_rx_byte, 1U, Comms_RxByteCb);

    uint32_t last_tel_ms = 0U;

    for (;;) {
        Comms_ProcessRx();

        if (s_channel_vcp && s_stream_active) {
            uint32_t now      = xTaskGetTickCount();
            uint32_t interval = 1000U / (uint32_t)s_stream_rate_hz;
            if ((now - last_tel_ms) >= interval) {
                last_tel_ms = now;
                ControlState_t cs;
                Task_control_GetState(&cs);
                Comms_SendImuTelemetry(&cs);
                Comms_SendPidTelemetry(&cs);
            }
        }

        vTaskDelay(pdMS_TO_TICKS(2U));
    }
}
