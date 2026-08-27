"""Ступень 2: какой звук ученик произнёс НА САМОМ ДЕЛЕ.

Зачем отдельная ступень. GOP (`gop.py`) отвечает на вопрос «подтверждает ли
звук именно это слово» и на живой речи ФИПИ вердикт эксперта НЕ предсказывает
(docs/DECISIONS.md §6.24): whisper по построению устойчив к акценту, а эксперт
задания 1 судит ровно акцент. Здесь другой прибор — CTC-модель, обученная на
ФОНЕМАХ: она называет сам звук, поэтому видит θ→t, потерю долготы, русское /r/
— то, что перечисляет методичка.

Что уже замерено (§6.20, §6.25) и почему этот код вообще пишется:
  * на 12 минимальных парах: 10/12 верных вердиктов, НОЛЬ ложных обвинений;
  * на 7 живых записях ФИПИ: доля расхождений разделила баллы 1 и 0 без
    пересечения (24.3-29.8% против 30.4-47.6%), а счёт критичных подмен пошёл
    за числом ошибок эксперта (r=0.75) — там, где GOP не разделял вовсе.

ЧЕГО ЗДЕСЬ НЕТ. Балла и показа ученику. Порог не выбран: семь записей — это
не выборка, а анекдот, и подгонять по ним значит выдумывать точность. Модуль
СЧИТАЕТ и КЛАДЁТ В КОПИЛКУ, решение «это ошибка» принимается позже, когда
наберутся размеченные работы (шаг Б, docs/CALIBRATION-SET.md).

Модель не лежит в репозитории: 123 МБ int8-ONNX скачиваются по PHONEME_MODEL_URL
и кэшируются на диске. Пустой URL = ступень 2 выключена, всё остальное работает
как раньше. Конвертировать на Render нечем — там нет torch, и не будет.
"""

from __future__ import annotations

import os
import re
import threading
import time
import urllib.request

# Откуда качать веса и словарь. Пусто -> ступень 2 выключена (так и на localhost,
# пока владелец не выложил файл).
MODEL_URL = os.environ.get("PHONEME_MODEL_URL", "").strip()
VOCAB_URL = os.environ.get(
    "PHONEME_VOCAB_URL",
    "https://huggingface.co/mostafaashahin/wav2vec2-base-timit-phoneme-arpa-39/raw/main/vocab.json",
).strip()
# CMUdict — эталонное произношение слова. Лицензия BSD-2, вес 3.6 МБ.
CMUDICT_URL = os.environ.get(
    "PHONEME_CMUDICT_URL",
    "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict",
).strip()

# Куда класть скачанное. На Render диск эфемерный: после деплоя скачается
# заново, и это осознанная цена — 123 МБ раз в деплой против 123 МБ в git.
CACHE_DIR = os.environ.get("PHONEME_CACHE_DIR", "").strip() or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".models")

# Сколько секунд звука кладём в одно окно. Внимание трансформера квадратично:
# 90 секунд одним куском не влезают в память бесплатного Render.
_WIN_SEC = 20.0
_HOP_SEC = 18.0
_SR = 16000

# Поля вокруг слова: коартикуляция съедает начало и конец, и без запаса
# первый согласный систематически теряется.
_PAD_SEC = 0.3

# ARPA -> словарь модели: ударения срезаем, части фонов модель не различает.
_FOLD = {"AO": "AA", "AX": "AH", "AXR": "ER", "IX": "IH", "ZH": "SH"}

# Смыслоразличительные подмены из методички ФИПИ: именно их считает эксперт.
# Пара (эталон, услышанное) -> короткое имя явления для копилки.
CRITICAL = {
    ("th", "s"): "межзубный",
    ("th", "t"): "межзубный",
    ("th", "f"): "межзубный",
    ("dh", "z"): "межзубный",
    ("dh", "d"): "межзубный",
    ("iy", "ih"): "долгота",
    ("ih", "iy"): "долгота",
    ("uw", "uh"): "долгота",
    ("uh", "uw"): "долгота",
    ("aa", "ah"): "долгота",
    ("ah", "aa"): "долгота",
    ("v", "w"): "v/w",
    ("w", "v"): "v/w",
    ("ae", "eh"): "гласный",
    ("eh", "ae"): "гласный",
    ("ng", "n"): "носовой",
}

_sess = None
_id2tok: dict[int, str] = {}
_blank = 0
_cmu: dict[str, list[str]] = {}
_lock = threading.Lock()
_disabled_reason = ""


def available() -> bool:
    """Настроена ли ступень 2. Без URL модуль молчит и памяти не занимает."""
    return bool(MODEL_URL) and not _disabled_reason


