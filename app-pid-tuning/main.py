#!/usr/bin/env python3
"""
robot-pid-tuner — PID tuning tool for the STM32 self-balancing robot.

Four independent modes:

  gui      PySide6 graphical interface (plots + gains + optimiser + MCP toggle).
  mcp      Run as an MCP server so Claude can tune the robot autonomously.
  monitor  Rich live telemetry dashboard (read-only, no motor commands).
  tune     Automated Kp/Ki optimisation using Nelder-Mead (scipy).

Quick start:
  pip install -e .

  python main.py gui     --port COM4
  python main.py monitor --port COM4
  python main.py tune    --port COM4 --motor both --target 60
  python main.py mcp     --port COM4
"""

import argparse
import asyncio
import signal
import sys

from pid_tuner.robot_client import RobotClient


# ─── MCP mode ─────────────────────────────────────────────────────────────────

def run_mcp(args: argparse.Namespace) -> None:
    from pid_tuner.mcp_server import run_mcp as _run_mcp, set_client

    client: RobotClient | None = None
    if args.port:
        client = RobotClient(args.port, args.baud)
        client.connect()
        set_client(client)

    try:
        asyncio.run(_run_mcp(client))
    finally:
        if client and client.is_connected():
            client.motor_coast()
            client.disconnect()


# ─── Monitor mode ──────────────────────────────────────────────────────────────

def run_monitor(args: argparse.Namespace) -> None:
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.columns import Columns
    from rich import box

    client = RobotClient(args.port, args.baud)
    client.connect()
    client.motor_enable()
    client.start_stream(args.rate)

    def _err_color(err: int) -> str:
        return "green" if abs(err) < 10 else ("yellow" if abs(err) < 30 else "red")

    def _bar(value: float, width: int = 20) -> str:
        filled = int(abs(value) * width)
        bar = ("█" * filled).ljust(width)
        return f"[{'cyan' if value >= 0 else 'magenta'}]{bar}[/]"

    def build_display(tel, connected: bool) -> Panel:
        status = "[green]●  LIVE[/green]" if connected else "[red]○  NO SIGNAL[/red]"

        tbl = Table(box=box.SIMPLE_HEAVY, show_header=True,
                    header_style="bold bright_white", padding=(0, 1))
        tbl.add_column("Motor",     style="bold", width=7)
        tbl.add_column("SP (RPM)",  justify="right", width=9)
        tbl.add_column("PV (RPM)",  justify="right", width=9)
        tbl.add_column("Error",     justify="right", width=8)
        tbl.add_column("PWM %",     justify="right", width=7)
        tbl.add_column("",          width=22)          # bar

        if tel:
            for side, pv, err, pwm in [
                ("LEFT",  tel.pv_l_rpm, tel.err_l, tel.pwm_l_pct),
                ("RIGHT", tel.pv_r_rpm, tel.err_r, tel.pwm_r_pct),
            ]:
                tbl.add_row(
                    side,
                    f"[cyan]{tel.sp_rpm:+d}[/cyan]",
                    f"{pv:+d}",
                    f"[{_err_color(err)}]{err:+d}[/{_err_color(err)}]",
                    f"{pwm * 100:+.0f}",
                    _bar(pwm),
                )
        else:
            tbl.add_row("LEFT",  "—", "—", "—", "—", "")
            tbl.add_row("RIGHT", "—", "—", "—", "—", "")

        footer = Text(f" {args.port}  {args.rate} Hz  Ctrl-C to quit", style="dim")
        return Panel(tbl, title=f"[bold]ROBOT PID TUNER[/bold]  {status}",
                     subtitle=footer, border_style="bright_blue")

    latest = None
    try:
        with Live(build_display(None, False), refresh_per_second=10,
                  screen=False) as live:
            while True:
                tel = client.get_telemetry(timeout=0.1)
                if tel is not None:
                    latest = tel
                live.update(build_display(latest, latest is not None))
    except KeyboardInterrupt:
        pass
    finally:
        client.motor_coast()
        client.stop_stream()
        client.disconnect()


# ─── Tune mode ─────────────────────────────────────────────────────────────────

