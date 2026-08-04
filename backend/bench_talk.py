"""Разложение паузы до первого звука по этапам. Замер, а не догадки.

Зачем. Сводка показывает одно число — «пауза до звука 2.94 с» — и по нему
нельзя решить, что чинить: оно складывается из распознавания, ожидания первого
токена, генерации первого куска и его синтеза. Оптимизировать вслепую тут
особенно опасно: три из четырёх слагаемых можно «ускорить» ценой качества
(короче ответ, меньше памяти, грубее нарезка), и такой обмен нам не нужен.

Что меряется — РОВНО боевой путь: функции берутся из main.py, а не пишутся
заново, иначе замер будет про стенд, а не про продукт.

  connect    TCP+TLS до api.mistral.ai с нуля
  stt        распознавание реплики ученика (Voxtral mini)
  ttft       от отправки запроса до ПЕРВОГО токена модели
  head_gen   от первого токена до момента, когда набралась голова для озвучки
  tts        синтез головы
  ------------------------------------------------------------------
  first_audio = stt + ttft + head_gen + tts — это и есть пауза для ученика

ХОЛОДНО и ТЕПЛО — отдельные серии, и разница между ними это главное, ради чего
стенд написан. httpx по умолчанию держит простаивающее соединение 5 секунд; в
живом разговоре между репликами проходит 10-60 с, значит КАЖДАЯ реплика платит
новый TLS-хендшейк. Стенд, гоняющий реплики подряд, этого никогда не увидит и
покажет красивые цифры, которых у ученика нет.

Запуск (ключ из backend/.env, в вывод не попадает):
    .\\.venv\\Scripts\\python.exe bench_talk.py                # 4 холодных + 4 тёплых
    .\\.venv\\Scripts\\python.exe bench_talk.py --runs 6
    .\\.venv\\Scripts\\python.exe bench_talk.py --gap 30       # пауза между репликами
    .\\.venv\\Scripts\\python.exe bench_talk.py --label "без VPN"
"""

from __future__ import annotations

import argparse
import asyncio
import socket
import ssl
import statistics
import sys
import time

import edge_tts

import dialogue
import main
import personas

# Реплика ученика ОДНА И ТА ЖЕ во всех прогонах: сравнивать замеры на разных
# фразах бессмысленно — длина аудио меняет время распознавания.
UTTERANCE = ("I went to the cinema with my friend yesterday and we watched "
             "a comedy about a dog.")
HISTORY = [
    {"role": "user", "content": "Hi! I want to practise my English today."},
    {"role": "assistant", "content": "Good to hear it. What did you get up to yesterday?"},
]


async def student_audio() -> bytes:
    """Речь ученика синтезируем — микрофон для замера не нужен (см. CLAUDE.md)."""
    chunks = bytearray()
    async for chunk in edge_tts.Communicate(UTTERANCE, "en-US-AndrewMultilingualNeural").stream():
        if chunk["type"] == "audio":
            chunks.extend(chunk["data"])
    return bytes(chunks)


def connect_ms(host: str, port: int = 443, local_ip: str | None = None) -> float:
    """TCP+TLS с нуля. Именно это платит каждая реплика, когда соединение
    протухло, — и именно это не видно ни в одной метрике продукта.

    `local_ip` привязывает сокет к физическому адаптеру, и трафик идёт МИМО
    VPN-туннеля (тот же приём, что у боевого клиента LLM: OUTBOUND_LOCAL_IP).
    Выключить VPN на машине нельзя, а сравнить два маршрута — можно, и это
    честнее: видно цену туннеля в миллисекундах, а не «примерно медленнее».
    """
    ctx = ssl.create_default_context()
    t0 = time.time()
    with socket.create_connection((host, port), timeout=15,
                                  source_address=(local_ip, 0) if local_ip else None) as raw:
        with ctx.wrap_socket(raw, server_hostname=host):
            return (time.time() - t0) * 1000


