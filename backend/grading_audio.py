"""Keep speech intact while shortening long pauses before exam transcription.

The stored/playable recording is unchanged. Silero VAD is bundled with the
existing faster-whisper dependency; no new model download or provider is used.
This is NOT pronunciation assessment. Never derive delivery/pace from this copy.
"""
from __future__ import annotations

import io
import wave

import numpy as np

import audio_check


def prepare(data: bytes, filename: str = "speech.webm") -> bytes:
    from pathlib import Path
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    pcm = audio_check.to_pcm(data, Path(filename).suffix)
    if pcm is None or len(pcm) < 30 * 16000:
        return data
    spans = get_speech_timestamps(pcm, VadOptions(
        threshold=0.25, min_silence_duration_ms=2000, speech_pad_ms=500))
    if not spans:
        return data  # uncertainty never deletes the student's entire answer
    samples = sum(s["end"] - s["start"] for s in spans) + max(0, len(spans) - 1) * 8000
    if len(pcm) - samples < max(5 * 16000, len(pcm) * 0.1):
        return data
    # Keep a half-second separator and the VAD's half-second margins. Grammar,
    # repetitions and self-corrections INSIDE speech are never rewritten.
    parts = []
    for s in spans:
        if parts:
            parts.append(np.zeros(8000, dtype=np.float32))
        parts.append(pcm[s["start"]:s["end"]])
    compact = np.concatenate(parts)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(compact, -1, 1) * 32767).astype("<i2").tobytes())
    return out.getvalue()
