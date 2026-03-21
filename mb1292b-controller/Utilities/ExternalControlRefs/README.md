# External Control References

This folder tracks the mainstream PID implementations and robot references evaluated for the project.

The actual upstream sources are not vendored here yet because downloading from GitHub was blocked in this session.

Selected references:

- `CMSIS-DSP`: already available locally under `mb1292b-controller/Drivers/CMSIS`
- `QuickPID`: advanced PID behavior reference
- `ArduPID`: configurable PID behavior reference
- `PID-Library`: STM32-oriented PID wrapper reference
- `Mealy`: STM32 self-balancing robot reference

Recommendation:

- use the local `Utilities/Control` implementation for project code
- borrow ideas from the references when refining anti-windup, tuning, and telemetry
- vendor the upstream projects later when network access is available
