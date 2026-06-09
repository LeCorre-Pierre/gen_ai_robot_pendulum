// ============================================================
// Berceau batterie — robot pendule inversé
// Batterie Ni-MH 12V : section ovale 50×25mm, longueur 215mm
// Cables sortent côté +Y (vers centre du robot)
// Fixation : 4 tiges M4, entraxe latéral 200mm
// ============================================================

// --- Paramètres batterie ---
BAT_W  = 50;    // largeur (grand axe ovale), mm
BAT_H  = 25;    // hauteur (petit axe ovale), mm
BAT_L  = 215;   // longueur, mm
JEU    = 1.0;   // jeu radial de chaque côté

// --- Paramètres berceau ---
WALL   = 3.0;   // épaisseur paroi
FOND   = 4.0;   // épaisseur fond
HAUTEUR_PAROI = BAT_H / 2 + WALL;  // demi-hauteur + paroi
REBORD = 5.0;   // hauteur du rebord latéral au-dessus de l'axe neutre

// --- Tiges M4 ---
ROD_D        = 4.2;   // diamètre perçage (M4 + jeu)
ENTRAXE_LAT  = 200;   // entraxe gauche-droite (= entraxe roues)
ENTRAXE_LON  = 60;    // entraxe avant-arrière (à ajuster selon châssis)
LATTE_W      = 12;    // largeur des pattes de fixation
LATTE_H      = 6;     // épaisseur des pattes

// --- Encoche câbles ---
CABLE_W = 12;   // largeur de l'encoche câbles
CABLE_H = 10;   // hauteur de l'encoche câbles

// ============================================================
// Profil ovale (section transversale de la batterie)
// ============================================================
module oval_2d(w, h) {
    // hull de deux cercles de diamètre h, espacés de (w-h) sur X
    hull() {
        translate([-(w - h) / 2, 0]) circle(d = h, $fn = 48);
        translate([ (w - h) / 2, 0]) circle(d = h, $fn = 48);
    }
}

// ============================================================
// Corps principal du berceau (demi-coquille + rebords)
// ============================================================
module corps_berceau() {
    iw = BAT_W + 2 * JEU;   // section intérieure largeur
    ih = BAT_H + 2 * JEU;   // section intérieure hauteur
    ow = iw + 2 * WALL;      // section extérieure largeur
    oh = ih + 2 * WALL;      // section extérieure hauteur
    L  = BAT_L + 4;          // longueur intérieure (2mm jeu chaque bout)
    Lo = L + 2 * WALL;       // longueur extérieure

    difference() {
        // Corps extérieur — extrusion du profil ovale sur la longueur
        translate([0, 0, 0])
        linear_extrude(height = Lo)
            oval_2d(ow, oh);

        // Évidement intérieur batterie (s'arrête à FOND du fond)
        translate([0, 0, FOND])
        linear_extrude(height = Lo)  // on coupe ensuite par le demi-espace
            oval_2d(iw, ih);

        // Couper la moitié supérieure (on garde la coquille inférieure)
        // Z est l'axe longueur, Y est le grand axe, X est l'axe vertical
        // → on veut garder X < 0 (bas du robot)
        translate([0, oh, 0])
        cube([ow * 2, oh * 2, Lo + 1], center = true);

        // Encoche câbles : côté +Y (vers centre robot), centré en longueur
        translate([-CABLE_H / 2, iw / 2 - 1, Lo / 2 - CABLE_W / 2])
        cube([CABLE_H + WALL, WALL + 2, CABLE_W]);
    }
}

// ============================================================
// Pattes de fixation M4 (4 coins)
// Soudées sur les faces extrémités du berceau
// ============================================================
module patte(side_y) {
    // side_y = +1 (droit) ou -1 (gauche)
    ow = BAT_W + 2 * JEU + 2 * WALL;
    Lo = BAT_L + 4 + 2 * WALL;

    // Position X de la tige : centrée sur la paroi basse du berceau
    tx = -(BAT_H / 2 + JEU + WALL / 2);
    ty = side_y * (ENTRAXE_LAT / 2);

    // Avant (Z=0) et arrière (Z=Lo)
    for (tz = [WALL, Lo - WALL]) {
        translate([tx, ty, tz])
        difference() {
            // Bloc de la patte
            cube([LATTE_H, LATTE_W, LATTE_H], center = true);
            // Perçage M4
            rotate([0, 90, 0])
            cylinder(d = ROD_D, h = LATTE_H + 1, center = true, $fn = 24);
        }
    }
}

// ============================================================
// Assemblage final
// ============================================================
module berceau_batterie() {
    corps_berceau();
    patte(+1);
    patte(-1);
}

berceau_batterie();
