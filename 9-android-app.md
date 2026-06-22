# Android App — Product Vision

An Android app controls the robot and serves as its primary human interface. It connects to the robot via BLE 5.2, leveraging the STM32WB5MMG integrated radio. No intermediary (Raspberry Pi, PC) is involved in the control path: the smartphone talks directly to the robot.

The app targets **Android 10 and above** (API level 29+), covering the vast majority of active Android devices. Portrait orientation is the primary layout; landscape is optional.

---

## Connection

The app scans for nearby BLE devices and presents a list filtered to the robot's advertised name. The user connects with a single tap. Once paired, the bond is remembered so subsequent sessions connect automatically without re-scanning.

The connection status is always visible in the app (indicator in the header: Connected / Connecting / Disconnected). If the connection drops unexpectedly (robot out of range, battery low, robot fell), the app displays a clear alert and attempts to reconnect automatically with progressive back-off. The user can also trigger a manual reconnect.

**On disconnect, the robot stops immediately** — this is enforced by the firmware's built-in BLE timeout safety (200 ms). The app relies on this and does not need to send an explicit stop command on drop.

---

## Safety

A prominent **Emergency Stop button** is always visible on every screen of the app, regardless of which control mode or panel is active. Tapping it sends an immediate stop command to the robot and disables all control inputs until the user explicitly re-enables them.

The app also monitors the robot's tilt angle received via telemetry. If the robot tips beyond its safety threshold (reported by the firmware), the app automatically disables control inputs and shows a "Robot fell — reconnect to resume" message.

---

## Telemetry

The app displays live data streamed from the robot at approximately **10–20 Hz**, which is sufficient for smooth UI updates without saturating the BLE link. The telemetry panel shows:

- **Pitch angle** — current tilt in degrees (with a live gauge showing the balance zone)
- **Wheel speed** — left and right wheel velocity in RPM, or a combined average
- **Motor command** — normalized drive output (−1.0 to +1.0) for each side
- **Battery level** — voltage or percentage, with a low-battery warning
- **Control loop status** — whether the balance loop is active, in safety cutoff, or idle

Data is pushed from the robot to the app (BLE notifications); the app does not poll. A scrolling time-series chart for pitch angle and speed gives the user a sense of the robot's dynamic behavior over the last ~10 seconds.

---

## Controls

Three control modes are available, selectable from a toggle in the Control screen. Only one mode is active at a time.

### Virtual Joystick
A thumb-sized on-screen joystick controls forward/backward speed (Y axis) and left/right turning (X axis). The joystick recenters on release, sending a zero-speed command. This is the default mode.

### Buttons & Sliders
Simple directional buttons (Forward, Back, Left, Right, Stop) for precise incremental commands. A speed slider sets the maximum speed for the directional buttons.

### Accelerometer (Tilt Control)
The phone's accelerometer drives the robot: tilting the phone forward moves the robot forward, tilting backward reverses. Left/right phone roll controls turning. A configurable **deadzone** (default ±5°) prevents drift when the phone is held nearly flat. A **sensitivity** setting maps phone tilt angle to robot speed. This mode is opt-in and clearly labeled as "Hands-free mode."

In all modes, the app applies a **command rate limit of 20 Hz** — faster inputs from the accelerometer or rapid UI taps are throttled before transmission, keeping the BLE link stable for telemetry notifications.

---

## Predefined Demo Commands

The app includes a Demo screen with one-tap commands that showcase the robot's capabilities. Each demo runs until completion or until the user taps Stop or the Emergency Stop button.

- **Auto-Spin** — The robot spins on itself for 2 seconds, then stops. The user can set a repeat interval (5 s to 60 s) to loop the demo automatically. Useful as an attention-grabbing demonstration.

- **Back and Forth** — The robot travels forward a set distance, stops, reverses, and repeats. Configurable parameters:
  - Distance (0.2 m to 2.0 m)
  - Speed (slow / medium / fast)
  The robot uses encoder-based dead reckoning for distance estimation; no absolute positioning is assumed.

- **Sinusoidal Sweep** — The robot oscillates laterally in a smooth sine-wave pattern, demonstrating turning agility. Configurable parameters:
  - Sweep width (how far left/right)
  - Period (how fast the oscillation repeats)
  > Note: A full figure-8 path (as originally envisioned) requires closed-loop odometry which is beyond the current sensor suite. The sinusoidal sweep delivers a visually compelling demo without that dependency.

---

## Settings

A dedicated Settings screen covers:

- **Robot name** — custom label shown in scan results and the app header
- **Auto-reconnect** — on/off toggle, backoff delay
- **Tilt control sensitivity and deadzone** — sliders
- **Demo command parameters** — distance, speed, sweep width, repeat interval (mirrors what is shown inline in the Demo screen)
- **Telemetry chart duration** — 5 s / 10 s / 30 s
- **Units** — metric (m, km/h) or imperial (ft, mph)

---

## Out of Scope (v1)

The following are explicitly deferred to a future version:

- **Parameter tuning** (PID gains, control loop constants) — handled by the PC monitor app over USB/VCP in v1
- **Firmware OTA update** — no BLE DFU in v1
- **Multi-robot control** — single robot only
- **iOS app** — Android only in v1; Flutter migration can enable iOS in v2 if the architecture is kept clean
