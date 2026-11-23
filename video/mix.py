"""Mix narration + original synthesized music + sound effects -> build/<video>_mix.wav (48 kHz stereo).
The music (pad, arpeggio, sub bass, shaker) and every effect are generated here from sine waves and
noise, so the soundtrack has no licence to worry about.
usage: mix.py <video>"""
import json, sys, pathlib
import numpy as np, soundfile as sf
from scipy.signal import resample_poly, butter, sosfilt
import script_data

ROOT = pathlib.Path(__file__).parent
BUILD = ROOT / "build"
if len(sys.argv) < 2:
    sys.exit(__doc__)
vid = sys.argv[1]
SR = 48000
tl = json.load(open(BUILD / f"{vid}_timeline.json"))
voice, vsr = sf.read(BUILD / f"{vid}_voice.wav")
voice = resample_poly(voice, SR, vsr).astype(np.float64)
N = int(tl["duration"] * SR)
voice = np.pad(voice, (0, max(0, N - len(voice))))[:N]
voice *= 0.9 / np.max(np.abs(voice))
rng = np.random.default_rng(7)
t_all = np.arange(N) / SR


def lp(x, hz, order=2): return sosfilt(butter(order, hz, "low", fs=SR, output="sos"), x)
def hp(x, hz, order=2): return sosfilt(butter(order, hz, "high", fs=SR, output="sos"), x)
def note(m): return 440 * 2 ** ((m - 69) / 12)


# ---- music: slow four-chord pad + soft arpeggio + sub bass, 80 bpm -------------------------------
BPM = 80; beat = 60 / BPM; bar = 4 * beat
PROGRESSIONS = [  # MIDI notes, four chords each; pick one per video with MUSIC in script_data.py
    [[57, 60, 64, 67], [53, 57, 60, 64], [48, 55, 60, 64], [55, 59, 62, 67]],   # Am7 Fmaj7 C G
    [[50, 57, 60, 65], [46, 53, 58, 62], [53, 57, 60, 65], [48, 55, 60, 64]],   # Dm7 Bb F C
    [[52, 59, 64, 67], [48, 55, 60, 64], [55, 59, 62, 67], [50, 57, 62, 66]],   # Em C G D
    [[50, 57, 62, 65], [46, 53, 58, 62], [53, 57, 60, 65], [48, 55, 60, 64]],   # Dm Bb F C
]
chords = PROGRESSIONS[getattr(script_data, "MUSIC", {}).get(vid, 0) % len(PROGRESSIONS)]
L = np.zeros(N); R = np.zeros(N)
nbars = int(np.ceil(tl["duration"] / (2 * bar)))
for b in range(nbars):
    ch = chords[b % 4]; t0 = b * 2 * bar; n0 = int(t0 * SR); dur = 2 * bar + 1.2
    n = min(int(dur * SR), N - n0)
    if n <= 0: break
    t = np.arange(n) / SR
    env = np.minimum(t / 1.4, 1) * np.minimum((dur - t) / 1.2, 1).clip(0, 1)
    for i, m in enumerate(ch):
        f = note(m)
        for det, pan in ((-0.25, 0.3), (0.25, 0.7)):
            w = np.sin(2 * np.pi * (f * (1 + det / 100)) * t + i) + 0.35 * np.sin(2 * np.pi * 2 * f * t) + 0.12 * np.sin(2 * np.pi * 3 * f * t)
            w *= env * 0.05 * (1 + 0.15 * np.sin(2 * np.pi * 0.2 * t + i))
            L[n0:n0 + n] += w * (1 - pan); R[n0:n0 + n] += w * pan
    # sub bass on the root
    f = note(ch[0] - 12); w = np.sin(2 * np.pi * f * t) * env * 0.10
    L[n0:n0 + n] += w; R[n0:n0 + n] += w
    # arpeggio: eighth notes, enters after the first two chords
    if b >= 1:
        pat = [0, 2, 1, 3, 2, 1, 3, 2] * 2
        for k, idx in enumerate(pat):
            ts = t0 + k * beat / 2; ns = int(ts * SR); nn = min(int(0.9 * SR), N - ns)
            if nn <= 0: break
            tt = np.arange(nn) / SR; f = note(ch[idx] + 12)
            w = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt)) * np.exp(-tt * 5.5) * np.minimum(tt / 0.005, 1) * 0.06
            pan = 0.35 + 0.3 * ((k % 4) / 3)
            L[ns:ns + nn] += w * (1 - pan); R[ns:ns + nn] += w * pan
            d = ns + int(0.375 * SR)  # one echo
            if d + nn < N: L[d:d + nn] += w * 0.3 * pan; R[d:d + nn] += w * 0.3 * (1 - pan)
    # gentle shaker on off-beats from the third chord on
    if b >= 2:
        for k in range(8):
            ns = int((t0 + (k + 0.5) * beat) * SR); nn = int(0.08 * SR)
            if ns + nn >= N: break
            w = hp(rng.standard_normal(nn), 6000) * np.exp(-np.arange(nn) / SR * 60) * 0.02
            L[ns:ns + nn] += w; R[ns:ns + nn] += w
