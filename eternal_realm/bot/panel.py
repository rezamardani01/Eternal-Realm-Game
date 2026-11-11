"""The personal panel: every screen is a message with glass buttons that edits itself in place.

A tap carries the owner's Bale id (``PanelCb.o``). The server compares it with the person who
tapped, so a panel opened in a group can only be used by its owner.
Screens double as actions: tapping «پوشیدن» runs the action and re-renders the piece screen.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace

from baleropy import Button, F, Router
from baleropy.exceptions import BaleAPIError, BaleForbidden, BaleNetworkError, SkipHandler
from baleropy.fsm import FSMContext, State, StatesGroup
from baleropy.types import CallbackQuery, InlineKeyboardButton, Message
from baleropy.types.markup import _build_inline_markup

from ..game import item_info
from ..game.data.chests import CHESTS
from ..game.data.items import GEAR_KINDS, Item, Kind, get_item, item_value
from ..game.data.stats import STAT_HELP, STAT_LABELS
from ..game.models import Player
from ..game.services.inventory import InventoryView, Piece
from ..game.services.shop import shop_items
from ..shared.errors import GameError
from ..shared.text import bar, bold, duration, fa, headline, to_int
from . import keyboards, views
from ..game.data.packs import PACKS
from .callbacks import BuyCb, PanelCb
from .services import Services

log = logging.getLogger("eternal_realm.panel")
Rows = list[list[InlineKeyboardButton]]
PER_PAGE = 6


class ListingFlow(StatesGroup):
    waiting = State()


@dataclass
class Screen:
    #: ``None`` = do not touch the message, just show the toast
    text: str | None
    rows: Rows = field(default_factory=list)
    toast: str | None = None
    alert: bool = False
    #: show the screen as a picture (a Bale file id) with the text as its caption
    photo: str | None = None


@dataclass
class Ctx:
    services: Services
    player: Player
    owner: int
    a: str
    b: str
    is_group: bool
    chat_id: int = 0
    state: FSMContext | None = None
    message: Message | None = None
    #: a progress frame has taken the buttons off the message (so a failure must give them back)
    dimmed: bool = False
    #: where the way back leads when a screen fails halfway
    recover_to: str = "home"

    def btn(self, label: str, screen: str, a: object = "", b: object = "", style: str | None = None):
        data = PanelCb(s=screen, a=str(a) or None, b=str(b) or None, o=self.owner)
        return Button.inline(label, data, style=style)

    def back(self, screen: str, label: str = "🔙 بازگشت", a: object = "", b: object = "") -> list:
        return [self.btn(label, screen, a, b)]

    def who(self, player: Player) -> str:
        return player.mention if self.is_group else player.name

    async def show(self, text: str) -> None:
        """A progress frame: replaces the panel text and removes the buttons (no double taps)."""
        if self.message is not None:
            self.dimmed = True
            with contextlib.suppress(BaleAPIError, BaleNetworkError):
                await self.message.edit_text(headline(text))
            await self.services.ctx.pause()

    async def refresh(self) -> Player:
        self.player = await self.services.players.require(self.player.platform_user_id)
        return self.player


ScreenFn = Callable[[Ctx], Awaitable[Screen]]
SCREENS: dict[str, ScreenFn] = {}


def screen(name: str) -> Callable[[ScreenFn], ScreenFn]:
    def register(fn: ScreenFn) -> ScreenFn:
        SCREENS[name] = fn
        return fn

    return register


def _page(seq: list, page: int, per: int = PER_PAGE) -> tuple[list, bool, bool]:
    page = max(0, page)
    chunk = seq[page * per : (page + 1) * per]
    return chunk, page > 0, (page + 1) * per < len(seq)


def _nav(c: Ctx, name: str, page: int, has_prev: bool, has_next: bool, b: object = "") -> list:
    row = []
    if has_prev:
        row.append(c.btn("‹ قبلی", name, page - 1, b))
    if has_next:
        row.append(c.btn("بعدی ›", name, page + 1, b))
    return row


def _int(text: str, what: str = "شماره") -> int:
    value = to_int(text)
    if value is None:
        raise GameError(f"{what} نامعتبر است؛ دوباره از منو شروع کنید.")
    return value


# --- home -------------------------------------------------------------------------------------
@screen("fight")
async def fight_menu(c: Ctx) -> Screen:
    if c.is_group:
        return await home(c)
    text = "\n".join([
        f"⚔️ {bold('نبرد و چالش')}",
        "",
        "تنها به دل خطر بروید، داستان بخوانید یا در تالارها نامتان را بر سنگ بکوبید.",
        "دوئل و باس و مبارزه‌ی تیمی را با دوستان در گروه انجام می‌دهید.",
        "",
        "کدام؟ 👇",
    ])
    rows = [
        [c.btn("🕳️ سیاه‌چال", "dungeon"), c.btn("📜 داستان‌ها", "quests")],
        [c.btn("🏆 تالار بزرگان", "top"), c.btn("🏁 مسابقات", "contests")],
        [c.btn("⚔️ راهنمای مبارزه در گروه", "fighthelp")],
        c.back("home"),
    ]
    return Screen(text, rows)


@screen("trade")
async def trade_menu(c: Ctx) -> Screen:
    if c.is_group:
        return await home(c)
    p = await c.refresh()
    text = "\n".join([
        f"🛒 {bold('بازار و تجارت')}",
        "",
        f"🪙 {fa(p.gold)} سکه · 💎 {fa(p.crystal)} کریستال",
        "",
        "بخرید، بفروشید، سکه و کریستال را مبادله کنید یا سلاح افسانه‌ای بسازید 👇",
    ])
    rows = [
        [c.btn("🛒 فروشگاه آیتم", "shop"), c.btn("🏪 بازارچه", "market")],
        [c.btn("🏦 مرکز مبادله", "exch"), c.btn("🔥 کوره آهنگری", "craft")],
        c.back("home"),
    ]
    return Screen(text, rows)


@screen("fighthelp")
async def fight_help(c: Ctx) -> Screen:
    text = "\n".join([
        f"⚔️ {bold('راهنمای مبارزه')}",
        "",
        "این‌ها در گروه انجام می‌شوند 👇",
        "",
        "🗡️ دوئل: روی پیام حریف ریپلای کنید و بنویسید «مبارزه»",
        "🎰 دوئل شرطی: بنویسید «مبارزه شرطی» و سر سکه، کریستال یا آیتم شرط ببندید",
        "👥 مبارزه‌ی تیمی: بنویسید «مبارزه تیمی»، جایگاه‌ها را پر کنید و سازنده شروع می‌کند",
        "🐉 باس گروهی: بنویسید «احضار باس» و با دوستانتان بزنیدش",
        "🕳️ سیاه‌چال گروهی: بنویسید «سیاه‌چال گروهی»",
        "💰 انتقال: روی پیام کسی ریپلای کنید و بنویسید «انتقال»",
    ])
    return Screen(text, [c.back("home")])


@screen("noop")
async def noop(c: Ctx) -> Screen:
    """A button that only decorates or explains: nothing happens when it is tapped."""
    return Screen(None)


def _greeting(now: int) -> str:
    """A greeting for the hour of the day in Tehran."""
    hour = (now + 12600) % 86400 // 3600
    if 5 <= hour < 11:
        return "صبح قلمرو به‌خیر"
    if 11 <= hour < 16:
        return "آفتاب قلمرو بلند است"
    if 16 <= hour < 20:
        return "غروب قلمرو به‌خیر"
    return "شب قلمرو آرام"


@screen("home")
async def home(c: Ctx) -> Screen:
    p = c.player
    top, need = c.services.characters.max_energy(p), c.services.characters.xp_needed(p)
    text = (
        f"🏰 {_greeting(c.services.ctx.now())}، فرمانده {c.who(p) if c.is_group else bold(p.name)}!\n"
        f"سطح {fa(p.level)} · {p.race.name} · {p.char_class.name}\n\n"
        f"⭐ تجربه تا سطح بعد: {fa(p.xp)} / {fa(need)}\n{bar(p.xp, need)}\n"
        f"⚡ انرژی: {fa(p.energy)} / {fa(top)}\n{bar(p.energy, top)}\n"
        f"🪙 {fa(p.gold)} سکه · 💎 {fa(p.crystal)} کریستال\n\n"
        "دروازه‌های قلمرو باز است؛ امروز پرچمتان را کجا می‌کوبید؟"
    )
    if c.is_group:  # a short menu in groups: play and fight here, manage things in the private chat
        rows = [
            [c.btn("👤 قهرمان من", "profile"), c.btn("⚔️ مبارزه", "fighthelp")],
            [c.btn("😴 استراحت", "rest")],
        ]
        if c.services.bot_username:
            rows.append(keyboards.open_panel_button(c.services.bot_username))
        return Screen(text, rows)
    rows = [
        [c.btn("🗺️ ماجراجویی", "adv", style="primary"), c.btn("🧭 سفر قهرمان", "trip", style="primary")],
        [c.btn("👤 قهرمان من", "profile"), c.btn("🏰 فرمانروایی", "city")],
        [c.btn("⚔️ نبرد و چالش", "fight"), c.btn("🛒 بازار و تجارت", "trade")],
        [c.btn("🏯 خاندان", "clan"), c.btn("💎 خزانه قلمرو", "premium")],
        [c.btn("🎁 جایزه روزانه", "daily"), c.btn("😴 استراحت", "rest")],
        [c.btn("❓ راهنمایی", "help"), c.btn("🤝 دعوت از دوستان", "invite", style="success")],
    ]
    shown = await c.services.admin.links()
    links = [Button.url(shown[key]["text"], shown[key]["url"]) for key in ("group", "channel") if shown[key]["url"]]
    if links:
        rows.append(links)
    return Screen(text, rows)


@screen("boss")
async def boss_panel(c: Ctx) -> Screen:
    b = c.services.ctx.balance
    if not c.is_group:
        return Screen(f"🐉 {bold('باس گروهی')}\n\nباس را در یک گروه احضار کنید و با دوستانتان بزنیدش!", [c.back("home")])
    if await c.services.bosses.active(c.chat_id) is not None:
        return Screen(None, toast="🐉 یک باس زنده است! پیامش را بالاتر ببینید یا «باس» را بنویسید.", alert=True)
    owed = await c.services.bosses.revenge_boss(c.chat_id)
    lines = [f"🐉 {bold('احضار باس')}", ""]
    if owed:
        lines += [f"🔥 {bold('فرصت انتقام!')}", f"{owed.emoji} {owed.name} از شما پیروز شد؛ این بار همان باس می‌آید، خشمگین‌تر و با پاداش ۱٫۵ برابر.", ""]
    lines += [
        f"💰 هزینه: {bold(fa(b.boss_summon_gold))} سکه",
        f"🎚️ از سطح {fa(b.boss_min_level)}",
        f"⏳ هر گروه هر {duration(b.boss_cooldown_seconds)} یک باس",
        "",
        "همه می‌پیوندند، نبرد خودکار است و پاداش به نسبت سهم هر نفر تقسیم می‌شود.",
        "",
        "احضار کنیم؟",
    ]
    text = "\n".join(lines)
    return Screen(text, [[c.btn("🐉 احضار", "bsummon", style="danger"), c.btn("↩️ نه", "home")]])


@screen("bsummon")
async def boss_summon(c: Ctx) -> Screen:
    from . import boss as boss_ui

    view = await c.services.bosses.summon(c.player, c.chat_id)
    if c.message is not None:
        await boss_ui.post(c.message, c.services, view)
    return Screen(f"🐉 {bold('باس احضار شد')}\n\nپیامش را در پایین ببینید 👇", [c.back("home")])


@screen("help")
async def help_(c: Ctx) -> Screen:
    pages = views.help_pages(c.services.ctx.balance)
    rows = keyboards.grid([c.btn(label, "helpsec", key) for key, (label, _) in pages.items()], 2)
    rows.append([c.btn("📖 همه‌ی دستورها", "helpsec", "all")])
    rows.append(c.back("home"))
    return Screen(views.help_hub(), rows)


@screen("helpsec")
async def help_section(c: Ctx) -> Screen:
    from .commands import REGISTRY

    if c.a == "all":
        return Screen(views.command_help(REGISTRY, c.is_group), [c.back("help")])
    pages = views.help_pages(c.services.ctx.balance)
    if c.a not in pages:
        raise GameError("این بخش راهنما پیدا نشد.")
    return Screen(pages[c.a][1], [c.back("help")])


@screen("daily")
async def daily(c: Ctx) -> Screen:
    reward = await c.services.players.claim_daily(c.player.id)
    await c.refresh()
    shown = await home(c)
    note = views.streak_note(reward)
    shown.toast, shown.alert = f"🎁 {fa(reward.gold)} سکه به گنجینه‌ی شما آمد" + (f"\n\n{note}" if note else ""), True
    return shown


@screen("rest")
async def rest(c: Ctx) -> Screen:
    restored = await c.services.activities.rest(c.player.id)
    await c.refresh()
    shown = await home(c)
    shown.toast, shown.alert = f"🔥 کنار آتش نشستید و {fa(restored)} انرژی گرفتید", True
    return shown


# --- profile ----------------------------------------------------------------------------------
@screen("profile")
async def profile(c: Ctx) -> Screen:
    """Your own character, or (with ``a`` = a player id) somebody else's, always with glass buttons."""
    me = c.player
    target = me
    if c.a and _int(c.a) != me.id:
        other = await c.services.players.get(_int(c.a))
        if other is None:
            raise GameError("این قهرمان پیدا نشد.")
        target = other
    stats = await c.services.characters.stats(target)
    top = c.services.characters.max_energy(target)

    def fmt(key: str) -> str:
        return f"{STAT_LABELS[key]} {fa(getattr(stats, key))}"

    sheet = "\n".join([
        f"❤️ جان {fa(stats.hp)} · ⚡ انرژی {fa(target.energy)}/{fa(top)}",
        f"{fmt('atk')} · {fmt('defense')}",
        f"{fmt('magic')} · {fmt('speed')} · {fmt('luck')}",
    ])
    rows = []
    if target is me and c.is_group:
        rows.append([c.btn("🏰 قلمرو من", "home")])
        if c.services.bot_username:
            rows.append(keyboards.open_panel_button(c.services.bot_username))
    elif target is me:
        rows += [
            [c.btn("🎒 کوله‌پشتی", "inv"), c.btn("🧰 تجهیزات", "gear")],
            [c.btn("🐾 یار همراه", "pets"), c.btn("🃏 آلبوم کارت", "album")],
            [c.btn("✨ ارتقای قهرمان", "ascend"), c.btn("🎟️ مسیر قهرمانی", "path")],
            [c.btn("📅 مأموریت‌ها", "missions"), c.btn("🏅 دستاوردها", "ach")],
            [c.btn("🕯️ محراب", "altar")],
            c.back("home"),
        ]
    elif c.b == "cm":
        rows.append(c.back("clanmember", "🔙 بازگشت به عضو خاندان", target.id))
    else:
        rows.append([c.btn("🏰 قلمرو من", "home")])
    header = views.profile_header(target, c.services.characters.xp_needed(target), c.services.ctx.now())
    return Screen(f"{header}\n{views.LINE}\n{sheet}", rows)


