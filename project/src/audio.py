"""Original soundtrack, synthesized from scratch (no samples, no licensing).

Luxury industrial minimalism at 120 BPM: sub drone, deep impacts, restrained
kick/percussion, FM metallic accents on every cut, noise risers into the
collection reveal and the brand finale. All hits come from timeline.py, so the
music is locked to the picture.
"""
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

sys.path.insert(0, str(Path(__file__).resolve().parent))
import timeline as TL  # noqa: E402

SR = 48000
N = int(SR * TL.DURATION)
rng = np.random.default_rng(7)


def t_axis(n):
    return np.arange(n) / SR


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def add(buf, sig, at, gain=1.0, pan=0.0):
    i = int(at * SR)
    if i >= N:
        return
    s = sig[: N - i] * gain
    buf[0, i:i + len(s)] += s * np.sqrt(0.5 * (1 - pan))
    buf[1, i:i + len(s)] += s * np.sqrt(0.5 * (1 + pan))


def env(n, a, d):
    t = t_axis(n)
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / d)


def impact(big=1.0):
    n = int(SR * 3.5)
    t = t_axis(n)
    f = 32 + 70 * np.exp(-t * 9)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.003, 1.1 * big)
    body = lp(rng.standard_normal(n), 180) * env(n, 0.002, 0.25) * 2.5
    crack = hp(rng.standard_normal(n), 2500) * env(n, 0.001, 0.05) * 0.25
    return (boom + body + crack) * 0.9


def kick():
    n = int(SR * 0.5)
    t = t_axis(n)
    f = 45 + 110 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, 0.16)


def hat(open_=False):
    n = int(SR * (0.25 if open_ else 0.06))
    return bp(rng.standard_normal(n), 7000, 15000) * env(n, 0.0005, 0.07 if open_ else 0.015)


def snap():
    n = int(SR * 0.3)
    s = bp(rng.standard_normal(n), 900, 5000) * env(n, 0.001, 0.05)
    return s + np.sin(2 * np.pi * 190 * t_axis(n)) * env(n, 0.001, 0.04) * 0.4


def metal(freq=880.0, dur=1.6, ratio=3.53):
    """FM bell/metal accent."""
    n = int(SR * dur)
    t = t_axis(n)
    idx = 4.0 * np.exp(-t * 6)
    s = np.sin(2 * np.pi * freq * t + idx * np.sin(2 * np.pi * freq * ratio * t))
    return s * env(n, 0.002, dur / 4)


def riser(dur):
    n = int(SR * dur)
    t = t_axis(n) / dur
    x = rng.standard_normal(n)
    out = np.zeros(n)
    seg = n // 16
    for k in range(16):  # sweeping band-pass
        lo = 300 * 2 ** (k * 0.35)
        sl = slice(k * seg, (k + 1) * seg if k < 15 else n)
        out[sl] = bp(x, lo, min(lo * 3, 20000))[sl]
    return out * t ** 2.2


def whoosh(dur=0.6):
    n = int(SR * dur)
    t = t_axis(n) / dur
    return bp(rng.standard_normal(n), 400, 4000) * np.sin(np.pi * t) ** 2


def drone():
    t = t_axis(N)
    root = 41.2  # E1
    d = np.sin(2 * np.pi * root * t) * 0.6 + np.sin(2 * np.pi * root * 2 * t + 0.4 * np.sin(2 * np.pi * 0.2 * t)) * 0.25
    # dark pad: E minor (E, G, B) detuned saws, low-passed
    pad = np.zeros(N)
    for f in (82.4, 98.0, 123.5, 164.8):
        for det in (-0.25, 0.25):
            ph = (f + det) * t
            pad += 2 * (ph - np.floor(ph + 0.5))
    pad = lp(pad, 650) * 0.06
    shape = np.interp(t, [0, 1.0, 6, 12, 16.9, 17.0, 17.9, 18.0, 20], [0.2, 0.7, 0.8, 0.9, 1.0, 0.25, 0.25, 0.9, 0.45])
    return (d * 0.35 + pad) * shape


def main(out):
    L = np.zeros((2, N))
    dry = np.zeros((2, N))
    add(dry, drone(), 0, 0.55)
    for at in TL.IMPACTS:
        big = 1.6 if at == TL.LOGO_HIT else 1.0
        add(dry, impact(big), at, 1.0 if at in (0.0, 12.0, TL.LOGO_HIT) else 0.7)
    # percussion: sparse kicks from 3 s, groove builds in the reveal
    beat = TL.BEAT
    for k in range(int(3.0 / beat), int(17.0 / beat)):
        at = k * beat
        if at in TL.IMPACTS:
            continue
        if at < 12 and k % 2 == 0:
            add(dry, kick(), at, 0.75)
        elif at >= 12:
            add(dry, kick(), at, 0.8)
        if at >= 6 and k % 4 == 2:
            add(L, snap(), at, 0.35)
    for k in range(int(6.0 / (beat / 4)), int(17.0 / (beat / 4))):
        at = k * beat / 4
        acc = 0.13 if k % 4 == 2 else 0.05
        add(dry, hat(k % 8 == 6), at, acc * (1.4 if at >= 12 else 1.0), pan=0.35 if k % 2 else -0.35)
    # metallic accents on the cuts
    notes = [880.0, 659.3, 987.8, 784.0, 1174.7, 880.0, 659.3, 784.0, 987.8, 1318.5]
    for i, at in enumerate(TL.ACCENTS):
        add(L, metal(notes[i % len(notes)] / 2, 1.8), at, 0.16, pan=(-0.3, 0.3)[i % 2])
    add(L, metal(329.6, 4.0, 2.0), TL.LOGO_HIT, 0.22)
    add(L, metal(659.3, 4.0, 3.53), TL.LOGO_HIT + 0.02, 0.10, pan=0.2)
    # risers and transitions
    add(L, riser(1.5), 12.0 - 1.5, 0.12)
    add(L, riser(1.0), 17.0 - 1.0, 0.10)
    for at in (5.85, 8.85, 11.85):
        add(L, whoosh(0.4), at - 0.25, 0.05)

    # stereo reverb (decorrelated exponential noise tails)
    ir_n = int(SR * 2.2)
    tt = t_axis(ir_n)
    wet = np.zeros_like(L)
    send = L + dry * 0.25
    for ch in range(2):
        ir = rng.standard_normal(ir_n) * np.exp(-tt / 0.55)
        ir = lp(ir, 6000)
        ir /= np.sqrt((ir ** 2).sum())
        wet[ch] = fftconvolve(send[ch], ir)[:N]
    mix = dry + L + wet * 0.55
    mix = hp(mix, 25)
    # gentle glue + master
    mix = np.tanh(mix * 1.1) / np.tanh(1.1)
    mix *= 10 ** (-1.0 / 20) / np.max(np.abs(mix))
    fade = np.ones(N)
    fade[-int(SR * 0.6):] = np.linspace(1, 0, int(SR * 0.6)) ** 2
    mix *= fade
    pcm = (mix.T * 32767).astype(np.int16)
    import wave
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[1] / "build" / "soundtrack.wav"))
