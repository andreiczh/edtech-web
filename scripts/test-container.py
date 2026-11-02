"""Smoke-test the exact Docker image with no live provider credentials."""
import json
import time
import urllib.error
import urllib.request

base = "http://127.0.0.1:7860"
deadline = time.monotonic() + 60
while True:
    try:
        with urllib.request.urlopen(base + "/ping", timeout=3) as r:
            assert r.status == 200
        break
    except (OSError, AssertionError):
        if time.monotonic() >= deadline:
            raise
        time.sleep(1)
with urllib.request.urlopen(base, timeout=5) as r:
    assert b'<div id="root">' in r.read(), "built frontend missing from container"
for path, status in (("/ready", 503), ("/me/stats", 401)):
    try:
        urllib.request.urlopen(base + path, timeout=5)
        raise AssertionError(f"{path} unexpectedly succeeded without credentials")
    except urllib.error.HTTPError as e:
        assert e.code == status, (path, e.code)
print("Docker frontend, liveness, readiness and authentication passed")
