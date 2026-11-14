"""Gift codes: the owner makes a code worth coins, crystals and/or items; a hero types it once to claim it."""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass, field

from ...context import AppContext
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa, normalize
from ..data.items import find_item, get_item
from ..models import Player
from .inventory import InventoryService

#: no 0/O/1/I/L so a code read aloud or from a picture is never mistaken
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_RE = re.compile(r"^[A-Z0-9_-]{4,20}$")
MAX_GOLD, MAX_CRYSTAL, MAX_QTY, MAX_USES, MAX_DAYS = 10_000_000, 100_000, 100_000, 1_000_000, 365

KEYS = {
    "سکه": "gold", "gold": "gold", "کریستال": "crystal", "crystal": "crystal", "آیتم": "item", "item": "item",
    "تعداد": "uses", "uses": "uses", "روز": "days", "days": "days", "کد": "code", "code": "code",
}


@dataclass
class GiftCode:
    code: str
    gold: int = 0
    crystal: int = 0
    items: dict[str, int] = field(default_factory=dict)
    max_uses: int = 1
    used: int = 0
    expires_at: int = 0
    active: bool = True

    def worth(self) -> str:
        parts = []
        if self.gold:
            parts.append(f"🪙 {fa(self.gold)} سکه")
        if self.crystal:
            parts.append(f"💎 {fa(self.crystal)} کریستال")
        parts += [f"{get_item(i).label} ×{fa(q)}" for i, q in self.items.items()]
        return "، ".join(parts)


def parse_spec(text: str) -> dict:
    """Read the owner's one-line description: ``سکه=5000 کریستال=10 آیتم=سنگ آهن*5 تعداد=100 روز=7 کد=EID``.

    Items are written ``name*count``; the ``آیتم`` key can be repeated for several items.
    """
    spec: dict = {"gold": 0, "crystal": 0, "items": {}, "uses": 1, "days": 0, "code": ""}
    tokens = re.split(r"\s+(?=[^\s=]+=)", normalize(text).strip())
    for token in tokens:
        key, sep, value = token.partition("=")
        key = KEYS.get(key.strip().lower())
        if not sep or key is None:
            raise GameError(f"«{token[:30]}» را نفهمیدم. نمونه: سکه=5000 کریستال=10 آیتم=سنگ آهن*5 تعداد=100 روز=7")
        value = value.strip()
        if key == "code":
            spec["code"] = value.upper()
        elif key == "item":
            name, _, qty = value.partition("*")
            item = find_item(name)
            if item is None:
                raise GameError(f"آیتم «{name.strip()[:20]}» پیدا نشد؛ نام دقیق فارسی را بنویسید.")
            amount = _number(qty or "1", "تعداد آیتم")
            if not 1 <= amount <= MAX_QTY:
                raise GameError(f"تعداد آیتم باید بین ۱ تا {fa(MAX_QTY)} باشد.")
            spec["items"][item.id] = spec["items"].get(item.id, 0) + amount
        else:
            spec[key] = _number(value, key)
    return spec


def _number(text: str, what: str) -> int:
    digits = normalize(text).replace(",", "").replace("٬", "")
    if not digits.isdigit():
        raise GameError(f"«{what}» باید یک عدد باشد.")
    return int(digits)


