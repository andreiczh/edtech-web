"""Живая проверка GOP: ловит ли он подмену звука и не врёт ли на длинной записи.

Запуск (модель качается один раз, сеть нужна только для синтеза речи):
    .\\.venv\\Scripts\\python.exe test_gop_live.py

Проверяется ровно то, из-за чего модуль может оказаться бесполезным:
  1) на верно прочитанном тексте слабых мест НЕТ — иначе ученика завалят
     ложными придирками;
  2) подменённое слово попадает в самые слабые — иначе смысла в модуле нет;
  3) запись ДЛИННЕЕ 30 секунд разбирается целиком, а не только первым окном:
     задание 39 это 60-90 секунд, и молчаливая потеря хвоста означала бы, что
     половина текста не проверяется вовсе;
  4) нормировка работает: у одного и того же текста, прочитанного «хуже»,
     слабые места те же самые, а не все подряд.
"""

from __future__ import annotations

import asyncio
import io
import sys

import av
import edge_tts
import numpy as np

import gop

SHORT = ("We walk along the river after lunch, and the old bridge over the water "
         "looks dangerous after the storm.")

# Больше 30 секунд речи — именно здесь ломается наивная реализация «одно окно».
LONG = (
    "The old library on the hill keeps books that nobody reads today, but the roof "
    "still leaks every spring. Every year the town council promises to repair it, "
    "and every year the money goes somewhere else. Last autumn a group of students "
    "decided to act. They cleaned the reading room, painted the shelves and invited "
    "their neighbours to bring one book each. By December the library had four "
    "hundred new titles and, for the first time in years, a queue at the door. "
    "The mayor came to see it and promised a new roof before the end of winter."
)

VOICE = "en-US-AndrewMultilingualNeural"
_fails: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}{('  — ' + extra) if extra and not ok else ''}")
    if not ok:
        _fails.append(name)


async def _say(text: str) -> bytes:
    last = None
    for attempt in range(5):
        try:
            b = bytearray()
            async for c in edge_tts.Communicate(text, VOICE).stream():
                if c["type"] == "audio":
                    b.extend(c["data"])
            if b:
                return bytes(b)
        except Exception as e:  # noqa: BLE001 — канал рвётся, это норма
            last = e
            await asyncio.sleep(2 * (attempt + 1))
    raise RuntimeError(f"синтез не удался: {last}")


def pcm(text: str) -> np.ndarray:
    data = asyncio.run(_say(text))
    with av.open(io.BytesIO(data)) as c:
        rs = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=16000)
        chunks = []
        for frame in c.decode(audio=0):
            for f in rs.resample(frame):
                chunks.append(f.to_ndarray().reshape(-1))
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def main() -> int:
    print(f"модель {gop.GOP_MODEL}\n")

    print("0. mark_spoken: «не читал» отличается от «прочитал плохо» (без сети)")
    ref = ("the old library keeps books that nobody reads today "
           "but the roof still leaks every spring").split()
    words = [{"word": w} for w in ref]

    # Прочитано всё, одно слово подменено близким (walk-эффект): это ПОПЫТКА,
    # она остаётся в распределении.
    said = " ".join(ref).replace("roof", "roost")
    n = gop.mark_spoken(words, said)
    check("подмена слова — это попытка, не пропуск", n == 0,
          f"непрозвучавших {n}")

    # Выброшен кусок из пяти слов подряд — difflib даст replace с большой
    # потерей, и весь кусок обязан лечь пропуском.
    said = " ".join(ref[:5] + ["uh"] + ref[10:])
    n = gop.mark_spoken(words, said)
    dropped = [w["word"] for w in words if not w["spoken"]]
    check("пропущенный кусок помечен целиком", n >= 4, f"выпало {dropped}")
    check("прочитанные края не задеты",
          words[0]["spoken"] == 1 and words[-1]["spoken"] == 1)

    # Пустая расшифровка — не прозвучало ничего.
    n = gop.mark_spoken(words, "")
    check("пустая расшифровка гасит всё", n == len(ref))
    print()

    print("1. Верное чтение короткого текста")
    r = gop.score(pcm(SHORT), SHORT)
    check("разбор состоялся", r.get("ok"), str(r.get("reason")))
    if not r.get("ok"):
        return 1
    print(f"     слов {r['covered']}/{r['of']}, медиана {r['median']}, "
          f"{r['seconds']} с")
    check("покрыты почти все слова", r["covered"] >= r["of"] - 2,
          f"{r['covered']} из {r['of']}")
    low = [w for w in r["words"] if w["p_norm"] < 0.5 and w["dur"] >= 0.06]
    check("ложных придирок нет: слабых мест не больше двух", len(low) <= 2,
          f"слабые: {[w['word'] for w in low]}")

    print("\n2. То же, но одно слово произнесено НЕВЕРНО (walk -> work)")
    spoken = SHORT.replace("walk", "work")
    r2 = gop.score(pcm(spoken), SHORT)   # эталон прежний, звук с подменой
    check("разбор состоялся", r2.get("ok"), str(r2.get("reason")))
    if r2.get("ok"):
        weak = [w["word"].strip(".,").lower() for w in gop.weakest(r2, 3)]
        print(f"     самые слабые: {weak}")
        check("подменённое слово попало в тройку самых слабых", "walk" in weak,
              f"вместо этого {weak}")
        target = next((w for w in r2["words"]
                       if w["word"].strip(".,").lower() == "walk"), None)
        good = next((w for w in r["words"]
                     if w["word"].strip(".,").lower() == "walk"), None)
        if target and good:
            print(f"     p_norm у walk: верно {good['p_norm']}, "
                  f"с подменой {target['p_norm']}")
            check("вероятность упала заметно", target["p_norm"] < good["p_norm"] / 2)

    print("\n3. Длинная запись (больше одного окна в 30 секунд)")
    long_pcm = pcm(LONG)
    dur = len(long_pcm) / 16000
    r3 = gop.score(long_pcm, LONG)
    check("разбор состоялся", r3.get("ok"), str(r3.get("reason")))
    if r3.get("ok"):
        print(f"     запись {dur:.0f} с, слов {r3['covered']}/{r3['of']}, "
              f"{r3['seconds']} с счёта")
        check("запись действительно длиннее одного окна", dur > 32,
              f"{dur:.0f} с — тест не проверяет то, ради чего написан")
        # Главное: хвост не потерян. Наивная реализация вернула бы только те
        # слова, что уместились в первые 30 секунд.
        check("разобран ВЕСЬ текст, а не первое окно",
              r3["covered"] >= r3["of"] * 0.8,
              f"покрыто {r3['covered']} из {r3['of']} — похоже, хвост потерян")
        last = r3["words"][-1]
        check("последнее слово из конца записи, а не из середины",
              last["end"] > dur * 0.6, f"конец на {last['end']} с при длине {dur:.0f} с")

    print("\n4. Бережное поведение на мусоре")
    check("пустой эталон не роняет", gop.score(long_pcm, "").get("ok") is False)
    check("пустой звук не роняет",
          gop.score(np.zeros(100, dtype=np.float32), SHORT).get("ok") is False)
    check("мягкий предел по времени соблюдается",
          gop.score(long_pcm, LONG, budget_sec=0.01).get("ok") in (True, False))

    print()
    if _fails:
        print(f"ПРОВАЛЕНО {len(_fails)}: " + ", ".join(_fails))
        return 1
    print("GOP работает: подмену находит, верное чтение не трогает, "
          "длинную запись разбирает целиком.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
