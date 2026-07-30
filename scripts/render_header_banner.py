"""Render the AeroGraph README header banner as a PNG.

We can't install cairo or Inkscape on this Windows box, so we hand-roll the
banner in Pillow (matching the SVG in docs/header-banner.svg) and write a
1280x320 PNG to docs/header-banner.png. The SVG remains the canonical
source; the PNG is what GitHub will render reliably.
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path


def font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf",   # Segoe UI Bold
        "C:/Windows/Fonts/segoeui.ttf",    # Segoe UI
        "C:/Windows/Fonts/arialbd.ttf",    # Arial Bold
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/consolab.ttf",   # Consolas Bold
        "C:/Windows/Fonts/consola.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def mono(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/consolab.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/courbd.ttf",
        "C:/Windows/Fonts/cour.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return font(size)


def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


# Palette
BG_TOP    = (0x0A, 0x16, 0x28)   # deep navy
BG_BOT    = (0x1E, 0x3A, 0x5F)   # mid navy
CYAN      = (0x22, 0xD3, 0xEE)
WHITE     = (0xF1, 0xF5, 0xF9)
MUTED     = (0x94, 0xA3, 0xB8)


W, H = 1280, 320
img = Image.new("RGB", (W, H), BG_TOP)
d = ImageDraw.Draw(img, "RGBA")

# Background gradient (deep navy -> mid navy, diagonal)
for y in range(H):
    t = y / H
    d.line([(0, y), (W, y)], fill=lerp_color(BG_TOP, BG_BOT, t * 0.9))

# Faint grid overlay
grid = []
for x in range(0, W, 32):
    d.line([(x, 0), (x, H)], fill=(*CYAN, 12), width=1)
for y in range(0, H, 32):
    d.line([(0, y), (W, y)], fill=(*CYAN, 12), width=1)

# Left: radar circles + crosshairs + center pin
cx, cy = 120, 160
for r, op in [(110, 40), (80, 70), (50, 110)]:
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*CYAN, op), width=1)
d.line([(cx - 110, cy), (cx + 110, cy)], fill=(*CYAN, 60), width=1)
d.line([(cx, cy - 110), (cx, cy + 110)], fill=(*CYAN, 60), width=1)
# Pin: teardrop + center dot
pin_top = cy - 32
d.polygon(
    [(cx, pin_top + 22),
     (cx - 18, pin_top + 10),
     (cx - 18, pin_top),
     (cx, pin_top - 12),
     (cx + 18, pin_top),
     (cx + 18, pin_top + 10)],
    fill=(*CYAN, 230),
)
d.ellipse([cx - 4, pin_top + 4, cx + 4, pin_top + 12], fill=BG_TOP)

# Eyebrow tag (cap badge)
d.rounded_rectangle([290, 84, 470, 106], radius=11, fill=(*CYAN, 30))
d.text((304, 88), "ASSISTIVE INNOVATION 2026", font=mono(11), fill=CYAN)

# Brand wordmark
d.text((290, 130), "AeroGraph", font=font(64), fill=WHITE)

# Tagline (two lines)
d.text((292, 200), "A spatial memory engine", font=font(20), fill=MUTED)
d.text((292, 226), "for visually impaired users.", font=font(20), fill=WHITE)

# Capability chips
chips = [("DETECT", CYAN, 30), ("REMEMBER", CYAN, 30), ("NAVIGATE", CYAN, 30), ("CALL FOR HELP", WHITE, 15)]
x = 290
y = 270
for label, color, op in chips:
    w = 11 * len(label) + 20
    d.rounded_rectangle([x, y, x + w, y + 22], radius=11, fill=(*color, op))
    d.text((x + 10, y + 5), label, font=mono(11), fill=color)
    x += w + 12

# Right: spatial-graph nodes + connecting lines
nodes = [
    (-20, -60, 6,  "door"),
    (50,  -10, 7,  "desk"),
    (-50,  40, 5,  "chair"),
    (80,   60, 6,  "box"),
    (-10,  80, 7,  "keys"),
]
g_cx, g_cy = 960, 160
node_pos = [(g_cx + nx, g_cy + ny, r) for (nx, ny, r, _) in nodes]

# Edges (drawn before nodes so nodes overlay them)
edges = [(0, 1), (0, 2), (1, 3), (1, 4), (2, 4), (3, 4), (0, 3)]
for a, b in edges:
    ax, ay, _ = node_pos[a]
    bx, by, _ = node_pos[b]
    d.line([(ax, ay), (bx, by)], fill=(*CYAN, 90), width=1)

# Nodes
for (nx, ny, r, _), (px, py, _) in zip(nodes, node_pos):
    d.ellipse([px - r, py - r, px + r, py + r], fill=BG_TOP, outline=(*CYAN, 200), width=2)
# Pulse on central node (desk)
d.ellipse([node_pos[1][0] - 14, node_pos[1][1] - 14, node_pos[1][0] + 14, node_pos[1][1] + 14],
          outline=(*CYAN, 60), width=2)
# Labels
for (nx, ny, _, label), (px, py, _) in zip(nodes, node_pos):
    d.text((px - 8, py - 22), label, font=mono(9), fill=MUTED)

# Bottom-right devpost tag
d.text((1080, 296), "DEVPOST.COM \u00B7 AUG 1 2026", font=mono(11), fill=MUTED)

out = Path("docs/header-banner.png")
img.save(out, "PNG", optimize=True)
print(f"saved {out} ({out.stat().st_size} bytes, {W}x{H})")
