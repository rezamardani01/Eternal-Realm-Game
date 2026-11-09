"""In-memory anti-spam: a minimum gap per user and a sliding window per group."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable


class Throttle:
    def __init__(
        self,
        user_gap: float,
        group_window: int,
        group_max: int,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.user_gap = user_gap
        self.group_window = group_window
        self.group_max = group_max
        self._now = monotonic
        self._user_last: dict[int, float] = {}
        self._group_hits: defaultdict[int, deque[float]] = defaultdict(deque)

    def allow_user(self, user_id: int) -> bool:
        now = self._now()
        last = self._user_last.get(user_id)
        if last is not None and now - last < self.user_gap:
            return False
        self._user_last[user_id] = now
        if len(self._user_last) > 20_000:
            cutoff = now - 60
            self._user_last = {u: t for u, t in self._user_last.items() if t > cutoff}
        return True

    def allow_group(self, chat_id: int) -> bool:
        now = self._now()
        hits = self._group_hits[chat_id]
        while hits and now - hits[0] > self.group_window:
            hits.popleft()
        if len(hits) >= self.group_max:
            return False
        hits.append(now)
        return True
