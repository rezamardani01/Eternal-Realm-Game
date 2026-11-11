// «ماجراجویی»: the day's works as scenic cards with a big start button. Starting one plays the work out (the tool
// swings, dust flies, a ring fills), then a chest drops and shakes; opening it throws the loot out one prize at a time,
// each number counting up. Below are the roads of the hero's trip.
import { useQuery } from "@tanstack/react-query";
import { type CSSProperties, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Art, Burst, Count, type Gem } from "../components/Art";
import { Chest } from "../components/Chest";
import { Bar, Icon, Inline, Skeleton } from "../components/ui";
import { call } from "../lib/api";
import { haptic } from "../lib/bale";
import { duration, fa } from "../lib/format";
import { iconFor, iconOfEmoji, ui } from "../lib/icons";
import type { ActResult, ActivityCard } from "../lib/types";
import { useApp } from "../store";

const ROADS: { label: string; about: string; icon: string; screen: string; gem: Gem }[] = [
  { label: "سفر قهرمان", about: "داستان، دخمه، باس، میدان و جهان زنده", icon: "ui.adventure", screen: "trip", gem: "amethyst" },
  { label: "هزارتوی ابدی", about: "چهار فصل، دویست طبقه، هر طبقه یک تصمیم", icon: "ui.maze", screen: "maze", gem: "sapphire" },
  { label: "برج بی‌پایان", about: "هر طبقه یک نبرد؛ رتبه‌ی جهانی", icon: "ui.tower", screen: "tower", gem: "silver" },
  { label: "سیاه‌چال", about: "پنج اتاق پشت‌سرهم و یک نگهبان", icon: "ui.dungeon", screen: "dungeon", gem: "emerald" },
  { label: "باس‌های تک‌نفره", about: "پنج باس با ترفند؛ کریستال و صندوقچه", icon: "ui.boss", screen: "sbosses", gem: "fire" },
  { label: "داستان سرزمین", about: "بیست مرحله با انتخاب راه", icon: "ui.story", screen: "story", gem: "bronze" },
  { label: "اعزام قهرمان", about: "قهرمان را بفرستید و بعد گزارش بگیرید", icon: "ui.camp", screen: "expd", gem: "gold" },
  { label: "داستان‌های انتخابی", about: "ماجراهایی که پایانش با شماست", icon: "ui.quest", screen: "quests", gem: "sapphire" },
  { label: "جهان زنده", about: "رویداد جهانی و تاریکی مناطق", icon: "ui.world", screen: "world", gem: "emerald" },
];
/** Each work has its own sky and its own jewel. */
const SCENE: Record<string, [string, Gem, string]> = {
  hunt: ["#5a1a1a", "ruby", "در حال شکار..."], fishing: ["#123a5a", "sapphire", "قلاب در آب است..."], mining: ["#313b49", "silver", "کلنگ به سنگ می‌خورد..."],
  herb: ["#1a4a2a", "emerald", "گیاه‌ها چیده می‌شوند..."], search: ["#3a2a5a", "amethyst", "همه‌جا گشته می‌شود..."], woodcutting: ["#4a2e14", "bronze", "تبر بالا می‌رود..."],
  farming: ["#4a4214", "gold", "خوشه‌ها درو می‌شوند..."], beekeeping: ["#5a4010", "gold", "کندوها باز می‌شوند..."], exploring: ["#2a3a5a", "bronze", "ویرانه‌ها کاویده می‌شوند..."],
  performing: ["#4a1a4a", "amethyst", "نوای ساز بلند است..."],
};
const MIN_WORK_MS = 1700;

type Phase = "work" | "chest" | "open";

