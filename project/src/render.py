"""GD TABLEWARE INDUSTRY - RS 3000 - 20 s cinematic commercial renderer.

Composites the real product photographs (cut out by prepare_assets.py) on a
deep black studio stage with 2.5D lighting: directional key light, rim light,
travelling light sweeps, mirror-floor reflections, push-ins and parallax.
This is honest 2D compositing of the supplied photographs - products are only
scaled and moved, never re-shaped, re-coloured or re-textured.

Usage:
  python3 -I src/render.py desktop            # full render -> output/*.mp4
  python3 -I src/render.py mobile
  python3 -I src/render.py desktop --stills 1.5,4.2,15.0   # review frames
  python3 -I src/render.py desktop --logo path/to/hires_logo.png
"""
import argparse
import math
import subprocess
import sys
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import timeline as TL  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PREP = ROOT / "assets" / "prepared"
FONTS = ROOT / "fonts"
BUILD = ROOT / "build"
OUTPUT = ROOT.parent / "output"
DEFAULT_LOGO = ROOT / "assets" / "original" / "GD_logo_official_59x48.jpg"

FPS, DURATION = TL.FPS, TL.DURATION
NFRAMES = int(round(FPS * DURATION))

BLACK = np.array([8, 8, 8], np.float32) / 255        # #080808
GRAPHITE = np.array([37, 37, 37], np.float32) / 255  # #252525
WHITE = np.array([245, 245, 245], np.float32) / 255  # #F5F5F5
RED = np.array([206, 44, 45], np.float32) / 255      # sampled from the official logo
WARM_SPEC = np.array([1.0, 0.97, 0.92], np.float32)
COOL_RIM = np.array([0.86, 0.90, 1.0], np.float32)

SERIF = "CormorantGaramond-Light.ttf"
SERIF_MED = "CormorantGaramond-Medium.ttf"
SANS_L = "Montserrat-Light.ttf"
SANS_M = "Montserrat-Medium.ttf"


# ----------------------------------------------------------------- easing --
def clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def ramp(t, a, b):
    return clamp01((t - a) / (b - a))


def smooth(x):
    x = clamp01(x)
    return x * x * (3 - 2 * x)


