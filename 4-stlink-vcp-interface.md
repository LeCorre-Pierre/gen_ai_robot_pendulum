# ST-Link VCP Interface Specification

**Version:** 0.1  
**Date:** 2026-03-21  
**Target:** MB1292B STM32WB5MMG firmware <-> PC GUI over ST-Link Virtual COM Port (`USART1`, `PB6/PB7`)

---

## 1. Purpose

This interface is dedicated to:

- bring-up and board validation
- control-loop debug
- real-time telemetry plotting
- PID tuning
- sensor and actuator diagnosis
- fault analysis
- capture and export of trace data for offline analysis

It is **not** the production tuning channel. The project already keeps:

- `BLE` for smartphone driving
- `LPUART1` for Raspberry Pi bridge / WiFi tuning
- `USART1` over ST-Link VCP for wired PC engineering tools

This document defines the PC-facing debug/tuning protocol that a future GUI can use directly.

---

## 2. Recommendation

Use **one framed binary protocol only** on the ST-Link VCP.

Do **not** mix:

- raw `printf` text
- ad hoc CSV lines
- binary frames

on the same UART stream.

Instead:

- all structured data is sent as framed packets
- human-readable logs are carried inside a dedicated `LOG_TEXT` packet

This makes the GUI simpler, avoids parser desynchronization, and keeps CSV export possible on the PC side.

---

## 3. Transport

### 3.1 Physical link

- Transport: ST-Link Virtual COM Port
- MCU peripheral: `USART1`
- Pins: `PB6` TX / `PB7` RX
- Default baudrate: `115200`
- Frame format: `8N1`

### 3.2 Framing

Each packet uses the same envelope:

```text
SOF1 SOF2 VER TYPE FLAGS SEQ LEN_L LEN_H PAYLOAD... CRC_L CRC_H EOF
```

### 3.3 Field definitions

| Field | Size | Description |
|---|---:|---|
| `SOF1` | 1 | `0xAA` |
| `SOF2` | 1 | `0x55` |
| `VER` | 1 | protocol version, initial value `0x01` |
| `TYPE` | 1 | message type |
| `FLAGS` | 1 | ack/error/stream flags |
| `SEQ` | 1 | host or device sequence counter |
| `LEN` | 2 | payload length in bytes, little-endian |
| `PAYLOAD` | N | message body |
| `CRC16` | 2 | CRC16-CCITT over `VER..PAYLOAD` |
| `EOF` | 1 | `0x33` |

### 3.4 Design notes

- little-endian for all numeric values
- fixed-width numeric types only
- no floats in text form
- no packet larger than `256 bytes` in V1
- host must ignore unknown message types
- device must reply with `NACK` on malformed writable requests

---

## 4. Session model

### 4.1 Startup flow

1. PC opens COM port.
2. PC sends `PING`.
3. STM32 replies with `PONG`.
4. PC sends `GET_DEVICE_INFO`.
5. STM32 replies with firmware identity and capability bitmap.
6. PC sends `GET_PARAMETER_TABLE`.
7. PC optionally enables telemetry streams.

### 4.2 Modes

The GUI should handle these device modes:

- `BOOT`
- `IDLE`
- `ARMED`
- `BALANCING`
- `FAULT`
- `CALIBRATION`
- `TEST`

---

## 5. Message families

| Family | Direction | Goal |
|---|---|---|
| Link / discovery | bidirectional | identify device and capabilities |
| Telemetry | STM32 -> PC | plot and log real-time state |
| Parameters | bidirectional | read/write tunable values |
| Commands | PC -> STM32 | request actions or tests |
| Events / faults | STM32 -> PC | async warnings and failures |
| Logs | STM32 -> PC | human-readable debug traces |
| Capture | bidirectional | buffered snapshot acquisition |

---

## 6. Core messages

### 6.1 Link / discovery

| Type | Name | Direction | Payload |
|---|---|---|---|
| `0x01` | `PING` | PC -> STM32 | empty |
| `0x02` | `PONG` | STM32 -> PC | uptime, protocol version |
| `0x03` | `GET_DEVICE_INFO` | PC -> STM32 | empty |
| `0x04` | `DEVICE_INFO` | STM32 -> PC | IDs and capability bitmap |
| `0x05` | `ACK` | STM32 -> PC | acked type + seq |
| `0x06` | `NACK` | STM32 -> PC | failed type + error code |

### 6.2 Telemetry control

