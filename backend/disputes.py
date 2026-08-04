"""Обратная связь ученика: словарь причин и разбор жалобы. Чистый модуль.

Зачем отдельный файл. Жалоба — это СЫРЬЁ ДЛЯ КАЛИБРОВКИ, а не «сообщение
владельцу»: из пар «наш балл — балл по мнению человека — почему» складывается
свой набор размеченных работ, тот самый, которого проекту не хватает (см.
docs/DECISIONS.md §6.1). Ценность такого набора определяется одним: полнотой
каждой записи. Поэтому проверка обязательных полей живёт ЗДЕСЬ, в коде, а не в
надежде на аккуратность формы: браузер можно обойти, а эту функцию — нет.

Второе назначение — КЛАСТЕРИЗАЦИЯ. Свободный текст «всё плохо» не суммируется;
код причины суммируется. Пятьдесят жалоб с `misheard` на №39 — это задача про
распознавание, а пятьдесят `no_error` на №42 — задача про промпт разбора, и
различить их надо ДО того, как читать полсотни комментариев. Поэтому причина
выбирается из закрытого списка, и список этот один на фронт и на сервер:
названия отдаются наружу (`catalog`), а принимаются только известные коды.
"""

from __future__ import annotations

import json
import re

# Где именно человек может не согласиться с ИИ. Не «раздел приложения», а
# ОБЪЕКТ спора: по нему видно, что пересматривать.
TARGETS = {
    "score":       "балл за работу целиком",
    "item":        "отдельный вопрос или ответ (№40, №41)",
    "criterion":   "критерий ФИПИ (№42)",
    "error":       "конкретная найденная ошибка",
    "talk_review": "разбор разговора",
    "talk_reply":  "реплика собеседника в разговоре",
    "app":         "приложение в целом",
}

KINDS = {"reading", "dialogue", "interview", "monologue", "talk", "app"}

# Причины. Код -> (что видит ученик, к каким объектам спора применима).
# Формулировки нарочно от первого лица ученика: он выбирает своё ощущение, а
# не диагноз системы, — иначе выбирают наугад.
REASONS: dict[str, tuple[str, tuple[str, ...]]] = {
    # --- разбор заданий ЕГЭ
    "misheard":  ("Записали не то, что я сказал",
                  ("score", "item", "criterion", "error", "talk_review")),
    "no_error":  ("Это не ошибка — так можно",
                  ("score", "item", "criterion", "error", "talk_review")),
    "missed":    ("Ошибку не заметили",
                  ("score", "item", "criterion", "talk_review")),
    "unfair":    ("Балл занижен",             ("score", "item", "criterion")),
    "too_soft":  ("Балл завышен",             ("score", "item", "criterion")),
    "unclear":   ("Объяснение непонятное или противоречит себе",
                  ("score", "item", "criterion", "error", "talk_review")),
    # --- разговор
    "off_context": ("Ответил не на то, о чём шла речь",  ("talk_reply",)),
    "invented":    ("Придумал то, чего я не говорил",    ("talk_reply", "talk_review")),
    "shallow":     ("Пусто и скучно, без встречного вопроса", ("talk_reply",)),
    "tone":        ("Ведёт себя не как выбранный характер",   ("talk_reply",)),
    "bad_english": ("Сам говорит с ошибками",            ("talk_reply", "talk_review")),
    # --- отзыв о приложении: всё, что не спор об оценке
    "mic":         ("Микрофон или запись не работают",         ("app",)),
    "task_broken": ("Ошибка в самом задании",  ("score", "item", "criterion", "app")),
    "confusing":   ("Непонятно или неудобно пользоваться",     ("app",)),
    "slow":        ("Долго думает, тормозит",   ("app", "talk_reply")),
    "idea":        ("Идея или пожелание",                      ("app",)),
    # --- общее
    "bug":   ("Что-то сломалось",
              ("score", "item", "criterion", "error", "talk_review", "talk_reply", "app")),
    "other": ("Другое",
              ("score", "item", "criterion", "error", "talk_review", "talk_reply", "app")),
}

# Вердикт владельца по жалобе — то, ради чего копилка и заведена.
VERDICTS = {
    "ours":    "наш балл верен",
    "student": "прав ученик",
    "partial": "частично прав",
}
STATUSES = ("new", "done", "skip")

# Минимальная длина объяснения. Десять символов — не формальность: «не согласен»
# (10 знаков) для калибровки бесполезно, а «сказал is, а не are» (17) уже
# годится. Порог отсекает пустое нажатие, не превращая жалобу в сочинение.
MIN_COMMENT = 10
_MAX_COMMENT = 800
_MAX_SAID = 500
_MAX_TRANSCRIPT = 4000
_MAX_FEEDBACK = 8000
# Обстановка вокруг спора: текст задания, соседние реплики беседы, снимок
# разбора. Без неё жалоба нечитаема через неделю — «балл занижен» невозможно
# пересмотреть, не видя, О ЧЁМ было задание и что ему предшествовало.
# 12000 знаков — с запасом на монолог с четырьмя пунктами плана и хвост
# беседы; при 1000 жалоб это ~20 МБ, для базы пыль.
_MAX_CONTEXT = 12000

_SPACES = re.compile(r"\s+")


