# Android App — Architecture

This document describes the technical architecture of the Android app defined in `9-android-app.md`. It covers the app structure, BLE GATT profile, binary protocols, data flows, and testing strategy. It is the reference for the Android developer and the STM32 firmware developer working on the BLE stack.

---

## Tech Stack

| Concern | Choice | Rationale |
|---|---|---|
| Language | Kotlin | First-class Android support, coroutines, null safety |
| UI | Jetpack Compose | Declarative, no XML, animates well for live data |
| Architecture | MVVM + Clean Architecture | Testable, lifecycle-safe, standard in modern Android |
| Async | Coroutines + Flow | Replaces RxJava; first-class Kotlin, less boilerplate |
| BLE | Nordic Android-BLE-Library | Handles queuing, bonding, reconnect — raw Android BLE API is error-prone |
| DI | Hilt | Standard Dagger wrapper, minimal boilerplate |
| Settings | DataStore (Preferences) | Replaces SharedPreferences; coroutine-native, crash-safe |
| Navigation | Compose NavController | Single-activity, no fragments |
| Min SDK | API 29 (Android 10) | Covers >95% of active devices |

---

## App Architecture

Three layers, strictly one-way dependency: UI → Domain → Data.

```
┌─────────────────────────────────────────────────────┐
│  UI LAYER                                           │
│  Compose screens + ViewModels                       │
│  ConnectionScreen  ControlScreen  TelemetryScreen   │
│  DemoScreen        SettingsScreen                   │
│  Shared: EStopButton  ConnectionBadge               │
└──────────────────────┬──────────────────────────────┘
                       │ StateFlow / events
┌──────────────────────▼──────────────────────────────┐
│  DOMAIN LAYER                                       │
│  Use cases + pure models (no Android dependencies)  │
│  ConnectToRobotUseCase    SendDriveCommandUseCase   │
│  ObserveTelemetryUseCase  RunDemoUseCase            │
│  Models: TelemetryFrame, DriveCommand, DemoCommand  │
│          ConnectionState                            │
└──────────────────────┬──────────────────────────────┘
                       │ Repository interfaces
┌──────────────────────▼──────────────────────────────┐
│  DATA LAYER                                         │
│  BLE: RobotBleManager (Nordic)  BleScanner          │
│       CommandEncoder  TelemetryDecoder  GattProfile │
│  Prefs: AppPreferences (DataStore)                  │
│  RobotRepositoryImpl  SettingsRepositoryImpl        │
└─────────────────────────────────────────────────────┘
```

---

## Package Structure

```
com.robot.pendulum/
├── MainActivity.kt                    // single Activity, hosts NavController
├── RobotApplication.kt                // Hilt app entry point
├── navigation/
│   └── AppNavGraph.kt                 // route definitions, bottom nav
├── ui/
│   ├── theme/                         // MaterialTheme, colors, typography
│   ├── components/                    // EStopButton.kt, ConnectionBadge.kt
│   ├── connection/
│   │   ├── ConnectionScreen.kt
│   │   └── ConnectionViewModel.kt
│   ├── control/
│   │   ├── ControlScreen.kt
│   │   ├── ControlViewModel.kt
│   │   ├── joystick/JoystickComposable.kt
│   │   └── accelerometer/AccelerometerController.kt
│   ├── telemetry/
│   │   ├── TelemetryScreen.kt
│   │   └── TelemetryViewModel.kt
│   ├── demo/
│   │   ├── DemoScreen.kt
│   │   └── DemoViewModel.kt
│   └── settings/
│       ├── SettingsScreen.kt
│       └── SettingsViewModel.kt
├── domain/
│   ├── model/
│   │   ├── ConnectionState.kt
│   │   ├── TelemetryFrame.kt
│   │   ├── DriveCommand.kt
│   │   └── DemoCommand.kt
│   ├── repository/
│   │   ├── RobotRepository.kt         // interface
│   │   └── SettingsRepository.kt      // interface
│   └── usecase/
│       ├── ConnectToRobotUseCase.kt
│       ├── SendDriveCommandUseCase.kt
│       ├── ObserveTelemetryUseCase.kt
│       └── RunDemoUseCase.kt
└── data/
    ├── ble/
    │   ├── RobotBleManager.kt          // extends Nordic BleManager
    │   ├── BleScanner.kt
    │   ├── GattProfile.kt              // all UUID constants
    │   └── protocol/
    │       ├── CommandEncoder.kt
    │       └── TelemetryDecoder.kt
    ├── preferences/
    │   └── AppPreferences.kt           // DataStore wrapper
    └── repository/
        ├── RobotRepositoryImpl.kt
        └── SettingsRepositoryImpl.kt
```