@screen("stat")
async def stat(c: Ctx) -> Screen:
    return Screen(None, toast=STAT_HELP.get(c.a, "این ویژگی را در بازی ببینید."), alert=True)


# --- adventure --------------------------------------------------------------------------------
@screen("adv")
async def adventure(c: Ctx) -> Screen:
    if c.is_group:
        return Screen(None)  # the adventure panel is private; in a group only the activity words work
    from ..game.data.activities import ACTIVITIES

    buttons = [c.btn(f"{a.emoji} {a.title} · {fa(a.energy)}⚡", "act", a.id) for a in ACTIVITIES.values()]
    rows = [[c.btn("🐺 شکار هیولا · ۱۰⚡", "act", "hunt", style="danger")]]
    rows += keyboards.grid(buttons, 2)
    rows.append(c.back("home", "🔙 بازگشت"))
    p = await c.refresh()
    text = (
        f"🗺️ {bold('ماجراجویی')}\n\n"
        f"⚡ انرژی شما: {fa(p.energy)}\n\n"
        "کارهای آرام سکه، تجربه و منابع می‌دهند. شکار سخت‌تر است ولی پاداش بیشتری دارد.\n\n"
        "کجا می‌روید؟ 👇"
    )
    return Screen(text, rows)


NOTES = {
    "gold": "🪙 سکه‌هایی که همین الان گرفتید. در فروشگاه خرجشان کنید.",
    "xp": "⭐ تجربه‌ای که گرفتید. با پر شدنش یک سطح بالاتر می‌روید.",
    "crystal": "💎 کریستال ناب؛ ارز کمیاب قلمرو.",
    "energy": "⚡ انرژی باقی‌مانده. با گذر زمان، استراحت یا معجون پر می‌شود.",
    "hp": "❤️ جانی که در پایان نبرد برایتان مانده بود. جان بعد از نبرد خودبه‌خود پر می‌شود.",
}


@screen("note")
async def note(c: Ctx) -> Screen:
    if c.a == "item":
        item = get_item(c.b)
        text = f"{item.label}: " + "، ".join(_describe(item))
    else:
        text = NOTES.get(c.a, "این هم از غنیمت‌های شما.")
    return Screen(None, toast=text, alert=True)


@screen("act")
async def act(c: Ctx) -> Screen:
    services, p = c.services, c.player
    if c.a == "hunt":
        hunted = await services.hunting.hunt(p.id, c.chat_id if c.is_group else None)
        for frame in views.hunt_frames(c.who(p), hunted):
            await c.show(frame)
        text = views.hunt_result(c.who(p), hunted)
        rows = keyboards.result_rows(
            c.owner, gold=hunted.gold, xp=hunted.xp, items=hunted.items, energy=hunted.player.energy,
            again="hunt", hp=(hunted.hero_hp, hunted.hero_max_hp), wait=hunted.next_in,
        )
        return Screen(text, rows)
    else:
        done = await services.activities.perform(p.id, c.a, c.chat_id if c.is_group else None)
        for frame in views.activity_frames(c.who(p), done.activity):
            await c.show(frame)
        text = views.activity_result(c.who(p), done)
        rows = keyboards.result_rows(
            c.owner, gold=done.rolled.gold, xp=done.rolled.xp, crystal=done.rolled.crystal, items=done.items,
            energy=done.player.energy, again=c.a, wait=done.next_in,
        )
        return Screen(text, rows)