| Type | Name | Direction | Payload |
|---|---|---|---|
| `0x10` | `SET_STREAM_CONFIG` | PC -> STM32 | stream ID, enable, period |
| `0x11` | `GET_STREAM_CONFIG` | PC -> STM32 | stream ID |
| `0x12` | `STREAM_CONFIG` | STM32 -> PC | stream ID, state, period |
| `0x13` | `TELEMETRY_SAMPLE` | STM32 -> PC | sample packet |
| `0x14` | `TELEMETRY_BURST` | STM32 -> PC | compact multi-sample packet |

### 6.3 Parameter access

| Type | Name | Direction | Payload |
|---|---|---|---|
| `0x20` | `GET_PARAMETER_TABLE` | PC -> STM32 | empty |
| `0x21` | `PARAMETER_TABLE` | STM32 -> PC | parameter descriptors |
| `0x22` | `READ_PARAMETER` | PC -> STM32 | parameter ID |
| `0x23` | `WRITE_PARAMETER` | PC -> STM32 | parameter ID + value |
| `0x24` | `PARAMETER_VALUE` | STM32 -> PC | parameter ID + value |
| `0x25` | `SAVE_PARAMETERS` | PC -> STM32 | empty |
| `0x26` | `LOAD_PARAMETERS` | PC -> STM32 | profile slot or defaults |

### 6.4 Commands

| Type | Name | Direction | Payload |
|---|---|---|---|
| `0x30` | `SET_CONTROL_MODE` | PC -> STM32 | target mode |
| `0x31` | `SET_MANUAL_COMMAND` | PC -> STM32 | forward/turn command |
| `0x32` | `EMERGENCY_STOP` | PC -> STM32 | reason code |
| `0x33` | `CLEAR_FAULT` | PC -> STM32 | empty |
| `0x34` | `START_TEST` | PC -> STM32 | test ID + args |
| `0x35` | `STOP_TEST` | PC -> STM32 | empty |
| `0x36` | `SET_LOG_LEVEL` | PC -> STM32 | module mask + level |

### 6.5 Events / faults / logs

| Type | Name | Direction | Payload |
|---|---|---|---|
| `0x40` | `EVENT` | STM32 -> PC | event code + context |
| `0x41` | `FAULT` | STM32 -> PC | fault code + latched snapshot |
| `0x42` | `LOG_TEXT` | STM32 -> PC | UTF-8 text line |
| `0x43` | `STATE_SNAPSHOT` | STM32 -> PC | full state dump |

### 6.6 Capture

| Type | Name | Direction | Payload |
|---|---|---|---|
| `0x50` | `CAPTURE_CONFIG` | PC -> STM32 | trigger + signal mask |
| `0x51` | `CAPTURE_ARM` | PC -> STM32 | empty |
| `0x52` | `CAPTURE_STATUS` | STM32 -> PC | idle/armed/done |
| `0x53` | `CAPTURE_DATA` | STM32 -> PC | chunked ring-buffer data |

---

## 7. Default telemetry sets

To make the future GUI simple, telemetry is grouped into named streams.

### 7.1 Stream `0x01` - Control fast

Recommended period: `10 ms` (`100 Hz`)

Fields:

- `timestamp_ms` `u32`
- `control_cycle` `u32`
- `mode` `u8`
- `pitch_deg` `f32`
- `pitch_rate_dps` `f32`
- `target_pitch_deg` `f32`
- `velocity_left_rpm` `f32`
- `velocity_right_rpm` `f32`
- `velocity_mean_rpm` `f32`
- `target_velocity_rpm` `f32`
- `drive_output` `f32`
- `yaw_output` `f32`
- `motor_left_cmd` `f32`
- `motor_right_cmd` `f32`

Use:

- tuning angle loop
- tuning velocity loop
- verifying saturation and oscillation

### 7.2 Stream `0x02` - Sensors

Recommended period: `20 ms` (`50 Hz`)

Fields:

- `timestamp_ms` `u32`
- `acc_x_g` `f32`
- `acc_y_g` `f32`
- `acc_z_g` `f32`
- `gyro_x_dps` `f32`
- `gyro_y_dps` `f32`
- `gyro_z_dps` `f32`
- `pitch_fused_deg` `f32`
- `roll_fused_deg` `f32`
- `yaw_fused_deg` `f32`
- `ahrs_flags` `u16`
- `imu_sample_age_ms` `u16`

Use:

- IMU validation
- axis sign debugging
- filter bring-up

### 7.3 Stream `0x03` - Actuators and power

Recommended period: `20 ms` (`50 Hz`)

Fields:

- `timestamp_ms` `u32`
- `motor_left_current_a` `f32`
- `motor_right_current_a` `f32`
- `battery_v` `f32`
- `left_pwm` `u16`
- `right_pwm` `u16`
- `left_brake` `u8`
- `right_brake` `u8`
- `safety_flags` `u16`

