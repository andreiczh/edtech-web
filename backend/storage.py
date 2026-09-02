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
import re
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
        # Снимки экрана к жалобам — ОТДЕЛЬНОЙ таблицей, а не колонкой в
        # disputes. Картинка весит на два порядка больше всей текстовой части
        # жалобы, а очередь разбора выбирает жалобы пачками: держи снимок
        # рядом — и каждое открытие админки тянуло бы десятки мегабайт ради
        # списка, где картинок не видно. base64 в TEXT по тем же причинам, что
        # и у картинок заданий: один тип на оба движка.
        # Замеры произношения для КАЛИБРОВКИ. По строке на слово.
        #
        # Хранятся ЧИСЛА, а не голос. Это не осторожность ради осторожности:
        # для подбора порога нужно распределение показателя на живой речи, а
        # не сама речь, и запись голоса несовершеннолетних потребовала бы
        # согласия, которого у нас нет. Общее правило «транскрипты не храним»
        # остаётся в силе; здесь нет даже транскрипта — только эталонное слово,
        # которое и так лежит в банке заданий, и число рядом с ним.
        "CREATE TABLE IF NOT EXISTS pron_samples ("
        " id TEXT PRIMARY KEY, student_id TEXT NOT NULL, kind TEXT NOT NULL,"
        " variant TEXT, word TEXT NOT NULL, ord INTEGER NOT NULL,"
        " p REAL NOT NULL, p_norm REAL NOT NULL, dur REAL,"
        " model TEXT, created_at TEXT NOT NULL)",
        "CREATE INDEX IF NOT EXISTS idx_pron_created ON pron_samples(created_at)",
        # Маленький ключ-значение под факты о самой системе. Первый жилец —
        # время последнего скачанного бэкапа: скрипт на ноуте может умереть
        # (задача отключилась, файл удалили, ноут спал), и снаружи это никак
        # не видно — задача в планировщике проваливается молча. Пусть сервер
        # сам показывает, когда его последний раз забирали.
        # КОРПУС ГОЛОСА (28.08.2026). Звук лежит base64-ТЕКСТОМ, как картинки
        # заданий: типа BLOB в PostgreSQL нет вовсе, и попытка объявить его
        # роняет ensure_schema с UndefinedObject, а вместе с ним всю память
        # системы (поймано на проде в тот же день). Плата — +33% объёма.
        #
        # Здесь ЛЕЖИТ САМА ЗАПИСЬ — единственное
        # место в системе, кроме dispute_shots, где это так, и потому единственное
        # с явным согласием: без consent=1 в настройках ученика сюда не попадает
        # ничего. Зачем: любая оценка произношения и любая проверка точности
        # упирались в отсутствие живых размеченных работ, а покупать их негде.
        #
        # Разметка КЛАДЁТСЯ СРАЗУ и автоматически: транскрипт, балл по шкале
        # ФИПИ, разбор по критериям, ошибки с цитатами, числа GOP и осмотр
        # звука. Ручная проверка владельца (verified) добавляется поверх —
        # так корпус годен и как обучающий набор, и как сетка точности.
        "CREATE TABLE IF NOT EXISTS voice_corpus ("
        " id TEXT PRIMARY KEY, student_id TEXT NOT NULL, kind TEXT NOT NULL,"
        " variant TEXT, mime TEXT, data TEXT NOT NULL, bytes INTEGER NOT NULL,"
        " duration REAL, transcript TEXT, reference TEXT,"
        " score INTEGER, max_score INTEGER, labels TEXT,"
        " verified TEXT, verified_at TEXT, created_at TEXT NOT NULL)",
        "CREATE INDEX IF NOT EXISTS idx_corpus_created ON voice_corpus(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_corpus_kind ON voice_corpus(kind)",
        # РАЗМЕЧЕННЫЕ РАБОТЫ 42 (01.09.2026). Тестировщик заводит текст
        # монолога, расставляет баллы по трём критериям с обоснованием и
        # перечисляет ошибки. Это калибровочный корпус: точность монолога —
        # слабейшее место оценивания (2-4 из 6 в пределах ±1), и лечится она
        # только такими работами. Формат полей повторяет золотой набор
        # fipi_cases.MONOLOGUE_EXTRA, чтобы экспорт шёл в сетку без ручной
        # переклейки. system — что сказала СИСТЕМА об этой же работе в момент
        # разметки: расхождение видно сразу и навсегда.
        "CREATE TABLE IF NOT EXISTS labeled42 ("
        " id TEXT PRIMARY KEY, name TEXT NOT NULL, variant TEXT,"
        " brief TEXT NOT NULL, facts TEXT, script TEXT NOT NULL,"
        " k1 INTEGER NOT NULL, k2 INTEGER NOT NULL, k3 INTEGER NOT NULL,"
        " rationale TEXT, aspects TEXT, opening INTEGER, closing INTEGER,"
        " errors TEXT, notes TEXT, labeler TEXT, system TEXT,"
        " created_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS meta ("
        " key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS dispute_shots ("
        " id TEXT PRIMARY KEY, dispute_id TEXT NOT NULL, mime TEXT NOT NULL,"
        " data TEXT NOT NULL, bytes INTEGER NOT NULL, created_at TEXT NOT NULL)",
        "CREATE INDEX IF NOT EXISTS idx_shots_dispute ON dispute_shots(dispute_id)",
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
    # Каким СПОСОБОМ получен замер произношения (смешивать нельзя) и ПЫТАЛСЯ
    # ли ученик произнести слово (spoken): пропущенный кусок текста ложится
    # нулями, неотличимыми от «произнёс ужасно», — см. pron_stats.
    _add_columns("pron_samples", ("method TEXT", "spoken INTEGER"))
    # Наследство фонемной ступени 2 (убрана 28.08.2026, DECISIONS §6.29).
    # Колонки оставлены пустыми намеренно: на проде они уже созданы, а
    # восстановление из бэкапа сверяет схемы по факту — удалить их значит
    # сломать заливку вчерашнего дампа.
    _add_columns("pron_samples", ("expected TEXT", "heard TEXT",
                                  "subs INTEGER", "drops INTEGER",
                                  "critical TEXT"))
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
        # Память прошлого разговора едет тем же единственным SELECT: ещё один
        # ключ в IN — это не второй поход в базу.
        scopes.append(f"talk:{student_id}")
    if kind:
        scopes.append(f"global:{kind}")
    if not scopes:
        return {}
    marks = ",".join("?" for _ in scopes)
    rows = _exec(f"SELECT scope, text FROM digests WHERE scope IN ({marks})",
                 tuple(scopes)).fetchall()
    out: dict = {}
    for scope, text in rows:
        key = ("user" if scope.startswith("user:")
               else "talk" if scope.startswith("talk:") else "global")
        out[key] = text
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


