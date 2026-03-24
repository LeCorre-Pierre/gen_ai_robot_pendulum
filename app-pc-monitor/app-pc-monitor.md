# PC Monitor — Application Specification

**Version:** 0.1
**Date:** 2026-03-22
**Protocol reference:** `4-stlink-vcp-interface.md`
**Target platform:** Windows / Linux / macOS (Python 3.11+)

---

## 1. Purpose

This application is the wired engineering tool for the self-balancing robot project.
It connects to the STM32WB5MMG firmware over the ST-Link Virtual COM Port (`USART1`, `PB6/PB7`).

It is dedicated to:

- bring-up and board validation
- control-loop debug
- real-time telemetry plotting
- PID tuning
- sensor and actuator diagnosis
- fault analysis
- capture and export of trace data for offline analysis

It is **not** the production driving interface. That role belongs to the BLE smartphone app.

---

## 2. Technology stack

| Layer | Library | Rationale |
|---|---|---|
| UI framework | **PySide6** (Qt 6) | LGPL, cross-platform, mature, dockable windows |
| Real-time plots | **pyqtgraph** | GPU-accelerated, Qt-native, handles 1 kHz+ samples |
| Serial I/O | **pyserial** | industry standard, thread-safe `Serial` object |
| Data model | **numpy** | ring buffers for live plot data |
| CSV export | **csv** (stdlib) | no extra dependency |
| Packaging | **pyproject.toml** + `pip` | simple install, no build step required |

**No matplotlib in the real-time path.** matplotlib is only acceptable for offline post-processing or export previews.

---

## 3. Application layout

The main window is built around a **dockable panel system** (Qt `QDockWidget`).
The user can rearrange, float, and hide any panel. Layout is saved and restored between sessions.

### 3.1 Persistent toolbar (top)

```
[ Port: COM3 ▼ ] [ 115200 ▼ ] [ Connect ] [ Disconnect ]   |  Mode: BALANCING  |  Fault: OK  |  Uptime: 00:12:34
```

- COM port list is auto-refreshed; STM32 VCP adapters are highlighted.
- Baud rate selector: 115200 (default), 230400, 460800.
- Mode badge: colour-coded (`BOOT`=grey, `IDLE`=blue, `ARMED`=orange, `BALANCING`=green, `FAULT`=red, `CALIBRATION`=yellow, `TEST`=purple).
- Fault badge: `OK` (green) or fault name in red. Click → jumps to Fault panel.

### 3.2 Panels

| Panel | Default position | Resizable |
|---|---|---|
| **Telemetry** | centre (tabbed or split) | yes |
| **Parameters** | right dock | yes |
| **Commands** | left dock | yes |
| **Events & Faults** | bottom-left | yes |
| **Log** | bottom-right | yes |
| **Capture** | tabbed with Telemetry | yes |

---

## 4. Connection and session management

### 4.1 Startup flow

Follows the session model from `4-stlink-vcp-interface.md §4.1`:

1. User selects COM port and clicks **Connect**.
2. App opens port and sends `PING`.
3. On `PONG` → marks link as live, shows uptime.
4. App sends `GET_DEVICE_INFO` → displays firmware ID and capability bitmap in status bar tooltip.
5. App sends `GET_PARAMETER_TABLE` → populates Parameters panel.
6. App restores previously saved stream subscriptions and re-sends `SET_STREAM_CONFIG` for each active stream.

### 4.2 Disconnect / error recovery

- On port close or read timeout > 2 s: show `DISCONNECTED` badge, stop all timers, keep last telemetry frozen on screen.
- On `NACK`: highlight the offending command in the Command panel with the error code.
- Reconnect button re-runs the startup flow without clearing the plot history.

### 4.3 Serial reader

Runs in a **dedicated `QThread`**.
Emits Qt signals carrying parsed `Packet` objects into the main thread.
No Qt UI calls from the serial thread.
Implements the packet framing from `4-stlink-vcp-interface.md §3.2`:

```
SOF1(0xAA) SOF2(0x55) VER TYPE FLAGS SEQ LEN_L LEN_H PAYLOAD... CRC16_L CRC16_H EOF(0x33)
```

CRC16-CCITT computed over `VER..PAYLOAD`.
On CRC failure: discard packet, increment `rx_crc_errors` counter visible in status bar.

---

## 5. Telemetry panel

### 5.1 Plot engine

- Each **stream** (`0x01`–`0x06`) maps to one or more **plot lanes**.
- A lane is a scrolling time-domain waveform backed by a fixed-size numpy ring buffer (default: 10 000 samples per signal, configurable up to 100 000).
- Up to **8 lanes visible simultaneously** in the default layout.
- Lanes can be split into multiple plot widgets (top/bottom split) or stacked.