Use:

- current-limit tuning
- battery sag observation
- power-stage diagnosis

### 7.4 Stream `0x04` - Runtime health

Recommended period: `100 ms` (`10 Hz`)

Fields:

- `timestamp_ms` `u32`
- `uptime_ms` `u32`
- `cpu_load_permille` `u16`
- `control_loop_period_us` `u16`
- `control_loop_jitter_us` `u16`
- `missed_control_deadlines` `u16`
- `uart_rx_overruns` `u16`
- `uart_tx_drops` `u16`
- `watchdog_resets` `u16`
- `fault_code_active` `u16`

Use:

- real-time validation
- serial transport health
- regression detection

### 7.5 Stream `0x05` - Encoders

Recommended period: `20 ms` (`50 Hz`)

Fields:

- `timestamp_ms` `u32`
- `enc_left_count` `i32`
- `enc_right_count` `i32`
- `enc_left_delta` `i16`
- `enc_right_delta` `i16`
- `wheel_left_rpm` `f32`
- `wheel_right_rpm` `f32`

Use:

- encoder sign check
- tick loss detection
- wheel asymmetry tuning

### 7.6 Stream `0x06` - Fault-focused snapshot

Generated on demand or fault only.

Fields:

- all critical values around failure
- latest command source
- latest setpoints
- last 3 fault causes
- last parameter change ID

Use:

- root-cause analysis

---

## 8. Parameter model

Every tunable value must have:

- stable numeric ID
- name
- type
- unit
- min/max
- default
- persistence flag
- access rights
- group name

### 8.1 Parameter descriptor

| Field | Type | Meaning |
|---|---|---|
| `param_id` | `u16` | unique parameter ID |
| `type` | `u8` | `bool/u8/i32/f32` |
| `flags` | `u8` | read-only, persistent, expert |
| `min_value` | variant | lower limit |
| `max_value` | variant | upper limit |
| `default_value` | variant | factory default |
| `name` | string | short stable key |
| `unit` | string | display unit |
| `group` | string | GUI grouping |

### 8.2 Recommended parameter groups

#### Group `control.angle`

- `angle.kp`
- `angle.ki`
- `angle.kd`
- `angle.output_limit`
- `angle.integral_limit`

#### Group `control.velocity`

- `velocity.kp`
- `velocity.ki`
- `velocity.kd`
- `velocity.target_limit_rpm`
- `velocity.integral_limit`

#### Group `control.yaw`

- `yaw.kp`
- `yaw.ki`
- `yaw.kd`
- `yaw.output_limit`

#### Group `control.general`

- `control.sample_time_ms`
- `control.balance_enable`
- `control.target_pitch_bias_deg`
- `control.deadband_left`
- `control.deadband_right`

#### Group `safety`

- `safety.tilt_cutoff_deg`
- `safety.current_limit_left_a`
- `safety.current_limit_right_a`
- `safety.command_timeout_ms`
- `safety.ble_timeout_ms`

#### Group `imu`

- `imu.accel_scale`
- `imu.gyro_scale`
- `imu.pitch_offset_deg`
- `imu.filter_gain`
- `imu.acc_rejection`

#### Group `robot`

- `robot.wheel_radius_m`
- `robot.encoder_ticks_per_rev`
- `robot.gear_ratio`
- `robot.motor_polarity_left`
- `robot.motor_polarity_right`

### 8.3 Recommended first values

These are interface defaults for bring-up, not validated final gains.

| Parameter | Suggested initial value |
|---|---:|
| `control.sample_time_ms` | `5.0` |
| `angle.output_limit` | `1.0` |
| `velocity.target_limit_rpm` | `10.0` |
| `yaw.output_limit` | `0.30` |
| `safety.tilt_cutoff_deg` | `45.0` |
| `safety.current_limit_left_a` | `1.8` |
| `safety.current_limit_right_a` | `1.8` |
| `control.deadband_left` | `0.15` |
| `control.deadband_right` | `0.15` |
| `imu.filter_gain` | `0.5` |

---

## 9. Commands the GUI must support

### 9.1 Safe commands

- read all parameters
- write one parameter
- save parameters to flash
- reset parameters to defaults
- clear latched fault
- request full snapshot
- enable or disable telemetry streams

### 9.2 Bring-up commands

- `motor.left.step`
- `motor.right.step`
- `motor.both.coast`
- `motor.both.brake`
- `encoder.reset`
- `imu.zero_pitch`

These commands must only be accepted in `IDLE` or `TEST` mode.

### 9.3 Closed-loop commands