# --- backpack ---------------------------------------------------------------------------------
def _split(view: InventoryView) -> tuple[list[tuple[Item, int]], list[tuple[Item, int]]]:
    chests = [(i, q) for i, q in view.stacks if i.kind is Kind.CHEST]
    others = [(i, q) for i, q in view.stacks if i.kind is not Kind.CHEST]
    return others, chests


@screen("inv")
async def inventory(c: Ctx) -> Screen:
    view = await c.services.inventory.view(c.player.id)
    others, chests = _split(view)
    worn = sum(1 for p in view.gear if p.slot)
    text = (
        f"🎒 {bold('کوله‌پشتی')}\n\n"
        f"⚔️ تجهیزات: {fa(len(view.gear))} ({fa(worn)} پوشیده)\n"
        f"📦 آیتم‌ها: {fa(sum(q for _, q in others))}\n"
        f"🎁 صندوقچه‌ها: {fa(sum(q for _, q in chests))}\n\n"
        "یک بخش را انتخاب کنید 👇"
    )
    rows = [
        [c.btn("⚔️ تجهیزات", "gear"), c.btn("📦 آیتم‌ها", "items")],
        [c.btn("🎁 صندوقچه‌ها", "chests")],
        c.back("profile", "🔙 بازگشت"),
    ]
    return Screen(text, rows)


@screen("gear")
async def gear(c: Ctx) -> Screen:
    view = await c.services.inventory.view(c.player.id)
    pieces = sorted(view.gear, key=lambda p: (p.slot is None, p.id))
    if not pieces:
        text = f"⚔️ {bold('تجهیزات')}\n\nهنوز تجهیزاتی ندارید. از «فروشگاه» بخرید یا از هیولاها غنیمت بگیرید."
        return Screen(text, [[c.btn("🛒 فروشگاه", "shop")], c.back("inv")])
    page = _int(c.a or "0", "صفحه")
    chunk, prev, nxt = _page(pieces, page)
    rows = [[c.btn(f"{p.label}{' ✅' if p.slot else ''}", "piece", p.id)] for p in chunk]
    if nav := _nav(c, "gear", page, prev, nxt):
        rows.append(nav)
    rows.append(c.back("inv"))
    return Screen(f"⚔️ {bold('تجهیزات')}\n✅ یعنی پوشیده است. یکی را انتخاب کنید 👇", rows)


async def _piece(c: Ctx, gear_id: int) -> Piece:
    view = await c.services.inventory.view(c.player.id)
    for p in view.gear:
        if p.id == gear_id:
            return p
    raise GameError("این تجهیزات دیگر در کوله‌پشتی شما نیست.")


def _sell_price(piece: Piece) -> int:
    return round(piece.item.sell * (1 + 0.5 * piece.upgrade)) if piece.item.sell > 0 else 0


async def _piece_screen(c: Ctx, gear_id: int, toast: str | None = None) -> Screen:
    p = await _piece(c, gear_id)
    lines = [
        f"{p.item.emoji} {bold(p.item.name + (f' +{fa(p.upgrade)}' if p.upgrade else ''))}",
        f"{p.item.rarity_label} · سطح لازم {fa(p.item.level_req)}",
        "",
        *p.stats.bonus_lines(),
    ]
    if p.slot:
        lines += ["", "✅ الان بر تن شماست"]
    if p.item.slot == "weapon":
        from ..game.data.sets import BOND_NAMES, BOND_STEPS

        level = p.bond
        nxt = f" · تا سطح بعد {fa(BOND_STEPS[level] - p.bond_uses)} نبرد" if level < len(BOND_STEPS) else " · به اوج رسیده"
        lines += ["", f"🔗 پیوند با صاحب: {BOND_NAMES[level]} ({fa(level)}){nxt}"]
        if level:
            lines.append(f"هر نبرد سلاح را به شما نزدیک‌تر می‌کند؛ الان {fa(5 * level)}٪ توان سلاح بیشتر می‌دهد.")
    set_lines = await c.services.inventory.set_lines(c.player.id, p.item.id)
    if set_lines:
        lines += ["", *set_lines]
    lines += item_info.info_lines(p.item)
    if p.origin:
        lines += ["", "📜 تاریخچه‌ی این تجهیزات", *p.origin.split("\n")]
    rows = [[c.btn("↩️ درآوردن" if p.slot else "🛡️ پوشیدن", "unequip" if p.slot else "equip", p.id,
                   style=None if p.slot else "success")]]
    second = [c.btn("🔨 ارتقا", "upq", p.id)]
    if not p.slot and (price := _sell_price(p)):
        second.append(c.btn(f"💰 فروش {fa(price)}🪙", "sellq", p.id))
    rows.append(second)
    if not p.slot and p.item.tradable:
        rows.append([c.btn("🏷️ عرضه در بازار", "listask", "g", p.id)])
    rows.append(c.back("gear", "🔙 بازگشت"))
    return Screen("\n".join(lines), rows, toast=toast)


@screen("piece")
async def piece(c: Ctx) -> Screen:
    return await _piece_screen(c, _int(c.a))


@screen("equip")
async def equip(c: Ctx) -> Screen:
    worn, replaced = await c.services.inventory.equip(c.player, _int(c.a))
    note = f" و {replaced.item.name} را کنار گذاشتید" if replaced else ""
    return await _piece_screen(c, worn.id, f"🛡️ {worn.item.name} را پوشیدید{note}")


@screen("unequip")
async def unequip(c: Ctx) -> Screen:
    taken = await c.services.inventory.unequip(c.player, _int(c.a))
    return await _piece_screen(c, taken.id, f"↩️ {taken.item.name} را درآوردید")


@screen("sellq")
async def sell_confirm(c: Ctx) -> Screen:
    p = await _piece(c, _int(c.a))
    text = f"💰 {bold('فروش به بازارچه')}\n\n{p.label} را می‌فروشید و {bold(fa(_sell_price(p)))} سکه می‌گیرید.\nمطمئنید؟"
    return Screen(text, [[c.btn("✅ بله، بفروش", "sell", p.id, style="danger"), c.btn("↩️ نه", "piece", p.id)]])


@screen("sell")
async def sell_gear(c: Ctx) -> Screen:
    sold, total = await c.services.shop.sell_gear(c.player, _int(c.a))
    shown = await gear(replace(c, a="0", b=""))  # «a» held the gear id, not a page number
    shown.toast = f"💰 {sold.item.name} فروخته شد: {fa(total)} سکه"
    return shown


@screen("upq")
async def upgrade_ask(c: Ctx) -> Screen:
    p, quote = await c.services.shop.quote(c.player, _int(c.a))
    rows = [[c.btn(f"🔨 ارتقا به +{fa(quote.next_level)}", "up", p.id, quote.next_level, style="success")],
            c.back("piece", "🔙 بازگشت", p.id)]
    return Screen(views.upgrade_quote(p, quote), rows)


@screen("up")
async def upgrade(c: Ctx) -> Screen:
    result = await c.services.shop.upgrade(c.player, _int(c.a), _int(c.b))
    await c.show(views.upgrade_working())
    rows = [[c.btn("🔨 دوباره ارتقا", "upq", result.piece.id)], c.back("piece", "🔙 بازگشت", result.piece.id)]
    return Screen(views.upgrade_result(result), rows,
                  toast="✨ ارتقا موفق بود" if result.success else "💥 این بار نشد")


# --- items and chests -------------------------------------------------------------------------
def _describe(item: Item) -> list[str]:
    """What the item does (its stats, if any), then what it is used for and where it comes from."""
    if item.kind is Kind.CONSUMABLE:
        head = [f"⚡ {fa(item.energy)} انرژی بازمی‌گرداند"]
    elif item.kind is Kind.CHEST:
        head = ["🎁 درونش گنجی پنهان است"]
    elif item.is_gear:
        head = item.stats.bonus_lines()
    else:
        head = ["📦 منبع"]
    return head + item_info.info_lines(item)


async def _stack_qty(c: Ctx, item_id: str) -> int:
    view = await c.services.inventory.view(c.player.id)
    return next((q for i, q in view.stacks if i.id == item_id), 0)


@screen("items")
async def items(c: Ctx) -> Screen:
    view = await c.services.inventory.view(c.player.id)
    others, _ = _split(view)
    if not others:
        text = f"📦 {bold('آیتم‌ها')}\n\nهنوز آیتمی ندارید. ماجراجویی کنید و کوله‌تان را پر کنید!"
        return Screen(text, [[c.btn("🗺️ ماجراجویی", "adv")], c.back("inv")])
    page = _int(c.a or "0", "صفحه")
    chunk, prev, nxt = _page(others, page)
    rows = [[c.btn(f"{i.label} ×{fa(q)}", "item", i.id)] for i, q in chunk]
    if nav := _nav(c, "items", page, prev, nxt):
        rows.append(nav)
    rows.append(c.back("inv"))
    return Screen(f"📦 {bold('آیتم‌ها')}\nیکی را انتخاب کنید 👇", rows)


