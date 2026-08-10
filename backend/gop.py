"""Насколько звук подтверждает КАЖДОЕ слово эталона: GOP по чтению вслух.

Зачем это существует. Задание 1 официально оценивается произношением, а система
до сих пор судит по расшифровке и звука не слышит — главный честный пробел
продукта. Спрашивать модель «как прозвучало» уже пробовали: она отвечала
одинаково на любое аудио (docs/DECISIONS.md §6.5). Здесь другой путь: ничего не
спрашиваем, а ИЗМЕРЯЕМ.

Что именно измеряется. Не «что модель услышала» (это уже делает распознавание,
и сверка с эталоном ловит выданные ошибки), а обратное: НАСКОЛЬКО ЗВУК
ПОДДЕРЖИВАЕТ ИМЕННО ТО СЛОВО, которое написано в тексте. Декодер Whisper
прогоняется по НАВЯЗАННЫМ токенам эталона, и ctranslate2 отдаёт вероятность
каждого. Слово, прочитанное неверно, получает низкую вероятность, даже если
распознавание всё равно написало правильное — а это ровно тот случай, ради
которого фонемный разбор и нужен.

Замер 10.08.2026 (docs/DECISIONS.md §6.15), двенадцать минимальных пар из
методички ФИПИ, три условия:

    подмена звука против верного чтения носителя   AUC 0.958 (base.en)
    то же, но против сильного русского акцента     AUC 0.847
    small.en с нормировкой на средний уровень      AUC 0.903

Цена: 3.1 с на запись 29 с у base.en на слабом ядре — ВТРОЕ дешевле обычного
распознавания той же моделью, потому что лучевого поиска здесь нет, декодер
идёт по уже известным токенам.

ЧЕГО ЗДЕСЬ НЕТ И НЕ БУДЕТ БЕЗ КАЛИБРОВКИ. Балла. Шкала ЕГЭ решается на границе
«не более 5 фонетических ошибок», а пороги сняты на синтезированной речи —
живой школьник даст другое распределение. Поэтому модуль СЧИТАЕТ и СКЛАДЫВАЕТ
числа, а решение «это ошибка» принимается позже, когда наберётся реальная речь.
"""

from __future__ import annotations

import os
import statistics
import threading
import time

# Модель намеренно та же по семейству, что у delivery.py: веса скачиваются один
# раз на процесс, и держать в памяти два разных размера незачем.
GOP_MODEL = os.environ.get("GOP_MODEL", "base.en").strip()

# Сколько секунд аудио соответствует одному окну кодировщика Whisper.
WINDOW_SEC = 30.0
_SR = 16000

# Слово короче этого в эталоне не оценивается: на артикле в 60 мс вероятность
# скачет от соседей, а не от произношения.
_MIN_WORD_SEC = 0.06

_model = None
_lock = threading.Lock()