def ease_out(x):
    x = clamp01(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp01(x)
    return 0.5 - 0.5 * math.cos(math.pi * x)


def fade_window(t, a, b, fin=0.4, fout=0.3):
    """1 inside [a, b] with smooth fade in after a and fade out before b."""
    return smooth(ramp(t, a, a + fin)) * (1 - smooth(ramp(t, b - fout, b)))


# ----------------------------------------------------------------- assets --
class Asset:
    """Premultiplied float RGBA with a small mip chain for clean downscaling."""

    def __init__(self, path):
        im = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        rgba = cv2.cvtColor(im, cv2.COLOR_BGRA2RGBA).astype(np.float32) / 255
        rgba[..., :3] *= rgba[..., 3:4]
        self.h, self.w = rgba.shape[:2]
        self.levels = [rgba]
        f = 1.0
        while f > 0.15:
            f *= 0.7
            self.levels.append(cv2.resize(rgba, (max(2, round(self.w * f)), max(2, round(self.h * f))),
                                          interpolation=cv2.INTER_AREA))

    def level(self, scale):
        best = self.levels[0]
        for arr in self.levels:
            if arr.shape[1] / self.w >= scale * 0.98:
                best = arr
        return best


ASSETS = {}


def asset(key):
    if key not in ASSETS:
        ASSETS[key] = Asset(PREP / f"{key}.png")
    return ASSETS[key]


def warp(a, scale, cx, cy, W, H):
    arr = a.level(scale)
    lf = arr.shape[1] / a.w
    sw, sh = a.w * scale, a.h * scale
    x0, y0 = cx - sw / 2, cy - sh / 2
    ix0, iy0 = max(0, math.floor(x0)), max(0, math.floor(y0))
    ix1, iy1 = min(W, math.ceil(x0 + sw)), min(H, math.ceil(y0 + sh))
    if ix1 - ix0 < 2 or iy1 - iy0 < 2:
        return None
    s = scale / lf
    M = np.float32([[s, 0, x0 - ix0 + 0.5 * s - 0.5], [0, s, y0 - iy0 + 0.5 * s - 0.5]])
    P = cv2.warpAffine(arr, M, (ix1 - ix0, iy1 - iy0),
                       flags=cv2.INTER_CUBIC if s > 1.0 else cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    P[..., 3] = np.clip(P[..., 3], 0, 1)
    P[..., :3] = np.clip(P[..., :3], 0, P[..., 3:4])
    return P, ix0, iy0, x0, y0, sw, sh


def comp(canvas, rgb, a, ox, oy, opacity=1.0):
    """Premultiplied 'over' of a patch at integer offset, clipped to canvas."""
    H, W = canvas.shape[:2]
    h, w = a.shape[:2]
    x0, y0 = max(0, ox), max(0, oy)
    x1, y1 = min(W, ox + w), min(H, oy + h)
    if x1 <= x0 or y1 <= y0:
        return
    sx, sy = x0 - ox, y0 - oy
    r = rgb[sy:sy + y1 - y0, sx:sx + x1 - x0]
    al = a[sy:sy + y1 - y0, sx:sx + x1 - x0]
    if opacity != 1.0:
        r, al = r * opacity, al * opacity
    region = canvas[y0:y1, x0:x1]
    region *= (1 - al)
    region += r


def draw_product(canvas, key, cx, cy, width, *, expo=1.0, light=(-0.55, -0.8), ambient=0.35,
                 contrast=1.3, sweep=None, rim=0.0, reflect=0.14, opacity=1.0, blur=0.0,
                 floor_glow=0.0):
    """Place a product cutout and light it.

    sweep: (pos, angle_deg, width, strength) - a soft specular band travelling
           across the product in normalized product coordinates.
    """
    H, W = canvas.shape[:2]
    a_ = asset(key)
    scale = width / a_.w
    r = warp(a_, scale, cx, cy, W, H)
    if r is None:
        return
    P, ix0, iy0, x0, y0, sw, sh = r
    h, w = P.shape[:2]
    u = ((np.arange(w, dtype=np.float32) + ix0 - x0) / sw)[None, :]
    v = ((np.arange(h, dtype=np.float32) + iy0 - y0) / sh)[:, None]
    rgb, a = P[..., :3], P[..., 3:4]

    lx, ly = light
    n = math.hypot(lx, ly) or 1
    lx, ly = lx / n, ly / n
    p = (u - 0.5) * lx + (v - 0.5) * ly          # negative = towards the light
    L = ambient + (1 - ambient) * np.clip(0.55 - p * contrast, 0, 1.25)
    rgb = rgb * (L[..., None] * expo)

    if sweep is not None:
        pos, ang, wid, strength = sweep
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        d = (u * ca + v * sa) - pos
        band = np.exp(-(d / wid) ** 2) + 0.25 * np.exp(-(d / (wid * 4)) ** 2)
        rgb = rgb + (band * strength)[..., None] * a * WARM_SPEC

    if rim > 0:
        px = max(1.5, width / 260)
        M = np.float32([[1, 0, -lx * px], [0, 1, -ly * px]])
        shifted = cv2.warpAffine(a[..., 0], M, (w, h), borderMode=cv2.BORDER_CONSTANT)
        edge = np.clip(a[..., 0] - shifted, 0, 1)
        edge = cv2.GaussianBlur(edge, (0, 0), max(0.8, px * 0.5))
        rgb = rgb + (edge * rim)[..., None] * COOL_RIM

    if blur > 0:
        k = cv2.GaussianBlur(np.dstack([rgb, a]), (0, 0), blur)
        rgb, a = k[..., :3], k[..., 3:4]

    rgb = np.clip(rgb, 0, None)
    yb = int(round(y0 + sh - 6 * scale))           # cutouts carry 6px padding
    if floor_glow > 0:
        draw_glow(canvas, cx, yb, width * 0.62, width * 0.09, floor_glow, GRAPHITE * 2.2)
    if reflect > 0 and iy0 + h >= yb - 2:
        # mirror about the floor line: canvas row Y -> 2*yb - Y
        rows = 2 * yb - (iy0 + np.arange(h)[::-1])
        R = rgb[::-1]
        Ra = a[::-1]
        dist = (rows - yb).astype(np.float32)
        g = reflect * np.clip(1 - dist / (0.32 * sh), 0, 1) ** 2
        R = cv2.GaussianBlur(R * g[:, None, None], (0, 0), 1.6)
        Ra = cv2.GaussianBlur(Ra[..., 0] * g[:, None], (0, 0), 1.6)[..., None]
        comp(canvas, R * opacity, Ra * opacity, ix0, int(rows[0]))
    comp(canvas, rgb, a, ix0, iy0, opacity)


def draw_glow(canvas, cx, cy, rx, ry, strength, color):
    H, W = canvas.shape[:2]
    x0, x1 = int(max(0, cx - rx * 2.2)), int(min(W, cx + rx * 2.2))
    y0, y1 = int(max(0, cy - ry * 2.2)), int(min(H, cy + ry * 2.2))
    if x1 <= x0 or y1 <= y0 or strength <= 0:
        return
    xx = (np.arange(x0, x1, dtype=np.float32) - cx)[None, :] / rx
    yy = (np.arange(y0, y1, dtype=np.float32) - cy)[:, None] / ry
    g = np.exp(-(xx * xx + yy * yy) * 1.2) * strength
    canvas[y0:y1, x0:x1] += g[..., None] * color


def draw_macro(canvas, key, focus, scale, panel, drift=(0, 0), t=0.0, sweep=None, expo=1.0):
    """Macro close-up: the real surface enlarged, focus point centred in panel."""
    a_ = asset(key)
    px, py = panel
    fx, fy = focus[0] + drift[0] * t, focus[1] + drift[1] * t
    cx = px - (fx - a_.w / 2) * scale
    cy = py - (fy - a_.h / 2) * scale
    draw_product(canvas, key, cx, cy, a_.w * scale, expo=expo, light=(-0.7, -0.5),
                 ambient=0.55, contrast=0.9, sweep=sweep, rim=0.0, reflect=0.0)


# ------------------------------------------------------------------- text --
@lru_cache(maxsize=512)
def text_mask(text, font, size, tracking):
    f = ImageFont.truetype(str(FONTS / font), size)
    track = tracking * size
    widths = [f.getlength(c) for c in text]
    total = sum(widths) + track * (len(text) - 1)
    asc, desc = f.getmetrics()
    pad = 4
    img = Image.new("L", (int(math.ceil(total)) + 2 * pad, asc + desc + 2 * pad), 0)
    d = ImageDraw.Draw(img)
    x = pad
    for c, wc in zip(text, widths):
        d.text((x, pad), c, font=f, fill=255)
        x += wc + track
    m = np.asarray(img).astype(np.float32) / 255
    # trim to ink bbox vertically so y means cap-top
    rows = np.where(m.max(1) > 0.02)[0]
    m = m[rows.min():rows.max() + 1]
    return m, total


def draw_text(canvas, text, font, size, x, y, *, tracking=0.3, anchor="l", color=WHITE,
              opacity=1.0, reveal=1.0, dy=0.0):
    """y is the top of the capitals. reveal 0..1 = soft left-to-right wipe."""
    if opacity <= 0.002 or reveal <= 0.002:
        return
    m, total = text_mask(text, font, size, round(tracking, 3))
    h, w = m.shape
    if anchor == "c":
        ox = x - w / 2
    elif anchor == "r":
        ox = x - w
    else:
        ox = x
    if reveal < 1:
        soft = 0.25
        xs = np.linspace(0, 1, w, dtype=np.float32)
        edge = reveal * (1 + soft)
        wm = np.clip((edge - xs) / soft, 0, 1)
        m = m * wm[None, :]
    a = m[..., None] * opacity
    comp(canvas, a * color, a, int(round(ox)), int(round(y + dy)))


def draw_rule(canvas, cx, y, length, thick, color, opacity=1.0, glow=0.0, anchor="c"):
    H, W = canvas.shape[:2]
    if length < 1 or opacity <= 0:
        return
    x0 = cx - length / 2 if anchor == "c" else cx
    x1 = x0 + length
    ix0, ix1 = int(max(0, math.floor(x0))), int(min(W, math.ceil(x1)))
    iy0, iy1 = int(y - thick / 2), int(math.ceil(y + thick / 2))
    canvas[iy0:iy1, ix0:ix1] = canvas[iy0:iy1, ix0:ix1] * (1 - opacity) + color * opacity
    if glow > 0:
        draw_glow(canvas, (x0 + x1) / 2, y, max(8, (x1 - x0) * 0.55), thick * 6, glow, color)


# ------------------------------------------------------------------- logo --
LOGO_CARD = {}


def logo_card(logo_path, logo_h):
    """The official logo on a premium white card (its black wordmark needs a
    light field). Upscaled with Lanczos only - geometry is untouched."""
    k = (str(logo_path), logo_h)
    if k in LOGO_CARD:
        return LOGO_CARD[k]
    src = Image.open(logo_path).convert("RGBA")
    w = round(src.width * logo_h / src.height)
    logo = src.resize((w, logo_h), Image.LANCZOS)
    if logo_h / src.height > 1.5:
        logo = logo.filter(ImageFilter.UnsharpMask(radius=max(1, logo_h / 120), percent=60, threshold=2))
    pad_x, pad_y = round(logo_h * 0.22), round(logo_h * 0.17)
    cw, ch = w + 2 * pad_x, logo_h + 2 * pad_y
    card = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    mask = Image.new("L", (cw * 4, ch * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, cw * 4 - 1, ch * 4 - 1), radius=round(logo_h * 0.05) * 4, fill=255)
    mask = mask.resize((cw, ch), Image.LANCZOS)
    face = Image.new("RGBA", (cw, ch), (245, 245, 245, 255))
    face.paste(logo, (pad_x, pad_y))
    card.paste(face, (0, 0), mask)
    arr = np.asarray(card).astype(np.float32) / 255
    arr[..., :3] *= arr[..., 3:4]
    LOGO_CARD[k] = arr
    return arr


# --------------------------------------------------------------- versions --
DESKTOP = dict(
    name="desktop", W=1300, H=500, file="GD_Tableware_RS3000_Desktop_1300x500.mp4",
    poster="GD_Tableware_RS3000_Desktop_Poster.jpg", poster_t=15.2, grain=0.016,
    s1=dict(cx=650, cy=238, w=640),
    s2=dict(panel=(860, 250), fade=(430, 660), scale=1.55, side="left",
            text=dict(x=96, y=212, lines=["CRAFTED TO IMPRESS"], size=27, gap=0, rule_y=268)),
    s3=dict(bowl=dict(cx=680, cy=232, w=640), pot=dict(cx=680, cy=226, w=600)),
    s4=dict(dish=dict(cx=390, cy=232, w=530), bowl=dict(cx=390, cy=232, w=520),
            text=dict(x=700, y=212, lines=["DESIGNED FOR ELEGANCE"], size=27, gap=0, rule_y=268)),
    s5=dict(center=(800, 250), pieces=[
        # key, cx, cy, width, depth(0 back..2 front), reveal beat index
        ("plate_marble_lg", 610, 150, 320, 0, 0),
        ("tray_marble_rect", 950, 140, 280, 0, 0),
        ("bowl_black", 470, 300, 250, 1, 1),
        ("bowl_two_tone", 1080, 300, 240, 1, 2),
        ("plate_marble_sm", 560, 398, 220, 2, 3),
        ("dish_white", 990, 398, 230, 2, 3),
        ("pot_black", 775, 268, 340, 1.5, 4),
    ], text=dict(x=92, title_y=180, title=50, sub_y=250, sub=15, art_y=[178, 236], art=44)),
    s6=dict(card_cy=150, logo_h=150, rule_y=272, title_y=300, title=22, tag_y=346, tag=27),
)

MOBILE = dict(
    name="mobile", W=1080, H=1920, file="GD_Tableware_RS3000_Mobile_1080x1920.mp4",
    poster="GD_Tableware_RS3000_Mobile_Poster.jpg", poster_t=15.2, grain=0.014,
    s1=dict(cx=540, cy=900, w=880),
    s2=dict(panel=(540, 720), fade=(1180, 1330), scale=2.05, side="bottom",
            text=dict(x=540, y=1400, lines=["CRAFTED", "TO IMPRESS"], size=58, gap=92, rule_y=1600)),
    s3=dict(bowl=dict(cx=540, cy=880, w=940), pot=dict(cx=540, cy=870, w=860)),
    s4=dict(dish=dict(cx=540, cy=820, w=940), bowl=dict(cx=540, cy=830, w=920),
            text=dict(x=540, y=1400, lines=["DESIGNED", "FOR ELEGANCE"], size=58, gap=92, rule_y=1600)),
    s5=dict(center=(540, 860), pieces=[
        ("plate_marble_lg", 345, 570, 500, 0, 0),
        ("tray_marble_rect", 760, 550, 420, 0, 0),
        ("bowl_black", 280, 870, 370, 1, 1),
        ("bowl_two_tone", 810, 875, 350, 1, 2),
        ("plate_marble_sm", 345, 1135, 390, 2, 3),
        ("dish_white", 750, 1140, 400, 2, 3),
        ("pot_black", 545, 840, 520, 1.5, 4),
    ], text=dict(x=540, title_y=1410, title=96, sub_y=1555, sub=30, art_y=[1405, 1500], art=78)),
    s6=dict(card_cy=760, logo_h=300, rule_y=1040, title_y=1090, title=40, tag_y=1170, tag=48),
)


# ----------------------------------------------------------------- scenes --
def background(V, t, glow_xy, glow_r, glow_s):
    W, H = V["W"], V["H"]
    c = np.empty((H, W, 3), np.float32)
    c[:] = BLACK
    if glow_s > 0:
        draw_glow(c, glow_xy[0], glow_xy[1], glow_r[0], glow_r[1], glow_s, GRAPHITE * 1.6)
    return c


def scene1(V, t):
    p = V["s1"]
    lt = t - TL.S1[0]
    c = background(V, t, (p["cx"], p["cy"]), (p["w"] * 0.7, p["w"] * 0.45), 0.55 * smooth(ramp(lt, 0.4, 2.6)))
    push = 1 + 0.07 * ease_io(lt / 3.0)
    expo = 0.05 + 1.0 * smooth(ramp(lt, 0.5, 2.7))
    rim = 0.9 * smooth(ramp(lt, 0.05, 0.9))
    sw = (-0.35 + 1.7 * ease_io(ramp(lt, 0.15, 2.5)), 15, 0.06, 0.55 * fade_window(lt, 0.1, 2.7, 0.3, 0.4))
    draw_product(c, "pot_black", p["cx"], p["cy"], p["w"] * push, expo=expo, light=(-0.6, -0.8),
                 ambient=0.25, contrast=1.5, sweep=sw, rim=rim, reflect=0.16 * expo,
                 floor_glow=0.12 * expo)
    return c


MACROS = [
    # key, focus (cutout px), scale multiplier, drift px/s, sweep angle
    ("plate_marble_lg", (455, 365), 1.00, (40, -8), 25),
    ("tray_marble_rect", (715, 735), 1.05, (-10, -35), 120),
    ("plate_marble_lg", (840, 320), 1.15, (-35, 10), 200),
]


def two_line_block(c, V, block, t, t_in, t_out, font=SANS_L, tracking=0.34, color=WHITE):
    op = fade_window(t, t_in, t_out, 0.5, 0.35)
    rev = ease_out(ramp(t, t_in, t_in + 0.7))
    anchor = "c" if V["name"] == "mobile" else "l"
    for i, line in enumerate(block["lines"]):
        r = ease_out(ramp(t, t_in + 0.12 * i, t_in + 0.12 * i + 0.7))
        draw_text(c, line, font, block["size"], block["x"], block["y"] + i * block["gap"], tracking=tracking,
                  anchor=anchor, color=color, opacity=op, reveal=r, dy=10 * (1 - ease_out(ramp(t, t_in, t_in + 0.8))))
    # signature red accent rule
    L = (60 if V["name"] == "desktop" else 120) * ease_out(ramp(t, t_in + 0.35, t_in + 0.95))
    rx = block["x"] if anchor == "c" else block["x"] + L / 2
    draw_rule(c, rx, block["rule_y"], L, 2 if V["name"] == "desktop" else 4, RED, opacity=op, glow=0.25 * op)


def scene2(V, t):
    p = V["s2"]
    W, H = V["W"], V["H"]
    i = min(2, int(t - TL.S2[0]))
    lt = t - TL.MACRO_CUTS[i]
    key, focus, smul, drift, ang = MACROS[i]
    c = background(V, t, (0, 0), (1, 1), 0)
    scale = p["scale"] * smul * (1 + 0.045 * lt)
    sw = (-0.4 + 1.8 * ease_io(ramp(lt, 0.0, 1.0)), ang, 0.09, 0.22)
    expo = 0.55 + 0.45 * smooth(ramp(lt, 0.0, 0.25))       # quick light-up on every cut
    draw_macro(c, key, focus, scale, p["panel"], drift=drift, t=lt, sweep=sw, expo=expo)
    # fade the macro into the black text field
    a0, a1 = p["fade"]
    if p["side"] == "left":
        x = np.arange(W, dtype=np.float32)
        g = np.clip((x - a0) / (a1 - a0), 0, 1) ** 1.5
        c *= g[None, :, None]
    else:
        y = np.arange(H, dtype=np.float32)
        g = 1 - np.clip((y - a0) / (a1 - a0), 0, 1) ** 0.8
        c *= g[:, None, None]
        top = np.clip(y / 200, 0, 1) ** 0.7
        c *= top[:, None, None]
    c += BLACK * (1 - g[None, :, None] if p["side"] == "left" else 1 - g[:, None, None])
    two_line_block(c, V, p["text"], t, 3.35, 5.95)
    return c


def scene3(V, t):
    p = V["s3"]
    if t < TL.MATCH_CUT:
        lt = t - TL.S3[0]
        q = p["bowl"]
        drift = -18 * ease_io(lt / 1.5) * (V["W"] / 1300)
        c = background(V, t, (q["cx"] + 30 * ease_io(lt / 1.5), q["cy"]), (q["w"] * 0.7, q["w"] * 0.45), 0.55)
        sw = (-0.3 + 1.0 * ease_io(lt / 1.5), 25, 0.07, 0.45)
        draw_product(c, "bowl_black", q["cx"] + drift, q["cy"], q["w"] * (1 + 0.04 * lt / 1.5), expo=1.05,
                     light=(0.5, -0.85), ambient=0.3, contrast=1.3, sweep=sw, rim=0.55,
                     reflect=0.15, floor_glow=0.1)
    else:
        lt = t - TL.MATCH_CUT
        q = p["pot"]
        drift = 18 * ease_io(lt / 1.5) * (V["W"] / 1300)
        c = background(V, t, (q["cx"] - 30 * ease_io(lt / 1.5), q["cy"]), (q["w"] * 0.7, q["w"] * 0.45), 0.55)
        # the light band continues across the match cut
        sw = (0.7 + 0.9 * ease_io(lt / 1.5), 25, 0.07, 0.45)
        expo = 1.1 * (1 - 0.6 * smooth(ramp(lt, 1.3, 1.5)))
        draw_product(c, "pot_black", q["cx"] + drift, q["cy"], q["w"] * (1.04 + 0.04 * lt / 1.5), expo=expo,
                     light=(0.5, -0.85), ambient=0.3, contrast=1.4, sweep=sw, rim=0.6,
                     reflect=0.15, floor_glow=0.1)
    return c


def scene4(V, t):
    p = V["s4"]
    if t < TL.TWO_TONE_CUT:
        lt = t - TL.S4[0]
        q = p["dish"]
        c = background(V, t, (q["cx"], q["cy"]), (q["w"] * 0.6, q["w"] * 0.4), 0.35)
        sw = (-0.3 + 1.6 * ease_io(lt / 1.5), 35, 0.08, 0.18)
        draw_product(c, "dish_white", q["cx"] + 14 * ease_io(lt / 1.5), q["cy"], q["w"] * (1 + 0.045 * lt / 1.5),
                     expo=0.84 + 0.05 * smooth(ramp(lt, 0, 0.4)), light=(-0.6, -0.8), ambient=0.6, contrast=0.95,
                     sweep=sw, rim=0.15, reflect=0.12, floor_glow=0.08)
    else:
        lt = t - TL.TWO_TONE_CUT
        q = p["bowl"]
        c = background(V, t, (q["cx"], q["cy"]), (q["w"] * 0.6, q["w"] * 0.4), 0.45)
        # narrow vertical strip-light reflection drifting across the bowl
        sw = (-0.1 + 1.2 * ease_io(lt / 1.5), 0, 0.03, 0.4)
        draw_product(c, "bowl_two_tone", q["cx"] - 14 * ease_io(lt / 1.5), q["cy"], q["w"] * (1 + 0.04 * lt / 1.5),
                     expo=0.92, light=(0.6, -0.8), ambient=0.6, contrast=0.95, sweep=sw, rim=0.3,
                     reflect=0.13, floor_glow=0.08)
    two_line_block(c, V, p["text"], t, 9.45, 11.95)
    return c


def scene5(V, t):
    p = V["s5"]
    lt = t - TL.S5[0]
    gx, gy = p["center"]
    c = background(V, t, (gx, gy), (V["W"] * 0.45, V["H"] * 0.42), 0.6 * smooth(ramp(lt, 0.0, 2.2)))
    end_fade = 1 - smooth(ramp(t, 16.65, 17.0))
    for key, x, y, w, depth, beat in sorted(p["pieces"], key=lambda q: q[4]):
        tb = TL.REVEAL_BEATS[beat]
        on = smooth(ramp(t, tb, tb + 0.55))
        if on <= 0:
            continue
        # camera push-in with depth-dependent parallax
        z = 1 + (0.035 + 0.025 * depth) * ease_io(lt / 5.0)
        X, Y = gx + (x - gx) * z, gy + (y - gy) * z
        depth_dim = (0.85, 0.95, 1.0)[min(2, int(depth))] if depth != 1.5 else 1.08
        expo = on * depth_dim * end_fade * (1.12 if key in ("dish_white", "bowl_two_tone") else 1.0)
        sw_t = ramp(t, tb, tb + 1.4)
        sw = (-0.4 + 1.8 * ease_io(sw_t), 25, 0.07, 0.42 * (1 - sw_t * 0.4)) if sw_t < 1 else None
        if key == "pot_black":
            sw = (-0.4 + 1.8 * ease_io(ramp(t, tb, tb + 2.2)), 20, 0.07, 0.3)
        draw_product(c, key, X, Y, w * z, expo=expo, light=(-0.4, -0.9), ambient=0.33, contrast=1.25,
                     sweep=sw, rim=0.45 * on * end_fade, reflect=(0.12 if depth >= 1.5 else 0.0) * end_fade,
                     blur=0.5 if depth == 0 else 0.0, floor_glow=0.06 * expo if depth >= 1.5 else 0.0)
    tx = p["text"]
    anchor = "c" if V["name"] == "mobile" else "l"
    # RS 3000 COLLECTION
    op1 = fade_window(t, 14.05, 15.55, 0.5, 0.3)
    r1 = ease_out(ramp(t, 14.05, 14.75))
    draw_text(c, "RS 3000", SANS_L, tx["title"], tx["x"], tx["title_y"], tracking=0.12, anchor=anchor,
              opacity=op1, reveal=r1, dy=10 * (1 - r1))
    r1b = ease_out(ramp(t, 14.3, 15.0))
    draw_text(c, "COLLECTION", SANS_L, tx["sub"], tx["x"], tx["sub_y"], tracking=0.62, anchor=anchor,
              opacity=op1, reveal=r1b)
    rl = (70 if anchor == "l" else 140) * ease_out(ramp(t, 14.4, 15.0))
    rule_y = tx["sub_y"] + tx["sub"] * 2.2
    draw_rule(c, tx["x"] + (rl / 2 if anchor == "l" else 0), rule_y, rl, 2 if anchor == "l" else 4, RED,
              opacity=op1, glow=0.25 * op1)
    # THE ART OF THE TABLE
    op2 = fade_window(t, 15.6, 16.95, 0.45, 0.3)
    for i, line in enumerate(["THE ART OF", "THE TABLE"]):
        r = ease_out(ramp(t, 15.6 + 0.15 * i, 16.25 + 0.15 * i))
        draw_text(c, line, SERIF, tx["art"], tx["x"], tx["art_y"][i], tracking=0.16, anchor=anchor,
                  opacity=op2, reveal=r, dy=8 * (1 - r))
    return c


def scene6(V, t, logo_path):
    p = V["s6"]
    W = V["W"]
    lt = t - TL.S6[0]
    c = background(V, t, (W / 2, p["card_cy"]), (W * 0.35, p["logo_h"] * 1.3), 0.35 * smooth(ramp(lt, 0.3, 1.2)))
    cx = W / 2
    # red accent light line draws outward from the centre
    card = logo_card(logo_path, p["logo_h"])
    ch, cw = card.shape[:2]
    rl = cw * 1.25 * ease_out(ramp(lt, 0.0, 0.7))
    draw_rule(c, cx, p["rule_y"], rl, 2 if V["name"] == "desktop" else 4, RED, opacity=1.0,
              glow=0.6 * (1 - 0.6 * ramp(lt, 0.7, 1.6)))
    # logo card
    op = smooth(ramp(lt, 0.3, 1.0))
    if op > 0:
        s = 0.97 + 0.03 * ease_out(ramp(lt, 0.3, 1.3))
        k = cv2.resize(card, (round(cw * s), round(ch * s)), interpolation=cv2.INTER_AREA) if s < 1 else card
        kh, kw = k.shape[:2]
        draw_glow(c, cx, p["card_cy"], kw * 0.75, kh * 0.75, 0.10 * op, WHITE)
        # one subtle red sweep across the card on the musical hit
        comp(c, k[..., :3], k[..., 3:4], int(round(cx - kw / 2)), int(round(p["card_cy"] - kh / 2)), op)
        hit = ramp(t, TL.LOGO_HIT - 0.05, TL.LOGO_HIT + 0.9)
        if 0 < hit < 1:
            draw_glow(c, cx - kw * 0.8 + kw * 1.6 * ease_io(hit), p["card_cy"], kw * 0.12, kh * 0.7,
                      0.10 * math.sin(math.pi * hit), RED)
    r = ease_out(ramp(lt, 1.0, 1.6))
    draw_text(c, "GD TABLEWARE INDUSTRY", SANS_M, p["title"], cx, p["title_y"], tracking=0.42, anchor="c",
              opacity=smooth(ramp(lt, 1.0, 1.5)), reveal=r, dy=8 * (1 - r))
    r2 = ease_out(ramp(lt, 1.5, 2.2))
    draw_text(c, "WHERE ELEGANCE TAKES SHAPE", SERIF, p["tag"], cx, p["tag_y"], tracking=0.16, anchor="c",
              opacity=smooth(ramp(lt, 1.5, 2.0)), reveal=r2, dy=8 * (1 - r2))
    return c


# ------------------------------------------------------------------- post --
POST = {}


def post(V, c, frame_idx):
    W, H = V["W"], V["H"]
    if "vig" not in POST:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d = ((xx - W / 2) / (W / 2)) ** 2 * 0.7 + ((yy - H / 2) / (H / 2)) ** 2 * 0.7
        POST["vig"] = (1 - 0.32 * np.clip(d, 0, 1.6) ** 1.3)[..., None].astype(np.float32)
    # bloom on highlights
    hi = np.clip(c - 0.85, 0, None)
    small = cv2.resize(hi, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), max(W, H) / 4 * 0.02)
    c = c + 0.25 * cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)
    c = c * POST["vig"]
    # protect highlights with a soft shoulder
    s = 0.82
    c = np.where(c > s, s + (1 - s) * np.tanh((c - s) / (1 - s)), c)
    # fine luminance grain (deterministic per frame)
    rng = np.random.default_rng(1000 + frame_idx)
    g = rng.standard_normal((H, W), dtype=np.float32) * V["grain"]
    c = c + g[..., None] * (0.35 + 0.65 * np.sqrt(np.clip(c, 0, 1)))
    c = np.maximum(c, BLACK * 0.6)
    return np.clip(c * 255 + rng.random((H, W, 1), dtype=np.float32) - 0.5, 0, 255).astype(np.uint8)