async def _item_screen(c: Ctx, item_id: str, toast: str | None = None) -> Screen:
    item = get_item(item_id)
    qty = await _stack_qty(c, item_id)
    if qty <= 0:
        first_page = replace(c, a="0", b="")  # «a» held the item id, not a page number
        shown = await (chests(first_page) if item.kind is Kind.CHEST else items(first_page))
        shown.toast = toast
        return shown
    lines = [f"{item.emoji} {bold(item.name)}", f"{item.rarity_label} · در کوله‌پشتی: {bold(fa(qty))}", "", *_describe(item)]
    if item.kind is Kind.CHEST and item.id in CHESTS:
        lines += ["", views.chest_contents(item, c.services.chests.odds(CHESTS[item.id]))]
    if item.sell > 0:
        lines.append(f"💰 بها در بازارچه: {fa(item.sell)} سکه")
    rows: Rows = []
    if item.kind is Kind.CONSUMABLE:
        rows.append([c.btn("🧪 مصرف", "use", item.id, style="success")])
    if item.kind is Kind.CHEST:
        rows.append([c.btn("🗝️ باز کردن", "open", item.id, style="success")])
    if item.sell > 0:
        sell_row = [c.btn("💰 فروش ۱", "isellq", item.id, "1")]
        if qty > 1:
            sell_row.append(c.btn(f"💰 فروش همه ({fa(qty)})", "isellq", item.id, "all"))
        rows.append(sell_row)
    if item.tradable:
        rows.append([c.btn("🏷️ عرضه در بازار", "lqty", item.id)])
    rows.append(c.back("chests" if item.kind is Kind.CHEST else "items", "🔙 بازگشت"))
    return Screen("\n".join(lines), rows, toast=toast)


@screen("item")
async def item_detail(c: Ctx) -> Screen:
    return await _item_screen(c, c.a)


@screen("use")
async def use(c: Ctx) -> Screen:
    message = await c.services.inventory.use(c.player, get_item(c.a))
    return await _item_screen(c, c.a, message)


@screen("isellq")
async def item_sell_ask(c: Ctx) -> Screen:
    item = get_item(c.a)
    have = await _stack_qty(c, item.id)
    qty = have if c.b == "all" else 1
    if qty <= 0 or item.sell <= 0:
        raise GameError("این آیتم را نمی‌شود به بازارچه فروخت.")
    total = item.sell * qty
    text = (
        f"💰 {bold('تأیید فروش به بازارچه')}\n\n"
        f"{item.label} ×{fa(qty)}\n\n"
        f"بها: {fa(item.sell)} سکه برای هر عدد\n\n"
        f"دریافتی شما: {bold(fa(total))} سکه\n\n"
        f"کیسه‌ی شما: {fa(c.player.gold)} ← {fa(c.player.gold + total)} سکه\n\n"
        "مطمئنید می‌فروشید؟"
    )
    return Screen(text, [[c.btn("✅ بله، بفروش", "isell", item.id, c.b, style="danger"), c.btn("↩️ نه", "item", item.id)]])


@screen("isell")
async def item_sell(c: Ctx) -> Screen:
    item = get_item(c.a)
    qty = await _stack_qty(c, item.id) if c.b == "all" else 1
    total = await c.services.shop.sell_stack(c.player, item, qty)
    return await _item_screen(c, item.id, f"💰 {item.name} ×{fa(qty)} فروخته شد: {fa(total)} سکه")


@screen("odds")
async def odds(c: Ctx) -> Screen:
    item = get_item(c.a)
    if item.id not in CHESTS:
        raise GameError("این صندوقچه شناخته نشد.")
    text = views.chest_odds(item, c.services.chests.odds(CHESTS[item.id]))
    if c.b == "p":
        return Screen(text, [c.back("prem", "🔙 بازگشت", "chests")])
    return Screen(text, [c.back("item", "🔙 بازگشت", item.id)])


@screen("open")
async def open_chest(c: Ctx) -> Screen:
    item = get_item(c.a)
    opened = await c.services.chests.open(c.player, item)
    await c.show(views.chest_opening(item))
    left = await _stack_qty(c, item.id)
    rows = []
    if left:
        rows.append([c.btn(f"🗝️ باز کردن دوباره ({fa(left)})", "open", item.id, style="success")])
    rows.append(c.back("chests", "🔙 بازگشت"))
    return Screen(views.chest_opened(c.player.name, opened), rows)


@screen("chests")
async def chests(c: Ctx) -> Screen:
    view = await c.services.inventory.view(c.player.id)
    _, owned = _split(view)
    rows = [[c.btn(f"{i.label} ×{fa(q)}", "item", i.id)] for i, q in owned]
    rows.append([c.btn("🛍️ خرید صندوقچه", "chestshop", style="success")])
    rows.append(c.back("inv"))
    text = f"🎁 {bold('صندوقچه‌ها')}\n" + (
        "یکی را بزنید تا باز کنید 👇" if owned else "هنوز صندوقچه‌ای ندارید. می‌توانید بخرید یا در ماجراجویی پیدا کنید!"
    )
    return Screen(text, rows)


@screen("chestshop")
async def chest_shop(c: Ctx) -> Screen:
    p = await c.refresh()
    rows = []
    for chest in CHESTS.values():
        if chest.price is None:
            continue
        icon = "🪙" if chest.price[0] == "gold" else "💎"
        item = get_item(chest.item_id)
        rows.append([c.btn(f"{item.label} — {fa(chest.price[1])}{icon}", "cbuyq", item.id)])
    rows.append(c.back("chests"))
    text = (
        f"🛍️ {bold('خرید صندوقچه')}\n🪙 {fa(p.gold)} · 💎 {fa(p.crystal)}\n\n"
        "شانس محتویات هر صندوقچه با دکمه‌ی «شانس‌ها» دیده می‌شود."
    )
    return Screen(text, rows)


@screen("cbuy")
async def chest_buy(c: Ctx) -> Screen:
    item = get_item(c.a)
    currency, total = await c.services.chests.buy(c.player, item.id, 1)
    icon = "🪙" if currency == "gold" else "💎"
    text = f"✅ {bold('صندوقچه خریده شد')}\n{item.label} به کوله‌پشتی شما رسید ({fa(total)}{icon})."
    rows = [
        [c.btn("🗝️ باز کردن", "open", item.id, style="success")],
        [c.btn("🛍️ خرید دیگر", "chestshop")],
        c.back("chests", "🔙 بازگشت"),
    ]
    return Screen(text, rows, toast="✅ صندوقچه شما شد")


# --- shop -------------------------------------------------------------------------------------
@screen("shop")
async def shop(c: Ctx) -> Screen:
    p = await c.refresh()
    text = f"🛒 {bold('فروشگاه')}\n«بفرمایید فرمانده!»\n\n🪙 سکه‌ی شما: {fa(p.gold)}"
    rows = [
        [c.btn("⚔️ سلاح و زره", "shopcat", "gear"), c.btn("🧪 معجون‌ها", "shopcat", "pot")],
        [c.btn("🎁 صندوقچه‌ها", "chestshop"), c.btn("💰 فروش آیتم‌ها", "items")],
        c.back("trade", "🔙 بازگشت"),
    ]
    return Screen(text, rows)


@screen("shopcat")
async def shop_category(c: Ctx) -> Screen:
    want_gear = c.a == "gear"
    goods = [i for i in shop_items() if i.is_gear == want_gear]
    page = _int(c.b or "0", "صفحه")
    chunk, prev, nxt = _page(goods, page)
    owned = {p_.item.id for p_ in (await c.services.inventory.view(c.player.id)).gear} if want_gear else set()
    rows = [  # two columns: the item, then its price (or «owned»); both open the item
        [c.btn(i.label, "shopitem", i.id, c.a), c.btn("دارید ✔" if i.id in owned else f"🪙 {fa(i.buy)}", "shopitem", i.id, c.a)]
        for i in chunk
    ]
    # paging keeps the category in `a` and the page in `b`
    nav = ([c.btn("‹ قبلی", "shopcat", c.a, page - 1)] if prev else []) + (
        [c.btn("بعدی ›", "shopcat", c.a, page + 1)] if nxt else []
    )
    if nav:
        rows.append(nav)
    rows.append(c.back("shop"))
    title = "⚔️ سلاح و زره" if want_gear else "🧪 معجون‌ها"
    return Screen(f"{title.split(' ', 1)[0]} {bold(title.split(' ', 1)[1])}\nیکی را انتخاب کنید 👇", rows)


async def _shop_item_screen(c: Ctx, item_id: str, cat: str, toast: str | None = None) -> Screen:
    item = get_item(item_id)
    p = await c.refresh()
    lines = [f"{item.emoji} {bold(item.name)}", item.rarity_label, "", *_describe(item)]
    if item.is_gear and item.level_req > 1:
        lines.append(f"🎚️ سطح لازم: {fa(item.level_req)}")
    lines += ["", f"🪙 بها: {bold(fa(item.buy))} سکه", f"کیسه‌ی شما: {fa(p.gold)} سکه"]
    owned = item.is_gear and any(p_.item.id == item.id for p_ in (await c.services.inventory.view(p.id)).gear)
    if owned:
        lines += ["", "✅ این تجهیزات را از قبل دارید؛ خرید دوباره لازم نیست."]
        rows = []
    elif item.is_gear:
        rows = [[c.btn("🛍️ خرید", "buyq", item.id, "1", style="success")]]
    else:
        rows = [[c.btn(f"🛍️ ×{fa(n)}", "buyq", item.id, str(n), style="success") for n in (1, 5, 10)]]
    rows.append(c.back("shopcat", "🔙 بازگشت", cat))
    return Screen("\n".join(lines), rows, toast=toast)