---

## BLE GATT Profile

### Advertising

The robot advertises its presence with:
- **Local name:** `"RobotPendulum"`
- **Advertising interval:** 100 ms (fast mode while unpaired), 1 s (slow mode after first bond)
- The app filters scan results by local name so the user always sees the correct device.

### Services and Characteristics

One custom service covers all communication. A second standard service provides battery level.

**Base UUID pattern:** `A0B0XXXX-C000-4000-8000-000000000001`

| Name | UUID | Properties | Direction |
|---|---|---|---|
| **Robot Service** | `A0B00001-C000-4000-8000-000000000001` | — | — |
| Command | `A0B00002-C000-4000-8000-000000000001` | Write Without Response | App → Robot |
| Telemetry | `A0B00003-C000-4000-8000-000000000001` | Notify | Robot → App |
| **Battery Service** | `0x180F` (standard) | — | — |
| Battery Level | `0x2A19` (standard) | Read + Notify | Robot → App |

**Write Without Response** is used for the Command characteristic — it has lower latency than Write With Response and is acceptable for control commands where the firmware's own safety loop handles protection.

**MTU negotiation:** the app requests MTU = 128 bytes during connection setup. The default 23-byte MTU (20 bytes payload) already fits all frames, but larger MTU reduces per-byte overhead if telemetry is extended later.

---

## Binary Protocols

All values are **little-endian**. Fixed-size frames, no framing overhead needed at the GATT level.

### Command Frame (App → Robot, max 8 bytes)

```
[CMD_ID: uint8] [PAYLOAD: 0–7 bytes]
```

| CMD_ID | Command | Payload | Total |
|---|---|---|---|
| `0x01` | DRIVE | `speed: int8, turn: int8` | 3 bytes |
| `0x02` | EMERGENCY_STOP | _(none)_ | 1 byte |
| `0x03` | RESUME | _(none)_ | 1 byte |
| `0x04` | DEMO_AUTO_SPIN | `repeat_interval_s: uint8` (0 = single shot) | 2 bytes |
| `0x05` | DEMO_BACK_FORTH | `distance_dm: uint8, speed_level: uint8` (0/1/2) | 3 bytes |
| `0x06` | DEMO_SINUS_SWEEP | `width: uint8, period_ds: uint8` | 3 bytes |
| `0x07` | DEMO_STOP | _(none)_ | 1 byte |

`speed` and `turn` in DRIVE: signed int8 in range [−100, +100], mapping to normalized motor command [−1.0, +1.0]. Value 0 = stop.

### Telemetry Frame (Robot → App, 11 bytes, ~10–20 Hz)

```
[SEQ: uint8] [FLAGS: uint8] [PITCH: int16] [SPEED_L: int16] [SPEED_R: int16] [DRIVE: int8] [BATT_MV: uint16]
```

| Field | Type | Scale | Range | Notes |
|---|---|---|---|---|
| SEQ | uint8 | — | 0–255, wraps | Detects missed packets |
| FLAGS | uint8 | bitfield | — | See below |
| PITCH | int16 | × 0.01 ° | ±327 ° | Pitch angle from firmware |
| SPEED_L | int16 | × 0.1 RPM | ±3276 RPM | Left wheel |
| SPEED_R | int16 | × 0.1 RPM | ±3276 RPM | Right wheel |
| DRIVE | int8 | /100.0 | −1.0 to +1.0 | Combined motor command |
| BATT_MV | uint16 | mV | 0–65535 mV | Raw battery voltage |

**FLAGS bitfield:**

| Bit | Name | Meaning when set |
|---|---|---|
| 0 | `BALANCE_ACTIVE` | Control loop is running |
| 1 | `SAFETY_CUTOFF` | Robot tipped — motors off |
| 2 | `DEMO_RUNNING` | A demo command is executing |
| 3 | `ESTOP_ACTIVE` | E-stop commanded, awaiting RESUME |

---

## Connection State Machine

Managed by `RobotBleManager` (extends Nordic `BleManager`). States are exposed as a `StateFlow<ConnectionState>` consumed by all ViewModels.

