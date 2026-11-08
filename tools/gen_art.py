"""Renders the small illustrations the bot sends with items, bosses, pets, cards and events.

Developer tool (needs ``pip install pillow`` and the Windows "Segoe UI Emoji" font); the finished files are committed
under ``eternal_realm/assets/art`` so the server needs nothing. Run from the project root::

    python tools/gen_art.py

File names are the stable game ids (``items/wooden_sword.jpg``, ``bosses/beast_fire.jpg`` ...).
"""

from __future__ import annotations

import hashlib
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "eternal_realm" / "assets" / "art"
FONT = "C:/Windows/Fonts/seguiemj.ttf"
BASE = (8, 11, 26)

RARITY = {1: "#9aa3b5", 2: "#3fbf6e", 3: "#3b82f6", 4: "#a855f7", 5: "#f59e0b", 6: "#ef4444"}
ELEMENT = {
    "fire": "#ff5a2a", "ice": "#5bc8ff", "lightning": "#ffd43b", "nature": "#3fbf6e", "water": "#2b7de9",
    "shadow": "#7c3aed", "earth": "#b07a45", "wind": "#7dd3c0", "light": "#fde68a", "poison": "#84cc16",
}
EVENTS = {  # id: (emoji, small emoji, colour)
    "mystery_chest": ("🔐", "🎁", "#f59e0b"),
    "merchant": ("🧳", "💰", "#14b8a6"),
    "double_xp": ("📈", "⭐", "#a855f7"),
    "hidden_boss": ("👹", "💀", "#ef4444"),
}


def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))  # type: ignore[return-value]


_font = ImageFont.truetype(FONT, 109)
_cache: dict[str, Image.Image] = {}


def emoji(ch: str, height: int) -> Image.Image:
    if ch not in _cache:
        canvas = Image.new("RGBA", (500, 300), (0, 0, 0, 0))
        ImageDraw.Draw(canvas).text((200, 60), ch, font=_font, embedded_color=True, anchor="la")
        _cache[ch] = canvas.crop(canvas.getbbox())
    src = _cache[ch]
    width = max(1, round(src.width * height / src.height))
    return src.resize((width, height), Image.LANCZOS)


def paste_center(base: Image.Image, layer: Image.Image, cx: int, cy: int, glow: tuple[int, int, int] | None = None, shadow: bool = True) -> None:
    x, y = cx - layer.width // 2, cy - layer.height // 2
    alpha = layer.getchannel("A")
    if glow:
        halo = Image.new("RGBA", base.size, (0, 0, 0, 0))
        tint = Image.new("RGBA", layer.size, glow + (255,))
        tint.putalpha(alpha.point(lambda v: int(v * 0.9)))
        halo.paste(tint, (x, y), tint)
        halo = halo.filter(ImageFilter.GaussianBlur(base.width // 14))
        base.alpha_composite(halo)
    if shadow:
        dark = Image.new("RGBA", layer.size, (0, 0, 0, 255))
        dark.putalpha(alpha.point(lambda v: int(v * 0.55)))
        sh = Image.new("RGBA", base.size, (0, 0, 0, 0))
        sh.paste(dark, (x + 5, y + 8), dark)
        base.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)))
    base.alpha_composite(layer, (x, y))


