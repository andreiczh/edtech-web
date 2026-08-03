"""Живой прогон разговорного промпта: качество ответов и скорость, по моделям.

Зачем отдельно от test_talk.py: там чистые функции без сети, здесь — настоящая
модель с настоящим промптом. Проверяется ровно то, на что жаловался владелец:
ответы поверхностные, короткие, вопросы не по контексту, ошибки не разбираются.
Каждая жалоба превращена в ИЗМЕРИМЫЙ признак — иначе «стало лучше» остаётся
вопросом веры.

Что меряется на каждой реплике:
  слов          — длина ответа. Жалоба «отвечает очень коротко»;
  вопрос        — есть ли вопрос в конце (без него разговор умирает);
  зацепка       — повторил ли ответ содержательное слово из реплики ученика.
                  Это и есть «отвечает по контексту», выраженное числом;
  пустые фразы  — «That's interesting», «Great job» и прочее из запретного
                  списка промпта;
  поправка      — прозвучало ли исправление там, где ученик ошибся нарочно;
  первый токен  — задержка, из которой складывается пауза до первого звука.

Разговор ФИКСИРОВАННЫЙ (реплики ученика заданы заранее) — иначе две модели
сравнивались бы на разных беседах, и сравнение ничего не значило бы. В сценарий
намеренно вложены ловушки: односложный ответ, фраза по-русски, грубая ошибка
и вопрос, на который уже отвечали раньше.

Запуск (ключ из backend/.env, в вывод не попадает):
    .\\.venv\\Scripts\\python.exe test_talk_live.py                 # текущая модель
    .\\.venv\\Scripts\\python.exe test_talk_live.py --ab            # small против medium
    .\\.venv\\Scripts\\python.exe test_talk_live.py --model X --runs 2
"""

from __future__ import annotations

import argparse
import os
import re
import statistics
import sys
import time

import httpx
from dotenv import load_dotenv
from openai import OpenAI

import personas
import scenarios

load_dotenv()
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.mistral.ai/v1")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "mistral-small-latest")
_LOCAL_IP = os.environ.get("OUTBOUND_LOCAL_IP") or None

# Пустые фразы из запретного списка промпта. Ищем ровно их: это самый
# однозначный признак ответа-пустышки.
BANNED = [
    "that's interesting", "that is interesting", "that's great", "that is great",
    "i see.", "nice to hear", "thanks for sharing", "as an ai", "great job",
    "sounds great", "that sounds interesting",
]

# Служебные слова: по ним нельзя судить, зацепился ли ответ за смысл реплики.
STOP = set("""a an the i you he she it we they me my your his her our their this that
these those is am are was were be been being do does did have has had will would can
could should may might must and or but so if then than of in on at to for with from
by about as not no yes very really just too also there here what when where why how
who which some any all more most much many one two first like get got go going went
""".split())


def client() -> OpenAI:
    """Тот же транспорт, что в бою: свой исходящий адрес и БЕЗ системного
    прокси. Через прокси замеры выходили втрое хуже реальных — боевой путь в
    него не ходит (см. main.llm_client)."""
    return OpenAI(
        base_url=BASE_URL, api_key=os.environ["LLM_API_KEY"],
        timeout=40.0, max_retries=1,
        http_client=httpx.Client(
            transport=httpx.HTTPTransport(local_address=_LOCAL_IP),
            timeout=40.0, trust_env=False,
        ),
    )


# --------------------------------------------------------------------------
# Сценарий беседы. Реплики ученика заданы заранее — включая ловушки.
# --------------------------------------------------------------------------
TOPIC_ID = "weekend"

STUDENT_TURNS = [
    # обычное начало с грубой ошибкой времени
    ("I go to the cinema with my friend yesterday.",
     {"expect_fix": ["went"], "trap": "ошибка времени"}),
    # односложный ответ — тут промпт запрещает переспрашивать то же самое
    ("Yes.", {"trap": "односложный ответ"}),
    # содержательная реплика с конкретной деталью, за которую надо зацепиться
    ("We watched a comedy about a dog who lost his owner in Saint Petersburg.",
     {"hook": ["comedy", "dog", "owner", "petersburg"], "trap": "конкретная деталь"}),
    # переход на русский — промпт требует подсказать фразу и продолжить по-английски
    ("Ну я не знаю как сказать... было смешно, но конец грустный.",
     {"trap": "переход на русский"}),
    # длинная реплика с мнением
    ("I think weekends are too short. Two days is not enough for rest because "
     "I have homework and my mother ask me to help at home.",
     {"expect_fix": ["asks"], "trap": "ошибка согласования"}),
]


def words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def content_words(text: str) -> set[str]:
    return {w for w in words(text) if len(w) > 3 and w not in STOP}


def questions(text: str) -> list[str]:
    """Вопросы из ответа — по ним ловится повтор одного и того же вопроса."""
    return [s.strip() for s in re.split(r"(?<=\?)\s+", text) if s.strip().endswith("?")]


