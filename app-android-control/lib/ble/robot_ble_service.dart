import 'dart:async';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'robot_ble_constants.dart';
import '../domain/model/telemetry_frame.dart';

enum BleConnectionState { disconnected, scanning, connecting, ready }

class RobotBleService extends Notifier<BleConnectionState> {
  BluetoothDevice?      _device;
  BluetoothCharacteristic? _cmdChar;
  BluetoothCharacteristic? _telemChar;
  StreamSubscription?   _scanSub;
  // ignore: unused_field
  StreamSubscription?   _connSub;

  final _telemetryController = StreamController<TelemetryFrame>.broadcast();
  Stream<TelemetryFrame> get telemetryStream => _telemetryController.stream;

  @override
  BleConnectionState build() => BleConnectionState.disconnected;

  Future<void> startScan() async {
    if (state == BleConnectionState.scanning) return;
    state = BleConnectionState.scanning;

    await FlutterBluePlus.startScan(timeout: const Duration(seconds: 10));

    _scanSub = FlutterBluePlus.scanResults.listen((results) {
      for (final r in results) {
        if (r.device.platformName == kAdvertisedName) {
          FlutterBluePlus.stopScan();
          _connectTo(r.device);
          break;
        }
      }
    });
  }

  Future<void> stopScan() async {
    await FlutterBluePlus.stopScan();
    _scanSub?.cancel();
    if (state == BleConnectionState.scanning) {
      state = BleConnectionState.disconnected;
    }
  }

  Future<void> _connectTo(BluetoothDevice device) async {
    _device = device;
    state = BleConnectionState.connecting;

    _connSub = device.connectionState.listen((s) {
      if (s == BluetoothConnectionState.disconnected) {
        state = BleConnectionState.disconnected;
        _cmdChar = null;
        _telemChar = null;
      }
    });

    try {
      await device.connect(autoConnect: false);
      await device.requestMtu(128);

      final services = await device.discoverServices();
      final svc = services.where((s) => s.uuid == kRobotServiceUuid).firstOrNull;
      if (svc == null) { await device.disconnect(); return; }

      _cmdChar   = svc.characteristics.where((c) => c.uuid == kCommandCharUuid).firstOrNull;
      _telemChar = svc.characteristics.where((c) => c.uuid == kTelemetryCharUuid).firstOrNull;

      if (_cmdChar == null || _telemChar == null) { await device.disconnect(); return; }

      await _telemChar!.setNotifyValue(true);
      _telemChar!.lastValueStream.listen((bytes) {
        final frame = TelemetryFrame.decode(bytes);
        if (frame != null) _telemetryController.add(frame);
      });

      state = BleConnectionState.ready;
    } catch (_) {
      state = BleConnectionState.disconnected;
    }
  }

  Future<void> disconnect() async {
    await _device?.disconnect();
    state = BleConnectionState.disconnected;
  }

  Future<void> sendCommand(List<int> bytes) async {
    if (_cmdChar == null || state != BleConnectionState.ready) return;
    await _cmdChar!.write(bytes, withoutResponse: true);
  }

  Future<void> sendDrive(double speed, double turn) =>
      sendCommand(encodeDrive(speed, turn));

  Future<void> sendEmergencyStop() => sendCommand(encodeEmergencyStop());
  Future<void> sendResume()        => sendCommand(encodeResume());
}

final robotBleProvider =
    NotifierProvider<RobotBleService, BleConnectionState>(RobotBleService.new);

final telemetryStreamProvider = StreamProvider<TelemetryFrame>((ref) {
  return ref.watch(robotBleProvider.notifier).telemetryStream;
});
