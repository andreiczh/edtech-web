# -*- coding: utf-8 -*-
"""Сборка index.html из Figma-SVG «MacBook Air - 15»: координаты и картинки —
из файла дословно (масштаб 5225 -> 1710), тексты — шрифтом Onest по боксам."""
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SRC = r"C:\Users\Lenovo\Downloads\Telegram Desktop\MacBook Air - 15 (2).svg"
S = 5225 / 1710
CAP = 0.705          # кап-высота Onest в em (замер)
INK_TOP = 0.125      # верх заглавной от верха строки при line-height = 1em

src = open(SRC, encoding="utf-8").read()
body = src.split("<defs>")[0]
defs = src.split("<defs>")[1]


def attrs_of(tag):
    return dict(re.findall(r'([\w:-]+)="([^"]*)"', tag))


import html as _html


def fix_id(v):
    t = _html.unescape(v)
    raw = bytearray()
    for ch in t:
        o = ord(ch)
        if o < 256:
            raw.append(o)
        else:
            try:
                raw += ch.encode("cp1252")
            except UnicodeEncodeError:
                return t
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return t


elems = {}
for t in re.findall(r'<(?:path|rect|circle)[^>]*/?>', body):
    a = attrs_of(t)
    if a.get("id"):
        elems[fix_id(a["id"])] = (t.split()[0][1:], a)

# безымянные контуры: подпись кнопки «Перейти в канал» (белая заливка, ~10k символов)
for t in re.findall(r'<path[^>]*/?>', body):
    a = attrs_of(t)
    if not a.get("id") and a.get("fill") == "white" and 9000 < len(a.get("d", "")) < 11000:
        elems["Перейти в канал"] = ("path", a)
assert "Перейти в канал" in elems

# ---------------------------------------------------------------- картинки
images = {}
for m in re.finditer(r'<image id="([^"]+)"[^>]*?width="([\d.]+)" height="([\d.]+)"', src):
    images[m.group(1)] = (float(m.group(2)), float(m.group(3)))
patterns = {}
for m in re.finditer(r'<pattern id="([^"]+)"[^>]*>\s*<use xlink:href="#([^"]+)" transform="matrix\(([^)]+)\)"', src):
    a, d, e, f = [float(v) for v in m.group(3).split()][0::3] if False else None, None, None, None
    vals = [float(v) for v in m.group(3).split()]
    patterns[m.group(1)] = {"image": m.group(2), "a": vals[0], "d": vals[3], "e": vals[4], "f": vals[5]}


def px(v):
    return f"{float(v) / S:.2f}px"


def image_box(rect_id, extra_style="", z=1):
    _, r = elems[rect_id]
    p = patterns[r["fill"][5:-1]]
    iw, ih = images[p["image"]]
    x, y, w, h = (float(r.get(k, 0)) / S for k in ("x", "y", "width", "height"))
    rx = float(r.get("rx", 0)) / S
    dw, dh = p["a"] * iw * w, p["d"] * ih * h
    dl, dt = p["e"] * w, p["f"] * h
    op = r.get("opacity", "1")
    return (f'<div class="pic" style="left:{x:.2f}px;top:{y:.2f}px;width:{w:.2f}px;height:{h:.2f}px;'
            f'border-radius:{rx:.2f}px;opacity:{op};z-index:{z};{extra_style}">'
            f'<img src="img/{p["image"]}.png" alt="" style="left:{dl:.2f}px;top:{dt:.2f}px;'
            f'width:{dw:.2f}px;height:{dh:.2f}px"></div>')


