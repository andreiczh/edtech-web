# -*- coding: utf-8 -*-
"""design2/index.html (откалиброванная копия макета) -> src/screens/homeV2Layout.ts

Раскладка живёт в данных, а не в JSX: координаты, размеры, кегли и трекинг —
ровно те, что прошли автокалибровку под боксы SVG. Компонент только вешает
обработчики по ключам.
"""
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

html = open("index.html", encoding="utf-8").read()
stage = html.split('<div id="stage">')[1].split("</div>\n<script>")[0]

# порядок элементов в сборке (build.py) -> ключи
PIC_KEYS = ["theory", "ai", "telegram", "trainer", "speaking", "demo", "avatar"]
IMG_FILES = {"image1_1146_10595": "theory.png", "image0_1146_10595": "ai.png",
             "image4_1146_10595": "telegram.png", "image5_1146_10595": "trainer.png",
             "image6_1146_10595": "speaking.png", "image2_1146_10595": "demo.png",
             "image3_1146_10595": "avatar.png"}
BOX_KEYS = ["railNav", "railTheme", "avatarBg", "bellBg", "btnTheory", "btnAi", "btnTelegram",
            "prevCircle", "nextCircle", "dot1", "dot2", "dot3", "dot4", "btnTrainer", "btnSpeaking", "btnDemo"]
ICON_KEYS = ["navHome", "navCalendar", "navStats", "navSettings", "navSun", "navMoon", "flame", "bell",
             "arrowTheory", "arrowAi", "tgLogo", "arrowTelegram", "chevPrev", "chevNext",
             "arrowTrainer", "arrowSpeaking", "arrowDemo"]
TEXT_KEYS = {
    "Good morning, Rashid!": "greeting", "ТЕОРИЯ": "theoryLabel",
    "Повтори теорию по заданиям": "theoryTitle",
    "Краткие конспекты и примеры ответов по всем заданиям": "theoryText",
    "Читать теорию": "theoryBtn", "AI РЕКОМЕНДАЦИИ": "aiLabel", "Вариант по ошибкам": "aiTitle",
    "Собран на основе последних тренировок": "aiText", "Читать теорию_2": "aiBtn",
    "Присоединяйся к Telegram GoSpeak": "tgTitle",
    "Разборы заданий, новый вариант, советы по ЕГЭ и обновления платформы": "tgText",
    "Перейти в канал": "tgBtn", "ТРЕНАЖЕР": "trainerTitle",
    "Практикуй все 4 задания устой части ЕГЭ": "trainerText", "Начать_3": "trainerBtn",
    "SPEAKING": "speakingTitle", "Свободные разговоры с AI-собеседником": "speakingText",
    "Начать_2": "speakingBtn", "DEMO": "demoTitle", "Полный экзамен в формате ЕГЭ": "demoText",
    "Начать": "demoBtn",
}


def style_dict(s):
    out = {}
    for part in s.split(";"):
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        k = k.strip()
        v = v.strip()
        if k.startswith("--") or k == "z-index" or k == "white-space":
            continue
        out[k] = v
    return out


pics, boxes, icons, texts = [], [], [], {}
tokens = re.findall(r'<div class="pic"[^>]*>.*?</div>|<div class="box"[^>]*></div>|<svg class="ic[^"]*"[^>]*>.*?</svg>|<div class="t"[^>]*>.*?</div>', stage, re.S)
pi = bi = ii = 0
for tok in tokens:
    if tok.startswith('<div class="pic"'):
        outer = style_dict(re.search(r'<div class="pic" style="([^"]*)"', tok).group(1))
        src = re.search(r'src="img/([^"]+)"', tok).group(1)
        inner = style_dict(re.search(r'<img[^>]*style="([^"]*)"', tok).group(1))
        pics.append({"key": PIC_KEYS[pi], "box": outer, "img": {"file": IMG_FILES[src.split(".")[0]], **inner}})
        pi += 1
    elif tok.startswith('<div class="box"'):
        st = style_dict(re.search(r'style="([^"]*)"', tok).group(1))
        boxes.append({"key": BOX_KEYS[bi], "style": st})
        bi += 1
    elif tok.startswith("<svg"):
        st = style_dict(re.search(r'style="([^"]*)"', tok).group(1))
        svg = re.sub(r' class="ic[^"]*"', "", tok)
        svg = re.sub(r' style="[^"]*"', "", svg, count=1)
        icons.append({"key": ICON_KEYS[ii], "style": st, "svg": svg})
        ii += 1
    else:
        eid = re.search(r'data-eid="([^"]*)"', tok).group(1)
        st = style_dict(re.search(r'style="([^"]*)"', tok).group(1))
        inner = re.search(r'>(.*)</div>$', tok, re.S).group(1)
        texts[TEXT_KEYS[eid]] = {"style": st, "html": inner}

assert pi == len(PIC_KEYS) and bi == len(BOX_KEYS) and ii == len(ICON_KEYS) and len(texts) == len(TEXT_KEYS), (pi, bi, ii, len(texts))


def css_to_react(d):
    """kebab-case -> camelCase; значения строкой (px внутри)."""
    o = {}
    for k, v in d.items():
        ck = re.sub(r"-([a-z])", lambda m: m.group(1).upper(), k)
        o[ck] = v
    return o


data = {
    "pics": [{"key": p["key"], "box": css_to_react(p["box"]), "img": css_to_react(p["img"])} for p in pics],
    "boxes": [{"key": b["key"], "style": css_to_react(b["style"])} for b in boxes],
    "icons": [{"key": i["key"], "style": css_to_react(i["style"]), "svg": i["svg"]} for i in icons],
    "texts": {k: {"style": css_to_react(v["style"]), "html": v["html"]} for k, v in texts.items()},
}
ts = ("/* Сгенерировано из откалиброванной копии макета «MacBook Air - 15 (2)»\n"
      " * (scratchpad/design2/emit_layout.py). Не править руками: координаты,\n"
      " * кегли и трекинг подогнаны под боксы SVG автоматически. */\n"
      "import type { CSSProperties } from 'react'\n\n"
      "export const STAGE_W = 1710\nexport const STAGE_H = 1112\n\n"
      "export interface Pic { key: string; box: CSSProperties; img: CSSProperties & { file: string } }\n"
      "export interface Box { key: string; style: CSSProperties }\n"
      "export interface Icon { key: string; style: CSSProperties; svg: string }\n"
      "export interface Txt { style: CSSProperties; html: string }\n\n"
      "export const HOME_LAYOUT: { pics: Pic[]; boxes: Box[]; icons: Icon[]; texts: Record<string, Txt> } = "
      + json.dumps(data, ensure_ascii=False, indent=2) + "\n")
out = r"C:\Users\Lenovo\edtech-copilot-web\src\screens\homeV2Layout.ts"
open(out, "w", encoding="utf-8", newline="\n").write(ts)
print("written:", out, len(ts) // 1024, "КБ; pics", len(pics), "boxes", len(boxes), "icons", len(icons), "texts", len(texts))
