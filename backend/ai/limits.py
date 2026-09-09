"""Per-process demo limits; access code is the primary public cost-control boundary."""

import time
from collections import deque
from threading import Lock


class ChatLimiter:
    def __init__(self, per_minute=6, daily=200):
        self.per_minute = per_minute
        self.daily = daily
        self.recent = {}
        self.day = None
        self.count = 0
        self.lock = Lock()

    def allow(self, client, now=None):
        now = time.time() if now is None else now
        with self.lock:
            day = int(now // 86400)
            if day != self.day:
                self.day, self.count = day, 0
            # Bound memory and remove inactive callers.
            self.recent = {
                key: deque(t for t in values if now - t < 60)
                for key, values in self.recent.items()
                if values and now - values[-1] < 60
            }
            values = self.recent.setdefault(client, deque())
            if len(values) >= self.per_minute or self.count >= self.daily:
                return False
            values.append(now)
            self.count += 1
            return True