```
          ┌────────┐
          │  IDLE  │ ◄────────────────────────────────────────┐
          └───┬────┘                                          │
              │ startScan()                                   │
          ┌───▼────────┐                                      │
          │  SCANNING  │                                      │
          └───┬────────┘                                      │
              │ user taps device                              │
          ┌───▼──────────┐                                    │
          │  CONNECTING  │ ◄──────────────────────────────┐  │
          └───┬──────────┘  auto-reconnect (backoff)      │  │
              │ GATT connected                            │  │
          ┌───▼──────────────────┐                        │  │
          │  DISCOVERING_SERVICES│                        │  │
          └───┬──────────────────┘                        │  │
              │ services validated                        │  │
          ┌───▼──────┐                                    │  │
          │   READY  │ ──── unexpected drop ──────────────┘  │
          └───┬──────┘                                        │
              │ user disconnects                              │
          ┌───▼─────────────┐                                 │
          │  DISCONNECTING  │ ─────────────────────────────── ┘
          └─────────────────┘
```

Reconnect back-off: 1 s → 2 s → 4 s → 8 s → 30 s (cap). After 5 failed attempts the app stops and shows a "Connection lost" banner; user must reconnect manually.

Service discovery validates that both the Robot Service and Command/Telemetry characteristics are present. If not found, the connection is dropped with an error.

---

## Data Flows

### Telemetry Path (Robot → UI)

```
BLE radio
  → onCharacteristicChanged() callback [Main thread, Nordic lib]
  → TelemetryDecoder.decode(ByteArray): TelemetryFrame
  → RobotBleManager emits to SharedFlow<TelemetryFrame>
  → RobotRepositoryImpl.telemetryFlow (public SharedFlow, replay=1)
  → ObserveTelemetryUseCase.invoke(): Flow<TelemetryFrame>
  → TelemetryViewModel collects → updates StateFlow<TelemetryUiState>
  → Compose collectAsStateWithLifecycle() → recomposition
```

The `SharedFlow` with `replay=1` ensures a late subscriber (e.g. screen rotation) gets the last known state immediately.

### Command Path (UI → Robot, Drive example)

```
User moves joystick
  → ControlViewModel._rawDriveCommand.value = DriveCommand(speed, turn)
  → Flow.sample(50.ms)  [20 Hz throttle, IO dispatcher]
  → SendDriveCommandUseCase.invoke(cmd)
  → RobotRepositoryImpl.sendDrive(cmd)
  → CommandEncoder.encodeDrive(cmd): ByteArray  [3 bytes]
  → RobotBleManager.writeCharacteristic(COMMAND_CHAR, bytes, WRITE_TYPE_NO_RESPONSE)
  → BLE radio
```

### Emergency Stop Path

E-stop bypasses the 20 Hz throttle and the normal command queue. It is sent immediately via a dedicated `writeCharacteristic` call that jumps the Nordic operation queue using `enqueue()` with priority.

```
User taps EStopButton (any screen)
  → RobotRepository.sendEmergencyStop()   // bypass throttle
  → CommandEncoder.encodeEmergencyStop(): [0x02]
  → BleManager.writeCharacteristic(COMMAND_CHAR, priority=HIGH)
  → ControlViewModel.setEStopActive(true) // disables all input composables
```

### Accelerometer Control Path

```
SensorManager (SENSOR_DELAY_GAME ≈ 50 Hz)
  → AccelerometerController.onSensorChanged()
  → low-pass filter (α = 0.15, smooths noise)
  → apply deadzone (±5° default, from Settings)
  → map to DriveCommand [-100, +100] with sensitivity factor
  → ControlViewModel._rawDriveCommand.value = ...
  → [same throttled path as joystick above]
```

---

## Key Implementation Notes

### Command Throttle

```kotlin
// ControlViewModel.kt
private val _rawDriveCommand = MutableStateFlow(DriveCommand(0, 0))

init {
    viewModelScope.launch {
        _rawDriveCommand
            .sample(50.milliseconds)     // 20 Hz ceiling
            .distinctUntilChanged()      // skip if value unchanged
            .collect { cmd ->
                sendDriveCommandUseCase(cmd)
            }
    }
}
```

`distinctUntilChanged()` prevents redundant BLE writes when the joystick is held still.

### Safety Cutoff Reaction

