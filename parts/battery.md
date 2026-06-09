# Batterie — 12V 3800mAh Ni-MH

## Caractéristiques électriques

| Paramètre       | Valeur         |
|-----------------|----------------|
| Tension nominale | 12V           |
| Capacité        | 3800 mAh       |
| Chimie          | Ni-MH          |
| Connecteur      | Jack DC barillet (câbles rouge/noir) |

## Dimensions physiques

| Paramètre             | Valeur    |
|-----------------------|-----------|
| Section transversale  | Ovale     |
| Largeur (grand axe)   | 50 mm     |
| Hauteur (petit axe)   | 25 mm     |
| Longueur              | 215 mm    |

```
Vue de face (section ovale) :
        50 mm
   ┌────────────┐
   │            │  25 mm
   └────────────┘

Vue de dessus :
   ╔══════════════════════════════════════════╗
   ║                                          ║ ← câbles sur ce côté
   ╚══════════════════════════════════════════╝
   │←──────────────── 215 mm ────────────────→│
                                    ↑
                           câbles d'alimentation
                           (sortent vers le centre du robot)
```

## Montage sur le robot

- Positionnée **en haut du châssis** (centre de masse élevé = chute plus lente = meilleur contrôle)
- Axe longitudinal **parallèle à l'axe des roues** (perpendiculaire à la direction d'avancement)
- Les câbles d'alimentation sortent **vers le centre** (côté électronique)
- Maintenue par un berceau imprimé en 3D (à concevoir)

## Berceau 3D (à concevoir)

Contraintes pour le design OpenSCAD :
- Section intérieure ovale : 51 × 26 mm (+ 1 mm de jeu)
- Longueur utile : 217 mm (+ 2 mm de jeu)
- Passage câbles : encoche sur le côté → centre
- Fixation sur tiges M4 : entraxe tiges = **200 mm** (entraxe roues)
