# -*- coding: utf-8 -*-
"""Замер ink-боксов текстов на bare-рендере (2x) и расчёт твиков под боксы SVG."""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "../pdfcheck")
from PIL import Image  # noqa: E402

im = Image.open("bare-2x.png").convert("RGB")
px = im.load()
texts = json.load(open("texts.json", encoding="utf-8"))
old = json.load(open("tweaks.json", encoding="utf-8")) if os.path.exists("tweaks.json") else {}
tweaks = {}
ALL = [tuple(t["bare"]) for t in texts.values()]


def dist(p, c):
    return abs(p[0] - c[0]) + abs(p[1] - c[1]) + abs(p[2] - c[2])


for eid, t in texts.items():
    x0, y0, x1, y1 = t["bbox"]
    c = tuple(t["bare"])
    X0, Y0 = int((x0 - 40) * 2), int((y0 - 30) * 2)
    X1, Y1 = int((x1 + 60) * 2), int((y1 + 30) * 2)
    xs, ys = [], []
    for y in range(max(0, Y0), min(im.size[1], Y1)):
        for x in range(max(0, X0), min(im.size[0], X1)):
            p = px[x, y]
            d = dist(p, c)
            # пиксель наш, если ближе к нашему ключу, чем к любому другому, и не фон
            # только почти сплошные пиксели своего ключа: полупрозрачные края
            # соседей (ключи отличаются на 100 по каналу) сюда не проходят
            if d < 60 and all(d < dist(p, o) for o in ALL if o != c):
                xs.append(x)
                ys.append(y)
    if not xs:
        print("нет чернил:", eid)
        continue
    ix0, iy0 = min(xs) / 2, min(ys) / 2
    ix1, iy1 = max(xs) / 2 + 0.5, max(ys) / 2 + 0.5
    ew, eh, iw, ih = x1 - x0, y1 - y0, ix1 - ix0, iy1 - iy0
    prev = old.get(eid, {})
    k = 1.0 if t.get("lock") else eh / ih
    # широкая гарнитура: если по высоте текст вылезает за бокс по ширине
    # больше чем на 4% (трекинг -1.5 не спасёт) — ужимаем по ширине
    if not t.get("lock") and iw * k > ew * 1.04 + 0.9 * max(t["chars"] - 1, 1):
        k = (ew + 0.9 * max(t["chars"] - 1, 1)) / iw
    scale = prev.get("scale", 1.0) * k
    n = max(t["chars"] - 1, 1)
    ls = 0.0 if t.get("lock") else prev.get("ls", 0) + (ew - iw * k) / n
    ls = max(min(ls, 3.0), -0.9)
    dy = prev.get("dy", 0) + (y0 - iy0)
    dx = prev.get("dx", 0) + (x0 - ix0)
    tweaks[eid] = {"scale": round(scale, 4), "ls": round(ls, 3), "dy": round(dy, 2), "dx": round(dx, 2)}
    print(f"{eid[:34]:34s} h {ih:5.1f}->{eh:5.1f}  w {iw:6.1f}->{ew:6.1f}  "
          f"scale={scale:.3f} ls={ls:+.2f} dy={y0 - iy0:+.1f} dx={x0 - ix0:+.1f}")
json.dump(tweaks, open("tweaks.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
