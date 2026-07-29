"""Импорт заданий устной части из открытого банка ФИПИ.

ОТКУДА И ПОЧЕМУ ИМЕННО ОТТУДА. Владелец просил тянуть задания с «РЕШУ ЕГЭ»,
но там на странице «Авторские права» копирование заданий, ответов и решений
в сторонние приложения запрещено прямым текстом. ФИПИ — первоисточник тех же
заданий (сам «РЕШУ ЕГЭ» пишет, что берёт их из открытого банка ФИПИ):
явного запрета нет, но и лицензии нет, в подвале «Все права защищены».
Решение владельца от 30.07.2026 — импортировать из ФИПИ, но осторожно:
  * каждое задание приезжает ЧЕРНОВИКОМ (active=0) и публикуется руками;
  * храним номер задания ФИПИ и источник — чтобы происхождение было видно;
  * ходим редко и по одной странице, с паузой между запросами;
  * всё импортированное можно вычистить одной командой.

ЧТО ВАЖНО ЗНАТЬ ПРО САМ БАНК (выяснено разбором 30.07.2026):
1. Банк СМЕШАННЫЙ по форматам. Задание 3 там — старое «These are photos from
   your photo album, choose one photo to describe», которого в ЕГЭ 2026 больше
   нет. Импортировать его нельзя: ученик тренировал бы отменённый тип, а наш
   разбор, написанный под критерии 2026, оценивал бы его неверно. Поэтому
   `classify` берёт ТОЛЬКО задания 1, 2 и 4 нового формата и молча отбрасывает
   всё остальное.
2. Задание 1: текста для чтения в HTML НЕТ — он нарисован картинкой (gif).
   Без распознавания этой картинки задание бесполезно: наш разбор №39 сверяет
   слова ученика с эталоном. Текст достаёт `read_text_from_image` зрением модели.
3. Картинки вставляются не тегом <img>, а вызовом `ShowPictureQ('docs/...')`
   внутри <script>. Обычный парсер тегов их не видит.
4. Страница отдаётся в windows-1251, а не в utf-8.
"""

from __future__ import annotations

import base64
import html
import os
import re
import tempfile
import time

PROJ = "4B53A6CB75B0B5E1427E596EB4931A2A"  # английский язык в банке ФИПИ
HOST = "https://ege.fipi.ru"
BANK = f"{HOST}/bank/questions.php"
SOURCE = "fipi"

# Наши номера заданий: у ФИПИ они Task 1..4, у нас 39..42.
TASK_NO = {"reading": 39, "dialogue": 40, "interview": 41, "monologue": 42}


# --------------------------------------------------------------------------
# Разбор HTML
# --------------------------------------------------------------------------

def _strip_tags(block_html: str) -> str:
    """Текст задания без разметки, служебных блоков и скриптов."""
    s = re.sub(r"<script[\s\S]*?</script>", " ", block_html)
    # Панель «СВОЙСТВА ЗАДАНИЯ» — это метаданные ФИПИ, в задании они не нужны.
    s = re.sub(r'<div class="task-info-panel"[\s\S]*', " ", s)
    s = re.sub(r"<[^>]+>", "\n", s)
    # Именно unescape, а не список замен: у ФИПИ в тексте попадается «&#x2013;»,
    # и точка с запятой ВНУТРИ этой записи резала пункты плана пополам, когда
    # замены делались руками по списку.
    s = html.unescape(s).replace("\xa0", " ")
    # Переносы внутри слов и строк ФИПИ ставит щедро — схлопываем.
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n[ \t]*", "\n", s)
    return re.sub(r"\n{2,}", "\n", s).strip()


def _images(block_html: str) -> list[str]:
    """Пути картинок задания. Ищем и обычные <img>, и вызовы ShowPictureQ."""
    found = re.findall(r"ShowPictureQ\('([^']+)'\)", block_html)
    found += re.findall(r'<img[^>]+src="([^"]*xs3qstsrc[^"]*)"', block_html)
    out = []
    for p in found:
        p = p.lstrip("./")
        if not p.startswith("docs/"):
            p = re.sub(r"^.*?(docs/)", r"\1", p)
        url = f"{HOST}/{p}"
        if url not in out:
            out.append(url)
    return out


def _clean_line(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" ;. ")


def classify(text: str) -> str | None:
    """Тип задания по его формулировке — или None, если брать не надо.

    Отбраковываем сознательно и молча: в банке лежит устаревший формат задания 3
    и полсотни неустных заданий, и это нормально, а не ошибка импорта.
    """
    t = re.sub(r"\s+", " ", text)
    if re.search(r"Task\s*1\.", t) and "read this text to your friend" in t:
        return "reading"
    if re.search(r"Task\s*2\.", t) and "Study the advertisement" in t:
        return "dialogue"
    # Задание 3 (интервью) из банка НЕ берём, хотя формат 2026 у него верный:
    # в HTML лежит только общая инструкция, а сами пять вопросов интервьюер
    # задаёт голосом — в банке их нет ни текстом, ни в картинке (проверено:
    # все 32 таких задания различаются только номером). Импортировать их —
    # значит завести три десятка пустых близнецов.
    if re.search(r"Task\s*4\.", t) and re.search(r"voice message", t, re.I):
        return "monologue"
    return None