### 5.2 Stream controls

For each stream there is a collapsible header:

```
[ ▼ Stream 0x01 — Control fast ]  [ Enable ]  [ Period: 10 ms ▼ ]  [ Signal checkboxes... ]
```

- `Enable` sends `SET_STREAM_CONFIG` to firmware.
- `Period` dropdown: 5 / 10 / 20 / 50 / 100 ms.
- Signal checkboxes: each field in the stream has a checkbox and a colour swatch. Unchecked signals are decoded but not plotted (still available for export).

### 5.3 Streams and their default enabled signals

#### Stream `0x01` — Control fast (100 Hz default)

Default-enabled signals: `pitch_deg`, `target_pitch_deg`, `drive_output`, `motor_left_cmd`, `motor_right_cmd`

Available: `timestamp_ms`, `control_cycle`, `mode`, `pitch_deg`, `pitch_rate_dps`, `target_pitch_deg`, `velocity_left_rpm`, `velocity_right_rpm`, `velocity_mean_rpm`, `target_velocity_rpm`, `drive_output`, `yaw_output`, `motor_left_cmd`, `motor_right_cmd`

#### Stream `0x02` — Sensors (50 Hz default)

Default-enabled signals: `pitch_fused_deg`, `roll_fused_deg`, `gyro_x_dps`

Available: `timestamp_ms`, `acc_x_g`, `acc_y_g`, `acc_z_g`, `gyro_x_dps`, `gyro_y_dps`, `gyro_z_dps`, `pitch_fused_deg`, `roll_fused_deg`, `yaw_fused_deg`, `ahrs_flags`, `imu_sample_age_ms`

#### Stream `0x03` — Actuators and power (50 Hz default)

Default-enabled signals: `motor_left_current_a`, `motor_right_current_a`, `battery_v`

Available: `timestamp_ms`, `motor_left_current_a`, `motor_right_current_a`, `battery_v`, `left_pwm`, `right_pwm`, `left_brake`, `right_brake`, `safety_flags`

#### Stream `0x04` — Runtime health (10 Hz default)

Default-enabled signals: `cpu_load_permille`, `control_loop_jitter_us`

Available: `timestamp_ms`, `uptime_ms`, `cpu_load_permille`, `control_loop_period_us`, `control_loop_jitter_us`, `missed_control_deadlines`, `uart_rx_overruns`, `uart_tx_drops`, `watchdog_resets`, `fault_code_active`

#### Stream `0x05` — Encoders (50 Hz default)

Default-enabled signals: `wheel_left_rpm`, `wheel_right_rpm`

Available: `timestamp_ms`, `enc_left_count`, `enc_right_count`, `enc_left_delta`, `enc_right_delta`, `wheel_left_rpm`, `wheel_right_rpm`

### 5.4 Cursor and measurement tools

- Vertical cursor: click on plot → shows values of all visible signals at that timestamp.
- Delta cursor: drag between two points → shows Δt and Δvalue.
- Auto-scale per lane (button) or manual Y-axis drag.
- Freeze / unfreeze button to pause scrolling without closing the port.

### 5.5 Export

- **Export CSV**: saves all decoded signals (checked or not) from the ring buffer to a timestamped CSV file.
  Format: one row per sample, one column per signal, header row with signal names and units.
- **Export PNG**: saves current visible plot as image.
- Export is triggered from the File menu or a toolbar icon.

---

## 6. Parameters panel

### 6.1 Layout

Tree view grouped by parameter group (`control.angle`, `control.velocity`, `control.yaw`, `control.general`, `safety`, `imu`, `robot`).

Each row shows:

```
param_name    [value input]   unit   [min .. max]   [R/W badge]   [Saved badge]
```

- `[R/W badge]`: grey if read-only, blue if writable.
- `[Saved badge]`: dot appears when local value differs from firmware value (unsaved edit).

### 6.2 Edit flow

1. User changes value in the input widget.
2. Value is validated against `[min .. max]` locally; out-of-range shown in red immediately.
3. User presses Enter or clicks **Apply** → app sends `WRITE_PARAMETER`.
4. On `ACK`: update row to confirmed value, clear unsaved dot.
5. On `NACK`: show error code inline, revert to last confirmed value.

### 6.3 Persistence

- **Save to flash** button → sends `SAVE_PARAMETERS` → waits for `EVENT_PARAMETERS_SAVED` or timeout.
- **Load defaults** button → sends `LOAD_PARAMETERS(defaults)`.
- **Export preset**: saves current parameter values to a local JSON file.
- **Import preset**: loads a local JSON file and writes all parameters to firmware one by one.