# ---------------------------------------------------------------- иконки из SVG
def bbox_of_d(d):
    toks = re.findall(r'[MLHVCSQTAZmlhvcsqtaz]|-?\d*\.?\d+(?:e-?\d+)?', d)
    xs, ys = [], []
    i = 0
    cmd = None
    cx = cy = 0.0
    while i < len(toks):
        t = toks[i]
        if re.match(r'[A-Za-z]', t):
            cmd = t
            i += 1
            continue
        try:
            if cmd == 'H':
                cx = float(t); xs.append(cx); i += 1
            elif cmd == 'h':
                cx += float(t); xs.append(cx); i += 1
            elif cmd == 'V':
                cy = float(t); ys.append(cy); i += 1
            elif cmd == 'v':
                cy += float(t); ys.append(cy); i += 1
            elif cmd == 'A':
                cx, cy = float(toks[i + 5]), float(toks[i + 6]); xs.append(cx); ys.append(cy); i += 7
            elif cmd == 'a':
                cx += float(toks[i + 5]); cy += float(toks[i + 6]); xs.append(cx); ys.append(cy); i += 7
            elif cmd and cmd.islower():
                cx += float(t); cy += float(toks[i + 1]); xs.append(cx); ys.append(cy); i += 2
            else:
                cx, cy = float(t), float(toks[i + 1]); xs.append(cx); ys.append(cy); i += 2
        except (IndexError, ValueError):
            break
    return min(xs), min(ys), max(xs), max(ys)


def elem_bbox(eid):
    tag, a = elems[eid]
    if tag == "path":
        return bbox_of_d(a["d"])
    if tag == "rect":
        x, y, w, h = (float(a.get(k, 0)) for k in ("x", "y", "width", "height"))
        return x, y, x + w, y + h
    if tag == "circle":
        cx, cy, r = (float(a[k]) for k in ("cx", "cy", "r"))
        return cx - r, cy - r, cx + r, cy + r


def elem_markup(eid):
    tag, a = elems[eid]
    a = {k: v for k, v in a.items() if k != "id"}
    return f'<{tag} ' + " ".join(f'{k}="{v}"' for k, v in a.items()) + "/>"


RADIAL = re.search(r'<radialGradient.*?</radialGradient>', defs, re.S).group(0)
LINEAR = re.search(r'<linearGradient.*?</linearGradient>', defs, re.S).group(0)


def icon(ids, pad=6, extra_defs="", z=5, cls=""):
    """Вырезка векторной группы 1:1: viewBox = бокс группы в исходных единицах."""
    bbs = [elem_bbox(i) for i in ids]
    x0 = min(b[0] for b in bbs) - pad
    y0 = min(b[1] for b in bbs) - pad
    x1 = max(b[2] for b in bbs) + pad
    y1 = max(b[3] for b in bbs) + pad
    inner = "".join(elem_markup(i) for i in ids)
    d = f"<defs>{extra_defs}</defs>" if extra_defs else ""
    return (f'<svg class="ic {cls}" style="left:{x0 / S:.2f}px;top:{y0 / S:.2f}px;'
            f'width:{(x1 - x0) / S:.2f}px;height:{(y1 - y0) / S:.2f}px;z-index:{z}" '
            f'viewBox="{x0:.2f} {y0:.2f} {x1 - x0:.2f} {y1 - y0:.2f}" fill="none" '
            f'xmlns="http://www.w3.org/2000/svg">{d}{inner}</svg>')


# ---------------------------------------------------------------- текст по боксу
import json as _json
import os as _os

TWEAKS = _json.load(open("tweaks.json", encoding="utf-8")) if _os.path.exists("tweaks.json") else {}
TEXTS = {}
FONT = _json.load(open(_os.environ.get("FONT_VARIANT", "variants/gospeak2.json"), encoding="utf-8"))


