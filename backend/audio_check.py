"""Осмотр записи ДО распознавания: есть ли там вообще речь.

Зачем это появилось (05.08.2026, по разбору жалоб тестировщика). Ученик ничего
не сказал — и получил разбор чужого текста. Воспроизведено на этой машине:
шесть секунд тишины с шумом микрофонного пола Voxtral превратил в
**960 слов** сочинённого монолога («Hello, my name is Sasha. I'm 15 years
old...»). У тестировщика та же поломка вылезла кусками «Мастера и Маргариты».

Это свойство распознавания, а не наша ошибка в коде: модель обязана что-то
вернуть и на пустом входе выдаёт самое вероятное. Но последствие наше — ученику
приписывается несказанное, и он теряет доверие ко всему разбору сразу.

Единственная надёжная защита — не спрашивать. Тишину видно из САМОГО ЗВУКА,
арифметикой, до всякой модели: у неё нет громких кадров. Заодно экономится
вызов распознавания и вызов LLM.

Второй случай, который ловится здесь же: распознавание вернуло горстку слов на
длинной записи. Ученик говорил сорок секунд, а в транскрипте два слова — это
провал распознавания, а НЕ провал ученика, и обвинять его нельзя. Тестировщик
поймал ровно это: «пишет, я прочитал только 2 слова, хотя фактически прочитал
предложение».

Все пороги — с большим запасом в пользу ученика: сомнительное считается речью.
"""

from __future__ import annotations

import io

import av
import numpy as np

# Кадр считаем «громким», если его среднеквадратичная амплитуда выше этого.
# 0.01 от полной шкалы — это примерно −40 дБFS: тише говорит только тот, кто
# не говорит. Шум микрофонного пола на порядок ниже.
_LOUD_RMS = 0.01
_FRAME_MS = 30

# Доля громких кадров, ниже которой запись считается пустой. Два процента от
# сорока секунд — меньше секунды звука: даже одно слово даёт больше.
_MIN_SPEECH_RATIO = 0.02

# Совсем короткая запись — не ответ. Полторы секунды не хватает даже на
# «I don't know».
_MIN_SECONDS = 1.5

# Ниже стольких слов в минуту распознавание считается провалившимся, а не
# ученик — молчавшим. Медленное чтение вслух — 90 слов/мин, очень медленная
# спонтанная речь — 60. Порог 25 не задевает никого, кто действительно говорил.
_MIN_WPM = 25
# На записях короче этого судить о темпе нельзя: одно слово в трёхсекундном
# файле — нормальный ответ на «yes or no».
_WPM_MIN_SECONDS = 8.0


def inspect(data: bytes, ext: str = ".webm") -> dict:
    """Длительность и доля кадров с речью. Ошибка разбора — не приговор:
    возвращаем ok=False, и все проверки ниже пропускают запись дальше.

    Декодируем тем же PyAV, что уже стоит ради перекодирования в wav, — новой
    зависимости не появляется.
    """
    try:
        with av.open(io.BytesIO(data), format=ext.lstrip(".") or None) as c:
            rs = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=16000)
            chunks: list[np.ndarray] = []
            for frame in c.decode(audio=0):
                for f in rs.resample(frame):
                    chunks.append(f.to_ndarray().reshape(-1))
    except Exception:
        try:  # формат не угадали — пусть PyAV определит сам
            with av.open(io.BytesIO(data)) as c:
                rs = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=16000)
                chunks = []
                for frame in c.decode(audio=0):
                    for f in rs.resample(frame):
                        chunks.append(f.to_ndarray().reshape(-1))
        except Exception:
            return {"ok": False}

    if not chunks:
        return {"ok": True, "seconds": 0.0, "speech_ratio": 0.0}

    pcm = np.concatenate(chunks).astype(np.float32) / 32768.0
    sr = 16000
    step = int(sr * _FRAME_MS / 1000)
    if step <= 0 or len(pcm) < step:
        return {"ok": True, "seconds": len(pcm) / sr, "speech_ratio": 0.0}

    frames = pcm[: len(pcm) // step * step].reshape(-1, step)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    return {
        "ok": True,
        "seconds": round(len(pcm) / sr, 2),
        "speech_ratio": round(float((rms > _LOUD_RMS).mean()), 4),
    }


def silence_reason(info: dict) -> str | None:
    """Почему эту запись нельзя разбирать. None — можно."""
    if not info.get("ok"):
        return None  # не смогли посмотреть — не мешаем
    seconds = float(info.get("seconds") or 0.0)
    # Текст уже с заглавной: str.capitalize() на стороне вызова опускал бы
    # регистр во всём остальном предложении («…тишина. проверь, что микрофон»).
    if seconds < _MIN_SECONDS:
        return ("Запись почти пустая — она длится меньше двух секунд. "
                "Проверь микрофон и попробуй ещё раз.")
    if float(info.get("speech_ratio") or 0.0) < _MIN_SPEECH_RATIO:
        return ("В записи нет речи — только тишина. Проверь, что микрофон "
                "включён и разрешён в браузере, и попробуй ещё раз.")
    return None


def recognition_failed(info: dict, transcript: str) -> bool:
    """Похоже ли, что распознавание не справилось, хотя человек говорил.

    Признак: звук длинный и громкий, а слов почти нет. Виноват не ученик, и
    обвинять его нулём за «слишком короткий ответ» нечестно — честнее сказать,
    что не расслышали, и дать переписать.
    """
    if not info.get("ok"):
        return False
    seconds = float(info.get("seconds") or 0.0)
    if seconds < _WPM_MIN_SECONDS:
        return False
    if float(info.get("speech_ratio") or 0.0) < _MIN_SPEECH_RATIO:
        return False  # тишину ловит silence_reason, это другой случай
    words = len(transcript.split())
    return (words * 60.0 / seconds) < _MIN_WPM
