"""Turns generated pictures into the small files the bot sends.

Put the pictures in one folder, named after the id they belong to (see ``tools/art_prompts.md``), either flat
(``fire_sword.png``) or in kind folders (``items/fire_sword.png``), then run::

    python tools/import_art.py path/to/folder

Each one is cropped to the right shape, shrunk and saved as a JPEG of at most ~55 KB in ``eternal_realm/assets/art``.
Files whose id is unknown are reported and skipped.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "eternal_realm" / "assets" / "art"
SIZES = {"items": (384, 384), "pets": (384, 384), "races": (384, 384), "classes": (384, 384), "cards": (360, 480), "bosses": (640, 360), "events": (640, 360)}
LIMIT = 55_000


def known_ids() -> dict[str, str]:
    from eternal_realm.game.data import bosses, cards, items, pets
    from eternal_realm.game.services.events import KINDS

    def each(group):
        return list(group.values()) if isinstance(group, dict) else list(group)

    ids = {i.id: "items" for i in each(items.ITEMS)}
    ids |= {p.id: "pets" for p in each(pets.PETS)}
    ids |= {c.id: "cards" for c in each(cards.CARDS)}
    ids |= {b.id: "bosses" for b in each(bosses.BOSSES)}
    ids |= {k: "events" for k in KINDS}
    return ids


def convert(src: Path, kind: str, ident: str) -> int:
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    img = ImageOps.fit(img, SIZES[kind], Image.LANCZOS, centering=(0.5, 0.42))
    target = OUT / kind / f"{ident}.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    for quality in (88, 82, 76, 70, 64, 58):
        img.save(target, "JPEG", quality=quality, optimize=True, progressive=True)
        if target.stat().st_size <= LIMIT:
            break
    return target.stat().st_size


def main(folder: str) -> None:
    ids = known_ids()
    done, skipped = 0, []
    for src in sorted(Path(folder).rglob("*")):
        if src.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        ident = src.stem
        if ident not in ids:
            skipped.append(src.name)
            continue
        size = convert(src, ids[ident], ident)
        done += 1
        print(f"{ids[ident]}/{ident}: {size // 1024} KB")
    print(f"{done} imported; {len(skipped)} skipped {skipped[:10]}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
