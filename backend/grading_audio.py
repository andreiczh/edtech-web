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

    Low confidence speech is kept. Two-second overlaps and one-second padding
    protect words at window boundaries, and merged spans are copied only once.
    """
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    options = VadOptions(threshold=0.05, min_silence_duration_ms=2000,
                         speech_pad_ms=1000)
    spans = []
    step = VAD_WINDOW_SAMPLES - 2 * 16000
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
        return _prepare(data, filename)


def _prepare(data: bytes, filename: str) -> bytes:
    from pathlib import Path

    pcm = audio_check.to_pcm(data, Path(filename).suffix)
    if pcm is None or len(pcm) < 30 * 16000:
        return data
    spans = speech_spans(pcm)
    if not spans:
        return data  # uncertainty never deletes the student's entire answer
    samples = sum(s["end"] - s["start"] for s in spans) + max(0, len(spans) - 1) * 8000
    if len(pcm) - samples < max(5 * 16000, len(pcm) * 0.1):
        return data
    # Keep a half-second separator and the VAD's one-second margins. Grammar,
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