def talk_memory_set(student_id: str, text: str) -> None:
    """Память ПРОШЛОГО разговора: темы и интересы, 1-2 предложения.

    Пишется из разбора беседы (talk_review) — дословной речи здесь нет,
    только выжимка «о чём говорили и что зацепило». Хранится последняя:
    собеседнику важно, о чём говорили В ПРОШЛЫЙ РАЗ, а не архив за месяц.
    """
    if text:
        _upsert_digest(f"talk:{student_id}", text)


def talk_memory_get(student_id: str) -> str:
    row = _exec("SELECT text FROM digests WHERE scope=?",
                (f"talk:{student_id}",)).fetchone()
    return str(row[0]) if row else ""


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
    """{день: {метрика: значение}} за последние N дней, новые сверху.

    Отбираем ПО ДАТЕ, а не «первые N×12 строк». Слепой LIMIT молча резал отчёт
    посередине: метрик за день уже под два десятка (расход + замеры скорости по
    этапам), и `usage_report(1)` отдавал двенадцать случайных из них. В
    `/health` это выглядело как «замеров нет» там, где они были, — то есть
    диагностика врала ровно в тот момент, когда по ней принимали решение
    (поймано 05.08.2026 при разборе жалобы на «не удалось разобрать»).
    Строка дня — 'ГГГГ-ММ-ДД', она сравнивается как текст.
    """
    first = (datetime.now(timezone.utc) - timedelta(days=max(1, days) - 1)).strftime("%Y-%m-%d")
    rows = _exec("SELECT day, metric, value FROM usage_daily WHERE day >= ?"
                 " ORDER BY day DESC", (first,)).fetchall()
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


def task_active_by_prefix(prefix: str) -> dict | None:
    """Опубликованное задание по НАЧАЛУ id. Нужно озвучке слова (`/speak`).

    Фронт зовёт серверные варианты `39-x<первые 8 знаков uuid>` — полного id у
    него нет, и по этому огрызку сервер обязан найти задание сам, иначе
    сверять слово будет не с чем. Префикс проверяется регуляркой ДО запроса:
    в LIKE попадают `%` и `_`, и подставлять туда чужую строку нельзя.
    Неоднозначный префикс (нашлось больше одного) — это не задание, а совпадение
    первых знаков; такое честнее считать ненайденным.
    """
    p = str(prefix or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{6,32}", p):
        return None
    rows = _exec("SELECT id, task_no, kind, payload FROM tasks"
                 " WHERE active=1 AND id LIKE ? LIMIT 2", (p + "%",)).fetchall()
    if len(rows) != 1:
        return None
    r = rows[0]
    return {"id": r[0], "task_no": r[1], "kind": r[2], "payload": r[3]}


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


def pron_add(student_id: str, kind: str, variant: str, words: list[dict],
             model: str, method: str = "forced") -> int:
    """Замеры произношения одной работы. Возвращает число записанных слов.

    Пишется фоном, после того как ученик уже получил разбор: калибровка не
    должна стоить ему ни секунды ожидания.

    `method` — КАК получен эталон для сверки, см. pron_stats."""
    now = _now()
    n = 0
    for i, w in enumerate(words):
        # Ступень 2 кладёт долю совпавших фонем в p_norm: одно число, по
        # которому потом выбирается порог, живёт в той же колонке и тех же
        # границах 0..1, что и показатель ступени 1. Смешать их нельзя —
        # различает method, см. pron_stats.
        crit = w.get("critical") or []
        crit_s = ",".join(str(c.get("kind", "")) for c in crit) if crit else None
        _exec("INSERT INTO pron_samples(id, student_id, kind, variant, word, ord,"
              " p, p_norm, dur, model, method, spoken, expected, heard, subs,"
              " drops, critical, created_at)"
              " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (str(uuid.uuid4()), student_id, kind, variant[:64],
               str(w.get("word") or "")[:40], i, float(w.get("p") or 0.0),
               float(w.get("p_norm") or 0.0), float(w.get("dur") or 0.0),
               model[:32], method[:16], int(w.get("spoken", 1)),
               (str(w.get("expected"))[:120] if w.get("expected") else None),
               (str(w.get("heard"))[:120] if w.get("heard") else None),
               (int(w["subs"]) if w.get("subs") is not None else None),
               (int(w["drops"]) if w.get("drops") is not None else None),
               crit_s, now))
        n += 1
    return n


