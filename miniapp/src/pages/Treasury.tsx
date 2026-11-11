// «خزانه قلمرو»: every real-money product on shelves. Each pack is a card with its treasure piled up (more treasure, a
// bigger pile), a ribbon for the best value, and a glossy price button that opens Bale's own payment sheet.
import { useQuery } from "@tanstack/react-query";
import { type CSSProperties, useMemo, useState } from "react";
import { Art, type Gem, Pile } from "../components/Art";
import { Icon, Skeleton } from "../components/ui";
import { call } from "../lib/api";
import { duration, fa } from "../lib/format";
import { iconFor, iconOfEmoji, ui } from "../lib/icons";
import type { ItemInfo } from "../lib/types";
import { useApp } from "../store";

interface Pack {
  id: string; emoji: string; title: string; section: string; toman: number; full_toman: number; gold: number; crystal: number; xp: number;
  spins: number; vip_days: number; boost_hours: number; pet: string; season: boolean; items: { item: ItemInfo; qty: number }[]; about: string; percent?: number;
}
interface Shelf { id: string; name: string; packs: Pack[] }
interface TreasuryData {
  enabled: boolean; shelves: Shelf[]; deals: Pack[]; deals_left: number; boost_left: number;
  vip: { active: boolean; left: number; perks: [string, string, string][] };
}

const SHELF_ART: Record<string, [string, Gem]> = {
  vip: ["ui.crown", "amethyst"], coins: ["ui.gold", "gold"], crystals: ["ui.crystal", "sapphire"], bundles: ["ui.gift", "ruby"],
  rare: ["item.dragon_scale", "emerald"], boost: ["ui.energy", "fire"], xp: ["ui.xp", "gold"], pets: ["ui.pet", "bronze"],
  materials: ["item.iron_ore", "silver"], services: ["ui.ticket", "amethyst"], city: ["b.city", "emerald"], deals: ["ui.gift", "ruby"],
};
const GEM_BY_RARITY: Gem[] = ["silver", "silver", "emerald", "sapphire", "amethyst", "gold", "ruby"];

/** The picture, the colour and the big number of a pack. */
function look(pack: Pack): { icon: string; gem: Gem; amount: string; sub: string } {
  if (pack.vip_days) return { icon: ui("ui.crown"), gem: "amethyst", amount: `${fa(pack.vip_days)} روز`, sub: "اشتراک VIP" };
  if (pack.boost_hours) return { icon: ui("ui.energy"), gem: "fire", amount: `${fa(pack.boost_hours)} ساعت`, sub: "بوست دو برابر" };
  if (pack.xp) return { icon: ui("ui.xp"), gem: "gold", amount: `${fa(pack.xp)}`, sub: "تجربه" };
  if (pack.spins) return { icon: ui("ui.wheel"), gem: "gold", amount: `${fa(pack.spins)} چرخش`, sub: "گردونه شانس" };
  if (pack.season) return { icon: ui("ui.path"), gem: "gold", amount: "بلیط طلایی", sub: "مسیر قهرمانی این فصل" };
  if (pack.pet) return { icon: iconOfEmoji(pack.emoji) || ui("ui.pet"), gem: "bronze", amount: pack.title.replace(/^.*:\s*/, ""), sub: "حیوان خانگی" };
  if (pack.crystal && !pack.gold && !pack.items.length) return { icon: ui("ui.crystal"), gem: "sapphire", amount: fa(pack.crystal), sub: "کریستال" };
  if (pack.gold && !pack.crystal && !pack.items.length) return { icon: ui("ui.gold"), gem: "gold", amount: fa(pack.gold), sub: "سکه" };
  if (pack.items.length === 1 && !pack.gold && !pack.crystal) {
    const { item, qty } = pack.items[0];
    return { icon: iconFor("item", item.id, item.emoji), gem: GEM_BY_RARITY[item.rarity] ?? "gold", amount: `×${fa(qty)}`, sub: item.name };
  }
  return { icon: iconOfEmoji(pack.emoji) || ui("ui.gift"), gem: "ruby", amount: pack.title, sub: pack.about };
}

