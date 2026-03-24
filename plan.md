# MCU Implementation Plan

This file tracks the implementation status of the wired engineering interface and its MCU-side dependencies.

Status convention:

- `[TODO]` not implemented yet
- `[DONE]` implemented in the firmware tree

## Phase 1 - Interface foundation

- `[DONE]` Define a dedicated module name for the wired PC interface: `host_link`
- `[DONE]` Create an actionable implementation plan with explicit status markers
- `[DONE]` Reserve `USART1` / ST-Link VCP for framed packets only
- `[DONE]` Disable the legacy text console path on `USART1` to avoid protocol corruption
- `[DONE]` Keep the protocol framing aligned with `4-stlink-vcp-interface.md`

## Phase 2 - Packet transport

- `[DONE]` Create `host_link_protocol.h` with message IDs, framing constants, and flags
- `[DONE]` Implement a byte-wise framed packet parser on `USART1`
- `[DONE]` Implement CRC16 validation on incoming and outgoing frames
- `[DONE]` Implement non-blocking TX using the existing UART DMA path
- `[DONE]` Add request handlers for:
  - `PING`
  - `GET_DEVICE_INFO`
  - `GET_PARAMETER_TABLE`
  - `READ_PARAMETER`
  - `WRITE_PARAMETER`
  - `SAVE_PARAMETERS`
  - `LOAD_PARAMETERS`
  - `SET_STREAM_CONFIG`
  - `GET_STREAM_CONFIG`

## Phase 3 - Parameter model

- `[DONE]` Create a small but stable parameter table for bring-up and tuning
- `[DONE]` Add typed parameter metadata:
  - ID
  - type
  - flags
  - min / max
  - default
  - stable key
- `[DONE]` Implement runtime read/write access with range validation
- `[DONE]` Keep defaults compatible with the selected cascade PID architecture

## Phase 4 - Persistent storage

- `[DONE]` Use the external QSPI flash as the persistence backend
- `[DONE]` Enable the STM32 HAL QSPI module in the CubeIDE project
- `[DONE]` Add the BSP QSPI driver to the build
- `[DONE]` Store parameters in a versioned image with:
  - magic
  - version
  - payload length
  - CRC
- `[DONE]` Implement default fallback when the stored image is invalid

## Phase 5 - Runtime telemetry

- `[DONE]` Add a first telemetry stream for runtime health
- `[DONE]` Allow the PC to enable or disable the stream and set its period
- `[DONE]` Report basic counters useful during bring-up:
  - uptime
  - protocol errors
  - UART RX overruns
  - UART TX drops
  - persistence state

## Phase 6 - Firmware integration

- `[DONE]` Initialize `host_link` during application startup
- `[DONE]` Poll `host_link` from the main application process loop
- `[DONE]` Load persisted parameters during startup
- `[DONE]` Keep the implementation isolated so the future GUI can evolve independently

## Phase 7 - Remaining work

- `[TODO]` Bind every persisted parameter to the actual control loop implementation
- `[TODO]` Expose live IMU, motor, encoder, and safety values in dedicated telemetry streams
- `[TODO]` Emit typed `EVENT`, `FAULT`, and `LOG_TEXT` packets from the real firmware subsystems
- `[TODO]` Add PC-side automated protocol tests and a reference logger
- `[TODO]` Persist additional calibration data beyond control parameters
