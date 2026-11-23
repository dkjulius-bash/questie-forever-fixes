"""Procedural icon for "Questie Forever Fixes": a tilted folded map with an
infinity-loop dotted route, a gold map pin (exclamation cut-out) and a green
"fix" badge. Pure Pillow, no fonts, no external artwork. Deterministic.

Run:  .venv\\Scripts\\python.exe -I assets\\icon-source.py
Writes assets/icon-400.png (400x400) and addon/QuestieForeverFixes/icon.png (64x64).
"""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# ---- constants -------------------------------------------------------------
SIZE = 400                 # output size
SS = 4                     # supersample factor
N = SIZE * SS
RADIUS = 0.18              # corner radius, fraction of size
BG_A, BG_B = (0x0f, 0x4c, 0x5c), (0x14, 0x21, 0x3d)
PARCH = [(0xf2, 0xe3, 0xc6), (0xe6, 0xd2, 0xab), (0xd9, 0xc0, 0x8e)]
ROUTE = (0x6b, 0x44, 0x23)
GOLD, GOLD_EDGE = (0xf4, 0xb9, 0x42), (0xc9, 0x8a, 0x1a)
GREEN = (0x3f, 0xb9, 0x50)
TILT_DEG = -9
MAP_CENTER = (185, 208)    # in 400-unit coordinates
MAP_W, MAP_H = 290, 215

ROOT = Path(__file__).resolve().parent.parent
OUT_400 = ROOT / "assets" / "icon-400.png"
OUT_64 = ROOT / "addon" / "QuestieForeverFixes" / "icon.png"


def S(v):
    return v * SS


def pts(points):
    return [(S(x), S(y)) for x, y in points]


def rot(p, c, deg):
    a = math.radians(deg)
    x, y = p[0] - c[0], p[1] - c[1]
    return (c[0] + x * math.cos(a) - y * math.sin(a), c[1] + x * math.sin(a) + y * math.cos(a))


def layer():
    return Image.new("RGBA", (N, N), (0, 0, 0, 0))


def shadow(mask_layer, dx, dy, blur, alpha):
    a = mask_layer.getchannel("A").point(lambda v: int(v * alpha))
    sh = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    sh.putalpha(a)
    sh = ImageChops.offset(sh, S(dx), S(dy))
    return sh.filter(ImageFilter.GaussianBlur(S(blur)))


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ---- background ------------------------------------------------------------
def background():
    g = Image.new("RGB", (256, 256))
    px = g.load()
    for y in range(256):
        for x in range(256):
            px[x, y] = lerp(BG_A, BG_B, (x + y) / 510)
    g = g.resize((N, N), Image.BILINEAR).convert("RGBA")
    v = Image.new("L", (256, 256))
    vp = v.load()
    for y in range(256):
        for x in range(256):
            d = math.hypot(x - 128, y - 128) / 181
            vp[x, y] = int(max(0, d - 0.45) / 0.55 * 110)
    v = v.resize((N, N), Image.BILINEAR)
    dark = Image.new("RGBA", (N, N), (3, 8, 20, 255))
    dark.putalpha(v)
    g = Image.alpha_composite(g, dark)
    m = Image.new("L", (N, N), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, N - 1, N - 1], radius=int(N * RADIUS), fill=255)
    g.putalpha(m)
    return g, m


# ---- map -------------------------------------------------------------------
def map_geometry():
    cx, cy = MAP_CENTER
    x0 = cx - MAP_W / 2
    y0, y1 = cy - MAP_H / 2, cy + MAP_H / 2
    xs = [x0 + MAP_W * i / 3 for i in range(4)]
    top = [y0 + 6, y0 - 6, y0 + 6, y0 - 6]
    bot = [y1 - 6, y1 + 6, y1 - 6, y1 + 6]
    panels = []
    for i in range(3):
        q = [(xs[i], top[i]), (xs[i + 1], top[i + 1]), (xs[i + 1], bot[i + 1]), (xs[i], bot[i])]
        panels.append([rot(p, MAP_CENTER, TILT_DEG) for p in q])
    return panels


def lemniscate(t):
    a = 112
    d = 1 + math.sin(t) ** 2
    return (a * math.cos(t) / d, a * 1.25 * math.sin(t) * math.cos(t) / d)


def route_points(spacing=15.5):
    ts = [i * math.tau / 4000 for i in range(4001)]
    P = [lemniscate(t) for t in ts]
    out, acc = [], spacing
    for i in range(1, len(P)):
        acc += math.dist(P[i], P[i - 1])
        if acc >= spacing:
            acc = 0
            out.append(P[i])
    return out


