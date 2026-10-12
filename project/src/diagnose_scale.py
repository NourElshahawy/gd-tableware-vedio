"""Report max on-screen scale (display px / source px) per image per scene."""
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import render as R

def run(V):
    rec = defaultdict(float)
    cur = {}
    orig = R.draw_product
    def spy(canvas, key, cx, cy, width, **kw):
        s = width / R.asset(key).w / R.SS
        k = (cur["scene"], key)
        rec[k] = max(rec[k], s)
    R.draw_product = spy
    R.comp = lambda *a, **k: None
    for i in range(R.NFRAMES):
        t = i / R.FPS
        cur["scene"] = 1 + sum(t >= b for b in (3, 6, 9, 12, 17))
        R.render_frame(R.internal(V), t, str(R.DEFAULT_LOGO))
    R.draw_product = orig
    return rec

for V in (R.DESKTOP, R.MOBILE):
    print(f"\n== {V['name']} {V['W']}x{V['H']} ==")
    for (sc, key), s in sorted(run(V).items()):
        a = R.asset(key)
        flag = "  <-- UPSCALED" if s > 1.0 else ""
        print(f"  S{sc} {key:18s} src {a.w}x{a.h} cutout  max {s:5.2f}x{flag}")
    lh = V["s6"]["logo_h"]
    print(f"  S6 logo              src 59x48 original  max {lh/48:5.2f}x  <-- UPSCALED")
