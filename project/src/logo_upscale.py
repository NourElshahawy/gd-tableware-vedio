"""Edge-clean upscale of the official 59x48 GD logo (no redrawing).

Each pixel of the original is softly assigned to the logo's three colours
(white field, GD red, black). Each membership map is upsampled with a smooth
filter and re-thresholded, which sharpens edges while following the original
pixel geometry. The palette is sampled from the original file.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "original" / "GD_logo_official_59x48.jpg"
PAL = {"white": (247, 244, 244), "red": (206, 44, 45), "black": (14, 12, 13)}


def upscale(scale=16):
    im = np.asarray(Image.open(SRC).convert("RGB")).astype(np.float32)
    cols = np.array(list(PAL.values()), np.float32)
    d = ((im[:, :, None, :] - cols[None, None]) ** 2).sum(-1)
    w = np.exp(-d / (2 * 45.0 ** 2))
    w /= w.sum(-1, keepdims=True)
    H, W = im.shape[:2]
    big = []
    for k in range(3):
        m = Image.fromarray((w[..., k] * 255).astype(np.uint8))
        m = m.resize((W * scale, H * scale), Image.BICUBIC).filter(ImageFilter.GaussianBlur(scale * 0.35))
        big.append(np.asarray(m).astype(np.float32) / 255)
    big = np.stack(big, -1)
    # soft argmax -> anti-aliased hard edges
    sharp = np.exp(big * 40)
    sharp /= sharp.sum(-1, keepdims=True)
    out = (sharp[..., None] * cols[None, None]).sum(2)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)), sharp


if __name__ == "__main__":
    img, _ = upscale(int(sys.argv[1]) if len(sys.argv) > 1 else 16)
    img.save(ROOT / "assets" / "prepared" / "logo_upscaled.png")
    print(img.size)
