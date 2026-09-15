# -*- coding: utf-8 -*-
"""Вход через MAX и страница-проба /max-check (15.09.2026).

Проверяется: подпись данных запуска (оба порядка HMAC, подделка, чужой
токен, срок, миллисекунды, фрагмент адреса), вывод id и ника, /auth/max
(создание, повторный вход, занятый ник, тормоз MAX_SIGNUP, пароль у такого
аккаунта не работает, в базе нет ни имени, ни MAX-id), ручки пробы (без
личных данных в ответе, формат записи по байтам, потолок размера,
выключатель) и подпись файла для распознавания по содержимому.

Запуск: .\.venv\Scripts\python.exe test_max_auth.py
Сети не требует, база во временном файле; LLM и распознавание не вызываются.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import os
import re
import sys
import tempfile
import time
import wave
from urllib.parse import quote, urlencode

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np  # noqa: E402

import audio_check  # noqa: E402
import max_auth  # noqa: E402
import storage  # noqa: E402

failed = 0


def check(cond: bool, name: str, detail: str = "") -> None:
    global failed
    if cond:
        print(f"OK   {name}")
    else:
        failed += 1
        print(f"FAIL {name}: {detail}")


TOKEN = "test-bot-token-123"
# id из девяти цифр: такой строки не бывает ни в хеше, ни в метке времени —
# проверка «в базе нет MAX-id» не может сработать случайно.
ANNA = {"id": 987654321, "first_name": "Аня", "last_name": "Тестова"}


def launch(user: dict | None = ANNA, token: str = TOKEN, variant: str = "A",
           auth_date: int | None = None) -> str:
    """Данные запуска так, как их отдал бы MAX: query-string с подписью."""
    params = {"auth_date": str(auth_date if auth_date is not None else int(time.time())),
              "query_id": "q-1"}
    if user is not None:
        params["user"] = json.dumps(user, ensure_ascii=False, separators=(",", ":"))
    params["hash"] = max_auth.sign(params, token, variant)
    return urlencode(params)


# ------------------------------------------------------------ подпись

r = max_auth.verify(launch(), TOKEN)
check(r["valid"] and r["variant"] == "A" and r["user"]["id"] == 987654321,
      "подпись: вариант A (ключ HMAC — литерал WebAppData)", str(r))
r = max_auth.verify(launch(variant="B"), TOKEN)
check(r["valid"] and r["variant"] == "B", "подпись: вариант B (ключ HMAC — токен)", str(r))
r = max_auth.verify(launch(token="чужой-токен"), TOKEN)
check(not r["valid"] and "не совпала" in r["reason"], "чужой токен не проходит", str(r))
r = max_auth.verify(launch().replace("987654321", "987654322"), TOKEN)
check(not r["valid"] and "не совпала" in r["reason"], "подменённый id не проходит", str(r))
r = max_auth.verify(launch(auth_date=int(time.time()) - 2 * 86400), TOKEN)
check(not r["valid"] and "устарели" in r["reason"], "старые данные запуска отвергаются", str(r))
now_ms = int(time.time() * 1000)
r = max_auth.verify(launch(auth_date=now_ms), TOKEN)
check(r["valid"] and abs(r["auth_date"] - now_ms // 1000) <= 1,
      "auth_date в миллисекундах понимается", str(r))
frag = "#WebAppData=" + quote(launch(), safe="") + "&WebAppPlatform=ios&WebAppVersion=25.9.0"
r = max_auth.verify(frag, TOKEN)
check(r["valid"], "данные из фрагмента адреса (#WebAppData=...)", str(r))
r = max_auth.verify("auth_date=1&user=%7B%7D", TOKEN)
check(not r["valid"] and "нет подписи" in r["reason"], "без hash — отказ", str(r))
r = max_auth.verify(launch(), "")
check(not r["valid"] and "токен" in r["reason"], "без токена на сервере — отказ", str(r))
r = max_auth.verify("", TOKEN)
check(not r["valid"] and "нет" in r["reason"], "пустые данные — отказ", str(r))
r = max_auth.verify(launch(user={"first_name": "Без id"}), TOKEN)
check(not r["valid"] and "пользователя" in r["reason"], "пользователь без id — отказ", str(r))
r = max_auth.verify(launch(user=None), TOKEN)
check(not r["valid"] and "пользователя" in r["reason"], "без пользователя — отказ", str(r))

# ------------------------------------------------------------ перебор для пробы

params = {"auth_date": str(int(time.time())),
          "user": json.dumps(ANNA, ensure_ascii=False)}
check_str = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
params["hash"] = hmac.new(hashlib.sha256(TOKEN.encode()).digest(), check_str.encode(),
                          hashlib.sha256).hexdigest()
raw_c = urlencode(params)
check(not max_auth.verify(raw_c, TOKEN)["valid"],
      "подпись «секрет = SHA-256 токена» основным путём не проходит")
check("C/decoded/sorted/nl" in max_auth.diagnose(raw_c, TOKEN),
      "перебор находит вариант C", str(max_auth.diagnose(raw_c, TOKEN)))
check("B/decoded/sorted/nl" in max_auth.diagnose(launch(variant="B"), TOKEN),
      "перебор находит вариант B")
check(max_auth.diagnose(launch(), "") == [], "перебор без токена пуст")

# ------------------------------------------------------------ id и ник

a1 = max_auth.account_id(987654321, "s1")
check(a1 == max_auth.account_id("987654321", "s1") and a1.startswith("max_") and len(a1) == 36,
      "id аккаунта стабилен и одного вида", a1)
check(a1 != max_auth.account_id(987654321, "s2"), "id зависит от соли")
check(a1 != max_auth.account_id(987654322, "s1"), "id зависит от пользователя")
n1 = max_auth.nickname(987654321, "s1")
check(re.fullmatch(r"[A-Za-z]{15,32}", n1) is not None and n1 == max_auth.nickname(987654321, "s1"),
      "запасной ник: только буквы и стабилен", n1)
check(n1 != max_auth.nickname(987654322, "s1"), "запасной ник у разных людей разный")

# ------------------------------------------------------------ формат по байтам

for head, want in (
    (b"\x00\x00\x00\x1cftypiso5\x00\x00", "mp4"),
    (b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81", "webm"),
    (b"OggS\x00\x02\x00\x00", "ogg"),
    (b"RIFF\x24\x00\x00\x00WAVEfmt ", "wav"),
    (b"ID3\x04\x00\x00\x00\x00", "mp3"),
    (b"\xff\xfb\x90\x64\x00", "mp3"),
    (b"\xff\xf1\x50\x80\x02", "aac"),
    (b"fLaC\x00\x00\x00\x22", "flac"),
    (b"hello world!", "unknown"),
    (b"", "unknown"),
):
    got = audio_check.sniff(head)
    check(got == want, f"sniff {head[:4]!r} -> {want}", got)

# ------------------------------------------------------------ сервер

tmp = os.path.join(tempfile.gettempdir(), "max_auth_suite.db")
if os.path.exists(tmp):
    os.remove(tmp)
storage._SQLITE_PATH = tmp
storage._conn = None
storage.ensure_schema()

import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from starlette.datastructures import Headers, UploadFile  # noqa: E402
from starlette.requests import Request  # noqa: E402

main._storage_ok = True
os.environ["MAX_BOT_TOKEN"] = TOKEN
for k in ("MAX_SIGNUP", "MAX_PROBE", "MAX_ID_SALT"):
    os.environ.pop(k, None)

_ip = [0]


def req() -> Request:
    # Каждый вызов — с нового адреса: рейт-лимиты здесь не предмет теста.
    _ip[0] += 1
    ip = f"10.9.{_ip[0] // 250}.{_ip[0] % 250}"
    return Request({"type": "http", "method": "POST", "path": "/", "query_string": b"",
                    "headers": [(b"x-forwarded-for", ip.encode())], "client": (ip, 5000)})


def call(coro):
    try:
        return asyncio.run(coro), None
    except HTTPException as e:
        return None, e


def why(res, err) -> str:
    return str(res) if err is None else f"{err.status_code}: {err.detail}"


# ------------------------------------------------------------ /auth/max

res, err = call(main.auth_max(req(), {"init_data": launch(),
                                      "nicknames": ["ShortNick", "BraveNightingale", "bad nick", 42]}))
check(err is None and res["created"] is True and res["nickname"] == "BraveNightingale"
      and res["id"].startswith("max_"),
      "первый вход создаёт аккаунт с предложенным ником", why(res, err))
acc = res["id"] if res else ""
check(storage.account_exists(acc), "аккаунт виден шлюзу API (account_exists)")

res, err = call(main.auth_max(req(), {"init_data": launch(), "nicknames": ["CalmHummingbird"]}))
check(err is None and res["created"] is False and res["id"] == acc
      and res["nickname"] == "BraveNightingale",
      "повторный вход — тот же аккаунт и тот же ник", why(res, err))

bob = {"id": 777001, "first_name": "Боб"}
res, err = call(main.auth_max(req(), {"init_data": launch(user=bob), "nicknames": ["BraveNightingale"]}))
check(err is None and res["created"] and res["id"] != acc
      and res["nickname"] == max_auth.nickname(777001, main._max_salt()),
      "занятый ник — берётся запасной из хеша", why(res, err))

res, err = call(main.auth_max(req(), {"init_data": launch(token="чужой")}))
check(err is not None and err.status_code == 401, "поддельная подпись — 401", why(res, err))

res, err = call(main.auth_max(req(), {"init_data": ""}))
check(err is not None and err.status_code == 422, "без данных запуска — 422", why(res, err))

os.environ["MAX_SIGNUP"] = "0"
res, err = call(main.auth_max(req(), {"init_data": launch(user={"id": 555000111})}))
check(err is not None and err.status_code == 403, "MAX_SIGNUP=0: новый аккаунт не создаётся",
      why(res, err))
res, err = call(main.auth_max(req(), {"init_data": launch()}))
check(err is None and res["id"] == acc, "MAX_SIGNUP=0: существующий входит", why(res, err))
os.environ.pop("MAX_SIGNUP")

saved = os.environ.pop("MAX_BOT_TOKEN")
res, err = call(main.auth_max(req(), {"init_data": launch()}))
check(err is not None and err.status_code == 503, "без токена на сервере — 503", why(res, err))
os.environ["MAX_BOT_TOKEN"] = saved

res, err = call(main.auth_login(req(), {"nickname": "BraveNightingale", "password": "max"}))
check(err is not None and err.status_code == 401,
      "пароля у MAX-аккаунта нет: по нику он не открывается", why(res, err))

row = storage._exec("SELECT * FROM accounts WHERE id=?", (acc,)).fetchone()
dump = json.dumps([str(x) for x in row], ensure_ascii=False)
check("987654321" not in dump and "Аня" not in dump and "Тестова" not in dump,
      "в базе нет ни MAX-id, ни имени", dump)

# ------------------------------------------------------------ проба: подпись

res, err = call(main.max_probe_initdata(req(), {"init_data": launch()}))
check(err is None and res["token_set"] and res["valid"] and res["variant"] == "A"
      and "user" in res["keys"], "проба: подпись сходится", why(res, err))
dump = json.dumps(res, ensure_ascii=False)
check("987654321" not in dump and "Аня" not in dump, "проба: в ответе нет ни id, ни имени", dump)
res, err = call(main.max_probe_initdata(req(), {"init_data": raw_c}))
check(err is None and not res["valid"] and "C/decoded/sorted/nl" in res["diagnose"],
      "проба: несошедшаяся подпись приходит с перебором", why(res, err))

# ------------------------------------------------------------ проба: запись


def wav_bytes(samples: np.ndarray, sr: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(samples.astype("<i2").tobytes())
    return buf.getvalue()


def upload(data: bytes, name: str, ctype: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name,
                      headers=Headers({"content-type": ctype}))


t = np.arange(32000) / 16000
tone = wav_bytes(0.3 * np.sin(2 * np.pi * 220 * t) * 32767)
res, err = call(main.max_probe_audio(req(), upload(tone, "probe.webm", "audio/webm"), "0"))
check(err is None and res["detected"] == "wav" and res["decoded"]
      and abs(res["duration_s"] - 2.0) < 0.1 and res["silence"] is None and "text" not in res,
      "проба: формат по байтам, а не по подписи; без stt распознавания нет", why(res, err))

silent = wav_bytes(np.zeros(48000))
res, err = call(main.max_probe_audio(req(), upload(silent, "probe.wav", "audio/wav"), "1"))
check(err is None and res["decoded"] and res["silence"] and "text" not in res,
      "проба: тишину распознаванию не отдаём", why(res, err))

res, err = call(main.max_probe_audio(req(), upload(b"not audio at all " * 50, "x.webm",
                                                   "audio/webm"), "0"))
check(err is None and res["detected"] == "unknown" and not res["decoded"],
      "проба: мусор честно называется нечитаемым", why(res, err))

res, err = call(main.max_probe_audio(req(), upload(b"\0" * (2 * 1024 * 1024 + 10), "big.webm",
                                                   "audio/webm"), "0"))
check(err is not None and err.status_code == 413, "проба: больше 2 МБ — 413", why(res, err))

page = main.max_check_page()
check(str(getattr(page, "path", "")).endswith("max-check.html"), "страница /max-check отдаётся",
      str(getattr(page, "path", None)))

os.environ["MAX_PROBE"] = "0"
res, err = call(main.max_probe_initdata(req(), {"init_data": launch()}))
check(err is not None and err.status_code == 404, "MAX_PROBE=0 выключает ручки пробы",
      why(res, err))
try:
    main.max_check_page()
    off = False
except HTTPException as e:
    off = e.status_code == 404
check(off, "MAX_PROBE=0 выключает страницу")
os.environ.pop("MAX_PROBE")

# ------------------------------------------------------------ подпись файла для STT

for head, want in (
    (b"\x00\x00\x00\x1cftypM4A \x00\x00", ("speech.m4a", "audio/mp4")),
    (b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81", ("speech.webm", "audio/webm")),
    (b"OggS\x00\x02\x00\x00", ("speech.ogg", "audio/ogg")),
    (b"garbage-bytes", ("speech.webm", "audio/webm")),
):
    got = main._stt_upload_name(head)
    check(got == want, f"распознаванию уходит {want[0]}", str(got))

# ------------------------------------------------------------ правило ника

check(main._nick_ok("CheerfulHummingbird") and not main._nick_ok("BraveFalcon")
      and not main._nick_ok("Cheerful Hummingbird") and not main._nick_ok("Cheerful4Hummingbird"),
      "правило ника: от 15 букв, только латиница, без пробелов и цифр")
front = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "auth",
                          "nickname.ts"), encoding="utf-8").read()
m = re.search(r"export const NICK_MIN = (\d+)", front)
check(m is not None and int(m.group(1)) == main.NICK_MIN,
      "минимальная длина ника на фронте и на сервере одна",
      m.group(0) if m else "NICK_MIN во фронте не найден")

print()
print("ВСЁ ЗЕЛЁНОЕ" if not failed else f"ПРОВАЛОВ: {failed}")
sys.exit(1 if failed else 0)