---

## 7. Commands panel

Buttons are grouped by safety level with visual separation.

### 7.1 Safe commands (always enabled when connected)

- `Read all parameters` — re-fetch the full parameter table.
- `Clear fault` — sends `CLEAR_FAULT`.
- `Request snapshot` — sends `STATE_SNAPSHOT` request.
- `Emergency stop` — sends `EMERGENCY_STOP(reason=MANUAL)`. Large red button, always reachable.

### 7.2 Bring-up commands (enabled in IDLE or TEST mode only)

| Button | Command sent |
|---|---|
| Motor A step+ | `START_TEST(motor.left.step)` |
| Motor B step+ | `START_TEST(motor.right.step)` |
| Coast both | `START_TEST(motor.both.coast)` |
| Brake both | `START_TEST(motor.both.brake)` |
| Reset encoders | `START_TEST(encoder.reset)` |
| Zero IMU pitch | `START_TEST(imu.zero_pitch)` |

Greyed out in any other mode.
Tooltips explain why the button is disabled if the mode is wrong.

### 7.3 Closed-loop commands (enabled in IDLE, ARMED, BALANCING)

- Mode selector: `IDLE` / `ARMED` / `BALANCING` — sends `SET_CONTROL_MODE`.
- Velocity target slider: −50 to +50 RPM (sends `SET_MANUAL_COMMAND`).
- Yaw target slider: −1.0 to +1.0 (sends `SET_MANUAL_COMMAND`).

### 7.4 Test sequences (enabled in TEST mode only)

- Sine excitation on motor command
- Step response on velocity target
- Static IMU monitor
- Encoder spin test
- Current sensor monitor

Each test has a **Start** / **Stop** pair. Start sends `START_TEST(test_id, args)`, Stop sends `STOP_TEST`.
Args are shown as inline spinboxes (frequency, amplitude, duration).

---

## 8. Events and Faults panel

Split into two sub-tabs: **Events** and **Faults**.

### 8.1 Events tab

Scrolling log table:

```
Timestamp   | Code   | Name                  | Context
00:01:23.450 | 0x0102 | EVENT_MODE_CHANGED    | IDLE → ARMED
00:01:30.012 | 0x0103 | EVENT_PARAMETER_CHANGED | angle.kp = 1.20
```

- Each event type has a distinct icon.
- Table is filterable by event code.
- Right-click → jump to timestamp in Telemetry plots.

### 8.2 Faults tab

```
Timestamp   | Code   | Name                | pitch | vel_L | vel_R | motor_L | motor_R | battery | i_L | i_R
00:02:11.000 | 0x0001 | FAULT_TILT_LIMIT   | 47.2° | 38rpm | 36rpm | 0.95    | 0.93    | 11.8V   | 1.2A | 1.1A
```

- Row background: red for active fault, dark-red for latched.
- **Clear fault** shortcut button on this panel.
- **Export faults to CSV** button.
- Double-click → open detailed fault dialog showing full `FAULT` payload.

---

## 9. Log panel

Scrolling text display rendering `LOG_TEXT` packets.

```
[00:01:22.100] [INFO ] [SYSTEM ] Boot complete. FW v0.1.0
[00:01:22.120] [INFO ] [IMU    ] ISM330DHCX init OK, addr=0x6B
[00:01:25.400] [WARN ] [SAFETY ] Tilt limit soft threshold reached: 38.1°
[00:01:30.000] [DEBUG] [CONTROL] angle.kp updated: 1.20 → 1.40
```

- Log level filter: `ERROR` / `WARN` / `INFO` / `DEBUG` / `TRACE` checkboxes.
- Module filter: `SYSTEM` / `CONTROL` / `IMU` / `MOTOR` / `ENCODER` / `COMM` / `SAFETY` / `STORAGE` checkboxes.
- Colour coding: ERROR=red, WARN=orange, INFO=white, DEBUG=grey, TRACE=dark-grey.
- **Pause** button: freezes display without discarding incoming lines.
- **Export log** button: saves visible (filtered) log to `.txt`.

---

## 10. Capture panel

### 10.1 Configuration

```
Trigger: [ Rising edge ▼ ]  Signal: [ pitch_deg ▼ ]  Threshold: [ 15.0 ] deg
Signal mask: [ pitch_deg ✓ ] [ drive_output ✓ ] [ motor_left_cmd ✓ ] [ ... ]
Pre-trigger samples: [ 200 ]    Post-trigger samples: [ 800 ]
```