music = np.stack([lp(L, 5000), lp(R, 5000)], 1)

# duck the music under the voice
env = lp(np.abs(voice), 4, 1); env = np.clip(env / 0.12, 0, 1)
music *= (1 - 0.5 * env)[:, None]
music *= (np.minimum(t_all / 1.5, 1) * np.clip((tl["duration"] - t_all) / 1.6, 0, 1))[:, None]

# ---- sound effects ---------------------------------------------------------------------------
sfx = np.zeros((N, 2))
def put(x, at, gain=1.0, pan=0.5):
    n0 = int(at * SR)
    if n0 < 0 or n0 >= N: return
    x = x[: N - n0]; sfx[n0:n0 + len(x), 0] += x * gain * (1 - pan) * 2; sfx[n0:n0 + len(x), 1] += x * gain * pan * 2
def whoosh(d=0.55):
    n = int(d * SR); t = np.arange(n) / SR; x = rng.standard_normal(n)
    y = np.zeros(n)
    for i in range(0, n, 480):  # band sweeps upward
        fc = 400 + 3600 * (i / n)
        y[i:i + 480] = sosfilt(butter(2, [fc * 0.6, fc * 1.5], "band", fs=SR, output="sos"), x[max(0, i - 2400):i + 480])[-len(x[i:i + 480]):]
    return y * np.sin(np.pi * t / d) ** 2 * 0.22
def pop():
    n = int(0.09 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * (880 - 3000 * t) * t) * np.exp(-t * 45) * 0.22
def ding():
    n = int(1.4 * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 1318.5 * t) + 0.5 * np.sin(2 * np.pi * 1975.5 * t) + 0.25 * np.sin(2 * np.pi * 2637 * t)) * np.exp(-t * 4) * np.minimum(t / 0.003, 1) * 0.16
def buzz():
    n = int(0.32 * SR); t = np.arange(n) / SR
    return lp(np.sign(np.sin(2 * np.pi * 98 * t)), 900) * np.minimum(t / 0.01, 1) * np.minimum((0.32 - t) / 0.05, 1) * 0.16
def thud():
    n = int(0.5 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * (90 - 60 * t) * t) * np.exp(-t * 9) * 0.5

sc = {s["id"]: s for s in tl["scenes"]}
P = lambda sid, i, off=0.0: sc[sid]["phrases"][i]["t0"] + off
for i, s in enumerate(tl["scenes"]):
    if i: put(whoosh(), s["t0"] - 0.38, pan=0.3 + 0.4 * (i % 2))
SOUNDS = {"pop": pop, "ding": ding, "buzz": buzz, "thud": thud, "whoosh": whoosh}
for sound, sid, i, *rest in getattr(script_data, "CUES", {}).get(vid, []):   # the cues listed in script_data.py
    put(SOUNDS[sound](), P(sid, i, rest[0] if rest else 0.0), rest[1] if len(rest) > 1 else 1.0)

mix = np.stack([voice, voice], 1) + music * 0.24 + sfx * 0.5
peak = np.max(np.abs(mix)); mix *= 0.97 / peak
rms = lambda x: 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)
act = np.abs(voice) > 0.02; print(f"voice active rms {rms(voice[act]):.1f} dB, music rms {rms(music * 0.24):.1f} dB, peak {peak:.2f}")
sf.write(BUILD / f"{vid}_mix.wav", mix, SR, subtype="PCM_16")
