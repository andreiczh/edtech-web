#!/bin/bash
# Калибровка текстов (2 итерации) + финальный рендер + дифф по зонам.
# Использование: run_calib.sh reset [variants/x.json]
cd "/c/Users/Lenovo/AppData/Local/Temp/claude/C--Users-Lenovo-edtech-copilot-web/894d458b-565a-4a27-a864-637497dd012e/scratchpad/design2" || exit 1
CH="/c/Program Files/Google/Chrome/Application/chrome.exe"
URL="file:///C:/Users/Lenovo/AppData/Local/Temp/claude/C--Users-Lenovo-edtech-copilot-web/894d458b-565a-4a27-a864-637497dd012e/scratchpad/design2/index.html"
OUT='C:\Users\Lenovo\AppData\Local\Temp\claude\C--Users-Lenovo-edtech-copilot-web\894d458b-565a-4a27-a864-637497dd012e\scratchpad\design2'
PY="/c/Users/Lenovo/edtech-copilot-web/backend/.venv/Scripts/python.exe"
if [ -n "$2" ]; then export FONT_VARIANT="$2"; fi
NAME=$(basename "${FONT_VARIANT:-variants/gospeak2.json}" .json)
shot () { "$CH" --headless --disable-gpu --disable-lcd-text --hide-scrollbars --force-device-scale-factor=$1 --window-size=1710,1112 --virtual-time-budget=9000 --screenshot="$OUT\\$2" "$3" 2>&1 | grep -ci written; }
if [ "$1" = "reset" ]; then rm -f tweaks.json; fi
for i in 1 2; do
  "$PY" build.py > /dev/null || exit 1
  shot 2 bare-2x.png "$URL#bare" > /dev/null
  echo "--- калибровка $i ($NAME) ---"
  "$PY" calibrate.py
done
"$PY" build.py
shot 1 out-1x.png "$URL" > /dev/null
shot 2 out-2x.png "$URL" > /dev/null
cp out-1x.png "variant-$NAME.png"
cp out-2x.png "variant-$NAME-2x.png"
cp tweaks.json "tweaks-$NAME.json"
"$PY" zonediff.py
