"""
MCP server — exposes robot PID tuning as Claude-callable tools.

Tools:
  connect             Connect to the robot serial port
  disconnect          Disconnect (coasts motors first)
  set_gains           Set Kp / Ki / Kd on one or both motors
  set_setpoint        Set shared target RPM
  motor_control       COAST / BRAKE / ENABLE
  start_telemetry     Begin streaming telemetry at requested rate
  stop_telemetry      Stop streaming
  get_telemetry       Single snapshot of live telemetry
  record_step_response  Step + log → metrics + raw samples
  run_optimization    Automated Nelder-Mead Kp/Ki search

Usage as MCP server (stdio transport):
  python main.py mcp --port COM4

Claude Desktop / Claude Code config:
  {
    "mcpServers": {
      "robot-pid-tuner": {
        "command": "python",
        "args": ["main.py", "mcp", "--port", "COM4"],
        "cwd": "<path-to>/app-pid-tuning"
      }
    }
  }
"""

from __future__ import annotations
import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

from .robot_client import RobotClient
from .optimizer import optimize_pid, analyze_step

# ── Module-level client (set before run_mcp is called) ────────────────────────
_client: RobotClient | None = None


def set_client(client: RobotClient) -> None:
    global _client
    _client = client


def _require() -> RobotClient:
    if _client is None or not _client.is_connected():
        raise RuntimeError("Robot not connected — call the 'connect' tool first.")
    return _client


# ── Server instance ────────────────────────────────────────────────────────────
app = Server("robot-pid-tuner")


# ── Tool registry ──────────────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="connect",
            description="Connect to the STM32 robot via its ST-Link VCP serial port.",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "string",
                             "description": "Serial port name, e.g. COM4 or /dev/ttyACM0"},
                    "baud": {"type": "integer", "default": 115200},
                },
                "required": ["port"],
            },
        ),
        types.Tool(
            name="disconnect",
            description="Coast both motors and close the serial connection.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="set_gains",
            description=(
                "Upload new PID velocity gains to one or both motors. "
                "Takes effect immediately without resetting the integrator. "
                "Kd is almost always 0 for velocity loops."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "motor": {"type": "string", "enum": ["left", "right", "both"]},
                    "kp":    {"type": "number", "description": "Proportional gain (try 0.002–0.02)"},
                    "ki":    {"type": "number", "description": "Integral gain (try 0.001–0.01)"},
                    "kd":    {"type": "number", "default": 0.0},
                },
                "required": ["motor", "kp", "ki"],
            },
        ),
        types.Tool(
            name="set_setpoint",
            description="Set the shared target wheel velocity in RPM (−250 to +250).",
            inputSchema={
                "type": "object",
                "properties": {
                    "rpm": {"type": "integer",
                            "description": "Target RPM, positive = forward"},
                },
                "required": ["rpm"],
            },
        ),
        types.Tool(
            name="motor_control",
            description="Send a motor state command: coast (free-wheel), brake, or enable (velocity PID).",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["coast", "brake", "enable"]},
                },
                "required": ["action"],
            },
        ),
        types.Tool(
            name="start_telemetry",
            description="Start telemetry streaming from the robot (max 100 Hz).",
            inputSchema={
                "type": "object",
                "properties": {
                    "rate_hz": {"type": "integer", "default": 50,
                                "description": "Streaming rate in Hz (1–100)"},
                },
            },
        ),
        types.Tool(
            name="stop_telemetry",
            description="Stop telemetry streaming.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="get_telemetry",
            description=(
                "Get one telemetry snapshot. "
                "Returns: timestamp_ms, sp_rpm, pv_l_rpm, pv_r_rpm, err_l, err_r, pwm_l_pct, pwm_r_pct. "
                "Requires stream to be active (call start_telemetry first)."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="record_step_response",
            description=(
                "Apply a step setpoint, record the response, and return performance metrics. "
                "Automatically enables motors, starts the stream, records, then coasts. "
                "Returns: overshoot_pct, settling_time_s, steady_error_rpm, rise_time_s, and raw samples."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "setpoint_rpm": {"type": "integer",
                                     "description": "Step target RPM"},
                    "duration_s":   {"type": "number", "default": 2.0,
                                     "description": "Recording window in seconds"},
                    "rate_hz":      {"type": "integer", "default": 50},
                },
                "required": ["setpoint_rpm"],
            },
        ),
        types.Tool(
            name="run_optimization",
            description=(
                "Automatically optimize Kp and Ki using Nelder-Mead. "
                "Runs up to max_iter step responses, minimising "
                "overshoot + settling time + steady-state error. "
                "Returns optimal gains, final metrics, and a per-iteration log."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "motor":      {"type": "string", "enum": ["left", "right", "both"]},
                    "target_rpm": {"type": "integer",
                                   "description": "RPM used as the optimization target"},
                    "duration_s": {"type": "number", "default": 2.0},
                    "rate_hz":    {"type": "integer", "default": 50},
                    "max_iter":   {"type": "integer", "default": 30},
                },
                "required": ["motor", "target_rpm"],
            },
        ),
    ]


