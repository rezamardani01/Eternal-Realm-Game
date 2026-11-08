"""The VIP subscription page: what it gives, how long it lasts, how to buy it."""

from __future__ import annotations

from ..game.data.packs import PACKS
from ..shared.text import bold, duration, fa
from .panel import Ctx, Screen, screen

PERKS = (
    "⏱️ زمان انتظار ماجراجویی و شکار ۲۰٪ کمتر",
    "📅 یک مأموریت روزانه‌ی چهارم",
    "🎟️ ۱۰٪ امتیاز بیشتر در مسیر قهرمانی",
    "💠 نشان VIP در پروفایل",
)


@screen("vip")
async def vip(c: Ctx) -> Screen:
    me = await c.refresh()
    now = c.services.ctx.now()
    pack = PACKS["vip_30"]
    lines = [f"💠 {bold('اشتراک VIP')}", "", "راحتی و سرعت بیشتر، بدون هیچ قدرت رزمی اضافه.", "بازیکن رایگان در رقابت هیچ عقب نمی‌ماند.", ""]
    lines += [f"✨ {bold('امتیازها')}", *PERKS, ""]
    active = me.vip_until > now
    if active:
        lines.append(f"✅ وضعیت: فعال ({duration(me.vip_until - now)} مانده)")
    else:
        lines.append("⛔ وضعیت: غیرفعال")
    lines += [f"💰 قیمت: {fa(pack.price_toman)} تومان برای ۳۰ روز", "➕ تمدید به باقی‌مانده اضافه می‌شود"]
    rows = []
    if c.is_group:
        lines += ["", "📲 خرید فقط در پیام خصوصی ربات انجام می‌شود"]
    else:
        rows.append([c.btn(("🔁 تمدید" if active else "💠 خرید") + f" ({fa(pack.price_toman)} تومان)", "prem", "vip", style="primary")])
    rows.append(c.back("premium" if not c.is_group else "home"))
    return Screen("\n".join(lines), rows)