def run_dialog(model: str, persona_id: str = "tutor", verbose: bool = True) -> dict:
    """Один прогон беседы. Возвращает метрики и сами ответы."""
    who = personas.PERSONAS[persona_id]
    sc = scenarios.by_id(TOPIC_ID)
    cl = client()

    history: list[dict] = []
    rows: list[dict] = []
    asked: list[str] = []

    for i, (utterance, marks) in enumerate(STUDENT_TURNS):
        sys_prompt = personas.SYSTEM_PROMPT + f"\n\n{who['prompt']}"
        sys_prompt += "\n" + scenarios.plan_block(sc, len(history) // 2)

        # Домашний канал рвёт соединения — это давно известно и к качеству
        # модели отношения не имеет. Без повторов замер срывался на середине
        # беседы и сравнивать было нечего.
        first_token = None
        reply = ""
        total = 0.0
        last_err: Exception | None = None
        for attempt in range(4):
            t0 = time.time()
            first_token = None
            reply = ""
            try:
                stream = cl.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": sys_prompt},
                              *history,
                              {"role": "user", "content": utterance}],
                    max_tokens=personas.reply_tokens(who),
                    stream=True,
                )
                for chunk in stream:
                    delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
                    if delta and first_token is None:
                        first_token = time.time() - t0
                    reply += delta
                total = time.time() - t0
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                print(f"    (сеть сорвалась: {type(e).__name__}, повтор "
                      f"{attempt + 1}/3)")
                time.sleep(3.0 * (attempt + 1))
        else:
            raise RuntimeError(f"реплика {i + 1} не прошла: {last_err}")
        reply = reply.strip()

        low = reply.lower()
        # Для односложной реплики цепляться не за что — признак неприменим,
        # и записывать его в минус модели было бы враньём.
        hooks = marks.get("hook") or list(content_words(utterance))
        row = {
            "turn": i + 1,
            "trap": marks.get("trap", ""),
            "words": len(words(reply)),
            "question": "?" in reply,
            # Зацепка: ответ повторил конкретное слово из реплики ученика.
            "hooked": any(h in low for h in hooks) if hooks else None,
            "banned": [b for b in BANNED if b in low],
            "fixed": all(f.lower() in low for f in marks.get("expect_fix", []))
            if marks.get("expect_fix") else None,
            "repeat_q": any(
                q.lower() in [a.lower() for a in asked] for q in questions(reply)),
            "first_token": round(first_token or total, 2),
            "total": round(total, 2),
            "reply": reply,
        }
        asked += questions(reply)
        rows.append(row)
        history += [{"role": "user", "content": utterance},
                    {"role": "assistant", "content": reply}]

        if verbose:
            flags = []
            if not row["question"]:
                flags.append("НЕТ ВОПРОСА")
            if row["hooked"] is False:
                flags.append("не зацепился")
            if row["banned"]:
                flags.append("пустая фраза: " + row["banned"][0])
            if row["fixed"] is False:
                flags.append("не поправил")
            if row["repeat_q"]:
                flags.append("ПОВТОР ВОПРОСА")
            mark = ("  <- " + ", ".join(flags)) if flags else ""
            print(f"\n[{i + 1}] ученик ({row['trap']}): {utterance}")
            print(f"    ответ ({row['words']} слов, "
                  f"{row['first_token']}с до первого токена){mark}:")
            print(f"    {reply}")

    fixes = [r["fixed"] for r in rows if r["fixed"] is not None]
    hookable = [r for r in rows if r["hooked"] is not None]
    return {
        "model": model,
        "rows": rows,
        "avg_words": round(statistics.mean(r["words"] for r in rows), 1),
        "questions": sum(1 for r in rows if r["question"]),
        "hooked": f"{sum(1 for r in hookable if r['hooked'])}/{len(hookable)}",
        "banned": sum(len(r["banned"]) for r in rows),
        "repeats": sum(1 for r in rows if r["repeat_q"]),
        "fixes": f"{sum(1 for f in fixes if f)}/{len(fixes)}",
        "first_token": round(statistics.mean(r["first_token"] for r in rows), 2),
        "worst_first_token": max(r["first_token"] for r in rows),
        "total": round(statistics.mean(r["total"] for r in rows), 2),
    }


def summary_line(res: dict) -> str:
    n = len(res["rows"])
    return (f"{res['model']:<26} слов~{res['avg_words']:<6} "
            f"вопрос {res['questions']}/{n}  зацепка {res['hooked']}  "
            f"поправки {res['fixes']}  пустых {res['banned']}  "
            f"повторов {res['repeats']}  первый токен {res['first_token']}с "
            f"(худший {res['worst_first_token']}с)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--ab", action="store_true",
                    help="сравнить mistral-small-latest и mistral-medium-latest")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--persona", default="tutor")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not os.environ.get("LLM_API_KEY"):
        print("Нет LLM_API_KEY в backend/.env")
        return 2

    models = (["mistral-small-latest", "mistral-medium-latest"] if args.ab
              else [args.model])
    results = []
    for model in models:
        for run in range(args.runs):
            label = f"{model} (прогон {run + 1})" if args.runs > 1 else model
            print(f"\n{'=' * 78}\n{label}\n{'=' * 78}")
            try:
                results.append(run_dialog(model, args.persona, not args.quiet))
            except Exception as e:  # noqa: BLE001
                print(f"  ОШИБКА: {type(e).__name__}: {str(e)[:200]}")

    print(f"\n{'=' * 78}\nИТОГО (беседа из {len(STUDENT_TURNS)} реплик, персона "
          f"{args.persona})\n{'=' * 78}")
    for r in results:
        print(summary_line(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