def render_frame(V, t, logo_path):
    if t < TL.S2[0]:
        c = scene1(V, t)
    elif t < TL.S3[0]:
        c = scene2(V, t)
    elif t < TL.S4[0]:
        c = scene3(V, t)
    elif t < TL.S5[0]:
        c = scene4(V, t)
    elif t < TL.S6[0]:
        c = scene5(V, t)
    else:
        c = scene6(V, t, logo_path)
    return c


_W = {}


def _init(vname, logo):
    _W["V"] = DESKTOP if vname == "desktop" else MOBILE
    _W["logo"] = logo


def _work(i):
    V = _W["V"]
    t = i / FPS
    return post(V, render_frame(V, t, _W["logo"]), i).tobytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version", choices=["desktop", "mobile"])
    ap.add_argument("--stills", default="")
    ap.add_argument("--logo", default=str(DEFAULT_LOGO))
    ap.add_argument("--audio", default=str(BUILD / "soundtrack.wav"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--preview-width", type=int, default=960, help="downsize stills for review")
    args = ap.parse_args()
    V = DESKTOP if args.version == "desktop" else MOBILE
    BUILD.mkdir(exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)

    if args.stills:
        _init(args.version, args.logo)
        for s in args.stills.split(","):
            t = float(s)
            i = int(round(t * FPS))
            img = Image.fromarray(post(V, render_frame(V, t, args.logo), i))
            if args.preview_width and img.width > args.preview_width:
                img = img.resize((args.preview_width, round(img.height * args.preview_width / img.width)), Image.LANCZOS)
            out = BUILD / f"still_{V['name']}_{t:05.2f}.jpg"
            img.save(out, quality=88)
            print(out, flush=True)
        return

    out = OUTPUT / V["file"]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{V['W']}x{V['H']}", "-r", str(FPS), "-i", "-",
           "-i", args.audio, "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "slow", "-crf", str(args.crf), "-tune", "film",
           "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-g", str(FPS * 2),
           "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
           "-movflags", "+faststart", "-t", f"{DURATION:.3f}", str(out)]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(args.workers, initializer=_init, initargs=(args.version, args.logo)) as pool:
        for n, buf in enumerate(pool.imap(_work, range(NFRAMES), chunksize=4)):
            ff.stdin.write(buf)
            if n % 60 == 0:
                print(f"{V['name']}: frame {n}/{NFRAMES}", flush=True)
    ff.stdin.close()
    if ff.wait() != 0:
        sys.exit("ffmpeg failed")
    # poster
    _init(args.version, args.logo)
    i = int(round(V["poster_t"] * FPS))
    img = post(V, render_frame(V, V["poster_t"], args.logo), i)
    Image.fromarray(img).save(OUTPUT / V["poster"], quality=90, optimize=True, progressive=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
