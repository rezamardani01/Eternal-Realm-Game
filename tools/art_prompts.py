"""Writes ``tools/art_prompts.md``: one ready-to-paste image-generator prompt per game id.

Generate the pictures with any AI image tool (Midjourney, DALL-E, Stable Diffusion, Leonardo ...), save each one under
the id it was made for (``fire_sword.png``, ``beast_fire.png`` ...) in one folder and run ``tools/import_art.py``.

    python tools/art_prompts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STYLE = (
    "epic dark fantasy digital painting, ultra detailed, dramatic cinematic lighting, glowing magical energy, rich deep "
    "blue and violet atmosphere with warm gold highlights, volumetric light, sharp focus, masterpiece game art, "
    "no text, no watermark, no letters"
)
KIND_WORDS = {
    "weapon": "a fantasy weapon", "shield": "an ornate battle shield", "helmet": "an ornate battle helmet",
    "armor": "a suit of heroic armor", "boots": "a pair of enchanted armored boots", "ring": "a magical ring with a glowing gem",
    "amulet": "a glowing magical amulet", "consumable": "a glowing potion bottle", "material": "a crafting resource",
    "chest": "an ornate treasure chest",
}
RARITY_LOOK = {1: "plain humble worn look", 2: "well made, slightly polished", 3: "fine quality with blue glow", 4: "epic, purple magical glow",
               5: "legendary, golden radiant glow, particles", 6: "mythic, blazing red and gold aura"}
ELEMENT_LOOK = {
    "fire": "wreathed in flames and embers, orange and red", "ice": "covered in frost and ice shards, icy cyan", "lightning": "crackling with lightning bolts, electric yellow",
    "nature": "overgrown with vines, leaves and glowing moss, green", "water": "streaming with water, waves and bubbles, deep blue", "shadow": "made of swirling dark smoke and violet shadow",
    "earth": "armored in rock and crystal, brown and amber", "wind": "surrounded by swirling storm winds and clouds, teal", "light": "radiant holy light and golden rays", "poison": "dripping toxic green venom and spores",
}
BOSS_LOOK = {
    "beast": "a monstrous giant tusked beast", "dragon": "a colossal winged dragon roaring", "giant": "a towering stone giant", "golem": "a huge ancient golem made of masonry",
    "serpent": "a gigantic coiled serpent with glowing eyes", "spider": "an enormous terrifying spider", "wraith": "a hooded floating wraith with glowing eyes",
}
EVENTS = {
    "mystery_chest": "a mysterious locked vault safe with a glowing combination dial and keyhole in a dark cave, treasure light leaking out",
    "merchant": "a mysterious travelling merchant with a lantern and a heavily loaded cart of magic goods at a night roadside",
    "double_xp": "a swirling vortex of golden star energy and glowing runes rising into the night sky",
    "hidden_boss": "a gigantic shadowy demon boss rising from a dark portal, glowing red eyes, ominous",
}
PET_LOOK = {"cat": "an agile mystical cat", "hawk": "a noble guardian hawk with spread wings", "fox": "a fiery fox with burning tail", "wolf": "a majestic dawn wolf howling", "phoenix": "a small radiant phoenix bird of fire"}
PLACE_LOOK = {
    "forest": "a cursed dark forest with twisted trees and glowing fog", "castle": "a looming castle of darkness at night", "lake": "a mirror lake reflecting the moon and stars",
    "mine": "a forgotten abandoned mine with glowing crystals", "peak": "a windswept mountain peak above the clouds", "gate": "a mist-covered ancient stone gate with a glowing eye sigil",
}
LEGEND_LOOK = {
    "ember_king": "the Ember King, a crowned skeletal king of ashes and living fire", "moon_witch": "the Moon Witch, a mystical sorceress under a giant moon", "iron_titan": "the Iron Titan, a colossal armored steel giant",
    "star_dragon": "the Star Dragon, a cosmic dragon made of stars and galaxies", "lost_prince": "the Lost Prince, a young noble hero in a torn royal cloak",
}
HERO_LOOK = {"warrior": "a mighty warrior with sword and shield", "mage": "a powerful mage casting arcane magic", "archer": "an elite archer drawing a glowing bow",
             "guardian": "a heavily armored guardian knight with a great shield", "rogue": "a swift shadowy rogue with twin daggers"}
MONSTER_LOOK = {"goblin": "a sneaky goblin raider", "wolf": "a wild snarling wolf", "skeleton": "a skeleton warrior with rusty sword", "orc": "a roaring orc brute",
                "golem": "an ice golem of frozen stone", "whelp": "a young baby dragon"}


def _all(group):
    return list(group.values()) if isinstance(group, dict) else list(group)


def words(ident: str) -> str:
    return ident.replace("_", " ")


def main() -> None:
    from eternal_realm.game.data import bosses, cards, items, pets

    out: list[str] = [
        "# Image prompts for Eternal Realm", "",
        f"Style line added to every prompt: `{STYLE}`", "",
        "Save every picture under the file name shown in **bold** (any image format), then run `python tools/import_art.py <folder>`.", "",
    ]

    def section(title: str, aspect: str, rows: list[tuple[str, str]]) -> None:
        out.extend([f"## {title}  ({len(rows)} images, aspect {aspect})", ""])
        for ident, subject in rows:
            out.append(f"- **{ident}** — {subject}, {STYLE} --ar {aspect.replace(':', ':')}")
        out.append("")

    rows = []
    for it in _all(items.ITEMS):
        base = KIND_WORDS.get(it.kind.value, "a fantasy object")
        subject = f"{words(it.id)}, {base}, centered single object on a dark magical background, {RARITY_LOOK[it.rarity]}"
        rows.append((f"items/{it.id}", subject))
    section("Items", "1:1", rows)

    rows = []
    for b in _all(bosses.BOSSES):
        arche, _, element = b.id.rpartition("_")
        rows.append((f"bosses/{b.id}", f"{BOSS_LOOK[arche]}, {ELEMENT_LOOK[element]}, epic wide boss encounter scene, menacing"))
    section("Bosses", "16:9", rows)

    section("Pets", "1:1", [(f"pets/{p.id}", f"{PET_LOOK.get(p.id, words(p.id))}, cute but majestic companion creature, glowing aura") for p in _all(pets.PETS)])

    rows = []
    for c in _all(cards.CARDS):
        kind, _, key = c.id.partition("_")
        if c.set_id == "heroes":
            subject = HERO_LOOK[key]
        elif c.set_id == "monsters":
            subject = MONSTER_LOOK[key]
        elif c.set_id == "dragons":
            arche, _, element = c.id.partition("_")[2], "", c.id.rpartition("_")[2]
            subject = f"a majestic dragon, {ELEMENT_LOOK[element]}"
        elif c.set_id == "places":
            subject = PLACE_LOOK[key]
        else:
            subject = LEGEND_LOOK[c.id.removeprefix("legend_")]
        frame = f"{RARITY_LOOK[c.rarity]}, collectible trading card illustration, full portrait"
        rows.append((f"cards/{c.id}", f"{subject}, {frame}"))
    section("Cards", "3:4", rows)

    section("Events", "16:9", [(f"events/{k}", v) for k, v in EVENTS.items()])

    path = ROOT / "tools" / "art_prompts.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"{sum(1 for line in out if line.startswith('- **'))} prompts written to {path}")


if __name__ == "__main__":
    main()