async def one_turn(audio: bytes, persona_id: str = "tutor") -> dict:
    """Одна реплика по боевому пути, с секундомером на каждом этапе."""
    who = personas.PERSONAS[persona_id]

    t0 = time.time()
    user_text = await main.transcribe_auto(audio, main.WHISPER_MODEL_FAST)
    t_stt = time.time()

    # Промпт собирается ТАК ЖЕ, как в talk_stream: иначе замер ttft окажется
    # про другой объём префилла.
    sys_prompt = main.SYSTEM_PROMPT + (f"\n\n{who['prompt']}" if who.get("prompt") else "")
    sys_prompt += "\n" + dialogue.flow_block(len(HISTORY) // 2)

    client = main.async_llm_client()
    stream = await client.chat.completions.create(
        model=main.LLM_MODEL,
        messages=[{"role": "system", "content": sys_prompt}, *HISTORY,
                  {"role": "user", "content": user_text}],
        max_tokens=personas.reply_tokens(who),
        stream=True,
    )
    t_first_token = None
    buf = ""
    head = ""
    async for chunk in stream:
        delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
        if not delta:
            continue
        if t_first_token is None:
            t_first_token = time.time()
        buf += delta
        head, rest = main._take_head(buf)
        if head:
            break
    t_head = time.time()

    await main.synthesize(head or buf, who)
    t_tts = time.time()

    return {
        "stt": t_stt - t0,
        "ttft": (t_first_token or t_head) - t_stt,
        "head_gen": t_head - (t_first_token or t_head),
        "tts": t_tts - t_head,
        "first_audio": t_tts - t0,
        "head_chars": len(head or buf),
        "prompt_chars": len(sys_prompt),
        "text": user_text,
    }


def table(name: str, rows: list[dict]) -> None:
    if not rows:
        print(f"{name}: замеров нет")
        return
    keys = ("stt", "ttft", "head_gen", "tts", "first_audio")
    print(f"\n{name} ({len(rows)} реплик)")
    print("  " + "".join(f"{k:>13}" for k in keys) + f"{'голова':>10}")
    for r in rows:
        print("  " + "".join(f"{r[k]:>13.2f}" for k in keys) + f"{r['head_chars']:>10}")
    med = {k: statistics.median(r[k] for r in rows) for k in keys}
    print("  " + "".join(f"{med[k]:>13.2f}" for k in keys) + "   <- медиана")


async def main_async(args) -> int:
    print(f"провайдеры: STT={main.STT_PROVIDER} TTS={main.TTS_PROVIDER} "
          f"LLM={main.LLM_MODEL}")
    if args.label:
        print(f"условия: {args.label}")

    print("\nTCP+TLS с нуля до api.mistral.ai (4 попытки на маршрут):")
    routes = {"маршрут по умолчанию (через VPN)": None}
    if main._LOCAL_IP:
        routes[f"привязка к {main._LOCAL_IP} (мимо VPN)"] = main._LOCAL_IP
    for name, ip in routes.items():
        got = []
        for _ in range(4):
            try:
                got.append(connect_ms("api.mistral.ai", local_ip=ip))
            except OSError as e:
                print(f"  {name}: не подключиться ({e})")
                got = []
                break
            await asyncio.sleep(0.4)
        if got:
            print(f"  {name}: " + ", ".join(f"{h:.0f}" for h in got)
                  + f" мс   медиана {statistics.median(got):.0f} мс")

    audio = await student_audio()
    print(f"\nреплика ученика: {len(audio)} байт аудио\n")

    # ХОЛОДНО: пауза больше времени жизни простаивающего соединения — так
    # выглядит настоящий разговор, где человек думает перед ответом.
    cold: list[dict] = []
    for i in range(args.runs):
        if i:
            await asyncio.sleep(args.gap)
        r = await one_turn(audio)
        cold.append(r)
        print(f"  холодная {i + 1}/{args.runs}: {r['first_audio']:.2f} с")

    # ТЕПЛО: реплики подряд, соединение живое.
    warm: list[dict] = []
    for i in range(args.runs):
        r = await one_turn(audio)
        warm.append(r)
        print(f"  тёплая   {i + 1}/{args.runs}: {r['first_audio']:.2f} с")

    table("ХОЛОДНОЕ соединение (как у ученика между репликами)", cold)
    table("ТЁПЛОЕ соединение (реплики подряд)", warm)

    if cold and warm:
        dc = statistics.median(r["first_audio"] for r in cold)
        dw = statistics.median(r["first_audio"] for r in warm)
        print(f"\nцена холодного старта: {dc - dw:+.2f} с "
              f"({dc:.2f} против {dw:.2f})")
    print(f"системный промпт: {cold[0]['prompt_chars']} знаков "
          f"(~{cold[0]['prompt_chars'] // 4} токенов префилла)")
    print(f"распознано: «{cold[0]['text']}»")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=4)
    ap.add_argument("--gap", type=float, default=20.0,
                    help="пауза между холодными репликами, секунды")
    ap.add_argument("--label", default="", help="пометка условий для протокола")
    sys.exit(asyncio.run(main_async(ap.parse_args())))