export default function Adventure() {
  const { me, open, refresh, toast } = useApp();
  const adventure = useQuery({ queryKey: ["adventure"], queryFn: () => call<{ activities: ActivityCard[] }>("adventure") });
  const [run, setRun] = useState<{ card: ActivityCard; phase: Phase; result: ActResult | null } | null>(null);
  const opener = useRef<number>();
  const p = me.player;

  const start = async (card: ActivityCard) => {
    if (run) return;
    haptic("tap");
    setRun({ card, phase: "work", result: null });
    const began = performance.now();
    try {
      const { result } = await call<{ result: ActResult }>("act", { id: card.id });
      await new Promise((done) => window.setTimeout(done, Math.max(0, MIN_WORK_MS - (performance.now() - began))));
      haptic("success");
      setRun({ card, phase: "chest", result });
      opener.current = window.setTimeout(() => setRun((r) => (r && r.phase === "chest" ? { ...r, phase: "open" } : r)), 1800);
    } catch (error) {
      setRun(null);
      toast(error instanceof Error ? error.message.replace(/\p{Extended_Pictographic}️?/gu, "").trim() : "نشد", true);
    } finally {
      void refresh();
    }
  };
  const openChest = () => { window.clearTimeout(opener.current); haptic("success"); setRun((r) => (r ? { ...r, phase: "open" } : r)); };
  const close = () => { window.clearTimeout(opener.current); setRun(null); };

  return (
    <div className="page adv">
      <div className="adv-head">
        <span className="adv-orb"><Art icon={ui("ui.energy")} size={44} gem="frost" /></span>
        <div className="grow">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h1 className="title gold-text">ماجراجویی</h1>
            <b className="num adv-energy">{fa(p.energy)}<small>/{fa(p.max_energy)}</small></b>
          </div>
          <Bar value={p.energy} max={p.max_energy} tone="sky" />
        </div>
      </div>

      <h3 className="section-title"><Icon name={ui("ui.swords")} />کارهای امروز</h3>
      {!adventure.data ? <Skeleton height={190} count={2} /> : (
        <div className="works">
          {adventure.data.activities.map((card, i) => {
            const icon = iconFor("act", card.id, card.emoji);
            const [sky, gem] = SCENE[card.id] ?? ["#1c2d47", "gold"];
            const waiting = card.wait > 0;
            return (
              <div key={card.id} className={`work ${waiting ? "resting" : ""} ${card.danger ? "danger" : ""}`} style={{ "--sky": sky, "--i": i } as CSSProperties}>
                <span className="work-sun" />
                <span className="work-art"><Art icon={icon} size={70} gem={card.danger ? "ruby" : gem} /></span>
                <b className="work-title">{card.title}</b>
                <div className="work-meta">
                  <span><Icon name={ui("ui.energy")} tone="sky" />{fa(card.energy)}</span>
                  <span className={waiting ? "late" : "ok"}><Icon name={ui("ui.clock")} />{waiting ? duration(card.wait) : "آماده"}</span>
                </div>
                <button className={`work-go ${card.danger ? "red" : ""}`} disabled={waiting || Boolean(run)} onClick={() => start(card)}>
                  {waiting ? "استراحت" : card.danger ? "به شکار!" : "شروع"}
                </button>
              </div>
            );
          })}
        </div>
      )}

      <h3 className="section-title"><Icon name={ui("ui.adventure")} />راه‌های قهرمان</h3>
      <div className="roads">
        {ROADS.map((road, i) => (
          <button key={road.screen} className={`road g-${road.gem}`} style={{ "--i": i } as CSSProperties} onClick={() => open(road.screen)}>
            <Art icon={ui(road.icon)} size={50} gem={road.gem} />
            <span className="grow"><b>{road.label}</b><small>{road.about}</small></span>
            <Icon name={ui("ui.pointer")} className="road-go" />
          </button>
        ))}
      </div>

      {run && (() => {
        const { card, phase, result } = run;
        const icon = iconFor("act", card.id, card.emoji);
        const [sky, gem, doing] = SCENE[card.id] ?? ["#1c2d47", "gold", "در حال کار..."];
        const lost = result && result.kind === "hunt" && !result.won;
        const prizes = result ? [
          ...(result.gold > 0 ? [{ key: "g", icon: ui("ui.gold"), gem: "gold" as Gem, n: result.gold, name: "سکه" }] : []),
          ...(result.xp > 0 ? [{ key: "x", icon: ui("ui.xp"), gem: "gold" as Gem, n: result.xp, name: "تجربه" }] : []),
          ...(result.crystal > 0 ? [{ key: "c", icon: ui("ui.crystal"), gem: "sapphire" as Gem, n: result.crystal, name: "کریستال" }] : []),
          ...result.items.map(({ item, qty }) => ({ key: item.id, icon: iconFor("item", item.id, item.emoji), gem: (["silver", "silver", "emerald", "sapphire", "amethyst", "gold", "ruby"][item.rarity] ?? "gold") as Gem, n: qty, name: item.name })),
        ] : [];
        return createPortal(
          <div className="quest-room" style={{ "--sky": sky } as CSSProperties} onClick={phase === "chest" ? openChest : undefined}>
            {phase === "work" && (
              <div className="doing">
                <span className="doing-ring" />
                <span className="doing-dust">{Array.from({ length: 8 }, (_, i) => <i key={i} style={{ "--a": `${i * 45}deg` } as CSSProperties} />)}</span>
                <span className={`doing-art act-${card.id}`}><Art icon={icon} size={120} gem={card.danger ? "ruby" : gem} /></span>
                <p className="doing-text">{doing}</p>
              </div>
            )}
            {phase === "chest" && result && (
              <div className="chest-drop">
                <span className="chest-rays" />
                {lost ? <span className="chest-shake"><Art icon={ui("ui.skull")} size={150} gem="silver" /></span> : <span className="chest-in"><Chest look={card.danger ? "royal" : "wood"} state="shake" size={200} /></span>}
                <p className="doing-text">{lost ? "شکست خوردید..." : "برای باز کردن بزنید!"}</p>
              </div>
            )}
            {phase === "open" && result && (
              <div className="loot" onClick={(event) => event.stopPropagation()}>
                <span className="chest-rays big" />
                {!lost && <Burst count={34} />}
                {lost ? <span className="loot-hero"><Art icon={iconOfEmoji(result.emoji) || icon} size={88} gem="silver" /></span> : <span className="loot-chest"><Chest look={card.danger ? "royal" : "wood"} state="open" size={150} /></span>}
                <h2 className="loot-title">{result.title}</h2>
                <p className="loot-text"><Inline text={result.text} />{result.rounds ? ` (${fa(result.rounds)} دور)` : ""}</p>
                {prizes.length > 0 && (
                  <div className="loot-grid">
                    {prizes.map((prize, i) => (
                      <div key={prize.key} className="prize" style={{ "--i": i } as CSSProperties}>
                        <Art icon={prize.icon} size={46} gem={prize.gem} />
                        <b className="num">+<Count to={prize.n} delay={350 + i * 160} /></b>
                        <small className="ellipsis">{prize.name}</small>
                      </div>
                    ))}
                  </div>
                )}
                {result.hp && (
                  <div className="loot-hp">
                    <span><Icon name={ui("ui.hp")} /> جان <b className="num">{fa(result.hp[0])} / {fa(result.hp[1])}</b></span>
                    <Bar value={result.hp[0]} max={result.hp[1]} tone="blood" />
                  </div>
                )}
                {result.card && <div className="loot-flag"><Art icon={ui("ui.cards")} size={30} gem="amethyst" />کارت تازه: <b>{result.card.name}</b></div>}
                {result.level_up > 0 && <div className="loot-level"><Art icon={ui("ui.star")} size={36} gem="gold" />به سطح {fa(result.level_up)} رسیدید!</div>}
                <p className="loot-next"><Icon name={ui("ui.energy")} /> انرژی {fa(result.energy)} · <Icon name={ui("ui.clock")} /> نوبت بعد {duration(result.next_in)}</p>
                <button className="buy loot-ok" onClick={close}>عالی!</button>
              </div>
            )}
          </div>,
          document.querySelector(".app") ?? document.body,
        );
      })()}
    </div>
  );
}
