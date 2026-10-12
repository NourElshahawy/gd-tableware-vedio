"""Technical QC of the delivered MP4s (ffprobe/ffmpeg)."""
import json
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "output"
SPECS = {
    "GD_Tableware_RS3000_Desktop_1300x500.mp4": (1300, 500),
    "GD_Tableware_RS3000_Mobile_1080x1920.mp4": (1080, 1920),
}


def probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(p)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def faststart(p):
    head = p.read_bytes()[:4096]
    return head.find(b"moov") != -1 and (head.find(b"mdat") == -1 or head.find(b"moov") < head.find(b"mdat"))


def black_runs(p):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(p), "-vf", "blackdetect=d=0.25:pix_th=0.06",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    return [ln.split("blackdetect ")[1] for ln in r.stderr.splitlines() if "black_start" in ln]


def decode_ok(p):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "null", "-"], capture_output=True, text=True)
    return r.stderr.strip() == ""


ok = True
for name, (w, h) in SPECS.items():
    p = OUT / name
    if not p.exists():
        print(f"MISSING {name}")
        ok = False
        continue
    d = probe(p)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    a = [s for s in d["streams"] if s["codec_type"] == "audio"]
    num, den = map(int, v["r_frame_rate"].split("/"))
    checks = {
        "resolution": (v["width"], v["height"]) == (w, h),
        "codec h264": v["codec_name"] == "h264",
        "yuv420p": v["pix_fmt"] == "yuv420p",
        "fps 30": num / den == 30,
        "frames 600": int(v.get("nb_frames", 0)) == 600,
        "duration ~20s": abs(float(d["format"]["duration"]) - 20.0) < 0.1,
        "audio aac": bool(a) and a[0]["codec_name"] == "aac",
        "faststart": faststart(p),
        "decodes cleanly": decode_ok(p),
    }
    size = p.stat().st_size / 1e6
    print(f"\n{name}  {size:.2f} MB  {int(d['format']['bit_rate']) / 1e6:.2f} Mb/s")
    for k, val in checks.items():
        print(f"  {'PASS' if val else 'FAIL'}  {k}")
        ok &= val
    runs = black_runs(p)
    print("  black runs (>0.25s):", runs or "none")
sys.exit(0 if ok else 1)
