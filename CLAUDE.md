# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Self-balancing two-wheeled inverted pendulum robot. Three subsystems:
1. **Firmware** — STM32WB5MMG on MB1292B, C/C++ with FreeRTOS
2. **PC Monitor app** — Python/PySide6, connects via ST-Link VCP
3. **Smartphone app** — BLE 5.2 client (not yet started; Flutter recommended)

The STM32 is the sole master of the control loop. The PC app is an engineering/tuning tool only. No motor commands come from the PC or RPi.

---

## Build Commands

### Firmware (STM32)

Must run from the build directory:
```bash
cd /d/Projects/gen_ai_robot_pendulum/mb1292b-controller/Projects/STM32WB5MM-DK/Applications/BLE/BLE_Sensor/STM32CubeIDE/Debug
make -j16 all      # build
make -j16 clean    # clean
```

Git Bash aliases (defined in shell profile):
- `mbuild` — compile firmware
- `mclean` — remove build artifacts
- `mrebuild` — clean + rebuild
- `cmcu` — cd to firmware project root
- `cproj` — cd to repo root

> **Note:** `PB3` is used for `ENC_RIGHT_CHB` (TIM2_CH2). SWO debug trace must be disabled in Release builds.

### PC Monitor App

```bash
cd app-pc-monitor
pip install -e ".[dev]"   # install with test deps
py -3.11 main.py          # run app
```

### Tests

```bash
cd app-pc-monitor
pytest                            # all tests
pytest tests/test_protocol.py     # single test file
```

### Serial Console (firmware debug)

```bash
python -m serial.tools.miniterm COM4 115200
```

---

## STM32 Firmware Architecture

**Board:** MB1292B (STM32WB5MMG — Cortex-M4 @ 64 MHz + M0+ @ 32 MHz for BLE 5.2)

**Project root:** `mb1292b-controller/Projects/STM32WB5MM-DK/Applications/BLE/BLE_Sensor/`

**Key source files:**
- `Core/Src/main.c` — entry point, peripheral init
- `Core/Src/periph_init.c` — peripheral initialization
- `Core/Src/host_link.c` / `host_link_params.c` / `host_link_storage.c` — VCP protocol host interface
- `Core/Src/hw_uart.c` — UART driver

**Control modules:** `mb1292b-controller/Utilities/Control/`
- `pid_controller.c/h` — generic PID with anti-windup
- `cascade_balance_controller.c/h` — cascade PID (outer velocity → inner angle)

**FreeRTOS task structure (planned):**
- `task_control` — balance loop @ 200 Hz (Cortex-M4)
- `task_ble` — BLE smartphone channel
- `task_vcp` — ST-Link VCP to PC
- `task_safety` — watchdog, tilt limit, fault management

**IMU:** ISM330DHCX onboard MB1292B, connected via I2C3 (PB13=SCL, PB11=SDA), address `0x6B`. Driver: `Drivers/BSP/Components/ism330dhcx/`. Do not add an external IMU.

**CubeIDE project files** (modify to change project properties):
- `STM32CubeIDE/.project`
- `STM32CubeIDE/.cproject`

---

## Pin Allocation (STM32WB5MMG)

| Function | Pin | Peripheral | Connector |
|---|---|---|---|
| Left encoder CHA | PD14 | TIM1_CH1 | Arduino D3 |
| Left encoder CHB | PD15 | TIM1_CH2 | Arduino D9 |
| Right encoder CHA | PA15 | TIM2_CH1 | STMod+ pin 14 |
| Right encoder CHB | PB3 | TIM2_CH2 | Direct (disables SWO) |
| Left motor PWM | PC1 | LPTIM1_OUT | Arduino A3 |
| Right motor PWM | PE0 | TIM16_CH1 | Arduino D6 |
| Left motor DIR | PD12 | GPIO out | Arduino D2 |
| Left motor BRAKE | PD13 | GPIO out | Arduino D8 |
| Right motor DIR | PE3 | GPIO out | Arduino D4 |
| Right motor BRAKE | PB2 | GPIO out | Arduino D7 |
| Left current sense | PA5 | ADC1_IN10 | Arduino A2 |
| Right current sense | PC3 | ADC1_IN4 | Arduino A0 |
| VCP TX | PB6 | USART1_TX | ST-Link onboard |
| VCP RX | PB7 | USART1_RX | ST-Link onboard |
| IMU SCL | PB13 | I2C3_SCL | Internal |
| IMU SDA | PB11 | I2C3_SDA | Internal |