def background(size: tuple[int, int], colour: tuple[int, int, int], seed: str, rays: bool = False) -> Image.Image:
    w, h = size
    rnd = random.Random(int(hashlib.md5(seed.encode()).hexdigest()[:8], 16))
    top, bottom = mix(BASE, colour, 0.28), mix(BASE, colour, 0.06)
    img = Image.new("RGB", size, top)
    img.paste(Image.new("RGB", size, bottom), mask=Image.linear_gradient("L").resize(size))
    img = img.convert("RGBA")
    # a soft light behind the subject, placed a little differently for every id
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    cx, cy = int(w * rnd.uniform(0.42, 0.58)), int(h * rnd.uniform(0.40, 0.52))
    ImageDraw.Draw(glow).ellipse((cx - w * 0.38, cy - h * 0.38, cx + w * 0.38, cy + h * 0.38), fill=colour + (120,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(w // 7)))
    if rays:
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        start = rnd.uniform(0, math.pi)
        for k in range(14):
            a = start + k * math.pi / 7
            d.polygon([(cx, cy), (cx + math.cos(a) * w, cy + math.sin(a) * w), (cx + math.cos(a + 0.12) * w, cy + math.sin(a + 0.12) * w)], fill=colour + (34,))
        img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(2)))
    sparks = ImageDraw.Draw(img)
    for _ in range(26):
        x, y, r = rnd.randrange(w), rnd.randrange(h), rnd.choice((1, 1, 2, 2, 3))
        sparks.ellipse((x - r, y - r, x + r, y + r), fill=mix(colour, (255, 255, 255), 0.6) + (rnd.randrange(60, 170),))
    return img


def vignette(img: Image.Image, strength: int = 150) -> None:
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((-w * 0.25, -h * 0.25, w * 1.25, h * 1.25), fill=255)
    mask = ImageChops.invert(mask.filter(ImageFilter.GaussianBlur(w // 6)))
    shade = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    shade.putalpha(mask.point(lambda v: v * strength // 255))
    img.alpha_composite(shade)


def frame(img: Image.Image, colour: tuple[int, int, int], thick: int = 6, glow: bool = False) -> None:
    w, h = img.size
    if glow:
        halo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(halo).rounded_rectangle((3, 3, w - 4, h - 4), 18, outline=colour + (255,), width=thick + 6)
        img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(7)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, w - 3, h - 3), 18, outline=colour, width=thick)
    d.rounded_rectangle((thick + 5, thick + 5, w - thick - 6, h - thick - 6), 12, outline=mix(colour, BASE, 0.45), width=2)
    for x, y in ((thick + 5, thick + 5), (w - thick - 6, thick + 5), (thick + 5, h - thick - 6), (w - thick - 6, h - thick - 6)):
        d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=colour)


def stars(img: Image.Image, count: int, colour: tuple[int, int, int], y: int) -> None:
    d = ImageDraw.Draw(img)
    size, gap = 11, 28
    x0 = img.width // 2 - (count - 1) * gap // 2
    for i in range(count):
        cx = x0 + i * gap
        pts = []
        for k in range(10):
            r = size if k % 2 == 0 else size * 0.45
            a = -math.pi / 2 + k * math.pi / 5
            pts.append((cx + r * math.cos(a), y + r * math.sin(a)))
        d.polygon(pts, fill=mix(colour, (255, 255, 255), 0.35), outline=mix(colour, BASE, 0.4))


def save(img: Image.Image, kind: str, ident: str) -> None:
    folder = OUT / kind
    folder.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(folder / f"{ident}.jpg", "JPEG", quality=80, optimize=True, progressive=True)


def square(ch: str, rarity: int, ident: str, kind: str, side: int = 320) -> None:
    col = rgb(RARITY[rarity])
    img = background((side, side), col, ident, rays=rarity >= 5)
    paste_center(img, emoji(ch, int(side * 0.5)), side // 2, int(side * 0.45), glow=col)
    vignette(img, 120)
    stars(img, rarity, col, side - 34)
    frame(img, col, glow=rarity >= 4)
    save(img, kind, ident)


def card(ch: str, rarity: int, ident: str) -> None:
    w, h = 300, 400
    col = rgb(RARITY[rarity])
    img = background((w, h), col, ident, rays=rarity >= 5)
    paste_center(img, emoji(ch, 190), w // 2, int(h * 0.44), glow=col)
    ImageDraw.Draw(img).rounded_rectangle((26, 40, w - 27, h - 78), 14, outline=mix(col, BASE, 0.3), width=2)
    vignette(img, 110)
    stars(img, rarity, col, h - 42)
    frame(img, col, glow=rarity >= 4)
    save(img, "cards", ident)


def boss(ident: str, archetype: str, element_id: str, element_emoji: str) -> None:
    w, h = 480, 270
    col = rgb(ELEMENT[element_id])
    img = background((w, h), col, ident, rays=True)
    ghost = emoji(element_emoji, 230)
    ghost.putalpha(ghost.getchannel("A").point(lambda v: v * 28 // 100))
    img.alpha_composite(ghost, (w - ghost.width - 10, 20))
    floor = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(floor).ellipse((w * 0.24, h * 0.80, w * 0.76, h * 0.96), fill=(0, 0, 0, 170))
    img.alpha_composite(floor.filter(ImageFilter.GaussianBlur(8)))
    paste_center(img, emoji(archetype, 190), w // 2, int(h * 0.48), glow=col)
    vignette(img, 170)
    d = ImageDraw.Draw(img)
    d.ellipse((w - 82, 18, w - 18, 82), fill=mix(BASE, col, 0.25), outline=col, width=3)
    badge = emoji(element_emoji, 38)
    img.alpha_composite(badge, (w - 50 - badge.width // 2, 50 - badge.height // 2))
    frame(img, mix(col, (255, 255, 255), 0.1), thick=5, glow=True)
    save(img, "bosses", ident)


def event(ident: str, big: str, small: str, colour: str) -> None:
    w, h = 480, 270
    col = rgb(colour)
    img = background((w, h), col, ident, rays=True)
    paste_center(img, emoji(big, 170), w // 2, int(h * 0.5), glow=col)
    paste_center(img, emoji(small, 62), int(w * 0.70), int(h * 0.28), glow=col)
    paste_center(img, emoji(small, 44), int(w * 0.28), int(h * 0.70), glow=col)
    vignette(img, 140)
    frame(img, col, thick=5, glow=True)
    save(img, "events", ident)


def main() -> None:
    from eternal_realm.game.data import bosses, cards, classes, items, pets, races

    n = 0
    for it in (items.ITEMS.values() if isinstance(items.ITEMS, dict) else items.ITEMS):
        square(it.emoji, it.rarity, it.id, "items"); n += 1
    for p in (pets.PETS.values() if isinstance(pets.PETS, dict) else pets.PETS):
        square(p.emoji, p.rarity, p.id, "pets"); n += 1
    for c in (cards.CARDS.values() if isinstance(cards.CARDS, dict) else cards.CARDS):
        card(c.emoji, c.rarity, c.id); n += 1
    for b in (bosses.BOSSES.values() if isinstance(bosses.BOSSES, dict) else bosses.BOSSES):
        boss(b.id, b.emoji, b.element.id, b.element.emoji); n += 1
    for key, (big, small, colour) in EVENTS.items():
        event(key, big, small, colour); n += 1
    for r in (races.RACES.values() if isinstance(races.RACES, dict) else races.RACES):
        square(r.emoji, 4, r.id, "races"); n += 1
    for k in (classes.CLASSES.values() if isinstance(classes.CLASSES, dict) else classes.CLASSES):
        square(k.emoji, 5, k.id, "classes"); n += 1
    size = sum(f.stat().st_size for f in OUT.rglob("*.jpg"))
    print(f"{n} images, {size / 1024:.0f} KB in total")


if __name__ == "__main__":
    main()
