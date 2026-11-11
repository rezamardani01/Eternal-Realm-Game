// A fight as a staged battle: a torch-lit arena, the foe on a far platform and the hero on a near one, both breathing.
// Every move is played out: the hero lunges and a slash cuts the foe (or a spell orb flies and bursts, or a shield dome
// rises), the foe is knocked back and the camera shakes, then the foe strikes back and the screen flashes red. HP bars
// drain with a lagging ghost, each round is announced, and the end is a victory or defeat banner.
import { useQuery } from "@tanstack/react-query";
import { type CSSProperties, useEffect, useRef, useState } from "react";
import { Art, Burst } from "../components/Art";
import { Button, Icon, Inline, Sheet } from "../components/ui";
import { call } from "../lib/api";
import { haptic } from "../lib/bale";
import { fa } from "../lib/format";
import { iconFor, iconOfEmoji, ui } from "../lib/icons";
import type { Shown } from "../lib/types";
import { useApp } from "../store";

interface Fighter { name: string; emoji: string; hp: number; max_hp: number; shield: boolean }
interface FightState {
  title: string; kind: string; round: number; max_rounds: number; hero: Fighter; foe: Fighter;
  skill: { name: string; emoji: string; wait: number }; warn: string;
}
interface Answer { fight: FightState | null; shown?: Shown }
type Move = "attack" | "skill" | "defend" | "flee";
interface Fx { move?: Move; foeHit?: number; heroHit?: number; blocked?: boolean; crit?: boolean; key: number; stage: 0 | 1 | 2 }

const clean = (text: string) => text.replace(/^[•\s]+/, "");

function Plate({ who, f, hp, side }: { who: string; f: Fighter; hp: number; side: "foe" | "me" }) {
  const percent = Math.max(0, Math.min(100, (100 * hp) / Math.max(1, f.max_hp)));
  return (
    <div className={`bt-plate ${side}`}>
      <div className="bt-plate-top"><b className="ellipsis">{who}</b><span className="num">{fa(hp)}<small>/{fa(f.max_hp)}</small></span></div>
      <div className="bt-hp"><i className="ghost" style={{ width: `${percent}%` }} /><i className="live" style={{ width: `${percent}%` }} /></div>
      {f.shield && <span className="bt-shield-tag"><Icon name={ui("ui.defense")} />سپر</span>}
    </div>
  );
}

