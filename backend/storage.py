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
        # Копилка несогласий с ИИ. ЕДИНСТВЕННОЕ место, где хранится речь
        # ученика, — и попадает она сюда только по ЯВНОМУ нажатию «не
        # согласен»: человек сам отдаёт свой ответ на пересмотр, о чём форма
        # прямо предупреждает. Кроме расшифровки сохраняется ОБСТАНОВКА
        # (колонка context): текст задания, соседние реплики беседы, снимок
        # разбора — без них спор через неделю нечитаем. Общее решение
        # «транскрипты не храним» остаётся в силе для всего остального.
        # Зачем копилка: спорные разборы + вердикт человека = свой
        # калибровочный набор, как шесть работ ФИПИ, только растущий.
        # Дневные счётчики голосовых запросов: лимит 300/день должен
        # переживать деплой (= каждый git push), иначе он декоративный.
        "CREATE TABLE IF NOT EXISTS voice_daily ("
        " student_id TEXT NOT NULL, day TEXT NOT NULL,"
        " n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (student_id, day))",
        # Коды приглашений. Переехали из переменной окружения в базу
        # (03.08.2026): владелец не должен ходить в панель Render и делать
        # редеплой, чтобы выдать код классу или забрать его у одного человека.
        # Переменная INVITE_CODES осталась как «первый ключ» для холодного
        # старта — ею создаётся первый код, когда база ещё пустая.
        "CREATE TABLE IF NOT EXISTS invites ("
        " code TEXT PRIMARY KEY, note TEXT, uses INTEGER NOT NULL DEFAULT 0,"
        " max_uses INTEGER NOT NULL DEFAULT 0,"
        " active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS disputes ("
        " id TEXT PRIMARY KEY, student_id TEXT NOT NULL, kind TEXT NOT NULL,"
        " variant TEXT, persona TEXT, score INTEGER, max_score INTEGER,"
        " transcript TEXT NOT NULL, feedback TEXT NOT NULL, comment TEXT,"
        " status TEXT NOT NULL DEFAULT 'new', created_at TEXT NOT NULL)",
    ):
        _exec(ddl)

    # Миграции существующих таблиц — отдельно от CREATE TABLE.
    #
    # source='fipi' + source_id='F2934C' у задания: это и защита от дублей при
    # повторном импорте, и видимое происхождение — заимствованное задание
    # должно быть отличимо от своего.
    _add_columns("tasks", ("source TEXT", "source_id TEXT"))
    # Жалоба ученика: без этих полей у неё нет ни причины, ни обстановки —
    # см. backend/disputes.py. Порядок колонок здесь = порядок в dispute_add.
    _add_columns("disputes", (
        "target TEXT", "target_key TEXT", "target_label TEXT", "reason TEXT",
        "claim_score INTEGER", "said TEXT", "context TEXT",
        "verdict TEXT", "verdict_score INTEGER", "verdict_note TEXT",
        "resolved_at TEXT",
    ))


def _columns(table: str) -> set[str]:
    """Имена колонок таблицы. Способ узнать их у движков разный — прячем."""
    if _IS_PG:
        rows = _exec("SELECT column_name FROM information_schema.columns"
                     " WHERE table_name=?", (table,)).fetchall()
        return {r[0] for r in rows}
    return {r[1] for r in _exec(f"PRAGMA table_info({table})").fetchall()}  # noqa: S608


def _add_columns(table: str, specs: tuple[str, ...]) -> None:
    """Дописать недостающие колонки. Спрашиваем схему ОДНИМ запросом, а не
    ловим исключение на каждой колонке: «уже есть» — норма при каждом старте,
    а на Postgres каждая такая проверка стоила бы отдельного похода в Neon."""
    have = _columns(table)
    for spec in specs:
        name = spec.split()[0]
        if name in have:
            continue
        try:
            _exec(f"ALTER TABLE {table} ADD COLUMN {spec}")  # noqa: S608 — свои строки
        except Exception:  # noqa: BLE001 — гонка двух процессов на старте
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