@screen("shopitem")
async def shop_item(c: Ctx) -> Screen:
    return await _shop_item_screen(c, c.a, c.b or "gear")


async def _confirm(
    c: Ctx, what: str, currency: str, total: int, action: str, a: str, b: str, back: tuple[str, str, str],
    extra: str = "",
) -> Screen:
    """«Are you sure?» step before spending gold or crystals."""
    p = await c.refresh()
    icon = "🪙" if currency == "gold" else "💎"
    have = p.gold if currency == "gold" else p.crystal
    undo = c.btn("↩️ نه، برگرد", back[0], back[1], back[2])
    if have < total:
        text = (
            f"💸 {bold('موجودی کافی نیست')}\n\n{what}\n"
            f"بها: {fa(total)} {icon}\nموجودی شما: {fa(have)} {icon}\nکمبود: {bold(fa(total - have))} {icon}"
            + (f"\n\n{extra}" if extra else "")
        )
        return Screen(text, [[undo]])
    text = (
        f"🛍️ {bold('تأیید خرید')}\n\n{what}\nبها: {bold(fa(total))} {icon}\n"
        f"موجودی شما: {fa(have)} {icon} ← پس از خرید {fa(have - total)} {icon}\n\n"
        + (f"{extra}\n\n" if extra else "")
        + "مطمئنید می‌خواهید بخرید؟"
    )
    return Screen(text, [[c.btn("✅ بله، بخر", action, a, b, style="success"), undo]])


@screen("buyq")
async def buy_confirm(c: Ctx) -> Screen:
    item, qty = get_item(c.a), _int(c.b)
    if item.buy <= 0:
        raise GameError("این کالا در بازارچه فروخته نمی‌شود.")
    cat = "gear" if item.is_gear else "pot"
    if item.is_gear and any(p_.item.id == item.id for p_ in (await c.services.inventory.view(c.player.id)).gear):
        raise GameError(f"شما از قبل {item.label} را دارید؛ خرید دوباره لازم نیست.")
    return await _confirm(c, f"{item.label} ×{fa(qty)}", "gold", item.buy * qty, "buy", item.id, str(qty),
                          ("shopitem", item.id, cat))


@screen("cbuyq")
async def chest_confirm(c: Ctx) -> Screen:
    item = get_item(c.a)
    chest = CHESTS.get(item.id)
    if chest is None or chest.price is None:
        raise GameError("این صندوقچه فروشی نیست.")
    currency, unit = chest.price
    contents = views.chest_contents(item, c.services.chests.odds(chest))
    back = ("prem", "chests", "") if c.b == "p" else ("chestshop", "", "")
    return await _confirm(c, item.label, currency, unit, "cbuy", item.id, "", back, contents)


@screen("buy")
async def buy(c: Ctx) -> Screen:
    item, qty = get_item(c.a), _int(c.b)
    paid = await c.services.shop.buy(c.player, item, qty)
    cat = "gear" if item.is_gear else "pot"
    return await _shop_item_screen(c, item.id, cat, f"🛍️ {item.name} ×{fa(qty)} خریدید ({fa(paid)} سکه)")


# --- market -----------------------------------------------------------------------------------
MARKET_TABS = {
    "all": ("🧺 همه", None),
    "gear": ("⚔️ سلاح و زره", GEAR_KINDS),
    "pot": ("🧪 معجون", {Kind.CONSUMABLE}),
    "mat": ("📦 منابع", {Kind.MATERIAL}),
    "chest": ("🎁 صندوقچه", {Kind.CHEST}),
}
MARKET_SORTS = {
    "new": "🆕 جدیدترین",
    "cheap": "💰 ارزان‌ترین",
    "expensive": "💎 گران‌ترین",
    "rare": "🌟 کمیاب‌ترین",
}


def _tab_sort(c: Ctx) -> tuple[str, str]:
    """The market keeps «category.sort» in the second argument, e.g. ``gear.cheap``."""
    tab, _, sort = (c.b or "").partition(".")
    return (tab if tab in MARKET_TABS else "all"), (sort if sort in MARKET_SORTS else "new")


async def _market_first_page(c: Ctx) -> Screen:
    """The market list from its first page; ``c.a`` of the caller is a listing id, not a page."""
    return await market(replace(c, a="0", b=""))


@screen("market")
async def market(c: Ctx) -> Screen:
    page = _int(c.a or "0", "صفحه")
    tab, sort = _tab_sort(c)
    found, nxt = await c.services.market.page(MARKET_TABS[tab][1], sort, page, PER_PAGE)
    head = f"🏪 {bold('بازار')}\nدسته: {MARKET_TABS[tab][0]} · مرتب‌سازی: {MARKET_SORTS[sort]}"
    if found:
        text = f"{head}\n\nآگهی بازیکنان از همه‌ی گروه‌ها؛ یکی را انتخاب کنید 👇"
    else:
        text = f"{head}\n\nدر این دسته آگهی فعالی نیست. شما می‌توانید اولین فروشنده باشید!"
    rows = [[
        c.btn(f"📂 دسته: {MARKET_TABS[tab][0].split(' ', 1)[1]}", "mcat", 0, f"{tab}.{sort}"),
        c.btn(f"🔎 فیلتر: {MARKET_SORTS[sort].split(' ', 1)[1]}", "mfilter", 0, f"{tab}.{sort}"),
    ]]
    if not found:
        rows.append([c.btn("🚫 هیچ آیتمی برای خرید وجود ندارد", "market", 0, f"{tab}.{sort}")])
    rows += [
        [c.btn(f"{lst.label} {lst.item.rarity_label.split(' ')[0]} — {fa(lst.price)}🪙", "listing", lst.id)]
        for lst in found
    ]
    if nav := _nav(c, "market", page, page > 0, nxt, f"{tab}.{sort}"):
        rows.append(nav)
    rows.append([c.btn("🏷️ فروش کالای من", "msell", style="success"), c.btn("📋 آگهی‌های من", "mine")])
    rows.append(c.back("trade"))
    return Screen(text, rows)


async def _tick_screen(c: Ctx, title: str, blurb: str, options: dict[str, str], current: str, action: str) -> Screen:
    """A list of options with a tick on the chosen one; tapping one applies it and stays here."""
    tab, sort = _tab_sort(c)
    rows = []
    for key, label in options.items():
        mark = "✅ " if key == current else "⬜ "
        value = f"{key}.{sort}" if action == "mcat" else f"{tab}.{key}"
        rows.append([c.btn(mark + label.split(" ", 1)[1], action, 0, value)])
    rows.append([c.btn("🏪 نمایش آگهی‌ها", "market", 0, f"{tab}.{sort}", style="primary")])
    return Screen(f"{title}\n\n{blurb}", rows)


@screen("mcat")
async def market_category(c: Ctx) -> Screen:
    tab, _ = _tab_sort(c)
    labels = {k: label for k, (label, _) in MARKET_TABS.items()}
    return await _tick_screen(
        c, f"📂 {bold('دسته‌ی کالا')}", "نوع کالاهایی را که می‌خواهید ببینید تیک بزنید، بعد «نمایش آگهی‌ها».",
        labels, tab, "mcat",
    )


@screen("mfilter")
async def market_filter(c: Ctx) -> Screen:
    _, sort = _tab_sort(c)
    return await _tick_screen(
        c, f"🔎 {bold('فیلتر و ترتیب')}", "ترتیب نمایش آگهی‌ها را تیک بزنید، بعد «نمایش آگهی‌ها».",
        dict(MARKET_SORTS), sort, "mfilter",
    )


@screen("msell")
async def market_sell(c: Ctx) -> Screen:
    """Pick what to sell: every tradable piece and stack you own, one button each."""
    view = await c.services.inventory.view(c.player.id)
    entries = [(p.label, "listask", "g", str(p.id)) for p in view.gear if p.slot is None and p.item.tradable]
    entries += [(f"{i.label} ×{fa(q)}", "lqty", i.id, "") for i, q in view.stacks if i.tradable]
    if not entries:
        text = f"🏷️ {bold('فروش کالای من')}\n\nچیزی برای فروش ندارید. تجهیزات پوشیده را اول درآورید."
        return Screen(text, [c.back("market")])
    page = _int(c.a or "0", "صفحه")
    chunk, prev, nxt = _page(entries, page)
    rows = [[c.btn(label, screen_, a, b)] for label, screen_, a, b in chunk]
    if nav := _nav(c, "msell", page, prev, nxt):
        rows.append(nav)
    rows.append(c.back("market"))
    text = f"🏷️ {bold('فروش کالای من')}\n\nکالایی را که می‌خواهید بفروشید انتخاب کنید؛ قیمت را خودتان تعیین می‌کنید 👇"
    return Screen(text, rows)


