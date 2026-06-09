/*
 * task_comms.c — VCP telemetry + PID tuning command handler
 *
 * Uplink  (STM32 → PC) : VCP_TYPE_TELEMETRY_PID at configurable rate (1–100 Hz)
 * Downlink (PC → STM32) : SET_GAINS, SET_SP, STREAM_CTRL, MOTOR_CTRL
 *
 * UART RX is byte-at-a-time interrupt-driven into a 256-byte ring buffer.
 * Task polls the buffer every 2 ms, assembles frames, dispatches commands.
 * TX uses blocking HAL_UART_Transmit (small frames, < 3 ms at 115200).
 */

#include "task_comms.h"
#include "task_control.h"
#include "vcp_protocol.h"
#include "motor_control.h"
#include "FreeRTOS.h"
#include "task.h"
#include "main.h"          /* huart1 declared here */
#include <string.h>

/* ── Constants ──────────────────────────────────────────────────────────── */
#define COMMS_TASK_STACK_SIZE  384U
#define COMMS_TASK_PRIORITY    (tskIDLE_PRIORITY + 2U)

#define RX_RING_SIZE    256U   /* must be power-of-2 */
#define FRAME_BUF_SIZE   64U   /* max frame bytes we handle */
#define TX_BUF_SIZE      64U

#define STREAM_RATE_DEFAULT_HZ  50U
#define STREAM_RATE_MAX_HZ     100U

/* ── Shared state (written by comms task, read by display task) ─────────── */
static volatile uint8_t  s_stream_active    = 0U;
static volatile uint16_t s_stream_rate_hz   = STREAM_RATE_DEFAULT_HZ;
static volatile uint32_t s_last_cmd_tick    = 0U;
static volatile int16_t  s_vcp_sp_rpm       = 0;

/* RPM override: SET_SP command active within the last 500 ms */
#define RPM_OVERRIDE_TIMEOUT_MS  500U
static volatile uint8_t  s_rpm_override_active = 0U;
static volatile uint32_t s_rpm_override_ts     = 0U;

/* ── UART RX ring buffer (ISR → task) ───────────────────────────────────── */
static volatile uint8_t  s_rx_ring[RX_RING_SIZE];
static volatile uint16_t s_rx_head = 0U;   /* written by ISR  */
static volatile uint16_t s_rx_tail = 0U;   /* read   by task  */
static          uint8_t  s_rx_byte;         /* HAL_UART_Receive_IT target */

/* ── TX sequence counter ────────────────────────────────────────────────── */
static uint8_t s_tx_seq = 0U;

/* ── Forward declarations ───────────────────────────────────────────────── */
static void CommsTask(void *pvParameters);
static void Comms_ProcessRx(void);
static void Comms_Dispatch(const VcpPacket_t *pkt);
static void Comms_SendTelemetry(void);
static void Comms_SendAck(uint8_t cmd_type, uint8_t status);
static void Comms_SendImuTelemetry(void);
static void Comms_SendCalibTelemetry(const ControlState_t *cs);

/* ── Public API ─────────────────────────────────────────────────────────── */

void Task_comms_Init(void)
{
    xTaskCreate(CommsTask, "Comms", COMMS_TASK_STACK_SIZE, NULL,
                COMMS_TASK_PRIORITY, NULL);
}

void VCP_NotifyRxByte(uint8_t byte)
{
    uint16_t next = (s_rx_head + 1U) & (RX_RING_SIZE - 1U);
    if (next != s_rx_tail) {
        s_rx_ring[s_rx_head] = byte;
        s_rx_head = next;
    }
    /* If ring is full the byte is silently dropped */
}

uint8_t VCP_IsStreamActive(void)   { return s_stream_active; }
uint32_t VCP_GetLastCmdTick(void)  { return s_last_cmd_tick; }
int16_t  VCP_GetSetpointRpm(void)  { return s_vcp_sp_rpm; }

uint8_t VCP_IsRpmOverrideActive(void)
{
    if (!s_rpm_override_active) { return 0U; }
    if ((HAL_GetTick() - s_rpm_override_ts) > RPM_OVERRIDE_TIMEOUT_MS) {
        s_rpm_override_active = 0U;
        return 0U;
    }
    return 1U;
}

void VCP_SetStreamActive(uint8_t enable)
{
    s_stream_active = enable ? 1U : 0U;
}

