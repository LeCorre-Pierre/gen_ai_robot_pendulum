import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'ui/theme/app_theme.dart';
import 'ui/screens/connection_screen.dart';
import 'ui/screens/control_screen.dart';
import 'ui/screens/telemetry_screen.dart';

void main() {
  runApp(const ProviderScope(child: RobotApp()));
}

final _router = GoRouter(
  routes: [
    ShellRoute(
      builder: (context, state, child) => _Shell(child: child),
      routes: [
        GoRoute(path: '/',        builder: (_, __) => const ConnectionScreen()),
        GoRoute(path: '/control', builder: (_, __) => const ControlScreen()),
        GoRoute(path: '/telem',   builder: (_, __) => const TelemetryScreen()),
      ],
    ),
  ],
);

class RobotApp extends StatelessWidget {
  const RobotApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp.router(
    title: 'Robot Pendulum',
    theme: appTheme,
    routerConfig: _router,
  );
}

class _Shell extends ConsumerWidget {
  final Widget child;
  const _Shell({required this.child});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).uri.toString();
    final idx = switch (location) {
      '/control' => 1,
      '/telem'   => 2,
      _          => 0,
    };

    return Scaffold(
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: idx,
        onDestinationSelected: (i) {
          switch (i) {
            case 0: context.go('/');        break;
            case 1: context.go('/control'); break;
            case 2: context.go('/telem');   break;
          }
        },
        destinations: const [
          NavigationDestination(icon: Icon(Icons.bluetooth), label: 'Connexion'),
          NavigationDestination(icon: Icon(Icons.gamepad),   label: 'Contrôle'),
          NavigationDestination(icon: Icon(Icons.show_chart),label: 'Télémétrie'),
        ],
      ),
    );
  }
}