def save_talk_mistakes(student_id: str, errors: list) -> None:
    """Ошибки из разбора РАЗГОВОРА — в ту же копилку, что и ошибки заданий.

    Отдельная функция, а не `save_result` с нулевым баллом: разговор не
    оценивается баллом, и строка в `results` со счётом 0 из 0 испортила бы и
    среднюю успеваемость в сводке, и начисление XP (оно живёт в save_result).
    Здесь только память об ошибках — ровно то, ради чего копилка и заведена:
    частые ошибки ученика подмешиваются в промпты следующих разборов.
    """
    if not student_id or not errors:
        return
    now = _now()
    if _IS_PG:
        _exec("INSERT INTO students(id, created_at) VALUES(?, ?) ON CONFLICT (id) DO NOTHING",
              (student_id, now))
    else:
        _exec("INSERT OR IGNORE INTO students(id, created_at) VALUES(?, ?)",
              (student_id, now))
    for e in errors[:10]:
        if not isinstance(e, dict):
            continue
        quote = str(e.get("quote") or "").strip()
        if not quote:
            continue
        _exec("INSERT INTO mistakes(id, student_id, kind, cat, quote, correction,"
              " explanation, created_at) VALUES(?,?,?,?,?,?,?,?)",
              (str(uuid.uuid4()), student_id, "talk", "talk", quote[:_TRUNC],
               str(e.get("correction") or "")[:_TRUNC],
               str(e.get("explanation") or "")[:_TRUNC], now))
    _rebuild_user_digest(student_id)


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


