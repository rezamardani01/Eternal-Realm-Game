def sub(p, o, n, count=1):
    s = open(p, encoding="utf-8").read()
    assert o in s, (p, o[:70])
    open(p, "w", encoding="utf-8").write(s.replace(o, n, count))


M = "eternal_realm/bot/middlewares.py"
s = open(M, encoding="utf-8").read()
s = s.replace("import logging\n", "import asyncio\nimport logging\n", 1)
s += '''

class UserLockMiddleware(BaseMiddleware):
    """Handles one update at a time per player.

    Two fast taps (or two devices) can no longer interleave halfway through a purchase, a claim or an
    animation; the second tap simply waits for the first to finish and then sees the new state.
    """

    def __init__(self) -> None:
        self._locks: dict[int, asyncio.Lock] = {}
        self._waiting: dict[int, int] = {}

    async def __call__(self, handler: Any, event: Any, data: dict[str, Any]) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)
        uid = user.id
        lock = self._locks.setdefault(uid, asyncio.Lock())
        self._waiting[uid] = self._waiting.get(uid, 0) + 1
        try:
            async with lock:
                return await handler(event, data)
        finally:
            self._waiting[uid] -= 1
            if not self._waiting[uid]:  # nobody queued: forget the lock so the table never grows
                self._waiting.pop(uid, None)
                self._locks.pop(uid, None)
'''
open(M, "w", encoding="utf-8").write(s)

A = "eternal_realm/bot/app.py"
sub(A, '''    errors = ErrorMiddleware()
    dp.message.middleware(errors)
    dp.callback_query.middleware(errors)''', '''    locks, errors = UserLockMiddleware(), ErrorMiddleware()
    for observer in (dp.message, dp.callback_query):
        observer.middleware(locks)  # outermost: one update per player at a time
        observer.middleware(errors)''')
sub(A, "from .middlewares import ErrorMiddleware", "from .middlewares import ErrorMiddleware, UserLockMiddleware")

D = "eternal_realm/db/database.py"
s = open(D, encoding="utf-8").read()
s = s.replace('''        async with self._lock:
            conn = self.conn
            await conn.execute("BEGIN IMMEDIATE")''', '''        await self._acquire()
        try:
            conn = self.conn
            await conn.execute("BEGIN IMMEDIATE")''', 1)
s = s.replace('''            else:
                await conn.execute("COMMIT")
''', '''            else:
                await conn.execute("COMMIT")
        finally:
            self._lock.release()
''', 1)
s = s.replace('''        """Read-only access that still waits for any running write transaction."""
        async with self._lock:
            yield Tx(self.conn)''', '''        """Read-only access that still waits for any running write transaction."""
        await self._acquire()
        try:
            yield Tx(self.conn)
        finally:
            self._lock.release()''', 1)
s = s.replace('''    @asynccontextmanager
    async def transaction(self)''', '''    async def _acquire(self) -> None:
        """Take the database lock, but never wait forever: a stuck holder becomes a logged error."""
        try:
            await asyncio.wait_for(self._lock.acquire(), LOCK_TIMEOUT)
        except TimeoutError as exc:
            raise RuntimeError("database lock timeout: another task held the database for too long") from exc

    @asynccontextmanager
    async def transaction(self)''', 1)
s = s.replace("import asyncio\n", "import asyncio\n", 1)
s = s.replace("\nclass Database", "\nLOCK_TIMEOUT = 30.0\n\n\nclass Database", 1)
open(D, "w", encoding="utf-8").write(s)

C = "eternal_realm/game/services/cards.py"
sub(C, '''        await tx.execute(
            "UPDATE card_listings SET status = 'sold', buyer_id = ? WHERE id = ? AND status = 'active'",
            (buyer.id, listing_id),
        )''', '''        await tx.execute(
            "UPDATE card_listings SET status = 'sold', buyer_id = ? WHERE id = ? AND status = 'active'",
            (buyer.id, listing_id),
        )
        if tx.rowcount != 1:  # somebody else got there first: the status flip is the gate
            raise GameError("این کارت دیگر برای فروش نیست؛ شاید کسی زودتر خریده یا فروشنده پس گرفته است.")''')
