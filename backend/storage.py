"""Память продукта: ошибки учеников, результаты сессий и готовые выжимки.

Что храним — РОВНО ключевую информацию для профиля ученика (решение владельца
от 23.07.2026): категории ошибок, пары «как сказал → как надо», баллы сессий.
Полные транскрипты речи НЕ храним: ученики несовершеннолетние, записи речи —
отдельное согласие, которого нет.

Два бэкенда за одним API:
  - без DATABASE_URL  → SQLite-файл рядом (backend/pingo.db). Работает сразу,
    но на Render диск эфемерный — база живёт до ближайшего деплоя;
  - DATABASE_URL=postgres://…  → Postgres (Neon free). Постоянное хранилище,
    включается одной переменной окружения, код тот же.

Скорость: весь модуль синхронный и зовётся из main.py через asyncio.to_thread.
В горячем пути запроса живёт ровно ОДНА функция — get_digests (один SELECT по
первичному ключу). Всё остальное (записи, пересборка выжимок) — фоновое.

Выжимки строятся ДЕТЕРМИНИРОВАННО из SQL, без вызовов LLM: на этом объёме
подсчёт категорий с примерами информативнее и надёжнее генеративного пересказа,
стоит миллисекунды и не может ни соврать, ни упасть по квоте.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
_IS_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))

if _IS_PG:
    import psycopg  # ставится из requirements, но нужен только с Postgres

# Одно соединение под замком: трафик пилота крошечный, пул — лишняя сущность.
_lock = threading.Lock()
_conn = None

_SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pingo.db")

# Сколько последних ошибок ученика участвует в выжимке и как часто пересобирать
# общую по типу задания.
_USER_DIGEST_WINDOW = 60
_GLOBAL_DIGEST_TTL = timedelta(hours=1)
_TRUNC = 200  # обрезка текстовых полей: выжимке длиннее не нужно


def describe() -> str:
    return "postgres (Neon)" if _IS_PG else f"sqlite ({os.path.basename(_SQLITE_PATH)})"


def _connect():
    global _conn
    if _IS_PG:
        _conn = psycopg.connect(DATABASE_URL, autocommit=True)
    else:
        _conn = sqlite3.connect(_SQLITE_PATH, check_same_thread=False)
        # WAL: читатели не блокируют писателя — важно, ведь чтение выжимки
        # сидит в горячем пути ответа.
        _conn.execute("PRAGMA journal_mode=WAL")


def _exec(sql: str, params: tuple = ()):  # noqa: ANN202
    """Выполнить запрос, пережив обрыв соединения одной попыткой реконнекта.

    Плейсхолдеры пишем в стиле sqlite («?»), для Postgres меняем на «%s» —
    литералов с вопросительным знаком в наших запросах нет.
    """
    global _conn
    q = sql.replace("?", "%s") if _IS_PG else sql
    with _lock:
        for attempt in (1, 2):
            try:
                if _conn is None:
                    _connect()
                cur = _conn.execute(q, params)
                if not _IS_PG:
                    _conn.commit()
                return cur
            except Exception:
                _conn = None
                if attempt == 2:
                    raise


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_schema() -> None:
    # Типы нарочно самые скучные (TEXT/INTEGER): одна и та же DDL проходит и в
    # SQLite, и в Postgres. Ключи строк — uuid-текст: автоинкремент у движков
    # разный, а нам он ничего не даёт.
    for ddl in (
        "CREATE TABLE IF NOT EXISTS students ("
        " id TEXT PRIMARY KEY, created_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS results ("
        " id TEXT PRIMARY KEY, student_id TEXT NOT NULL, kind TEXT NOT NULL,"
        " variant TEXT, score INTEGER, max_score INTEGER, duration_sec INTEGER,"
        " created_at TEXT NOT NULL)",
        "CREATE INDEX IF NOT EXISTS idx_results_student ON results(student_id, created_at)",
        "CREATE TABLE IF NOT EXISTS mistakes ("
        " id TEXT PRIMARY KEY, student_id TEXT NOT NULL, kind TEXT NOT NULL,"
        " cat TEXT, quote TEXT, correction TEXT, explanation TEXT,"
        " created_at TEXT NOT NULL)",
        "CREATE INDEX IF NOT EXISTS idx_mistakes_student ON mistakes(student_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_mistakes_kind ON mistakes(kind)",
        "CREATE TABLE IF NOT EXISTS digests ("
        " scope TEXT PRIMARY KEY, text TEXT NOT NULL, updated_at TEXT NOT NULL)",
    ):
        _exec(ddl)


# ------------------------------------------------------------------ Чтение

def get_digests(student_id: str | None, kind: str | None) -> dict:
    """Единственная функция горячего пути: один SELECT по первичным ключам."""
    scopes = []
    if student_id:
        scopes.append(f"user:{student_id}")
    if kind:
        scopes.append(f"global:{kind}")
    if not scopes:
        return {}
    marks = ",".join("?" for _ in scopes)
    rows = _exec(f"SELECT scope, text FROM digests WHERE scope IN ({marks})",
                 tuple(scopes)).fetchall()
    out: dict = {}
    for scope, text in rows:
        out["user" if scope.startswith("user:") else "global"] = text
    return out


# ------------------------------------------------------------------ Запись

def save_result(student_id: str, kind: str, variant: str, score: int,
                max_score: int, duration_sec: int, errors: list) -> None:
    """Сохранить итог одного ответа и обновить выжимки. Зовётся фоном."""
    now = _now()
    if _IS_PG:
        _exec("INSERT INTO students(id, created_at) VALUES(?, ?) ON CONFLICT (id) DO NOTHING",
              (student_id, now))
    else:
        _exec("INSERT OR IGNORE INTO students(id, created_at) VALUES(?, ?)",
              (student_id, now))
    _exec("INSERT INTO results(id, student_id, kind, variant, score, max_score,"
          " duration_sec, created_at) VALUES(?,?,?,?,?,?,?,?)",
          (str(uuid.uuid4()), student_id, kind, variant[:64], int(score),
           int(max_score), int(duration_sec), now))

    for e in (errors or [])[:10]:
        if not isinstance(e, dict):
            continue
        _exec("INSERT INTO mistakes(id, student_id, kind, cat, quote, correction,"
              " explanation, created_at) VALUES(?,?,?,?,?,?,?,?)",
              (str(uuid.uuid4()), student_id, kind,
               str(e.get("cat") or kind)[:32],
               str(e.get("quote") or "")[:_TRUNC],
               str(e.get("correction") or "")[:_TRUNC],
               str(e.get("explanation") or "")[:_TRUNC], now))

    _rebuild_user_digest(student_id)
    _maybe_rebuild_global_digest(kind)


def _upsert_digest(scope: str, text: str) -> None:
    # Синтаксис ON CONFLICT одинаков в SQLite 3.24+ и Postgres.
    _exec("INSERT INTO digests(scope, text, updated_at) VALUES(?,?,?)"
          " ON CONFLICT (scope) DO UPDATE SET text=excluded.text,"
          " updated_at=excluded.updated_at",
          (scope, text, _now()))


# ------------------------------------------------------------------ Выжимки

def _rebuild_user_digest(student_id: str) -> None:
    rows = _exec(
        "SELECT cat, quote, correction FROM mistakes WHERE student_id=?"
        " ORDER BY created_at DESC LIMIT ?",
        (student_id, _USER_DIGEST_WINDOW)).fetchall()

    parts: list[str] = []
    if rows:
        by_cat: dict[str, list] = {}
        for cat, quote, corr in rows:
            by_cat.setdefault(cat or "other", []).append((quote, corr))
        chunks = []
        for cat, items in sorted(by_cat.items(), key=lambda kv: -len(kv[1]))[:5]:
            q, c = items[0]
            example = f", e.g. \"{q}\" -> \"{c}\"" if q and c else ""
            chunks.append(f"{cat} ({len(items)}x){example}")
        parts.append("Recurring mistakes: " + "; ".join(chunks) + ".")

    scores = _exec(
        "SELECT kind, score, max_score FROM results WHERE student_id=?"
        " ORDER BY created_at DESC LIMIT 5", (student_id,)).fetchall()
    if scores:
        parts.append("Recent scores: " +
                     ", ".join(f"{k} {s}/{m}" for k, s, m in scores) + ".")

    if parts:
        _upsert_digest(f"user:{student_id}", " ".join(parts))


def _maybe_rebuild_global_digest(kind: str) -> None:
    row = _exec("SELECT updated_at FROM digests WHERE scope=?",
                (f"global:{kind}",)).fetchone()
    if row:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(row[0])
            if age < _GLOBAL_DIGEST_TTL:
                return
        except ValueError:
            pass

    rows = _exec(
        "SELECT cat, quote, correction, COUNT(*) AS n FROM mistakes WHERE kind=?"
        " GROUP BY cat, quote, correction ORDER BY n DESC LIMIT 8",
        (kind,)).fetchall()
    if not rows:
        return
    chunks = []
    for cat, quote, corr, n in rows:
        example = f" \"{quote}\" -> \"{corr}\"" if quote and corr else ""
        chunks.append(f"{cat}{example} ({n}x)")
    _upsert_digest(f"global:{kind}",
                   "Mistakes students often make in this task: " +
                   "; ".join(chunks) + ".")
