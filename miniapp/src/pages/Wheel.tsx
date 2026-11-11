// The wheel of fortune as a wheel: it turns, slows and stops under the pin on the prize the server drew.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import { Button, Emblem, Icon, Sheet, Skeleton } from "../components/ui";
import { call } from "../lib/api";
import { haptic } from "../lib/bale";
import { fa } from "../lib/format";
import { iconFor, iconOfEmoji, ui } from "../lib/icons";
import type { ItemInfo } from "../lib/types";
import { useApp } from "../store";

interface Slice { id: string; emoji: string; label: string; jackpot: boolean; item: ItemInfo | null; gold: number; crystal: number }
interface WheelData { spins: number; free: boolean; slices: Slice[]; free_slices: Slice[]; packs: { id: string; spins: number; toman: number; save: number }[] }

const SEGMENTS = 10;
const COLORS = ["#3a6bb5", "#142642", "#a8792a", "#142642", "#7a2424", "#142642", "#1f6a4a", "#142642", "#1f547a", "#142642"];

const pictureOf = (slice: Slice) =>
  slice.item ? iconFor("item", slice.item.id, slice.item.emoji) : slice.crystal && !slice.gold ? ui("ui.crystal") : slice.gold ? ui("ui.gold") : iconOfEmoji(slice.emoji) || ui("ui.gift");

/** The few characters that fit on a face of the wheel: an amount, never a sentence. */
function short(slice: Slice): string {
  const amount = slice.item ? 0 : slice.crystal && !slice.gold ? slice.crystal : slice.gold;
  if (amount >= 1000) return `${fa(Math.round(amount / 1000))} هزار`;
  if (amount > 0) return fa(amount);
  const count = slice.label.match(/×\s*([\d۰-۹]+)/);
  return count ? `×${fa(count[1])}` : "";
}

/** Ten faces for the wheel: the showiest prizes of the table, with the drawn prize put among them when there is one. */
function faces(table: Slice[], prize?: Slice): Slice[] {
  const seen = new Set<string>();
  const out: Slice[] = [];
  for (const slice of [...table].sort((a, b) => Number(b.jackpot) - Number(a.jackpot))) {
    const key = pictureOf(slice) + (slice.jackpot ? "!" : "");
    if (seen.has(key) && out.length + (table.length - seen.size) > SEGMENTS) continue;
    seen.add(key);
    out.push(slice);
    if (out.length === SEGMENTS) break;
  }
  while (out.length < SEGMENTS) out.push(table[out.length % table.length]);
  if (prize && !out.some((s) => s.id === prize.id)) out[3] = prize;
  return out;
}

