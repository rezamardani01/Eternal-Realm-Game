// «مسیر قهرمانی»: one road of a hundred steps with two lanes of rewards, the golden lane above and the free one below.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type CSSProperties, useEffect, useRef, useState } from "react";
import { Art } from "../components/Art";
import { Bar, Emblem, Icon, Skeleton } from "../components/ui";
import { call } from "../lib/api";
import { duration, fa } from "../lib/format";
import { iconFor, iconOfEmoji, ui } from "../lib/icons";
import type { ItemInfo } from "../lib/types";
import { useApp } from "../store";

interface Reward { gold: number; crystal: number; title: string; items: { item: ItemInfo; qty: number }[]; cards: { name: string; emoji: string }[] }
interface Tier { tier: number; free: Reward | null; ticket: Reward | null; free_claimed: boolean; ticket_claimed: boolean }
interface PathData { season: number; points: number; tier: number; premium: boolean; per_tier: number; tiers: number; seconds_left: number; ticket: { id: string; toman: number } | null; track: Tier[] }

const STEP = 96;  // the width of one tier column with its gap

/** The one picture and number that best stand for a reward. */
function face(reward: Reward): { icon: string; text: string; rarity: number } {
  if (reward.title) return { icon: ui("ui.laurel"), text: "عنوان", rarity: 6 };
  if (reward.items.length) return { icon: iconFor("item", reward.items[0].item.id, reward.items[0].item.emoji), text: `${reward.items[0].item.name}`, rarity: Math.max(3, reward.items[0].item.rarity) };
  if (reward.cards.length) return { icon: iconOfEmoji(reward.cards[0].emoji) || ui("ui.cards"), text: `کارت ${reward.cards[0].name}`, rarity: 4 };
  if (reward.crystal) return { icon: ui("ui.crystal"), text: `${fa(reward.crystal)} کریستال`, rarity: 3 };
  return { icon: ui("ui.gold"), text: `${fa(reward.gold)} سکه`, rarity: 1 };
}

/** The golden ticket's sales box: what the golden lane holds, added up from the season's own rewards. */
function TicketOffer({ data, onBuy, onClose }: { data: PathData; onBuy: () => void; onClose: () => void }) {
  const lane = data.track.map((t) => t.ticket).filter(Boolean) as Reward[];
  const sum = (f: (r: Reward) => number) => lane.reduce((n, r) => n + f(r), 0);
  const ready = data.track.filter((t) => t.ticket && t.tier <= data.tier).length;
  const titles = lane.filter((r) => r.title).length;
  const perks: { icon: string; gem: "gold" | "sapphire" | "amethyst" | "emerald" | "ruby"; title: string; sub: string }[] = [
    { icon: ui("ui.gift"), gem: "gold", title: `${fa(lane.length)} جایزه‌ی ویژه`, sub: "یک جایزه‌ی طلایی در هر مرحله" },
    ...(sum((r) => r.crystal) ? [{ icon: ui("ui.crystal"), gem: "sapphire" as const, title: `${fa(sum((r) => r.crystal))} کریستال`, sub: "در طول فصل" }] : []),
    ...(sum((r) => r.gold) ? [{ icon: ui("ui.gold"), gem: "gold" as const, title: `${fa(sum((r) => r.gold))} سکه`, sub: "در طول فصل" }] : []),
    ...(sum((r) => r.items.length) ? [{ icon: ui("ui.chest"), gem: "ruby" as const, title: `${fa(sum((r) => r.items.reduce((q, x) => q + x.qty, 0)))} آیتم و صندوقچه`, sub: "منابع کمیاب، صندوقچه، معجون" }] : []),
    ...(sum((r) => r.cards.length) ? [{ icon: ui("ui.cards"), gem: "amethyst" as const, title: `${fa(sum((r) => r.cards.length))} کارت کلکسیونی`, sub: "برای آلبوم کارت" }] : []),
    ...(titles ? [{ icon: ui("ui.laurel"), gem: "emerald" as const, title: `${fa(titles)} عنوان افتخاری`, sub: "روی پروفایل شما" }] : []),
    ...(ready ? [{ icon: ui("ui.check"), gem: "emerald" as const, title: `${fa(ready)} جایزه همین الان آماده`, sub: "مرحله‌هایی که رد کرده‌اید فوراً باز می‌شوند" }] : []),
  ];
  return (
    <div className="ticket-room" onClick={onClose}>
      <div className="ticket-box" onClick={(event) => event.stopPropagation()}>
        <span className="ticket-rays" />
        <div className="ticket">
          <span className="ticket-notch l" /><span className="ticket-notch r" />
          <Art icon={ui("ui.crown")} size={54} gem="gold" />
          <div className="ticket-text"><small>فصل جاری</small><b>بلیط طلایی</b></div>
          <span className="ticket-perf" />
          <span className="ticket-stub num">{fa(data.tiers)}<small>مرحله</small></span>
        </div>
        <ul className="ticket-perks">
          {perks.map((perk, i) => (
            <li key={perk.title} style={{ "--i": i } as CSSProperties}>
              <Art icon={perk.icon} size={34} gem={perk.gem} />
              <span><b>{perk.title}</b><small>{perk.sub}</small></span>
            </li>
          ))}
        </ul>
        <button className="g-btn big ticket-buy" onClick={onBuy}>
          <Art icon={ui("ui.crown")} size={26} gem="gold" />خرید بلیط · {fa(data.ticket!.toman)} تومان
        </button>
        <button className="ticket-later" onClick={onClose}>بعداً</button>
        <p className="ticket-note">پرداخت امن با کیف پول بله · فقط برای همین فصل</p>
      </div>
    </div>
  );
}

