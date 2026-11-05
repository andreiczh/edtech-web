"""Compare the same exam judge on recorded speech and a human transcript.

Manifest rows contain id, kind, audio (relative to manifest), transcript,
expert (ordered criteria), payload. Use a private manifest for student work.
Run in the configured grading environment; no student records are written.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from ege_scoring import _words


def marks_of(feedback, count):
    if feedback.get("short_response"):
        return [0] * count
    marks = [c.get("score") for c in feedback.get("criteria", [])]
    if len(marks) == count and all(type(mark) is int for mark in marks):
        return marks
    return None


def word_error_rate(reference, actual):
    source, output = _words(reference), _words(actual)
    previous = list(range(len(output) + 1))
    for i, word in enumerate(source, 1):
        current = [i]
        for j, other in enumerate(output, 1):
            current.append(min(previous[j] + 1, current[-1] + 1, previous[j - 1] + (word != other)))
        previous = current
    return round(previous[-1] / max(1, len(source)), 3)


def summarize(rows):
    groups = {}
    for row in rows:
        groups.setdefault((row["kind"], row["path"]), []).append(row)
    summary = {}
    for (kind, path), group in groups.items():
        good = [r for r in group if r.get("marks") is not None]
        cases = {r["id"] for r in group}
        repeatable = 0
        repeated = 0
        for case in cases:
            comparable = [r for r in group if r["id"] == case]
            if len(comparable) >= 2:
                repeated += 1
                if all(r.get("marks") is not None and r["marks"] == comparable[0]["marks"] for r in comparable):
                    repeatable += 1
        summary[f"{kind}/{path}"] = {
            "attempts": len(group),
            "graded": len(good),
            "exact_vectors": sum(r["marks"] == r["expert"] for r in good),
            "criteria_match": [sum(r["marks"][i] == r["expert"][i] for r in good)
                               for i in range(len(group[0]["expert"]))],
            "criterion_denominator": len(good),
            "repeatable_cases": repeatable,
            "repeated_cases": repeated,
        }
    return summary


async def run(args):
    import main

    cases = json.loads(args.manifest.read_text(encoding="utf-8"))
    rows = []
    if not main.os.environ.get("LLM_API_KEY"):
        raise SystemExit("Configure LLM_API_KEY in this environment before running the evaluation.")
    for case in cases:
        audio = args.manifest.parent / case["audio"]
        data = audio.read_bytes()
        main.audio_check.validate_duration(data)
        for repeat in range(1, args.repeats + 1):
            for path in ("audio", "manual"):
                row = {k: case[k] for k in ("id", "kind", "expert")}
                row.update(path=path, repeat=repeat, marks=None)
                started = time.perf_counter()
                try:
                    if path == "audio":
                        result = await asyncio.wait_for(main._task_feedback_work(
                            case["kind"], json.dumps(case["payload"]), data, None, "", 0,
                            filename=audio.name), 150)
                        feedback = result["feedback"]
                        row["wer"] = word_error_rate(case["transcript"], result["transcript"])
                        row["latency"] = result["latency"]
                    else:
                        feedback, _, judge, recheck = await asyncio.wait_for(
                            main._grade_task_text(case["kind"], case["payload"], case["transcript"]), 150)
                        row["latency"] = {"judge": round(judge, 3), "recheck": round(recheck, 3)}
                    row["marks"] = marks_of(feedback, len(case["expert"]))
                except Exception as exc:
                    row["error"] = type(exc).__name__
                row["seconds"] = round(time.perf_counter() - started, 2)
                rows.append(row)
                args.output.write_text(json.dumps({"rows": rows, "summary": summarize(rows)},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(row, ensure_ascii=False), flush=True)
                await asyncio.sleep(1)
    return int(any(r["marks"] is None for r in rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repeats", type=int, choices=range(2, 6), default=2)
    raise SystemExit(asyncio.run(run(parser.parse_args())))