def draw_map():
    panels = map_geometry()
    lay = layer()
    d = ImageDraw.Draw(lay)
    for i, q in enumerate(panels):
        d.polygon(pts(q), fill=PARCH[i] + (255,))
    shade = layer()
    sd = ImageDraw.Draw(shade)
    for i, q in enumerate(panels):
        sd.polygon(pts(q), fill=(255, 250, 235, 40) if i == 1 else (90, 55, 20, 38))
    lay = Image.alpha_composite(lay, shade)
    crease = layer()
    cd = ImageDraw.Draw(crease)
    for i in range(1, 3):
        a, b = panels[i][0], panels[i][3]
        cd.line([(S(a[0]), S(a[1])), (S(b[0]), S(b[1]))], fill=(70, 40, 10, 150), width=int(S(2.5)))
    crease = crease.filter(ImageFilter.GaussianBlur(S(2.2)))
    crease.putalpha(ImageChops.multiply(crease.getchannel("A"), lay.getchannel("A")))
    lay = Image.alpha_composite(lay, crease)
    od = ImageDraw.Draw(lay)
    for q in panels:
        od.line(pts(q + [q[0]]), fill=(150, 110, 60, 255), width=int(S(1.6)), joint="curve")
    for p in route_points():
        x, y = rot((MAP_CENTER[0] + p[0], MAP_CENTER[1] + p[1]), MAP_CENTER, TILT_DEG)
        r = 4.3
        od.ellipse([S(x - r), S(y - r), S(x + r), S(y + r)], fill=ROUTE + (255,))
    tip = rot((MAP_CENTER[0] + 78, MAP_CENTER[1] + 14), MAP_CENTER, TILT_DEG)
    return lay, tip


# ---- pin -------------------------------------------------------------------
def draw_pin(tip):
    tx, ty = tip
    R = 50               # head radius
    cx, cy = tx, ty - 96  # head centre
    lay = layer()
    d = ImageDraw.Draw(lay)

    def shape(grow, fill):
        r = R + grow
        d.ellipse([S(cx - r), S(cy - r), S(cx + r), S(cy + r)], fill=fill)
        ang = math.asin(R / (cy - ty) * -1) if False else math.asin(R / abs(ty - cy))
        a = math.pi / 2 - ang
        p1 = (cx + r * math.cos(a), cy + r * math.sin(a))
        p2 = (cx - r * math.cos(a), cy + r * math.sin(a))
        d.polygon(pts([p1, (tx, ty + grow * 1.6), p2]), fill=fill)

    shape(4.5, GOLD_EDGE + (255,))
    shape(0, GOLD + (255,))
    sh = layer()
    ImageDraw.Draw(sh).ellipse([S(cx - R * 0.2), S(cy - R * 1.05), S(cx + R * 1.35), S(cy + R * 1.2)],
                               fill=(201, 138, 26, 90))
    sh = sh.filter(ImageFilter.GaussianBlur(S(6)))
    sh.putalpha(ImageChops.multiply(sh.getchannel("A"), lay.getchannel("A")))
    lay = Image.alpha_composite(lay, sh)
    hl = layer()
    ImageDraw.Draw(hl).ellipse([S(cx - 33), S(cy - 36), S(cx - 14), S(cy - 16)], fill=(255, 241, 190, 200))
    lay = Image.alpha_composite(lay, hl.filter(ImageFilter.GaussianBlur(S(2))))
    cut = Image.new("L", (N, N), 255)
    cd = ImageDraw.Draw(cut)
    cd.rounded_rectangle([S(cx - 8), S(cy - 34), S(cx + 8), S(cy + 8)], radius=S(8), fill=0)
    cd.ellipse([S(cx - 9), S(cy + 16), S(cx + 9), S(cy + 34)], fill=0)
    lay.putalpha(ImageChops.multiply(lay.getchannel("A"), cut))
    return lay


# ---- badge -----------------------------------------------------------------
def draw_badge():
    cx, cy, r = 322, 322, 40
    lay = layer()
    d = ImageDraw.Draw(lay)
    d.ellipse([S(cx - r - 4), S(cy - r - 4), S(cx + r + 4), S(cy + r + 4)], fill=(14, 40, 30, 255))
    d.ellipse([S(cx - r), S(cy - r), S(cx + r), S(cy + r)], fill=GREEN + (255,))
    hl = layer()
    ImageDraw.Draw(hl).ellipse([S(cx - r + 6), S(cy - r + 4), S(cx + r - 6), S(cy - 2)], fill=(255, 255, 255, 38))
    lay = Image.alpha_composite(lay, hl.filter(ImageFilter.GaussianBlur(S(3))))
    d = ImageDraw.Draw(lay)
    w, l = 6.5, 22
    d.rounded_rectangle([S(cx - l), S(cy - w), S(cx + l), S(cy + w)], radius=S(w), fill=(255, 255, 255, 255))
    d.rounded_rectangle([S(cx - w), S(cy - l), S(cx + w), S(cy + l)], radius=S(w), fill=(255, 255, 255, 255))
    return lay


def main():
    canvas, mask = background()
    maplay, tip = draw_map()
    canvas = Image.alpha_composite(canvas, shadow(maplay, 4, 9, 7, 0.55))
    canvas = Image.alpha_composite(canvas, maplay)
    pin = draw_pin(tip)
    canvas = Image.alpha_composite(canvas, shadow(pin, 5, 7, 4.5, 0.6))
    canvas = Image.alpha_composite(canvas, pin)
    badge = draw_badge()
    canvas = Image.alpha_composite(canvas, shadow(badge, 2, 4, 3.5, 0.55))
    canvas = Image.alpha_composite(canvas, badge)
    canvas.putalpha(ImageChops.multiply(canvas.getchannel("A"), mask))
    OUT_400.parent.mkdir(parents=True, exist_ok=True)
    canvas.resize((SIZE, SIZE), Image.LANCZOS).save(OUT_400, optimize=True)
    canvas.resize((64, 64), Image.LANCZOS).save(OUT_64, optimize=True)
    print(OUT_400, OUT_64)


if __name__ == "__main__":
    main()
