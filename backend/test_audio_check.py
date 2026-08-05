"""Проверка осмотра записи: тишина, речь и провал распознавания.

Почему это важнее, чем кажется. Распознавание НЕ умеет отвечать «здесь ничего
нет»: на шести секундах тишины Voxtral выдал 960 слов сочинённого монолога, и
ученик получил разбор чужого текста. Единственная защита — не спрашивать, а
посмотреть на звук. Если эти пороги однажды поедут, поломка вернётся молча.

Сети не требует: сигналы синтезируются здесь же.

Запуск:  .\.venv\Scripts\python.exe test_audio_check.py
"""

from __future__ import annotations

import io
import sys
import wave

import numpy as np

import audio_check

_fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _fails.append(name)


def wav(samples: np.ndarray, sr: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.clip(samples, -1, 1).astype(np.float32).__mul__(32767)
                      .astype("<i2").tobytes())
    return buf.getvalue()


rng = np.random.default_rng(11)
SR = 16000


def noise(seconds: float, level: float) -> np.ndarray:
    return rng.normal(0, level, int(SR * seconds))


def speech(seconds: float) -> np.ndarray:
    """Грубая имитация речи: громкие куски вперемежку с паузами. Тон здесь не
    важен — проверка смотрит только на громкость."""
    out = []
    t = 0.0
    while t < seconds:
        out.append(rng.normal(0, 0.25, int(SR * 0.4)))   # слово
        out.append(rng.normal(0, 0.001, int(SR * 0.15)))  # пауза
        t += 0.55
    return np.concatenate(out)[: int(SR * seconds)]


print("Осмотр записи")

# --- тишина ---------------------------------------------------------------
quiet = audio_check.inspect(wav(noise(6.0, 0.0006)), ".wav")
check("тишина распознана как тишина",
      quiet["ok"] and quiet["speech_ratio"] < 0.02, f"({quiet})")
check("у тишины есть внятная причина отказа",
      "нет речи" in (audio_check.silence_reason(quiet) or ""))
check("причина отказа начинается с заглавной и не ломает регистр дальше",
      (audio_check.silence_reason(quiet) or "").startswith("В записи")
      and "Проверь" in (audio_check.silence_reason(quiet) or ""))

# Шум микрофонного пола бывает и погромче — но всё равно не речь.
floor = audio_check.inspect(wav(noise(6.0, 0.003)), ".wav")
check("громкий шум пола — всё ещё не речь",
      audio_check.silence_reason(floor) is not None, f"({floor})")

# --- речь -----------------------------------------------------------------
talk = audio_check.inspect(wav(speech(12.0)), ".wav")
check("речь распознана как речь",
      talk["ok"] and talk["speech_ratio"] > 0.5, f"({talk})")
check("речь пропускается дальше", audio_check.silence_reason(talk) is None)
check("длительность считается верно", 11.0 < talk["seconds"] < 13.0, f"({talk})")

# Тихая, но настоящая речь — сомнение трактуем в пользу ученика.
soft = audio_check.inspect(wav(speech(10.0) * 0.12), ".wav")
check("тихая речь не отбраковывается", audio_check.silence_reason(soft) is None,
      f"({soft})")

# --- провал распознавания -------------------------------------------------
long_talk = {"ok": True, "seconds": 40.0, "speech_ratio": 0.7}
check("говорил 40 секунд, а слов два — виновато распознавание",
      audio_check.recognition_failed(long_talk, "Scientists have"))
check("нормальный темп чтения провалом не считается",
      not audio_check.recognition_failed(long_talk, " ".join(["word"] * 90)))
check("на короткой записи о темпе не судим",
      not audio_check.recognition_failed(
          {"ok": True, "seconds": 3.0, "speech_ratio": 0.7}, "yes"))
check("тишину сюда не приплетаем — у неё свой отказ",
      not audio_check.recognition_failed(
          {"ok": True, "seconds": 40.0, "speech_ratio": 0.001}, "две слова"))
check("не смогли осмотреть звук — никого не обвиняем",
      not audio_check.recognition_failed({"ok": False}, "")
      and audio_check.silence_reason({"ok": False}) is None)

# --- задания с ПАУЗАМИ ВНУТРИ (05.08.2026, жалоба «не удалось разобрать»)
#
# У 40 и 41 молчание заложено в само задание: 20 секунд на вопрос, 40 на ответ,
# и почти всё это время ученик думает. Запись длинная, слов мало — и проверка,
# считавшая темп от ПОЛНОЙ длины файла, отвергала каждую такую работу.
task40 = {"ok": True, "seconds": 80.0, "speech_ratio": 0.07}   # 4 вопроса, ~6 с речи
check("№40: четыре коротких вопроса — не провал распознавания",
      not audio_check.recognition_failed(task40, " ".join(["word"] * 20)))
task41 = {"ok": True, "seconds": 200.0, "speech_ratio": 0.06}  # 5 ответов, ~12 с речи
check("№41: короткие ответы в длинной записи — не провал распознавания",
      not audio_check.recognition_failed(task41, " ".join(["word"] * 15)))

# А настоящий сбой обязан ловиться по-прежнему: речи много, слов нет.
check("длинная РЕЧЬ с парой слов — по-прежнему провал распознавания",
      audio_check.recognition_failed(
          {"ok": True, "seconds": 200.0, "speech_ratio": 0.5}, "two words"))
check("темп считается от секунд речи, а не от длины файла",
      abs(audio_check.speech_seconds(task41) - 12.0) < 0.01)

# --- мусор на входе -------------------------------------------------------
check("битые байты не роняют осмотр",
      audio_check.inspect(b"not audio at all", ".webm").get("ok") is False)
check("пустой вход не роняет осмотр",
      audio_check.inspect(b"", ".webm").get("ok") is False)

print()
if _fails:
    print(f"ПРОВАЛЕНО: {len(_fails)} — " + ", ".join(_fails))
    sys.exit(1)
print("Всё сошлось: тишина не пройдёт, речь пройдёт.")
