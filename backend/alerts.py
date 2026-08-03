"""Алерты владельцу в Telegram.

Вынесено из main.py 03.08.2026 вторым блоком после personas. Критерий тот же:
никаких обратных зависимостей на состояние main — только окружение, httpx и
поток.

До этого о падении прода владелец узнавал от друзей. Схема минимальная: бот
BotFather + chat_id в переменных Render, шлём только СОБЫТИЯ-ПЕРЕХОДЫ (упал,
кончился бюджет, пачка сбоев), а не поток логов. Без переменных модуль молчит
и ничего не стоит.

Снаружи прод сторожит внешний пингер по /health (docs/MONITORING.md): умерший
процесс сам о себе не сообщит, поэтому пингер обязан быть внешним.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque

import httpx

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
_ALERT_COOLDOWN = 1800.0  # одна тема — не чаще раза в полчаса, иначе шторм
_alert_last: dict[str, float] = {}
_fail_win: dict[str, deque] = {}  # скользящее окно сбоев по узлам


def notify_owner(topic: str, text: str) -> None:
    """Fire-and-forget: никогда не бросает и не задерживает запрос ученика.

    Отдельный поток, а не await: зовётся и из sync-кода, и из горячего пути,
    где +10 секунд таймаута телеграма были бы хуже пропущенного алерта."""
    if not (TG_TOKEN and TG_CHAT):
        return
    now = time.monotonic()
    if now - _alert_last.get(topic, -1e9) < _ALERT_COOLDOWN:
        return
    _alert_last[topic] = now

    def _send() -> None:
        try:
            httpx.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": f"[Pingo] {text}"[:3900]},
                timeout=10.0,
            )
        except Exception as e:  # noqa: BLE001 — алерт не важнее работы сервиса
            print(f"[alert] телеграм не доставлен ({type(e).__name__})")

    threading.Thread(target=_send, daemon=True).start()


def note_failure(node: str, detail: str = "") -> None:
    """Счётчик сбоев узла (stt/llm/tts): 5 за 10 минут = алерт владельцу.
    Единичные обрывы на нестабильном канале — норма, алертит только серия."""
    win = _fail_win.setdefault(node, deque())
    now = time.monotonic()
    win.append(now)
    while win and now - win[0] > 600.0:
        win.popleft()
    if len(win) >= 5:
        notify_owner(f"fail:{node}",
                     f"{node.upper()}: {len(win)} сбоев за 10 минут. "
                     f"Последний: {detail[:120]}")


def send_now(text: str) -> tuple[bool, str]:
    """Синхронная отправка БЕЗ кулдауна — для ручной проверки канала из
    админки. Возвращает (успех, детали): владельцу нужна причина отказа,
    иначе «не пришло» неотличимо от «неверный chat_id»."""
    if not (TG_TOKEN and TG_CHAT):
        return False, "не заданы TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID"
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": f"[Pingo] {text}"[:3900]},
            timeout=15.0,
        )
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}"
    if r.status_code != 200:
        # Тело телеграма содержит внятную причину («chat not found»),
        # но не токен — показать владельцу можно.
        return False, f"HTTP {r.status_code}: {r.text[:160]}"
    return True, "ok"


def discover_chat_id() -> tuple[bool, str]:
    """Найти chat_id по сообщениям, написанным боту.

    Самый муторный шаг настройки: владельцу иначе пришлось бы вручную собирать
    ссылку getUpdates и выковыривать число из сырого JSON. Токен при этом никуда
    не уходит — запрос делает сервер своим собственным, уже настроенным токеном.
    """
    if not TG_TOKEN:
        return False, "сначала задай TELEGRAM_BOT_TOKEN в переменных Render"
    try:
        r = httpx.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates", timeout=15.0)
    except Exception as e:  # noqa: BLE001
        return False, f"телеграм недоступен ({type(e).__name__})"
    if r.status_code != 200:
        # Тело телеграма объясняет причину («Unauthorized» = неверный токен),
        # но самого токена не содержит — показать владельцу можно.
        return False, f"телеграм ответил {r.status_code}: {r.text[:160]}"
    found: dict[str, str] = {}
    for upd in (r.json().get("result") or []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        if cid is not None:
            who = chat.get("username") or chat.get("title") or chat.get("first_name") or "?"
            found[str(cid)] = str(who)
    if not found:
        return False, ("сообщений боту нет. Напиши ему что-нибудь в Telegram "
                       "и нажми ещё раз (бот не может написать первым)")
    return True, "; ".join(f"{cid} — {who}" for cid, who in found.items())
