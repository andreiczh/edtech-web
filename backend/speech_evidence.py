"""Link a verified, unique quote to a segment of the original recording."""
from __future__ import annotations

import math

from ege_scoring import _words


def attach_spans(feedback: dict, transcript: str, segments: list, sound: dict) -> None:
    duration = sound.get("seconds") or 0.0
    if not duration or not segments:
        return
    timeline = sound.get("timeline") or []
    timed_words = []
    bounds = []
    last_start = -1.0
    for segment in segments[:400]:
        if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
            return
        try:
            start, end = float(segment["start"]), float(segment["end"])
        except (KeyError, TypeError, ValueError):
            return
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end and start >= last_start):
            return
        last_start = start
        words = _words(segment["text"])
        timed_words.extend(words)
        bounds.extend([(start, end)] * len(words))

    spoken_words = _words(transcript)

    def unique_start(words: list[str], quote: list[str]) -> int | None:
        matches = [i for i, word in enumerate(words) if word == quote[0]
                   and words[i:i + len(quote)] == quote]
        return matches[0] if len(matches) == 1 else None

    for item in [*feedback.get("criteria", []), *feedback.get("errors", []),
                 *feedback.get("practice", [])]:
        quote = _words(item.get("quote") or "")
        if not quote or unique_start(spoken_words, quote) is None:
            continue
        index = unique_start(timed_words, quote)
        if index is None:
            continue
        start, end = bounds[index][0], bounds[index + len(quote) - 1][1]
        if timeline:
            overlaps = [(original + max(lo, start) - lo, original + min(hi, end) - lo)
                        for lo, hi, original in timeline if min(hi, end) > max(lo, start)]
            if not overlaps:
                continue
            start, end = overlaps[0][0], overlaps[-1][1]
        # Avoid misleading seek links when STT provides a very wide or invalid segment.
        if 0 <= start < end <= duration + 0.25 and end - start <= 25:
            item["audio_span"] = {"start": round(start, 3), "end": round(min(end, duration), 3)}
