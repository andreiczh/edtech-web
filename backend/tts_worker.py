"""TTS-воркер: отдельный процесс на каждый синтез.

Зачем отдельный процесс: pyttsx3 держит singleton-движок, и на ВТОРОМ вызове
`runAndWait()` в том же процессе часто падает («run loop already started»)
или зависает — особенно на Windows SAPI. На push-to-talk ты упрёшься в это
сразу. Изоляция в подпроцессе лечит это ценой ~0.3с на старт процесса.
Спайку ок; в Pipecat-версии TTS будет другой (Kokoro/стриминг).

Вызов:  python tts_worker.py <out.wav>   ← текст подаётся в stdin
(через stdin, а не argv, чтобы не ломаться на кавычках/длине/юникоде).
"""

import sys

import pyttsx3

# Голоса, которые пробуем выбрать (английские). Порядок = приоритет.
_VOICE_HINTS = ("english", "david", "zira", "mark", "samantha", "alex")


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: tts_worker.py <out.wav>  (текст в stdin)", file=sys.stderr)
        sys.exit(2)
    out = sys.argv[1]
    text = sys.stdin.read()

    engine = pyttsx3.init()
    for v in engine.getProperty("voices"):
        name = (v.name or "").lower()
        if any(k in name for k in _VOICE_HINTS):
            engine.setProperty("voice", v.id)
            break
    engine.save_to_file(text, out)
    engine.runAndWait()


if __name__ == "__main__":
    main()