def _parse_dialogue(text: str) -> dict:
    """Задание 2: рекламное объявление и четыре пункта для вопросов."""
    points = [_clean_line(m) for m in re.findall(r"\n\s*\d\)\s*([^\n]+)", "\n" + text)]
    intro = ""
    m = re.search(r"(You are [\s\S]*?more information[^\n]*)", text)
    if m:
        intro = _clean_line(m.group(1))
    # Заголовок объявления — строка между установкой и списком пунктов.
    caption = ""
    m = re.search(r"following:\s*\n([^\n]+)", text)
    if m and not re.match(r"^\s*\d\)", m.group(1)):
        caption = _clean_line(m.group(1))
    return {"ad": caption, "intro": intro, "points": points[:4]}


def _parse_monologue(text: str) -> dict:
    """Задание 4: тема проекта и план из четырёх пунктов."""
    topic = ""
    m = re.search(r"project\s*[“\"‘']([^”\"’']+)", text)
    if m:
        topic = _clean_line(m.group(1))
    # Границу плана ищем двумя способами. По фразе «be ready to:» — ненадёжно:
    # ФИПИ рассыпает по тексту лишние пробелы прямо внутри слов («do ing»,
    # «t he»), и на 16 заданиях из 34 фраза просто не находилась. Поэтому
    # запасной и более верный ориентир — сами маркеры пунктов «·».
    flat = re.sub(r"\s+", " ", text)
    start = None
    m = re.search(r"be\s*ready\s*to\s*:", flat, re.I)
    if m:
        start = m.end()
    elif "·" in flat:
        start = flat.index("·")
    plan = []
    if start is not None:
        tail = flat[start:]
        m = re.search(r"You will speak|You have to talk", tail)
        body = tail[: m.start()] if m else tail
        # Пункты разделены либо маркерами «·», либо точкой с запятой.
        chunks = body.split("·") if "·" in body else body.split(";")
        for chunk in chunks:
            chunk = _clean_line(chunk).lstrip("·").strip()
            if len(chunk) > 12:
                plan.append(chunk)
    return {"topic": topic, "plan": plan[:4]}


def parse_page(page_html: str) -> list[dict]:
    """Страница банка → список заданий устной части нужного формата.

    Чистая функция: сети не касается, поэтому проверяется на сохранённой
    странице (см. test_fipi_import.py).
    """
    out: list[dict] = []
    for block in re.split(r'(?=<div class="qblock)', page_html)[1:]:
        text = _strip_tags(block)
        kind = classify(text)
        if not kind:
            continue
        # Номер ищем в СЫРОМ блоке: он лежит в панели «СВОЙСТВА ЗАДАНИЯ»,
        # которую _strip_tags намеренно отрезает вместе с метаданными ФИПИ.
        m = re.search(r"Номер:\s*(?:<[^>]+>\s*)*([0-9A-F]{4,8})", block)
        fipi_id = m.group(1) if m else ""
        if not fipi_id:
            continue
        # Инструкцию оставляем как есть — это и есть формулировка задания.
        brief = _clean_line(re.sub(r"^Дайте развернутый ответ\.\s*", "", text.split("\ni\n")[0]))
        item = {
            "fipi_id": fipi_id,
            "kind": kind,
            "task_no": TASK_NO[kind],
            "brief": brief,
            "images": _images(block),
        }
        if kind == "dialogue":
            item.update(_parse_dialogue(text))
        elif kind == "monologue":
            item.update(_parse_monologue(text))
        out.append(item)
    return out


# --------------------------------------------------------------------------
# Сеть
# --------------------------------------------------------------------------

def ca_bundle() -> str:
    """Путь к набору корневых сертификатов, которым проверяем ФИПИ.

    Обычная проверка на ege.fipi.ru падает с «unable to get local issuer»,
    и это НЕ российский УЦ и не наша беда: сертификат выдан GlobalSign, но
    сервер ФИПИ не досылает промежуточный сертификат цепочки. Браузеры и curl
    достают его сами, python — нет. Поэтому недостающее звено лежит рядом
    (certs/) и подклеивается к обычному набору. Отключать проверку из-за чужой
    недоконфигурации не станем: это ровно тот случай, когда «и так работает»
    превращается в тихую дыру.
    """
    import certifi  # noqa: PLC0415 — нужен только здесь

    here = os.path.dirname(os.path.abspath(__file__))
    extra = os.path.join(here, "certs", "globalsign-gcc-r3-dv-tls-2020.pem")
    if not os.path.exists(extra):
        return certifi.where()
    merged = os.path.join(tempfile.gettempdir(), "pingo_fipi_ca.pem")
    if not os.path.exists(merged):
        with open(merged, "w", encoding="utf-8") as out:
            for src in (certifi.where(), extra):
                with open(src, encoding="utf-8") as f:
                    out.write(f.read() + "\n")
    return merged


