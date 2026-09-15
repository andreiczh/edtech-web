"""Вход через MAX: разбор и проверка подписи данных запуска мини-приложения.

MAX передаёт мини-приложению строку initData (в документации — WebAppData):
параметры запуска в формате query-string, подписанные токеном бота. Верить id
пользователя можно только после того, как сервер сам пересчитал подпись.

Алгоритм (dev.max.ru/docs/webapps/validation): из параметров убирается hash,
остальные сортируются по ключу и склеиваются строками «ключ=значение» через
перевод строки; secret_key = HMAC_SHA256('WebAppData', токен бота), подпись =
HMAC_SHA256(secret_key, эта строка) в hex. Какой из двух аргументов первого
шага — ключ HMAC, документация говорит двусмысленно, поэтому проверяются оба
порядка и наружу отдаётся, какой совпал. Страница-проба /max-check показывает
это на настоящих данных; лишний вариант после этого убираем.

Модуль без ввода-вывода: только разбор и криптография.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, unquote

# Сутки: данные запуска выдаются при открытии мини-приложения, а человек может
# держать его открытым долго. Старше — просим открыть заново.
MAX_AGE_S = 24 * 3600

_VARIANTS = ("A", "B")


def extract_launch_params(raw: str) -> str:
    """Строка initData как есть — или вынутая из фрагмента адреса (#WebAppData=...)."""
    s = (raw or "").strip()
    if s.startswith("#"):
        s = s[1:]
    if "WebAppData=" in s:
        for part in s.split("&"):
            if part.startswith("WebAppData="):
                return unquote(part[len("WebAppData="):])
    return s


def parse_init_data(raw: str) -> dict[str, str]:
    return dict(parse_qsl(extract_launch_params(raw), keep_blank_values=True))


def _check_string(params: dict[str, str]) -> str:
    return "\n".join(f"{k}={v}" for k, v in sorted(params.items()) if k != "hash")


def _secret(bot_token: str, variant: str) -> bytes:
    if variant == "A":  # как в Telegram: ключ HMAC — литерал WebAppData
        return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(bot_token.encode(), b"WebAppData", hashlib.sha256).digest()


def sign(params: dict[str, str], bot_token: str, variant: str = "A") -> str:
    """Подпись набора параметров — нужна тестам и пробе."""
    return hmac.new(_secret(bot_token, variant), _check_string(params).encode(),
                    hashlib.sha256).hexdigest()


def verify(raw: str, bot_token: str, max_age_s: int = MAX_AGE_S,
           now: float | None = None) -> dict:
    """Проверить данные запуска. Возвращает словарь, а не бросает исключения:
    вызывающему (эндпоинту и пробе) нужна причина отказа человеческими словами."""
    params = parse_init_data(raw)
    out: dict = {
        "valid": False,
        "variant": None,
        "reason": "",
        "user": None,
        "auth_date": None,
        "age_s": None,
        "start_param": params.get("start_param") or None,
        "keys": sorted(k for k in params if k != "hash"),
    }
    got = (params.get("hash") or "").strip().lower()
    if not params:
        out["reason"] = "данных запуска нет"
        return out
    if not got:
        out["reason"] = "в данных запуска нет подписи"
        return out
    if not bot_token:
        out["reason"] = "токен бота не задан на сервере"
        return out
    for variant in _VARIANTS:
        if hmac.compare_digest(sign(params, bot_token, variant), got):
            out["variant"] = variant
            break
    if out["variant"] is None:
        out["reason"] = "подпись не совпала"
        return out

    try:
        auth_date = int(float(params.get("auth_date") or ""))
    except ValueError:
        out["reason"] = "в данных нет времени выдачи"
        return out
    if auth_date > 10**11:  # пришло в миллисекундах
        auth_date //= 1000
    out["auth_date"] = auth_date
    age = int((now if now is not None else time.time()) - auth_date)
    out["age_s"] = age
    if age > max_age_s:
        out["reason"] = "данные запуска устарели — открой мини-приложение заново"
        return out

    try:
        user = json.loads(params.get("user") or "null")
    except ValueError:
        user = None
    if not isinstance(user, dict) or not user.get("id"):
        out["reason"] = "в данных нет пользователя"
        return out
    out["user"] = user
    out["valid"] = True
    return out


def diagnose(raw: str, bot_token: str) -> list[str]:
    """Какие способы подписи сходятся с присланной — только для пробы.

    Если verify не сошёлся на настоящих данных MAX, перебор сразу покажет, в
    чём расхождение: порядок аргументов HMAC (A/B), секрет как SHA-256 токена
    (C) или сам токен (D), кодированные значения, порядок параметров,
    разделитель. Тридцать две HMAC — ничто по времени, зато одна проба с
    телефона отвечает на вопрос, на который иначе ушла бы переписка.
    """
    s = extract_launch_params(raw)
    decoded = parse_qsl(s, keep_blank_values=True)
    got = (dict(decoded).get("hash") or "").strip().lower()
    if not (bot_token and got):
        return []
    raw_pairs = [(p.split("=", 1) + [""])[:2] for p in s.split("&") if p]
    keys = {
        "A": _secret(bot_token, "A"),
        "B": _secret(bot_token, "B"),
        "C": hashlib.sha256(bot_token.encode()).digest(),
        "D": bot_token.encode(),
    }
    found: list[str] = []
    for values, pairs in (("decoded", decoded), ("raw", raw_pairs)):
        items = [(k, v) for k, v in pairs if k != "hash"]
        for order, seq in (("sorted", sorted(items)), ("as_is", items)):
            for sep_name, sep in (("nl", "\n"), ("amp", "&")):
                check = sep.join(f"{k}={v}" for k, v in seq).encode()
                for name, key in keys.items():
                    sig = hmac.new(key, check, hashlib.sha256).hexdigest()
                    if hmac.compare_digest(sig, got):
                        found.append(f"{name}/{values}/{order}/{sep_name}")
    return found


def account_id(max_user_id: str | int, salt: str) -> str:
    """Id аккаунта из MAX-id. Хешем, а не самим id: в базе не лежит ничего,
    по чему человека можно найти в MAX без знания соли."""
    digest = hashlib.sha256(f"{salt}:{max_user_id}".encode()).hexdigest()
    return f"max_{digest[:32]}"


def nickname(max_user_id: str | int, salt: str) -> str:
    """Запасной ник — если все предложенные фронтом заняты. Только латинские
    буквы и 16 знаков (правило main.NICK_MIN: ник длиннее любого приветствия),
    стабильный для одного человека — повторный вход не ловит коллизий."""
    digest = hashlib.sha256(f"nick:{salt}:{max_user_id}".encode()).digest()
    return "Max" + "".join(chr(ord("a") + b % 26) for b in digest[:13])
