# Control Utilities

This folder contains the local control implementation selected for the project:

- `pid_controller.[ch]`: fixed-step PID with clamped integrator and derivative-on-measurement
- `cascade_balance_controller.[ch]`: outer velocity loop, inner angle loop, optional yaw loop

Why this exists:

- the project already targets a classic cascade PID architecture
- the STM32 loop needs a small and deterministic implementation
- external libraries could not be vendored in this session because network download was blocked

Expected integration path:

1. estimate pitch angle from the IMU fusion layer
2. compute wheel speed from encoders with `MotorControl`
3. call `CBC_Update(...)` at the control loop rate
4. apply `left_output` and `right_output` through `MTR_SetDifferential(...)`

Suggested first tuning order:

1. tune `angle_pid` with velocity loop disabled
2. tune `velocity_pid` to generate a limited target pitch
3. tune `yaw_pid` last