def _distribution(rows: list[float]) -> dict:
    """Процентили и «сколько слов станет ошибкой» для одного набора чисел."""
    if not rows:
        return {"total": 0, "percentiles": {}, "below": {}}

    def pct(q: float) -> float:
        i = min(len(rows) - 1, max(0, int(round(q * (len(rows) - 1)))))
        return round(rows[i], 3)

    below = {}
    for thr in (0.2, 0.35, 0.5, 0.7):
        k = sum(1 for v in rows if v < thr)
        below[str(thr)] = {"words": k, "pct": round(100.0 * k / len(rows), 1)}
    return {"total": len(rows),
            "percentiles": {"p05": pct(0.05), "p10": pct(0.10), "p25": pct(0.25),
                            "p50": pct(0.50), "p75": pct(0.75)},
            "below": below}


def pron_stats() -> dict:
    """Распределения показателя на живой речи — то, ради чего всё копится.

    РАЗДЕЛЬНО ПО СПОСОБАМ, и это не педантизм. Способа два, и числа у них
    несравнимые:

      forced — эталон ИЗВЕСТЕН заранее (чтение вслух, задание 39). Мы
        навязываем модели тот самый текст, который был на экране, и меряем,
        подтверждает ли его звук. Это настоящий GOP;
      cross  — эталона нет (задания 40-42 и свободный разговор: ученик говорит
        что хочет). Сверяем звук с тем, что услышал ДРУГОЙ распознаватель
        (Mistral). Не замкнутый круг — системы разные, — но и не то же самое:
        низкий показатель здесь значит «два распознавателя не сошлись», а не
        «звук не похож на нужное слово».

    Смешать их в одном распределении — значит вывести порог, который не годится
    ни там, ни там.
    """
    out: dict = {"by_method": {}, "students": 0, "variants": 0, "total": 0}
    row = _exec("SELECT COUNT(*), COUNT(DISTINCT student_id),"
                " COUNT(DISTINCT variant) FROM pron_samples").fetchone()
    out["total"] = int(row[0] or 0)
    out["students"] = int(row[1] or 0)
    out["variants"] = int(row[2] or 0)
    if not out["total"]:
        return out

    for method in ("forced", "cross"):
        # Старые строки писались до появления колонки method — они все из чтения.
        base = ("(method='forced' OR method IS NULL)" if method == "forced"
                else "method='cross'")
        # В распределение порога идут ТОЛЬКО слова, которые ученик пытался
        # произнести. У forced это spoken=1 строго: строки без колонки не
        # отличают «прочитано плохо» от «не прочитано вовсе», и на проде эти
        # нули составили весь хвост (p05=0.046 при 0.695 на чистом чтении) —
        # в порог им нельзя. У cross эталон — сама расшифровка, непрозвучавших
        # слов там нет по построению, старые строки равноправны.
        cond = (f"{base} AND spoken=1" if method == "forced"
                else f"{base} AND (spoken=1 OR spoken IS NULL)")
        vals = [float(r[0]) for r in _exec(
            f"SELECT p_norm FROM pron_samples WHERE {cond}"  # noqa: S608
            " ORDER BY p_norm").fetchall()]
        d = _distribution(vals)
        if method == "forced":
            # Исключённое показываем счётчиком, а не прячем: владелец должен
            # видеть, сколько слов лежит вне распределения и почему.
            d["excluded"] = {
                "unspoken": int(_exec(
                    f"SELECT COUNT(*) FROM pron_samples WHERE {base}"  # noqa: S608
                    " AND spoken=0").fetchone()[0] or 0),
                "legacy": int(_exec(
                    f"SELECT COUNT(*) FROM pron_samples WHERE {base}"  # noqa: S608
                    " AND spoken IS NULL").fetchone()[0] or 0),
            }
        d["kinds"] = {r[0]: int(r[1]) for r in _exec(
            f"SELECT kind, COUNT(*) FROM pron_samples WHERE {cond}"  # noqa: S608
            " GROUP BY kind").fetchall()}
        d["worst"] = [{"word": r[0], "p_norm": round(float(r[1]), 3), "kind": r[2]}
                      for r in _exec(
                          f"SELECT word, p_norm, kind FROM pron_samples"  # noqa: S608
                          f" WHERE {cond} ORDER BY p_norm LIMIT 12").fetchall()]
        out["by_method"][method] = d
    return out


