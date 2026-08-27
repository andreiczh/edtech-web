# -*- coding: utf-8 -*-
"""Тест ступени 2 (фонемный разбор).

Две части. Первая — БЕЗ модели и сети: выравнивание, разбор словаря, разметка
смыслоразличительных подмен. Она обязана проходить везде, в том числе на машине
без весов.

Вторая — ЖИВАЯ, включается сама, если рядом лежит модель (PHONEME_MODEL_URL или
локальный файл ~/pingo-models/base39mm.onnx): синтезируем минимальную пару и
проверяем главное свойство, без которого показывать ученику нельзя — на ВЕРНОМ
чтении обвинений нет, а подмена звука видна.

Запуск: .\.venv\Scripts\python.exe test_phoneme.py
"""
from __future__ import annotations

import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import phoneme  # noqa: E402

failed = 0


def check(cond: bool, name: str, detail: str = "") -> None:
    global failed
    if cond:
        print(f"OK   {name}")
    else:
        failed += 1
        print(f"FAIL {name}: {detail}")


# ------------------------------------------------ выравнивание (без модели)
pairs = phoneme.align(["th", "ih", "ng", "k"], ["s", "ih", "ng", "k"])
subs = [(a, b) for a, b in pairs if a and b and a != b]
check(subs == [("th", "s")], "подмена th->s поймана одна",
      f"получили {subs}")

pairs = phoneme.align(["th", "r", "iy"], ["r", "iy"])
drops = [a for a, b in pairs if a and not b]
check(drops == ["th"], "пропуск первого звука виден", f"получили {drops}")

pairs = phoneme.align(["k", "ae", "t"], ["k", "ae", "t"])
check(all(a == b for a, b in pairs), "верное чтение не даёт расхождений")

pairs = phoneme.align(["k", "ae", "t"], ["k", "ah", "ae", "t"])
ins = [b for a, b in pairs if b and not a]
check(ins == ["ah"], "вставка отмечена отдельно и в подмены не попала",
      f"получили {ins}")

# ------------------------------------------- смыслоразличительные подмены
check(("th", "s") in phoneme.CRITICAL and phoneme.CRITICAL[("th", "s")] == "межзубный",
      "межзубный в списке критичных")
check(("iy", "ih") in phoneme.CRITICAL, "долгота в списке критичных")
check(("k", "g") not in phoneme.CRITICAL,
      "случайная пара НЕ считается критичной (список закрытый)")

# ------------------------------------------------------------- выключенность
saved = phoneme.MODEL_URL
phoneme.MODEL_URL = ""
check(phoneme.available() is False, "без URL ступень 2 выключена")
check(phoneme.diagnose_words([0.0] * 16000, [{"word": "think", "start": 0, "end": 1}]) == [],
      "выключенная ступень 2 молчит, а не падает")
phoneme.MODEL_URL = saved

# ------------------------------------------------------ живая часть, если есть
LOCAL = os.path.expanduser("~/pingo-models/base39mm.onnx")
if not phoneme.MODEL_URL and os.path.exists(LOCAL):
    # file:// URL — модуль скачает «по сети» с локального диска, путь тот же.
    phoneme.MODEL_URL = "file:///" + LOCAL.replace("\\", "/")

if not phoneme.available():
    print("\nЖивая часть пропущена: модели нет (PHONEME_MODEL_URL пуст).")
else:
    import asyncio

    import av
    import edge_tts
    import numpy as np

    VOICE = "en-US-AndrewMultilingualNeural"

    async def say(text: str) -> np.ndarray:
        buf = io.BytesIO()
        for attempt in range(1, 5):
            try:
                buf = io.BytesIO()
                async for ch in edge_tts.Communicate(text, VOICE).stream():
                    if ch["type"] == "audio":
                        buf.write(ch["data"])
                if buf.tell():
                    break
            except Exception:  # noqa: BLE001 — сеть рвётся, пробуем ещё
                await asyncio.sleep(2 * attempt)
        buf.seek(0)
        with av.open(buf) as c:
            rs = av.AudioResampler(format="s16", layout="mono", rate=16000)
            pcm = b"".join(bytes(f.planes[0])[: f.samples * 2]
                           for fr in c.decode(audio=0) for f in rs.resample(fr))
        return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

    async def live() -> None:
        phoneme._load()
        ref = phoneme.reference_phones("think")
        check(ref[:1] == ["th"], "словарь знает think и начинает с межзубного",
              f"получили {ref}")
        check(phoneme.reference_phones("zzzqqq") == [],
              "неизвестное слово даёт пустой эталон, а не выдумку")

        good = await say("Say think again.")
        bad = await say("Say sink again.")
        span = [{"word": "think", "start": 0.55, "end": 1.15}]

        r_good = phoneme.diagnose_words(good, span, budget_sec=120)
        r_bad = phoneme.diagnose_words(bad, span, budget_sec=120)
        check(len(r_good) == 1 and len(r_bad) == 1, "оба разбора состоялись",
              f"{len(r_good)} и {len(r_bad)}")
        if r_good and r_bad:
            g, b = r_good[0], r_bad[0]
            print(f"     верно:  эталон [{g['expected']}] услышано [{g['heard']}] "
                  f"match={g['match']}")
            print(f"     подмена: эталон [{b['expected']}] услышано [{b['heard']}] "
                  f"match={b['match']}")
            check(g["match"] >= b["match"],
                  "верное чтение совпадает с эталоном не хуже подмены",
                  f"{g['match']} против {b['match']}")
            check(not any(c["kind"] == "межзубный" for c in g["critical"]),
                  "на ВЕРНОМ чтении межзубный не обвинён",
                  str(g["critical"]))

        s = phoneme.summary(r_bad)
        check(s["words"] == 1 and "worst" in s, "свод собирается", str(s))

        # Полный декод записи — метрика, на которой держится разделение баллов.
        whole = phoneme.whole_record(good, "Say think again.")
        check(whole.get("ok") and whole["phones"] >= 8,
              "полный декод считает фонемы эталона", str(whole))
        check(0.0 <= whole["match"] <= 1.0, "доля совпадения в границах 0..1",
              str(whole.get("match")))
        print(f"     полный декод: {whole['pct']}% расхождений на {whole['phones']} фонем")
        empty = phoneme.whole_record(good, "")
        check(empty.get("ok") is False, "пустой эталон отвергнут, а не посчитан")

        # Арена памяти обязана быть выключена: с ней пик 1059 МБ при лимите
        # Render 512 (замер 27.08.2026). Это условие работоспособности.
        check(phoneme._sess.get_session_options().enable_cpu_mem_arena is False,
              "арена памяти onnxruntime выключена")
        phoneme.unload()
        check(phoneme._sess is None, "выгрузка отпускает модель")

    asyncio.run(live())

print()
if failed:
    print(f"ПРОВАЛ: {failed}")
    sys.exit(1)
print("Все проверки прошли: фонемная ступень 2.")
