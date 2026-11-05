"""Keep speech intact while shortening long pauses before exam transcription.

The stored/playable recording is unchanged. Silero VAD is bundled with the
existing faster-whisper dependency; no new model download or provider is used.
This is NOT pronunciation assessment. Never derive delivery/pace from this copy.
"""
from __future__ import annotations

import io
import wave
import threading

import numpy as np

import audio_check

_VAD_LOCK = threading.Lock()
VAD_WINDOW_SAMPLES = 20 * 16000


def speech_spans(pcm):
    """Bound ONNX encoder batches; its default batches a whole five-minute file.

    Three-second margins keep hesitant onsets. Six-second overlaps and padding
    protect words at window boundaries, and merged spans are copied only once.
    """
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    options = VadOptions(threshold=0.25, min_silence_duration_ms=2000,
                         speech_pad_ms=3000)
    spans = []
    step = VAD_WINDOW_SAMPLES - 6 * 16000
    for offset in range(0, len(pcm), step):
        part = pcm[offset:offset + VAD_WINDOW_SAMPLES]
        # The upstream VAD mutates its last context frame; protect source audio.
        for s in get_speech_timestamps(part.copy(), options):
            start, end = offset + s["start"], offset + s["end"]
            if spans and start <= spans[-1]["end"]:
                spans[-1]["end"] = max(spans[-1]["end"], end)
            else:
                spans.append({"start": start, "end": end})
        if offset + VAD_WINDOW_SAMPLES >= len(pcm):
            break
    return spans


def prepare(data: bytes, filename: str = "speech.webm") -> bytes:
    # Upload concurrency is independent; only one local VAD/decoder allocation
    # is allowed at a time on the 512 MiB deployment.
    with _VAD_LOCK:
        from pathlib import Path
        return _prepare(data, audio_check.to_pcm(data, Path(filename).suffix))


def _prepare(data: bytes, pcm: np.ndarray | None, timeline: list | None = None) -> bytes:
    if pcm is None or len(pcm) < 30 * 16000:
        return data
    spans = speech_spans(pcm)
    if not spans:
        return data  # uncertainty never deletes the student's entire answer
    samples = sum(s["end"] - s["start"] for s in spans) + max(0, len(spans) - 1) * 8000
    if len(pcm) - samples < max(5 * 16000, len(pcm) * 0.1):
        return data
    # Keep a half-second separator and the VAD's three-second margins. Grammar,
    # repetitions and self-corrections INSIDE speech are never rewritten.
    parts = []
    offset = 0
    for s in spans:
        if parts:
            parts.append(np.zeros(8000, dtype=np.float32))
            offset += 8000
        length = s["end"] - s["start"]
        if timeline is not None:
            timeline.append((offset / 16000, (offset + length) / 16000, s["start"] / 16000))
        parts.append(pcm[s["start"]:s["end"]])
        offset += length
    compact = np.concatenate(parts)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(compact, -1, 1) * 32767).astype("<i2").tobytes())
    return out.getvalue()


def analyze_isolated(data: bytes, filename: str, *, compact: bool = True) -> tuple[dict, bytes]:
    """Release decoder/ONNX arenas after every upload, including native caches.

    A lock keeps simultaneous requests from creating simultaneous model workers.
    The child sees only public/audio bytes, never provider credentials or DB data.
    A timeout/crash fails the analysis instead of taking down the API process.
    """
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys

    env = {key: value for key, value in os.environ.items()
           if key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME",
                      "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH")}
    env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    with _VAD_LOCK:
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), Path(filename).suffix or ".webm",
             "compact" if compact else "inspect"],
            input=data, capture_output=True, timeout=75, check=True, env=env)
    header, prepared = completed.stdout.split(b"\n", 1)
    return json.loads(header), prepared or data


if __name__ == "__main__":
    import json
    import sys
    data = sys.stdin.buffer.read()
    pcm = audio_check.to_pcm(data, sys.argv[1])
    sound = audio_check.inspect_pcm(pcm)
    prepared = data
    if sys.argv[2] == "compact" and audio_check.silence_reason(sound) is None:
        timeline = []
        prepared = _prepare(data, pcm, timeline)
        if timeline:
            sound["timeline"] = timeline
    # When there is no change, the parent already has the original bytes.
    sys.stdout.buffer.write(json.dumps(sound).encode() + b"\n")
    if prepared is not data:
        sys.stdout.buffer.write(prepared)