Sends `CAPTURE_CONFIG` when the user clicks **Configure**.

### 10.2 Arm and retrieve

1. **Arm capture** button → sends `CAPTURE_ARM`.
2. Status badge: `IDLE` / `ARMED` / `TRIGGERED` / `DONE` (polled via `CAPTURE_STATUS`).
3. On `DONE`: app automatically fetches data with `CAPTURE_DATA` (chunked).
4. Data displayed in a dedicated plot widget (non-scrolling, fixed time axis).
5. **Export capture CSV** button.

---

## 11. Settings and preferences

Stored in `~/.config/robot-monitor/settings.json` (cross-platform path via `platformdirs`).

| Key | Default | Description |
|---|---|---|
| `port` | last used | COM port |
| `baud` | `115200` | baud rate |
| `plot_buffer_samples` | `10000` | ring buffer depth per signal |
| `plot_theme` | `dark` | `dark` or `light` |
| `stream_configs` | see §5.3 | per-stream enable + period |
| `layout` | default | Qt dock geometry (base64 blob) |
| `log_level_filter` | all on | bitmask |

---

## 12. Software architecture

```
app-pc-monitor/
├── main.py                  # entry point, QApplication
├── pyproject.toml           # dependencies
├── monitor/
│   ├── serial/
│   │   ├── port_scanner.py  # list COM ports, tag STM32 VCP adapters
│   │   ├── reader_thread.py # QThread, reads bytes, emits Packet signals
│   │   └── protocol.py      # framing, CRC16-CCITT, Packet dataclass
│   ├── model/
│   │   ├── ring_buffer.py   # numpy-backed fixed-size circular buffer
│   │   ├── telemetry.py     # stream decoders, signal registry
│   │   ├── parameters.py    # parameter table, descriptor, validation
│   │   └── session.py       # connection state machine
│   ├── ui/
│   │   ├── main_window.py   # QMainWindow, dock layout
│   │   ├── toolbar.py       # port selector, connect button, status badges
│   │   ├── telemetry_panel.py
│   │   ├── parameters_panel.py
│   │   ├── commands_panel.py
│   │   ├── faults_panel.py
│   │   ├── log_panel.py
│   │   └── capture_panel.py
│   └── export/
│       ├── csv_export.py
│       └── png_export.py
└── tests/
    ├── test_protocol.py     # packet encode/decode, CRC, bad-frame rejection
    └── test_ring_buffer.py
```

### 12.1 Threading model

```
Main thread (Qt event loop)
  └── serial reader QThread
        emits packet_received(Packet) → queued connection → main thread slot
        emits link_lost() → queued connection → reconnect logic
```

All ring buffer writes and UI updates happen in the main thread via queued signals.
No mutex needed for the ring buffers because only the main thread writes.

### 12.2 Packet dataclass

```python
@dataclass
class Packet:
    ver:     int
    type:    int
    flags:   int
    seq:     int
    payload: bytes
```

Protocol constants live in `protocol.py` alongside the framer and CRC function.

### 12.3 Signal registry

The telemetry panel is data-driven.
`telemetry.py` contains a static description of every stream and every signal field (name, type, unit, scale factor).
The UI reads this description at startup to build the checkbox list and plot legend.
Adding a new firmware stream requires only adding an entry here, not touching UI code.

---

## 13. Dependencies (pyproject.toml)

```toml
[project]
name = "robot-monitor"
requires-python = ">=3.11"
dependencies = [
    "PySide6>=6.6",
    "pyqtgraph>=0.13",
    "pyserial>=3.5",
    "numpy>=1.26",
    "platformdirs>=4.0",
]
```

Install with:

```bash
pip install -e .
python -m monitor.main
```

---

## 14. Non-functional requirements

- **Plot frame rate:** ≥ 30 FPS at 100 Hz telemetry, 8 signals active, on a mid-range laptop.
- **Latency:** parameter write → ACK round-trip shown within 200 ms of firmware response.
- **Memory:** ring buffer at default depth (10 000 samples × 14 signals × 4 bytes) ≈ 560 KB. Acceptable.
- **Startup time:** < 3 s from launch to connect-ready state.
- **No telemetry loss:** the serial reader must never block the Qt main thread.
- **Unitary tests** are presents to easily detects broken features

---

## 15. Out of scope

- OTA firmware update (future feature).
- BLE connection (BLE is the smartphone channel, not this app).
- Raspberry Pi LPUART1 bridge configuration.
- Any motor command while the robot is in `BALANCING` mode (enforced by firmware, verified by UI greying).
