/// Telemetry frame decoded from robot BLE notification (11 bytes).
/// Protocol: [SEQ][FLAGS][PITCH_L][PITCH_H][SPD_L_L][SPD_L_H][SPD_R_L][SPD_R_H][DRIVE][BATT_L][BATT_H]
class TelemetryFrame {
  final int seq;
  final bool balanceActive;
  final bool safetyCutoff;
  final bool demoRunning;
  final bool estopActive;
  final double pitchDeg;      // PITCH / 100.0
  final double speedLRpm;     // SPEED_L / 10.0
  final double speedRRpm;     // SPEED_R / 10.0
  final double driveOutput;   // DRIVE / 100.0
  final double batteryMv;     // BATT_MV raw

  const TelemetryFrame({
    required this.seq,
    required this.balanceActive,
    required this.safetyCutoff,
    required this.demoRunning,
    required this.estopActive,
    required this.pitchDeg,
    required this.speedLRpm,
    required this.speedRRpm,
    required this.driveOutput,
    required this.batteryMv,
  });

  static TelemetryFrame? decode(List<int> bytes) {
    if (bytes.length < 11) return null;

    final seq   = bytes[0];
    final flags = bytes[1];
    final pitch = (bytes[2] | (bytes[3] << 8)).toSigned(16) / 100.0;
    final spdL  = (bytes[4] | (bytes[5] << 8)).toSigned(16) / 10.0;
    final spdR  = (bytes[6] | (bytes[7] << 8)).toSigned(16) / 10.0;
    final drive = bytes[8].toSigned(8) / 100.0;
    final batt  = (bytes[9] | (bytes[10] << 8)).toDouble();

    return TelemetryFrame(
      seq:           seq,
      balanceActive: (flags & 0x01) != 0,
      safetyCutoff:  (flags & 0x02) != 0,
      demoRunning:   (flags & 0x04) != 0,
      estopActive:   (flags & 0x08) != 0,
      pitchDeg:      pitch,
      speedLRpm:     spdL,
      speedRRpm:     spdR,
      driveOutput:   drive,
      batteryMv:     batt,
    );
  }

  double get speedAvgRpm => (speedLRpm + speedRRpm) / 2.0;
  double get batteryV    => batteryMv / 1000.0;
}

extension on int {
  int toSigned(int bits) {
    final sign = 1 << (bits - 1);
    return (this & (sign - 1)) - (this & sign);
  }
}
