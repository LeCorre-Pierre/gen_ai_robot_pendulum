import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_joystick/flutter_joystick.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../ble/robot_ble_service.dart';
import '../../domain/model/telemetry_frame.dart';
import '../widgets/estop_button.dart';

class ControlScreen extends ConsumerStatefulWidget {
  const ControlScreen({super.key});

  @override
  ConsumerState<ControlScreen> createState() => _ControlScreenState();
}

class _ControlScreenState extends ConsumerState<ControlScreen> {
  double _speed = 0.0;
  double _turn  = 0.0;
  Timer? _driveTimer;

  @override
  void initState() {
    super.initState();
    // Send drive at 20 Hz while joystick is active
    _driveTimer = Timer.periodic(const Duration(milliseconds: 50), (_) {
      if (_speed != 0.0 || _turn != 0.0) {
        ref.read(robotBleProvider.notifier).sendDrive(_speed, _turn);
      }
    });
  }

  @override
  void dispose() {
    _driveTimer?.cancel();
    ref.read(robotBleProvider.notifier).sendDrive(0, 0);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final telem = ref.watch(telemetryStreamProvider).valueOrNull;
    final bleState = ref.watch(robotBleProvider);

    if (bleState != BleConnectionState.ready) {
      WidgetsBinding.instance.addPostFrameCallback((_) => context.go('/'));
      return const SizedBox.shrink();
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Contrôle'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: _ConnectionBadge(telem),
          ),
        ],
      ),
      body: Column(
        children: [
          // Telemetry bar
          _TelemetryBar(telem),

          const Divider(height: 1),

          // Pitch gauge
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: _PitchGauge(telem?.pitchDeg ?? 0.0),
          ),

          const Spacer(),

          // Joystick
          Center(
            child: Joystick(
              mode: JoystickMode.all,
              listener: (details) {
                setState(() {
                  _speed = -details.y;  // joystick Y up = forward
                  _turn  =  details.x;
                });
              },
              onStickDragEnd: () {
                setState(() { _speed = 0; _turn = 0; });
                ref.read(robotBleProvider.notifier).sendDrive(0, 0);
              },
            ),
          ),

          const Spacer(),

          // E-stop + Resume
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                const EStopButton(),
                OutlinedButton.icon(
                  onPressed: () => ref.read(robotBleProvider.notifier).sendResume(),
                  icon: const Icon(Icons.play_circle_outline),
                  label: const Text('Resume'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TelemetryBar extends StatelessWidget {
  final TelemetryFrame? t;
  const _TelemetryBar(this.t);

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.bodySmall;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          Text('Pitch: ${t?.pitchDeg.toStringAsFixed(1) ?? '--'}°', style: style),
          Text('L: ${t?.speedLRpm.toStringAsFixed(0) ?? '--'} RPM', style: style),
          Text('R: ${t?.speedRRpm.toStringAsFixed(0) ?? '--'} RPM', style: style),
          Text('Bat: ${t?.batteryV.toStringAsFixed(1) ?? '--'} V', style: style),
        ],
      ),
    );
  }
}

class _PitchGauge extends StatelessWidget {
  final double pitchDeg;
  const _PitchGauge(this.pitchDeg);

  @override
  Widget build(BuildContext context) {
    final clamped = pitchDeg.clamp(-45.0, 45.0) / 45.0;
    final color = pitchDeg.abs() > 30 ? Colors.red
                : pitchDeg.abs() > 15 ? Colors.orange
                : Colors.green;
    return Column(
      children: [
        Text('${pitchDeg.toStringAsFixed(1)}°',
            style: TextStyle(color: color, fontSize: 20, fontWeight: FontWeight.bold)),
        const SizedBox(height: 4),
        SizedBox(
          width: 200,
          child: LinearProgressIndicator(
            value: (clamped + 1) / 2,
            color: color,
            minHeight: 8,
          ),
        ),
      ],
    );
  }
}

class _ConnectionBadge extends StatelessWidget {
  final TelemetryFrame? t;
  const _ConnectionBadge(this.t);

  @override
  Widget build(BuildContext context) {
    final active = t?.balanceActive ?? false;
    return Row(
      children: [
        Icon(Icons.circle, size: 10, color: active ? Colors.green : Colors.orange),
        const SizedBox(width: 4),
        Text(active ? 'Balance ON' : 'En attente',
            style: const TextStyle(fontSize: 12)),
      ],
    );
  }
}