function PackCard({ pack, index, rank, onBuy }: { pack: Pack; index: number; rank: number; onBuy: () => void }) {
  const art = look(pack);
  const many = pack.items.length + (pack.gold ? 1 : 0) + (pack.crystal ? 1 : 0) > 1;
  const ribbon = pack.percent ? `${fa(pack.percent)}٪ تخفیف` : rank === 0 ? "به‌صرفه‌ترین" : rank === 1 ? "محبوب" : "";
  if (many) {
    return (
      <div className="pk combo" style={{ "--i": index } as CSSProperties}>
        {ribbon && <span className={`ribbon ${pack.percent ? "" : "purple"}`}>{ribbon}</span>}
        <Pile icon={art.icon} count={3} size={54} gem={art.gem} />
        <div className="info">
          <div className="amount" style={{ fontSize: 19 }}>{pack.title}</div>
          <div className="chips">
            {pack.gold > 0 && <span className="tag gold"><Icon name={ui("ui.gold")} />{fa(pack.gold)}</span>}
            {pack.crystal > 0 && <span className="tag"><Icon name={ui("ui.crystal")} tone="sky" />{fa(pack.crystal)}</span>}
            {pack.items.map(({ item, qty }) => <span key={item.id} className="tag"><Icon name={iconFor("item", item.id, item.emoji)} />{item.name} ×{fa(qty)}</span>)}
          </div>
        </div>
        <button className="buy" onClick={onBuy}>{pack.percent ? <span className="was">{fa(pack.full_toman)}</span> : null}{fa(pack.toman)} تومان</button>
      </div>
    );
  }
  return (
    <div className={`pk ${rank === 0 ? "best" : ""}`} style={{ "--i": index } as CSSProperties}>
      {ribbon && <span className={`ribbon ${pack.percent ? "" : rank === 0 ? "green" : "purple"}`}>{ribbon}</span>}
      <Pile icon={art.icon} count={pack.percent ? 2 : index + 1} gem={art.gem} />
      <div className="amount num">{art.amount}</div>
      <div className="sub">{art.sub}</div>
      <button className="buy" onClick={onBuy}>{pack.percent ? <span className="was">{fa(pack.full_toman)}</span> : null}{fa(pack.toman)} تومان</button>
    </div>
  );
}

/** Which packs of a shelf deserve a ribbon: the cheapest per unit (best value) and the one after it (popular). */
function ranks(packs: Pack[]): Map<string, number> {
  const unit = (p: Pack) => p.toman / Math.max(1, p.gold + p.crystal * 600 + p.xp + p.items.reduce((s, x) => s + x.qty, 0) + p.spins * 80000 + p.boost_hours * 3000);
  const sorted = packs.length > 2 ? [...packs].sort((a, b) => unit(a) - unit(b)) : [];
  return new Map(sorted.slice(0, 2).map((p, i) => [p.id, i]));
}