def run_tune(args: argparse.Namespace) -> None:
    from rich.console import Console
    from rich.table import Table
    from rich.rule import Rule
    from rich import box
    from pid_tuner.optimizer import optimize_pid

    console = Console()
    client  = RobotClient(args.port, args.baud)

    console.print(Rule("[bold cyan]Robot PID Optimizer[/bold cyan]"))
    console.print(f"  Port    : [yellow]{args.port}[/yellow]")
    console.print(f"  Motor   : [yellow]{args.motor}[/yellow]")
    console.print(f"  Target  : [yellow]{args.target} RPM[/yellow]")
    console.print(f"  Duration: [yellow]{args.duration} s per step[/yellow]")
    console.print(f"  Max iter: [yellow]{args.iter}[/yellow]")
    console.print()

    client.connect()

    def progress_cb(i: int, kp: float, ki: float, cost: float, metrics) -> None:
        os_color  = "green" if metrics.overshoot_pct < 10 else ("yellow" if metrics.overshoot_pct < 25 else "red")
        ts_color  = "green" if metrics.settling_time_s < 1.0 else "yellow"
        console.print(
            f"  [dim]#{i:3d}[/dim]"
            f"  Kp=[cyan]{kp:.5f}[/cyan]"
            f"  Ki=[cyan]{ki:.5f}[/cyan]"
            f"  cost=[white]{cost:.2f}[/white]"
            f"  OS=[{os_color}]{metrics.overshoot_pct:.1f}%[/{os_color}]"
            f"  Ts=[{ts_color}]{metrics.settling_time_s:.2f}s[/{ts_color}]"
            f"  Err=[dim]{metrics.steady_error:.1f}rpm[/dim]"
        )

    try:
        kp, ki, kd, final = optimize_pid(
            client,
            motor=args.motor,
            target_rpm=args.target,
            duration_s=args.duration,
            stream_rate_hz=args.rate,
            max_iter=args.iter,
            progress_cb=progress_cb,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        client.motor_coast()
        client.disconnect()
        return
    finally:
        client.motor_coast()
        client.disconnect()

    console.print()
    console.print(Rule("[bold green]Optimisation complete[/bold green]"))

    result = Table(box=box.ROUNDED, show_header=False, padding=(0, 2))
    result.add_column("param", style="bold white")
    result.add_column("value", justify="right")
    result.add_row("Kp (optimal)",        f"[cyan]{kp:.5f}[/cyan]")
    result.add_row("Ki (optimal)",        f"[cyan]{ki:.5f}[/cyan]")
    result.add_row("Kd",                  f"[dim]{kd:.1f}[/dim]")
    result.add_row("Overshoot",           f"[green]{final.overshoot_pct:.1f} %[/green]")
    result.add_row("Settling time",       f"[green]{final.settling_time_s:.3f} s[/green]")
    result.add_row("Steady-state error",  f"[green]{final.steady_error:.1f} RPM[/green]")
    console.print(result)

    console.print()
    console.print("[bold]Paste into motor_control.h:[/bold]")
    console.print(f"[bright_white]#define MTR_VEL_KP_DEFAULT  {kp:.4f}f[/bright_white]")
    console.print(f"[bright_white]#define MTR_VEL_KI_DEFAULT  {ki:.4f}f[/bright_white]")
    console.print()


# ─── GUI mode ──────────────────────────────────────────────────────────────────

def run_gui(args: argparse.Namespace) -> None:
    from pid_tuner.gui import run_gui as _run_gui
    _run_gui(port=args.port)


# ─── CLI parser ────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="robot-tuner",
        description="STM32 robot PID tuning tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    # ── gui ───────────────────────────────────────────────────────────────────
    p = sub.add_parser("gui", help="PySide6 graphical interface (recommended)")
    p.add_argument("--port", default=None,
                   help="Pre-select serial port on launch (e.g. COM4)")

    # ── mcp ──────────────────────────────────────────────────────────────────
    p = sub.add_parser("mcp", help="Run as MCP server for Claude integration")
    p.add_argument("--port", default=None,
                   help="Optional pre-connect port (Claude can also connect via tool)")
    p.add_argument("--baud", type=int, default=115200)

    # ── monitor ───────────────────────────────────────────────────────────────
    p = sub.add_parser("monitor", help="Live telemetry Rich dashboard")
    p.add_argument("--port", required=True, help="Serial port, e.g. COM4")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--rate", type=int, default=50,
                   help="Telemetry rate Hz (default 50, max 100)")

    # ── tune ──────────────────────────────────────────────────────────────────
    p = sub.add_parser("tune", help="Automated Kp/Ki optimisation (Nelder-Mead)")
    p.add_argument("--port", required=True)
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--motor", choices=["left", "right", "both"], default="both")
    p.add_argument("--target", type=int, default=50,
                   help="Step RPM used as optimisation target (default 50)")
    p.add_argument("--duration", type=float, default=2.0,
                   help="Step-response recording duration in seconds (default 2.0)")
    p.add_argument("--rate", type=int, default=50,
                   help="Telemetry rate Hz during optimisation (default 50)")
    p.add_argument("--iter", type=int, default=30,
                   help="Maximum Nelder-Mead iterations (default 30)")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    dispatch = {"gui": run_gui, "mcp": run_mcp, "monitor": run_monitor, "tune": run_tune}
    dispatch[args.mode](args)


if __name__ == "__main__":
    main()