def _fetch(url: str, path: str, timeout: int = 600, retries: int = 4) -> None:
    """Скачивание во временный файл с повторами.

    Повторы не перестраховка: 123 МБ по неидеальной сети рвутся на середине
    (TLS EOF ловился и на дампе базы, и на этом словаре), а оборванная загрузка
    не должна оставить битый файл, который потом падает при каждом запуске.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            if os.path.getsize(tmp) == 0:
                raise OSError("пустой ответ")
            os.replace(tmp, path)
            return
        except Exception as e:  # noqa: BLE001 — сеть; пробуем ещё
            last = e
            print(f"[phoneme] не скачалось ({type(e).__name__}), "
                  f"попытка {attempt} из {retries}: {url.split('/')[-1]}")
            try:
                os.remove(tmp)
            except OSError:
                pass
            time.sleep(3 * attempt)
    raise last if last else OSError("не удалось скачать")


def _load_vocab() -> None:
    global _id2tok, _blank
    import json

    path = os.path.join(CACHE_DIR, "phoneme_vocab.json")
    if not os.path.exists(path):
        _fetch(VOCAB_URL, path, timeout=120)
    raw = json.load(open(path, encoding="utf-8"))
    _id2tok = {int(i): str(t).strip() for t, i in raw.items()}
    _blank = {t: i for i, t in _id2tok.items()}.get("<pad>", 0)


def _load_cmudict() -> None:
    global _cmu
    path = os.path.join(CACHE_DIR, "cmudict.dict")
    if not os.path.exists(path):
        _fetch(CMUDICT_URL, path, timeout=300)
    out: dict[str, list[str]] = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        if not line.strip() or line.startswith(";;;"):
            continue
        parts = line.split()
        word = parts[0].lower()
        if "(" in word:  # альтернативные произношения — берём первое
            continue
        word = re.sub(r"[^a-z']", "", word)
        if not word:
            continue
        phones = []
        for p in parts[1:]:
            bare = re.sub(r"\d", "", p).upper()
            phones.append(_FOLD.get(bare, bare).lower())
        out[word] = phones
    _cmu = out


def _load():
    """Ленивая загрузка: модель качается и поднимается ТОЛЬКО когда реально
    нужен разбор. Холодный старт сервера от неё не страдает."""
    global _sess, _disabled_reason
    if _sess is not None:
        return _sess
    with _lock:
        if _sess is not None:
            return _sess
        import onnxruntime as ort

        path = os.path.join(CACHE_DIR, "phoneme.onnx")
        if not os.path.exists(path):
            _fetch(MODEL_URL, path)
        if not _id2tok:
            _load_vocab()
        if not _cmu:
            _load_cmudict()
        so = ort.SessionOptions()
        # Потоков ровно столько, сколько есть: на бесплатном Render это доля
        # ядра, и разгон потоками там только вредит.
        so.intra_op_num_threads = int(os.environ.get("PHONEME_THREADS", "1"))
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        # БЕЗ АРЕНЫ ПАМЯТИ. Это не тонкая настройка, а условие работоспособности:
        # внимание трансформера на 20-секундном окне выделяет сотни мегабайт
        # промежуточных тензоров, и арена их не отдаёт — пик 1059 МБ при
        # лимите Render 512. Замер 27.08.2026: arena=False -> 279 МБ, метрика
        # бит-в-бит та же (30.4%), время +4%. Уменьшать окно вместо этого
        # НЕ надо: оно сдвигает саму метрику (30.4 -> 28.9% на 4 секундах),
        # а разделение баллов держится на зазоре в 0.6 п.п.
        so.enable_cpu_mem_arena = False
        _sess = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
        return _sess


def unload() -> None:
    """Отпустить память. Путь «модели по очереди» (§6.20): держать резидентно
    и whisper, и фонемную в 512 МБ Render нельзя, а перезагрузка стоит секунды."""
    global _sess
    with _lock:
        _sess = None


def reference_phones(word: str) -> list[str]:
    """Как слово ДОЛЖНО звучать. Пустой список — слова нет в словаре."""
    if not _cmu:
        return []
    return list(_cmu.get(re.sub(r"[^a-z']", "", word.lower()), []))


def decode(pcm) -> list[str]:
    """Жадный CTC-декод окнами: цепочка фонем, как её слышит модель."""
    import numpy as np

    sess = _load()
    win, hop = int(_WIN_SEC * _SR), int(_HOP_SEC * _SR)
    phones: list[str] = []
    for start in range(0, max(1, len(pcm)), hop):
        chunk = np.asarray(pcm[start:start + win], dtype=np.float32)
        if len(chunk) < _SR // 4:  # огрызок короче четверти секунды не несёт фонем
            break
        logits = sess.run(None, {"input": chunk[None, :]})[0][0]
        prev = -1
        for i in logits.argmax(-1):
            i = int(i)
            if i != prev and i != _blank:
                tok = _id2tok.get(i, "")
                if tok and tok not in ("<unk>", "<s>", "</s>", "|", "sil"):
                    phones.append(tok.lower())
            prev = i
        if start + win >= len(pcm):
            break
    return phones


def align(ref: list[str], hyp: list[str]) -> list[tuple[str, str]]:
    """Выравнивание Левенштейна: пары (эталон, услышанное).

    Пропуск -> ("th", ""), вставка -> ("", "t"). Вставки считаем отдельно и в
    ошибки не пишем: заикания и самоисправления дают их пачками, а эксперт за
    них не наказывает (§6.25).
    """
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1,
                           dp[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))
    pairs: list[tuple[str, str]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            pairs.append((ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            pairs.append((ref[i - 1], ""))
            i -= 1
        else:
            pairs.append(("", hyp[j - 1]))
            j -= 1
    pairs.reverse()
    return pairs


def diagnose_words(pcm, words: list[dict], budget_sec: float = 0.0) -> list[dict]:
    """Диагноз по СЛАБЫМ словам: что должно было прозвучать и что прозвучало.

    `words` — куски результата gop.score: {"word", "start", "end"}. Разбираем
    вырезки, а не всю запись: полный декод чтения на бесплатном Render идёт
    минуты и в бюджет фоновой задачи не влезает, а вырезка ~1 с — секунды.

    Возвращает по строке на слово: эталонные и услышанные фонемы, число подмен
    и какие из них смыслоразличительные по методичке.
    """
    import numpy as np

    if not available() or not words:
        return []
    started = time.time()
    out: list[dict] = []
    _load()  # словари нужны до первого reference_phones
    for w in words:
        if budget_sec and time.time() - started > budget_sec:
            break
        word = str(w.get("word") or "").strip()
        ref = reference_phones(word)
        if not ref:
            continue  # слова нет в словаре — сверять не с чем, молчим
        start = max(0.0, float(w.get("start") or 0.0) - _PAD_SEC)
        end = float(w.get("end") or 0.0) + _PAD_SEC
        if end <= start:
            continue
        cut = np.asarray(pcm[int(start * _SR):int(end * _SR)], dtype=np.float32)
        if len(cut) < _SR // 10:
            continue
        heard = decode(cut)
        pairs = align(ref, heard)
        subs = [(a, b) for a, b in pairs if a and b and a != b]
        drops = [a for a, b in pairs if a and not b]
        critical = [{"ref": a, "heard": b, "kind": CRITICAL[(a, b)]}
                    for a, b in subs if (a, b) in CRITICAL]
        out.append({
            "word": word,
            "expected": " ".join(ref),
            "heard": " ".join(heard),
            "subs": len(subs),
            "drops": len(drops),
            "critical": critical,
            # Доля совпавших фонем — одно число, по которому потом выбирается
            # порог. Держим в тех же границах 0..1, что и p_norm ступени 1.
            "match": round(1.0 - min(1.0, (len(subs) + len(drops)) / max(1, len(ref))), 3),
            "seconds": round(time.time() - started, 2),
        })
    return out


def whole_record(pcm, reference: str, budget_sec: float = 0.0) -> dict:
    """Доля расхождений по ВСЕЙ записи — единственная метрика, которая на живых
    записях ФИПИ разделила баллы эксперта.

    Замерено дважды независимо (§6.25 и повтор 27.08.2026, те же семь записей):
    балл 1 -> 24.3-29.8% расхождений, балл 0 -> 30.4-47.6%, классы не
    пересекаются с зазором 0.6 п.п. Ни разбор слабых слов по GOP (r=0.48 с
    числом ошибок эксперта), ни целевая выборка слов со спорными звуками
    (r=0.12) так не умеют — они говорят о словах, а не о чтении целиком.

    ЦЕНА, из-за которой это не включено по умолчанию: 34 с на запись 90 с на
    ноуте в один поток, то есть 4-6 минут на бесплатном Render. Включать
    выборочно (PHONEME_FULL_EVERY), а не на каждую работу.
    """
    import re

    if not available() or not reference:
        return {"ok": False, "reason": "ступень 2 недоступна"}
    started = time.time()
    _load()
    ref: list[str] = []
    for w in re.findall(r"[A-Za-z']+", reference):
        ref.extend(reference_phones(w))
    if len(ref) < 10:
        return {"ok": False, "reason": "эталон не разложился в фонемы"}
    heard = decode(pcm)
    if not heard:
        return {"ok": False, "reason": "звук не дал фонем"}
    pairs = align(ref, heard)
    subs = sum(1 for a, b in pairs if a and b and a != b)
    drops = sum(1 for a, b in pairs if a and not b)
    pct = 100.0 * (subs + drops) / len(ref)
    return {
        "ok": True,
        "phones": len(ref),
        "subs": subs,
        "drops": drops,
        "pct": round(pct, 1),
        # Доля СОВПАВШЕГО — чтобы число росло с качеством, как p_norm ступени 1.
        "match": round(max(0.0, 1.0 - pct / 100.0), 3),
        "seconds": round(time.time() - started, 1),
    }


def summary(rows: list[dict]) -> dict:
    """Свод по записи: сколько слов разобрано и какие явления встретились."""
    if not rows:
        return {"words": 0}
    kinds: dict[str, int] = {}
    for r in rows:
        for c in r.get("critical", []):
            kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    return {
        "words": len(rows),
        "subs": sum(r["subs"] for r in rows),
        "drops": sum(r["drops"] for r in rows),
        "critical": sum(len(r.get("critical", [])) for r in rows),
        "by_kind": kinds,
        "worst": sorted(rows, key=lambda r: r["match"])[:5],
    }
