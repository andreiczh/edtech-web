"""Anonymous stop-to-playback latency histograms for the live conversation."""
from __future__ import annotations

import math
import secrets
import time
from collections import Counter, OrderedDict

BUCKETS_MS = (250, 500, 750, 1000, 1250, 1500, 1750, 2000, 2250, 2500,
              2750, 3000, 3500, 4000, 5000, 6000, 8000, 12000, 20000, 35000, 75000)
GROUPS = ("first", "followup")
MIN_SAMPLES = 20
WINDOW_DAYS = 14


class PlaybackTokens:
    def __init__(self):
        self.pending: OrderedDict[str, tuple[float, str, str]] = OrderedDict()

    def issue(self, account: str, has_history: bool) -> str:
        now = time.monotonic()
        while self.pending and (next(iter(self.pending.values()))[0] <= now
                                or len(self.pending) >= 2048):
            self.pending.popitem(last=False)
        token = secrets.token_urlsafe(18)
        self.pending[token] = (now + 90, account, "followup" if has_history else "first")
        return token

    def consume(self, account: str, token: str, elapsed_ms: int) -> str | None:
        if not 1 <= elapsed_ms <= BUCKETS_MS[-1]:
            return None
        entry = self.pending.get(token)
        if not entry or entry[1] != account or entry[0] <= time.monotonic():
            return None
        self.pending.pop(token)
        upper = next(bound for bound in BUCKETS_MS if elapsed_ms <= bound)
        return f"playback_{entry[2]}_{upper}"


def summary(metrics: dict) -> dict:
    result = {}
    for group in GROUPS:
        counts = [metrics.get(f"playback_{group}_{bound}", 0) for bound in BUCKETS_MS]
        count = sum(counts)
        upper = None
        if count >= MIN_SAMPLES:
            target = math.ceil(count * 0.9)
            cumulative = 0
            for bound, n in zip(BUCKETS_MS, counts):
                cumulative += n
                if cumulative >= target:
                    upper = bound
                    break
        result[group] = {"samples": count, "p90_upper_ms": upper}
    return {"metric": "microphone_stop_to_playback", "min_samples": MIN_SAMPLES, **result}


def period_summary(days: dict) -> dict:
    """Sum bucket counts across days before calculating the percentile."""
    buckets = Counter()
    for metrics in days.values():
        buckets.update({key: value for key, value in metrics.items() if key.startswith("playback_")})
    result = summary(buckets)
    for group in GROUPS:
        result[group]["needed_for_p90"] = max(0, MIN_SAMPLES - result[group]["samples"])
    return {"window_days": WINDOW_DAYS, **result}