export default function Treasury({ start = "vip", onClose }: { start?: string; onClose: () => void }) {
  const app = useApp();
  const data = useQuery({ queryKey: ["treasury"], queryFn: () => call<TreasuryData>("treasury") });
  const [picked, setTab] = useState(start);
  const shelves = useMemo(() => data.data?.shelves ?? [], [data.data]);
  const tabs = useMemo(() => [...(data.data?.deals.length ? [{ id: "deals", name: "تخفیف امروز" }] : []), ...shelves.map(({ id, name }) => ({ id, name }))], [data.data, shelves]);
  const tab = tabs.some((t) => t.id === picked) || !tabs.length ? picked : tabs[0].id;
  const shelf = shelves.find((s) => s.id === tab);
  const order = shelf ? ranks(shelf.packs) : new Map();
  const buy = (pack: Pack) => app.pay({ kind: pack.percent ? "deal" : "cash", id: pack.id });

  return (
    <div className="treasury">
      <div className="g-title">
        <button className="g-back" onClick={onClose} aria-label="بستن"><Icon name={ui("ui.back")} /></button>
        <h2>خزانه قلمرو</h2>
      </div>
      <div className="t-tabs">
        {tabs.map((t) => {
          const [icon, gem] = SHELF_ART[t.id] ?? ["ui.gift", "gold"];
          return (
            <button key={t.id} className={`t-tab ${tab === t.id ? "on" : ""}`} onClick={() => setTab(t.id)}>
              <Art icon={ui(icon)} size={20} gem={gem} />{t.name}
            </button>
          );
        })}
      </div>
      <div className="t-body">
        {!data.data ? <Skeleton height={190} count={2} /> : !data.data.enabled ? (
          <div className="window" style={{ textAlign: "center" }}>خرید با پول واقعی فعلاً بسته است.</div>
        ) : tab === "deals" ? (
          <>
            <div className="section-ribbon"><Art icon={ui("ui.gift")} size={30} gem="ruby" />تخفیف‌های امروز<span className="deal-timer num"><Icon name={ui("ui.clock")} tone="blood" />{duration(data.data.deals_left)}</span></div>
            <div className="t-grid">{data.data.deals.map((pack, i) => <PackCard key={pack.id} pack={pack} index={i} rank={-1} onBuy={() => buy(pack)} />)}</div>
          </>
        ) : tab === "vip" ? (
          <>
            <div className="vip-hero">
              <div className="vip-orbit">{Array.from({ length: 6 }, (_, i) => <i key={i} style={{ transform: `rotate(${i * 60}deg) translateX(86px) scale(${i % 2 ? 0.6 : 1})` }} />)}</div>
              <Art icon={ui("ui.crown")} size={108} gem="amethyst" />
              <h3>باشگاه VIP</h3>
              {data.data.vip.active
                ? <div className="vip-state on"><Icon name={ui("ui.check")} tone="ink" />فعال · {duration(data.data.vip.left)} مانده</div>
                : <div className="vip-state">راحت‌تر و سریع‌تر، بدون قدرت رزمی اضافه</div>}
            </div>
            <div className="perks">
              {data.data.vip.perks.map(([icon, title, sub], i) => (
                <div key={title} className="perk" style={{ "--i": i } as CSSProperties}>
                  <Art icon={ui(`ui.${icon}`)} size={48} gem={i % 2 ? "gold" : "amethyst"} />
                  <b>{title}</b><small>{sub}</small>
                </div>
              ))}
            </div>
            <div className="section-ribbon"><Art icon={ui("ui.crown")} size={28} gem="amethyst" />اشتراک</div>
            <div className="t-grid one">{shelf?.packs.map((pack, i) => (
              <div key={pack.id} className="pk best" style={{ "--i": i, "--glow": "rgba(107, 166, 255,.4)" } as CSSProperties}>
                <span className="ribbon purple">۳۰ روز</span>
                <div className="amount">{data.data!.vip.active ? "تمدید VIP" : "خرید VIP"}</div>
                <div className="sub">تمدید به روزهای باقی‌مانده اضافه می‌شود</div>
                <button className="buy green" onClick={() => buy(pack)}>{fa(pack.toman)} تومان</button>
              </div>
            ))}</div>
          </>
        ) : shelf ? (
          <>
            {tab === "boost" && data.data.boost_left > 0 && <div className="window" style={{ textAlign: "center", marginBottom: 12 }}><Icon name={ui("ui.energy")} /> بوست شما فعال است · {duration(data.data.boost_left)} مانده</div>}
            <div className={`t-grid ${shelf.packs.some((p) => p.items.length + (p.gold ? 1 : 0) + (p.crystal ? 1 : 0) > 1) && tab !== "rare" ? "one" : ""}`}>
              {shelf.packs.map((pack, i) => <PackCard key={pack.id} pack={pack} index={i} rank={order.get(pack.id) ?? -1} onBuy={() => buy(pack)} />)}
            </div>
            <p className="small muted" style={{ textAlign: "center", marginTop: 14 }}>پرداخت با کیف پول بله · خرید پس از تأیید بله به کیفتان می‌رسد</p>
          </>
        ) : null}
      </div>
    </div>
  );
}
