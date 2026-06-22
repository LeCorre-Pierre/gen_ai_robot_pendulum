# BLE Firmware — Vision

This directory contains the BLE firmware module for the robot pendulum. It will be developed as a standalone CubeIDE project first, it replace the existing main firmware (`emb-sw/`).

The full Android ↔ BLE ↔ STM32 contract is defined in `10-android-app-architecture.md`. This document covers only the firmware side.

---

## Role

The STM32WB5MMG has two cores:
- **Cortex-M4** — runs the application (FreeRTOS, control loop, BLE app logic)
- **Cortex-M0+** — runs the ST BLE stack autonomously, communicates with M4 via IPCC

The BLE firmware module lives entirely on the **M4 side**. It registers a custom GATT server, handles write events from the Android app (commands), and sends telemetry notifications to the app. It does not touch the control loop directly — it communicates with `task_control` and `task_comms` via FreeRTOS queues.

---

## Starting Point

Two ST examples from STM32CubeWB, both available as CubeMX projects for the **STM32WB5MM-DK (MB1292B)**:

| Example | What we take from it |
|---|---|
| **BLE_p2pServer** (../references/BLE_p2pServer) | GATT server structure, Write + Notify characteristic pattern, `custom_stm.c` template |
| **BLE_Sensor** (../references/BLE_Sensor) | CubeMX board configuration for MB1292B (IPCC, RTC, HSE/LSE, M0+ flash offset) |
| **BLE_HeartRateFreeRTOS** (../references/BLE_HeartRateFreeRTOS) | FreeRTOS integration, BLE event pump task, queue-based command dispatch |

**Do not adopt BLE_Sensor's GATT profile** (ST proprietary sensor UUIDs). Use it only for the `.ioc` / board-level config.

Procedure:
Creation of an entire firmware project in the directory `emb-sw-ble/`.

1. Start from **BLE_Sensor** — it is the only example targeting our exact board (STM32WB5MM-DK / MB1292B). It provides the correct CubeMX configuration: IPCC, RTC, HSE/LSE clocks, M0+ flash offset.
 - Copy source code and headers from `BLE_Sensor` into `emb-sw-ble/`
 - Copy libraries from `emb-sw` if possible and required
 - Search in `C:\ST\STM32CubeWB` if required libraries are not found in `emb-sw`
 - Ask me if you have any problem with libraries
 - Ensure that the project compiles and runs on the MB1292B board (verify advertising and phone can connect). This requires manual verification. Do not rely on CubeMX.
2. Graft the FreeRTOS integration patterns from **BLE_HeartRateFreeRTOS** onto the existing files in `emb-sw-ble/` (BLE event pump task, queue-based dispatch).
 - Note: BLE_HeartRateFreeRTOS targets Nucleo, not MB1292B — use it as a code reference only, do not copy board-level init from it.
 - Ensure that the project still compiles and runs on the MB1292B board. This requires manual verification.
3. Graft the GATT server structure from **BLE_p2pServer** onto the existing files in `emb-sw-ble/` to implement the Robot Service and characteristics (Command + Telemetry) with the UUIDs defined below.
 - Ensure that the project compiles and runs on the MB1292B board (verify advertising, service discovery, and phone can connect). This requires manual verification.
4. Port the robot/pendulum logic from `emb-sw` into `emb-sw-ble/`: control tasks, motor drivers, IMU, encoders, safety layer.
 - Ensure that the full system compiles and runs on the MB1292B board. This requires manual verification.

---

## GATT Profile

### Advertising

```c
#define ROBOT_LOCAL_NAME        "RobotPendulum"
#define ADV_INTERVAL_FAST_MS    100   // before first bond
#define ADV_INTERVAL_SLOW_MS    1000  // after bond established
```

### Services and Characteristics

One custom service, two characteristics. UUIDs are 128-bit, little-endian in the ST BLE API.

```c
/* Robot Service */
#define ROBOT_SERVICE_UUID   0x01,0x00,0x00,0x00,0x00,0x00,0x00,0x80, \
                             0x00,0x40,0x00,0xC0,0xB0,0xA0,0x00,0x00  // A0B00001-C000-4000-8000-000000000001

/* Command Characteristic — Write Without Response, App → Robot */
#define ROBOT_CMD_UUID       0x02,0x00,0x00,0x00,0x00,0x00,0x00,0x80, \
                             0x00,0x40,0x00,0xC0,0xB0,0xA0,0x00,0x00  // A0B00002-C000-4000-8000-000000000001

/* Telemetry Characteristic — Notify, Robot → App */
#define ROBOT_TELEM_UUID     0x03,0x00,0x00,0x00,0x00,0x00,0x00,0x80, \
                             0x00,0x40,0x00,0xC0,0xB0,0xA0,0x00,0x00  // A0B00003-C000-4000-8000-000000000001
```

Characteristic properties:
- **Command**: `CHAR_PROP_WRITE_WITHOUT_RESP`, max length 8 bytes, no encryption required
- **Telemetry**: `CHAR_PROP_NOTIFY`, fixed length 11 bytes, CCCD descriptor required

---

## Binary Protocol

Full specification in `10-android-app-architecture.md §Binary Protocols`. Summary:

### Command Frame (received, max 8 bytes)

```
[CMD_ID: uint8] [PAYLOAD: 0–7 bytes]
```

