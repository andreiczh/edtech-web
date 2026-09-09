# -*- coding: utf-8 -*-
"""Дифф HTML-рендера с референсом по зонам + композиты для глаз."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "../pdfcheck")
from PIL import Image, ImageChops  # noqa: E402

ref = Image.open("ref-1x.png").convert("RGB")
out = Image.open("out-1x.png").convert("RGB")
diff = ImageChops.difference(ref, out).convert("L")
zones = {"header": (0, 0, 1710, 150), "rail": (30, 370, 140, 1090), "theory": (160, 150, 600, 600),
         "ai": (620, 150, 1060, 600), "banner": (140, 620, 1060, 1100), "trainer": (1075, 150, 1710, 450),
         "speaking": (1075, 460, 1710, 760), "demo": (1075, 770, 1710, 1080)}
for k, (x0, y0, x1, y1) in zones.items():
    z = diff.crop((x0, y0, x1, y1))
    hist = z.histogram()
    n = z.size[0] * z.size[1]
    bad = sum(hist[41:])
    print(f"{k:9s} mismatch>40: {100 * bad / n:5.1f}%")
ref2 = Image.open("ref-2x.png").convert("RGB")
out2 = Image.open("out-2x.png").convert("RGB")
for k, (x0, y0, x1, y1) in zones.items():
    a = ref2.crop((x0 * 2, y0 * 2, x1 * 2, y1 * 2))
    b = out2.crop((x0 * 2, y0 * 2, x1 * 2, y1 * 2))
    w, h = a.size
    if w > h:
        comp = Image.new("RGB", (w, h * 2 + 8), "red")
        comp.paste(a, (0, 0))
        comp.paste(b, (0, h + 8))
    else:
        comp = Image.new("RGB", (w * 2 + 8, h), "red")
        comp.paste(a, (0, 0))
        comp.paste(b, (w + 8, 0))
    comp.save(f"cmp-{k}.png")
print("composites ok")
