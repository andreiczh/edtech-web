"""Живая сетка на НАСТОЯЩЕЙ речи: записи участников ЕГЭ из архива ФИПИ
через боевой /task_feedback, сверка с вердиктами экспертов методички 2026.

Чем отличается от test_ege_live.py: тот гоняет расшифровки-скрипты в обход
распознавания, здесь же проверяется ВЕСЬ конвейер — осмотр звука, Voxtral,
суждения модели, правила кода, шкала. Обе поломки 16.08 (§6.21) были видны
только на живом голосе.

Нужен запущенный сервер и записи на диске (fipi_audio.AUDIO_DIR):

    $env:ADMIN_KEY = "golden-check"; $env:REQUIRE_ACCOUNT = "0"
    .\.venv\Scripts\python.exe -m uvicorn main:app --port 8046
    .\.venv\Scripts\python.exe test_fipi_audio_live.py            # всё
    .\.venv\Scripts\python.exe test_fipi_audio_live.py dialogue   # только №40
    .\.venv\Scripts\python.exe test_fipi_audio_live.py monologue 3  # три прогона
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

import fipi_audio

BASE = os.environ.get("GOLDEN_BASE", "http://127.0.0.1:8046")
KEY = os.environ.get("GOLDEN_KEY", "golden-check")


def post(kind: str, audio_path: str, payload: dict, duration: str):
    data = open(audio_path, "rb").read()
    ext = os.path.splitext(audio_path)[1].lower()
    mime = "audio/ogg" if ext == ".ogg" else "audio/mpeg"
    boundary = "----pingo"
    parts = []
    for name, value in (("kind", kind),
                        ("payload", json.dumps(payload, ensure_ascii=False)),
                        ("variant", f"golden-{kind}"), ("duration", duration)):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                     f'name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                 f'name="audio"; filename="a{ext}"\r\nContent-Type: {mime}'
                 f"\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        BASE + "/task_feedback", data=b"".join(parts), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "X-Device": KEY, "X-Admin-Key": KEY})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        body = r.read()          # дочитать ПОТОК, потом мерить время
    return time.perf_counter() - t0, json.loads(body)


def run_dialogue() -> tuple[int, int]:
    agree_total = total = 0
    sum_ours = sum_exp = 0
    for c in fipi_audio.dialogue_cases():
        time.sleep(3)
        try:
            dt, res = post("dialogue", fipi_audio.path(c["audio"]),
                           {"ad": c["ad"], "points": c["points"]}, "110")
        except Exception as e:  # noqa: BLE001
            print(f"{c['work']}: ЗАПРОС УПАЛ — {type(e).__name__}: {str(e)[:100]}")
            continue
        fb = res.get("feedback")
        if not fb:
            print(f"?? {c['work']}: без feedback — "
                  f"{json.dumps(res, ensure_ascii=False)[:200]}")
            continue
        marks = [x.get("score", 0) for x in (fb.get("criteria") or [])][:4]
        marks += [0] * (4 - len(marks))
        agree = sum(1 for a, b in zip(marks, c["expert"]) if a == b)
        agree_total += agree
        total += 4
        sum_ours += sum(marks)
        sum_exp += sum(c["expert"])
        flag = "==" if marks == c["expert"] else ("~~" if agree >= 3 else "!!")
        print(f"{flag} {c['work']}: наш {marks} = {sum(marks)}/4 | "
              f"эксперты {c['expert']} = {sum(c['expert'])}/4 | "
              f"совпало {agree}/4 | {dt:.0f} с")
    if total:
        print(f"№40 ИТОГ: {agree_total}/{total} вердиктов "
              f"({100 * agree_total / total:.0f}%), баллы наши {sum_ours} / "
              f"экспертов {sum_exp}")
    return agree_total, total


def run_monologue() -> tuple[int, int, float]:
    exact = close = total = 0
    err_sum = 0
    for c in fipi_audio.monologue_cases():
        time.sleep(3)
        try:
            dt, res = post("monologue", fipi_audio.path(c["audio"]),
                           {"brief": c["brief"], "photoFacts": c["photoFacts"]},
                           "170")
        except Exception as e:  # noqa: BLE001
            print(f"{c['work']}: ЗАПРОС УПАЛ — {type(e).__name__}: {str(e)[:100]}")
            continue
        fb = res.get("feedback")
        if not fb:
            print(f"?? {c['work']}: без feedback — "
                  f"{json.dumps(res, ensure_ascii=False)[:200]}")
            continue
        marks = tuple(x.get("score", 0) for x in (fb.get("criteria") or []))[:3]
        while len(marks) < 3:
            marks += (0,)
        expert = tuple(c["expert"])
        total += 1
        delta = abs(sum(marks) - sum(expert))
        err_sum += delta
        exact += marks == expert
        close += delta <= 1
        flag = "==" if marks == expert else ("~~" if delta <= 1 else "!!")
        print(f"{flag} {c['work']}: наш {marks[0]}/{marks[1]}/{marks[2]} = "
              f"{sum(marks)}/10 | эксперты {expert[0]}/{expert[1]}/{expert[2]} "
              f"= {sum(expert)}/10 | разница {delta} | {dt:.0f} с")
    if total:
        print(f"№42 ИТОГ: точно {exact}/{total}, ±1 балл {close}/{total}, "
              f"суммарная ошибка {err_sum}")
    return exact, total, err_sum


def run_reading() -> tuple[int, int]:
    """Чтение вслух: балл 1/0. Эти записи уже служили сеткой фонемной модели
    (§6.24), здесь же они идут через БОЕВОЙ разбор — STT и правила счёта."""
    agree = total = 0
    for c in fipi_audio.reading_cases():
        time.sleep(3)
        try:
            dt, res = post("reading", fipi_audio.path(c["audio"]),
                           {"referenceText": c["reference"]}, "120")
        except Exception as e:  # noqa: BLE001
            print(f"{c['work']}: ЗАПРОС УПАЛ — {type(e).__name__}: {str(e)[:100]}")
            continue
        fb = res.get("feedback")
        if not fb:
            print(f"?? {c['work']}: без feedback — "
                  f"{json.dumps(res, ensure_ascii=False)[:200]}")
            continue
        ours = int(fb.get("score") or 0)
        total += 1
        agree += ours == c["expert_score"]
        flag = "==" if ours == c["expert_score"] else "!!"
        print(f"{flag} {c['work']}: наш {ours}/1 | эксперт {c['expert_score']}/1 "
              f"(ошибок у эксперта {c['expert_errors']}) | {dt:.0f} с")
    if total:
        print(f"№39 ИТОГ: {agree}/{total} вердиктов")
    return agree, total


def main() -> int:
    what = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    for i in range(runs):
        if runs > 1:
            print(f"\n===== прогон {i + 1}/{runs} =====")
        if what in ("all", "reading"):
            run_reading()
        if what in ("all", "dialogue"):
            run_dialogue()
        if what in ("all", "monologue"):
            run_monologue()
    return 0


if __name__ == "__main__":
    sys.exit(main())
