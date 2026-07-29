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
        # timeout=5: при конкуренции двух ПРОЦЕССОВ за файл SQLite ждёт снятия
        # блокировки, а не мгновенно падает «database is locked».
        _conn = sqlite3.connect(_SQLITE_PATH, check_same_thread=False, timeout=5)
        # WAL: читатели не блокируют писателя — важно, ведь чтение выжимки
        # сидит в горячем пути ответа.
        _conn.execute("PRAGMA journal_mode=WAL")


def _drop_connection():
    """Бросить соединение ПРАВИЛЬНО: с откатом и закрытием.

    Грабли, найденные тестом 23.07.2026: первый же IntegrityError (занятый
    никнейм) оставлял соединение с открытой транзакцией — «брошенный» объект
    жил до сборщика мусора и держал блокировку файла, после чего ВСЕ записи
    падали с «database is locked». Ошибка одного запроса превращалась в отказ
    всей памяти.
    """
    global _conn
    try:
        if _conn is not None:
            _conn.rollback()
            _conn.close()
    except Exception:  # noqa: BLE001 — соединение уже мертво, нам всё равно
        pass
    _conn = None


def _exec(sql: str, params: tuple = ()):  # noqa: ANN202
    """Выполнить запрос, пережив обрыв соединения одной попыткой реконнекта.

    Плейсхолдеры пишем в стиле sqlite («?»), для Postgres меняем на «%s» —
    литералов с вопросительным знаком в наших запросах нет.
    """
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
                _drop_connection()
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
        # Аккаунты: никнейм + хэш пароля. id аккаунта становится student_id для
        # памяти — история следует за человеком между устройствами.
        "CREATE TABLE IF NOT EXISTS accounts ("
        " id TEXT PRIMARY KEY, nickname TEXT NOT NULL UNIQUE,"
        " pass_hash TEXT NOT NULL, exam TEXT NOT NULL, created_at TEXT NOT NULL)",
        # Банк заданий: payload — JSON с полями варианта (readText/images/steps/...).
        # active как INTEGER (0/1) — булев тип у движков разный, а этот одинаков.
        "CREATE TABLE IF NOT EXISTS tasks ("
        " id TEXT PRIMARY KEY, exam TEXT NOT NULL, task_no INTEGER NOT NULL,"
        " kind TEXT NOT NULL, payload TEXT NOT NULL,"
        " active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)",
        # Картинки заданий храним У СЕБЯ, а не ссылками на чужой сайт: ученик
        # не должен зависеть от доступности стороннего сервера, а тот — получать
        # наш трафик. base64 в TEXT, а не BLOB: у SQLite и Postgres типы разные,
        # а текст одинаков; двести картинок по 20 КБ — это ~5 МБ, для базы пыль.
        "CREATE TABLE IF NOT EXISTS task_images ("
        " id TEXT PRIMARY KEY, mime TEXT NOT NULL, data TEXT NOT NULL,"
        " source TEXT, created_at TEXT NOT NULL)",
        # Свой счётчик расхода Mistral: лимиты у ключа НЕ безлимитные
        # (замерено по заголовкам 23.07.2026: LLM 50 req/мин и 50k токенов/мин),
        # а месячные квоты видны только в консоли — значит, продукт обязан
        # считать расход сам. По строке на (день, метрика).
        "CREATE TABLE IF NOT EXISTS usage_daily ("
        " day TEXT NOT NULL, metric TEXT NOT NULL, value INTEGER NOT NULL,"
        " PRIMARY KEY (day, metric))",
        # Streak и XP: по строке на (ученик, день). Дни — МОСКОВСКИЕ (аудитория
        # РФ): день занятий должен кончаться в полночь по часам ученика, а не в
        # 3 утра. Стрик НЕ хранится — вычисляется из этих строк, поэтому его
        # невозможно рассинхронизировать и не нужно чинить.
        "CREATE TABLE IF NOT EXISTS activity_days ("
        " student_id TEXT NOT NULL, day TEXT NOT NULL,"
        " replies INTEGER NOT NULL DEFAULT 0, tasks INTEGER NOT NULL DEFAULT 0,"
        " xp INTEGER NOT NULL DEFAULT 0,"
        " PRIMARY KEY (student_id, day))",
        # Настройки аккаунта (тема, громкость, показывать ли текст) — один JSON
        # на ученика: следуют за человеком между устройствами, как и память.
        "CREATE TABLE IF NOT EXISTS settings ("
        " student_id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL)",
    ):
        _exec(ddl)

    # Миграции существующих таблиц — отдельно от CREATE TABLE и каждая под
    # своим try: ALTER TABLE ADD COLUMN падает, если колонка уже есть, а
    # «уже есть» — это норма при каждом втором старте, а не авария.
    #
    # source='fipi' + source_id='F2934C' у задания: это и защита от дублей при
    # повторном импорте, и видимое происхождение — заимствованное задание
    # должно быть отличимо от своего.
    for column in ("source TEXT", "source_id TEXT"):
        try:
            _exec(f"ALTER TABLE tasks ADD COLUMN {column}")
        except Exception:  # noqa: BLE001 — колонка уже на месте
            pass


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
                max_score: int, duration_sec: int, errors: list,
                session_done: bool = False) -> None:
    """Сохранить итог одного ответа и обновить выжимки. Зовётся фоном."""
    now = _now()
    if _IS_PG:
        _exec("INSERT INTO students(id, created_at) VALUES(?, ?) ON CONFLICT (id) DO NOTHING",
              (student_id, now))
    else:
        _exec("INSERT OR IGNORE INTO students(id, created_at) VALUES(?, ?)",
              (student_id, now))
    # Повтор ли это: проверка ДО вставки нового результата — единственное место,
    # где «решал ли он этот вариант раньше» можно узнать честно. От ответа
    # зависит цена XP (повтор — половинная), поэтому XP начисляется здесь же.
    repeat = bool(variant) and _exec(
        "SELECT 1 FROM results WHERE student_id=? AND variant=? LIMIT 1",
        (student_id, variant[:64])).fetchone() is not None
    _exec("INSERT INTO results(id, student_id, kind, variant, score, max_score,"
          " duration_sec, created_at) VALUES(?,?,?,?,?,?,?,?)",
          (str(uuid.uuid4()), student_id, kind, variant[:64], int(score),
           int(max_score), int(duration_sec), now))
    note_task(student_id, int(score), repeat=repeat, session_done=session_done)

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
    # Жёсткая крышка длины: выжимка едет в промпт КАЖДОГО запроса, и токены
    # у ключа не безлимитные (50k/мин). 700 символов ≈ 180 токенов — потолок,
    # выше которого выжимка перестаёт быть выжимкой.
    _exec("INSERT INTO digests(scope, text, updated_at) VALUES(?,?,?)"
          " ON CONFLICT (scope) DO UPDATE SET text=excluded.text,"
          " updated_at=excluded.updated_at",
          (scope, text[:700], _now()))