- `set_mode(ARMED/BALANCING/IDLE)`
- `set_velocity_target`
- `set_yaw_target`
- `emergency_stop`

### 9.4 Test modes

- sine excitation on motor command
- step response on velocity target
- static IMU monitor
- encoder spin test
- current sensor monitor

---

## 10. Fault and event model

The GUI needs reliable asynchronous diagnostics. Faults must be explicit and machine-readable.

### 10.1 Fault codes

| Code | Name |
|---|---|
| `0x0001` | `FAULT_TILT_LIMIT` |
| `0x0002` | `FAULT_OVERCURRENT_LEFT` |
| `0x0003` | `FAULT_OVERCURRENT_RIGHT` |
| `0x0004` | `FAULT_IMU_TIMEOUT` |
| `0x0005` | `FAULT_IMU_DATA_INVALID` |
| `0x0006` | `FAULT_CONTROL_OVERRUN` |
| `0x0007` | `FAULT_WATCHDOG_PRE_RESET` |
| `0x0008` | `FAULT_PARAM_OUT_OF_RANGE` |
| `0x0009` | `FAULT_MOTOR_DRIVER_INHIBITED` |
| `0x000A` | `FAULT_COMMAND_TIMEOUT` |

### 10.2 Event codes

| Code | Name |
|---|---|
| `0x0101` | `EVENT_BOOT_COMPLETE` |
| `0x0102` | `EVENT_MODE_CHANGED` |
| `0x0103` | `EVENT_PARAMETER_CHANGED` |
| `0x0104` | `EVENT_PARAMETERS_SAVED` |
| `0x0105` | `EVENT_CAPTURE_READY` |
| `0x0106` | `EVENT_STREAM_OVERRUN` |

### 10.3 Fault payload contents

Every `FAULT` packet should include:

- `timestamp_ms`
- `fault_code`
- `mode`
- `pitch_deg`
- `velocity_left_rpm`
- `velocity_right_rpm`
- `motor_left_cmd`
- `motor_right_cmd`
- `battery_v`
- `current_left_a`
- `current_right_a`

This avoids having to guess what the robot was doing at the moment of failure.

---

## 11. Human-readable logs

Use `LOG_TEXT` for:

- boot banner
- module init success/failure
- calibration completion
- parameter save status
- warnings that do not justify a `FAULT`

Recommended payload:

| Field | Type |
|---|---|
| `timestamp_ms` | `u32` |
| `level` | `u8` |
| `module` | `u8` |
| `text_len` | `u8` |
| `text` | `bytes` |

### 11.1 Log levels

- `0` `ERROR`
- `1` `WARN`
- `2` `INFO`
- `3` `DEBUG`
- `4` `TRACE`

### 11.2 Log modules

- `SYSTEM`
- `CONTROL`
- `IMU`
- `MOTOR`
- `ENCODER`
- `COMM`
- `SAFETY`
- `STORAGE`

---

## 12. GUI-oriented requirements

The future PC GUI should be able to:

- discover firmware version and capabilities
- show current mode and fault state
- plot at least 8 live signals at once
- change one parameter at a time and see ack/nack
- save parameter presets on the PC
- export telemetry to CSV
- request a snapshot after a fault
- arm a capture and retrieve buffered samples

This is why the protocol must include:

- a parameter table
- stream configuration
- typed fault packets
- typed event packets
- machine-readable logs

---

## 13. Anti-patterns to avoid

- sending raw `printf` intermixed with binary packets
- sending anonymous CSV without schema version
- relying on packet order alone without `SEQ`
- using variable names only and no numeric parameter IDs
- changing parameter names across firmware versions
- allowing motor test commands in `BALANCING` mode

---

## 14. Minimal V1 implementation plan

### Required in firmware V1

- `PING/PONG`
- `GET_DEVICE_INFO`
- `SET_STREAM_CONFIG`
- `TELEMETRY_SAMPLE`
- `GET_PARAMETER_TABLE`
- `READ_PARAMETER`
- `WRITE_PARAMETER`
- `SAVE_PARAMETERS`
- `FAULT`
- `EVENT`
- `LOG_TEXT`

### Required telemetry V1

- `control fast`
- `sensors`
- `actuators and power`
- `runtime health`

### Optional for V2

- `CAPTURE_*`
- test sequencer commands
- multi-sample burst packets

---

## 15. Dedicated file ownership

This file is the reference contract for:

- the STM32 serial protocol implementation
- the PC desktop GUI
- any future Python logger or test harness

If the protocol evolves:

- increment `VER`
- keep old message IDs stable whenever possible
- add fields at the end of payloads only

