"""Проверка разбора страниц открытого банка ФИПИ.

Тест работает на СОХРАНЁННОЙ странице (fixtures/fipi_page.html), а не по сети:
чужой сайт не должен падать от наших тестов, а тест не должен зависеть от того,
доступен ли он сейчас. Страница сохранена как есть, в windows-1251.

Запуск:  .\\.venv\\Scripts\\python.exe test_fipi_import.py
"""

from __future__ import annotations

import os
import sys

import fipi_import as fi

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "fipi_page.html")


def load() -> str:
    with open(FIXTURE, "rb") as f:
        return f.read().decode("cp1251", errors="replace")


def main() -> int:
    bad: list[str] = []
    items = fi.parse_page(load())
    by_kind: dict[str, list[dict]] = {}
    for it in items:
        by_kind.setdefault(it["kind"], []).append(it)

    print(f"на странице распознано заданий: {len(items)} "
          f"({', '.join(f'{k}: {len(v)}' for k, v in sorted(by_kind.items()))})")

    if not items:
        print("FAIL страница не разобралась вообще")
        return 1

    # 1. Берём только форматы 2026. Старое задание 3 «photo album» и неустные
    #    задания обязаны отсеиваться, иначе ученик тренирует отменённый формат.
    if any(it["kind"] not in ("reading", "dialogue", "monologue") for it in items):
        bad.append("в выдаче есть тип, которого мы не импортируем")
    if "photo album" in load() and any("photo album" in it["brief"] for it in items):
        bad.append("устаревшее задание 3 «photo album» просочилось в импорт")
    print(f"{'OK  ' if not bad else 'FAIL'} отбор форматов: только 39, 40 и 42")

    # 2. У каждого задания есть номер ФИПИ — по нему работает защита от дублей.
    noid = [it for it in items if not it["fipi_id"]]
    if noid:
        bad.append(f"без номера ФИПИ: {len(noid)}")
    ids = [it["fipi_id"] for it in items]
    if len(ids) != len(set(ids)):
        bad.append("номера заданий повторяются внутри страницы")
    print(f"{'OK  ' if not noid else 'FAIL'} у всех заданий есть номер ФИПИ")

    # 3. Диалог: заголовок объявления и ровно четыре пункта для вопросов.
    for it in by_kind.get("dialogue", []):
        if len(it.get("points", [])) != 4:
            bad.append(f"диалог {it['fipi_id']}: пунктов {len(it.get('points', []))}, а не 4")
        if not it.get("ad"):
            bad.append(f"диалог {it['fipi_id']}: не найден заголовок объявления")
        if not it["images"]:
            bad.append(f"диалог {it['fipi_id']}: нет картинки объявления")
    print(f"{'OK  ' if not bad else 'FAIL'} задание 40: объявление и четыре пункта")

    # 4. Чтение: текст лежит КАРТИНКОЙ, без неё задание бесполезно —
    #    разбор №39 сверяет слова ученика с эталоном.
    for it in by_kind.get("reading", []):
        if not it["images"]:
            bad.append(f"чтение {it['fipi_id']}: нет картинки с текстом")
    print(f"{'OK  ' if not bad else 'FAIL'} задание 39: картинка с текстом на месте")

    # 5. Монолог: тема проекта, четыре пункта плана и ровно две фотографии.
    for it in by_kind.get("monologue", []):
        if not it.get("topic"):
            bad.append(f"монолог {it['fipi_id']}: не извлеклась тема проекта")
        if len(it.get("plan", [])) != 4:
            bad.append(f"монолог {it['fipi_id']}: пунктов плана {len(it.get('plan', []))}, а не 4")
        if len(it["images"]) != 2:
            bad.append(f"монолог {it['fipi_id']}: фотографий {len(it['images'])}, а не 2")
    print(f"{'OK  ' if not bad else 'FAIL'} задание 42: тема, план и две фотографии")

    # 6. Ссылки на картинки абсолютные и ведут на ФИПИ: относительный путь
    #    «../../docs/...» из iframe скачать нельзя.
    for it in items:
        for u in it["images"]:
            if not u.startswith("https://ege.fipi.ru/docs/"):
                bad.append(f"{it['fipi_id']}: путь картинки не абсолютный — {u[:60]}")
    print(f"{'OK  ' if not bad else 'FAIL'} пути картинок абсолютные")

    # 7. Классификатор: отменённый формат и посторонние задания не берём.
    checks = [
        ("Task 3. These are photos from your photo album. Choose one photo", None),
        ("Установите соответствие между текстами A-G и заголовками", None),
        ("Task 1. Imagine that you are preparing a project with your friend. "
         "You have found some interesting material and you want to read this "
         "text to your friend.", "reading"),
        ("Task 2. Study the advertisement. You are considering going", "dialogue"),
        ("Task 4. Imagine that you are doing a project together with your friend. "
         "Leave a voice message to your friend.", "monologue"),
        ("Task 3. You are going to give an interview. You have to answer five "
         "questions.", None),  # вопросов в банке нет — брать нечего
    ]
    for text, want in checks:
        got = fi.classify(text)
        if got != want:
            bad.append(f"классификатор: «{text[:40]}…» → {got}, ждали {want}")
    print(f"{'OK  ' if not bad else 'FAIL'} классификатор: {len(checks)} формулировок")

    print()
    if bad:
        print(f"ПРОВАЛЕНО {len(bad)}:")
        for b in bad[:12]:
            print("  -", b)
        return 1
    print("Разбор банка ФИПИ работает как задумано.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
