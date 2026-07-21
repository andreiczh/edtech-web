# check.ps1 - one-shot diagnostic: "did the VPN break the server?"
# Run in a SECOND PowerShell window (do NOT touch the window running uvicorn):
#     powershell -ExecutionPolicy Bypass -File C:\Users\Lenovo\edtech-copilot-web\backend\check.ps1
#
# Read-only. Never prints the API key - only llm_key true/false from /health.
# The report is copied to the clipboard: paste it into the chat on the Mac.
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads .ps1 as the
# system ANSI codepage (CP1251 on RU Windows), so Cyrillic would break parsing.

$ErrorActionPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$ROOT = Split-Path -Parent $PSScriptRoot
$PY   = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$R    = New-Object System.Collections.ArrayList

function Add-Line($s) { [void]$R.Add($s) }

Add-Line ("=== PINGO CHECK  " + (Get-Date -Format "yyyy-MM-dd HH:mm") + " ===")
Add-Line ("project  : " + $ROOT)

# --- git state -------------------------------------------------------------
Push-Location $ROOT
$commit = (git rev-parse --short HEAD 2>$null)
$branch = (git rev-parse --abbrev-ref HEAD 2>$null)
$dirty  = @(git status --porcelain 2>$null).Count
Add-Line ("commit   : " + $commit + "  branch=" + $branch)
Add-Line ("dirty    : " + $dirty + " files (expected 0)")
Add-Line ("autostash: " + (git config --get rebase.autoStash))
Pop-Location

# --- port 8000 -------------------------------------------------------------
$lis = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($lis) {
    foreach ($p in $lis) {
        $pname = (Get-Process -Id $p.OwningProcess -ErrorAction SilentlyContinue).ProcessName
        Add-Line ("port8000 : LISTEN " + $p.LocalAddress + " <- " + $pname + " (pid " + $p.OwningProcess + ")")
    }
} else {
    Add-Line "port8000 : nobody is listening (server not running?)"
}

# --- network / proxy shape -------------------------------------------------
$rt = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
      Sort-Object RouteMetric | Select-Object -First 1
Add-Line ("route    : default via " + $rt.InterfaceAlias)

$pr = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -ErrorAction SilentlyContinue
Add-Line ("sysproxy : enable=" + $pr.ProxyEnable + " server=" + $pr.ProxyServer)
Add-Line ("env      : HTTP_PROXY=" + $env:HTTP_PROXY + " HTTPS_PROXY=" + $env:HTTPS_PROXY + " NO_PROXY=" + $env:NO_PROXY)

if (Test-Path $PY) {
    $pyproxy = & $PY -c "import urllib.request,json;print(json.dumps(urllib.request.getproxies()))" 2>&1
    Add-Line ("py-proxy : " + $pyproxy)
} else {
    Add-Line ("py-proxy : venv not found at " + $PY)
}

# --- our server ------------------------------------------------------------
try {
    $h = Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 10 -ErrorAction Stop
    Add-Line ("health   : OK  llm_key=" + $h.llm_key + "  llm=" + $h.llm_model + "  stt=" + $h.stt)
} catch {
    Add-Line ("health   : FAIL - " + $_.Exception.Message)
}

# --- Mistral reachability (401 is a GOOD answer: network is fine) ----------
$sw = [Diagnostics.Stopwatch]::StartNew()
try {
    Invoke-WebRequest "https://api.mistral.ai/v1/models" -TimeoutSec 20 -UseBasicParsing -ErrorAction Stop | Out-Null
    $st = "HTTP 200"
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    if ($code) { $st = "HTTP $code" } else { $st = "NO NETWORK: " + $_.Exception.Message }
}
$sw.Stop()
Add-Line ("mistral  : " + $st + " in " + [int]$sw.ElapsedMilliseconds + " ms  (401 means network OK)")

# --- clock skew (edge-tts token dies if the clock drifts) ------------------
try {
    $hdr = (Invoke-WebRequest "https://www.bing.com" -Method Head -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop).Headers["Date"]
    $srv = [datetime]::Parse($hdr, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AdjustToUniversal)
    Add-Line ("clock    : skew " + [int](((Get-Date).ToUniversalTime() - $srv).TotalSeconds) + " s (normal < 60)")
} catch {
    Add-Line "clock    : not checked"
}

# --- edge-tts over the network + faster-whisper offline --------------------
if (Test-Path $PY) {
    $probe = @'
import os, sys, asyncio, tempfile, time
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
try:
    import edge_tts
except Exception as e:
    print("tts-ver  : import failed %s" % e); sys.exit(0)
print("tts-ver  : %s" % getattr(edge_tts, "__version__", "unknown"))
mp3 = os.path.join(tempfile.gettempdir(), "pingo_tts.mp3")
t = time.time()
try:
    asyncio.run(edge_tts.Communicate("Hello, this is a short test of the voice pipeline.",
                                     "en-US-AriaNeural").save(mp3))
    print("edge-tts : OK %.2f s, %d bytes" % (time.time() - t, os.path.getsize(mp3)))
except Exception as e:
    print("edge-tts : FAIL %s: %s" % (type(e).__name__, e)); sys.exit(0)
try:
    from faster_whisper import WhisperModel
    t = time.time(); m = WhisperModel("base.en", device="cpu", compute_type="int8")
    load = time.time() - t
    t = time.time(); segs, _ = m.transcribe(mp3, language="en", beam_size=1)
    heard = " ".join(s.text for s in segs).strip()
    print("whisper  : load %.2f s, run %.2f s" % (load, time.time() - t))
    print("heard    : %s" % heard)
except Exception as e:
    print("whisper  : FAIL %s: %s" % (type(e).__name__, e))
'@
    $probe | Set-Content -Encoding UTF8 -Path (Join-Path $env:TEMP "pingo_probe.py")
    Write-Host "Testing voice pipeline (takes ~20 s on first run)..." -ForegroundColor Cyan
    $out = & $PY (Join-Path $env:TEMP "pingo_probe.py") 2>&1
    foreach ($line in $out) { Add-Line ([string]$line) }
}

# --- report ----------------------------------------------------------------
$txt = ($R -join "`r`n")
Write-Host ""
Write-Host $txt
try {
    $txt | Set-Clipboard
    Write-Host ""
    Write-Host "Report copied to clipboard - paste it into the chat on the Mac." -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "Could not copy automatically - select the text above and copy it." -ForegroundColor Yellow
}
Read-Host "Press Enter to close" | Out-Null