@screen("lqty")
async def market_quantity(c: Ctx) -> Screen:
    item = get_item(c.a)
    have = await _stack_qty(c, item.id)
    if have <= 0:
        raise GameError("این آیتم دیگر در کوله‌پشتی شما نیست.")
    options = sorted({n for n in (1, 5, 10, 50, have) if n <= have})
    buttons = [c.btn("همه (" + fa(n) + ")" if n == have and n > 1 else f"×{fa(n)}", "listask", "s", f"{item.id}.{n}") for n in options]
    rows = keyboards.grid(buttons, 3) + [c.back("msell")]
    text = f"🏷️ {bold('چند عدد؟')}\n\n{item.label}\nدر کوله‌پشتی شما: {fa(have)} عدد\n\nتعداد فروش را انتخاب کنید 👇"
    return Screen(text, rows)


@screen("mine")
async def mine(c: Ctx) -> Screen:
    mine_ = await c.services.market.mine(c.player)
    rows = [[c.btn(f"{lst.label} — {fa(lst.price)}🪙", "listing", lst.id)] for lst in mine_]
    rows.append(c.back("market"))
    text = f"📋 {bold('آگهی‌های من')}\n" + ("یکی را بزنید تا لغو کنید 👇" if mine_ else "آگهی فعالی ندارید.")
    return Screen(text, rows)


@screen("listing")
async def listing(c: Ctx) -> Screen:
    lst = await c.services.market.get(_int(c.a))
    if lst is None:
        shown = await _market_first_page(c)
        shown.toast = "این آگهی دیگر روی تخته نیست"
        return shown
    own = lst.seller_id == c.player.id
    lines = [
        f"{lst.item.emoji} {bold(lst.item.name + (f' +{fa(lst.upgrade)}' if lst.upgrade else ''))}",
        f"{lst.item.rarity_label}" + (f" · تعداد {fa(lst.qty)}" if lst.qty > 1 else ""),
        "",
        *_describe(lst.item),
        "",
        f"💰 بها: {bold(fa(lst.price))} سکه",
        f"👤 فروشنده: {lst.seller_name}",
    ]
    rows = (
        [[c.btn("↩️ لغو آگهی", "mcancel", lst.id, style="danger")]]
        if own
        else [[c.btn(f"🛍️ خرید با {fa(lst.price)}🪙", "mbuyq", lst.id, style="success")]]
    )
    rows.append(c.back("market"))
    return Screen("\n".join(lines), rows)


@screen("mbuyq")
async def market_buy_ask(c: Ctx) -> Screen:
    lst = await c.services.market.get(_int(c.a))
    if lst is None:
        shown = await _market_first_page(c)
        shown.toast = "این آگهی دیگر روی تخته نیست"
        return shown
    what = f"{lst.label}" + (f" ×{fa(lst.qty)}" if lst.qty > 1 else "") + f"\nفروشنده: {lst.seller_name}"
    return await _confirm(c, what, "gold", lst.price, "mbuy", str(lst.id), "", ("listing", str(lst.id), ""))


@screen("mbuy")
async def market_buy(c: Ctx) -> Screen:
    bought = await c.services.market.buy(c.player, _int(c.a))
    shown = await _market_first_page(c)
    done = f"✅ {bold('خرید موفق')}\n{bought.item.label} از آن شماست. آگهی‌های دیگر را ببینید 👇"
    shown.text = f"{done}\n\n{shown.text}"
    shown.toast = f"🛍️ معامله مبارک! {bought.item.name} از آن شماست"
    return shown


@screen("lconfirm")
async def listing_confirm(c: Ctx) -> Screen:
    """Create the listing the player just priced."""
    ref, _, price_text = c.b.rpartition("~")
    price = _int(price_text)
    if c.a == "g":
        made = await c.services.market.list_gear(c.player, _int(ref), price)
    else:
        item_id, _, qty = ref.partition(".")
        made = await c.services.market.list_stack(c.player, get_item(item_id), _int(qty), price)
    fee = c.services.market.fee_for(made.price)
    text = (
        f"🏷️ {bold('آگهی شما نصب شد')}\n\n{made.label}\nبها: {fa(made.price)} سکه\n\n"
        "💡 همه‌ی بازیکنان در هر گروهی آن را در بازار می‌بینند.\n\n"
        f"کارمزد بازار ({fa(fee)} سکه) هنگام فروش کسر می‌شود."
    )
    return Screen(text, [[c.btn("🏪 بازار", "market"), c.btn("📋 آگهی‌های من", "mine")], c.back("home")])


@screen("mcancel")
async def market_cancel(c: Ctx) -> Screen:
    done = await c.services.market.cancel(c.player, _int(c.a))
    shown = await mine(c)
    shown.toast = f"↩️ آگهی لغو شد و {done.item.name} برگشت"
    return shown


@screen("listask")
async def listing_ask(c: Ctx) -> Screen:
    if c.state is None:
        raise GameError("برای عرضه در بازار از «فروش کالای من» در بازار شروع کنید.")
    kind, ref = c.a, c.b
    if kind == "g":
        piece_ = await _piece(c, _int(ref))
        what, back = piece_.label, c.btn("❌ انصراف", "piece", piece_.id)
        low, high = c.services.market.price_range(piece_.item, 1, piece_.upgrade)
    else:
        item_id, _, qty = ref.partition(".")
        item = get_item(item_id)
        what, back = f"{item.label} ×{fa(_int(qty))}", c.btn("❌ انصراف", "lqty", item.id)
        low, high = c.services.market.price_range(item, _int(qty))
    await c.state.set_state(ListingFlow.waiting)
    await c.state.update_data(kind=kind, ref=ref)
    text = (
        f"🏷️ {bold('قیمت فروش')}\n\n{what}\n\n"
        f"قیمت کل را به سکه بنویسید و بفرستید.\nمجاز: {fa(low)} تا {fa(high)} سکه (۵۰٪ تا ۱۲۰٪ ارزش واقعی)\n\n"
        "پس از ثبت، آگهی شما برای همه‌ی بازیکنان در هر گروهی دیده می‌شود."
    )
    return Screen(text, [[back]])


# --- rankings and premium ---------------------------------------------------------------------
@screen("top")
async def top(c: Ctx) -> Screen:
    board_id = c.a or ("group" if c.is_group else "level")
    bracket = c.b or "all"
    ranking = c.services.rankings
    group_only = ("group", "hero", "history")
    if board_id in group_only and not c.is_group:
        board_id = "level"
    if board_id == "history":
        text = views.battle_history(await ranking.battle_history(c.chat_id))
    else:
        if board_id == "group":
            board = await ranking.group_board(c.chat_id)
        elif board_id == "hero":
            board = await ranking.hero_of_the_week(c.chat_id)
        elif board_id == "bosses":
            board = await ranking.boss_hunters(c.player)
        elif board_id == "path":
            board = await ranking.path_board(c.player)
        else:
            board = await ranking.global_board(board_id, c.player, bracket=bracket)
        text = views.ranking(board, mentions=c.is_group)
    from ..game.services.rankings import BRACKETS, BOARDS

    brackets = []
    if board_id in BOARDS:  # the four global boards can be narrowed to heroes of a similar level
        brackets = [
            [c.btn(("✔️ " if bracket == key else "") + label, "top", board_id, key) for key, (label, _, _) in BRACKETS.items()]
        ]
    rows = [
        [c.btn("🏆 سطح", "top", "level", bracket), c.btn("💰 ثروت", "top", "rich", bracket)],
        [c.btn("⚔️ دوئل", "top", "wins", bracket), c.btn("🏅 لیگ", "top", "rating", bracket)],
        *brackets,
        [c.btn("🎟️ مسیر قهرمانی", "top", "path"), c.btn("🐉 شکارچیان باس", "top", "bosses")],
        [c.btn("🏁 مسابقات", "contests")],
    ]
    if c.is_group:
        rows.append([c.btn("🏰 این گروه", "top", "group"), c.btn("🌟 قهرمان هفته", "top", "hero")])
        rows.append([c.btn("📜 تاریخچه‌ی نبردها", "top", "history")])
    else:
        rows.append(c.back("fight", "🔙 بازگشت"))
    return Screen(text, rows)


