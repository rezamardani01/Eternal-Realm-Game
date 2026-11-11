// «قهرمان من»: a throne hall. The hero stands on a turning rune circle under a spotlight between banners and torches,
// the worn gear hangs in framed slots on both sides, the power burns in a flame badge, the six stats are ring gauges
// that fill as the page opens, and the bag and resources are slots in rarity frames like a game inventory.
import { useQuery } from "@tanstack/react-query";
import { type CSSProperties } from "react";
import { Art, Count, type Gem } from "../components/Art";
import { Icon, Inline } from "../components/ui";
import { call } from "../lib/api";
import { haptic } from "../lib/bale";
import { fa } from "../lib/format";
import { iconFor, ui } from "../lib/icons";
import type { HeroPage } from "../lib/types";
import { useApp } from "../store";

const STATS = [
  { key: "hp", label: "جان", icon: "ui.hp", gem: "ruby", color: "#ff6a6a" },
  { key: "atk", label: "حمله", icon: "ui.atk", gem: "gold", color: "#f6d26a" },
  { key: "defense", label: "دفاع", icon: "ui.defense", gem: "sapphire", color: "#6cc8ff" },
  { key: "magic", label: "جادو", icon: "ui.magic", gem: "amethyst", color: "#c49bff" },
  { key: "speed", label: "سرعت", icon: "ui.speed", gem: "frost", color: "#9ff0ff" },
  { key: "luck", label: "شانس", icon: "ui.luck", gem: "emerald", color: "#5fe08e" },
] as const;
const GROW: { label: string; icon: string; screen: string; gem: Gem }[] = [
  { label: "ارتقای قهرمان", icon: "ui.laurel", screen: "ascend", gem: "gold" },
  { label: "مسیر قهرمانی", icon: "ui.path", screen: "path", gem: "amethyst" },
  { label: "حیوان خانگی", icon: "ui.pet", screen: "pets", gem: "bronze" },
  { label: "آلبوم کارت", icon: "ui.cards", screen: "album", gem: "sapphire" },
  { label: "محراب", icon: "ui.altar", screen: "altar", gem: "amethyst" },
  { label: "کوره آهنگری", icon: "ui.anvil", screen: "craft", gem: "fire" },
  { label: "مأموریت‌ها", icon: "ui.mission", screen: "missions", gem: "bronze" },
  { label: "دستاوردها", icon: "ui.trophy", screen: "ach", gem: "gold" },
];
const GEM_BY_RARITY: Gem[] = ["silver", "silver", "emerald", "sapphire", "amethyst", "gold", "ruby"];

