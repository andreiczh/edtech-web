"""Run in the actual container with a 512 MiB cgroup limit, no provider calls."""
import io
import resource
import wave
import numpy as np
import main  # include the application's normal import footprint
import grading_audio

pcm = np.zeros(360 * 16000, dtype=np.int16)
out = io.BytesIO()
with wave.open(out, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(pcm.tobytes())
data = out.getvalue()
assert grading_audio.prepare(data, "six-minutes.wav") == data
print("Six-minute VAD completed; peak RSS KiB:", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
