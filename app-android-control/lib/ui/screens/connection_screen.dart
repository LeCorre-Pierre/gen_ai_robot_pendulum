import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../ble/robot_ble_service.dart';

class ConnectionScreen extends ConsumerWidget {
  const ConnectionScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bleState = ref.watch(robotBleProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Robot Pendulum')),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.bluetooth, size: 80, color: Colors.blue),
            const SizedBox(height: 24),
            Text(
              _stateLabel(bleState),
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 32),
            if (bleState == BleConnectionState.ready) ...[
              FilledButton.icon(
                onPressed: () => context.go('/control'),
                icon: const Icon(Icons.gamepad),
                label: const Text('Contrôler le robot'),
              ),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: () => ref.read(robotBleProvider.notifier).disconnect(),
                child: const Text('Déconnecter'),
              ),
            ] else if (bleState == BleConnectionState.scanning ||
                       bleState == BleConnectionState.connecting) ...[
              const CircularProgressIndicator(),
              const SizedBox(height: 16),
              OutlinedButton(
                onPressed: () => ref.read(robotBleProvider.notifier).stopScan(),
                child: const Text('Annuler'),
              ),
            ] else ...[
              FilledButton.icon(
                onPressed: () => ref.read(robotBleProvider.notifier).startScan(),
                icon: const Icon(Icons.bluetooth_searching),
                label: const Text('Connecter RobotPend'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _stateLabel(BleConnectionState s) => switch (s) {
    BleConnectionState.disconnected => 'Déconnecté',
    BleConnectionState.scanning     => 'Recherche de RobotPend…',
    BleConnectionState.connecting   => 'Connexion en cours…',
    BleConnectionState.ready        => 'Connecté ✓',
  };
}