export default function Wheel({ onClose }: { onClose: () => void }) {
  const app = useApp();
  const client = useQueryClient();
  const wheel = useQuery({ queryKey: ["wheel"], queryFn: () => call<WheelData>("wheel"), staleTime: 0 });
  const [shownFaces, setShownFaces] = useState<Slice[] | null>(null);
  const [turn, setTurn] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const [prize, setPrize] = useState<Slice | null>(null);
  const turns = useRef(0);

  const list = useMemo(() => shownFaces ?? (wheel.data ? faces(wheel.data.slices) : []), [shownFaces, wheel.data]);

  const spin = async (free: boolean) => {
    if (spinning || !wheel.data) return;
    setSpinning(true);
    try {
      const result = await call<{ prize: Slice; left: number }>("wheel", { free });
      const next = faces(free ? wheel.data.free_slices : wheel.data.slices, result.prize);
      setShownFaces(next);
      const index = next.findIndex((s) => s.id === result.prize.id);
      turns.current += 6;
      const step = 360 / SEGMENTS;
      // the pin is at the top: turn until the middle of the prize's face stands under it
      setTurn(turns.current * 360 - index * step - step / 2 + (Math.random() - 0.5) * step * 0.5);
      haptic("tap");
      window.setTimeout(() => {
        setPrize(result.prize);
        setSpinning(false);
        haptic("success");
        void client.invalidateQueries();
      }, 5400);
    } catch (error) {
      setSpinning(false);
      app.toast(error instanceof Error ? error.message : "نشد", true);
    }
  };

  const data = wheel.data;
  const canFree = Boolean(data?.free);
  const canPaid = Boolean(data && data.spins > 0);
  return (
    <div className="overlay">
      <div className="topbar">
        <button className="round-btn" onClick={onClose} aria-label="بستن"><Icon name={ui("ui.back")} /></button>
        <h2>گردونه شانس</h2>
        <span className="pill gold num small"><Icon name={ui("ui.ticket")} />{fa(data?.spins ?? 0)}</span>
      </div>
      <div className="body">
        {!data ? <Skeleton height={300} count={1} /> : (
          <>
            <div className="wheel-scene">
              <div className="beam" />
              <div className="wheel-pin" />
              <div className="wheel-rim">
                {Array.from({ length: 20 }, (_, i) => <i key={i} className="bulb" style={{ transform: `rotate(${i * 18}deg) translateY(calc(min(42vw, 170px) * -1 + 7px))` }} />)}
                <div className="wheel-disc" style={{ transform: `rotate(${turn}deg)`, background: `conic-gradient(${COLORS.map((c, i) => `${c} ${i * 36}deg ${(i + 1) * 36}deg`).join(",")})` }}>
                  {list.map((slice, i) => (
                    <div key={i} className="wheel-seg" style={{ transform: `rotate(${i * 36 + 18}deg)` }}>
                      <Icon name={pictureOf(slice)} tone={slice.jackpot ? "gold" : undefined} />
                      <span className="num">{short(slice)}</span>
                    </div>
                  ))}
                </div>
                <button className="wheel-hub" disabled={spinning || (!canFree && !canPaid)} onClick={() => spin(canFree)}>
                  {spinning ? "..." : "بچرخان"}
                </button>
              </div>
            </div>
            <p style={{ textAlign: "center", margin: "6px 0 12px" }} className="muted small">هیچ چرخشی پوچ نیست؛ هر بار جایزه می‌گیرید.</p>
            <div className="stack">
              {canFree && <Button kind="gold" busy={spinning} onClick={() => spin(true)}><Icon name={ui("ui.gift")} />چرخش رایگان امروز</Button>}
              {canPaid && <Button kind="primary" busy={spinning} onClick={() => spin(false)}><Icon name={ui("ui.wheel")} />بچرخان ({fa(data.spins)} فرصت)</Button>}
              {!canFree && !canPaid && <div className="window" style={{ textAlign: "center" }}>چرخش رایگان امروز را برداشته‌اید؛ فردا دوباره بیایید یا فرصت بخرید.</div>}
            </div>
            {data.packs.length > 0 && (
              <>
                <h3 className="section-title"><Icon name={ui("ui.ticket")} />خرید فرصت</h3>
                <div className="grid-2">
                  {data.packs.map((pack) => (
                    <button key={pack.id} className="tile" onClick={() => app.pay({ kind: "cash", id: pack.id })}>
                      <Emblem icon={ui("ui.wheel")} size={48} rarity={5} badge={fa(pack.spins)} />
                      <b>{fa(pack.spins)} فرصت</b>
                      <span className="pill gold num small">{fa(pack.toman)} تومان</span>
                      {pack.save > 0 && <span className="tag green">{fa(pack.save)}٪ ارزان‌تر</span>}
                    </button>
                  ))}
                </div>
              </>
            )}
            <div style={{ marginTop: 14 }}><Button onClick={() => app.open("wheelodds")}>جایزه‌ها و شانس‌ها</Button></div>
          </>
        )}
      </div>
      {prize && (
        <Sheet onClose={() => setPrize(null)}>
          <div className="prize-burst">
            <div className="rays" />
            <div className="pop"><Emblem icon={pictureOf(prize)} size={110} rarity={prize.jackpot ? 6 : 5} round /></div>
          </div>
          <h2 className="title gold-text" style={{ textAlign: "center", fontSize: 26 }}>{prize.jackpot ? "جکپات! جایزه‌ی بزرگ" : "تبریک فرمانده!"}</h2>
          <p style={{ textAlign: "center", margin: "4px 0 14px", fontWeight: 800 }}>{prize.label}</p>
          <Button kind="gold" onClick={() => setPrize(null)}>به کیفم رسید</Button>
        </Sheet>
      )}
    </div>
  );
}
