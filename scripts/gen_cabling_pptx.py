"""
Generate a PowerPoint presentation explaining the wiring of the inverted pendulum robot.
Boards: MB1292B (STM32WB5MMG) + Arduino Motor Shield Rev3 + DC motors + encoders
"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
import copy

# ─── Color palette ───────────────────────────────────────────────────────────
C_BG        = RGBColor(0x1A, 0x1A, 0x2E)   # dark navy
C_ACCENT    = RGBColor(0x16, 0x21, 0x3E)   # slightly lighter navy
C_BLUE_H    = RGBColor(0x0F, 0x3C, 0x78)   # header blue
C_WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
C_YELLOW    = RGBColor(0xFF, 0xD7, 0x00)
C_GREEN     = RGBColor(0x00, 0xCC, 0x66)
C_RED       = RGBColor(0xFF, 0x44, 0x44)
C_ORANGE    = RGBColor(0xFF, 0x88, 0x00)
C_PURPLE    = RGBColor(0xAA, 0x55, 0xFF)   # PWM wire color
C_GREY      = RGBColor(0xAA, 0xAA, 0xAA)   # DIR wire color
C_CYAN_W    = RGBColor(0x00, 0xBF, 0xFF)   # Brake wire color
C_GREEN_W   = RGBColor(0x00, 0xDD, 0x88)   # Current sense wire color
C_LIGHT_BG  = RGBColor(0x0D, 0x47, 0x9A)   # table row alt

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)

prs = Presentation()
prs.slide_width  = SLIDE_W
prs.slide_height = SLIDE_H


# ─── Helper functions ─────────────────────────────────────────────────────────

def blank_slide(prs):
    blank_layout = prs.slide_layouts[6]  # completely blank
    return prs.slides.add_slide(blank_layout)


def fill_bg(slide, color=C_BG):
    from pptx.util import Inches
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_rect(slide, x, y, w, h, fill_color, line_color=None, line_width=Pt(0)):
    from pptx.util import Pt
    shape = slide.shapes.add_shape(1, x, y, w, h)  # MSO_SHAPE_TYPE.RECTANGLE = 1
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if line_color:
        shape.line.color.rgb = line_color
        shape.line.width = line_width
    else:
        shape.line.fill.background()
    return shape


def add_text_box(slide, text, x, y, w, h,
                 font_size=Pt(14), bold=False, color=C_WHITE,
                 align=PP_ALIGN.LEFT, wrap=True, italic=False):
    txBox = slide.shapes.add_textbox(x, y, w, h)
    tf = txBox.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = font_size
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    return txBox


def add_title_bar(slide, title, subtitle=None):
    # Full-width top bar
    add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(1.2), C_BLUE_H)
    add_text_box(slide, title,
                 Inches(0.3), Inches(0.05), Inches(12), Inches(0.7),
                 font_size=Pt(32), bold=True, color=C_YELLOW,
                 align=PP_ALIGN.LEFT)
    if subtitle:
        add_text_box(slide, subtitle,
                     Inches(0.3), Inches(0.72), Inches(12), Inches(0.45),
                     font_size=Pt(16), bold=False, color=C_WHITE,
                     align=PP_ALIGN.LEFT, italic=True)


def add_section_label(slide, text, x, y, w=Inches(4), h=Inches(0.38),
                       bg=C_BLUE_H, fg=C_YELLOW):
    add_rect(slide, x, y, w, h, bg)
    add_text_box(slide, text, x + Inches(0.08), y + Inches(0.02),
                 w - Inches(0.1), h,
                 font_size=Pt(14), bold=True, color=fg, align=PP_ALIGN.LEFT)


def add_table_manual(slide, headers, rows, x, y, col_widths,
                     row_height=Inches(0.34),
                     header_bg=C_BLUE_H, alt_bg=C_ACCENT,
                     header_fg=C_YELLOW, cell_fg=C_WHITE,
                     font_size=Pt(11), bold_header=True,
                     col_colors=None):
    """Draw a table using rectangles and text boxes (more style control)."""
    total_w = sum(col_widths)
    # header row
    cx = x
    for i, h in enumerate(headers):
        add_rect(slide, cx, y, col_widths[i], row_height, header_bg,
                 line_color=C_WHITE, line_width=Pt(0.5))
        add_text_box(slide, h, cx + Inches(0.05), y + Inches(0.04),
                     col_widths[i] - Inches(0.1), row_height,
                     font_size=font_size, bold=bold_header,
                     color=header_fg, align=PP_ALIGN.CENTER)
        cx += col_widths[i]
    # data rows
    for r, row in enumerate(rows):
        ry = y + row_height * (r + 1)
        bg = alt_bg if r % 2 == 0 else RGBColor(0x0A, 0x28, 0x55)
        cx = x
        for c, cell in enumerate(row):
            cell_color = cell_fg
            if col_colors and c < len(col_colors) and col_colors[c]:
                cell_color = col_colors[c].get(cell, cell_fg)
            add_rect(slide, cx, ry, col_widths[c], row_height, bg,
                     line_color=RGBColor(0x33, 0x55, 0x88), line_width=Pt(0.3))
            add_text_box(slide, str(cell), cx + Inches(0.05), ry + Inches(0.03),
                         col_widths[c] - Inches(0.1), row_height,
                         font_size=font_size, bold=False,
                         color=cell_color, align=PP_ALIGN.LEFT)
            cx += col_widths[c]


def add_bullet_list(slide, items, x, y, w, h, font_size=Pt(13),
                    color=C_WHITE, bullet="•  ", spacing=Inches(0.38)):
    for i, item in enumerate(items):
        add_text_box(slide, bullet + item,
                     x, y + spacing * i, w, spacing,
                     font_size=font_size, color=color)


def add_wire_chip(slide, x, y, label, color):
    w, h = Inches(1.8), Inches(0.36)
    add_rect(slide, x, y, w, h, color, line_color=C_WHITE, line_width=Pt(0.5))
    add_text_box(slide, label, x + Inches(0.05), y + Inches(0.04),
                 w - Inches(0.1), h,
                 font_size=Pt(13), bold=True, color=C_BG,
                 align=PP_ALIGN.CENTER)


def add_card_box(slide, x, y, w, h, title, lines, title_bg=C_BLUE_H,
                 body_bg=C_ACCENT, title_h=Inches(0.42)):
    add_rect(slide, x, y, w, title_h, title_bg,
             line_color=C_YELLOW, line_width=Pt(1))
    add_text_box(slide, title, x + Inches(0.1), y + Inches(0.04),
                 w - Inches(0.2), title_h,
                 font_size=Pt(14), bold=True, color=C_YELLOW,
                 align=PP_ALIGN.CENTER)
    body_h = h - title_h
    add_rect(slide, x, y + title_h, w, body_h, body_bg,
             line_color=C_YELLOW, line_width=Pt(1))
    for i, line in enumerate(lines):
        add_text_box(slide, line,
                     x + Inches(0.12), y + title_h + Inches(0.06) + Inches(0.3)*i,
                     w - Inches(0.24), Inches(0.32),
                     font_size=Pt(11), color=C_WHITE)


# ─── Slide 1 — Title ─────────────────────────────────────────────────────────

slide = blank_slide(prs)
fill_bg(slide, C_BG)

# Big robot icon area (decorative strip)
add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.5), C_BLUE_H)
add_rect(slide, Inches(0), Inches(7.0), SLIDE_W, Inches(0.5), C_BLUE_H)

add_text_box(slide, "ROBOT PENDULE INVERSÉ",
             Inches(1), Inches(1.0), Inches(11), Inches(1.3),
             font_size=Pt(44), bold=True, color=C_YELLOW,
             align=PP_ALIGN.CENTER)

add_text_box(slide, "Guide de Câblage Complet",
             Inches(1), Inches(2.4), Inches(11), Inches(0.8),
             font_size=Pt(28), bold=False, color=C_WHITE,
             align=PP_ALIGN.CENTER)

# Horizontal separator
add_rect(slide, Inches(2), Inches(3.3), Inches(9), Inches(0.05), C_YELLOW)

cards = [
    ("MB1292B\nSTM32WB5MMG", Inches(1.0)),
    ("Motor Shield\nArduino Rev3", Inches(4.0)),
    ("Moteurs DC\n+ Encodeurs", Inches(7.0)),
    ("Alimentation\nBatteries", Inches(10.0)),
]
for label, cx in cards:
    add_rect(slide, cx - Inches(0.7), Inches(3.6), Inches(2.0), Inches(1.5),
             C_BLUE_H, line_color=C_YELLOW, line_width=Pt(1.5))
    add_text_box(slide, label, cx - Inches(0.6), Inches(3.75), Inches(1.8), Inches(1.2),
                 font_size=Pt(13), bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)

add_text_box(slide, "Projet : Self-balancing two-wheeled robot  |  Carte : MB1292B (STM32WB5MMG @ 64 MHz)  |  Version : 1.0",
             Inches(0.5), Inches(6.6), Inches(12.3), Inches(0.5),
             font_size=Pt(11), color=C_GREY, align=PP_ALIGN.CENTER)


# ─── Slide 2 — Architecture globale ──────────────────────────────────────────

slide = blank_slide(prs)
fill_bg(slide, C_BG)
add_title_bar(slide, "Architecture Globale", "Vue d'ensemble des cartes et des flux de signaux")

# Cards layout (y=1.4 to 6.8)
CARD_Y = Inches(1.45)

# MB1292B
add_rect(slide, Inches(0.2), CARD_Y, Inches(3.2), Inches(5.0),
         C_BLUE_H, line_color=C_YELLOW, line_width=Pt(2))
add_text_box(slide, "MB1292B", Inches(0.3), CARD_Y + Inches(0.08), Inches(3.0), Inches(0.5),
             font_size=Pt(18), bold=True, color=C_YELLOW, align=PP_ALIGN.CENTER)
add_text_box(slide, "STM32WB5MMG\nCortex-M4 @ 64 MHz\n+ M0+ BLE 5.2",
             Inches(0.3), CARD_Y + Inches(0.55), Inches(3.0), Inches(0.9),
             font_size=Pt(11), color=C_WHITE, align=PP_ALIGN.CENTER)

mb_features = [
    "• Boucle de contrôle RT (200 Hz)",
    "• IMU ISM330DHCX (I2C3 interne)",
    "• Encodeurs via TIM1 / TIM2",
    "• USART1 → PC (ST-Link VCP)",
    "• BLE 5.2 → Smartphone",
    "• PWM + DIR + BRAKE → Shield",
    "• ADC courant ← Shield",
    "• OLED / RGB / Boutons natifs",
]
for i, f in enumerate(mb_features):
    add_text_box(slide, f, Inches(0.32), CARD_Y + Inches(1.5) + Inches(0.38)*i,
                 Inches(3.05), Inches(0.38), font_size=Pt(10), color=C_WHITE)

# Motor Shield
add_rect(slide, Inches(5.0), CARD_Y, Inches(3.2), Inches(3.5),
         C_ACCENT, line_color=C_ORANGE, line_width=Pt(2))
add_text_box(slide, "Motor Shield Rev3", Inches(5.1), CARD_Y + Inches(0.08), Inches(3.0), Inches(0.5),
             font_size=Pt(16), bold=True, color=C_ORANGE, align=PP_ALIGN.CENTER)
add_text_box(slide, "L298P — 2 canaux, 2 A/canal",
             Inches(5.1), CARD_Y + Inches(0.55), Inches(3.0), Inches(0.4),
             font_size=Pt(11), color=C_WHITE, align=PP_ALIGN.CENTER)
shield_features = [
    "• Reçoit PWM, DIR, BRAKE",
    "• Pilote moteurs gauche & droit",
    "• Fournit mesure courant (analog.)",
    "• Alimentation Vs (puissance)",
    "  et Vss (logique) séparées",
]
for i, f in enumerate(shield_features):
    add_text_box(slide, f, Inches(5.12), CARD_Y + Inches(1.05) + Inches(0.45)*i,
                 Inches(3.0), Inches(0.45), font_size=Pt(11), color=C_WHITE)

# Motors
add_rect(slide, Inches(5.0), CARD_Y + Inches(3.7), Inches(3.2), Inches(1.2),
         C_ACCENT, line_color=C_GREEN, line_width=Pt(2))
add_text_box(slide, "Moteurs DC + Encodeurs", Inches(5.1), CARD_Y + Inches(3.78), Inches(3.0), Inches(0.5),
             font_size=Pt(14), bold=True, color=C_GREEN, align=PP_ALIGN.CENTER)
add_text_box(slide, "29:1 gearbox — 64 CPR — 1856 ticks/tour\nGauche + Droit indépendants",
             Inches(5.1), CARD_Y + Inches(4.25), Inches(3.0), Inches(0.6),
             font_size=Pt(10), color=C_WHITE, align=PP_ALIGN.CENTER)

# Smartphone
add_rect(slide, Inches(9.5), CARD_Y, Inches(3.5), Inches(1.5),
         C_ACCENT, line_color=C_PURPLE, line_width=Pt(2))
add_text_box(slide, "Smartphone", Inches(9.6), CARD_Y + Inches(0.05), Inches(3.3), Inches(0.5),
             font_size=Pt(16), bold=True, color=C_PURPLE, align=PP_ALIGN.CENTER)
add_text_box(slide, "Client BLE 5.2\nCommandes conduite / télémétrie",
             Inches(9.6), CARD_Y + Inches(0.55), Inches(3.3), Inches(0.75),
             font_size=Pt(11), color=C_WHITE, align=PP_ALIGN.CENTER)

# PC
add_rect(slide, Inches(9.5), CARD_Y + Inches(1.8), Inches(3.5), Inches(1.5),
         C_ACCENT, line_color=C_CYAN_W, line_width=Pt(2))
add_text_box(slide, "PC Ingénierie", Inches(9.6), CARD_Y + Inches(1.85), Inches(3.3), Inches(0.5),
             font_size=Pt(16), bold=True, color=C_CYAN_W, align=PP_ALIGN.CENTER)
add_text_box(slide, "ST-Link VCP (USB)\nTuning PID / Télémétrie détaillée",
             Inches(9.6), CARD_Y + Inches(2.35), Inches(3.3), Inches(0.75),
             font_size=Pt(11), color=C_WHITE, align=PP_ALIGN.CENTER)

# Batteries
add_rect(slide, Inches(9.5), CARD_Y + Inches(3.5), Inches(3.5), Inches(1.5),
         C_ACCENT, line_color=C_RED, line_width=Pt(2))
add_text_box(slide, "Alimentation", Inches(9.6), CARD_Y + Inches(3.55), Inches(3.3), Inches(0.5),
             font_size=Pt(16), bold=True, color=C_RED, align=PP_ALIGN.CENTER)
add_text_box(slide, "Batt. puissance → Vs Shield\nBatt. logique → MB1292B + Vss\nMasse commune partagée",
             Inches(9.6), CARD_Y + Inches(4.05), Inches(3.3), Inches(0.9),
             font_size=Pt(10), color=C_WHITE, align=PP_ALIGN.CENTER)

# Arrows / connection labels
conn_labels = [
    # (x, y, label, color)
    (Inches(3.5), CARD_Y + Inches(0.6), "PWM+DIR+BRAKE →", C_ORANGE),
    (Inches(3.5), CARD_Y + Inches(1.0), "← Mesure courant", C_GREEN),
    (Inches(3.5), CARD_Y + Inches(1.4), "Encodeurs →", C_GREEN),
    (Inches(3.5), CARD_Y + Inches(1.8), "BLE 5.2 ↔", C_PURPLE),
    (Inches(3.5), CARD_Y + Inches(2.2), "USB ST-Link ↔", C_CYAN_W),
]
for (cx, cy, lbl, col) in conn_labels:
    add_text_box(slide, lbl, cx, cy, Inches(1.4), Inches(0.38),
                 font_size=Pt(10), bold=True, color=col, align=PP_ALIGN.CENTER)


# ─── Slide 3 — MB1292B signaux ────────────────────────────────────────────────

slide = blank_slide(prs)
fill_bg(slide, C_BG)
add_title_bar(slide, "MB1292B — Signaux d'Interface",
              "STM32WB5MMG · Cortex-M4 @ 64 MHz · BLE 5.2 intégré (M0+)")

# Left column — outputs
add_section_label(slide, "Sorties MB1292B → Motor Shield",
                  Inches(0.2), Inches(1.35), w=Inches(6.0))
headers_out = ["Signal", "Pin STM32", "Connecteur", "Périphérique", "Couleur fil"]
rows_out = [
    ["MOTOR_LEFT_PWM",    "PC1",  "Arduino A3", "LPTIM1_OUT", "Violet"],
    ["MOTOR_LEFT_DIR",    "PD12", "Arduino D2", "GPIO out",   "Gris"],
    ["MOTOR_LEFT_BRAKE",  "PD13", "Arduino D8", "GPIO out",   "Bleu"],
    ["MOTOR_RIGHT_PWM",   "PE0",  "Arduino D6", "TIM16_CH1",  "Violet"],
    ["MOTOR_RIGHT_DIR",   "PE3",  "Arduino D4", "GPIO out",   "Gris"],
    ["MOTOR_RIGHT_BRAKE", "PB2",  "Arduino D7", "GPIO out",   "Bleu"],
]
color_map_wire = {
    "Violet": C_PURPLE, "Gris": C_GREY, "Bleu": C_CYAN_W, "Vert": C_GREEN_W
}
col_colors_out = [None, None, None, None,
                  {k: v for k, v in color_map_wire.items()}]
add_table_manual(slide, headers_out, rows_out,
                 Inches(0.2), Inches(1.75),
                 [Inches(2.5), Inches(0.9), Inches(1.1), Inches(1.15), Inches(0.95)],
                 col_colors=col_colors_out)

# Right column — inputs
add_section_label(slide, "Entrées MB1292B ← Motor Shield / Encodeurs",
                  Inches(6.7), Inches(1.35), w=Inches(6.3))
headers_in = ["Signal", "Pin STM32", "Connecteur", "Périph.", "Couleur"]
rows_in = [
    ["MOTOR_LEFT_CURRENT",  "PA5",  "Arduino A2",    "ADC1_IN10", "Vert"],
    ["MOTOR_RIGHT_CURRENT", "PC3",  "Arduino A0",    "ADC1_IN4",  "Vert"],
    ["ENC_LEFT_CHA",        "PD14", "Arduino D3",    "TIM1_CH1",  "—"],
    ["ENC_LEFT_CHB",        "PD15", "Arduino D9",    "TIM1_CH2",  "—"],
    ["ENC_RIGHT_CHA",       "PA15", "STMod+ pin 14", "TIM2_CH1",  "—"],
    ["ENC_RIGHT_CHB",       "PB3",  "Direct (⚠ SWO)", "TIM2_CH2", "—"],
]
col_colors_in = [None, None, None, None,
                 {k: v for k, v in color_map_wire.items()}]
add_table_manual(slide, headers_in, rows_in,
                 Inches(6.7), Inches(1.75),
                 [Inches(2.3), Inches(0.9), Inches(1.3), Inches(1.1), Inches(0.8)],
                 col_colors=col_colors_in)

# Warning box
add_rect(slide, Inches(0.2), Inches(5.55), Inches(12.9), Inches(0.5),
         RGBColor(0x5C, 0x1C, 0x00), line_color=C_RED, line_width=Pt(1))
add_text_box(slide,
             "⚠  PB3 (ENC_RIGHT_CHB) désactive la trace SWO — OK en Release, nécessite désactivation dans CubeMX"
             "   |   ⚠  PB3 = SWO dans le .ioc par défaut : changer le signal vers TIM2_CH2",
             Inches(0.4), Inches(5.57), Inches(12.5), Inches(0.5),
             font_size=Pt(11), bold=True, color=C_RED)

# Communications section
add_section_label(slide, "Communication externe",
                  Inches(0.2), Inches(6.12), w=Inches(12.9))
headers_com = ["Canal", "Signal", "Pins", "Périphérique", "Description"]
rows_com = [
    ["PC (VCP)", "CTRL_VCP_TX / RX", "PB6 / PB7", "USART1", "ST-Link intégré — pas de câble externe nécessaire"],
    ["Smartphone", "BLE 5.2", "Interne M0+", "BLE stack", "Commandes + télémétrie temps réel"],
]
add_table_manual(slide, headers_com, rows_com,
                 Inches(0.2), Inches(6.52),
                 [Inches(1.3), Inches(2.2), Inches(1.3), Inches(1.4), Inches(6.6)],
                 row_height=Inches(0.38))


# ─── Slide 4 — Arduino Motor Shield Rev3 ─────────────────────────────────────

slide = blank_slide(prs)
fill_bg(slide, C_BG)
add_title_bar(slide, "Arduino Motor Shield Rev3",
              "Pont en H L298P — 2 canaux bidirectionnels — 2 A par canal max")

# Left: shield pinout table
add_section_label(slide, "Broches Motor Shield → câblage vers MB1292B",
                  Inches(0.2), Inches(1.35), w=Inches(7.5))
headers_sh = ["Broche Shield", "Signal Shield", "Signal STM32", "Pin STM32", "Connecteur MB1292B"]
rows_sh = [
    ["PWM A (D3 Arduino)",  "MOTOR_LEFT_PWM",    "MOTOR_LEFT_PWM",    "PC1",  "Arduino A3"],
    ["DIR A (D12 Arduino)", "MOTOR_LEFT_DIR",    "MOTOR_LEFT_DIR",    "PD12", "Arduino D2"],
    ["BRAKE A (D9 Arduino)","MOTOR_LEFT_BRAKE",  "MOTOR_LEFT_BRAKE",  "PD13", "Arduino D8"],
    ["PWM B (D11 Arduino)", "MOTOR_RIGHT_PWM",   "MOTOR_RIGHT_PWM",   "PE0",  "Arduino D6"],
    ["DIR B (D13 Arduino)", "MOTOR_RIGHT_DIR",   "MOTOR_RIGHT_DIR",   "PE3",  "Arduino D4"],
    ["BRAKE B (D8 Arduino)","MOTOR_RIGHT_BRAKE", "MOTOR_RIGHT_BRAKE", "PB2",  "Arduino D7"],
    ["CS A (A0 Arduino)",   "MOTOR_LEFT_CURRENT","MOTOR_LEFT_CURRENT","PA5",  "Arduino A2"],
    ["CS B (A1 Arduino)",   "MOTOR_RIGHT_CURRENT","MOTOR_RIGHT_CURRENT","PC3","Arduino A0"],
]
add_table_manual(slide, headers_sh, rows_sh,
                 Inches(0.2), Inches(1.75),
                 [Inches(2.0), Inches(2.0), Inches(2.0), Inches(0.9), Inches(2.0)],
                 font_size=Pt(10))

# Right: power section
add_section_label(slide, "Alimentation Motor Shield",
                  Inches(8.0), Inches(1.35), w=Inches(5.0))
power_items = [
    ("Vs  (bornes +/−)", "Batterie puissance 12 V", C_RED),
    ("Vss (pin 5 V)",    "Batterie logique ou reg. 5 V", C_ORANGE),
    ("GND",              "Masse commune avec MB1292B", C_GREY),
]
for i, (label, val, col) in enumerate(power_items):
    ry = Inches(1.75) + Inches(0.52)*i
    add_rect(slide, Inches(8.0), ry, Inches(5.0), Inches(0.44),
             C_ACCENT, line_color=col, line_width=Pt(1.5))
    add_text_box(slide, f"{label}  →  {val}",
                 Inches(8.15), ry + Inches(0.06), Inches(4.7), Inches(0.38),
                 font_size=Pt(11), color=col)

add_text_box(slide, "⚠  Masse commune obligatoire entre les deux rails d'alimentation",
             Inches(8.0), Inches(3.4), Inches(5.0), Inches(0.5),
             font_size=Pt(11), bold=True, color=C_RED)

# Right: output connectors
add_section_label(slide, "Sorties moteurs (bornes à vis)",
                  Inches(8.0), Inches(3.9), w=Inches(5.0))
out_items = [
    "MOTOR OUT A+ / A−  →  Moteur gauche (Borne + et −)",
    "MOTOR OUT B+ / B−  →  Moteur droit  (Borne + et −)",
]
for i, item in enumerate(out_items):
    add_text_box(slide, "• " + item,
                 Inches(8.1), Inches(4.3) + Inches(0.42)*i, Inches(4.8), Inches(0.42),
                 font_size=Pt(11), color=C_WHITE)

add_text_box(slide,
             "Note : Le shield est câblé manuellement — il n'est PAS branché en plug-in sur la MB1292B.\n"
             "Les numéros de broches Arduino du shield (D3, D12…) ne correspondent pas aux connecteurs de la MB1292B.\n"
             "Utiliser le tableau ci-contre pour raccorder fil à fil.",
             Inches(8.0), Inches(5.4), Inches(5.1), Inches(1.3),
             font_size=Pt(11), color=C_YELLOW, italic=True)

# Note on signal levels
add_rect(slide, Inches(0.2), Inches(5.55), Inches(7.6), Inches(1.05),
         RGBColor(0x0D, 0x2A, 0x00), line_color=C_GREEN, line_width=Pt(1))
add_text_box(slide,
             "Niveaux logiques :\n"
             "  DIR = 0 → sens A  |  DIR = 1 → sens B\n"
             "  BRAKE = 1 → frein actif (court-circuit bobines)  |  BRAKE = 0 → roue libre\n"
             "  PWM : duty cycle 0–100 % contrôle la vitesse",
             Inches(0.35), Inches(5.6), Inches(7.3), Inches(0.95),
             font_size=Pt(11), color=C_GREEN_W)


# ─── Slide 5 — Encodeurs ──────────────────────────────────────────────────────

slide = blank_slide(prs)
fill_bg(slide, C_BG)
add_title_bar(slide, "Encodeurs — Câblage QEI",
              "2× Motoréducteur 29:1 — Encodeur 64 CPR — Résolution effective 1856 ticks/tour")

# Left encoder
add_section_label(slide, "Encodeur GAUCHE  →  TIM1 (QEI mode)",
                  Inches(0.2), Inches(1.4), w=Inches(6.1))
headers_enc = ["Signal encodeur", "Pin MB1292B", "Connecteur", "Timer"]
rows_enc_l = [
    ["ENC_LEFT_CHA (voie A)", "PD14", "Arduino D3", "TIM1_CH1"],
    ["ENC_LEFT_CHB (voie B)", "PD15", "Arduino D9", "TIM1_CH2"],
    ["VCC  (3.3 V)",          "3.3 V", "Header 3V3",  "—"],
    ["GND",                   "GND",   "Header GND",  "—"],
]
add_table_manual(slide, headers_enc, rows_enc_l,
                 Inches(0.2), Inches(1.82),
                 [Inches(2.7), Inches(1.1), Inches(1.2), Inches(1.2)])

# Right encoder
add_section_label(slide, "Encodeur DROIT  →  TIM2 (QEI mode)",
                  Inches(6.7), Inches(1.4), w=Inches(6.3))
rows_enc_r = [
    ["ENC_RIGHT_CHA (voie A)", "PA15", "STMod+ pin 14", "TIM2_CH1"],
    ["ENC_RIGHT_CHB (voie B)", "PB3",  "Direct ⚠ SWO",  "TIM2_CH2"],
    ["VCC  (3.3 V)",           "3.3 V", "Header 3V3",    "—"],
    ["GND",                    "GND",   "Header GND",    "—"],
]
add_table_manual(slide, headers_enc, rows_enc_r,
                 Inches(6.7), Inches(1.82),
                 [Inches(2.7), Inches(1.1), Inches(1.4), Inches(1.2)])

# Warning
add_rect(slide, Inches(0.2), Inches(3.7), Inches(12.9), Inches(0.72),
         RGBColor(0x5C, 0x1C, 0x00), line_color=C_RED, line_width=Pt(1.5))
add_text_box(slide,
             "⚠  PB3 est le pin SWO de JTAG. Dans le fichier .ioc CubeMX, modifier le signal de PB3 : "
             "SYS_JTDO-SWO  →  TIM2_CH2.\n"
             "   Conséquence : le débogage par trace SWO (ITM) est désactivé. Utiliser USART1 (VCP) pour les traces de debug.",
             Inches(0.4), Inches(3.73), Inches(12.5), Inches(0.65),
             font_size=Pt(11), bold=True, color=C_RED)

# QEI explanation
add_section_label(slide, "Principe du mode QEI (Quadrature Encoder Interface)",
                  Inches(0.2), Inches(4.5), w=Inches(12.9))
qei_text = (
    "TIM1 et TIM2 sont configurés en mode Encoder (SMS = 011). "
    "Les fronts de CHA et CHB sont détectés par le timer hardware — le registre TIMx_CNT reflète la position "
    "absolue sans interruption CPU.\n"
    "Le sens de comptage dépend de la phase relative entre CHA et CHB. "
    "Inverser les deux fils d'un encodeur si le sens est incorrect dans le firmware.\n"
    "TIM1 et TIM2 sont EXCLUSIVEMENT dédiés aux encodeurs — ne pas y affecter de PWM moteur."
)
add_text_box(slide, qei_text,
             Inches(0.3), Inches(4.9), Inches(12.7), Inches(1.6),
             font_size=Pt(12), color=C_WHITE, wrap=True)

# Pinout quadrature diagram (text-art)
add_rect(slide, Inches(0.2), Inches(6.55), Inches(12.9), Inches(0.55),
         C_ACCENT, line_color=C_GREEN, line_width=Pt(1))
add_text_box(slide,
             "Brochage typique encodeur 6 fils : M+  M−  VCC  GND  CHA  CHB"
             "   |   M+/M− → Motor Shield (bornes A ou B)   |   VCC → 3.3 V MB1292B   |   GND → GND commun",
             Inches(0.35), Inches(6.57), Inches(12.5), Inches(0.5),
             font_size=Pt(11), color=C_GREEN_W)


# ─── Slide 6 — Connecteur Arduino header récap ───────────────────────────────

slide = blank_slide(prs)
fill_bg(slide, C_BG)
add_title_bar(slide, "Récapitulatif — Connecteur Arduino Header",
              "Broches utilisées sur la MB1292B pour l'interface avec le Motor Shield et les encodeurs")

# Arduino header table
add_section_label(slide, "Header Arduino de la MB1292B (Digital + Analog)",
                  Inches(0.2), Inches(1.35), w=Inches(8.8))
headers_arduino = ["Pin Arduino", "Pin STM32", "Signal Projet", "Fonction", "Destination"]
rows_arduino = [
    ["A0", "PC3",  "MOTOR_RIGHT_CURRENT_SENSE", "ADC1_IN4  (entrée analog.)",  "← Motor Shield CS B"],
    ["A2", "PA5",  "MOTOR_LEFT_CURRENT_SENSE",  "ADC1_IN10 (entrée analog.)",  "← Motor Shield CS A"],
    ["A3", "PC1",  "MOTOR_LEFT_PWM",            "LPTIM1_OUT 20 kHz (PWM)",     "→ Motor Shield PWM A"],
    ["D2", "PD12", "MOTOR_LEFT_DIR",             "GPIO Output",                 "→ Motor Shield DIR A"],
    ["D3", "PD14", "ENC_LEFT_CHA",              "TIM1_CH1 (QEI)",              "← Encodeur gauche CHA"],
    ["D4", "PE3",  "MOTOR_RIGHT_DIR",            "GPIO Output",                 "→ Motor Shield DIR B"],
    ["D6", "PE0",  "MOTOR_RIGHT_PWM",            "TIM16_CH1 PWM",              "→ Motor Shield PWM B"],
    ["D7", "PB2",  "MOTOR_RIGHT_BRAKE",          "GPIO Output",                 "→ Motor Shield BRAKE B"],
    ["D8", "PD13", "MOTOR_LEFT_BRAKE",           "GPIO Output",                 "→ Motor Shield BRAKE A"],
    ["D9", "PD15", "ENC_LEFT_CHB",              "TIM1_CH2 (QEI)",              "← Encodeur gauche CHB"],
]
add_table_manual(slide, headers_arduino, rows_arduino,
                 Inches(0.2), Inches(1.75),
                 [Inches(1.2), Inches(1.0), Inches(2.6), Inches(2.1), Inches(2.2)],
                 font_size=Pt(10), row_height=Inches(0.35))

# Reserved pins
add_section_label(slide, "Broches RÉSERVÉES — Ne pas utiliser",
                  Inches(0.2), Inches(5.65), w=Inches(5.5), bg=RGBColor(0x5C, 0x1C, 0x00))
reserved = [
    ("D10", "PA4",  "SPI1_NSS — OLED display"),
    ("D11", "PA7",  "SPI1_MOSI — OLED + RGB LED"),
    ("D12", "PB4",  "SPI1_MISO — OLED"),
    ("D13", "PA1",  "SPI1_SCK  — OLED"),
]
for i, (d, stm, fn) in enumerate(reserved):
    add_text_box(slide, f"  {d} ({stm}) → {fn}",
                 Inches(0.2), Inches(6.05) + Inches(0.35)*i, Inches(5.5), Inches(0.35),
                 font_size=Pt(11), color=C_RED)

# STMod+ note
add_section_label(slide, "Connecteur STMod+ (encodeur droit CHA)",
                  Inches(6.0), Inches(5.65), w=Inches(7.0), bg=C_BLUE_H)
add_text_box(slide,
             "PA15 → STMod+ pin 14  :  ENC_RIGHT_CHA  →  TIM2_CH1\n"
             "PB3  → Direct          :  ENC_RIGHT_CHB  →  TIM2_CH2  (⚠ désactive SWO)\n"
             "Ces deux signaux NE sont PAS sur le header Arduino — câblage direct sur le connecteur STMod+ ou pad.",
             Inches(6.0), Inches(6.05), Inches(7.1), Inches(0.9),
             font_size=Pt(11), color=C_WHITE, wrap=True)


# ─── Slide 7 — Alimentation ───────────────────────────────────────────────────

slide = blank_slide(prs)
fill_bg(slide, C_BG)
add_title_bar(slide, "Schéma d'Alimentation",
              "Deux rails indépendants + masse commune — 12 V Ni-MH 3800 mAh")

# Chain diagram (text boxes as blocks)
blocks = [
    # (x, y, w, h, title, body, border_color)
    (Inches(0.3),  Inches(1.5), Inches(2.8), Inches(1.2),
     "Batterie\nPuissance 12 V", "Rail moteurs", C_RED),
    (Inches(0.3),  Inches(3.5), Inches(2.8), Inches(1.2),
     "Batterie\nLogique (12 V)", "Rail logique", C_ORANGE),
    (Inches(3.5),  Inches(1.5), Inches(2.8), Inches(1.2),
     "Motor Shield — Vs", "Borne Vs+ / Vs−\nAlimente L298 puissance", C_RED),
    (Inches(3.5),  Inches(3.5), Inches(2.8), Inches(1.2),
     "Buck 5 V / 3 A", "→ MB1292B (VIN)\n→ Motor Shield Vss", C_ORANGE),
    (Inches(6.8),  Inches(1.5), Inches(2.5), Inches(1.2),
     "Moteurs DC", "Canal A + Canal B\nAlimentés par Vs", C_GREEN),
    (Inches(6.8),  Inches(3.5), Inches(2.5), Inches(1.2),
     "MB1292B", "Alim. via VIN header\n3.3 V régulé interne", C_CYAN_W),
    (Inches(9.7),  Inches(3.5), Inches(2.8), Inches(1.2),
     "Motor Shield Vss", "Logique L298\n(5 V max, typ. 4.5–5.5 V)", C_ORANGE),
    (Inches(0.3),  Inches(5.2), Inches(12.5), Inches(0.6),
     "MASSE COMMUNE", "GND Batterie puissance = GND Batterie logique = GND MB1292B = GND Shield", C_GREY),
]
for (bx, by, bw, bh, ttl, body, col) in blocks:
    th = Inches(0.44)
    add_rect(slide, bx, by, bw, th, col,
             line_color=col, line_width=Pt(1))
    add_text_box(slide, ttl, bx + Inches(0.1), by + Inches(0.04),
                 bw - Inches(0.2), th,
                 font_size=Pt(12), bold=True, color=C_BG, align=PP_ALIGN.CENTER)
    add_rect(slide, bx, by + th, bw, bh - th, C_ACCENT,
             line_color=col, line_width=Pt(1))
    add_text_box(slide, body, bx + Inches(0.1), by + th + Inches(0.06),
                 bw - Inches(0.2), bh - th - Inches(0.06),
                 font_size=Pt(11), color=C_WHITE)

# Key rules
add_section_label(slide, "Règles impératives",
                  Inches(0.3), Inches(6.0), w=Inches(12.8), bg=RGBColor(0x5C, 0x1C, 0x00))
rules = [
    "La masse des deux batteries DOIT être raccordée au même point GND — sinon les niveaux logiques sont flottants.",
    "Le Vs du Motor Shield NE doit PAS alimenter la logique MB1292B — deux rails séparés.",
    "Capacité de découplage (100 µF + 100 nF) au plus près de Vs du shield — spikes de commutation L298.",
]
for i, r in enumerate(rules):
    add_text_box(slide, f"⚠  {r}",
                 Inches(0.3), Inches(6.42) + Inches(0.38)*i, Inches(12.8), Inches(0.38),
                 font_size=Pt(10.5), bold=True, color=C_RED)


# ─── Slide 8 — Convention couleurs fils ──────────────────────────────────────

slide = blank_slide(prs)
fill_bg(slide, C_BG)
add_title_bar(slide, "Convention de Couleurs des Fils",
              "MB1292B → Motor Shield — couleurs standardisées pour le câblage du projet")

wire_defs = [
    ("VIOLET",  C_PURPLE,   "PWM",    "Commande vitesse moteur (duty cycle)", "MOTOR_LEFT_PWM, MOTOR_RIGHT_PWM",   "PC1 → Shield PWM A  |  PE0 → Shield PWM B"),
    ("GRIS",    C_GREY,     "DIR",    "Sens de rotation moteur",               "MOTOR_LEFT_DIR, MOTOR_RIGHT_DIR",   "PD12 → Shield DIR A  |  PE3 → Shield DIR B"),
    ("BLEU",    C_CYAN_W,   "BRAKE",  "Frein moteur actif",                   "MOTOR_LEFT_BRAKE, MOTOR_RIGHT_BRAKE","PD13 → Shield BRAKE A  |  PB2 → Shield BRAKE B"),
    ("VERT",    C_GREEN_W,  "CURRENT","Mesure de courant moteur (retour ADC)", "MOTOR_LEFT_CURRENT, MOTOR_RIGHT_CURRENT","Shield CS A → PA5  |  Shield CS B → PC3"),
]

for i, (color_name, color_rgb, sig_type, desc, signals, pins) in enumerate(wire_defs):
    ry = Inches(1.45) + Inches(1.4)*i
    # Color chip
    add_rect(slide, Inches(0.3), ry, Inches(1.3), Inches(1.1),
             color_rgb, line_color=C_WHITE, line_width=Pt(1.5))
    add_text_box(slide, color_name, Inches(0.3), ry + Inches(0.35), Inches(1.3), Inches(0.5),
                 font_size=Pt(13), bold=True, color=C_BG, align=PP_ALIGN.CENTER)
    # Type badge
    add_rect(slide, Inches(1.8), ry + Inches(0.1), Inches(1.3), Inches(0.5),
             C_BLUE_H, line_color=color_rgb, line_width=Pt(2))
    add_text_box(slide, sig_type, Inches(1.8), ry + Inches(0.15), Inches(1.3), Inches(0.5),
                 font_size=Pt(16), bold=True, color=color_rgb, align=PP_ALIGN.CENTER)
    # Description
    add_text_box(slide, desc, Inches(3.3), ry + Inches(0.05), Inches(4.5), Inches(0.4),
                 font_size=Pt(12), bold=True, color=C_WHITE)
    add_text_box(slide, f"Signaux : {signals}", Inches(3.3), ry + Inches(0.45), Inches(9.7), Inches(0.35),
                 font_size=Pt(11), color=C_GREY)
    add_text_box(slide, f"Broches : {pins}", Inches(3.3), ry + Inches(0.78), Inches(9.7), Inches(0.35),
                 font_size=Pt(11), color=color_rgb)

# Footer tip
add_rect(slide, Inches(0.3), Inches(7.0), Inches(12.8), Inches(0.38), C_ACCENT)
add_text_box(slide,
             "Conseil : étiqueter chaque fil avec le nom du signal (ex. MOTOR_LEFT_PWM) pour faciliter le dépannage.",
             Inches(0.4), Inches(7.03), Inches(12.5), Inches(0.35),
             font_size=Pt(11), color=C_YELLOW, italic=True)


# ─── Slide 9 — Points d'attention / Pièges ───────────────────────────────────

slide = blank_slide(prs)
fill_bg(slide, C_BG)
add_title_bar(slide, "Points d'Attention & Pièges",
              "Erreurs fréquentes à éviter — vérifications avant mise sous tension")

pitfalls = [
    (C_RED, "PB3 / SWO",
     "PB3 est par défaut configuré comme trace SWO (JTAG) dans le fichier .ioc CubeMX.\n"
     "Action : changer le signal PB3 de SYS_JTDO-SWO → TIM2_CH2 dans CubeMX.\n"
     "Impact : le débogage par trace ITM/SWO est désactivé. Utiliser USART1 VCP pour les traces."),
    (C_RED, "PA8 / PA9 — Microphones",
     "Sur la MB1292B, PA8 et PA9 sont connectés aux microphones MEMS internes.\n"
     "Ne JAMAIS les utiliser pour du PWM moteur ou tout autre signal externe."),
    (C_ORANGE, "D10–D13 — SPI OLED",
     "Les pins Arduino D10 (PA4), D11 (PA7), D12 (PB4), D13 (PA1) pilotent l'OLED et la LED RGB.\n"
     "Réservés aux fonctions natives MB1292B — ne pas câbler vers le Motor Shield."),
    (C_ORANGE, "Plug-in Shield",
     "Le Motor Shield N'est PAS branché en plug-in sur la MB1292B.\n"
     "Le câblage est fil à fil : les numéros Arduino du Shield ne correspondent pas aux connecteurs de la carte."),
    (C_YELLOW, "Masse commune",
     "Les GND des deux batteries (puissance et logique) DOIVENT être reliés au même point.\n"
     "Sans masse commune, les seuils logiques sont indéfinis → risque de destruction."),
    (C_YELLOW, "LPTIM1 — PC1",
     "Dans le .ioc d'origine, LPTIM1 est en mode compteur interne (non PWM).\n"
     "Action : reconfigurer LPTIM1 en sortie PWM continue sur PC1 (ARR=3200, PCLK1=64 MHz → 20 kHz)."),
]

cols_per_row = 2
for i, (col, title, body) in enumerate(pitfalls):
    row = i // cols_per_row
    col_i = i % cols_per_row
    px = Inches(0.2) + Inches(6.55)*col_i
    py = Inches(1.4) + Inches(1.82)*row
    pw, ph = Inches(6.3), Inches(1.7)
    # Title bar
    add_rect(slide, px, py, pw, Inches(0.4), col,
             line_color=col, line_width=Pt(1))
    add_text_box(slide, title, px + Inches(0.1), py + Inches(0.04),
                 pw - Inches(0.2), Inches(0.38),
                 font_size=Pt(13), bold=True, color=C_BG, align=PP_ALIGN.LEFT)
    add_rect(slide, px, py + Inches(0.4), pw, ph - Inches(0.4),
             C_ACCENT, line_color=col, line_width=Pt(1))
    add_text_box(slide, body, px + Inches(0.12), py + Inches(0.46),
                 pw - Inches(0.24), ph - Inches(0.5),
                 font_size=Pt(10.5), color=C_WHITE, wrap=True)

# ─── Slide 10 — Checklist câblage ────────────────────────────────────────────

slide = blank_slide(prs)
fill_bg(slide, C_BG)
add_title_bar(slide, "Checklist de Câblage",
              "À compléter avant chaque mise sous tension — cocher dans l'ordre")

checks_left = [
    ("MOTEURS & ENCODEURS", C_GREEN, [
        "M+ et M− moteur gauche → bornes OUT A+ / A− du shield",
        "M+ et M− moteur droit  → bornes OUT B+ / B− du shield",
        "ENC gauche CHA (violet)  → PD14 (Arduino D3)",
        "ENC gauche CHB (violet)  → PD15 (Arduino D9)",
        "ENC droit  CHA → PA15 (STMod+ pin 14)",
        "ENC droit  CHB → PB3  (fil direct — ⚠ SWO désactivé)",
        "VCC encodeurs → 3.3 V MB1292B",
        "GND encodeurs → GND commun",
    ]),
    ("MOTOR SHIELD — COMMANDE", C_ORANGE, [
        "PWM A   : PC1  (A3)  → Shield PWM A    [fil violet]",
        "DIR A   : PD12 (D2)  → Shield DIR A    [fil gris]",
        "BRAKE A : PD13 (D8)  → Shield BRAKE A  [fil bleu]",
        "PWM B   : PE0  (D6)  → Shield PWM B    [fil violet]",
        "DIR B   : PE3  (D4)  → Shield DIR B    [fil gris]",
        "BRAKE B : PB2  (D7)  → Shield BRAKE B  [fil bleu]",
    ]),
]

checks_right = [
    ("MOTOR SHIELD — MESURE COURANT", C_GREEN_W, [
        "CS A → PA5 (Arduino A2)   [fil vert]",
        "CS B → PC3 (Arduino A0)   [fil vert]",
    ]),
    ("ALIMENTATION", C_RED, [
        "Batt. puissance → Vs Motor Shield (bornes Vs+ / Vs−)",
        "Batt. logique → Buck 5 V → VIN MB1292B + Vss Shield",
        "GND Batt. puissance relié à GND Batt. logique",
        "GND commun relié à GND MB1292B et GND Shield",
        "Condensateur 100 µF + 100 nF sur Vs Shield",
    ]),
    ("FIRMWARE / CUBEMX", C_YELLOW, [
        "PB3 reconfiguré : SYS_JTDO-SWO → TIM2_CH2",
        "PC1 reconfiguré : ADCx_IN2 → LPTIM1_OUT (PWM mode)",
        "PB2, PD13, PE3, PD12 : GPIO_Output (pas GPIO_Input)",
        "TIM10 / PE0 : vérifier absence conflit LED RGB / IR",
    ]),
]

def render_checklist(slide, groups, x, w):
    y = Inches(1.45)
    for (group_title, group_color, items) in groups:
        th = Inches(0.38)
        add_rect(slide, x, y, w, th, group_color,
                 line_color=group_color, line_width=Pt(1))
        add_text_box(slide, group_title, x + Inches(0.1), y + Inches(0.04),
                     w - Inches(0.2), th,
                     font_size=Pt(12), bold=True, color=C_BG)
        for item in items:
            ih = Inches(0.33)
            add_rect(slide, x, y + th, w, ih, C_ACCENT,
                     line_color=group_color, line_width=Pt(0.3))
            add_text_box(slide, f"☐  {item}", x + Inches(0.15), y + th + Inches(0.04),
                         w - Inches(0.25), ih,
                         font_size=Pt(10), color=C_WHITE)
            y += ih
        y += Inches(0.08)

render_checklist(slide, checks_left,  x=Inches(0.2),  w=Inches(6.35))
render_checklist(slide, checks_right, x=Inches(6.75), w=Inches(6.35))


# ─── Slide 11 — Vérification fonctionnelle (1/2) ─────────────────────────────

slide = blank_slide(prs)
fill_bg(slide, C_BG)
add_title_bar(slide, "Vérification Fonctionnelle  (1/2)",
              "Encodeurs · IMU · Communication VCP — Tests à effectuer firmware chargé, alimentation ON")

# Helper to draw a function test block
def func_test_block(slide, x, y, w, h, category, color,
                    tests):
    """tests = list of (label, procedure, expected)"""
    # Category header
    th = Inches(0.38)
    add_rect(slide, x, y, w, th, color, line_color=color, line_width=Pt(1))
    add_text_box(slide, category, x + Inches(0.1), y + Inches(0.04),
                 w - Inches(0.2), th, font_size=Pt(13), bold=True, color=C_BG)
    row_h = Inches(0.36)
    col_w = [Inches(0.28), Inches(2.5), Inches(4.2), Inches(3.5)]  # ☐ | test | procédure | attendu
    # sub-header
    sy = y + th
    for ci, (ch, cw) in enumerate([("", col_w[0]), ("Test", col_w[1]),
                                    ("Procédure", col_w[2]), ("Résultat attendu", col_w[3])]):
        cx = x + sum(col_w[:ci])
        add_rect(slide, cx, sy, cw, row_h * 0.75, RGBColor(0x05, 0x20, 0x50),
                 line_color=color, line_width=Pt(0.3))
        add_text_box(slide, ch, cx + Inches(0.04), sy + Inches(0.04),
                     cw - Inches(0.08), row_h * 0.75,
                     font_size=Pt(9), bold=True, color=color, align=PP_ALIGN.CENTER)
    sy += row_h * 0.75
    for r, (label, proc, expected) in enumerate(tests):
        bg = C_ACCENT if r % 2 == 0 else RGBColor(0x0A, 0x28, 0x55)
        cx = x
        for ci, (cell, cw) in enumerate(zip(["☐", label, proc, expected], col_w)):
            add_rect(slide, cx, sy, cw, row_h, bg,
                     line_color=RGBColor(0x22, 0x44, 0x77), line_width=Pt(0.3))
            add_text_box(slide, cell, cx + Inches(0.03), sy + Inches(0.03),
                         cw - Inches(0.06), row_h,
                         font_size=Pt(9), color=C_WHITE if ci > 0 else C_YELLOW,
                         align=PP_ALIGN.CENTER if ci == 0 else PP_ALIGN.LEFT)
            cx += cw
        sy += row_h
    return sy  # next available y

y_cur = Inches(1.42)

y_cur = func_test_block(slide, Inches(0.2), y_cur, Inches(12.9), 0, "ENCODEUR GAUCHE — TIM1 (PD14/PD15)", C_GREEN, [
    ("TIM1 actif",        "Observer TIMx_CNT via debugger ou VCP",          "Compteur figé = 0 à l'arrêt"),
    ("Rotation CW",       "Faire tourner la roue gauche dans sens CW à la main", "TIM1_CNT augmente de ~1856 par tour"),
    ("Rotation CCW",      "Faire tourner la roue gauche dans sens CCW",     "TIM1_CNT diminue (overflow 16-bit normal)"),
    ("Résolution",        "1 tour complet → lire delta TIM1_CNT",          "Delta ≈ 1856 ticks (tolérance ±5 ticks)"),
])
y_cur += Inches(0.12)

y_cur = func_test_block(slide, Inches(0.2), y_cur, Inches(12.9), 0, "ENCODEUR DROIT — TIM2 (PA15/PB3)", C_GREEN, [
    ("TIM2 actif",        "Observer TIM2_CNT via debugger ou VCP",          "Compteur figé = 0 à l'arrêt"),
    ("Rotation CW",       "Faire tourner la roue droite dans sens CW à la main", "TIM2_CNT augmente de ~1856 par tour"),
    ("PB3 SWO désactivé", "Tenter une session trace SWO",                   "Aucune trace SWO — comportement normal"),
])
y_cur += Inches(0.12)

y_cur = func_test_block(slide, Inches(0.2), y_cur, Inches(12.9), 0, "IMU — ISM330DHCX  (I2C3 · PB13 SCL / PB11 SDA · adresse 0x6B)", C_CYAN_W, [
    ("I2C présence",      "HAL_I2C_IsDeviceReady(&hi2c3, 0x6B<<1, 3, 100)", "Retourne HAL_OK — sinon vérifier PB13/PB11"),
    ("Lecture Who Am I",  "Lire registre 0x0F → valeur attendue 0x6B",      "0x6B — sinon I2C3 mal initialisé"),
    ("Accel statique",    "Robot posé à plat, lire ax/ay/az en mg",          "az ≈ ±1000 mg, ax≈ay≈0 (±50 mg)"),
    ("Gyro repos",        "Robot immobile, lire gx/gy/gz en dps",            "Toutes valeurs < ±2 dps (bruit typ.)"),
    ("Détection tilt",    "Incliner le robot à ~30°, lire pitch estimé",     "Pitch ≈ 30° ± 3° — filtre complémentaire OK"),
])
y_cur += Inches(0.12)

func_test_block(slide, Inches(0.2), y_cur, Inches(12.9), 0, "LIAISON VCP — USART1 (PB6 TX / PB7 RX · 115200 baud · ST-Link USB)", C_PURPLE, [
    ("Connexion COM",     "python -m serial.tools.miniterm COM4 115200",     "Port s'ouvre sans erreur"),
    ("Réception texte",   "Le firmware émet un banner au démarrage",         "Texte lisible dans miniterm (pas de caractères parasites)"),
    ("Envoi commande",    "Envoyer trame de test (ex: 0xAA 0x55 …)",        "Firmware accuse réception ou echo visible"),
    ("Protocole framing", "Vérifier SOF1=0xAA, SOF2=0x55, EOF=0x33, CRC16","Pas de CRC error dans les logs firmware"),
])


# ─── Slide 12 — Vérification fonctionnelle (2/2) ─────────────────────────────

slide = blank_slide(prs)
fill_bg(slide, C_BG)
add_title_bar(slide, "Vérification Fonctionnelle  (2/2)",
              "Moteurs · Courant · BLE · Sécurité — Moteurs SURÉLEVÉS lors des tests PWM")

y_cur = Inches(1.42)

y_cur = func_test_block(slide, Inches(0.2), y_cur, Inches(12.9), 0,
    "MOTEUR GAUCHE — LPTIM1_OUT PC1 · DIR PD12 · BRAKE PD13  ⚠  Roues en l'air", C_ORANGE, [
    ("PWM 0 %",           "DIR=0, BRAKE=0, PWM=0 %",                        "Moteur gauche à l'arrêt, silencieux"),
    ("Sens A lent",       "DIR=0, BRAKE=0, PWM=10 %",                       "Roue gauche tourne dans sens A à faible vitesse"),
    ("Sens B lent",       "DIR=1, BRAKE=0, PWM=10 %",                       "Roue gauche tourne dans sens B (inverse)"),
    ("PWM montée",        "DIR=0, rampe PWM 10 %→90 %",                     "Vitesse augmente proportionnellement, pas de à-coup"),
    ("Frein actif",       "BRAKE=1 pendant rotation",                        "Arrêt brutal immédiat (bobines court-circuitées)"),
    ("Roue libre",        "BRAKE=0, PWM=0 % pendant rotation",              "La roue décélère progressivement (pas d'arrêt dur)"),
])
y_cur += Inches(0.12)

y_cur = func_test_block(slide, Inches(0.2), y_cur, Inches(12.9), 0,
    "MOTEUR DROIT — TIM16_CH1 PE0 · DIR PE3 · BRAKE PB2  ⚠  Roues en l'air", C_ORANGE, [
    ("Sens A lent",       "DIR=0, BRAKE=0, PWM=10 %",                       "Roue droite tourne dans sens A"),
    ("Sens B lent",       "DIR=1, BRAKE=0, PWM=10 %",                       "Roue droite tourne dans sens B"),
    ("Symétrie",          "Même commande gauche et droite simultanément",     "Les deux roues tournent dans le même sens à vitesse égale"),
    ("Frein actif",       "BRAKE=1 pendant rotation",                        "Arrêt brutal immédiat"),
])
y_cur += Inches(0.12)

y_cur = func_test_block(slide, Inches(0.2), y_cur, Inches(12.9), 0,
    "MESURE COURANT — ADC1  ·  PA5 = gauche (IN10)  ·  PC3 = droit (IN4)", C_GREEN_W, [
    ("Repos (0 A)",       "Moteurs arrêtés, lire ADC PA5 et PC3",           "Valeurs proches de 0 (< 50 mV typ.)"),
    ("Charge moteur",     "PWM=30 %, lire ADC en courant",                   "Valeur non nulle, cohérente avec charge (ex. 200–800 mV)"),
    ("Unité physique",    "Appliquer facteur V/A du CS L298 (typ. 1 V/A)",   "Courant calculé < 2 A (limite shield)"),
    ("Blocage roue",      "Bloquer la roue à la main, PWM=20 %",             "Courant monte (> 1 A typ.) — test surcourant"),
])
y_cur += Inches(0.12)

y_cur = func_test_block(slide, Inches(0.2), y_cur, Inches(12.9), 0,
    "BLE 5.2 — STM32WB5MMG M0+ intégré", C_PURPLE, [
    ("Advertisement",     "Scanner BLE sur smartphone (ex. nRF Connect)",    "Périphérique 'RobotPendule' visible à < 5 m"),
    ("Connexion",         "Se connecter depuis l'app smartphone",             "Connexion établie, RSSI > −80 dBm"),
    ("Commande test",     "Envoyer commande avant/arrière depuis l'app",      "Firmware reçoit et log la commande via VCP"),
    ("Timeout BLE",       "Couper la connexion BLE (fermer app)",             "Firmware détecte timeout 200 ms → moteurs coupés"),
])
y_cur += Inches(0.12)

func_test_block(slide, Inches(0.2), y_cur, Inches(12.9), 0,
    "SÉCURITÉS FIRMWARE", C_RED, [
    ("Tilt cutoff",       "Incliner le robot au-delà de 45°",                "Moteurs coupés immédiatement (PWM=0, BRAKE=1)"),
    ("Watchdog 50 ms",    "Bloquer la tâche control (simuler deadlock)",      "Reset MCU en < 50 ms — visible par redémarrage VCP"),
    ("3 miss I2C",        "Débrancher I2C3 SDA pendant exécution",           "Moteurs coupés après 3 lectures IMU manquées"),
    ("Remise en marche",  "Remettre robot droit après cutoff tilt",           "Contrôle reprend automatiquement si |tilt| < 45°"),
])


# ─── Save ─────────────────────────────────────────────────────────────────────

OUT = r"d:\Projects\gen_ai_robot_pendulum\cablage_robot_pendule.pptx"
prs.save(OUT)
print(f"Saved: {OUT}")
