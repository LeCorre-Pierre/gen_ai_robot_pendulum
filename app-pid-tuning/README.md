# robot-pid-tuner

PID velocity tuning tool for the STM32 self-balancing robot.
Communicates with the firmware over the ST-Link VCP (COM4 / `/dev/ttyACM0`)
using the binary VCP framing protocol defined in `emb-sw/Utilities/Protocol/`.

Three independent modes — pick the one that fits your workflow:

| Mode | Use case |
|------|----------|
| `monitor` | Read-only live dashboard — check RPM and error in real time |
| `tune` | Automated Kp/Ki search via Nelder-Mead (no interaction needed) |
| `mcp` | Expose robot control as MCP tools so Claude tunes it autonomously |

---

## Prerequisites

```
Python 3.11+
STM32 robot flashed and connected via USB (ST-Link VCP)
SCREEN_VCP_TUNER active on the robot display (first screen, B1 starts stream)
```

---

## Install

```bash
cd app-pid-tuning
pip install -e ".[dev]"
```

---

## Mode 1 — monitor (live dashboard)

Watch real-time telemetry without sending any motor commands.

```bash
python main.py monitor --port COM4
python main.py monitor --port COM4 --rate 100    # 100 Hz streaming
```

The display updates at up to 10 fps and shows:

```
╭──────── ROBOT PID TUNER  ●  LIVE ─────────────────╮
│  Motor   SP (RPM)   PV (RPM)   Error   PWM %       │
│  LEFT       +50       +47       +3      +45  ████▌  │
│  RIGHT      +50       +49       +1      +42  ████   │
╰── COM4  50 Hz  Ctrl-C to quit ────────────────────╯
```

Error colour: green < 10 RPM, yellow < 30, red ≥ 30.

---

## Mode 2 — tune (automated optimisation)

Runs a Nelder-Mead search over (Kp, Ki) to minimise a cost function:

```
cost = overshoot_pct × 0.5 + settling_time_s × 2.0 + steady_error_rpm × 0.1
```

Each iteration: enable motors → step setpoint → record 2 s → coast → measure.

```bash
# Tune both motors to 50 RPM (default)
python main.py tune --port COM4

# Custom target and iteration budget
python main.py tune --port COM4 --motor left --target 80 --iter 40 --duration 3
```

Output per iteration:

```
  # 1  Kp=0.00400  Ki=0.00200  cost=18.34  OS=12.1%  Ts=1.23s  Err=4.2rpm
  # 2  Kp=0.00520  Ki=0.00200  cost=14.21  OS= 7.8%  Ts=0.94s  Err=2.1rpm
  ...
```

Final result:

```
  Kp (optimal)        0.00612
  Ki (optimal)        0.00241
  Overshoot           5.3 %
  Settling time       0.721 s
  Steady-state error  1.4 RPM

Paste into motor_control.h:
  #define MTR_VEL_KP_DEFAULT  0.0061f
  #define MTR_VEL_KI_DEFAULT  0.0024f
```

### CLI options

| Option | Default | Description |
|--------|---------|-------------|
| `--port` | required | Serial port (COM4, /dev/ttyACM0 …) |
| `--motor` | `both` | `left`, `right`, or `both` |
| `--target` | `50` | Step target in RPM |
| `--duration` | `2.0` | Step recording window (s) |
| `--rate` | `50` | Telemetry Hz during optimisation |
| `--iter` | `30` | Max Nelder-Mead iterations |

---

## Mode 3 — mcp (Claude integration)

Run as an MCP server so Claude can tune the robot autonomously.

### Start the server

```bash
python main.py mcp --port COM4
```

Or without pre-connecting (Claude uses the `connect` tool):

```bash
python main.py mcp
```

### Connect Claude Code

Add to your Claude Code MCP config (`~/.claude/claude_code_config.json` or the
workspace `.claude/settings.json`):

```json
{
  "mcpServers": {
    "robot-pid-tuner": {
      "command": "python",
      "args": ["main.py", "mcp", "--port", "COM4"],
      "cwd": "D:/Projects/gen_ai_robot_pendulum/app-pid-tuning"
    }
  }
}
```

### Connect Claude Desktop

Add to `~/AppData/Roaming/Claude/claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "robot-pid-tuner": {
      "command": "python",
      "args": ["main.py", "mcp", "--port", "COM4"],
      "cwd": "D:/Projects/gen_ai_robot_pendulum/app-pid-tuning"
    }
  }
}
```

### Available MCP tools

| Tool | Description |
|------|-------------|
| `connect` | Open serial port |
| `disconnect` | Coast motors + close port |
| `set_gains` | Upload Kp/Ki/Kd to motor(s) |
| `set_setpoint` | Set target RPM |
| `motor_control` | COAST / BRAKE / ENABLE |
| `start_telemetry` | Begin streaming (1–100 Hz) |
| `stop_telemetry` | Stop streaming |
| `get_telemetry` | Single snapshot |
| `record_step_response` | Step + log → metrics + raw data |
| `run_optimization` | Full Nelder-Mead search (autonomous) |

### Example Claude conversation

> *"Connect to COM4, tune the left motor PID for 60 RPM — I want less than 10 % overshoot and settle within 1 second."*

Claude will:
1. Call `connect(port="COM4")`
2. Call `run_optimization(motor="left", target_rpm=60, max_iter=30)`
3. Analyse the log, apply the optimal gains, run a final `record_step_response`
4. Report gains + firmware defines

---

## Run tests (no hardware required)

```bash
pytest tests/test_protocol.py -v
```

21 unit tests covering CRC16, frame encode/decode, all command builders, and
telemetry parsing — verified against the firmware CRC implementation.

---

## File structure

```
app-pid-tuning/
├── main.py               Entry point — mcp / monitor / tune modes
├── pyproject.toml        Dependencies and package metadata
├── pid_tuner/
│   ├── protocol.py       VCP frame encode/decode (mirrors vcp_protocol.h)
│   ├── robot_client.py   Serial connection + blocking command API
│   ├── optimizer.py      Step-response metrics + scipy Nelder-Mead
│   └── mcp_server.py     MCP server (10 tools)
└── tests/
    └── test_protocol.py  Protocol unit tests (21 tests)
```

---

## VCP protocol summary

```
SOF1(0xAA) SOF2(0x55) VER TYPE FLAGS SEQ LEN_L LEN_H PAYLOAD… CRC16_L CRC16_H EOF(0x33)
```

CRC16-CCITT over bytes `[VER … end-of-payload]`.

| Direction | Type | Payload |
|-----------|------|---------|
| STM32→PC | `0x10` TELEMETRY_PID | `uint32 ts` + 7×`int16` (sp, pv_l, pv_r, err_l, err_r, pwm_l×100, pwm_r×100) |
| PC→STM32 | `0x20` SET_GAINS | `uint8 motor` + 3×`float` (kp, ki, kd) |
| PC→STM32 | `0x21` SET_SP | `int16 rpm` |
| PC→STM32 | `0x22` STREAM_CTRL | `uint8 enable` + `uint16 rate_hz` |
| PC→STM32 | `0x23` MOTOR_CTRL | `uint8 action` (0=COAST 1=BRAKE 2=ENABLE) |
| STM32→PC | `0x30` ACK | `uint8 cmd_type` + `uint8 status` |