export default function PathTrack({ onClose }: { onClose: () => void }) {
  const app = useApp();
  const client = useQueryClient();
  const path = useQuery({ queryKey: ["path"], queryFn: () => call<PathData>("path"), staleTime: 0 });
  const scroller = useRef<HTMLDivElement>(null);
  const [offer, setOffer] = useState(false);
  const data = path.data;

  useEffect(() => {
    if (data && scroller.current) scroller.current.scrollTo({ left: Math.max(0, (data.tier - 1.5) * STEP), behavior: "smooth" });
  }, [data?.tier]);  // eslint-disable-line react-hooks/exhaustive-deps

  const claim = async (payload: Record<string, unknown>) => {
    try {
      const result = await call<{ claimed: number }>("path", payload);
      app.toast(result.claimed > 1 ? `${fa(result.claimed)} جایزه به کیفتان آمد` : "جایزه به کیفتان آمد");
    } catch (error) {
      app.toast(error instanceof Error ? error.message : "نشد", true);
    }
    await client.invalidateQueries();
  };

  const box = (tier: Tier, lane: "free" | "ticket") => {
    const reward = tier[lane];
    if (!reward) return <span />;
    const claimed = lane === "free" ? tier.free_claimed : tier.ticket_claimed;
    const reached = data!.tier >= tier.tier;
    const allowed = lane === "free" || data!.premium;
    const ready = reached && allowed && !claimed;
    const { icon, text, rarity } = face(reward);
    const extra = (reward.gold ? 1 : 0) + (reward.crystal ? 1 : 0) + reward.items.length + reward.cards.length + (reward.title ? 1 : 0) - 1;
    return (
      <button
        className={`reward-box ${lane === "ticket" ? "gold-lane" : ""} ${ready ? "ready" : claimed ? "done" : !reached || !allowed ? "locked" : ""}`}
        onClick={() => (ready ? claim({ track: lane, tier: tier.tier }) : !claimed && !allowed && data!.ticket ? setOffer(true) : app.toast(claimed ? "این جایزه را گرفته‌اید." : !allowed ? "این ردیف با بلیط فصل باز می‌شود." : `در مرحله‌ی ${fa(tier.tier)} باز می‌شود.`, !claimed))}
      >
        <Emblem icon={icon} size={46} rarity={rarity} />
        <span style={{ padding: "0 4px", lineHeight: 1.35 }}>{text}{extra > 0 && ` +${fa(extra)}`}</span>
        {(claimed || !reached || !allowed) && <span className="mark"><Icon name={ui(claimed ? "ui.check" : "ui.lock")} tone={claimed ? "emerald" : "muted"} /></span>}
      </button>
    );
  };

  const waiting = data ? data.track.filter((t) => t.tier <= data.tier && ((t.free && !t.free_claimed) || (data.premium && t.ticket && !t.ticket_claimed))).length : 0;
  return (
    <div className="overlay">
      <div className="topbar">
        <button className="round-btn" onClick={onClose} aria-label="بستن"><Icon name={ui("ui.back")} /></button>
        <h2>مسیر قهرمانی</h2>
        <span className="pill gold num small"><Icon name={ui("ui.clock")} />{data ? duration(data.seconds_left) : ""}</span>
      </div>
      <div className="body" style={{ paddingInline: 0 }}>
        {!data ? <div style={{ padding: 14 }}><Skeleton height={130} /></div> : (
          <>
            <div className="window" style={{ margin: "0 14px 12px" }}>
              <div className="row">
                <Emblem icon={ui("ui.path")} size={62} rarity={5} badge={fa(data.tier)} />
                <div className="grow">
                  <div className="title gold-text" style={{ fontSize: 20 }}>مرحله‌ی {fa(data.tier)} از {fa(data.tiers)}</div>
                  <div className="row small" style={{ justifyContent: "space-between" }}>
                    <span className="muted">تا مرحله‌ی بعد</span><span className="num">{fa(data.points % data.per_tier)} / {fa(data.per_tier)}</span>
                  </div>
                  <Bar value={data.tier >= data.tiers ? 1 : data.points % data.per_tier} max={data.tier >= data.tiers ? 1 : data.per_tier} />
                </div>
              </div>
              <p className="small muted" style={{ marginTop: 8 }}>هر کاری در بازی امتیاز مسیر می‌دهد: ماجراجویی، شکار، مأموریت، باس و دوئل.</p>
            </div>

            <div className="row" style={{ padding: "0 16px", justifyContent: "space-between" }}>
              <span className="lane-tag gold"><Icon name={ui("ui.crown")} />ردیف طلایی {data.premium ? "· فعال" : "· قفل"}</span>
              {waiting > 0 && <button className="tag green" onClick={() => claim({ all: true })}>دریافت همه ({fa(waiting)})</button>}
            </div>
            <div className="track-wrap" ref={scroller}>
              <div className="track">
                <div className="rail"><i style={{ width: `${Math.min(100, ((Math.max(0, data.tier - 0.5) + (data.points % data.per_tier) / data.per_tier) / data.tiers) * 100)}%` }} /></div>
                {data.track.map((tier) => (
                  <div key={tier.tier} className={`tier ${data.tier >= tier.tier ? "reached" : ""}`}>
                    {box(tier, "ticket")}
                    <span className="node num">{fa(tier.tier)}</span>
                    {box(tier, "free")}
                  </div>
                ))}
              </div>
            </div>
            <div style={{ padding: "0 16px" }}><span className="lane-tag free"><Icon name={ui("ui.gift")} />ردیف رایگان · برای همه</span></div>

            <div className="stack" style={{ padding: "16px 14px 0" }}>
              {!data.premium && data.ticket && (
                <button className="g-btn big" onClick={() => setOffer(true)}>
                  <Art icon={ui("ui.crown")} size={26} gem="gold" />باز کردن ردیف طلایی
                </button>
              )}
              <button className="g-btn ghost" onClick={() => app.open("pathtiers")}>همه‌ی مرحله‌ها و جایزه‌ها</button>
            </div>
          </>
        )}
      </div>
      {offer && data?.ticket && <TicketOffer data={data} onClose={() => setOffer(false)} onBuy={() => { setOffer(false); app.pay({ kind: "cash", id: data.ticket!.id }); }} />}
    </div>
  );
}
