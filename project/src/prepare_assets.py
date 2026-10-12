"""Cut the real product photographs out of their white studio backgrounds.

The originals in assets/original are never modified; RGBA cutouts are written
to assets/prepared. Segmentation is OpenCV GrabCut seeded from the white
background, followed by hole filling so white interiors (bowl, dish) survive.
No pixels of the product itself are repainted or altered.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ORIG = ROOT / "assets" / "original"
OUT = ROOT / "assets" / "prepared"

# semantic id -> (source file, params)
MANIFEST = {
    "pot_black":        ("WhatsApp Image 2026-10-12 at 4.03.32 PM.jpeg", {}),
    "bowl_black":       ("WhatsApp Image 2026-10-12 at 4.03.32 PM (1).jpeg", {}),
    # white pieces on a white backdrop: plain threshold (backdrop is 254) +
    # hole fill; the dish additionally gets a clip polygon through its four
    # measured outer corners so its soft floor shadow is excluded.
    "bowl_two_tone":    ("WhatsApp Image 2026-10-12 at 4.03.32 PM (2).jpeg", {"thresh": 244}),
    "dish_white":       ("WhatsApp Image 2026-10-12 at 4.03.32 PM (3).jpeg",
                         {"thresh": 244, "clip": [(243, 343), (870, 25), (1491, 331), (850, 747)]}),
    "collection_full":  ("WhatsApp Image 2026-10-12 at 4.03.31 PM.jpeg", {"multi": True}),
    "plate_marble_lg":  ("WhatsApp Image 2026-10-12 at 4.03.31 PM (2).jpeg", {}),
    "plate_marble_md":  ("WhatsApp Image 2026-10-12 at 4.03.31 PM (1).jpeg", {}),
    "plate_marble_sm":  ("WhatsApp Image 2026-10-12 at 4.03.31 PM (3).jpeg", {}),
    "tray_marble_rect": ("WhatsApp Image 2026-10-12 at 4.03.31 PM (4).jpeg", {}),
}


def fill_holes(mask):
    h, w = mask.shape
    ff = mask.copy()
    pad = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, pad, (0, 0), 255)
    return mask | (~ff & 255)


def segment(img, bg_t=246, fg_t=215, multi=False):
    lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = lum.shape
    # background connected to the frame border
    bright = (lum >= bg_t).astype(np.uint8) * 255
    border_bg = np.zeros_like(bright)
    pad = np.zeros((h + 2, w + 2), np.uint8)
    tmp = bright.copy()
    for seed in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
        if tmp[seed[1], seed[0]] == 255:
            cv2.floodFill(tmp, pad, seed, 128)
    border_bg = (tmp == 128)

    gc = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    gc[lum < fg_t] = cv2.GC_PR_FGD
    gc[lum < 120] = cv2.GC_FGD
    gc[border_bg] = cv2.GC_BGD
    # keep a definite-bg frame
    gc[:4, :] = gc[-4:, :] = cv2.GC_BGD
    gc[:, :4] = gc[:, -4:] = cv2.GC_BGD
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    cv2.grabCut(img, gc, None, bgd, fgd, 6, cv2.GC_INIT_WITH_MASK)
    m = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m)
    if n > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        if multi:
            keep = [i + 1 for i, a in enumerate(areas) if a > 0.004 * h * w]
        else:
            keep = [int(np.argmax(areas)) + 1]
        m = np.isin(lab, keep).astype(np.uint8) * 255
    m = fill_holes(m)
    # soft 1.5px edge
    a = cv2.GaussianBlur(m.astype(np.float32) / 255.0, (0, 0), 1.0)
    a = np.clip((a - 0.5) * 1.6 + 0.5, 0, 1)
    return a


def segment_threshold(img, t, clip=None):
    lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    m = (lum < t).astype(np.uint8) * 255
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    m = (lab == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    m = fill_holes(m)
    if clip is not None:
        poly = np.zeros_like(m)
        cv2.fillPoly(poly, [np.array(clip, np.int32)], 255, cv2.LINE_AA)
        m = np.minimum(m, poly)
    a = cv2.GaussianBlur(m.astype(np.float32) / 255.0, (0, 0), 0.8)
    return a


def main(only=None):
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    for key, (fname, p) in MANIFEST.items():
        if only and key not in only:
            continue
        img = cv2.imread(str(ORIG / fname))
        if "thresh" in p:
            a = segment_threshold(img, p["thresh"], p.get("clip"))
        else:
            a = segment(img, p.get("bg", 246), p.get("fg", 215), p.get("multi", False))
        # de-fringe: pull edge pixels away from the white backdrop colour
        rgb = img.astype(np.float32) / 255.0
        edge = (a > 0.02) & (a < 0.98)
        aa = np.maximum(a, 1e-3)[..., None]
        defr = np.clip((rgb - (1 - aa) * 1.0) / aa, 0, 1)
        rgb = np.where(edge[..., None], defr, rgb)
        ys, xs = np.where(a > 0.05)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        pad = 6
        y0, x0 = max(0, y0 - pad), max(0, x0 - pad)
        y1, x1 = min(img.shape[0], y1 + pad), min(img.shape[1], x1 + pad)
        rgba = np.dstack([rgb[..., ::-1], a])[y0:y1, x0:x1]
        out = (rgba * 255 + 0.5).astype(np.uint8)
        cv2.imwrite(str(OUT / f"{key}.png"), cv2.cvtColor(out, cv2.COLOR_RGBA2BGRA))
        report[key] = {"source": fname, "crop": [int(x0), int(y0), int(x1), int(y1)], "size": [int(x1 - x0), int(y1 - y0)]}
        print(key, report[key])
    if not only:
        (OUT / "cutouts.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:] or None)
