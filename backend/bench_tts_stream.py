"""A/B a buffered and streamed Mistral TTS reply with identical inputs."""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import time

import av

PHRASES = (
    "That sounds like a wonderful weekend.",
    "I can see why you enjoyed that. What would you do differently next time?",
)


def audio_duration(data):
    try:
        with av.open(io.BytesIO(data), format="mp3") as source:
            return sum(frame.samples / frame.sample_rate for frame in source.decode(audio=0))
    except Exception:
        return 0.0


def playable_prefix(chunks):
    prefix = bytearray()
    for at, packet in chunks:
        prefix.extend(packet)
        if audio_duration(bytes(prefix)) >= 0.12:
            return at
    return None


async def compare(text, *, v3=False, stream_first=False):
    import main

    request = {
        "model": "voxtral-mini-tts-3-0" if v3 else main.TTS_REMOTE_MODEL,
        "input": text, "response_format": "mp3",
        **({"voice_id": "en_paul_neutral"} if v3 else {"voice": main.TTS_REMOTE_VOICE}),
    }
    client = main._stt_client()
    url = f"{main.LLM_BASE_URL.rstrip('/')}/audio/speech"
    headers = {"Authorization": f"Bearer {main._require('LLM_API_KEY')}"}
    result = {"model": request["model"], "characters": len(text)}
    for streaming in ((True, False) if stream_first else (False, True)):
        kind = "stream" if streaming else "batch"
        started = time.perf_counter()
        try:
            async with client.stream("POST", url, headers=headers, json={**request, "stream": streaming},
                                     timeout=15.0) as response:
                row = {"http": response.status_code}
                chunks = []
                if response.status_code == 200:
                    if streaming and "text/event-stream" in response.headers.get("content-type", ""):
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            raw = line.removeprefix("data:").strip()
                            if raw == "[DONE]":
                                break
                            event = json.loads(raw)
                            encoded = event.get("audio_data") or (event.get("data") or {}).get("audio_data")
                            if encoded:
                                chunks.append((time.perf_counter() - started, base64.b64decode(encoded)))
                    else:
                        body = await response.aread()
                        data = base64.b64decode(json.loads(body)["audio_data"]) if body.startswith(b"{") else body
                        if streaming:
                            row["transport"] = "buffered"
                        chunks.append((time.perf_counter() - started, data))
                    main._track_usage(tts_mistral_chars=len(text))
                row["total_sec"] = round(time.perf_counter() - started, 3)
            if chunks:
                first = await asyncio.to_thread(playable_prefix, chunks)
                seconds = await asyncio.to_thread(audio_duration, b"".join(data for _, data in chunks))
                row.update(first_playable_sec=round(first, 3) if first is not None else None,
                           first_chunk_sec=round(chunks[0][0], 3), chunks=len(chunks),
                           decoded_sec=round(seconds, 3))
        except Exception as exc:
            row = {"error": type(exc).__name__, "total_sec": round(time.perf_counter() - started, 3)}
        result[kind] = row
    return result


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, choices=range(1, 13), default=6)
    parser.add_argument("--v3", action="store_true")
    args = parser.parse_args()
    for i in range(args.runs):
        result = await compare(PHRASES[i % len(PHRASES)], v3=args.v3, stream_first=i % 2 == 1)
        print(json.dumps({"run": i + 1, **result}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