export default function Hero() {
  const { me, open } = useApp();
  const p = me.player;
  const hero = useQuery({ queryKey: ["hero"], queryFn: () => call<HeroPage>("hero") });
  const slots = hero.data?.slots ?? [];
  const go = (screen: string, a?: string) => { haptic(); open(screen, a); };
  const top = Math.max(...STATS.map((s) => (s.key === "hp" ? me.stats.hp / 4 : me.stats[s.key])), 1);

  const slotTile = (slot: HeroPage["slots"][number], i: number) => (
    <button key={slot.id} className={`h-slot r-${slot.piece?.item.rarity ?? 0} ${slot.piece ? "" : "empty"}`} style={{ "--i": i } as CSSProperties}
      onClick={() => (slot.piece ? go("piece", String(slot.piece.id)) : go("gear"))}>
      {slot.piece
        ? <Art icon={iconFor("item", slot.piece.item.id, slot.piece.item.emoji)} size={42} gem={GEM_BY_RARITY[slot.piece.item.rarity] ?? "silver"} />
        : <Icon name={iconFor("slot", slot.id)} size={30} tone="muted" />}
      {slot.piece?.upgrade ? <i className="num">+{fa(slot.piece.upgrade)}</i> : null}
    </button>
  );

  return (
    <div className="page hero-hall">
      <div className="throne">
        <span className="th-arch" />
        <span className="th-banner l" /><span className="th-banner r" />
        <span className="th-torch l"><i /></span><span className="th-torch r"><i /></span>
        <span className="th-spot" />
        <div className="h-col">{slots.slice(0, 4).map(slotTile)}</div>
        <div className="h-center">
          <span className="rune-ring" /><span className="rune-ring inner" />
          <span className="h-motes">{Array.from({ length: 10 }, (_, i) => <i key={i} style={{ "--i": i, left: `${10 + ((i * 37) % 80)}%` } as CSSProperties} />)}</span>
          <span className="h-figure"><Art icon={iconFor("class", p.class.id, p.class.emoji)} size={128} gem="gold" /></span>
        </div>
        <div className="h-col">{slots.slice(4).map((s, i) => slotTile(s, i + 4))}</div>
      </div>

      <div className="h-plate">
        <span className="h-level num">{fa(p.level)}</span>
        <h1>{p.name}</h1>
        {p.honor && <div className="h-honor"><Inline text={p.honor} /></div>}
        <div className="h-badges">
          <span><Icon name={iconFor("race", p.race.id, p.race.emoji)} />{p.race.name}</span>
          <span><Icon name={iconFor("class", p.class.id, p.class.emoji)} />{p.class.name}</span>
          {p.class2 && <span><Icon name={iconFor("class", p.class2.id, p.class2.emoji)} />{p.class2.name}</span>}
          {p.awakened && <span className="woke">قدرت بیدار</span>}
        </div>
        <div className="h-xp"><i style={{ width: `${Math.min(100, (100 * p.xp) / Math.max(1, p.xp_needed))}%` }} /><span className="num">{fa(p.xp)} / {fa(p.xp_needed)}</span></div>
      </div>

      <div className="h-record">
        <div className="h-power"><Art icon={ui("ui.power")} size={34} gem="fire" /><b className="num"><Count to={me.power} /></b><small>قدرت</small></div>
        <div><b className="num"><Count to={p.wins} /></b><small>پیروزی</small></div>
        <div><b className="num"><Count to={p.losses} /></b><small>شکست</small></div>
        <div><b className="num"><Count to={p.streak} /></b><small>زنجیره</small></div>
      </div>

      <h3 className="section-title"><Icon name={ui("ui.power")} />ویژگی‌ها</h3>
      <div className="h-stats">
        {STATS.map((stat, i) => {
          const value = stat.key === "hp" ? me.stats.hp / 4 : me.stats[stat.key];
          return (
            <button key={stat.key} className="h-stat" style={{ "--i": i, "--c": stat.color, "--p": `${Math.max(6, Math.min(100, (100 * value) / top))}` } as CSSProperties} onClick={() => go("stat", stat.key)}>
              <span className="h-ring"><Art icon={ui(stat.icon)} size={28} gem={stat.gem as Gem} /></span>
              <b className="num"><Count to={me.stats[stat.key]} delay={200 + i * 80} /></b>
              <small>{stat.label}</small>
            </button>
          );
        })}
      </div>

      {hero.data && hero.data.bag.length > 0 && (
        <>
          <h3 className="section-title"><Icon name={ui("ui.bag")} />کوله<button className="more" onClick={() => go("inv")}>همه</button></h3>
          <div className="h-bag">
            {hero.data.bag.slice(0, 12).map((piece, i) => (
              <button key={piece.id} className={`inv-slot r-${piece.item.rarity}`} style={{ "--i": i } as CSSProperties} onClick={() => go("piece", String(piece.id))}>
                <Art icon={iconFor("item", piece.item.id, piece.item.emoji)} size={40} gem={GEM_BY_RARITY[piece.item.rarity] ?? "silver"} />
                {piece.upgrade ? <i className="num">+{fa(piece.upgrade)}</i> : null}
                <small className="ellipsis">{piece.item.name}</small>
              </button>
            ))}
          </div>
        </>
      )}

      {hero.data && hero.data.stacks.length > 0 && (
        <>
          <h3 className="section-title"><Icon name={ui("ui.chest")} />منابع و آیتم‌ها<button className="more" onClick={() => go("items")}>همه</button></h3>
          <div className="h-inv">
            {hero.data.stacks.slice(0, 16).map(({ item, qty }, i) => (
              <button key={item.id} className={`inv-slot r-${item.rarity}`} style={{ "--i": i } as CSSProperties} onClick={() => go(item.kind === "chest" ? "chests" : "item", item.kind === "chest" ? "" : item.id)}>
                <Art icon={iconFor("item", item.id, item.emoji)} size={38} gem={GEM_BY_RARITY[item.rarity] ?? "silver"} />
                <i className="num">{fa(qty)}</i>
                <small className="ellipsis">{item.name}</small>
              </button>
            ))}
          </div>
        </>
      )}

      <h3 className="section-title"><Icon name={ui("ui.laurel")} />رشد قهرمان</h3>
      <div className="gp-tiles">
        {GROW.map((door, i) => (
          <button key={door.screen} className="gp-tile" style={{ "--i": i } as CSSProperties} onClick={() => go(door.screen)}>
            <Art icon={ui(door.icon)} size={44} gem={door.gem} />
            <span>{door.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
