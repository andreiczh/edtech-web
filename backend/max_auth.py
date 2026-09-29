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
import re
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


def parse_init_data(raw: str, plus_as_space: bool = False) -> dict[str, str]:
    """Пары key=value. По документации MAX значения снимаются decodeURIComponent:
    там «+» остаётся плюсом, а parse_qsl превратил бы его в пробел и сломал
    подпись. Поэтому по умолчанию — unquote; plus_as_space=True — прежний
    разбор, verify пробует оба (§6.51)."""
    s = extract_launch_params(raw)
    if plus_as_space:
        return dict(parse_qsl(s, keep_blank_values=True))
    out: dict[str, str] = {}
    for part in s.split("&"):
        if not part:
            continue
        k, _, v = part.partition("=")
        out[unquote(k)] = unquote(v)
    return out


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
    # compare_digest над str падает на не-ASCII → 500; подпись обязана быть hex.
    if not re.fullmatch(r"[0-9a-f]{64}", got):
        out["reason"] = "подпись не в hex"
        return out
    for variant in _VARIANTS:
        if hmac.compare_digest(sign(params, bot_token, variant), got):
            out["variant"] = variant
            break
    if out["variant"] is None:
        # Второй разбор: «+» как пробел (форменная кодировка). Если MAX когда-то
        # закодирует пробел плюсом, подпись сойдётся здесь.
        alt = parse_init_data(raw, plus_as_space=True)
        if alt != params:
            for variant in _VARIANTS:
                if hmac.compare_digest(sign(alt, bot_token, variant), got):
                    out["variant"] = variant
                    params = alt
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


# ------------------------------------------------------------ вход по ссылке от бота
#
# Пока адрес мини-приложения не привязан к боту в партнёрской платформе MAX,
# кнопка open_app не работает, и данных запуска (WebAppData) у приложения нет.
# Но бот и так знает, кто ему пишет: номер пользователя приходит в вебхуке, а
# вебхук подписан секретом из токена. Поэтому бот выдаёт ЛИЧНУЮ ссылку: номер
# пользователя, срок годности и подпись ключом, выведенным из токена бота. По
# ней приложение входит в тот же аккаунт, что и через /auth/max (account_id от
# того же номера и той же соли), — без регистрации (§6.50).
#
# Ссылка многоразовая в пределах срока: человек жмёт кнопку в чате не раз, а
# хранилище браузера внутри мессенджера может не переживать закрытие окна.
# Токен кладётся во фрагмент адреса (#mlogin=...): фрагмент не уходит на сервер
# и не попадает в журналы запросов.

LINK_TTL_S = 7 * 24 * 3600
_LINK_RE = re.compile(r"v1\.(\d{1,20})\.(\d{9,11})\.([0-9a-f]{32})")


def _link_sig(uid: str, exp: str, bot_token: str) -> str:
    key = hashlib.sha256(f"gospeak-login-link:{bot_token}".encode()).digest()
    return hmac.new(key, f"v1.{uid}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]


def link_token(max_user_id: str | int, bot_token: str, ttl_s: int = LINK_TTL_S,
               now: float | None = None) -> str:
    uid = str(int(max_user_id))
    exp = str(int((now if now is not None else time.time()) + ttl_s))
    return f"v1.{uid}.{exp}.{_link_sig(uid, exp, bot_token)}"


def verify_link(token: str, bot_token: str, now: float | None = None) -> dict:
    """{valid, user_id, reason}. Причины — по-русски, их видит человек."""
    out: dict = {"valid": False, "user_id": None, "reason": ""}
    m = _LINK_RE.fullmatch((token or "").strip())
    if not m:
        out["reason"] = "ссылка повреждена — открой её из чата с ботом"
        return out
    if not bot_token:
        out["reason"] = "токен бота не задан на сервере"
        return out
    uid, exp, sig = m.groups()
    if not hmac.compare_digest(sig.encode(), _link_sig(uid, exp, bot_token).encode()):
        out["reason"] = "ссылка выдана не нашим ботом"
        return out
    if int(exp) < (now if now is not None else time.time()):
        out["reason"] = "ссылка устарела — напиши боту любое сообщение, он пришлёт новую"
        return out
    out.update(valid=True, user_id=int(uid))
    return out
