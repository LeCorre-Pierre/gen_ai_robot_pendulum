# Dimensions mécaniques du châssis

Mesures physiques du robot (relevées 2026-06-08).

## Géométrie globale

| Paramètre                        | Valeur  | Notes |
|----------------------------------|---------|-------|
| Hauteur totale                   | 350 mm  | axle → sommet |
| Entraxe roues (gauche → droite)  | 200 mm  | centre roue à centre roue |
| Ossature                         | 4× tiges filetées M4 | longueur à déterminer |

## Moteurs (37Dx52L + encodeur)

| Paramètre                | Valeur  |
|--------------------------|---------|
| Diamètre corps moteur    | 37 mm   |
| Longueur corps moteur    | 52 mm   |
| Longueur encodeur        | ~20 mm  |
| Longueur totale          | ~72 mm  |
| Fixation flasque         | 4× M3   |
| Diamètre flasque         | 37 mm   |

Référence complète : [motors-encoders.md](motors-encoders.md)

## Roues

Roues existantes — pas à imprimer.
Référence complète : [wheel.md](wheel.md)

## Électronique

| Composant       | Empreinte (L × l) | Fixation      |
|-----------------|-------------------|---------------|
| MB1292B         | ~80 × 80 mm       | 4× M2.5       |
| Motor Shield R3 | ~80 × 80 mm       | empilé sur MB1292B |

## Batterie

Section ovale 50 × 25 mm, longueur 215 mm, câbles côté centre.
Référence complète : [battery.md](battery.md)

## Structure 3D cible

```
Z=350mm  ┌─────────────────────┐  Berceau batterie
         │  Batterie Ni-MH     │  (ovale 50×25, L=215mm)
Z=220mm  ├─────────────────────┤  Plateau électronique
         │  MB1292B            │  (MB1292B + Motor Shield)
         │  Motor Shield       │
Z=100mm  ├─────────────────────┤  Pont moteurs
         │  Moteurs 37D ×2     │  (axle commun, entraxe 200mm)
Z=0mm    └──────O─────────O───┘  Axle roues
```

Ossature : 4 tiges M4 aux 4 coins, reliées par les plateaux imprimés.