# ── Tool dispatcher ────────────────────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    args = arguments or {}
    loop = asyncio.get_running_loop()

    def run(fn, *a, **kw):
        return loop.run_in_executor(None, lambda: fn(*a, **kw))

    try:
        if name == "connect":
            global _client
            port = args["port"]
            baud = int(args.get("baud", 115200))
            _client = RobotClient(port, baud)
            await run(_client.connect)
            return _ok(f"Connected to {port} at {baud} baud.")

        elif name == "disconnect":
            c = _require()
            await run(c.motor_coast)
            await run(c.stop_stream)
            await run(c.disconnect)
            return _ok("Disconnected. Motors coasted.")

        elif name == "set_gains":
            c = _require()
            motor = args["motor"]
            kp = float(args["kp"])
            ki = float(args["ki"])
            kd = float(args.get("kd", 0.0))
            ok = await run(c.set_gains, motor, kp, ki, kd)
            if ok:
                return _ok(f"Gains applied to {motor}: Kp={kp:.5f}  Ki={ki:.5f}  Kd={kd:.5f}")
            return _err("No ACK received — verify serial connection and SCREEN_VCP_TUNER is active.")

        elif name == "set_setpoint":
            c = _require()
            rpm = int(args["rpm"])
            ok = await run(c.set_setpoint, rpm)
            return _ok(f"Setpoint → {rpm:+d} RPM") if ok else _err("No ACK.")

        elif name == "motor_control":
            c = _require()
            action = args["action"].lower()
            fn = {"coast": c.motor_coast, "brake": c.motor_brake, "enable": c.motor_enable}[action]
            ok = await run(fn)
            return _ok(f"Motor: {action}") if ok else _err("No ACK.")

        elif name == "start_telemetry":
            c = _require()
            rate = int(args.get("rate_hz", 50))
            ok = await run(c.start_stream, rate)
            return _ok(f"Streaming at {rate} Hz.") if ok else _err("No ACK.")

        elif name == "stop_telemetry":
            c = _require()
            ok = await run(c.stop_stream)
            return _ok("Stream stopped.") if ok else _err("No ACK.")

        elif name == "get_telemetry":
            c = _require()
            tel = await run(c.get_telemetry, 0.5)
            if tel is None:
                return _err("No frame received. Is streaming active? Call start_telemetry first.")
            return _ok(json.dumps({
                "timestamp_ms": tel.timestamp_ms,
                "sp_rpm":       tel.sp_rpm,
                "pv_l_rpm":     tel.pv_l_rpm,
                "pv_r_rpm":     tel.pv_r_rpm,
                "err_l":        tel.err_l,
                "err_r":        tel.err_r,
                "pwm_l_pct":    round(tel.pwm_l_pct * 100, 1),
                "pwm_r_pct":    round(tel.pwm_r_pct * 100, 1),
            }, indent=2))

        elif name == "record_step_response":
            c = _require()
            sp   = int(args["setpoint_rpm"])
            dur  = float(args.get("duration_s", 2.0))
            rate = int(args.get("rate_hz", 50))

            def _record():
                c.motor_enable()
                c.drain_telemetry()
                c.start_stream(rate)
                c.set_setpoint(sp)
                samples = c.record_telemetry(dur)
                c.set_setpoint(0)
                c.motor_coast()
                return samples

            samples = await run(_record)
            metrics = analyze_step(samples, sp)
            raw = [{"t_ms": s.timestamp_ms - samples[0].timestamp_ms,
                    "pv_l": s.pv_l_rpm, "pv_r": s.pv_r_rpm}
                   for s in samples[:500]]

            return _ok(json.dumps({
                "setpoint_rpm": sp,
                "n_samples":    metrics.n_samples,
                "metrics": {
                    "overshoot_pct":    round(metrics.overshoot_pct, 1),
                    "settling_time_s":  round(metrics.settling_time_s, 3),
                    "steady_error_rpm": round(metrics.steady_error, 1),
                    "rise_time_s":      round(metrics.rise_time_s, 3),
                },
                "raw_samples": raw,
            }, indent=2))

        elif name == "run_optimization":
            c = _require()
            motor    = args["motor"]
            target   = int(args["target_rpm"])
            duration = float(args.get("duration_s", 2.0))
            rate     = int(args.get("rate_hz", 50))
            max_iter = int(args.get("max_iter", 30))

            log: list[str] = []
            def progress_cb(i, kp, ki, cost, m):
                log.append(
                    f"#{i:3d}  Kp={kp:.5f}  Ki={ki:.5f}  "
                    f"cost={cost:.2f}  OS={m.overshoot_pct:.1f}%  "
                    f"Ts={m.settling_time_s:.2f}s  Err={m.steady_error:.1f}rpm"
                )

            kp, ki, kd, final = await run(
                optimize_pid, c, motor, target, duration, rate, max_iter, progress_cb
            )
            return _ok(json.dumps({
                "optimal_gains": {
                    "kp": round(kp, 5), "ki": round(ki, 5), "kd": kd
                },
                "final_metrics": {
                    "overshoot_pct":    round(final.overshoot_pct, 1),
                    "settling_time_s":  round(final.settling_time_s, 3),
                    "steady_error_rpm": round(final.steady_error, 1),
                    "rise_time_s":      round(final.rise_time_s, 3),
                },
                "firmware_defines": (
                    f"#define MTR_VEL_KP_DEFAULT  {kp:.4f}f\n"
                    f"#define MTR_VEL_KI_DEFAULT  {ki:.4f}f"
                ),
                "iterations": len(log),
                "log": log,
            }, indent=2))

        else:
            return _err(f"Unknown tool: {name!r}")

    except Exception as exc:
        return _err(f"{type(exc).__name__}: {exc}")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ok(text: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=text)]


def _err(text: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=f"ERROR: {text}")]


# ── Entry point ────────────────────────────────────────────────────────────────

async def run_mcp(pre_connected_client: RobotClient | None = None) -> None:
    """Run the MCP server over stdio (called by main.py)."""
    if pre_connected_client is not None:
        set_client(pre_connected_client)
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())