def corpus_add(student_id: str, kind: str, variant: str, audio: bytes,
               mime: str, duration: float, transcript: str, reference: str,
               score: int | None, max_score: int | None, labels: dict) -> str:
    """Записать работу в корпус вместе с автоматической разметкой.

    Вызывается ФОНОМ после того, как ученик получил разбор: сбор корпуса не
    должен стоить ему ни секунды. Согласие проверяется ВЫШЕ по стеку (main),
    здесь его нет намеренно — функция не должна быть местом, где легко
    забыть проверку, поэтому она просто пишет то, что ей дали.
    """
    import base64 as _b64
    import json as _json

    cid = str(uuid.uuid4())
    payload = _b64.b64encode(audio).decode("ascii")
    _exec("INSERT INTO voice_corpus(id, student_id, kind, variant, mime, data,"
          " bytes, duration, transcript, reference, score, max_score, labels,"
          " created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (cid, student_id, kind, str(variant or "")[:64], mime[:32], payload,
           len(audio), float(duration or 0.0), (transcript or "")[:8000],
           (reference or "")[:8000],
           (int(score) if score is not None else None),
           (int(max_score) if max_score is not None else None),
           _json.dumps(labels, ensure_ascii=False)[:20000], _now()))
    return cid


def corpus_bytes_total() -> int:
    """Сколько места занимает корпус. Neon free — 0.5 ГБ на весь проект, и
    корпус обязан знать свой потолок сам, а не узнавать о нём от базы."""
    row = _exec("SELECT COALESCE(SUM(bytes), 0) FROM voice_corpus").fetchone()
    return int(row[0] or 0)


def corpus_count_for(student_id: str, kind: str = "") -> int:
    """Сколько записей уже взято у этого ученика (чтобы один активный не
    занял весь корпус собой)."""
    if kind:
        row = _exec("SELECT COUNT(*) FROM voice_corpus WHERE student_id=?"
                    " AND kind=?", (student_id, kind)).fetchone()
    else:
        row = _exec("SELECT COUNT(*) FROM voice_corpus WHERE student_id=?",
                    (student_id,)).fetchone()
    return int(row[0] or 0)


def corpus_stats() -> dict:
    """Сводка для админки: сколько собрано, по каким заданиям, сколько места."""
    total, bytes_, students = _exec(
        "SELECT COUNT(*), COALESCE(SUM(bytes), 0), COUNT(DISTINCT student_id)"
        " FROM voice_corpus").fetchone()
    by_kind = {r[0]: {"n": int(r[1]), "mb": round(float(r[2] or 0) / 1048576, 1),
                      "avg_pct": (round(float(r[3]), 1) if r[3] is not None else None)}
               for r in _exec(
                   "SELECT kind, COUNT(*), SUM(bytes),"
                   " AVG(CASE WHEN max_score > 0 THEN 100.0*score/max_score END)"
                   " FROM voice_corpus GROUP BY kind").fetchall()}
    verified = int(_exec("SELECT COUNT(*) FROM voice_corpus"
                         " WHERE verified IS NOT NULL").fetchone()[0] or 0)
    return {
        "total": int(total or 0),
        "mb": round(float(bytes_ or 0) / 1048576, 1),
        "students": int(students or 0),
        "by_kind": by_kind,
        "verified": verified,
    }


def corpus_list(limit: int = 100, kind: str = "", unverified_only: bool = False,
                offset: int = 0) -> list[dict]:
    """Список записей БЕЗ самого звука: он тяжёлый, а листать надо быстро."""
    import json as _json

    where, params = [], []
    if kind:
        where.append("kind=?")
        params.append(kind)
    if unverified_only:
        where.append("verified IS NULL")
    cond = (" WHERE " + " AND ".join(where)) if where else ""
    rows = _exec(
        "SELECT id, student_id, kind, variant, bytes, duration, transcript,"
        " reference, score, max_score, labels, verified, created_at"
        f" FROM voice_corpus{cond} ORDER BY created_at DESC"  # noqa: S608
        " LIMIT ? OFFSET ?", tuple(params) + (int(limit), int(offset))).fetchall()
    out = []
    for r in rows:
        try:
            labels = _json.loads(r[10]) if r[10] else {}
        except Exception:  # noqa: BLE001
            labels = {}
        out.append({
            "id": r[0], "student_id": r[1], "kind": r[2], "variant": r[3],
            "bytes": int(r[4] or 0), "duration": float(r[5] or 0),
            "transcript": r[6], "reference": r[7],
            "score": r[8], "max_score": r[9], "labels": labels,
            "verified": r[11], "created_at": r[12],
        })
    return out


def corpus_audio(cid: str) -> tuple[bytes, str] | None:
    """Сам звук одной записи — для прослушивания в админке и выгрузки."""
    import base64 as _b64

    row = _exec("SELECT data, mime FROM voice_corpus WHERE id=?", (cid,)).fetchone()
    if not row:
        return None
    return _b64.b64decode(row[0]), str(row[1] or "audio/webm")