CHEST_BLURB = {
    "wooden_chest": "سکه، منابع و معجون",
    "magic_chest": "سکه، کریستال و تجهیزات خوب",
    "royal_chest": "گنج‌های بزرگ و تجهیزات افسانه‌ای",
}
PREMIUM_SECTIONS = {
    "coins": ("🪙", "خرید سکه", "با سکه تجهیزات و معجون می‌خرید و سلاح‌هایتان را ارتقا می‌دهید."),
    "crystals": ("💎", "خرید کریستال", "کریستال ارز کمیاب قلمرو است؛ با آن صندوقچه‌های جادویی و سلطنتی می‌خرید."),
    "bundles": ("🎁", "خرید بسته", "چند چیز با هم و به‌صرفه‌تر."),
    "materials": ("⛓️", "خرید منابع", "سنگ آهن برای ارتقای تجهیزات؛ هر مرتبه‌ی آهنگری به آن نیاز دارد."),
    "services": ("🎫", "خدمات قهرمان", "تغییر نام، نژاد یا کلاس قهرمان؛ بعد از خرید از «قهرمان من ← ارتقای قهرمان ← خدمات» مصرفش کنید."),
    "vip": ("💠", "اشتراک VIP", "راحتی بیشتر برای ۳۰ روز، بدون هیچ قدرت رزمی."),
    "path": ("🎟️", "بلیط مسیر قهرمانی", "جایزه‌های ویژه‌ی ۱۰۰ مرحله‌ی این فصل را باز می‌کند. کاملاً اختیاری است؛ جایزه‌های رایگان برای همه هست."),
    "pets": ("🐱", "حیوان خانگی", "یار وفاداری که در نبردها کنارتان می‌ماند و قدرتتان را بیشتر می‌کند."),
    "boost": ("🚀", "بوست دو برابر", "تا پایان بوست، دریافتی‌هایتان دو برابر می‌شود."),
    "city": ("🏰", "منابع فرمانروایی", "سکه، غذا، چوب، سنگ و آهن برای شهرتان؛ مستقیم به انبار شهر می‌رسد و ساخت‌وساز، ارتقا و لشکرسازی را سریع‌تر می‌کند."),
    "xp": ("⭐", "بسته‌های تجربه", "سریع‌تر سطح بالا بروید و زودتر به آیتم‌ها و مرحله‌های تازه برسید."),
}
BUY_HINT = "👇 یک بسته را بزنید؛ فاکتور پرداخت بله برایتان می‌آید"


@screen("premium")
async def premium(c: Ctx) -> Screen:
    if c.is_group:
        username = c.services.bot_username
        rows = [keyboards.start_button(username)] if username else []
        return Screen("💎 خزانه قلمرو فقط در پیام خصوصی باز می‌شود؛ خرید آن‌جا امن است.", rows)
    p = await c.refresh()
    text = "\n".join([
        f"💎 {bold('خزانه قلمرو')}",
        "",
        "هر چه برای پیشرفت سریع‌تر لازم دارید.",
        "",
        f"🪙 سکه: {bold(fa(p.gold))}",
        f"💎 کریستال: {bold(fa(p.crystal))}",
        "",
        "💳 پرداخت با کیف پول بله؛ اطلاعات کارت ذخیره نمی‌شود",
        "",
        "👇 یک بخش را انتخاب کنید",
    ])
    rows = [
        [c.btn("🎡 گردونه شانس", "wheel", style="success")],
        [c.btn("🪙 خرید سکه", "prem", "coins"), c.btn("💎 خرید کریستال", "prem", "crystals")],
        [c.btn("🎁 خرید بسته", "prem", "bundles"), c.btn("📦 خرید صندوق", "prem", "chests")],
        [c.btn("⛓️ خرید منابع", "prem", "materials"), c.btn("🐱 حیوان خانگی", "prem", "pets")],
        [c.btn("🎫 خدمات قهرمان", "prem", "services"), c.btn("🎟️ مسیر قهرمانی", "prem", "path")],
        [c.btn("🚀 بوست دو برابر", "prem", "boost", style="primary"), c.btn("⭐ بسته‌های تجربه", "prem", "xp", style="primary")],
        [c.btn("💠 اشتراک VIP", "vip"), c.btn("🏰 منابع فرمانروایی", "prem", "city")],
        [c.btn("🏷️ تخفیف‌های امروز", "deals", style="success")],
        c.back("home"),
    ]
    return Screen(text, rows)


def _lucky_block(c: Ctx, lines: list[str]) -> list:
    from ..game.data import lucky

    theme = lucky.theme_of_day(c.services.ctx.now())
    if lines and lines[-1] != "":
        lines.append("")
    lines += [
        f"🎲 {bold('بسته‌های شانسی امروز')}",
        f"{theme.emoji} تم امروز: {theme.name} (فردا عوض می‌شود)",
        "🪙 هر بسته سکه‌ی تضمینی دارد و چند جایزه‌ی تصادفی از همین تم",
        "",
    ]
    rows = []
    packs = [x for x in PACKS.values() if x.lucky]
    for pack in packs:
        tier = lucky.TIERS[pack.id]
        lines += [f"🎲 {bold(pack.title)} · {fa(pack.price_toman)} تومان", f"🪙 {fa(tier.guaranteed_gold)} سکه + {fa(tier.rolls)} جایزه", ""]
        rows.append([Button.inline(f"{pack.label} — {fa(pack.price_toman)} تومان", BuyCb(kind="cash", id=pack.id), style="success")])
    if lines and lines[-1] == "":
        lines.pop()
    rows.append([c.btn("🎲 شانس‌های امروز", "luckyodds")])
    return rows


@screen("deals")
async def deals(c: Ctx) -> Screen:
    from ..game.data.deals import daily_deals, seconds_left

    if c.is_group:
        return await premium(c)
    now = c.services.ctx.now()
    if not c.services.ctx.settings.payments_enabled:
        return Screen("🏷️ خرید با پول واقعی فعلاً بسته است.", [c.back("premium")])
    todays = daily_deals(now)
    rows = [
        [Button.inline(f"{d.pack.label} · {fa(d.price_toman)} تومان · {fa(d.percent)}٪-", BuyCb(kind="deal", id=d.pack.id), style="success")]
        for d in todays
    ]
    rows.append(c.back("premium"))
    return Screen(views.deals_text(todays, seconds_left(now)), rows)


@screen("luckyodds")
async def lucky_odds(c: Ctx) -> Screen:
    from ..game.data import lucky

    return Screen(views.lucky_odds(lucky.theme_of_day(c.services.ctx.now())), [c.back("prem", "🔙 بازگشت", "bundles")])


def _boost_or_xp_section(c: Ctx, p) -> Screen:  # noqa: ANN001 - Player
    """The two sections that sell speed: the 2x boost, and experience packs sized by the buyer's own level."""
    from ..game.engine import progression

    now = c.services.ctx.now()
    balance = c.services.ctx.balance
    enabled = c.services.ctx.settings.payments_enabled
    emoji, title, blurb = PREMIUM_SECTIONS[c.a]
    lines = [f"{emoji} {bold(title)}", "", blurb, ""]
    rows = []
    packs = [x for x in PACKS.values() if x.section == c.a]
    if c.a == "boost":
        lines += [
            f"📋 {bold('چه چیزهایی دو برابر می‌شود؟')}",
            "🪙 سکه",
            "⭐ تجربه",
            "📦 آیتم‌های ماجراجویی و شکار",
            "🐉 جایزه‌ی باس، دوئل، سیاه‌چال و داستان",
            "📅 جایزه‌ی مأموریت‌ها و جایزه‌ی روزانه",
            "",
            "💎 کریستال دو برابر نمی‌شود",
            "➕ خرید دوباره به زمان باقی‌مانده اضافه می‌شود",
            "",
        ]
        if p.boost_until > now:
            lines += [f"🚀 بوست شما فعال است؛ {duration(p.boost_until - now)} مانده", ""]
        lines.append(f"🛒 {bold('بسته‌ها')}")
        for pack in packs:
            lines.append(f"⏳ {fa(pack.boost_hours)} ساعته · {fa(pack.price_toman)} تومان (ساعتی {fa(round(pack.price_toman / pack.boost_hours))})")
    else:
        lines += [
            f"📋 {bold('چطور کار می‌کند؟')}",
            "📈 هر بسته مقدار ثابتی تجربه می‌دهد",
            "🧙 سطح پایین‌تر یعنی سطح بیشتر؛ سطح بالاتر یعنی کمتر",
            "♾️ هر تعداد و هر زمان که بخواهید می‌توانید بخرید",
            "",
            f"🧙 سطح شما: {bold(fa(p.level))}",
            "",
            f"🛒 {bold('بسته‌ها برای شما')}",
        ]
        for pack in packs:
            level, _, gained = progression.apply_xp(p.level, p.xp, pack.xp, balance)
            result = (
                f"حدود {fa(gained)} سطح (می‌رسید به {fa(level)})" if gained
                else f"حدود {fa(round(100 * pack.xp / progression.xp_needed(p.level, balance)))}٪ از یک سطح"
            )
            lines += [f"{pack.emoji} {pack.title} · {fa(pack.price_toman)} تومان", f"📈 {fa(pack.xp)} تجربه = {result}", ""]
        if lines[-1] == "":
            lines.pop()
    lines.append("")
    if not enabled:
        lines.append("🔒 خرید با پول واقعی فعلاً بسته است")
    else:
        for pack in packs:
            rows.append([Button.inline(f"{pack.label} — {fa(pack.price_toman)} تومان", BuyCb(kind="cash", id=pack.id), style="success")])
        lines.append(BUY_HINT)
    rows.append(c.back("premium"))
    return Screen("\n".join(lines), rows)