# ------------------------------------------------------------- Streak и XP
#
# Принцип: XP выдаёт СЕРВЕР за то, что полезно для экзамена, и цена встроена в
# конструкцию — накрутка упирается не в отдельную защиту, а в дневные потолки
# и рейт-лимиты, которые уже есть. Фронт эти числа только показывает.

REPLY_XP = 5           # реплика в разговоре
REPLY_XP_DAILY_CAP = 30  # XP дают первые N реплик в день (дальше — только счёт)
TASK_XP_BASE = 10      # решённый вариант задания
SESSION_BONUS_XP = 25  # закрытая серия из 5 вариантов


def _msk_day() -> str:
    """Московская дата: день занятий должен кончаться в полночь ПО ЧАСАМ УЧЕНИКА
    (аудитория — РФ), а не в 3 утра, как вышло бы с UTC. МСК = UTC+3 без
    переводов — сдвиг константой честен."""
    return (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%Y-%m-%d")


def _bump_activity(student_id: str, replies: int, tasks: int, xp: int) -> None:
    _exec("INSERT INTO activity_days(student_id, day, replies, tasks, xp)"
          " VALUES(?,?,?,?,?)"
          " ON CONFLICT (student_id, day) DO UPDATE SET"
          " replies = activity_days.replies + excluded.replies,"
          " tasks = activity_days.tasks + excluded.tasks,"
          " xp = activity_days.xp + excluded.xp",
          (student_id, _msk_day(), replies, tasks, xp))


def note_reply(student_id: str) -> None:
    """Реплика разговора: +1 к счёту дня, XP — только за первые N реплик,
    чтобы «hello-hello» не превращался в ферму опыта."""
    row = _exec("SELECT replies FROM activity_days WHERE student_id=? AND day=?",
                (student_id, _msk_day())).fetchone()
    done_today = int(row[0]) if row else 0
    _bump_activity(student_id, replies=1, tasks=0,
                   xp=REPLY_XP if done_today < REPLY_XP_DAILY_CAP else 0)


def note_task(student_id: str, score: int, repeat: bool, session_done: bool) -> None:
    """Решённый вариант: база + балл разбора (XP мягко тянет к качеству, а не
    только к активности). Повтор уже решённого — половинная цена. Закрытая
    серия из 5 — бонус за доведённое до конца."""
    xp = TASK_XP_BASE + max(0, min(int(score), 20))
    if repeat:
        xp //= 2
    if session_done:
        xp += SESSION_BONUS_XP
    _bump_activity(student_id, replies=0, tasks=1, xp=xp)


def activity_summary(student_id: str) -> dict:
    """Всё для экрана статистики одним запросом: дни (для стрика и недельных
    столбиков) и итоговые суммы. 400 дней хватает на год стрика."""
    rows = _exec("SELECT day, replies, tasks, xp FROM activity_days"
                 " WHERE student_id=? ORDER BY day DESC LIMIT 400",
                 (student_id,)).fetchall()
    days = [{"day": r[0], "replies": int(r[1]), "tasks": int(r[2]), "xp": int(r[3])}
            for r in rows]
    return {
        "days": days,
        "xp_total": sum(d["xp"] for d in days),
        "replies_total": sum(d["replies"] for d in days),
        "tasks_total": sum(d["tasks"] for d in days),
        "today": _msk_day(),
    }


# ------------------------------------------------------ Настройки аккаунта

def get_settings(student_id: str) -> str:
    row = _exec("SELECT data FROM settings WHERE student_id=?", (student_id,)).fetchone()
    return row[0] if row else "{}"


def save_settings(student_id: str, data: str) -> None:
    _exec("INSERT INTO settings(student_id, data, updated_at) VALUES(?,?,?)"
          " ON CONFLICT (student_id) DO UPDATE SET data=excluded.data,"
          " updated_at=excluded.updated_at",
          (student_id, data, _now()))


def rename_account(acc_id: str, nickname: str) -> bool:
    """Сменить ник. False — аккаунта нет; занятый ник летит наружу
    IntegrityError, как и при регистрации (main.py превращает его в 409)."""
    cur = _exec("UPDATE accounts SET nickname=? WHERE id=?", (nickname, acc_id))
    return bool(getattr(cur, "rowcount", 0))


# ------------------------------------------------------------ Расход Mistral

def bump_usage(metrics: dict) -> None:
    """Прибавить счётчики за сегодня. Зовётся фоном после каждого вызова API."""
    day = _now()[:10]
    for metric, value in metrics.items():
        v = int(value)
        if v <= 0:
            continue
        _exec("INSERT INTO usage_daily(day, metric, value) VALUES(?,?,?)"
              " ON CONFLICT (day, metric) DO UPDATE SET"
              " value = usage_daily.value + excluded.value",
              (day, metric, v))


def month_report() -> dict:
    """{метрика: сумма} за текущий календарный месяц (UTC). Кормит месячный
    бюджет в main.py: тот держит счётчик в памяти, а сюда ходит изредка —
    восстановиться после рестарта и сверить дрейф."""
    month = _now()[:7]
    rows = _exec(
        "SELECT metric, COALESCE(SUM(value),0) FROM usage_daily"
        " WHERE day LIKE ? GROUP BY metric",
        (month + "%",)).fetchall()
    return {metric: int(value) for metric, value in rows}


def usage_report(days: int = 14) -> dict:
    """{день: {метрика: значение}} за последние N дней, новые сверху."""
    rows = _exec(
        "SELECT day, metric, value FROM usage_daily ORDER BY day DESC LIMIT ?",
        (days * 12,)).fetchall()
    out: dict = {}
    for day, metric, value in rows:
        out.setdefault(day, {})[metric] = value
    return out


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


# ------------------------------------------------------------------ Аккаунты

def is_unique_violation(e: Exception) -> bool:
    """Занятый никнейм у SQLite и Postgres выглядит по-разному — прячем разницу."""
    name = type(e).__name__
    return "IntegrityError" in name or "UniqueViolation" in name or "unique" in str(e).lower()


def create_account(nickname: str, pass_hash: str, exam: str) -> str:
    acc_id = str(uuid.uuid4())
    _exec("INSERT INTO accounts(id, nickname, pass_hash, exam, created_at)"
          " VALUES(?,?,?,?,?)", (acc_id, nickname, pass_hash, exam, _now()))
    return acc_id


def get_account(nickname: str):
    return _exec("SELECT id, nickname, pass_hash, exam FROM accounts WHERE nickname=?",
                 (nickname,)).fetchone()


def account_exists(acc_id: str) -> bool:
    """Для входного шлюза API: is этот id настоящим аккаунтом. Один SELECT по
    первичному ключу; main.py кэширует ответ, чтобы не ходить сюда на каждый
    запрос голосовой петли."""
    return _exec("SELECT 1 FROM accounts WHERE id=?", (acc_id,)).fetchone() is not None


def solved_variants(student_id: str) -> list[str]:
    """Какие варианты этот ученик уже сдавал — по записанным результатам.
    Нужно, чтобы выдача сессий вычёркивала пройденное на ЛЮБОМ устройстве."""
    rows = _exec("SELECT DISTINCT variant FROM results WHERE student_id=? AND variant<>''",
                 (student_id,)).fetchall()
    return [r[0] for r in rows]


# ------------------------------------------------------------- Банк заданий

def tasks_active() -> list[dict]:
    rows = _exec("SELECT id, exam, task_no, kind, payload FROM tasks WHERE active=1"
                 " ORDER BY created_at").fetchall()
    return [{"id": r[0], "exam": r[1], "task_no": r[2], "kind": r[3], "payload": r[4]}
            for r in rows]


def tasks_all() -> list[dict]:
    rows = _exec("SELECT id, exam, task_no, kind, payload, active, created_at FROM tasks"
                 " ORDER BY created_at DESC").fetchall()
    return [{"id": r[0], "exam": r[1], "task_no": r[2], "kind": r[3], "payload": r[4],
             "active": bool(r[5]), "created_at": r[6]} for r in rows]


def task_add(exam: str, task_no: int, kind: str, payload_json: str) -> str:
    tid = str(uuid.uuid4())
    _exec("INSERT INTO tasks(id, exam, task_no, kind, payload, active, created_at)"
          " VALUES(?,?,?,?,?,1,?)", (tid, exam, int(task_no), kind, payload_json, _now()))
    return tid


def task_add_imported(exam: str, task_no: int, kind: str, payload_json: str,
                      source: str, source_id: str) -> str | None:
    """Задание из внешнего источника — СРАЗУ ЧЕРНОВИКОМ (active=0).

    Публикует его человек руками через админку: заимствованное задание может
    оказаться устаревшего формата, с чужой картинкой или просто кривым, и
    выпускать такое к ученикам без просмотра нельзя. Возвращает None, если
    задание с этим source_id уже импортировано — повторный запуск импорта
    ничего не дублирует и ничего не затирает.
    """
    if source_id:
        seen = _exec("SELECT id FROM tasks WHERE source=? AND source_id=?",
                     (source, source_id)).fetchone()
        if seen:
            return None
    tid = str(uuid.uuid4())
    _exec("INSERT INTO tasks(id, exam, task_no, kind, payload, active, created_at,"
          " source, source_id) VALUES(?,?,?,?,?,0,?,?,?)",
          (tid, exam, int(task_no), kind, payload_json, _now(), source, source_id))
    return tid


def task_exists(source: str, source_id: str) -> bool:
    """Уже импортировано? Проверять ДО скачивания и распознавания.

    Раньше проверка стояла после сборки payload, и повторный запуск импорта
    заново гонял зрение по всему банку, чтобы затем выбросить результат.
    Импорт возобновляемый, и дешёвым он должен быть именно на повторе.
    """
    if not source_id:
        return False
    return _exec("SELECT 1 FROM tasks WHERE source=? AND source_id=? LIMIT 1",
                 (source, source_id)).fetchone() is not None


def tasks_drafts() -> list[dict]:
    """Черновики для модерации — самые свежие сверху."""
    rows = _exec("SELECT id, exam, task_no, kind, payload, source, source_id, created_at"
                 " FROM tasks WHERE active=0 ORDER BY created_at DESC").fetchall()
    return [{"id": r[0], "exam": r[1], "task_no": r[2], "kind": r[3], "payload": r[4],
             "source": r[5], "source_id": r[6], "created_at": r[7]} for r in rows]


def task_delete(tid: str) -> bool:
    row = _exec("SELECT id FROM tasks WHERE id=?", (tid,)).fetchone()
    if row is None:
        return False
    _exec("DELETE FROM tasks WHERE id=?", (tid,))
    return True


def tasks_purge_source(source: str) -> int:
    """Вычистить всё, что приехало из источника. Нужно ровно на тот случай,
    если правообладатель попросит убрать материалы: одна кнопка, а не поиск
    по базе руками."""
    rows = _exec("SELECT id FROM tasks WHERE source=?", (source,)).fetchall()
    _exec("DELETE FROM tasks WHERE source=?", (source,))
    return len(rows)


def image_put(img_id: str, mime: str, data_b64: str, source: str) -> None:
    if _IS_PG:
        _exec("INSERT INTO task_images(id, mime, data, source, created_at)"
              " VALUES(?,?,?,?,?) ON CONFLICT (id) DO NOTHING",
              (img_id, mime, data_b64, source, _now()))
    else:
        _exec("INSERT OR IGNORE INTO task_images(id, mime, data, source, created_at)"
              " VALUES(?,?,?,?,?)", (img_id, mime, data_b64, source, _now()))


def image_get(img_id: str) -> tuple[str, str] | None:
    row = _exec("SELECT mime, data FROM task_images WHERE id=?", (img_id,)).fetchone()
    return (row[0], row[1]) if row else None


def task_toggle(tid: str) -> bool | None:
    row = _exec("SELECT active FROM tasks WHERE id=?", (tid,)).fetchone()
    if row is None:
        return None
    new = 0 if row[0] else 1
    _exec("UPDATE tasks SET active=? WHERE id=?", (new, tid))
    return bool(new)


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
