"""Synthesize the narration with the local Kokoro voice model. Each caption phrase is spoken
separately so caption timing is exact. Writes build/<video>_voice.wav and build/<video>_timeline.json.
usage: tts.py <video> [voice] [speed]      e.g. tts.py example am_michael 1.0"""
import json, sys, pathlib
import numpy as np, soundfile as sf
from kokoro_onnx import Kokoro
import script_data

ROOT = pathlib.Path(__file__).parent
BUILD = ROOT / "build"
if len(sys.argv) < 2 or sys.argv[1] not in script_data.VIDEOS:
    sys.exit(__doc__ + "\nvideos in script_data.py: " + ", ".join(script_data.VIDEOS))
vid = sys.argv[1]
voice = sys.argv[2] if len(sys.argv) > 2 else "am_michael"
speed = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
segs = script_data.VIDEOS[vid]
MODEL, VOICES = ROOT / "tts/kokoro-v1.0.onnx", ROOT / "tts/voices-v1.0.bin"
if not (MODEL.exists() and VOICES.exists()):
    sys.exit("voice model missing in video/tts/: run ./setup.sh")
k = Kokoro(str(MODEL), str(VOICES))
SR = 24000
LEAD = 0.6  # silence before the first word


def trim(x, thr=0.01, keep=0.04):
    idx = np.where(np.abs(x) > thr)[0]
    if not len(idx): return x
    a, b = max(0, idx[0] - int(keep * SR)), min(len(x), idx[-1] + int(keep * SR))
    return x[a:b]


BUILD.mkdir(exist_ok=True)
out, t, timeline = [np.zeros(int(LEAD * SR), dtype=np.float32)], LEAD, []
for sid, say, cap, pause in segs:
    caps = cap.split("|")
    chunks = say.split("|")
    if len(chunks) != len(caps):
        sys.exit(f"scene {sid}: {len(chunks)} spoken phrases but {len(caps)} caption phrases")
    start, phrases = t, []
    for j, (chunk, c) in enumerate(zip(chunks, caps)):
        x, sr = k.create(chunk, voice=voice, speed=speed, lang="en-us")
        assert sr == SR
        x = trim(x.astype(np.float32))
        gap = 0.0 if j == len(caps) - 1 else (0.28 if chunk[-1] in ".?!" else 0.10)
        phrases.append({"t0": round(t, 3), "t1": round(t + len(x) / SR, 3), "cap": c, "say": chunk})
        out += [x, np.zeros(int(gap * SR), dtype=np.float32)]
        t += len(x) / SR + gap
    out.append(np.zeros(int(pause * SR), dtype=np.float32)); t += pause
    timeline.append({"id": sid, "t0": round(start, 3), "t1": round(t, 3), "phrases": phrases})
    print(sid, f"{start:.2f}-{t:.2f}", flush=True)
audio = np.concatenate(out)
sf.write(BUILD / f"{vid}_voice.wav", audio, SR)
json.dump({"duration": round(len(audio) / SR, 3), "scenes": timeline}, open(BUILD / f"{vid}_timeline.json", "w"), indent=1)
print("total", len(audio) / SR)