def corpus_verify(cid: str, verdict: str) -> bool:
    """Вердикт владельца поверх автоматической разметки."""
    cur = _exec("UPDATE voice_corpus SET verified=?, verified_at=? WHERE id=?",
                (str(verdict)[:2000], _now(), cid))
    return bool(getattr(cur, "rowcount", 0))


def corpus_delete(cid: str) -> bool:
    cur = _exec("DELETE FROM voice_corpus WHERE id=?", (cid,))
    return bool(getattr(cur, "rowcount", 0))


def funnel_summary(days: int = 14) -> dict:
    """Воронка запуска из УЖЕ собираемых данных — без единого нового события.

    Вопросы, на которые она отвечает (и на которые нечем было ответить
    30.08.2026, за два дня до MVP): сколько зарегистрировавшихся дошло до
    первого разбора, как быстро, сколько вернулось назавтра и где люди
    отваливаются. Всё считается из accounts + results + activity_days:
    новых таблиц и событий с фронта не нужно, а значит, воронка честна задним
    числом — она видит и тех, кто пришёл до её появления.

    Объёмы пилотные (десятки учеников), поэтому три запроса и сборка в Python:
    SQL-джойны тут были бы преждевременной оптимизацией.
    """
    accounts = _exec("SELECT id, created_at FROM accounts").fetchall()
    firsts = dict(_exec(
        "SELECT student_id, MIN(created_at) FROM results GROUP BY student_id"
    ).fetchall())
    counts = dict(_exec(
        "SELECT student_id, COUNT(*) FROM results GROUP BY student_id"
    ).fetchall())
    act: dict = {}
    for sid, day in _exec("SELECT student_id, day FROM activity_days").fetchall():
        act.setdefault(sid, set()).add(str(day))

    def day_of(ts) -> str:
        return str(ts)[:10]

    def next_day(day: str) -> str:
        d = datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)
        return d.strftime("%Y-%m-%d")

    horizon = (datetime.now(timezone.utc) - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    by_day: dict = {}
    total = with_task = came_back = 0
    delays_min: list[float] = []
    for acc_id, created in accounts:
        total += 1
        reg_day = day_of(created)
        first = firsts.get(acc_id)
        if reg_day >= horizon:
            row = by_day.setdefault(reg_day, {"registered": 0, "reached_task": 0,
                                              "returned_next_day": 0})
            row["registered"] += 1
            if first is not None:
                row["reached_task"] += 1
            if next_day(reg_day) in act.get(acc_id, set()):
                row["returned_next_day"] += 1
        if first is not None:
            with_task += 1
            try:
                c = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                f = datetime.fromisoformat(str(first).replace("Z", "+00:00"))
                delays_min.append(max(0.0, (f - c).total_seconds() / 60.0))
            except ValueError:
                pass
        if next_day(day_of(created)) in act.get(acc_id, set()):
            came_back += 1

    delays_min.sort()
    tasks_by_active = [counts[a] for a, _ in accounts if a in counts]
    return {
        "days": [{"day": d, **v} for d, v in sorted(by_day.items(), reverse=True)],
        "cohort": {
            "accounts": total,
            "reached_first_task": with_task,
            "reached_pct": round(100.0 * with_task / total, 1) if total else 0.0,
            "returned_next_day": came_back,
            "returned_pct": round(100.0 * came_back / total, 1) if total else 0.0,
            "median_minutes_to_first_task": (
                round(delays_min[len(delays_min) // 2], 1) if delays_min else None),
            "avg_tasks_per_active": (
                round(sum(tasks_by_active) / len(tasks_by_active), 1)
                if tasks_by_active else 0.0),
        },
    }


def labeled42_add(rec: dict) -> str:
    """Сохранить размеченную работу. Валидация полей — на вызывающей стороне;
    здесь только фиксация. Возвращает id записи."""
    import json as _json

    rid = str(uuid.uuid4())
    _exec("INSERT INTO labeled42(id, name, variant, brief, facts, script,"
          " k1, k2, k3, rationale, aspects, opening, closing, errors, notes,"
          " labeler, system, created_at)"
          " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (rid, str(rec.get("name") or "")[:120],
           (str(rec.get("variant"))[:64] if rec.get("variant") else None),
           str(rec.get("brief") or "")[:4000],
           _json.dumps(rec.get("facts") or [], ensure_ascii=False)[:2000],
           str(rec.get("script") or "")[:8000],
           int(rec["k1"]), int(rec["k2"]), int(rec["k3"]),
           _json.dumps(rec.get("rationale") or {}, ensure_ascii=False)[:4000],
           _json.dumps(rec.get("aspects") or [], ensure_ascii=False)[:1000],
           int(bool(rec.get("opening"))), int(bool(rec.get("closing"))),
           _json.dumps(rec.get("errors") or [], ensure_ascii=False)[:6000],
           str(rec.get("notes") or "")[:2000],
           str(rec.get("labeler") or "")[:60], None, _now()))
    return rid


def labeled42_set_system(rid: str, system: dict) -> None:
    """Дописать вердикт системы к уже сохранённой работе. Отдельным шагом,
    потому что прогон LLM может упасть — разметка от этого не теряется."""
    import json as _json

    _exec("UPDATE labeled42 SET system=? WHERE id=?",
          (_json.dumps(system, ensure_ascii=False)[:4000], rid))


def labeled42_list(limit: int = 100) -> list[dict]:
    import json as _json

    rows = _exec("SELECT id, name, variant, k1, k2, k3, labeler, system,"
                 " created_at FROM labeled42 ORDER BY created_at DESC"
                 " LIMIT ?", (max(1, min(500, limit)),)).fetchall()
    out = []
    for r in rows:
        sys_ = None
        try:
            sys_ = _json.loads(r[7]) if r[7] else None
        except Exception:  # noqa: BLE001
            pass
        out.append({"id": r[0], "name": r[1], "variant": r[2],
                    "marks": [int(r[3]), int(r[4]), int(r[5])],
                    "labeler": r[6], "system": sys_, "created_at": str(r[8])})
    return out


def labeled42_export() -> dict:
    """Полный экспорт: сырые записи + готовые кейсы формата золотого набора.

    Кейсы можно вставлять в fipi_cases.MONOLOGUE_EXTRA как есть — ровно ради
    этого поля разметки повторяют его формат (name/brief/facts/script/expected).
    """
    import json as _json

    rows = _exec("SELECT id, name, variant, brief, facts, script, k1, k2, k3,"
                 " rationale, aspects, opening, closing, errors, notes, labeler,"
                 " system, created_at FROM labeled42 ORDER BY created_at").fetchall()

    def j(v, default):
        try:
            return _json.loads(v) if v else default
        except Exception:  # noqa: BLE001
            return default

    raw, golden = [], []
    for r in rows:
        raw.append({
            "id": r[0], "name": r[1], "variant": r[2], "brief": r[3],
            "facts": j(r[4], []), "script": r[5],
            "marks": [int(r[6]), int(r[7]), int(r[8])],
            "rationale": j(r[9], {}), "aspects": j(r[10], []),
            "opening": bool(r[11]), "closing": bool(r[12]),
            "errors": j(r[13], []), "notes": r[14], "labeler": r[15],
            "system": j(r[16], None), "created_at": str(r[17]),
        })
        golden.append({
            "name": r[1],
            "brief": r[3],
            "facts": j(r[4], []),
            "script": r[5],
            "expected": (int(r[6]), int(r[7]), int(r[8])),
        })
    return {"count": len(raw), "works": raw, "golden": golden}


def pron_raw(limit: int = 20000) -> list[dict]:
    """Сырые строки копилки — для подбора порога снаружи.

    Сводка отвечает на «как распределено», но порог выбирается по устройству
    хвоста: серии соседних слабых слов — это пропуск куска, одиночные — само
    произношение. Для такого разбора нужны ord и variant, то есть сами строки.
    """
    cols = ("student_id", "kind", "variant", "word", "ord", "p", "p_norm",
            "dur", "model", "method", "spoken", "created_at")
    rows = _exec(f"SELECT {', '.join(cols)} FROM pron_samples"  # noqa: S608
                 " ORDER BY created_at, ord LIMIT ?", (int(limit),)).fetchall()
    return [{k: (str(v) if k == "created_at" else v)
             for k, v in zip(cols, r)} for r in rows]


def meta_set(key: str, value: str) -> None:
    _exec("INSERT INTO meta(key, value, updated_at) VALUES(?,?,?)"
          " ON CONFLICT (key) DO UPDATE SET value=excluded.value,"
          " updated_at=excluded.updated_at", (key, value[:200], _now()))


def meta_get(key: str) -> tuple[str, str] | None:
    """(значение, когда обновлено) либо None."""
    row = _exec("SELECT value, updated_at FROM meta WHERE key=?", (key,)).fetchone()
    return (row[0], row[1]) if row else None


def shot_add(dispute_id: str, mime: str, data_b64: str, size: int) -> str:
    """Снимок экрана к жалобе. Пишется ПОСЛЕ самой жалобы: если картинка не
    доедет, спор всё равно сохранится — терять объяснение из-за картинки
    было бы обидно вдвойне."""
    sid = str(uuid.uuid4())
    _exec("INSERT INTO dispute_shots(id, dispute_id, mime, data, bytes, created_at)"
          " VALUES(?,?,?,?,?,?)", (sid, dispute_id, mime, data_b64, int(size), _now()))
    return sid


def shot_get(shot_id: str) -> tuple[str, str] | None:
    row = _exec("SELECT mime, data FROM dispute_shots WHERE id=?", (shot_id,)).fetchone()
    return (row[0], row[1]) if row else None


def shots_for(dispute_ids: list[str]) -> dict[str, list[dict]]:
    """{id жалобы: [{id, mime, bytes}]} — БЕЗ самих картинок.

    Список жалоб должен знать, что снимок есть, и не тащить его: сама картинка
    приезжает отдельной ручкой, когда владелец откроет карточку."""
    if not dispute_ids:
        return {}
    marks = ",".join("?" for _ in dispute_ids)
    rows = _exec(f"SELECT id, dispute_id, mime, bytes FROM dispute_shots"  # noqa: S608
                 f" WHERE dispute_id IN ({marks}) ORDER BY created_at",
                 tuple(dispute_ids)).fetchall()
    out: dict[str, list[dict]] = {}
    for sid, did, mime, size in rows:
        out.setdefault(did, []).append({"id": sid, "mime": mime, "bytes": int(size or 0)})
    return out


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
    # Со снимком экрана — отдельное число: жалоба с картинкой разбирается в
    # разы быстрее, и по этой доле видно, доносим ли мы до учеников, что
    # скриншот прикладывать можно.
    with_shot = int(_exec("SELECT COUNT(DISTINCT dispute_id) FROM dispute_shots")
                    .fetchone()[0] or 0)
    return {
        "total": total,
        "pending": pending,
        "with_shot": with_shot,
        "by_kind": group("SELECT kind, COUNT(*) FROM disputes GROUP BY kind"),
        "by_reason": group("SELECT reason, COUNT(*) FROM disputes GROUP BY reason"),
        "by_target": group("SELECT target, COUNT(*) FROM disputes GROUP BY target"),
        "by_persona": group("SELECT persona, COUNT(*) FROM disputes GROUP BY persona"),
        "by_verdict": group("SELECT verdict, COUNT(*) FROM disputes"
                            " WHERE verdict IS NOT NULL AND verdict<>'' GROUP BY verdict"),
    }


def dispute_brief(did: str) -> dict | None:
    """Минимум жалобы для перекрёстных запросов: кто, какой вариант, когда."""
    row = _exec("SELECT student_id, kind, variant, created_at FROM disputes"
                " WHERE id=?", (did,)).fetchone()
    if row is None:
        return None
    return {"student_id": row[0], "kind": row[1], "variant": row[2] or "",
            "created_at": str(row[3] or "")}


def pron_run_near(student_id: str, variant: str, at_iso: str,
                  window_min: float = 30.0) -> list[dict]:
    """Замер произношения ТОГО ЖЕ прогона, что и жалоба: тот же ученик и
    вариант, ближайший по времени запуск в окне ±window_min минут.

    Зачем: спор «я так не говорил» — это спор чтеца с распознавалкой, и
    решить его текстом нельзя: текст и есть предмет спора. А замер слышал
    ЗВУК. Первый такой арбитраж (жалоба про goldfish, 16.08.2026) делался
    руками через сырую выгрузку — теперь это запрос.

    Ближайший по модулю, а не «последний до»: сам замер пишется фоном через
    ~полминуты после разбора, и жалоба, отправленная сразу, может опередить
    его строку в базе.
    """
    runs = [str(r[0]) for r in _exec(
        "SELECT DISTINCT created_at FROM pron_samples WHERE student_id=?"
        " AND variant=?", (student_id, variant[:64])).fetchall()]
    if not runs or not at_iso:
        return []

    def _ts(iso: str) -> float:
        try:
            return datetime.fromisoformat(iso).timestamp()
        except ValueError:
            return 0.0

    at = _ts(at_iso)
    best = min(runs, key=lambda r: abs(_ts(r) - at))
    if abs(_ts(best) - at) > window_min * 60:
        return []
    cols = ("word", "ord", "p_norm", "dur", "method", "spoken", "model")
    rows = _exec(
        f"SELECT {', '.join(cols)} FROM pron_samples WHERE student_id=?"
        " AND variant=? AND created_at=? ORDER BY ord",
        (student_id, variant[:64], best)).fetchall()
    return [dict(zip(cols, r), run_at=best) for r in rows]


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
# invites, pron_samples, voice_daily и meta добавлены 27.08.2026: старый список
# молча терял коды доступа и копилку произношения — вскрылось, когда Neon встал
# на паузу и бэкап оказался единственной копией данных.
_BACKUP_TABLES = ("students", "accounts", "results", "mistakes", "digests",
                  "tasks", "usage_daily", "activity_days", "settings", "disputes",
                  "invites", "pron_samples", "voice_daily", "meta", "labeled42")


def dump_all(with_images: bool = False) -> dict:
    """Полный дамп для GET /admin/backup: {таблица: [строки-словари]}.

    Neon free — одна база без бэкапов; этот дамп, скачиваемый по расписанию
    на ноут владельца, и есть стратегия восстановления. Формат — честный
    JSON: восстановление в любую SQL-базу без спецсредств.

    Снимки экрана к жалобам едут только с `with_images`, как и картинки
    заданий: ночной бэкап не должен вырасти в сотню мегабайт из-за них.
    """
    tables = _BACKUP_TABLES + (("task_images", "dispute_shots") if with_images else ())
    out: dict = {}
    for t in tables:
        cur = _exec(f"SELECT * FROM {t}")  # noqa: S608 — имена из белого списка
        cols = [d[0] for d in cur.description]
        out[t] = [dict(zip(cols, row)) for row in cur.fetchall()]
    return out



# Картинки и снимки экрана хранятся base64-ТЕКСТОМ в колонке TEXT (см. схему
# task_images: у SQLite и Postgres разные бинарные типы, и текст — общий
# знаменатель). В бэкапе они лежат тем же текстом, поэтому при восстановлении
# их НЕ НАДО ни кодировать, ни декодировать.
#
# Стоило это дорого: 27.08.2026 восстановление декодировало base64 в байты,
# Postgres записал байты в TEXT-колонку как hex-строку "50...", и все 138
# картинок заданий стали отдавать 500. Прод жил так три дня. Тест это
# пропустил, потому что SQLite молча принимает bytes в TEXT-колонку и
# отдаёт их обратно байтами — проверка «декодировалось в байты» была зелёной
# ровно на том, что ломало прод.

_COLUMN_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def restore_all(tables: dict, force: bool = False,
                replace: bool = False) -> dict:
    """Восстановление из JSON-бэкапа /admin/backup — в ПУСТУЮ базу.

    Сценарий: Neon встал на паузу (квота), данные живут только в ночном дампе
    на ноуте владельца; создаётся свежий проект — и дамп заливается сюда.
    Защита по построению: если в базе уже есть аккаунты, восстановление
    отклоняется (force=True снимает проверку — для сознательной перезаливки).
    Строки кладутся как есть; конфликт первичного ключа роняет таблицу целиком
    — это желаемое поведение: молча пропущенная половина бэкапа хуже ошибки.
    """
    known = set(_BACKUP_TABLES) | {"task_images", "dispute_shots"}
    if not force and not replace:
        (n,) = _exec("SELECT COUNT(*) FROM accounts").fetchone()
        if n:
            raise ValueError(
                f"В базе уже {n} аккаунтов — восстановление только в пустую "
                "базу (или force=1, если перезаливка сознательная).")
    out: dict = {}
    for t, rows in tables.items():
        if t not in known or not isinstance(rows, list) or not rows:
            continue
        cols = [c for c in rows[0] if _COLUMN_RE.match(str(c))]
        if not cols:
            continue
        sql = (f"INSERT INTO {t} ({', '.join(cols)}) "  # noqa: S608 — имена из белого списка
               f"VALUES ({', '.join('?' * len(cols))})")
        for row in rows:
            vals = [row.get(c) for c in cols]
            if replace:
                # Перезаливка поверх существующих строк: нужна, когда чинишь
                # уже испорченные данные, а не заполняешь пустую базу.
                pk = "id" if "id" in cols else None
                if pk:
                    _exec(f"DELETE FROM {t} WHERE {pk}=?", (row.get(pk),))  # noqa: S608
            _exec(sql, tuple(vals))
        out[t] = len(rows)
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
    history = []
    for kind, score, mx, at in rows:
        if not mx:
            continue
        k = kinds.setdefault(kind, {"attempts": 0, "pcts": []})
        k["attempts"] += 1
        pct = 100.0 * (score or 0) / mx
        k["pcts"].append(pct)
        # История для графика прогресса: день + тип + процент. Объём — сотни
        # строк на ученика, агрегирует фронт (неделя/месяц/год из одного ряда).
        history.append({"d": str(at)[:10], "k": kind, "p": round(pct)})

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
            "history": history[-400:],
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

    last_backup = meta_get("last_backup")
    return {
        "users": {"total": users_total, "active_today": active_today,
                  "active_month": active_month},
        # Когда базу последний раз выгружали на ноут. None — не выгружали ни
        # разу с момента появления отметки.
        "last_backup": ({"at": last_backup[1], "what": last_backup[0]}
                        if last_backup else None),
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


def pron_weakest(student_id: str, variant: str, limit: int = 5,
                 threshold: float = 0.05) -> list[dict]:
    """Самые слабые слова ПОСЛЕДНЕГО замера ученика по этому варианту.

    Для экрана «переслушай эти слова». Берём только forced (эталон известен) и
    только spoken=1: непрочитанное — это пропуск, он виден в разборе отдельно и
    к произношению отношения не имеет.

    Порог 0.05 и потолок в пять слов — не вкус, а границы методички ФИПИ по
    заданию 1: «не более 5 фонетических ошибок». На 748 живых словах прода
    (замер 19.08.2026) он метит в среднем 4.3 слова на чтение, то есть внутри
    официальной границы; порог 0.35 пометил бы 8.7 и половину работ увёл за неё.
    """
    row = _exec("SELECT created_at FROM pron_samples WHERE student_id=?"
                " AND variant=? AND (method='forced' OR method IS NULL)"
                " ORDER BY created_at DESC LIMIT 1",
                (student_id, variant[:64])).fetchone()
    if row is None:
        return []
    rows = _exec("SELECT word, p_norm, ord FROM pron_samples WHERE student_id=?"
                 " AND variant=? AND created_at=? AND spoken=1 AND p_norm<?"
                 " ORDER BY p_norm LIMIT ?",
                 (student_id, variant[:64], str(row[0]), float(threshold),
                  int(limit))).fetchall()
    return [{"word": r[0], "p_norm": round(float(r[1]), 3), "ord": int(r[2])}
            for r in rows]