def client(timeout: float = 60.0):
    """httpx-клиент для похода в ФИПИ: со своей цепочкой и честным User-Agent."""
    import httpx  # noqa: PLC0415

    return httpx.Client(
        timeout=timeout, verify=ca_bundle(), trust_env=False, follow_redirects=True,
        headers={"User-Agent": "PingoAI/1.0 (edu task import; contact via pingo-ai.onrender.com)"},
    )


def download_image(cl, url: str) -> tuple[bytes, str]:
    """Картинка задания. Возвращает байты и mime."""
    r = cl.get(url)
    r.raise_for_status()
    mime = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    if not mime.startswith("image/"):
        raise ValueError(f"не картинка: {mime}")
    return r.content, mime


def fetch_page(client, page: int, pagesize: int = 20) -> str:
    """Одна страница банка. Кодировка windows-1251 — декодируем явно.

    `client` — httpx.Client снаружи: так вызывающий сам решает про таймауты,
    проверку сертификата и паузы между запросами.
    """
    r = client.get(BANK, params={"proj": PROJ, "page": page, "pagesize": pagesize})
    r.raise_for_status()
    return r.content.decode("cp1251", errors="replace")


def crawl(client, pages: int, pagesize: int = 20, pause: float = 1.0) -> list[dict]:
    """Обходит банк постранично. Пауза между страницами обязательна: чужой
    сервер нам ничего не должен, и выжимать из него страницы пачками — свинство."""
    seen: set[str] = set()
    items: list[dict] = []
    for page in range(pages):
        html = fetch_page(client, page, pagesize)
        for it in parse_page(html):
            if it["fipi_id"] in seen:
                continue
            seen.add(it["fipi_id"])
            items.append(it)
        if page + 1 < pages:
            time.sleep(pause)
    return items


# --------------------------------------------------------------------------
# Зрение: то, что в банке нарисовано картинкой, а нам нужно текстом
# --------------------------------------------------------------------------
#
# Здесь работает та же модель, что делает разборы (mistral-small), просто ей
# дают не только текст, но и картинку. Нужно это в двух местах:
#   1. Задание 39: текст для чтения в банке — КАРТИНКА. Наш разбор сверяет
#      слова ученика с эталоном пословно, значит без расшифровки задание мёртвое.
#   2. Задание 42: разбор фотографий не видит, а по критериям ФИПИ обязан ловить
#      фактические ошибки («на фото девочки», когда там мальчики). Значит для
#      каждой фотографии нужно текстовое описание того, что на ней на самом деле.

READ_TEXT_PROMPT = (
    "This image contains the text of an English exam task: a short passage the "
    "student must read aloud. Transcribe the passage EXACTLY as printed, word for "
    "word, keeping the original punctuation. Do not translate, do not summarise, "
    "do not add or fix anything, do not add any commentary. Ignore the task "
    "instruction if it is present and transcribe only the passage itself. If the "
    "image contains no readable passage, answer with the single word NONE."
)

PHOTO_FACT_PROMPT = (
    "Describe what is actually shown in this photograph in one or two English "
    "sentences: who is in it, what they are doing, where it happens, and the "
    "details that matter. Be literal and precise — this description will be used "
    "to catch factual mistakes in a student's spoken description of the same "
    "photo, so do not guess or embellish. If there are no people in the shot, "
    "say so explicitly."
)


def _vision(chat_client, model: str, prompt: str, data: bytes, mime: str,
            max_tokens: int, attempts: int = 4) -> str:
    """Один вопрос модели про одну картинку, с повторами.

    Повторы здесь не перестраховка: первый прогон импорта потерял 35 заданий
    на чтение из 48 именно потому, что полсотни запросов подряд упёрлись в
    лимит модели, а один 429 молча выбрасывал задание целиком. Пауза растёт,
    чтобы не долбить лимит в ту же секунду.
    """
    url = f"data:{mime};base64,{base64.b64encode(data).decode()}"
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            completion = chat_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": url},
                ]}],
                temperature=0.0,
                max_tokens=max_tokens,
            )
            return (completion.choices[0].message.content or "").strip()
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt + 1 < attempts:
                time.sleep(3 * (attempt + 1))
    raise last if last else RuntimeError("зрение не ответило")


def read_text_from_image(chat_client, model: str, data: bytes, mime: str) -> str:
    """Текст для чтения вслух с картинки задания 39. Пусто, если не вышло."""
    text = _vision(chat_client, model, READ_TEXT_PROMPT, data, mime, 900)
    if not text or text.strip().upper().startswith("NONE"):
        return ""
    # Модель иногда оборачивает ответ в кавычки или markdown — снимаем.
    text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text).strip()
    return text.strip('"“”').strip()


def photo_fact(chat_client, model: str, data: bytes, mime: str) -> str:
    """Что на фотографии на самом деле — для ловли фактических ошибок."""
    return _vision(chat_client, model, PHOTO_FACT_PROMPT, data, mime, 220)