@screen("prem")
async def premium_section(c: Ctx) -> Screen:
    if c.is_group:
        return await premium(c)
    p = await c.refresh()
    if c.a == "chests":
        lines = [f"📦 {bold('خرید صندوق')}", "", "در هر صندوقچه گنجی پنهان است؛ با سکه یا کریستال بخرید.", ""]
        rows = []
        for chest in CHESTS.values():
            if chest.price is None:
                continue
            icon = "🪙" if chest.price[0] == "gold" else "💎"
            item = get_item(chest.item_id)
            lines += [f"{item.emoji} {bold(item.name)} · {fa(chest.price[1])} {icon}", f"🎁 {CHEST_BLURB.get(item.id, '')}", ""]
            rows.append([c.btn(f"{item.label} · {fa(chest.price[1])}{icon}", "cbuyq", item.id, "p")])
        lines += [f"🪙 سکه‌ی شما: {fa(p.gold)}", f"💎 کریستال شما: {fa(p.crystal)}", "", "👇 روی هر صندوقچه بزنید تا محتویات و شانس‌هایش را ببینید"]
        rows.append(c.back("premium"))
        return Screen("\n".join(lines), rows)

    if c.a in ("boost", "xp"):
        return _boost_or_xp_section(c, p)
    emoji, title, blurb = PREMIUM_SECTIONS.get(c.a, PREMIUM_SECTIONS["coins"])
    enabled = c.services.ctx.settings.payments_enabled
    lines = [f"{emoji} {bold(title)}", "", blurb, ""]
    rows = []
    if not enabled:
        lines.append("🔒 خرید با پول واقعی فعلاً بسته است؛ با بازی کردن هم می‌توانید به این‌ها برسید!")
    else:
        for pack in (x for x in PACKS.values() if x.section == c.a and not x.lucky):
            if c.a in ("bundles", "city"):  # these hide their contents in the button, so say them here
                lines += [f"{pack.emoji} {bold(pack.title)} · {fa(pack.price_toman)} تومان", f"🎁 {views.pack_description(pack, c.services.ctx.now()).removeprefix('شامل: ')}", ""]
            rows.append([Button.inline(f"{pack.label} — {fa(pack.price_toman)} تومان", BuyCb(kind="cash", id=pack.id), style="success")])
        if c.a == "bundles":
            rows += _lucky_block(c, lines)
            lines.append("")
        lines.append(BUY_HINT)
    rows.append(c.back("premium"))
    return Screen("\n".join(lines), rows)


# --- entry points -----------------------------------------------------------------------------
def _is_group(message: Message) -> bool:
    return str(getattr(message.chat.type, "value", message.chat.type)) != "private"


async def send(
    message: Message, services: Services, player: Player, name: str, a: str = "", b: str = "",
    *, reply: bool = False, state: FSMContext | None = None,
) -> Message:
    """Open a screen as a new message (private /start, or a group command)."""
    ctx = Ctx(services, player, player.platform_user_id, a, b, _is_group(message), message.chat.id, state)
    shown = await SCREENS[name](ctx)
    text = headline(shown.text or "")
    if shown.photo:
        return await message.bot.send_photo(
            message.chat.id, shown.photo, text, message.message_id if reply else None,
            _build_inline_markup(shown.rows) if shown.rows else None,
        )
    if reply:
        return await message.reply(text, buttons=shown.rows or None)
    return await message.answer(text, buttons=shown.rows or None)


async def _show(message: Message, shown: Screen, *, retry: bool = True) -> None:
    """Put a screen on the tapped message: edit in place, or swap the message when text and picture trade places."""
    text, was_photo = headline(shown.text or ""), bool(message.photo)
    try:
        if shown.photo and was_photo:
            await message.edit_caption(text, buttons=shown.rows or None)
        elif shown.photo or was_photo:
            await message.delete()
            if shown.photo:
                await message.bot.send_photo(
                    message.chat.id, shown.photo, text, None, _build_inline_markup(shown.rows) if shown.rows else None
                )
            else:
                await message.answer(text, buttons=shown.rows or None)
        else:
            await message.edit_text(text, buttons=shown.rows or None)
    except (BaleAPIError, BaleNetworkError) as error:
        if "not modified" in str(error).lower():
            return
        if retry and not isinstance(error, BaleForbidden):
            await asyncio.sleep(0.5)  # a hiccup (a network blip, a rate limit): one more try before swapping the message
            return await _show(message, shown, retry=False)
        # the edit failed for a real reason: never leave the player staring at a dead screen, send it as a new message
        log.warning("could not edit a panel message, sending a new one: %s", error)
        with contextlib.suppress(BaleAPIError, BaleNetworkError):
            if shown.photo:
                await message.bot.send_photo(
                    message.chat.id, shown.photo, text, None, _build_inline_markup(shown.rows) if shown.rows else None
                )
            else:
                await message.answer(text, buttons=shown.rows or None)


router = Router(name="panel")


@router.callback_query(PanelCb.filter())
async def on_panel(
    query: CallbackQuery, callback_data: PanelCb, services: Services, state: FSMContext
) -> None:
    if query.from_user.id != callback_data.o:
        await query.answer("این پنل مال شما نیست؛ برای خودتان یکی باز کنید 🙂", show_alert=True)
        return
    message = query.message
    if message is None:
        await query.answer()
        return
    handler = SCREENS.get(callback_data.s)
    if handler is None:
        await query.answer("این دکمه قدیمی است؛ منو را دوباره باز کنید.", show_alert=True)
        return
    await state.clear()  # tapping anything cancels a half-finished text prompt
    player = await services.players.require(query.from_user.id)
    ctx = Ctx(
        services, player, callback_data.o, callback_data.a or "", callback_data.b or "",
        _is_group(message), message.chat.id, state, message,
    )
    try:
        shown = await handler(ctx)
    except Exception as error:
        if ctx.dimmed:  # a progress frame took the buttons away: never leave the player on a dead message
            rescue = Screen("⚠️ لحظه‌ای مشکلی پیش آمد، ولی چیزی از دست نرفت. از دکمه‌ی زیر ادامه بدهید 👇", [ctx.back(ctx.recover_to, "↩️ ادامه")])
            await _show(message, rescue)
        if not isinstance(error, KeyError):
            raise
        shown = None
    if shown is None:
        # a button that names something the game no longer has (an old message, a removed item)
        log.warning("stale panel button %s a=%r b=%r", callback_data.s, callback_data.a, callback_data.b, exc_info=True)
        await query.answer("این دکمه قدیمی است؛ منو را دوباره باز کنید.", show_alert=True)
        return
    if shown.text is not None:
        await _show(message, shown)
    await query.answer((shown.toast or "")[:190] or None, show_alert=shown.alert)


# --- text prompt: price of a market listing ---------------------------------------------------
listing_router = Router(name="listing-flow")


@listing_router.message(ListingFlow.waiting, F.text)
async def got_listing_price(message: Message, state: FSMContext, services: Services) -> None:
    price = to_int((message.text or "").strip())
    if price is None:
        if _is_group(message):
            raise SkipHandler  # ordinary chat or a game word: let the command router see it
        raise GameError("فقط یک عدد بنویسید؛ مثلاً: 5000")
    player = await services.players.require(message.from_user.id)  # type: ignore[union-attr]
    data = await state.get_data()
    kind, ref = str(data.get("kind")), str(data["ref"])
    if kind == "g":
        piece_ = await services.inventory.view(player.id)
        owned = next((p_ for p_ in piece_.gear if p_.id == int(ref)), None)
        what = owned.label if owned else "تجهیزات"
        worth = item_value(owned.item, owned.upgrade) if owned else 0
        if owned:
            services.market._check_price(price, owned.item, 1, owned.upgrade)  # a price outside the fair range is refused here
    else:
        item_id, _, qty = ref.partition(".")
        what = f"{get_item(item_id).label} ×{fa(int(qty))}"
        services.market._check_price(price, get_item(item_id), int(qty))
        worth = item_value(get_item(item_id)) * int(qty)
    await state.clear()  # the price passed the checks above; a refused one keeps the prompt open
    fee = services.market.fee_for(price)
    owner = player.platform_user_id
    lines = [f"🏷️ {bold('تأیید آگهی')}", "", f"📦 {what}", ""]
    if worth:
        lines += [f"💎 ارزش واقعی: {bold(fa(worth))} سکه", f"💰 قیمتی که زدید: {bold(fa(price))} سکه"]
        gap = round(100 * (price - worth) / worth)
        if gap > 0:
            lines.append(f"📈 {fa(gap)}٪ بالاتر از ارزش واقعی")
        elif gap < 0:
            lines.append(f"📉 {fa(-gap)}٪ پایین‌تر از ارزش واقعی")
        else:
            lines.append("✅ برابر ارزش واقعی")
        if price > 2 * worth:
            lines.append("⚠️ قیمت خیلی بالاست؛ احتمال فروش کم است.")
        elif price * 2 < worth:
            lines.append("⚠️ قیمت خیلی پایین است؛ ارزان‌تر از ارزش واقعی می‌فروشید.")
    else:
        lines.append(f"💰 قیمتی که زدید: {bold(fa(price))} سکه")
    lines += [
        "",
        f"🏦 کارمزد بازار: {fa(fee)} سکه (هنگام فروش کسر می‌شود)",
        f"🪙 دریافتی شما پس از فروش: {bold(fa(max(0, price - fee)))} سکه",
        "",
        "این کالا با همین قیمت در «بازارچه» برای همه گذاشته شود؟",
    ]
    await message.reply(
        "\n".join(lines),
        buttons=[
            [
                keyboards.panel_button("✅ بله", "lconfirm", owner, kind, f"{ref}~{price}"),
                keyboards.panel_button("❌ نه", "market", owner),
            ]
        ],
    )


__all__ = ["SCREENS", "Screen", "listing_router", "router", "send"]
