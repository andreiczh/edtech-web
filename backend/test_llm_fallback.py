# -*- coding: utf-8 -*-
"""Запасная модель LLM (22.09.2026): когда основная отвечает 429 с нулевым
лимитом запросов, обёртка клиента повторяет запрос запасной моделью, держит
подмену десять минут и показывает это в /health. Обычные ошибки и обычные
429 (лимит есть, запросы кончились) наружу летят как раньше.

Запуск: .\\.venv\\Scripts\\python.exe test_llm_fallback.py
Сети не требует: клиент SDK подменяется заглушкой.
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.environ["LLM_FALLBACK_MODEL"] = "fallback-model"
import main  # noqa: E402

failed = 0


def check(cond: bool, name: str, detail: str = "") -> None:
    global failed
    if cond:
        print(f"OK   {name}")
    else:
        failed += 1
        print(f"FAIL {name}: {detail}")


class _Resp:
    def __init__(self, headers):
        self.headers = headers


class RateLimit(Exception):
    def __init__(self, limit: str):
        super().__init__("Error code: 429 - Rate limit exceeded")
        self.status_code = 429
        self.response = _Resp({"x-ratelimit-limit-req-minute": limit})


class Inner:
    """Заглушка client.chat.completions: основная модель отвечает так, как скажут."""

    def __init__(self):
        self.calls: list[str] = []
        self.primary_error: Exception | None = None

    def create(self, **kw):
        self.calls.append(kw["model"])
        if kw["model"] == main.LLM_MODEL and self.primary_error:
            raise self.primary_error
        return f"ok:{kw['model']}"


class AsyncInner(Inner):
    async def create(self, **kw):  # type: ignore[override]
        return Inner.create(self, **kw)


def reset():
    main._llm_fallback_until = 0.0
    main._llm_fallback_count = 0
    main._llm_fallback_reason = ""


# ------------------------------------------------------------ синхронный
reset()
inner = Inner()
c = main._Completions(inner)
check(c.create(model=main.LLM_MODEL, messages=[]) == f"ok:{main.LLM_MODEL}" and inner.calls == [main.LLM_MODEL],
      "основная модель отвечает — запасная не трогается")

inner.calls.clear()
inner.primary_error = RateLimit("50")
try:
    c.create(model=main.LLM_MODEL, messages=[])
    check(False, "обычный 429 (лимит есть) летит наружу")
except RateLimit:
    check(inner.calls == [main.LLM_MODEL] and main._llm_fallback_count == 0,
          "обычный 429 (лимит есть) летит наружу, подмены нет", str(inner.calls))

inner.calls.clear()
inner.primary_error = ValueError("boom")
try:
    c.create(model=main.LLM_MODEL, messages=[])
    check(False, "чужая ошибка летит наружу")
except ValueError:
    check(main._llm_fallback_count == 0, "чужая ошибка летит наружу без подмены")

inner.calls.clear()
inner.primary_error = RateLimit("0")
out = c.create(model=main.LLM_MODEL, messages=[])
check(out == "ok:fallback-model" and inner.calls == [main.LLM_MODEL, "fallback-model"],
      "429 с лимитом 0 → повтор запасной моделью", str(inner.calls))
check(main._llm_fallback_count == 1 and main._llm_fallback_until > time.time()
      and "429" in main._llm_fallback_reason, "подмена отмечена: счётчик, срок, причина")

inner.calls.clear()
out = c.create(model=main.LLM_MODEL, messages=[])
check(out == "ok:fallback-model" and inner.calls == ["fallback-model"],
      "пока держится подмена — сразу запасная, без лишнего 429", str(inner.calls))

inner.calls.clear()
out = c.create(model="pixtral-vision", messages=[])
check(out == "ok:pixtral-vision" and inner.calls == ["pixtral-vision"],
      "другую модель (зрение) подмена не касается")

main._llm_fallback_until = 0.0
inner.calls.clear()
inner.primary_error = None
out = c.create(model=main.LLM_MODEL, messages=[])
check(out == f"ok:{main.LLM_MODEL}" and inner.calls == [main.LLM_MODEL],
      "срок вышел, основная ожила — снова основная")

# ------------------------------------------------------------ асинхронный
reset()
ainner = AsyncInner()
ainner.primary_error = RateLimit("0")
ac = main._AsyncCompletions(ainner)
out = asyncio.run(ac.create(model=main.LLM_MODEL, messages=[]))
check(out == "ok:fallback-model" and ainner.calls == [main.LLM_MODEL, "fallback-model"],
      "стриминговый клиент: та же подмена", str(ainner.calls))

# ------------------------------------------------------------ выключатель
reset()
saved = main.LLM_FALLBACK_MODEL
main.LLM_FALLBACK_MODEL = ""
inner = Inner()
inner.primary_error = RateLimit("0")
try:
    main._Completions(inner).create(model=main.LLM_MODEL, messages=[])
    check(False, "пустой LLM_FALLBACK_MODEL выключает подмену")
except RateLimit:
    check(inner.calls == [main.LLM_MODEL], "пустой LLM_FALLBACK_MODEL выключает подмену")
main.LLM_FALLBACK_MODEL = saved

# ------------------------------------------------------------ /health
reset()
h = main.health()
check(isinstance(h.get("llm_fallback"), dict) and h["llm_fallback"]["count"] == 0
      and h["llm_fallback"]["active"] is False and h["llm_fallback"]["model"] == "fallback-model",
      "/health показывает состояние подмены", str(h.get("llm_fallback")))

# ------------------------------------------------------------ обёртка клиента
class FakeSdk:
    class chat:  # noqa: N801
        completions = Inner()


proxy = main._LlmProxy(FakeSdk(), is_async=False)
check(proxy.chat.completions.create(model="x", messages=[]) == "ok:x",
      "обёртка отдаёт chat.completions.create как SDK")

print()
print("ВСЁ ЗЕЛЁНОЕ" if not failed else f"ПРОВАЛОВ: {failed}")
sys.exit(1 if failed else 0)
