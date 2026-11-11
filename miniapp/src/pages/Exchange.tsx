// «مرکز مبادله»: a pair of golden scales. Gold sits in one pan and crystals in the other; the beam tips toward what you
// give, the amount is set with a slider and quick steps, and a trade sends the coins flying across the beam.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type CSSProperties, useState } from "react";
import { Art, Burst, Pile } from "../components/Art";
import { Icon, Skeleton } from "../components/ui";
import { call } from "../lib/api";
import { haptic } from "../lib/bale";
import { fa } from "../lib/format";
import { ui } from "../lib/icons";
import { useApp } from "../store";

interface ExchangeData { rate: number; fee_percent: number; max: number; left_today: number; gold: number; crystal: number }
type Side = "buy" | "sell";

export default function Exchange({ onClose }: { onClose: () => void }) {
  const app = useApp();
  const client = useQueryClient();
  const data = useQuery({ queryKey: ["exchange"], queryFn: () => call<ExchangeData>("exchange") });
  const [side, setSide] = useState<Side>("buy");
  const [amount, setAmount] = useState(1);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(0);  // a counter: each trade replays the celebration

  const d = data.data;
  const fee = d ? Math.ceil((amount * d.rate * d.fee_percent) / 100) : 0;
  const gold = d ? (side === "buy" ? amount * d.rate + fee : amount * d.rate - fee) : 0;
  const top = d ? Math.max(1, side === "buy" ? Math.min(d.max, d.left_today, Math.floor(d.gold / (d.rate + Math.ceil((d.rate * d.fee_percent) / 100)))) : Math.min(d.max, d.crystal)) : 1;
  const value = Math.min(amount, top);
  const blocked = !d || (side === "buy" ? d.left_today < 1 || d.gold < gold : d.crystal < 1);

  const flip = () => { haptic(); setSide(side === "buy" ? "sell" : "buy"); setAmount(1); };
  const step = (delta: number) => { haptic(); setAmount(Math.max(1, Math.min(top, value + delta))); };
  const trade = async () => {
    if (busy || blocked) return;
    setBusy(true);
    try {
      const quote = await call<{ crystals: number; gold: number }>("exchange", { side, amount: value });
      haptic("success");
      setDone((n) => n + 1);
      app.toast(side === "buy" ? `${fa(quote.crystals)} کریستال گرفتید و ${fa(quote.gold)} سکه دادید` : `${fa(quote.crystals)} کریستال دادید و ${fa(quote.gold)} سکه گرفتید`);
      await client.invalidateQueries({ queryKey: ["exchange"] });
      void app.refresh();
      setAmount(1);
    } catch (error) {
      app.toast(error instanceof Error ? error.message : "مبادله انجام نشد.", true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bourse">
      <div className="g-title">
        <button className="g-back" onClick={onClose} aria-label="بستن"><Icon name={ui("ui.back")} /></button>
        <h2>مرکز مبادله</h2>
      </div>
      {!d ? <div style={{ padding: 16 }}><Skeleton height={120} count={2} /></div> : (
        <div className="bourse-body">
          <div className="wallet-row">
            <span className="pill gold num"><Icon name={ui("ui.gold")} />{fa(d.gold)}</span>
            <span className="pill gold num"><Icon name={ui("ui.crystal")} tone="sky" />{fa(d.crystal)}</span>
          </div>

          <div className={`scales tilt-${side}`}>
            <span className="scales-glow" />
            <div className="scales-post"><span className="scales-top"><Art icon={ui("ui.exchange")} size={46} gem="gold" /></span></div>
            <div className="scales-beam">
              <div className="pan pan-gold">
                <span className="chain" /><span className="dish" />
                <Pile icon={ui("ui.gold")} count={Math.min(3, 1 + Math.floor((3 * value) / Math.max(1, top)))} size={40} gem="gold" />
              </div>
              <div className="pan pan-crystal">
                <span className="chain" /><span className="dish" />
                <Pile icon={ui("ui.crystal")} count={Math.min(3, 1 + Math.floor((3 * value) / Math.max(1, top)))} size={38} gem="sapphire" />
              </div>
            </div>
            {done > 0 && <span key={done} className="scales-fly"><Burst count={22} /></span>}
          </div>

          <div className="ex-switch">
            <button className={side === "buy" ? "on" : ""} onClick={() => side !== "buy" && flip()}>
              <Icon name={ui("ui.gold")} />سکه بده، کریستال بگیر
            </button>
            <button className="ex-flip" onClick={flip} aria-label="برعکس"><Icon name={ui("ui.exchange")} tone="ink" /></button>
            <button className={side === "sell" ? "on" : ""} onClick={() => side !== "sell" && flip()}>
              <Icon name={ui("ui.crystal")} tone="sky" />کریستال بده، سکه بگیر
            </button>
          </div>

          <div className="ex-amount">
            <div className="ex-big num" key={value}>{fa(value)}<small> کریستال</small></div>
            <input className="ex-range" type="range" min={1} max={top} value={value} onChange={(event) => setAmount(Number(event.target.value))}
              style={{ "--fill": `${top > 1 ? ((value - 1) * 100) / (top - 1) : 100}%` } as CSSProperties} />
            <div className="ex-steps">
              {[-10, -1, 1, 10].map((delta) => <button key={delta} className="ex-step num" onClick={() => step(delta)}>{delta > 0 ? "+" : "−"}{fa(Math.abs(delta))}</button>)}
              <button className="ex-step max" onClick={() => { haptic(); setAmount(top); }}>حداکثر</button>
            </div>
          </div>

          <div className="ex-quote">
            <div className="ex-side give">
              <small>می‌دهید</small>
              {side === "buy"
                ? <b className="num"><Art icon={ui("ui.gold")} size={28} gem="gold" />{fa(gold)}</b>
                : <b className="num"><Art icon={ui("ui.crystal")} size={28} gem="sapphire" />{fa(value)}</b>}
            </div>
            <span className="ex-arrow"><Icon name={ui("ui.pointer")} /></span>
            <div className="ex-side get">
              <small>می‌گیرید</small>
              {side === "buy"
                ? <b className="num"><Art icon={ui("ui.crystal")} size={28} gem="sapphire" />{fa(value)}</b>
                : <b className="num"><Art icon={ui("ui.gold")} size={28} gem="gold" />{fa(gold)}</b>}
            </div>
          </div>
          <p className="ex-note">
            نرخ پایه: هر کریستال {fa(d.rate)} سکه · کارمزد {fa(d.fee_percent)}٪ ({fa(fee)} سکه)
            {side === "buy" && <> · سقف خرید امروز: {fa(d.left_today)} کریستال</>}
          </p>
          <button className={`buy ${side === "sell" ? "green" : ""} ex-go`} onClick={trade} disabled={busy || blocked}>
            {busy ? <span className="spinner" /> : blocked ? (side === "buy" ? (d.left_today < 1 ? "سقف امروز پر شده" : "سکه کافی ندارید") : "کریستالی ندارید") : "مبادله کن"}
          </button>
        </div>
      )}
    </div>
  );
}