| CMD_ID | Meaning | Payload |
|---|---|---|
| `0x01` | DRIVE | `speed: int8 [-100,+100], turn: int8 [-100,+100]` |
| `0x02` | EMERGENCY_STOP | _(none)_ |
| `0x03` | RESUME | _(none)_ |
| `0x04` | DEMO_AUTO_SPIN | `repeat_interval_s: uint8` |
| `0x05` | DEMO_BACK_FORTH | `distance_cm: uint8 [1-100], speed_level: uint8 [0-2]` |
| `0x06` | DEMO_SINUS_SWEEP | `width: uint8, period_ds: uint8` |
| `0x07` | DEMO_STOP | _(none)_ |

### Telemetry Frame (sent, 11 bytes, little-endian)

```c
typedef struct __packed {
    uint8_t  seq;        // wrapping counter, detects missed notifications
    uint8_t  flags;      // bitfield — see below
    int16_t  pitch;      // pitch_deg × 100  (0.01° resolution)
    int16_t  speed_l;    // left wheel RPM × 10
    int16_t  speed_r;    // right wheel RPM × 10
    int8_t   drive;      // normalized motor cmd × 100  (-1.0 → -100)
    uint16_t batt_mv;    // battery voltage in millivolts
} RobotTelemetryFrame_t;
```

FLAGS bitfield:
```c
#define FLAG_BALANCE_ACTIVE  (1 << 0)  // control loop running
#define FLAG_SAFETY_CUTOFF   (1 << 1)  // robot tipped, motors off
#define FLAG_DEMO_RUNNING    (1 << 2)  // demo command executing
#define FLAG_ESTOP_ACTIVE    (1 << 3)  // e-stop commanded, awaiting RESUME
```

---

## Integration with FreeRTOS Tasks

The BLE module does not implement application logic. It is a transport layer.

```
Android app
    │ BLE Write (Command characteristic)
    ▼
SVCCTL_App_Notification()           ← ST BLE event callback (M4, not in a task)
    │ parse CMD_ID
    │ xQueueSend(xBleCommandQueue, &cmd, 0)
    ▼
task_comms  OR  task_control        ← consumes queue, applies command
```

```
task_comms (200 Hz tick, or dedicated BLE timer at 20 Hz)
    │ read current state from task_control shared struct
    │ fill RobotTelemetryFrame_t
    │ Robot_STM_App_Update_Char(TELEMETRY_CHAR, frame, sizeof(frame))
    ▼
ST BLE stack → BLE notification → Android app
```

**Telemetry rate:** send a notification every 50 ms (20 Hz). The control loop runs at 200 Hz; `task_comms` decimates by 10 before sending. Do not send a notification on every control tick — it saturates the BLE link.

**Safety on disconnect:** the ST BLE stack fires `HCI_DISCONNECTION_COMPLETE_EVT` on the M4. The handler sets an `estop_from_ble` flag readable by `task_control`. This is the firmware enforcement of the 200 ms BLE timeout already in the safety layer.

---

## File Structure (target)

Modelled on BLE_p2pServer, adapted for our service:

```
emb-sw-ble/
├── Core/
│   ├── Src/main.c                      — board init, starts scheduler
│   └── Inc/
├── STM32_WPAN/
│   └── App/
│       ├── robot_stm.c / .h            — GATT service registration (replaces p2p_stm.c)
│       ├── robot_app.c / .h            — command dispatch, telemetry send (replaces p2p_server_app.c)
│       └── ble_conf.h                  — BLE stack config (max connections, ATT MTU, etc.)
├── App/
│   └── robot_ble_task.c / .h          — FreeRTOS task wrapper (BLE event pump)
└── emb-sw-ble.ioc                     — CubeMX project (from BLE_Sensor board config)
```

---

## Key Configuration Parameters

```c
/* ble_conf.h */
#define CFG_BLE_NUM_GATT_SERVICES       2   // Robot Service + Generic Attribute
#define CFG_BLE_NUM_GATT_ATTRIBUTES     8   // ~4 per characteristic (value + CCCD + ...)
#define CFG_BLE_MAX_ATT_MTU             128 // app requests 128; stack may negotiate lower
#define CFG_BLE_NUM_LINK                1   // single connection only

/* Connection parameters accepted from central (Android) */
#define CONN_INTERVAL_MIN_MS            15  // 12 × 1.25 ms
#define CONN_INTERVAL_MAX_MS            30  // 24 × 1.25 ms
#define SLAVE_LATENCY                   0
#define SUPERVISION_TIMEOUT_MS          2000
```

A 15–30 ms connection interval gives ample bandwidth for 20 Hz telemetry notifications (11 bytes) plus 20 Hz command writes (3 bytes), with headroom for retransmissions.

---

## Validation Milestones

| Step | What to verify manually on the board |
|---|---|
| After step 1 | Board advertises `"RobotPendulum"`, phone can see it and connect via nRF Connect or LightBlue |
| After step 2 | FreeRTOS scheduler starts, BLE event pump task runs, connection still works |
| After step 3 | nRF Connect shows Robot Service UUID, Command and Telemetry characteristics visible, DRIVE command write accepted, synthetic telemetry notification received at 20 Hz |
| After step 4 | Full robot system runs: balance loop active, real pitch/speed in telemetry, DRIVE command moves motors, EMERGENCY_STOP and disconnect cut motors |
