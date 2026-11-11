// «کوره‌ی آهنگری»: a smithy. A hearth glows on the wall, the chosen blueprint floats over the anvil, the recipes sit on a
// strip below and each material is a slot that shows what you have against what it takes. Forging swings the hammer four
// times with sparks flying, then the new piece rises in a burst of light.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type CSSProperties, useState } from "react";
import { Art, Burst, type Gem } from "../components/Art";
import { Icon, Skeleton } from "../components/ui";
import { call } from "../lib/api";
import { haptic } from "../lib/bale";
import { fa } from "../lib/format";
import { iconFor, leading, ui } from "../lib/icons";
import type { ItemInfo } from "../lib/types";
import { useApp } from "../store";

interface Need { item: ItemInfo; have: number; need: number; base: boolean }
interface Recipe { id: string; result: ItemInfo; stats: string[]; needs: Need[]; gold: number; gold_have: number; owned: boolean; ready: boolean }

const GEM_BY_RARITY: Gem[] = ["silver", "silver", "emerald", "sapphire", "amethyst", "gold", "ruby"];
const STRIKE_MS = 1750;

function Anvil() {
  return (
    <svg viewBox="0 0 220 120" aria-hidden>
      <defs>
        <linearGradient id="anv" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#8a90a8" /><stop offset="0.4" stopColor="#4a4e62" /><stop offset="1" stopColor="#22242e" /></linearGradient>
        <linearGradient id="anv-top" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#c8ccdc" /><stop offset="0.5" stopColor="#ffffff" /><stop offset="1" stopColor="#9aa0b8" /></linearGradient>
        <linearGradient id="stump" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#8a5a2a" /><stop offset="1" stopColor="#3a2410" /></linearGradient>
      </defs>
      <ellipse cx="110" cy="114" rx="90" ry="8" fill="#000" opacity="0.5" />
      <path d="M62 78 H158 L166 114 H54 Z" fill="url(#stump)" stroke="#1e0e04" strokeWidth="3" />
      <path d="M70 90 H150 M66 102 H154" stroke="#1e0e04" strokeOpacity="0.4" strokeWidth="2" />
      <path d="M20 18 H190 Q206 18 206 30 L180 34 Q160 36 150 48 L142 60 H78 L70 48 Q60 36 40 34 L4 26 Q8 18 20 18 Z" fill="url(#anv)" stroke="#12131a" strokeWidth="3" />
      <path d="M22 18 H188 Q200 18 202 24 H10 Q14 18 22 18 Z" fill="url(#anv-top)" />
      <path d="M78 60 H142 L150 80 H70 Z" fill="url(#anv)" stroke="#12131a" strokeWidth="3" />
      <path d="M96 30 h8 M120 30 h6" stroke="#fff" strokeOpacity="0.4" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function Hammer() {
  return (
    <svg className="forge-hammer" viewBox="0 0 70 110" aria-hidden>
      <defs><linearGradient id="ham" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#6a6e82" /><stop offset="0.5" stopColor="#e2e6f0" /><stop offset="1" stopColor="#5a5e72" /></linearGradient></defs>
      <rect x="31" y="22" width="9" height="86" rx="4" fill="#8a5a2a" stroke="#2a1404" strokeWidth="2.5" />
      <rect x="31" y="70" width="9" height="6" fill="#c9922e" /><rect x="31" y="84" width="9" height="6" fill="#c9922e" />
      <rect x="6" y="4" width="58" height="26" rx="5" fill="url(#ham)" stroke="#12131a" strokeWidth="3" />
      <rect x="8" y="6" width="54" height="6" rx="3" fill="#fff" opacity="0.4" />
    </svg>
  );
}

export default function Forge({ onClose }: { onClose: () => void }) {
  const app = useApp();
  const client = useQueryClient();
  const data = useQuery({ queryKey: ["forge"], queryFn: () => call<{ recipes: Recipe[] }>("forge") });
  const [picked, setPicked] = useState("");
  const [striking, setStriking] = useState(false);
  const [made, setMade] = useState<{ item: ItemInfo; stats: string[] } | null>(null);
  const recipes = data.data?.recipes ?? [];
  const r = recipes.find((x) => x.id === picked) ?? recipes.find((x) => x.ready) ?? recipes[0];

  const forge = async () => {
    if (!r || !r.ready || striking) return;
    setStriking(true);
    haptic("tap");
    const began = performance.now();
    try {
      const out = await call<{ item: ItemInfo; stats: string[] }>("forge", { id: r.id });
      for (let i = 1; i < 4; i++) window.setTimeout(() => haptic("tap"), i * 420);
      await new Promise((done) => window.setTimeout(done, Math.max(0, STRIKE_MS - (performance.now() - began))));
      haptic("success");
      setMade(out);
      await client.invalidateQueries({ queryKey: ["forge"] });
      void app.refresh();
    } catch (error) {
      app.toast(error instanceof Error ? error.message : "ساخته نشد", true);
    } finally {
      setStriking(false);
    }
  };

  return (
    <div className={`forge ${striking ? "striking" : ""}`}>
      <div className="g-title">
        <button className="g-back" onClick={onClose} aria-label="بستن"><Icon name={ui("ui.back")} /></button>
        <h2>کوره‌ی آهنگری</h2>
        <span className="g-purse num"><Icon name={ui("ui.gold")} />{fa(app.me.player.gold)}</span>
      </div>
      <div className="forge-body">
        <div className="forge-stage">
          <div className="forge-wall" />
          <div className="forge-hearth" />
          <span className="embers2">{Array.from({ length: 12 }, (_, i) => <i key={i} style={{ "--i": i, left: `${(i * 37 + 7) % 100}%` } as CSSProperties} />)}</span>
          <div className="forge-anvil">
            <Anvil />
            {r && <span className="forge-item" key={r.id}><Art icon={iconFor("item", r.result.id, r.result.emoji)} size={84} gem={GEM_BY_RARITY[r.result.rarity] ?? "gold"} /></span>}
            <span className="forge-sparks">{Array.from({ length: 12 }, (_, i) => <i key={i} style={{ "--i": i, "--a": `${190 + i * 15}deg` } as CSSProperties} />)}</span>
            <Hammer />
          </div>
        </div>
        {!r ? <div style={{ padding: 14 }}><Skeleton height={80} count={2} /></div> : (
          <>
            <div className="forge-recipes">
              {recipes.map((x, i) => (
                <button key={x.id} className={`recipe ${x.id === r.id ? "on" : ""} ${x.ready ? "ready" : ""} ${x.owned ? "owned" : ""}`} style={{ "--i": i } as CSSProperties} onClick={() => { haptic(); setPicked(x.id); }}>
                  <Art icon={iconFor("item", x.result.id, x.result.emoji)} size={40} gem={GEM_BY_RARITY[x.result.rarity] ?? "gold"} />
                  <span>{x.result.name}</span>
                </button>
              ))}
            </div>
            <div className="forge-card" key={r.id}>
              <h3>{r.result.name}</h3>
              <span className="rarity-pill">{r.result.rarity_name}</span>
              <div className="forge-stats">{r.stats.map((s) => <span key={s}>{leading(s).rest}</span>)}</div>
              <div className="needs">
                {r.needs.map((n) => (
                  <div key={n.item.id} className={`need ${n.have >= n.need ? "ok" : ""}`}>
                    <span className="need-mark"><Icon name={ui(n.have >= n.need ? "ui.check" : "ui.close")} /></span>
                    <Art icon={iconFor("item", n.item.id, n.item.emoji)} size={34} gem={GEM_BY_RARITY[n.item.rarity] ?? "silver"} />
                    <b className="num">{n.base ? (n.have ? "آماده" : "ندارید") : `${fa(Math.min(n.have, 999))}/${fa(n.need)}`}</b>
                    <small>{n.item.name}</small>
                  </div>
                ))}
                <div className={`need ${r.gold_have >= r.gold ? "ok" : ""}`}>
                  <span className="need-mark"><Icon name={ui(r.gold_have >= r.gold ? "ui.check" : "ui.close")} /></span>
                  <Art icon={ui("ui.gold")} size={34} gem="gold" />
                  <b className="num">{fa(r.gold)}</b><small>سکه</small>
                </div>
              </div>
              <button className={`g-btn big forge-go ${r.ready ? "red" : ""}`} disabled={!r.ready || striking} onClick={forge}>
                <Art icon={ui("ui.anvil")} size={28} gem="silver" />
                {r.owned ? "این را دارید" : r.ready ? "بکوب و بساز!" : "منابع کافی نیست"}
              </button>
            </div>
          </>
        )}
      </div>
      {made && (
        <div className="forge-made" onClick={() => setMade(null)}>
          <span className="chest-rays big" />
          <Burst count={40} />
          <div>
            <Art icon={iconFor("item", made.item.id, made.item.emoji)} size={130} gem={GEM_BY_RARITY[made.item.rarity] ?? "gold"} />
            <h2>{made.item.name} ساخته شد!</h2>
            <span className="rarity-pill">{made.item.rarity_name}</span>
            <div className="forge-stats">{made.stats.map((s) => <span key={s}>{leading(s).rest}</span>)}</div>
            <div className="vault-acts">
              <button className="g-btn green" onClick={() => { setMade(null); app.open("gear"); }}>بپوشم</button>
              <button className="g-btn ghost" onClick={() => setMade(null)}>ادامه</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
