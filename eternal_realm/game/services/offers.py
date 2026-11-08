"""The dynamic brain: looks at each player's situation and sends at most one personal suggestion a day."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...db.database import Tx
from ...db.repos import season as season_repo
from ...db.repos import wallet
from ...shared.errors import GameError
from ...shared.text import fa
from ..data.cards import cards_in
from ..data.cards import SETS as CARD_SETS
from ..data.offers import DAILY_CAP, DAY, RULES, Facts, Rule, get_rule
from ..models import Player

ACTIVE_WINDOW = 30 * DAY
RETURN_GIFT = 500
BATCH = 200


@dataclass
class Offer:
    rule: Rule
    text: str


class OfferService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    # --- facts --------------------------------------------------------------------------------------
    async def facts(self, tx: Tx, p: Player) -> Facts:
        now = self.ctx.now()
        last = int(await tx.scalar("SELECT MAX(created_at) FROM transactions WHERE player_id = ?", (p.id,), now))
        owned = {
            r["card_id"] for r in await tx.fetchall("SELECT card_id FROM player_cards WHERE player_id = ?", (p.id,))
        }
        best_ratio, best_name, best_missing = 0.0, "", 0
        for s in CARD_SETS:
            cards = cards_in(s.id)
            have = sum(1 for c in cards if c.id in owned)
            ratio = have / len(cards)
            if ratio < 1.0 and ratio > best_ratio:
                best_ratio, best_name, best_missing = ratio, s.name, len(cards) - have
        pet = await tx.fetchone("SELECT 1 FROM player_pets WHERE player_id = ?", (p.id,))
        clan = await tx.fetchone("SELECT 1 FROM clan_members WHERE player_id = ?", (p.id,))
        st = await season_repo.state(tx, p.id, now)
        return Facts(
            p.level, p.gold, p.crystal, p.wins, p.losses, max(0, (now - last) // DAY), pet is not None,
            clan is not None, bool(p.class2_id), best_ratio, best_name, best_missing, len(st.available()),
            st.tier, st.premium,
        )

    @staticmethod
    def _fill(rule: Rule, f: Facts) -> str:
        return rule.text.format(
            days=fa(f.inactive_days), ready=fa(f.ready_path_rewards), set=f.best_set_name,
            missing=fa(f.best_set_missing), level=fa(f.level), gold=fa(f.gold), tier=fa(f.path_tier),
        )

    # --- choosing ---------------------------------------------------------------------------------------
    async def choose(self, tx: Tx, p: Player) -> Offer | None:
        """The best rule that applies and is allowed by the limits, or ``None``."""
        now = self.ctx.now()
        off = await tx.scalar("SELECT offers_off FROM players WHERE id = ?", (p.id,), 0)
        if off:
            return None
        sent_today = int(await tx.scalar(
            "SELECT COUNT(*) FROM offers_log WHERE player_id = ? AND sent_at >= ?", (p.id, now - DAY), 0
        ))
        if sent_today >= DAILY_CAP:
            return None
        facts = await self.facts(tx, p)
        recent = {
            r["rule_id"]: r["last"] for r in await tx.fetchall(
                "SELECT rule_id, MAX(sent_at) AS last FROM offers_log WHERE player_id = ? GROUP BY rule_id", (p.id,)
            )
        }
        for rule in sorted(RULES, key=lambda r: -r.priority):
            if rule.id in recent and now - recent[rule.id] < rule.cooldown:
                continue
            if rule.check(facts):
                return Offer(rule, self._fill(rule, facts))
        return None

    async def record(self, tx: Tx, player_id: int, rule_id: str) -> None:
        await tx.execute(
            "INSERT INTO offers_log (player_id, rule_id, sent_at) VALUES (?, ?, ?)", (player_id, rule_id, self.ctx.now())
        )

    async def due(self) -> list[tuple[int, Offer]]:
        """Pick offers for recently active players and log them as sent. Returns (telegram-style user id, offer)."""
        now = self.ctx.now()
        out: list[tuple[int, Offer]] = []
        async with self.ctx.db.transaction() as tx:
            rows = await tx.fetchall(
                "SELECT p.id FROM players p WHERE p.banned = 0 AND p.offers_off = 0 AND EXISTS"
                " (SELECT 1 FROM transactions t WHERE t.player_id = p.id AND t.created_at >= ?)"
                " ORDER BY p.id LIMIT ?",
                (now - ACTIVE_WINDOW, BATCH),
            )
            from ...db.repos import players as player_repo

            for r in rows:
                p = await player_repo.get(tx, r["id"])
                if p is None:
                    continue
                offer = await self.choose(tx, p)
                if offer is not None:
                    await self.record(tx, p.id, offer.rule.id)
                    out.append((p.platform_user_id, offer))
        return out

    # --- the player's switch and the comeback gift ----------------------------------------------------------
    async def set_enabled(self, player: Player, enabled: bool) -> None:
        async with self.ctx.db.transaction() as tx:
            await tx.execute("UPDATE players SET offers_off = ? WHERE id = ?", (0 if enabled else 1, player.id))

    async def enabled(self, player: Player) -> bool:
        async with self.ctx.db.read() as tx:
            return not await tx.scalar("SELECT offers_off FROM players WHERE id = ?", (player.id,), 0)

    async def claim_return_gift(self, player: Player) -> int:
        now = self.ctx.now()
        async with self.ctx.db.transaction() as tx:
            row = await tx.fetchone(
                "SELECT MAX(sent_at) AS last FROM offers_log WHERE player_id = ? AND rule_id = 'comeback'", (player.id,)
            )
            if row is None or row["last"] is None:
                raise GameError("هدیه‌ی بازگشتی برای شما در کار نیست.")
            if now - row["last"] > 7 * DAY:
                raise GameError("مهلت این هدیه تمام شده است.")
            try:
                await wallet.apply(
                    tx, player.id, gold=RETURN_GIFT, reason="comeback", now=now,
                    ref=f"comeback:{player.id}:{row['last']}",
                )
            except wallet.DuplicateOperation as exc:
                raise GameError("این هدیه را قبلاً گرفته‌اید.") from exc
        return RETURN_GIFT


__all__ = ["Offer", "OfferService", "get_rule"]