/* ── HAL callback — overrides weak symbol, called from USART1_IRQHandler ── */

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    extern UART_HandleTypeDef huart1;
    if (huart->Instance == USART1) {
        VCP_NotifyRxByte(s_rx_byte);
        HAL_UART_Receive_IT(&huart1, &s_rx_byte, 1U);   /* re-arm */
    }
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
            /* Once we have the 8-byte header, compute expected total length */
            if (frame_pos == 8U && frame_total == 0U) {
                uint16_t plen = (uint16_t)frame_buf[6]
                              | ((uint16_t)frame_buf[7] << 8);
                if (plen > (uint16_t)(FRAME_BUF_SIZE - 11U)) {
                    state       = P_SOF1;
                    frame_pos   = 0U;
                    frame_total = 0U;
                } else {
                    /* SOF(2) + HDR(6) + PAYLOAD(plen) + CRC(2) + EOF(1) */
                    frame_total = 11U + plen;
                }
            }
            /* Complete frame? */
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
    s_last_cmd_tick = HAL_GetTick();

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
        s_vcp_sp_rpm          = cmd.sp_rpm;
        s_rpm_override_active = 1U;
        s_rpm_override_ts     = HAL_GetTick();
        /* Actual drive applied by control task (sees VCP_IsRpmOverrideActive). */
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

    case VCP_TYPE_CMD_MOTOR_CALIB: {
        if (pkt->len < (uint16_t)sizeof(VcpCmdMotorCalib_t)) { break; }
        VcpCmdMotorCalib_t cmd;
        memcpy(&cmd, pkt->payload, sizeof(cmd));
        if (cmd.enable) {
            Task_control_StartCalib();
        } else {
            Task_control_AbortCalib();
        }
        Comms_SendAck(VCP_TYPE_CMD_MOTOR_CALIB, 0U);
        break;
    }

    default:
        break;
    }
}

/* ── Telemetry sender ───────────────────────────────────────────────────── */

static void Comms_SendTelemetry(void)
{
    extern UART_HandleTypeDef huart1;

    float pv_l = MTR_GetCachedVelocityRPM(MTR_LEFT);
    float pv_r = MTR_GetCachedVelocityRPM(MTR_RIGHT);

    VcpTelPid_t tel;
    tel.timestamp_ms = HAL_GetTick();
    tel.sp_rpm       = s_vcp_sp_rpm;
    tel.pv_l_rpm     = (int16_t)pv_l;
    tel.pv_r_rpm     = (int16_t)pv_r;
    tel.err_l        = s_vcp_sp_rpm - (int16_t)pv_l;
    tel.err_r        = s_vcp_sp_rpm - (int16_t)pv_r;
    tel.pwm_l_x100   = (int16_t)(MTR_GetLastPwmOutput(MTR_LEFT)  * 100.0f);
    tel.pwm_r_x100   = (int16_t)(MTR_GetLastPwmOutput(MTR_RIGHT) * 100.0f);

    uint8_t tx_buf[TX_BUF_SIZE];
    VcpPacket_t pkt;
    pkt.type    = VCP_TYPE_TELEMETRY_PID;
    pkt.flags   = 0U;
    pkt.seq     = s_tx_seq++;
    pkt.len     = (uint16_t)sizeof(VcpTelPid_t);
    pkt.payload = (uint8_t *)&tel;

    int n = VcpProtocol_Frame(&pkt, tx_buf, sizeof(tx_buf));
    if (n > 0) {
        HAL_UART_Transmit(&huart1, tx_buf, (uint16_t)n, 10U);
    }
}

static void Comms_SendImuTelemetry(void)
{
    extern UART_HandleTypeDef huart1;

    ControlState_t cs;
    Task_control_GetState(&cs);

    VcpTelImu_t tel;
    tel.timestamp_ms = HAL_GetTick();
    tel.accel_x_mg   = (int16_t)(cs.accel_x_g  * 1000.0f);
    tel.accel_y_mg   = (int16_t)(cs.accel_y_g  * 1000.0f);
    tel.accel_z_mg   = (int16_t)(cs.accel_z_g  * 1000.0f);
    tel.gyro_x_x100  = (int16_t)(cs.gyro_x_dps * 100.0f);
    tel.gyro_y_x100  = (int16_t)(cs.gyro_y_dps * 100.0f);
    tel.gyro_z_x100  = (int16_t)(cs.gyro_z_dps * 100.0f);
    tel.pitch_x100   = (int16_t)(cs.pitch_deg    * 100.0f);
    tel.drive_x100   = (int16_t)(cs.drive_output * 100.0f);

    uint8_t tx_buf[TX_BUF_SIZE];
    VcpPacket_t pkt;
    pkt.type    = VCP_TYPE_TELEMETRY_IMU;
    pkt.flags   = 0U;
    pkt.seq     = s_tx_seq++;
    pkt.len     = (uint16_t)sizeof(VcpTelImu_t);
    pkt.payload = (uint8_t *)&tel;

    int n = VcpProtocol_Frame(&pkt, tx_buf, sizeof(tx_buf));
    if (n > 0) {
        HAL_UART_Transmit(&huart1, tx_buf, (uint16_t)n, 10U);
    }
}

