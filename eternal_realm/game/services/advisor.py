"""Smart suggestions: what to do next, worked out from the hero's real situation (not a random tip)."""

from __future__ import annotations

from dataclasses import dataclass

from ...context import AppContext
from ...shared.text import fa
from ..data import solo as data
from ..models import Player
from .achievements import AchievementService
from .city import CityService
from .inventory import InventoryService
from .missions import MissionService
from .solo import SoloService
from .wheel import WheelService

DAY = 86400


@dataclass
class Suggestion:
    emoji: str
    text: str
    screen: str
    arg: str = ""


class AdvisorService:
    def __init__(
        self, ctx: AppContext, solo: SoloService, achievements: AchievementService, missions: MissionService,
        wheel: WheelService, city: CityService, inventory: InventoryService,
    ) -> None:
        self.ctx = ctx
        self.solo = solo
        self.achievements = achievements
        self.missions = missions
        self.wheel = wheel
        self.city = city
        self.inventory = inventory

    async def for_player(self, player: Player, limit: int = 3) -> list[Suggestion]:
        now = self.ctx.now()
        out: list[Suggestion] = []
        if await self.solo.active(player.id) is not None:
            out.append(Suggestion("⚔️", "نبردی نیمه‌کاره دارید؛ تمامش کنید", "sfight"))
        claimable = await self.achievements.claimable_count(player)
        if claimable:
            out.append(Suggestion("🏅", f"{fa(claimable)} دستاورد آماده‌ی دریافت پاداش است", "ach"))
        if await self.wheel.free_ready(player.id):
            out.append(Suggestion("🎡", "چرخش رایگان امروز گردونه شانس را نگرفته‌اید", "wheel"))
        if any(m.done and not m.claimed for m in await self.missions.today(player)):
            out.append(Suggestion("📅", "پاداش مأموریتی آماده‌ی دریافت است", "missions"))
        if player.daily_at and now - player.daily_at > 3 * DAY:
            out.append(Suggestion("🎁", "چند روز نبوده‌اید؛ جایزه‌ی بازگشت را از جایزه‌ی روزانه بردارید", "daily"))
        recent = await self.solo.recent_results(player.id, 3)
        if len(recent) == 3 and all(r != "won" for r in recent):
            out.append(Suggestion("🥊", "چند شکست پشت‌سرهم داشتید؛ در میدان بات‌ها سطح تازه‌کار گرم شوید", "arenago", "easy"))
        progress = await self.solo.overview(player.id)
        cleared = progress.get("story", 0)
        if cleared < len(data.STAGES):
            stage = data.get_stage(cleared + 1)
            if player.level >= data.CHAPTERS[stage.chapter][2]:
                tag = "مأموریت آموزشی" if player.level < 5 else "داستان"
                out.append(Suggestion("📖", f"{tag}: مرحله‌ی {fa(stage.number)}، {stage.title}", "stage", str(stage.number)))
        async with self.ctx.db.read() as tx:
            worn = await tx.scalar("SELECT COUNT(*) FROM arms_equipped WHERE player_id = ?", (player.id,), 0)
        if worn < min(2, player.level):
            out.append(Suggestion("⚔️", "جایگاه‌های تجهیزات جنگی‌تان خالی است؛ قطعه‌ای بگذارید", "arms"))
        for boss in reversed(data.SOLO_BOSSES):
            if player.level >= boss.min_level and not progress.get(f"today:boss:{boss.foe}", 0):
                out.append(Suggestion("🐉", f"قدرتتان به باس «{data.get_foe(boss.foe).name}» می‌رسد؛ امروز پاداش اولش را بگیرید", "sbossv", boss.foe))
                break
        city = await self.city.mine(player, visit=False)
        if city is not None and not city.builds:
            out.append(Suggestion("🏗️", "سازندگان شهر بیکارند؛ ساختمانی را ارتقا دهید", "citybuild"))
        async with self.ctx.db.read() as tx:
            in_clan = await tx.scalar("SELECT 1 FROM clan_members WHERE player_id = ?", (player.id,), 0)
        if in_clan:
            out.append(Suggestion("🏯", "با خاندانتان در لیگ هفتگی امتیاز بگیرید", "clanwar"))
        return out[:limit]
