"""Replay official FIPI audio through the real authenticated grading pipeline.

FIPI_AUDIO_DIR must contain the 2026 archive, with taskN_example_work.ext names.
Credentials are read from a local JSON file (nickname/password), never arguments
or logs. Results contain public official samples only, never bearer tokens.
Run with --help. Missing recordings, failed grading and incomplete criteria are
reported as failures, never silently excluded from the accuracy denominator.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

import httpx
import fipi_audio


def cases():
    for kind, rows in (("reading", fipi_audio.READING_AUDIO),
                       ("dialogue", fipi_audio.DIALOGUE_AUDIO),
                       ("interview", fipi_audio.INTERVIEW_AUDIO),
                       ("monologue", fipi_audio.MONOLOGUE_AUDIO)):
        for row in rows:
            payload = {k: row[k] for k in
                       ("ad", "points", "questions", "brief", "photoFacts") if k in row}
            if kind == "reading":
                payload["referenceText"] = row["reference"]
            yield kind, row, payload


def summarize(rows):
    result = {}
    for kind in ("reading", "dialogue", "interview", "monologue"):
        group = [r for r in rows if r["kind"] == kind]
        good = [r for r in group if r.get("marks") is not None]
        errors = [sum(r["marks"]) - sum(r["expert"]) for r in good]
        result[kind] = {
            "attempted": len(group), "graded": len(good),
            "failed": len(group) - len(good),
            "exact_criteria": sum(r["marks"] == r["expert"] for r in good),
            "exact_total": sum(e == 0 for e in errors),
            "within_one": sum(abs(e) <= 1 for e in errors),
            "mae": round(sum(map(abs, errors)) / len(errors), 3) if errors else None,
            "bias": round(sum(errors) / len(errors), 3) if errors else None,
            "item_agreement": sum(a == b for r in good for a, b in zip(r["marks"], r["expert"])),
            "items": sum(len(r["expert"]) for r in good),
        }
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", required=True)
    p.add_argument("--credentials", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--kinds", nargs="+", default=["reading", "dialogue", "interview", "monologue"])
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--works", nargs="+", help="Optional official work IDs to replay")
    p.add_argument("--resume", action="store_true")
    args = p.parse_args()
    selected = [(kind, row, payload) for kind, row, payload in cases() if kind in args.kinds and (not args.works or row["work"] in args.works)]
    missing = [row["audio"] for _, row, _ in selected if not Path(fipi_audio.path(row["audio"])).is_file()]
    if missing:
        p.error("Missing official recordings: " + ", ".join(missing))
    secret = json.loads(args.credentials.read_text())
    report = json.loads(args.output.read_text()) if args.resume and args.output.exists() else {"rows": []}
    with httpx.Client(base_url=args.base.rstrip("/"), timeout=240, follow_redirects=True,
                      proxy=urllib.request.getproxies().get("https")) as c:
        health = c.get("/health"); health.raise_for_status()
        report["environment"] = {k: v for k, v in health.json().items()
                                 if k in ("build", "llm_model", "stt_task", "stt", "llm_fallback", "grading", "process_uptime_sec")}
        login = c.post("/auth/login", json={k: secret[k] for k in ("nickname", "password")})
        login.raise_for_status()
        c.headers["Authorization"] = "Bearer " + login.json()["session_token"]
        try:
            c.post("/me/settings", json={"corpus_consent": False}).raise_for_status()
            assert c.get("/me/settings").json()["settings"]["corpus_consent"] is False
            for run in range(1, args.runs + 1):
                for kind, row, payload in selected:
                    if any(r["kind"] == kind and r["work"] == row["work"] and r["run"] == run
                           for r in report["rows"]):
                        continue
                    expert = list(row["expert"]) if "expert" in row else [row["expert_score"]]
                    item = {"kind": kind, "work": row["work"], "run": run, "expert": expert,
                            "source_note": row.get("source_note"), "marks": None}
                    audio = Path(fipi_audio.path(row["audio"]))
                    t = time.monotonic()
                    try:
                        with audio.open("rb") as f:
                            r = c.post("/task_feedback", data={"kind": kind, "payload": json.dumps(payload),
                                      "variant": "fipi-2026-" + row["work"], "persona": "tutor"},
                                       files={"audio": (audio.name, f, "audio/ogg" if audio.suffix == ".ogg" else "audio/mpeg")})
                        item["status"] = r.status_code
                        if not r.is_success:
                            # Keep server diagnostics, not just HTTPStatusError.
                            item["server_error"] = r.text[:1500]
                        r.raise_for_status()
                        result = r.json(); item["response"] = result
                        fb = result.get("feedback") or {}
                        if kind == "reading" and "score" in fb:
                            item["marks"] = [fb["score"]]
                        else:
                            marks = [x.get("score") for x in fb.get("criteria", [])]
                            if len(marks) == len(expert) and all(isinstance(m, (int, float)) for m in marks):
                                item["marks"] = marks
                        if item["marks"] is None:
                            item["error"] = result.get("detail", "Missing score/criteria")
                    except Exception as e:
                        item["error"] = type(e).__name__
                    item["seconds"] = round(time.monotonic() - t, 2)
                    try:
                        status = c.get("/health").json()
                        item["build"] = status.get("build")
                        item["process_uptime_sec"] = status.get("process_uptime_sec")
                    except Exception:
                        item["health_unavailable"] = True
                    report["rows"].append(item)
                    report["summary"] = summarize(report["rows"])
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
                    print(json.dumps({k: v for k, v in item.items() if k != "response"}, ensure_ascii=False), flush=True)
                    # Do not turn an outage into a burst of rate-limit failures.
                    time.sleep(12 if item.get("status", 200) >= 400 else 1)
        finally:
            c.post("/auth/logout")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return int(any(r["marks"] is None for r in report["rows"]))


if __name__ == "__main__":
    raise SystemExit(main())
