import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../ble/robot_ble_service.dart';
import '../../domain/model/telemetry_frame.dart';
import '../widgets/estop_button.dart';

class TelemetryScreen extends ConsumerStatefulWidget {
  const TelemetryScreen({super.key});

  @override
  ConsumerState<TelemetryScreen> createState() => _TelemetryScreenState();
}

class _TelemetryScreenState extends ConsumerState<TelemetryScreen> {
  final List<double> _pitchHistory   = [];
  final List<double> _speedLHistory  = [];
  final List<double> _speedRHistory  = [];
  static const int _maxPoints = 200; // 10 s @ 20 Hz

  @override
  Widget build(BuildContext context) {
    final frame = ref.watch(telemetryStreamProvider);

    frame.whenData((t) {
      _pitchHistory.add(t.pitchDeg);
      _speedLHistory.add(t.speedLRpm);
      _speedRHistory.add(t.speedRRpm);
      if (_pitchHistory.length > _maxPoints) {
        _pitchHistory.removeAt(0);
        _speedLHistory.removeAt(0);
        _speedRHistory.removeAt(0);
      }
    });

    final t = frame.valueOrNull;

    return Scaffold(
      appBar: AppBar(title: const Text('Télémétrie')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Live values table
            _LiveValue('Pitch',     '${t?.pitchDeg.toStringAsFixed(2) ?? '--'}°'),
            _LiveValue('Vitesse G', '${t?.speedLRpm.toStringAsFixed(1) ?? '--'} RPM'),
            _LiveValue('Vitesse D', '${t?.speedRRpm.toStringAsFixed(1) ?? '--'} RPM'),
            _LiveValue('Drive',     t?.driveOutput.toStringAsFixed(3) ?? '--'),
            _LiveValue('Batterie',  '${t?.batteryV.toStringAsFixed(2) ?? '--'} V'),
            const SizedBox(height: 8),
            // Status flags
            _FlagRow(t),
            const SizedBox(height: 16),
            // Pitch chart
            Text('Pitch (10 s)', style: Theme.of(context).textTheme.labelLarge),
            const SizedBox(height: 8),
            Expanded(
              child: _SimpleLineChart(
                values: List<double>.from(_pitchHistory),
                minY: -45, maxY: 45,
                color: Colors.cyanAccent,
              ),
            ),
            const SizedBox(height: 16),
            const EStopButton(),
          ],
        ),
      ),
    );
  }
}

class _LiveValue extends StatelessWidget {
  final String label, value;
  const _LiveValue(this.label, this.value);

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 2),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: const TextStyle(color: Colors.white70)),
        Text(value,  style: const TextStyle(fontWeight: FontWeight.bold)),
      ],
    ),
  );
}

class _FlagRow extends StatelessWidget {
  final TelemetryFrame? t;
  const _FlagRow(this.t);

  @override
  Widget build(BuildContext context) => Wrap(
    spacing: 8,
    children: [
      _Chip('BALANCE', t?.balanceActive ?? false, Colors.green),
      _Chip('SAFETY',  t?.safetyCutoff  ?? false, Colors.red),
      _Chip('E-STOP',  t?.estopActive   ?? false, Colors.orange),
      _Chip('DEMO',    t?.demoRunning   ?? false, Colors.blue),
    ],
  );
}

class _Chip extends StatelessWidget {
  final String label;
  final bool active;
  final Color color;
  const _Chip(this.label, this.active, this.color);

  @override
  Widget build(BuildContext context) => Chip(
    label: Text(label, style: const TextStyle(fontSize: 11)),
    backgroundColor: active ? color.withOpacity(0.3) : Colors.transparent,
    side: BorderSide(color: active ? color : Colors.grey),
    labelStyle: TextStyle(color: active ? color : Colors.grey),
    padding: EdgeInsets.zero,
  );
}

class _SimpleLineChart extends StatelessWidget {
  final List<double> values;
  final double minY, maxY;
  final Color color;
  const _SimpleLineChart({required this.values, required this.minY, required this.maxY, required this.color});

  @override
  Widget build(BuildContext context) => CustomPaint(
    painter: _LinePainter(values: values, minY: minY, maxY: maxY, color: color),
    child: const SizedBox.expand(),
  );
}

class _LinePainter extends CustomPainter {
  final List<double> values;
  final double minY, maxY;
  final Color color;
  const _LinePainter({required this.values, required this.minY, required this.maxY, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    if (values.length < 2) return;
    final paint = Paint()..color = color..strokeWidth = 1.5..style = PaintingStyle.stroke;
    final path = Path();
    final range = maxY - minY;
    for (int i = 0; i < values.length; i++) {
      final x = i / (values.length - 1) * size.width;
      final y = (1 - (values[i] - minY) / range) * size.height;
      i == 0 ? path.moveTo(x, y) : path.lineTo(x, y);
    }
    // Zero line
    final zeroY = (1 - (0 - minY) / range) * size.height;
    canvas.drawLine(Offset(0, zeroY), Offset(size.width, zeroY),
        Paint()..color = Colors.white24..strokeWidth = 1);
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(_LinePainter old) => old.values != values;
}