**Do not use:** PA8/PA9 (microphones), PB0/PB1 (not routed on MB1292B), D10–D13 (SPI1/OLED).

TIM1 and TIM2 are exclusively for encoders (QEI mode). PWM uses LPTIM1 (20 kHz, PC1) and TIM16 (PE0).

---

## PC Monitor App Architecture

**Stack:** PySide6 (Qt6) + pyqtgraph + pyserial + numpy

```
app-pc-monitor/
├── main.py                     # QApplication entry, SIGINT handler
├── pyproject.toml
├── monitor/
│   ├── serial/
│   │   ├── port_scanner.py     # lists COM ports, flags STM32 VCP adapters
│   │   ├── reader_thread.py    # QThread — reads bytes, emits Packet signals
│   │   └── protocol.py        # framing, CRC16-CCITT, Packet dataclass
│   ├── model/
│   │   ├── ring_buffer.py      # numpy-backed circular buffer
│   │   ├── telemetry.py        # stream decoders, signal registry (data-driven)
│   │   ├── parameters.py       # parameter table and validation
│   │   └── session.py          # connection state machine
│   ├── ui/
│   │   └── main_window.py      # QMainWindow, dockable panels
│   └── export/
│       ├── csv_export.py
│       └── png_export.py
└── tests/
```

**Threading model:** Serial reader runs in a `QThread` and emits `Packet` signals via queued connections to the main thread. All ring buffer writes and UI updates happen on the main thread only — no mutex required.

**VCP packet framing:**
```
SOF1(0xAA) SOF2(0x55) VER TYPE FLAGS SEQ LEN_L LEN_H PAYLOAD... CRC16_L CRC16_H EOF(0x33)
```
CRC16-CCITT computed over `VER..PAYLOAD`.

**Adding a new telemetry stream:** only requires adding an entry to the signal registry in `telemetry.py` — no UI code changes needed.

Settings stored in `~/.config/robot-monitor/settings.json` (via `platformdirs`).

---

## Control Architecture

Cascade PID:
- **Outer loop:** wheel velocity → target pitch angle
- **Inner loop:** pitch angle → normalized motor command (−1.0 to +1.0)
- **Yaw:** differential left/right speed correction

Angle estimation: complementary filter (accel + gyro fusion). Kalman is an alternative.

Safety cutoffs: |tilt| > 45°, BLE timeout 200 ms, watchdog 50 ms, 3 consecutive missed I2C samples.

Motor resolution: 29:1 gearbox × 64 CPR encoder = **1856 ticks/revolution effective**.

---

## Key Documents

| File | Content |
|---|---|
| `1-requirements.md` | Full system requirements with IDs (SYS-*, HW-*, FW-*, PC-*, APP-*) |
| `2-system.md` | Board architecture and inter-board connections |
| `3-boards-interfaces.md` | Signal naming convention and documentation↔code mapping |
| `4-stm32wb5m-pins-allocations.txt` | Authoritative pin table and CubeMX actions required |
| `app-pc-monitor/app-pc-monitor.md` | Full PC app specification (panels, protocol, architecture) |
| `parts/` | Hardware datasheets and notes |
| `6-connections_colors.md` | Wire color convention (DIR=grey, PWM=purple, Brake=blue, Current=green) |