static void Comms_SendCalibTelemetry(const ControlState_t *cs)
{
    extern UART_HandleTypeDef huart1;

    VcpTelCalib_t tel;
    tel.timestamp_ms = HAL_GetTick();
    tel.drive_x1000  = (int16_t)(cs->drive_output * 1000.0f);
    tel.vel_l_rpm    = (int16_t)cs->vel_l_rpm;
    tel.vel_r_rpm    = (int16_t)cs->vel_r_rpm;
    tel.phase        = cs->calib_phase;
    tel.calib_active = cs->calib_active;

    uint8_t tx_buf[TX_BUF_SIZE];
    VcpPacket_t pkt;
    pkt.type    = VCP_TYPE_TELEMETRY_CALIB;
    pkt.flags   = 0U;
    pkt.seq     = s_tx_seq++;
    pkt.len     = (uint16_t)sizeof(VcpTelCalib_t);
    pkt.payload = (uint8_t *)&tel;

    int n = VcpProtocol_Frame(&pkt, tx_buf, sizeof(tx_buf));
    if (n > 0) {
        HAL_UART_Transmit(&huart1, tx_buf, (uint16_t)n, 10U);
    }
}

static void Comms_SendAck(uint8_t cmd_type, uint8_t status)
{
    extern UART_HandleTypeDef huart1;

    VcpAck_t ack = { cmd_type, status };
    uint8_t  tx_buf[TX_BUF_SIZE];
    VcpPacket_t pkt;
    pkt.type    = VCP_TYPE_ACK;
    pkt.flags   = 0U;
    pkt.seq     = s_tx_seq++;
    pkt.len     = (uint16_t)sizeof(VcpAck_t);
    pkt.payload = (uint8_t *)&ack;

    int n = VcpProtocol_Frame(&pkt, tx_buf, sizeof(tx_buf));
    if (n > 0) {
        HAL_UART_Transmit(&huart1, tx_buf, (uint16_t)n, 5U);
    }
}

/* ── FreeRTOS task ──────────────────────────────────────────────────────── */

static void CommsTask(void *pvParameters)
{
    (void)pvParameters;

    extern UART_HandleTypeDef huart1;
    HAL_UART_Receive_IT(&huart1, &s_rx_byte, 1U);   /* arm first RX */

    uint32_t last_tel_ms   = 0U;
    uint32_t last_calib_ms = 0U;
    uint8_t  prev_calib    = 0U;

    for (;;) {
        Comms_ProcessRx();

        uint32_t now = HAL_GetTick();

        ControlState_t cs;
        Task_control_GetState(&cs);

        /* Calibration telemetry — 100 Hz while running, one EOF packet on completion. */
        if (cs.calib_active) {
            if ((now - last_calib_ms) >= 10U) {
                last_calib_ms = now;
                Comms_SendCalibTelemetry(&cs);
            }
        } else if (prev_calib) {
            /* Transition 1→0 : send exactly one EOF packet (no rate limit) */
            Comms_SendCalibTelemetry(&cs);   /* calib_active==0 = done marker */
        }
        prev_calib = cs.calib_active;

        /* Normal telemetry — only when streaming enabled and not calibrating */
        if (s_stream_active && !cs.calib_active) {
            uint32_t interval = 1000U / (uint32_t)s_stream_rate_hz;
            if ((now - last_tel_ms) >= interval) {
                last_tel_ms = now;
                Comms_SendTelemetry();
                Comms_SendImuTelemetry();
            }
        }

        vTaskDelay(pdMS_TO_TICKS(2U));
    }
}