def reset_password(nickname: str, pass_hash: str) -> bool:
    """Сброс пароля ПО НИКУ — только для админ-ручки. У аккаунтов нет ни
    почты, ни телефона, так что «забыл пароль» решается через владельца:
    он один знает своих учеников в лицо. False — ника нет."""
    cur = _exec("UPDATE accounts SET pass_hash=? WHERE nickname=?",
                (pass_hash, nickname))
    return bool(getattr(cur, "rowcount", 0))


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
    """Сданные варианты В ХРОНОЛОГИЧЕСКОМ ПОРЯДКЕ: самые давние первыми.

    Порядок здесь — не украшение: фронт добирает в сессию давно решённые
    варианты именно с начала списка. Раньше стоял SELECT DISTINCT без
    ORDER BY, порядок был произвольный, и синхронизация перемешивала
    локальную хронологию (03.08.2026). Ключ сортировки — ПОСЛЕДНЯЯ сдача
    варианта: пересдал сегодня — уходит в конец очереди на повтор.
    """
    rows = _exec(
        "SELECT variant, MAX(created_at) AS last FROM results"
        " WHERE student_id=? AND variant<>'' GROUP BY variant ORDER BY last ASC",
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


# ------------------------------------------------ Копилка несогласий с оценкой

_DISPUTE_FIELDS = ("id", "student_id", "kind", "variant", "persona", "target",
                   "target_key", "target_label", "reason", "comment", "said",
                   "score", "max_score", "claim_score", "transcript", "feedback",
                   "context", "status", "verdict", "verdict_score", "verdict_note",
                   "created_at", "resolved_at")


def dispute_add(student_id: str, data: dict) -> str:
    """Несогласие с ИИ — по явному нажатию ученика (см. DDL disputes).

    На вход идёт УЖЕ проверенный словарь из disputes.normalize: сюда жалоба
    попадает только целиком собранной, и переписывать проверки в двух местах
    не приходится.
    """
    did = str(uuid.uuid4())
    _exec("INSERT INTO disputes(id, student_id, kind, variant, persona, target,"
          " target_key, target_label, reason, comment, said, score, max_score,"
          " claim_score, transcript, feedback, context, status, created_at)"
          " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'new',?)",
          (did, student_id, data["kind"], data["variant"], data["persona"],
           data["target"], data["target_key"], data["target_label"],
           data["reason"], data["comment"], data["said"], int(data["score"]),
           int(data["max_score"]), int(data["claim_score"]), data["transcript"],
           data["feedback"], data["context"], _now()))
    return did


def disputes_list(status: str | None = None, limit: int = 200) -> list[dict]:
    """Для админки: свежие жалобы ЦЕЛИКОМ, при желании только неразобранные.

    Отдаём все поля без обрезки: админка — рабочий стол калибровки, а урезанная
    жалоба ровно в том месте, где начинается суть, бесполезна. Экономить тут
    нечего: это один запрос владельца, а не горячий путь ученика."""
    where = " WHERE status=?" if status else ""
    params: tuple = (status, int(limit)) if status else (int(limit),)
    cols = ", ".join(_DISPUTE_FIELDS)
    rows = _exec(f"SELECT {cols} FROM disputes{where}"  # noqa: S608 — свой список
                 " ORDER BY created_at DESC LIMIT ?", params).fetchall()
    return [dict(zip(_DISPUTE_FIELDS, row)) for row in rows]


def disputes_stats() -> dict:
    """Сводка: где система спорит с людьми чаще всего.

    Считает БАЗА, а не админка: те же числа понадобятся в отчётах и тестах, а
    два независимых подсчёта разошлись бы при первой же правке. Разрезы выбраны
    по тому, какое РЕШЕНИЕ они подсказывают:
      * по типу задания — какой разбор чинить первым;
      * по причине — что именно чинить (распознавание, промпт, шкалу);
      * по вердикту владельца — сколько жалоб оказались справедливыми, то есть
        какова настоящая доля ошибок проверки, а не жалоб на неё.
    """
    def group(sql: str) -> dict:
        return {(r[0] or "?"): int(r[1]) for r in _exec(sql).fetchall()}

    total = int(_exec("SELECT COUNT(*) FROM disputes").fetchone()[0] or 0)
    pending = int(_exec("SELECT COUNT(*) FROM disputes WHERE status='new'")
                  .fetchone()[0] or 0)
    return {
        "total": total,
        "pending": pending,
        "by_kind": group("SELECT kind, COUNT(*) FROM disputes GROUP BY kind"),
        "by_reason": group("SELECT reason, COUNT(*) FROM disputes GROUP BY reason"),
        "by_target": group("SELECT target, COUNT(*) FROM disputes GROUP BY target"),
        "by_persona": group("SELECT persona, COUNT(*) FROM disputes GROUP BY persona"),
        "by_verdict": group("SELECT verdict, COUNT(*) FROM disputes"
                            " WHERE verdict IS NOT NULL AND verdict<>'' GROUP BY verdict"),
    }


def dispute_resolve(did: str, status: str, verdict: str, verdict_score: int,
                    verdict_note: str) -> bool:
    """Вердикт владельца по жалобе. Это и есть разметка золотого набора:
    строка «наш балл 3, верный 5, потому что аспект 2 раскрыт» — готовый
    калибровочный случай. False — жалобы с таким id нет."""
    cur = _exec("UPDATE disputes SET status=?, verdict=?, verdict_score=?,"
                " verdict_note=?, resolved_at=? WHERE id=?",
                (status, verdict, int(verdict_score), verdict_note, _now(), did))
    return bool(getattr(cur, "rowcount", 0))


# ---------------------------------------------------------------- Бэкап

# Таблицы, входящие в дамп. task_images — отдельным флагом: base64-картинки
# весят мегабайты, а меняются только при импорте.
_BACKUP_TABLES = ("students", "accounts", "results", "mistakes", "digests",
                  "tasks", "usage_daily", "activity_days", "settings", "disputes")


def dump_all(with_images: bool = False) -> dict:
    """Полный дамп для GET /admin/backup: {таблица: [строки-словари]}.

    Neon free — одна база без бэкапов; этот дамп, скачиваемый по расписанию
    на ноут владельца, и есть стратегия восстановления. Формат — честный
    JSON: восстановление в любую SQL-базу без спецсредств."""
    tables = _BACKUP_TABLES + (("task_images",) if with_images else ())
    out: dict = {}
    for t in tables:
        cur = _exec(f"SELECT * FROM {t}")  # noqa: S608 — имена из белого списка
        cols = [d[0] for d in cur.description]
        out[t] = [dict(zip(cols, row)) for row in cur.fetchall()]
    return out


# ------------------------------------------------- Аналитика ученика (/me)

def analytics_summary(student_id: str) -> dict:
    """Сырьё для экрана аналитики: динамика балла по типам + профиль ошибок.

    Всё считается из УЖЕ записываемых results/mistakes — новых источников
    данных экран не требует. Группировка в Python, а не в SQL: запросы
    остаются одинаковыми для SQLite и Postgres, а объём на ученика крошечный
    (сотни строк максимум).
    """
    rows = _exec(
        "SELECT kind, score, max_score, created_at FROM results"
        " WHERE student_id=? ORDER BY created_at ASC", (student_id,)).fetchall()

    kinds: dict = {}
    for kind, score, mx, _at in rows:
        if not mx:
            continue
        k = kinds.setdefault(kind, {"attempts": 0, "pcts": []})
        k["attempts"] += 1
        k["pcts"].append(100.0 * (score or 0) / mx)

    out_kinds = {}
    for kind, k in kinds.items():
        pcts = k["pcts"]
        recent = pcts[-5:]
        prev = pcts[-10:-5]
        avg = sum(pcts) / len(pcts)
        recent_avg = sum(recent) / len(recent)
        # Тренд только когда есть с чем сравнивать: стрелка по двум попыткам
        # врала бы. Порог 7 п.п. — меньше не отличимо от шума оценивания.
        trend = "flat"
        if len(prev) >= 3:
            prev_avg = sum(prev) / len(prev)
            if recent_avg - prev_avg > 7:
                trend = "up"
            elif prev_avg - recent_avg > 7:
                trend = "down"
        out_kinds[kind] = {
            "attempts": k["attempts"],
            "avg_pct": round(avg),
            "recent_pct": round(recent_avg),
            "trend": trend,
        }

    mrows = _exec(
        "SELECT cat, quote, correction FROM mistakes"
        " WHERE student_id=? ORDER BY created_at DESC LIMIT 300",
        (student_id,)).fetchall()
    by_cat: dict = {}
    repeats: dict = {}
    for cat, quote, corr in mrows:
        cat = cat or "other"
        c = by_cat.setdefault(cat, {"n": 0, "example": None})
        c["n"] += 1
        if c["example"] is None and quote and corr:
            c["example"] = {"quote": quote, "correction": corr}
        if quote:
            key = (quote or "").lower().strip()[:80]
            r = repeats.setdefault(key, {"quote": quote, "correction": corr or "", "n": 0})
            r["n"] += 1

    top_repeats = sorted((r for r in repeats.values() if r["n"] >= 2),
                         key=lambda r: -r["n"])[:5]
    cats = sorted(
        ({"cat": c, **v} for c, v in by_cat.items()), key=lambda x: -x["n"])[:6]
    return {"kinds": out_kinds,
            "mistakes": {"total": len(mrows), "by_cat": cats, "repeats": top_repeats}}


# ------------------------------------------- Дневной счётчик голосовых запросов

# Публичный псевдоним: main.py нужен тот же «московский день», что и у стрика.
msk_day = _msk_day


def voice_bump(student_id: str, day: str) -> None:
    """+1 к счётчику голосовых запросов ученика за день.

    Зачем в базе: раньше дневной лимит жил в памяти процесса, и каждый деплой
    (= каждый git push) выдавал всем ученикам свежие 300 запросов. Теперь
    счётчик переживает рестарт. Пишется фоном, мимо горячего пути."""
    if _IS_PG:
        _exec("INSERT INTO voice_daily(student_id, day, n) VALUES(?,?,1)"
              " ON CONFLICT (student_id, day) DO UPDATE SET n = voice_daily.n + 1",
              (student_id, day))
    else:
        _exec("INSERT INTO voice_daily(student_id, day, n) VALUES(?,?,1)"
              " ON CONFLICT(student_id, day) DO UPDATE SET n = n + 1",
              (student_id, day))


def voice_counts(day: str) -> dict:
    """Счётчики всех учеников за день — для прогрева памяти на старте."""
    rows = _exec("SELECT student_id, n FROM voice_daily WHERE day=?", (day,)).fetchall()
    return {r[0]: int(r[1]) for r in rows}


# --------------------------------------------------------- Коды приглашений

def invite_add(code: str, note: str, max_uses: int) -> bool:
    """Новый код. False — такой уже есть (перетирать чужой код опасно)."""
    try:
        _exec("INSERT INTO invites(code, note, uses, max_uses, active, created_at)"
              " VALUES(?,?,0,?,1,?)", (code, note, int(max_uses), _now()))
        return True
    except Exception:  # noqa: BLE001 — нарушение уникальности = код занят
        return False


def invite_check(code: str) -> bool:
    """Годен ли код: существует, включён и не исчерпан. Без побочных эффектов —
    расход считается ОТДЕЛЬНО (invite_use), уже после успешной регистрации."""
    row = _exec("SELECT active, uses, max_uses FROM invites WHERE code=?",
                (code,)).fetchone()
    if row is None or not row[0]:
        return False
    return row[2] <= 0 or row[1] < row[2]   # max_uses<=0 — без ограничения


def invite_use(code: str) -> None:
    _exec("UPDATE invites SET uses = uses + 1 WHERE code=?", (code,))


def invite_set_active(code: str, active: bool) -> bool:
    cur = _exec("UPDATE invites SET active=? WHERE code=?", (1 if active else 0, code))
    return bool(getattr(cur, "rowcount", 0))


def invites_list() -> list[dict]:
    rows = _exec("SELECT code, note, uses, max_uses, active, created_at FROM invites"
                 " ORDER BY created_at DESC").fetchall()
    return [{"code": r[0], "note": r[1], "uses": r[2], "max_uses": r[3],
             "active": bool(r[4]), "created_at": r[5]} for r in rows]


def invites_count() -> int:
    row = _exec("SELECT COUNT(*) FROM invites WHERE active=1").fetchone()
    return int(row[0]) if row else 0


# ------------------------------------------------------- Сводка для админки

def overview(month: str, msk_today: str) -> dict:
    """Все числа сводки ОДНИМ снимком из базы.

    Правила точности, ради которых функция вообще существует:
      - источник один — таблицы, а не счётчики в памяти процесса (те
        обнуляются рестартом и врали бы после каждого деплоя);
      - средние скорости считаются из СУММЫ и СЧЁТЧИКА (sum/n) — это точное
        среднее по всем запросам, а не по выборке и не «последнее значение»;
      - деления на ноль невозможны по построению: каждый делитель проверен.

    `month` — 'YYYY-MM' по UTC (тот же ключ, что у месячного бюджета),
    `msk_today` — московский день (тот же, что у стрика и дневных лимитов).
    """
    # Расход за месяц: те же строки usage_daily, из которых бюджет делает
    # свою сверку, — расхождений между сводкой и бюджетом быть не может.
    usage: dict = {}
    for metric, total in _exec(
            "SELECT metric, SUM(value) FROM usage_daily WHERE day LIKE ?"
            " GROUP BY metric", (month + "%",)).fetchall():
        usage[metric] = int(total or 0)

    days_with_traffic = _exec(
        "SELECT COUNT(DISTINCT day) FROM usage_daily WHERE day LIKE ? AND"
        " metric='llm_req'", (month + "%",)).fetchone()[0] or 0

    users_total = _exec("SELECT COUNT(*) FROM accounts").fetchone()[0] or 0
    active_today = _exec(
        "SELECT COUNT(DISTINCT student_id) FROM activity_days WHERE day=?",
        (msk_today,)).fetchone()[0] or 0
    active_month = _exec(
        "SELECT COUNT(DISTINCT student_id) FROM activity_days WHERE day LIKE ?",
        (msk_today[:7] + "%",)).fetchone()[0] or 0

    # Результаты учеников за месяц: попытки и средний процент от максимума.
    results = {}
    for kind, n, avg in _exec(
            "SELECT kind, COUNT(*), AVG(100.0*score/max_score) FROM results"
            " WHERE max_score > 0 AND created_at LIKE ? GROUP BY kind",
            (month + "%",)).fetchall():
        results[kind] = {"attempts": int(n), "avg_pct": round(float(avg or 0))}

    # Скорости: sum/n по каждому этапу. n=0 -> None, фронт покажет «нет данных»
    # вместо нуля — ноль читался бы как «мгновенно», а это неправда.
    latency = {}
    # conv_ttft и conv_tts — РАЗЛОЖЕНИЕ паузы до звука на слагаемые. Без них
    # видно только итог, и любое «ускорение» приходится делать вслепую.
    for stage in ("conv_stt", "conv_ttft", "conv_tts", "conv_answer",
                  "task_stt", "task_llm", "talk_review"):
        ms = usage.get(f"lat_{stage}_ms", 0)
        n = usage.get(f"lat_{stage}_n", 0)
        latency[stage] = {"avg_sec": round(ms / n / 1000, 2), "n": n} if n else None

    return {
        "users": {"total": users_total, "active_today": active_today,
                  "active_month": active_month},
        "month": month,
        "days_with_traffic": int(days_with_traffic),
        "llm_requests": usage.get("llm_req", 0),
        "llm_tokens": (usage.get("llm_prompt_tokens", 0)
                       + usage.get("llm_completion_tokens", 0)),
        "stt_requests": usage.get("stt_req", 0),
        "stt_audio_seconds": usage.get("stt_audio_seconds", 0),
        "tts_chars": (usage.get("tts_edge_chars", 0)
                      + usage.get("tts_mistral_chars", 0)),
        "latency": latency,
        "results": results,
    }
