"""Run offline backend suites only; never connect to a production database."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1] / "backend"
env = {**os.environ, "DATABASE_URL": "", "STT_PROVIDER": "mistral", "STT_FALLBACK_LOCAL": "0"}
failed = []
for suite in sorted(root.glob("test_*.py")):
    if "_live" in suite.stem:
        continue
    print(f"Running {suite.name}", flush=True)
    result = subprocess.run([sys.executable, suite.name], cwd=root, env=env, timeout=180)
    if result.returncode:
        failed.append(suite.name)
if failed:
    raise SystemExit("Failed: " + ", ".join(failed))
print("All offline backend suites passed")