def _load():
    """Модель грузится ОДИН раз и лениво. На Render, где разбор выключен, она
    не должна занимать память вовсе."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from faster_whisper import WhisperModel
                _model = WhisperModel(GOP_MODEL, device="cpu", compute_type="int8",
                                      cpu_threads=1, num_workers=1)
    return _model


def _tokenizer(model):
    from faster_whisper.tokenizer import Tokenizer
    return Tokenizer(model.hf_tokenizer, model.model.is_multilingual,
                     task="transcribe", language="en")


def _words_of(text: str) -> list[str]:
    return [w for w in text.split() if w.strip()]


def score(pcm, reference: str, budget_sec: float = 0.0) -> dict:
    """Оценить эталон по звуку. pcm — float32 моно 16 кГц, как в audio_check.

    Возвращает {"ok": bool, "words": [{"word", "p", "p_norm", "start", "end"}],
    "median", "seconds", "model"} либо {"ok": False, "reason": ...}.

    `p_norm` — отношение вероятности слова к медиане по всей записи. Нормировка
    не украшение: у говорящего с акцентом ПРОСЕДАЕТ ВСЁ, и абсолютный порог
    наказал бы его за акцент, а не за ошибку. С нормировкой медиана акцентной
    речи встала на 1.02 — ровно как у носителя, а подмена осталась на 0.01
    (замер §6.15).

    `budget_sec` > 0 — мягкий предел по времени: набрав его, прекращаем и
    отдаём то, что успели. Нужен на слабой машине, где полный разбор длинной
    записи может занять минуту.
    """
    from faster_whisper.audio import pad_or_trim

    ref_words = _words_of(reference)
    if not ref_words:
        return {"ok": False, "reason": "нет эталонного текста"}
    if pcm is None or len(pcm) < _SR // 2:
        return {"ok": False, "reason": "запись слишком короткая"}

    started = time.time()
    model = _load()
    tok = _tokenizer(model)
    feats = model.feature_extractor(pcm)
    nmax = model.feature_extractor.nb_max_frames
    frames_per_sec = _SR / model.feature_extractor.hop_length

    out: list[dict] = []
    rest = list(ref_words)
    window_start_sec = 0.0

    for start in range(0, feats.shape[-1], nmax):
        if not rest:
            break
        if budget_sec and time.time() - started > budget_sec:
            break
        # Кодировщик ждёт РОВНО 3000 кадров. Без добивки он получает обрубок и
        # выравнивание выходит мусорным: на этом легко обмануться — у верно
        # прочитанных слов вероятность падала до 0.003, пока не нашлась
        # причина (см. §6.15).
        seg = pad_or_trim(feats[:, start:start + nmax])
        try:
            enc = model.encode(seg)
            tokens = tok.encode(" " + " ".join(rest))
            num_frames = min(nmax, feats.shape[-1] - start)
            # Границы слов и вероятности считает САМ faster-whisper. Своя
            # реализация уже подвела: у односложных слов конец совпадал с
            # началом, длительность выходила нулевой, а вслед за ней врал и
            # счётчик израсходованных слов — окна переставали двигаться.
            # text_tokens здесь — ПАКЕТ (список списков), как и в самой
            # библиотеке; ответ приходит по элементу на каждый список.
            aligned = model.find_alignment(tok, [tokens], enc, num_frames)[0]
        except Exception as e:  # noqa: BLE001 — разбор не обязан удаваться
            return {"ok": False, "reason": f"{type(e).__name__}: {str(e)[:80]}"}

        consumed = 0
        for item in aligned:
            t_start = float(item["start"])
            t_end = float(item["end"])
            # Слово, дотянувшееся до самого края окна, скорее всего обрезано —
            # пусть его целиком оценит следующее окно.
            if t_end >= WINDOW_SEC - 0.2 and start + nmax < feats.shape[-1]:
                break
            word = item["word"].strip()
            # Токенизатор отдаёт знаки препинания отдельными «словами». Они не
            # произносятся, оценивать их нечего, а в списке слабых мест они
            # выглядели пустыми строками.
            if not any(ch.isalpha() for ch in word):
                consumed += 1
                continue
            out.append({
                "word": word,
                "p": float(item["probability"]),
                "start": round(window_start_sec + t_start, 2),
                "end": round(window_start_sec + t_end, 2),
                "dur": round(max(0.0, t_end - t_start), 3),
            })
            consumed += 1

        if consumed == 0:
            break  # окно ничего не дало — дальше будет то же самое
        rest = rest[consumed:]
        window_start_sec += WINDOW_SEC

    if not out:
        return {"ok": False, "reason": "не удалось выровнять эталон со звуком"}

    # Нормировка на СОБСТВЕННЫЙ уровень говорящего. Медиана, а не среднее:
    # одно провальное слово не должно сдвигать точку отсчёта.
    med = statistics.median(w["p"] for w in out) or 1e-6
    for w in out:
        w["p_norm"] = round(w["p"] / med, 3)
        w["p"] = round(w["p"], 4)

    return {
        "ok": True,
        "words": out,
        "median": round(med, 4),
        "covered": len(out),
        "of": len(ref_words),
        "seconds": round(time.time() - started, 2),
        "model": GOP_MODEL,
    }


def weakest(result: dict, limit: int = 5) -> list[dict]:
    """Слова с самой слабой поддержкой звуком — кандидаты на «переслушай».

    Порога здесь НЕТ намеренно: пока не набрана живая речь, любое «это ошибка»
    было бы выдумкой. Отдаём просто самые слабые места по возрастанию.
    """
    if not result.get("ok"):
        return []
    words = [w for w in result["words"] if w.get("dur", 0) >= _MIN_WORD_SEC]
    return sorted(words, key=lambda w: w["p_norm"])[:limit]
