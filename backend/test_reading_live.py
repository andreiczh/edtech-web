"""Живая сетка задания 39: от чистого чтения до каши, через настоящий сервер.

Каждый случай — настоящий звук (edge-tts) в настоящий эндпоинт /task_feedback.
Для каждого заранее записан балл, который ДОЛЖЕН выйти по критериям ФИПИ, и в
сводке видно, где система права, а где нет.

Зачем это лежит в репозитории, а не гоняется руками. 05.08.2026 ровно такая
сетка нашла две поломки, невидимые юнит-тестам: модель списывала явные подмены
(teachers -> doctors) на «шум распознавания» и ставила 1/1, а паттерн из трёх
искажённых окончаний проходил как чистое чтение. Юнит-тесты проверяют шкалу и
сборку, но НЕ суждение живой модели — его проверяет только живой прогон.

Правишь reading_prompt, reading_diff или score_reading — прогони сетку.
Требует запущенного сервера (uvicorn main:app) и ключа в backend/.env:
    .\.venv\Scripts\python.exe test_reading_live.py
Цена прогона: ~7 вызовов STT + LLM. Эталон здесь синтетический — живой голос
с акцентом эта сетка не заменяет.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE = os.environ.get("GRID_BASE_URL", "http://127.0.0.1:8000")
ADMIN = os.environ.get("ADMIN_KEY", "local-admin-key")
H = {"X-Device": ADMIN, "X-Admin-Key": ADMIN}
VOICE = "en-US-GuyNeural"
LOCAL = os.environ.get("OUTBOUND_LOCAL_IP") or None

REF = (
    "Scientists have discovered that reading aloud helps people remember "
    "information much better than reading silently. When we speak the words, "
    "two things happen at once. We produce the sound and we hear it. This "
    "double action makes the memory stronger. Teachers often use this simple "
    "trick in class."
)

# Каждый случай: (метка, что читаем, ожидаемый балл, что обязано попасть в разбор)
CASES = [
    ("чистое чтение", REF, 1, []),

    # Одна подмена слова — оговорка, балл остаётся, но ошибка ДОЛЖНА быть видна.
    ("одна подмена (simple->difficult)",
     REF.replace("this simple trick", "this difficult trick"), 1, ["simple"]),

    # Три разные подмены — по критериям 0.
    ("три подмены",
     REF.replace("discovered", "discussed")
        .replace("stronger", "strange")
        .replace("Teachers", "Doctors"), 0, ["discovered", "stronger"]),

    # Искажение грамматических форм — типичная ошибка чтеца.
    ("формы слов (helps->help, makes->make, happen->happens)",
     REF.replace("helps", "help").replace("makes", "make")
        .replace("things happen", "things happens"), 0, []),

    # Не дочитан хвост.
    ("оборван хвост (последние 7 слов)",
     " ".join(REF.split()[:-7]), 0, []),

    # Вставки-паразиты при верном тексте: балл снимать не за что.
    ("вставки-паразиты (well, uh)",
     REF.replace("Scientists have", "Well, scientists have")
        .replace("This double", "Uh, this double"), 1, []),

    # Отсебятина по теме — не чтение.
    ("пересказ своими словами",
     "Reading aloud is very useful because you remember better. "
     "Teachers like this method and use it in schools very often.", 0, []),
]


async def say(text: str) -> bytes:
    import aiohttp
    import edge_tts
    for _ in range(4):
        conn = aiohttp.TCPConnector(local_addr=(LOCAL, 0)) if LOCAL else None
        try:
            out = b""
            async for ch in edge_tts.Communicate(text, VOICE, connector=conn).stream():
                if ch["type"] == "audio":
                    out += ch["data"]
            if out:
                return out
        except Exception as e:
            print(f"    (сеть: {type(e).__name__})")
            await asyncio.sleep(2.0)
    return b""


def grade(audio: bytes) -> dict | None:
    c = httpx.Client(timeout=180.0, trust_env=False)
    for attempt in range(3):
        try:
            r = c.post(f"{BASE}/task_feedback", headers=H,
                       files={"audio": ("a.mp3", audio, "audio/mpeg")},
                       data={"kind": "reading",
                             "payload": json.dumps({"referenceText": REF}),
                             "persona": "tutor"})
            break
        except Exception as e:
            print(f"    (сеть: {type(e).__name__}, повтор {attempt + 1})")
            time.sleep(3.0)
    else:
        return None
    if r.status_code != 200:
        print(f"    HTTP {r.status_code}: {r.text[:200]}")
        return None
    data = r.json()
    if data.get("detail"):
        print(f"    ОТКАЗ: {data['detail'][:160]}")
        return None
    return data


async def main():
    verdicts = []
    for label, text, want, must_catch in CASES:
        print(f"\n=== {label} (ждём {want}/1) ===")
        audio = await say(text)
        if not audio:
            print("    синтез не удался")
            continue
        data = grade(audio)
        if not data:
            verdicts.append((label, want, None, False))
            continue
        fb = data["feedback"]
        got = fb["score"]
        errors = fb.get("errors") or []
        err_text = " | ".join(
            f"«{e.get('quote')}»->«{e.get('correction')}»" for e in errors) or "—"
        caught = all(
            any(word.lower() in (e.get("correction") or "").lower()
                or word.lower() in (e.get("quote") or "").lower()
                for e in errors)
            for word in must_catch) if must_catch else True
        mark = "OK " if got == want and caught else "РАСХОЖДЕНИЕ"
        print(f"    [{mark}] балл {got}/1, ошибок в разборе {len(errors)}")
        print(f"    итог: {fb['summary'][:180]}")
        print(f"    ошибки: {err_text[:260]}")
        verdicts.append((label, want, got, caught))

    print("\n" + "=" * 74)
    print("СВОДКА")
    print("=" * 74)
    good = 0
    for label, want, got, caught in verdicts:
        status = ("ok" if got == want and caught else
                  f"балл {got} вместо {want}" if got is not None and got != want
                  else "ошибка не показана" if got == want else "не прошёл")
        if got == want and caught:
            good += 1
        print(f"  {label:<46} {status}")
    print(f"\nСошлось {good} из {len(verdicts)}")
    return 0 if good == len(verdicts) else 1


sys.exit(asyncio.run(main()))