export default function Battle({ onClose, onFinish }: { onClose: () => void; onFinish: (shown: Shown) => void }) {
  const app = useApp();
  const first = useQuery({ queryKey: ["fight"], queryFn: () => call<Answer>("fight"), staleTime: 0, gcTime: 0 });
  const [state, setState] = useState<FightState | null>(null);
  const [hp, setHp] = useState<{ hero: number; foe: number } | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [fx, setFx] = useState<Fx>({ key: 0, stage: 0 });
  const [banner, setBanner] = useState<{ text: string; key: number; end?: "win" | "lose" } | null>(null);
  const [fleeing, setFleeing] = useState(false);
  const stamp = useRef(0);
  const timers = useRef<number[]>([]);
  const stage = useRef<HTMLDivElement>(null);
  const fight = state ?? first.data?.fight ?? null;
  const later = (ms: number, fn: () => void) => { timers.current.push(window.setTimeout(fn, ms)); };
  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), []);
  useEffect(() => {
    if (fight && !hp) setHp({ hero: fight.hero.hp, foe: fight.foe.hp });
    if (first.data?.fight && !state) setBanner({ text: `دور ${fa(first.data.fight.round)}`, key: ++stamp.current });
  }, [first.data]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {  // the camera shakes on a heavy blow (restarting the animation without rebuilding the scene)
    const el = stage.current;
    if (!el || !((fx.stage === 1 && fx.crit) || (fx.stage === 2 && fx.heroHit))) return;
    el.classList.remove("shake");
    void el.offsetWidth;
    el.classList.add("shake");
  }, [fx]);

  const act = async (move: Move) => {
    if (busy || !fight) return;
    setBusy(true);
    haptic("tap");
    const key = ++stamp.current;
    if (move !== "flee") setFx({ move, key, stage: 0 });
    try {
      const answer = await call<Answer>("fight", { action: move });
      const lines = (answer.shown?.text ?? "").split("\n").filter((line) => line.trim().startsWith("•")).map(clean);
      if (lines.length) setLog(lines.slice(-3));
      const next = answer.fight;
      const foeLost = next ? fight.foe.hp - next.foe.hp : fight.foe.hp;
      const heroLost = next ? fight.hero.hp - next.hero.hp : 0;
      // the blow lands
      later(320, () => {
        if (foeLost > 0) haptic("success");
        setFx({ move, key, stage: 1, foeHit: foeLost > 0 ? foeLost : undefined, crit: foeLost > fight.foe.max_hp * 0.2 });
        setHp((h) => ({ hero: h?.hero ?? fight.hero.hp, foe: next ? next.foe.hp : 0 }));
      });
      if (!next) {
        const won = /پیروز|بردید|شکست دادید/.test(answer.shown?.text ?? "") || foeLost >= fight.foe.hp;
        later(900, () => { haptic(won ? "success" : "error"); setBanner({ text: won ? "پیروزی!" : "پایان نبرد", key: ++stamp.current, end: won ? "win" : "lose" }); });
        if (answer.shown) later(2300, () => onFinish(answer.shown!));
        return;
      }
      // the answer comes back
      later(900, () => {
        if (heroLost > 0) haptic("error");
        setFx({ move, key, stage: 2, heroHit: heroLost > 0 ? heroLost : undefined, blocked: heroLost <= 0 && move === "defend" });
        setHp({ hero: next.hero.hp, foe: next.foe.hp });
      });
      later(1450, () => {
        setState(next);
        if (next.round !== fight.round) setBanner({ text: `دور ${fa(next.round)}`, key: ++stamp.current });
      });
    } catch (error) {
      app.toast(error instanceof Error ? error.message.replace(/\p{Extended_Pictographic}️?/gu, "").trim() : "نشد", true);
    } finally {
      later(1500, () => setBusy(false));
    }
  };

  if (first.isSuccess && !fight) {
    return (
      <div className="overlay">
        <div className="topbar"><button className="round-btn" onClick={onClose}><Icon name={ui("ui.back")} /></button><h2>میدان نبرد</h2><span style={{ width: 40 }} /></div>
        <div className="body"><div className="window" style={{ textAlign: "center" }}>
          <Icon name={ui("ui.swords")} size={52} tone="muted" />
          <p style={{ margin: "10px 0 14px" }}>الان نبردی در جریان نیست.</p>
          <Button kind="gold" onClick={() => { onClose(); app.open("trip"); }}>رفتن به سفر قهرمان</Button>
        </div></div>
      </div>
    );
  }

  const heroIcon = iconFor("class", app.me.player.class.id, app.me.player.class.emoji);
  const foeIcon = fight ? iconOfEmoji(fight.foe.emoji) || ui("ui.skull") : ui("ui.skull");
  const skillIcon = (fight && iconOfEmoji(fight.skill.emoji)) || ui("ui.magic");
  const heroAnim = fx.stage === 0 && fx.move ? `do-${fx.move}` : fx.stage === 2 && fx.heroHit ? "is-hit" : "";
  const foeAnim = fx.stage === 1 && fx.foeHit ? "is-hit" : fx.stage === 2 && (fx.heroHit || fx.blocked) ? "do-attack" : "";
  const shown = hp ?? (fight ? { hero: fight.hero.hp, foe: fight.foe.hp } : null);
  return (
    <div className="overlay bt">
      <div className="topbar">
        <button className="round-btn" onClick={onClose} aria-label="بستن"><Icon name={ui("ui.back")} /></button>
        <h2 className="ellipsis">{fight?.title.replace(/^.*·\s*/, "") ?? "نبرد"}</h2>
        <span className="bt-round num">دور {fa(fight?.round ?? 1)}/{fa(fight?.max_rounds ?? 0)}</span>
      </div>
      <div className="bt-stage" ref={stage}>
        <div className="bt-sky"><span className="bt-moon" /></div>
        <div className="bt-hills" />
        <div className="bt-ground" />
        <span className="bt-torch l"><i /></span><span className="bt-torch r"><i /></span>
        <div className="bt-fog" />
        {fx.stage === 2 && fx.heroHit && <div className="bt-flash" key={`f${fx.key}`} />}

        {fight && shown && (
          <>
            <Plate who={fight.foe.name} f={fight.foe} hp={shown.foe} side="foe" />
            <div className={`bt-fighter foe ${foeAnim}`} key={`foe-${foeAnim}-${fx.key}`}>
              <span className="bt-pad" /><span className="bt-ring" />
              <span className="bt-body"><Art icon={foeIcon} size={112} gem="ruby" /></span>
              {fx.stage >= 1 && fx.foeHit && fx.move === "attack" && <span className="bt-slash" key={`sl${fx.key}`} />}
              {fx.stage >= 1 && fx.foeHit && fx.move === "skill" && <span className="bt-boom" key={`bo${fx.key}`} />}
              {fx.stage >= 1 && fx.foeHit && <span className={`bt-dmg ${fx.crit ? "crit" : ""}`} key={`fd${fx.key}`}>{fx.crit && <small>ضربه‌ی کاری!</small>}-{fa(fx.foeHit)}</span>}
            </div>
            {fx.stage === 0 && fx.move === "skill" && <span className="bt-orb" key={`orb${fx.key}`}><Art icon={skillIcon} size={44} gem="amethyst" /></span>}
            <div className={`bt-fighter me ${heroAnim}`} key={`me-${heroAnim}-${fx.key}`}>
              <span className="bt-pad" /><span className="bt-ring" />
              <span className="bt-body"><Art icon={heroIcon} size={104} gem="gold" /></span>
              {(fx.move === "defend" || fight.hero.shield) && fx.stage <= 2 && fx.move === "defend" && <span className="bt-dome" key={`dm${fx.key}`} />}
              {fx.stage === 2 && fx.heroHit && <span className="bt-slash rev" key={`hs${fx.key}`} />}
              {fx.stage === 2 && fx.heroHit && <span className="bt-dmg hurt" key={`hd${fx.key}`}>-{fa(fx.heroHit)}</span>}
              {fx.stage === 2 && fx.blocked && <span className="bt-dmg block" key={`bl${fx.key}`}>دفع شد!</span>}
            </div>
            <Plate who={fight.hero.name} f={fight.hero} hp={shown.hero} side="me" />
          </>
        )}
        {fight?.warn && <div className="bt-warn"><Icon name={ui("ui.skull")} />{fight.warn}؛ بهتر است دفاع کنید!</div>}
        {banner && (
          <div className={`bt-banner ${banner.end ?? ""}`} key={banner.key} onAnimationEnd={() => !banner.end && setBanner(null)}>
            {banner.end === "win" && <Burst count={36} />}
            <span>{banner.text}</span>
          </div>
        )}
      </div>

      {log.length > 0 && <div className="bt-log" key={log.join("|")}>{log.map((line, i) => <div key={i} style={{ "--i": i } as CSSProperties}><Inline text={line} /></div>)}</div>}
      <div className="bt-acts">
        <button className="bt-act guard" disabled={busy} onClick={() => act("defend")}><span className="bt-disc"><Art icon={ui("ui.defense")} size={34} gem="sapphire" /></span>دفاع</button>
        <button className="bt-act strike" disabled={busy} onClick={() => act("attack")}><span className="bt-disc"><Art icon={ui("ui.swords")} size={46} gem="silver" /></span>حمله</button>
        <button className="bt-act cast" disabled={busy || (fight?.skill.wait ?? 0) > 0} onClick={() => act("skill")}>
          <span className="bt-disc" style={{ "--cd": `${fight && fight.skill.wait > 0 ? 100 : 0}%` } as CSSProperties}>
            <Art icon={skillIcon} size={34} gem="amethyst" />
            {fight && fight.skill.wait > 0 && <b className="bt-cd num">{fa(fight.skill.wait)}</b>}
          </span>
          <span className="ellipsis">{fight?.skill.name ?? "مهارت"}</span>
        </button>
        <button className="bt-act run" disabled={busy} onClick={() => setFleeing(true)}><span className="bt-disc"><Icon name={ui("ui.flee")} /></span>فرار</button>
      </div>
      {fleeing && (
        <Sheet onClose={() => setFleeing(false)}>
          <h3 className="title gold-text" style={{ textAlign: "center" }}>فرار از نبرد</h3>
          <p style={{ textAlign: "center", margin: "6px 0 14px" }}>اگر فرار کنید پاداشی نمی‌گیرید و انرژی برنمی‌گردد.</p>
          <div className="row"><Button kind="danger" onClick={async () => { setFleeing(false); await act("flee"); }}>بله، فرار</Button><Button kind="gold" onClick={() => setFleeing(false)}>می‌جنگم</Button></div>
        </Sheet>
      )}
    </div>
  );
}
