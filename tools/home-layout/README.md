# Раскладка главной из Figma-SVG

Конвейер, которым собран `src/screens/homeV2Layout.ts` (см. `docs/DECISIONS.md` §6.35).
Запускается из этой папки, нужен Python с Pillow и pypdf (в проекте — `backend/.venv`
плюс пакеты в `--target`), Chrome для рендера.

1. `build.py` — читает SVG макета (путь `SRC` в начале файла), вырезает картинки и
   иконки, ставит тексты по боксам контуров, собирает `index.html`.
2. `run_calib.sh reset variants/gospeak2.json` — два круга автокалибровки текстов
   (`calibrate.py`: bare-рендер с цветовыми ключами, замер ink-боксов) + дифф с
   референсом по зонам (`zonediff.py`).
3. `emit_layout.py` — превращает откалиброванный `index.html` в
   `src/screens/homeV2Layout.ts`. Ключи элементов заданы порядком в сборке.

Картинки макета лежат в `public/home`, шрифты — в `public/fonts` (Unbounded, Golos Text).

## Статус

Конвейер разовый: в сборку фронта и в Docker-образ не входит. Его результат,
`src/screens/homeV2Layout.ts`, лежит в репозитории.
