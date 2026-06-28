import 'package:flutter_test/flutter_test.dart';
import 'package:robot_pendulum/domain/model/telemetry_frame.dart';

void main() {
  group('TelemetryFrame.decode', () {
    test('decodes a valid 11-byte frame', () {
      // pitch = 150 (→ 1.50°), speedL = 200 (→ 20.0 RPM), speedR = -100 (→ -10.0 RPM)
      // drive = 50 (→ 0.50), batt = 7400 mV
      final bytes = [
        0x01,        // SEQ
        0x01,        // FLAGS: BALANCE_ACTIVE
        0x96, 0x00,  // PITCH = 150 little-endian
        0xC8, 0x00,  // SPEED_L = 200
        0x9C, 0xFF,  // SPEED_R = -100 (int16 signed)
        0x32,        // DRIVE = 50
        0x18, 0x1D,  // BATT_MV = 7448
      ];
      final frame = TelemetryFrame.decode(bytes);
      expect(frame, isNotNull);
      expect(frame!.seq, 1);
      expect(frame.balanceActive, isTrue);
      expect(frame.pitchDeg, closeTo(1.50, 0.01));
      expect(frame.speedLRpm, closeTo(20.0, 0.1));
      expect(frame.speedRRpm, closeTo(-10.0, 0.1));
      expect(frame.driveOutput, closeTo(0.50, 0.01));
    });

    test('returns null for short frame', () {
      expect(TelemetryFrame.decode([0x01, 0x00]), isNull);
    });
  });
}
