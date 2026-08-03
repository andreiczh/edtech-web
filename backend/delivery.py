"""Как прозвучало чтение вслух: ИЗМЕРЕНИЕ, а не суждение модели.

Зачем модуль вообще. Задание 1 официально оценивается исключительно
произношением, а система судит по расшифровке — это главный честный пробел
продукта. Первая попытка закрыть его (спросить мультимодальную модель «как
прозвучало») ПРОВАЛИЛАСЬ: модель отвечала одинаково на любое аудио, вплоть до
«дочитано до конца» на трети текста. Подробности и контрольный опыт —
docs/DECISIONS.md §6.5.

Здесь другой подход: ничего не спрашиваем, а СЧИТАЕМ. faster-whisper (уже в
проекте как запасной STT) отдаёт пословные таймкоды, из них арифметикой
выводятся темп речи и паузы. Проверено на синтезированных записях:
    темп       227 / 137 / 341 слов-в-минуту на обычной / медленной / быстрой;
    паузы      вставленные 1.5 с и 2 с находятся с точностью до 0.1 с и на
               правильной границе слов.
Это тот же принцип, что и во всём оценивании: модель наблюдает, решает код.

ЧЕГО ЗДЕСЬ НЕТ. Оценки произношения и акцента — пословная вероятность
whisper для этого не годится (она падает и от шума, и от имени собственного),
и выдавать её за фонетику было бы тем же обманом, что и путь А. Балл
задания 1 по-прежнему считает ege_scoring по сверке с эталоном; отсюда идёт
только обратная связь о подаче.

ЦЕНА. Это локальный whisper на процессоре: ~1.5-2 с на короткую запись здесь
и заметно больше на бесплатном Render (0.1 CPU), где локальный whisper прямо
запрещён. Поэтому модуль ВЫКЛЮЧЕН по умолчанию и включается переменной
DELIVERY_ANALYSIS=1 там, где процессор есть.
"""

from __future__ import annotations

import os
import tempfile

DELIVERY_ANALYSIS = os.environ.get("DELIVERY_ANALYSIS", "").strip() in ("1", "true", "yes")

# Модель для замера. Самая маленькая намеренно: нам нужны не слова (их уже
# распознал Voxtral), а ТАЙМКОДЫ — на них размер модели влияет слабо, а
# процессорное время растёт кратно.
DELIVERY_MODEL = os.environ.get("DELIVERY_MODEL", "tiny.en").strip()

# Пауза внутри чтения, которую слышно как заминку. 0.6 с выбрано по замеру:
# естественные паузы между предложениями укладываются в 0.3-0.5 с, вставленные
# «запинки» начинаются от 1 с. Порог посередине ловит вторые, не трогая первые.
PAUSE_SEC = 0.6

# Границы нормального темпа чтения вслух. За пределами — не ошибка, а повод
# сказать ученику: на экзамене время ограничено, а тараторить мешает эксперту.
SLOW_WPM, FAST_WPM = 120, 200

_model = None


def _load():
    """Модель грузится ОДИН раз и лениво: держать её в памяти на Render, где
    замер всё равно выключен, незачем."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(DELIVERY_MODEL, device="cpu", compute_type="int8")
    return _model


def measure(audio: bytes, suffix: str = ".mp3") -> dict | None:
    """Темп и паузы по записи. None — замер выключен или не получился.

    Никогда не бросает: подача — дополнение к разбору, из-за неё ученик не
    должен остаться без оценки.
    """
    if not DELIVERY_ANALYSIS:
        return None
    path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio)
            path = f.name
        segments, _ = _load().transcribe(path, word_timestamps=True, language="en")
        words = [w for s in segments for w in (s.words or [])]
        if len(words) < 5:          # слишком мало, чтобы считать темп
            return None

        span = words[-1].end - words[0].start
        if span <= 0:
            return None
        wpm = round(len(words) / span * 60)

        pauses = []
        for a, b in zip(words, words[1:]):
            gap = b.start - a.end
            if gap > PAUSE_SEC:
                pauses.append({"after": a.word.strip()[:30], "sec": round(gap, 1)})
        pauses.sort(key=lambda p: -p["sec"])

        return {
            "wpm": wpm,
            "pace": "slow" if wpm < SLOW_WPM else "fast" if wpm > FAST_WPM else "ok",
            "seconds": round(span, 1),
            "pauses": pauses[:5],
            "pause_count": len(pauses),
        }
    except Exception as e:  # noqa: BLE001 — замер не важнее разбора
        print(f"[delivery] замер не удался ({type(e).__name__}) — пропускаю")
        return None
    finally:
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass


def comment(d: dict, finished: bool) -> str:
    """Одна фраза ученику по ИЗМЕРЕННЫМ числам — без домыслов о произношении.

    `finished` приходит из детерминированной сверки с эталоном
    (ege_scoring.reading_diff), а не из аудио: код это уже знает точно.
    """
    bits = []
    if not finished:
        bits.append("текст не дочитан до конца")
    if d["pace"] == "slow":
        bits.append(f"темп низковат ({d['wpm']} слов/мин) — на экзамене время ограничено")
    elif d["pace"] == "fast":
        bits.append(f"тараторишь ({d['wpm']} слов/мин) — эксперту трудно разобрать")
    if d["pause_count"] >= 3:
        bits.append(f"{d['pause_count']} длинных пауз внутри текста")
    elif d["pause_count"]:
        longest = d["pauses"][0]
        bits.append(f"заминка на {longest['sec']} с после «{longest['after']}»")
    if not bits:
        return f"Темп ровный ({d['wpm']} слов/мин), без заминок."
    return "Читал(а) " + ", ".join(bits) + "."