def text(eid, html_, size, lh=None, weight=400, color="#000", width=None, extra="", z=6, first_cap=True,
         lock=False, role="body"):
    """Ставит текст так, чтобы верх заглавной первой строки совпал с верхом
    ink-бокса контура из SVG; калибровка (tweaks.json) правит размер, трекинг
    и сдвиг по замеру реального рендера. lock=True — калибруется только
    положение (размер и межстрочка заданы руками по замеру референса)."""
    x0, y0, x1, y1 = elem_bbox(eid)
    family, weight = FONT["faces"][role]
    extra = f"font-family:'{family}';" + extra
    if role == "demo" and FONT.get("demo_stroke"):
        extra += f"-webkit-text-stroke:{FONT['demo_stroke']}px #000;paint-order:stroke fill;"
    tw = TWEAKS.get(eid, {})
    k = 1.0 if lock else tw.get("scale", 1.0)
    size = round(size * k, 2)
    L = round((lh or size * 1.22) * k, 2)
    top = y0 / S - ((L - size) / 2 + INK_TOP * size) + tw.get("dy", 0)
    left = x0 / S - 0.04 * size + tw.get("dx", 0)
    ls = 0 if lock else tw.get("ls", 0)
    w = f"width:{width}px;" if width else "white-space:nowrap;"
    plain = re.sub(r"<[^>]+>", "", html_.replace("<br>", "\n"))
    lines = plain.split("\n")
    idx = len(TEXTS)
    # решётка заведомо разных цветов (шаг 100 по каналу, без светлых)
    lattice = [(r, g, b) for r in (0, 100, 200) for g in (0, 100, 200) for b in (0, 100, 200)
               if r + g + b <= 400]  # 23 цвета на 20 текстов, повторов нет
    bare = lattice[idx % len(lattice)]
    TEXTS[eid] = {"bbox": [x0 / S, y0 / S, x1 / S, y1 / S], "size": size, "lh": L,
                  "chars": max(len(l) for l in lines), "lines": len(lines), "bare": bare, "lock": lock}
    return (f'<div class="t" data-eid="{eid}" style="left:{left:.2f}px;top:{top:.2f}px;{w}'
            f'font-size:{size}px;line-height:{L}px;font-weight:{weight};color:{color};z-index:{z};'
            f'letter-spacing:{ls:.3f}px;--bare:rgb({bare[0]},{bare[1]},{bare[2]});{extra}">{html_}</div>')


def rect_box(eid, fill, z=4, shadow="", extra=""):
    x0, y0, x1, y1 = elem_bbox(eid)
    _, a = elems[eid]
    rx = float(a.get("rx", 0)) / S
    return (f'<div class="box" style="left:{x0 / S:.2f}px;top:{y0 / S:.2f}px;width:{(x1 - x0) / S:.2f}px;'
            f'height:{(y1 - y0) / S:.2f}px;border-radius:{rx:.2f}px;background:{fill};z-index:{z};'
            f'{"box-shadow:" + shadow + ";" if shadow else ""}{extra}"></div>')


def circle_box(cx, cy, r, fill, z=4, shadow=""):
    return (f'<div class="box" style="left:{(cx - r) / S:.2f}px;top:{(cy - r) / S:.2f}px;width:{2 * r / S:.2f}px;'
            f'height:{2 * r / S:.2f}px;border-radius:50%;background:{fill};z-index:{z};'
            f'{"box-shadow:" + shadow + ";" if shadow else ""}"></div>')


# ================================================================ сборка
parts = []
A = parts.append
GREY = "#696A71"

# фон-картинки карточек
A(image_box("image 9"))                                          # ТЕОРИЯ
A(image_box("image 8"))                                          # AI
A(image_box("768c4d55-2d59-413f-8cda-2ee949fe61c2 1"))          # Telegram
A(image_box("70d77972-fd25-4bfd-8858-ba6e0303d5f8 1"))          # ТРЕНАЖЕР
A(image_box("387307d4-2b4e-43cb-9bb1-eba1a3bb5c68 1"))          # SPEAKING
A(image_box("54176de8-307c-43f3-82fe-ee6b3847d5ad 2"))          # DEMO

# рейлы
RAIL_SHADOW = "0 0 13px rgba(0,0,0,.10)"
for t in re.findall(r'<g id="Rectangle 221[^"]*"[^>]*>\s*<rect[^>]*/>', body):
    a = attrs_of(t.split("<rect")[1])
    x, y, w, h, rx = (float(a.get(k, 0)) / S for k in ("x", "y", "width", "height", "rx"))
    A(f'<div class="box" style="left:{x:.2f}px;top:{y:.2f}px;width:{w:.2f}px;height:{h:.2f}px;'
      f'border-radius:{rx:.2f}px;background:#FCFAFD;box-shadow:{RAIL_SHADOW};z-index:3"></div>')
