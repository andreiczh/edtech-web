"""Sequential speech uploads in a 512 MiB container; no provider calls."""
import gc
import io
import os
from pathlib import Path
import resource
import wave
import numpy as np
import main  # include API import footprint while workers are alive
import grading_audio
import audio_check

fixture = Path(os.environ.get("VAD_SPEECH_FIXTURE", "../docs/test-data/reading_39.mp3"))
if fixture.is_file():
    speech = audio_check.to_pcm(fixture.read_bytes(), fixture.suffix)[:20 * 16000]
else:
    t = np.arange(20 * 16000, dtype=np.float32) / 16000
    speech = (.15 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
unit = np.concatenate([speech, np.zeros(10 * 16000, dtype=np.float32)])
for i in range(12 if os.environ.get("VAD_STRESS") == "1" else 2):
    seconds = (180, 300, 360)[i % 3]
    pcm = (np.tile(unit, int(np.ceil(seconds * 16000 / len(unit))))[:seconds * 16000] * 32767).astype("<i2")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(pcm.tobytes())
    data = out.getvalue()
    del pcm, out
    sound, result = grading_audio.analyze_isolated(data, "speech.wav")
    assert sound["ok"] and abs(sound["seconds"] - seconds) < 0.1
    assert len(result) > 32000 and len(result) <= len(data)
    del data, result
    gc.collect()
print("Sequential speech preparation passed; parent peak RSS:", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
peak = Path("/sys/fs/cgroup/memory.peak")
if peak.exists(): print("512 MiB container memory.peak:", peak.read_text().strip())
