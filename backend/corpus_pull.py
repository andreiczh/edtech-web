# -*- coding: utf-8 -*-
"""Скачать корпус голоса с прода на ноут (пара к backup.py).

Зачем отдельно от бэкапа: записи весят сотни килобайт каждая, и тащить их в
ночной JSON-дамп значит превратить его в неподъёмный. Корпус забирается по
требованию, когда владелец садится размечать или обучать.

Кладёт в ~/pingo-corpus:
    audio/<id>.webm          сами записи
    corpus.jsonl             по строке на запись: разметка системы + вердикт
    corpus.tsv               то же в таблице, чтобы открыть в Excel и слушать

Запуск:
    .\.venv\Scripts\python.exe corpus_pull.py            # всё, чего ещё нет
    .\.venv\Scripts\python.exe corpus_pull.py reading    # только чтение

Ключ — из PINGO_ADMIN_KEY или PROD_ADMIN_KEY в backend/.env (как у backup.py).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("PINGO_BASE_URL", "https://pingo-ai-dpd9.onrender.com")
OUT_DIR = os.path.join(os.path.expanduser("~"), "pingo-corpus")
AUDIO_DIR = os.path.join(OUT_DIR, "audio")
PAGE = 100
RETRIES = 3


def _admin_key() -> str:
    key = os.environ.get("PINGO_ADMIN_KEY", "").strip()
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("PROD_ADMIN_KEY="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def _get(url: str, key: str, binary: bool = False):
    """GET с повторами: сеть у владельца рвётся, а качать тут сотни файлов."""
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"X-Admin-Key": key})
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
            return data if binary else json.loads(data.decode("utf-8"))
        except urllib.error.HTTPError:
            raise
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * attempt)
    raise last if last else OSError("не скачалось")


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else ""
    key = _admin_key()
    if not key:
        print("Нет ключа: задай PINGO_ADMIN_KEY или PROD_ADMIN_KEY в backend/.env")
        return 1
    os.makedirs(AUDIO_DIR, exist_ok=True)

    items, offset = [], 0
    while True:
        url = (f"{BASE}/admin/corpus?limit={PAGE}&offset={offset}"
               + (f"&kind={kind}" if kind else ""))
        body = _get(url, key)
        batch = body.get("items") or []
        items.extend(batch)
        if offset == 0:
            st = body.get("stats", {})
            print(f"На сервере: {st.get('total', 0)} записей, {st.get('mb', 0)} МБ, "
                  f"учеников {st.get('students', 0)}, проверено {st.get('verified', 0)}")
            print(f"По заданиям: {st.get('by_kind', {})}")
        if len(batch) < PAGE:
            break
        offset += PAGE

    if not items:
        print("Корпус пуст — собирать пока нечего.")
        return 0

    fresh = 0
    for it in items:
        path = os.path.join(AUDIO_DIR, f"{it['id']}.webm")
        if os.path.exists(path) and os.path.getsize(path) == it.get("bytes", 0):
            continue
        try:
            audio = _get(f"{BASE}/admin/corpus/{it['id']}/audio", key, binary=True)
        except Exception as e:  # noqa: BLE001 — одна запись не должна ронять всё
            print(f"  {it['id'][:8]}: не скачалось ({type(e).__name__})")
            continue
        with open(path, "wb") as f:
            f.write(audio)
        fresh += 1

    with open(os.path.join(OUT_DIR, "corpus.jsonl"), "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    # Таблица для человека: слушать запись и сверять вердикт удобнее в Excel,
    # чем в JSON. Разделитель — табуляция, переводы строк вычищены.
    with open(os.path.join(OUT_DIR, "corpus.tsv"), "w", encoding="utf-8") as f:
        f.write("id\tзадание\tвариант\tсек\tбалл\tмакс\tошибок\t"
                "вердикт владельца\tрасшифровка\n")
        for it in items:
            lab = it.get("labels") or {}
            row = [it["id"], it.get("kind", ""), str(it.get("variant") or ""),
                   f"{it.get('duration', 0):.0f}",
                   "" if it.get("score") is None else str(it["score"]),
                   "" if it.get("max_score") is None else str(it["max_score"]),
                   str(lab.get("errors_n", "")),
                   str(it.get("verified") or ""),
                   (it.get("transcript") or "")[:400]]
            f.write("\t".join(c.replace("\t", " ").replace("\n", " ") for c in row) + "\n")

    print(f"Скачано новых записей: {fresh}, всего в папке: {len(items)}")
    print(f"Папка: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