A(icon(["Rectangle 222", "Vector_2", "Polygon 2"], cls="nav"))
A(icon(["Vector_3"], cls="nav"))
A(icon(["Rectangle 222_2", "Rectangle 223", "Rectangle 224"], cls="nav"))
A(icon(["Vector"], cls="nav"))
A(icon(["Rectangle 187", "Vector_4", "Vector_5"], cls="nav"))
A(icon(["Vector_6"], cls="nav"))

# шапка
A(text("Good morning, Rashid!", "Good morning, Rashid!", 41, lh=50, role="hero"))
A(icon(["Vector_8", "12"], extra_defs=RADIAL, pad=4))
SMALL_SHADOW = "0 0 3px rgba(0,0,0,.07)"
for t in re.findall(r'<g id="Rectangle 19[12]"[^>]*>\s*<rect[^>]*/>', body):
    a = attrs_of(t.split("<rect")[1])
    x, y, w, h = (float(a.get(k, 0)) / S for k in ("x", "y", "width", "height"))
    A(f'<div class="box" style="left:{x:.2f}px;top:{y:.2f}px;width:{w:.2f}px;height:{h:.2f}px;'
      f'border-radius:50%;background:#fff;box-shadow:{SMALL_SHADOW};z-index:3"></div>')
A(icon(["Vector_7"], pad=4))
A(image_box("0bbe14bd1cf8b868728cc24a5a9e314e 2", z=4))

# карточка ТЕОРИЯ
A(text("ТЕОРИЯ", "ТЕОРИЯ", 16, lh=20, color=GREY, role="label"))
A(text("Повтори теорию по заданиям", "Повтори теорию по<br>заданиям", 20, lh=25, role="sub"))
A(text("Краткие конспекты и примеры ответов по всем заданиям",
       "Краткие конспекты и примеры<br>ответов по всем заданиям", 12.5, lh=15.5, color=GREY, role="body"))
A(rect_box("Rectangle 232_5", "#fff"))
A(text("Читать теорию", "Читать теорию", 21, lh=26, role="button"))
A(icon(["Arrow 42_5"], pad=2, z=7))

# карточка AI РЕКОМЕНДАЦИИ
A(text("AI РЕКОМЕНДАЦИИ", "AI РЕКОМЕНДАЦИИ", 19, lh=23, color=GREY, role="label"))
A(text("Вариант по ошибкам", "Вариант по ошибкам", 21, lh=26, role="sub"))
A(text("Собран на основе последних тренировок", "Собран на основе последних<br>тренировок", 12.5, lh=15.5, color=GREY, role="body"))
A(rect_box("Rectangle 232_6", "#fff"))
A(text("Читать теорию_2", "Читать теорию", 21, lh=26, role="button"))
A(icon(["Arrow 42_6"], pad=2, z=7))

# баннер Telegram
A(text("Присоединяйся к Telegram GoSpeak", "Присоединяйся<br>к Telegram GoSpeak", 31, lh=39, role="title"))
A(text("Разборы заданий, новый вариант, советы по ЕГЭ и обновления платформы",
       "Разборы заданий, новый вариант, советы<br>по ЕГЭ и обновления платформы", 14, lh=20, color=GREY, role="body"))
A(rect_box("Rectangle 232_3", "#000"))
A(icon(["Vector_9", "Vector_10"], extra_defs=LINEAR, pad=1, z=7))
A(text("Перейти в канал", "Перейти в канал", 21, lh=26, color="#fff", role="button"))
A(icon(["Arrow 42_3"], pad=2, z=7))
A(circle_box(510.5, 2630.5, 84.5, "#FCFCFE", shadow="0 1.3px 7px rgba(0,0,0,.08)"))
A(circle_box(3168.5, 2629.5, 84.5, "#FCFCFE", shadow="0 1.3px 7px rgba(0,0,0,.08)"))
A(icon(["Line 218", "Line 219"], pad=2, z=7))
A(icon(["Line 220", "Line 221"], pad=2, z=7))
for cid in ("Ellipse 28", "Ellipse 29", "Ellipse 30", "Ellipse 31"):
    _, a = elems[cid]
    A(circle_box(float(a["cx"]), float(a["cy"]), float(a["r"]), a["fill"], z=7))

