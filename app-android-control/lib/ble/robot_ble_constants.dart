import 'package:flutter_blue_plus/flutter_blue_plus.dart';

/// BLE GATT profile — must match emb-sw-ble/STM32_WPAN/App/robot_stm.c
const String kAdvertisedName = 'RobotPend';

final Guid kRobotServiceUuid    = Guid('A0B00001-C000-4000-8000-000000000001');
final Guid kCommandCharUuid     = Guid('A0B00002-C000-4000-8000-000000000001');
final Guid kTelemetryCharUuid   = Guid('A0B00003-C000-4000-8000-000000000001');

/// Command IDs (App → Robot)
const int cmdDrive          = 0x01;
const int cmdEmergencyStop  = 0x02;
const int cmdResume         = 0x03;
const int cmdDemoAutoSpin   = 0x04;
const int cmdDemoBackForth  = 0x05;
const int cmdDemoSinusSweep = 0x06;
const int cmdDemoStop       = 0x07;

/// Build a DRIVE command frame [0x01, speed_int8, turn_int8]
/// speed / turn: double in [-1.0 .. +1.0]
List<int> encodeDrive(double speed, double turn) {
  int s = (speed.clamp(-1.0, 1.0) * 100).round().clamp(-128, 127);
  int t = (turn.clamp(-1.0, 1.0) * 100).round().clamp(-128, 127);
  return [cmdDrive, s & 0xFF, t & 0xFF];
}

List<int> encodeEmergencyStop() => [cmdEmergencyStop];
List<int> encodeResume()        => [cmdResume];
List<int> encodeDemoStop()      => [cmdDemoStop];