class GiftCodeService:
    def __init__(self, ctx: AppContext, inventory: InventoryService) -> None:
        self.ctx = ctx
        self.inventory = inventory

    def _row(self, r) -> GiftCode:  # noqa: ANN001 - Row
        return GiftCode(
            r["code"], r["gold"], r["crystal"], json.loads(r["items"] or "{}"), r["max_uses"], r["used"], r["expires_at"],
            bool(r["active"]),
        )

    async def create(self, admin_id: int, spec: dict) -> GiftCode:
        """Make a code from :func:`parse_spec`'s result. A missing code name is drawn at random."""
        gold, crystal, items = spec["gold"], spec["crystal"], spec["items"]
        if not (gold or crystal or items):
            raise GameError("کد هدیه باید دست‌کم یک جایزه داشته باشد (سکه، کریستال یا آیتم).")
        if gold > MAX_GOLD or crystal > MAX_CRYSTAL:
            raise GameError(f"حداکثر {fa(MAX_GOLD)} سکه و {fa(MAX_CRYSTAL)} کریستال برای هر کد.")
        if not 1 <= spec["uses"] <= MAX_USES:
            raise GameError(f"تعداد بار استفاده باید بین ۱ تا {fa(MAX_USES)} باشد.")
        if spec["days"] > MAX_DAYS:
            raise GameError(f"مهلت حداکثر {fa(MAX_DAYS)} روز است.")
        now = self.ctx.now()
        code = spec["code"] or "".join(secrets.choice(ALPHABET) for _ in range(8))
        if not CODE_RE.match(code):
            raise GameError("نام کد باید ۴ تا ۲۰ حرف انگلیسی، عدد یا خط‌تیره باشد؛ مثلاً EID1405.")
        expires = now + spec["days"] * 86400 if spec["days"] else 0
        async with self.ctx.db.transaction() as tx:
            if await tx.scalar("SELECT 1 FROM gift_codes WHERE code = ?", (code,), 0):
                raise GameError("این کد از قبل وجود دارد؛ نام دیگری بگذارید.")
            await tx.execute(
                "INSERT INTO gift_codes (code, gold, crystal, items, max_uses, used, expires_at, active, created_by, created_at)"
                " VALUES (?, ?, ?, ?, ?, 0, ?, 1, ?, ?)",
                (code, gold, crystal, json.dumps(items), spec["uses"], expires, admin_id, now),
            )
            await tx.execute(
                "INSERT INTO admin_log (admin_id, action, detail, created_at) VALUES (?, 'gift_code', ?, ?)",
                (admin_id, f"{code} gold={gold} crystal={crystal} items={items} uses={spec['uses']}", now),
            )
        return GiftCode(code, gold, crystal, items, spec["uses"], 0, expires, True)

    async def get(self, code: str) -> GiftCode | None:
        async with self.ctx.db.read() as tx:
            row = await tx.fetchone("SELECT * FROM gift_codes WHERE code = ?", (normalize(code).upper(),))
        return self._row(row) if row else None

    async def recent(self, limit: int = 8, offset: int = 0) -> tuple[list[GiftCode], int]:
        async with self.ctx.db.read() as tx:
            rows = await tx.fetchall(
                "SELECT * FROM gift_codes ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?", (limit, offset)
            )
            total = int(await tx.scalar("SELECT COUNT(*) FROM gift_codes", (), 0))
        return [self._row(r) for r in rows], total

    async def set_active(self, admin_id: int, code: str, active: bool) -> GiftCode:
        async with self.ctx.db.transaction() as tx:
            await tx.execute("UPDATE gift_codes SET active = ? WHERE code = ?", (1 if active else 0, code))
            if tx.rowcount != 1:
                raise GameError("این کد پیدا نشد.")
            row = await tx.fetchone("SELECT * FROM gift_codes WHERE code = ?", (code,))
            await tx.execute(
                "INSERT INTO admin_log (admin_id, action, detail, created_at) VALUES (?, 'gift_code', ?, ?)",
                (admin_id, f"{code} {'on' if active else 'off'}", self.ctx.now()),
            )
        return self._row(row)

    async def redeem(self, player: Player, raw: str) -> GiftCode:
        """Claim a code, once per hero; safe against double taps and against many heroes racing for the last use."""
        code = normalize(raw).strip().upper()
        if not CODE_RE.match(code):
            raise GameError("این کد درست نیست؛ کد را همان‌طور که دارید بنویسید (حرف و عدد انگلیسی).")
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM gift_codes WHERE code = ?", (code,))
            if row is None or not row["active"]:
                raise GameError("چنین کدی وجود ندارد یا غیرفعال شده است.")
            if row["expires_at"] and row["expires_at"] <= now:
                raise GameError("مهلت این کد تمام شده است.")
            if await tx.scalar("SELECT 1 FROM gift_code_uses WHERE code = ? AND player_id = ?", (code, player.id), 0):
                raise GameError("شما این کد را قبلاً فعال کرده‌اید.")
            await tx.execute("UPDATE gift_codes SET used = used + 1 WHERE code = ? AND used < max_uses", (code,))
            if tx.rowcount != 1:
                raise GameError("ظرفیت این کد تمام شده است؛ دیر رسیدید!")
            await tx.execute("INSERT INTO gift_code_uses (code, player_id, used_at) VALUES (?, ?, ?)", (code, player.id, now))
            found = self._row(row)
            if found.gold or found.crystal:
                await wallet.apply(
                    tx, player.id, gold=found.gold, crystal=found.crystal, reason="gift_code", now=now,
                    ref=f"giftcode:{code}:{player.id}",
                )
            for item_id, qty in found.items.items():
                await self.inventory.grant(tx, player.id, item_id, qty)
        found.used += 1
        return found