# правая колонка
A(text("ТРЕНАЖЕР", "ТРЕНАЖЕР", 42, lh=50, role="title"))
A(text("Практикуй все 4 задания устой части ЕГЭ",
       "Практикуй все 4 задания<br>устной части ЕГЭ", 19, lh=26, color=GREY, role="bodyr"))
A(rect_box("Rectangle 232_4", "#000"))
A(text("Начать_3", "Начать", 22, lh=26, color="#fff", role="button"))
A(icon(["Arrow 42_4"], pad=2, z=7))

A(text("SPEAKING", "SPEAKING", 42, lh=50, role="title"))
A(text("Свободные разговоры с AI-собеседником",
       "Свободные разговоры с<br>AI-собеседником", 19, lh=26, color=GREY, role="bodyr"))
A(rect_box("Rectangle 232_2", "#000"))
A(text("Начать_2", "Начать", 22, lh=26, color="#fff", role="button"))
A(icon(["Arrow 42_2"], pad=2, z=7))

A(text("DEMO", "DEMO", 42, lh=50, role="demo"))
A(text("Полный экзамен в формате ЕГЭ", "Полный экзамен в<br>формате ЕГЭ", 19, lh=26, color=GREY, role="bodyr"))
A(rect_box("Rectangle 232", "#000"))
A(text("Начать", "Начать", 22, lh=26, color="#fff", role="button"))
A(icon(["Arrow 42"], pad=2, z=7))

HTML = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GoSpeak — главная</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?__GF__&display=swap" rel="stylesheet">
<style>
  html, body { margin: 0; height: 100%; overflow: hidden; background: #F8F6FB; }
  body { font-family: "__BODYFAMILY__", "Segoe UI", system-ui, sans-serif; color: #000;
         -webkit-font-smoothing: antialiased; }
  #stage { position: absolute; left: 0; top: 0; width: 1710px; height: 1112px;
           transform-origin: 0 0; background: #F8F6FB; }
  .pic { position: absolute; overflow: hidden; }
  .pic img { position: absolute; display: block; max-width: none; }
  .box { position: absolute; }
  .ic  { position: absolute; display: block; overflow: visible; }
  .t   { position: absolute; letter-spacing: 0; }
  .t b { font-weight: __BOLD__; }
  .t.heavy { -webkit-text-stroke: 0.7px #000; paint-order: stroke fill; }
  #stage.bare .pic, #stage.bare .ic, #stage.bare .box { visibility: hidden; }
  #stage.bare .t { color: var(--bare) !important; }
</style>
</head>
<body>
<div id="stage">
__PARTS__
</div>
<script>
  (function () {
    var W = 1710, H = 1112, st = document.getElementById('stage');
    function fit() {
      var k = Math.min(window.innerWidth / W, window.innerHeight / H);
      var dx = (window.innerWidth - W * k) / 2, dy = (window.innerHeight - H * k) / 2;
      st.style.transform = 'translate(' + dx + 'px,' + dy + 'px) scale(' + k + ')';
    }
    if (location.hash === '#bare') st.classList.add('bare');
    window.addEventListener('resize', fit); fit();
  })();
</script>
</body>
</html>
"""
out = (HTML.replace("__PARTS__", "\n".join(parts)).replace("__GF__", FONT["gf"])
       .replace("__BODYFAMILY__", FONT["faces"]["body"][0]).replace("__BOLD__", str(FONT["bold"])))
open("index.html", "w", encoding="utf-8").write(out)
_json.dump(TEXTS, open("texts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("index.html:", len(out) // 1024, "КБ; элементов:", len(parts))