```kotlin
// TelemetryViewModel.kt
telemetryFlow.collect { frame ->
    if (frame.flags.safetyActif) {
        robotRepository.disableControl()
        _uiState.update { it.copy(showFellAlert = true) }
    }
}
```

### Telemetry Chart

A ring buffer of `N` `TelemetryFrame` values (N = chart_duration × 20 Hz) is maintained in the ViewModel. The Compose chart composable reads this buffer as a `SnapshotStateList` — mutations trigger recomposition only on the chart component, not the whole screen.

---

## Android Permissions

The manifest declares permissions for both API levels. Runtime requests are handled in `ConnectionScreen` before scanning starts.

```xml
<!-- Android 12+ (API 31+) -->
<uses-permission android:name="android.permission.BLUETOOTH_SCAN"
    android:usesPermissionFlags="neverForLocation" />
<uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />

<!-- Android 10–11 (API 29–30) -->
<uses-permission android:name="android.permission.BLUETOOTH" />
<uses-permission android:name="android.permission.BLUETOOTH_ADMIN" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />

<uses-feature android:name="android.hardware.bluetooth_le" android:required="true" />
```

The `neverForLocation` flag on `BLUETOOTH_SCAN` avoids the location permission requirement on API 31+ (Google Play policy: do not request more than necessary). Since the robot is identified by name, not by location, this flag is safe to use.

---

## Key Dependencies (`build.gradle.kts`)

```kotlin
// BLE
implementation("no.nordicsemi.android:ble:2.7.5")

// Jetpack
implementation("androidx.compose.ui:ui")
implementation("androidx.compose.material3:material3")
implementation("androidx.navigation:navigation-compose:2.7.x")
implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.7.x")
implementation("androidx.lifecycle:lifecycle-runtime-compose:2.7.x")
implementation("androidx.datastore:datastore-preferences:1.1.x")

// DI
implementation("com.google.dagger:hilt-android:2.x")
kapt("com.google.dagger:hilt-android-compiler:2.x")

// Charting
implementation("com.patrykandpatrick.vico:compose-m3:1.x")

// Testing
testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.x")
testImplementation("app.cash.turbine:turbine:1.x")   // Flow testing
testImplementation("junit:junit:4.13.2")
androidTestImplementation("androidx.compose.ui:ui-test-junit4")
```

---

## Testing Strategy

| Layer | What to test | How |
|---|---|---|
| `CommandEncoder` | Correct byte output for each command | JUnit5, pure Kotlin, no Android |
| `TelemetryDecoder` | Parse known byte arrays → correct field values, SEQ wrap, FLAGS bits | JUnit5, pure Kotlin |
| ViewModels | State transitions, throttle behavior, E-stop disables control | JUnit5 + Turbine + fake `RobotRepository` |
| Connection state machine | Reconnect backoff, service validation failure path | JUnit5 + fake Nordic callbacks |
| UI — Connection screen | Permission request flow, device list rendering | Compose UI test, instrumented |
| UI — E-stop | Button visible on all screens, disables joystick | Compose UI test, semantic matchers |
| BLE integration | Full round-trip with real firmware | Manual test on device, logged via logcat |

`CommandEncoder` and `TelemetryDecoder` are deliberately pure Kotlin (zero Android imports) so they run on the JVM without an emulator — this is the most valuable test coverage because the protocol is the contract shared with the firmware.

---

## Open Questions (decisions needed before coding)

| # | Question | Impact |
|---|---|---|
| Q1 | Does the firmware implement GATT server with the UUIDs defined here, or does the STM32 team define the UUIDs first? | GattProfile.kt |
=> IDK, i use the only the basic bricks provide by STM32WBM55
| Q2 | Is `distance_dm` (decimetres) sufficient resolution for Back-and-Forth, or should it be centimetres? | CommandEncoder, firmware |
=> The odometrie distance is very precise, go in cm. From 1 to 100.
| Q3 | Should telemetry continue when the app is in background (background BLE), or pause to save battery? | Service vs. bound service decision |
=> Stop telemetry when app is backgrounded. If the user wants to monitor while the app is backgrounded, they can use a separate BLE sniffer app. The robot will continue to run the last command until the app reconnects and resumes telemetry.
| Q4 | Target Compose chart library confirmed (Vico)? Other option: MPAndroidChart wrapper | Chart composable |
=> IDK and i don't care