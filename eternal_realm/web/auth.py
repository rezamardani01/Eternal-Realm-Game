"""Web panel sign-in: one-time links created in the bot, then a short session cookie.

Everything is kept in memory on purpose: a restart simply asks the admin for a fresh link.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

LINK_TTL = 300  # a login link works for five minutes, once
SESSION_TTL = 2 * 3600
MAX_FAILURES = 8  # per address inside FAIL_WINDOW before it is locked out
FAIL_WINDOW = 600


@dataclass
class Session:
    admin_id: int
    csrf: str
    expires: float


class WebAuth:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._now = clock
        self._links: dict[str, tuple[int, float]] = {}
        self._sessions: dict[str, Session] = {}
        self._failures: dict[str, list[float]] = {}

    # --- links ------------------------------------------------------------------------------------
    def issue_link_token(self, admin_id: int) -> str:
        self._sweep()
        # one live link per admin: asking again cancels the previous one
        for token, (owner, _) in list(self._links.items()):
            if owner == admin_id:
                del self._links[token]
        token = secrets.token_urlsafe(32)
        self._links[token] = (admin_id, self._now() + LINK_TTL)
        return token

    def peek(self, token: str) -> bool:
        """Is this link still good? (does not use it up: used by the confirmation page)"""
        entry = self._links.get(token)
        return entry is not None and entry[1] > self._now()

    def redeem(self, token: str, address: str) -> str | None:
        """Turn a link into a session id, or ``None``. A link works exactly once."""
        if self.locked(address):
            return None
        entry = self._links.pop(token, None)
        if entry is None or entry[1] <= self._now():
            self._fail(address)
            return None
        sid = secrets.token_urlsafe(32)
        self._sessions[sid] = Session(entry[0], secrets.token_urlsafe(24), self._now() + SESSION_TTL)
        return sid

    # --- sessions -----------------------------------------------------------------------------------
    def session(self, sid: str | None) -> Session | None:
        if not sid:
            return None
        found = self._sessions.get(sid)
        if found is None:
            return None
        if found.expires <= self._now():
            self._sessions.pop(sid, None)
            return None
        return found

    def end(self, sid: str | None) -> None:
        if sid:
            self._sessions.pop(sid, None)

    def end_all(self) -> None:
        self._sessions.clear()

    # --- brute force guard ------------------------------------------------------------------------------
    def _fail(self, address: str) -> None:
        now = self._now()
        hits = [t for t in self._failures.get(address, []) if now - t < FAIL_WINDOW]
        hits.append(now)
        self._failures[address] = hits

    def locked(self, address: str) -> bool:
        now = self._now()
        return len([t for t in self._failures.get(address, []) if now - t < FAIL_WINDOW]) >= MAX_FAILURES

    def _sweep(self) -> None:
        now = self._now()
        self._links = {t: v for t, v in self._links.items() if v[1] > now}
        self._sessions = {s: v for s, v in self._sessions.items() if v.expires > now}
        self._failures = {a: h for a, h in self._failures.items() if any(now - t < FAIL_WINDOW for t in h)}