def catalog() -> dict:
    """Словарь для фронта: причины с названиями и областью применения.

    Отдаём наружу, чтобы список причин существовал в ОДНОМ месте. Разъехавшись,
    фронт и сервер дали бы жалобы с кодом, который сервер молча выбросит, —
    и потеря нашлась бы через месяц по дыре в статистике.
    """
    return {
        "targets": TARGETS,
        "reasons": [{"code": code, "label": label, "targets": list(targets)}
                    for code, (label, targets) in REASONS.items()],
        "min_comment": MIN_COMMENT,
    }


def reasons_for(target: str) -> list[str]:
    return [code for code, (_label, targets) in REASONS.items() if target in targets]


def _clean(value: object, limit: int) -> str:
    return _SPACES.sub(" ", str(value or "").strip())[:limit]


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _json_capped(value: object, limit: int) -> str:
    """Объект -> JSON-строка не длиннее лимита, ВСЕГДА разбираемая обратно.

    Обычная обрезка строки ломает JSON, и админка вместо контекста показала бы
    ошибку разбора — то есть потеряла бы ровно то, ради чего контекст и
    хранится. Переросшее кладём внутрь валидной обёртки с пометкой."""
    if not value:
        return ""
    try:
        s = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""
    if len(s) <= limit:
        return s
    return json.dumps({"_truncated": True, "text": s[:limit]}, ensure_ascii=False)


def normalize(body: dict) -> tuple[dict | None, str]:
    """Жалоба с фронта -> строка для базы. (данные, "") либо (None, "что не так").

    Проверяем ровно то, без чего запись бесполезна для калибровки:
      * известный тип задания и известный объект спора — иначе жалоба не
        кластеризуется и потеряется в общей куче;
      * причина из списка И ПРИМЕНИМАЯ к этому объекту: «ведёт себя не как
        характер» про балл за чтение означает, что форма собрана неверно;
      * объяснение словами. Единственное поле, которое не выводится из
        контекста, и единственное, ради которого стоит читать жалобу;
      * «что я сказал на самом деле» — обязательно, когда человек жалуется на
        распознавание: без этой строки претензию нечем проверить, а с ней она
        становится готовым замером ошибки распознавания;
      * улика (расшифровка) для всего, кроме отзыва о приложении: спор о
        разборе без разбираемого текста пересмотреть невозможно.

    Обстановку (`context`) не требуем, но кладём целиком: текст задания,
    соседние реплики беседы, снимок разбора. Требовать её от ученика нельзя —
    её собирает экран, — а вот без неё жалоба протухает за неделю.
    """
    kind = _clean(body.get("kind"), 16)
    if kind not in KINDS:
        return None, "Неизвестный тип задания."

    target = _clean(body.get("target"), 16)
    if target not in TARGETS:
        return None, "Непонятно, с чем именно несогласие."

    reason = _clean(body.get("reason"), 16)
    if reason not in REASONS:
        return None, "Выбери, что не так."
    if target not in REASONS[reason][1]:
        return None, "Эта причина не подходит к тому, что оспаривается."

    comment = _clean(body.get("comment"), _MAX_COMMENT)
    if len(comment) < MIN_COMMENT:
        return None, f"Напиши хотя бы {MIN_COMMENT} символов — что именно не так."

    said = _clean(body.get("said"), _MAX_SAID)
    if reason == "misheard" and len(said) < 2:
        return None, "Напиши, что ты сказал на самом деле."

    transcript = str(body.get("transcript") or "").strip()[:_MAX_TRANSCRIPT]
    if kind != "app" and not transcript:
        return None, "Пустая жалоба: нет расшифровки."

    # Балл «по мнению ученика»: -1 — «дело не в балле». Значение выше максимума
    # ничего не значит, поэтому подрезаем, а не отвергаем: спорят о разборе, а
    # не о попадании в диапазон.
    max_score = max(0, _int(body.get("max")))
    claim = _int(body.get("claim_score"), -1)
    claim = -1 if claim < 0 else min(claim, max_score if max_score else claim)

    return {
        "kind": kind,
        "variant": _clean(body.get("variant"), 64),
        "persona": _clean(body.get("persona"), 32),
        "target": target,
        "target_key": _clean(body.get("target_key"), 40),
        "target_label": _clean(body.get("target_label"), 120),
        "reason": reason,
        "comment": comment,
        "said": said,
        "score": max(0, _int(body.get("score"))),
        "max_score": max_score,
        "claim_score": claim,
        "transcript": transcript,
        "feedback": _json_capped(body.get("feedback"), _MAX_FEEDBACK),
        "context": _json_capped(body.get("context"), _MAX_CONTEXT),
    }, ""


def resolution(body: dict) -> tuple[dict | None, str]:
    """Вердикт владельца по жалобе — из админки. Тут строгость другая: поля
    заполняет человек, который знает, что делает, и ему важно уметь ответить
    «пока не знаю» (status=skip) без выдумывания балла."""
    status = _clean(body.get("status"), 8) or "done"
    if status not in STATUSES:
        return None, "Неизвестный статус."
    verdict = _clean(body.get("verdict"), 8)
    if verdict and verdict not in VERDICTS:
        return None, "Неизвестный вердикт."
    if status == "done" and not verdict:
        return None, "Разобранная жалоба обязана иметь вердикт."
    return {
        "status": status,
        "verdict": verdict,
        "verdict_score": max(-1, _int(body.get("verdict_score"), -1)),
        "verdict_note": _clean(body.get("verdict_note"), 500),
    }, ""
