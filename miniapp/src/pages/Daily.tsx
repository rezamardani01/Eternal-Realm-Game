// «هدیه روزانه»: a week of gifts laid out as a calendar. Today's box glows and bounces; opening it throws the gold out
// with a shower of sparks, and the week's seventh day is a big chest worth coming back for.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type CSSProperties, useState } from "react";
import { Art, Burst } from "../components/Art";
import { Chest, lookOf } from "../components/Chest";
import { Icon, iconUrl, Skeleton } from "../components/ui";
import { call } from "../lib/api";
import { haptic } from "../lib/bale";
import { duration, fa } from "../lib/format";
import { iconFor, ui } from "../lib/icons";
import type { ItemInfo } from "../lib/types";
import { useApp } from "../store";

interface Day { day: number; gold: number; chest: ItemInfo | null; crystal: number; state: "claimed" | "today" | "next" | "locked" }
interface DailyData { ready: boolean; streak: number; days: Day[]; next_in: number; rescue: { streak: number; cost: number } | null }
interface Won { gold: number; streak: number; crystal: number; chest: ItemInfo | null }

export default function Daily({ onClose }: { onClose: () => void }) {
  const app = useApp();
  const client = useQueryClient();
  const data = useQuery({ queryKey: ["daily"], queryFn: () => call<DailyData>("daily") });
  const [won, setWon] = useState<Won | null>(null);
  const [busy, setBusy] = useState(false);

  const claim = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const prize = await call<Won>("daily", {});
      haptic("success");
      setWon(prize);
      void client.invalidateQueries({ queryKey: ["daily"] });
      void app.refresh();
    } catch (error) {
      app.toast(error instanceof Error ? error.message : "هدیه باز نشد.", true);
    } finally {
      setBusy(false);
    }
  };

  const d = data.data;
  return (
    <div className="gift-room" onClick={onClose}>
      <div className="gift-card" onClick={(event) => event.stopPropagation()}>
        <button className="round-btn gift-x" onClick={onClose} aria-label="بستن"><Icon name={ui("ui.close")} /></button>
        <div className="gift-crest"><Art icon={ui("ui.gift")} size={74} gem="ruby" /></div>
        <div className="daily">
          <h3>هدیه روزانه</h3>
          {!d ? <Skeleton height={70} count={2} /> : won ? (
            <>
              <div className="win">
                <span className="rays" />
                <Burst />
                <span className="pop" style={{ display: "flex", alignItems: "flex-end", gap: 4 }}>
                  {won.chest && <Chest look={lookOf(won.chest.id)} state="open" size={110} />}
                  <Art icon={ui("ui.gold")} size={won.chest ? 70 : 104} gem="gold" />
                  {won.crystal > 0 && <Art icon={ui("ui.crystal")} size={60} gem="sapphire" />}
                </span>
              </div>
              <div className="gift-sum">
                <span className="pill gold num"><Icon name={ui("ui.gold")} />+{fa(won.gold)}</span>
                {won.crystal > 0 && <span className="pill gold num"><Icon name={ui("ui.crystal")} />+{fa(won.crystal)}</span>}
                {won.chest && <span className="pill gold"><Icon name={iconFor("item", won.chest.id, won.chest.emoji)} />{won.chest.name}</span>}
              </div>
              <p className="streak-line">زنجیره‌ی <b className="num">{fa(won.streak)}</b> روزه · فردا بیشتر می‌گیرید</p>
              <button className="buy" onClick={onClose}>عالی!</button>
            </>
          ) : (
            <>
              <p className="streak-line">{d.streak ? <>زنجیره‌ی <b className="num">{fa(d.streak)}</b> روزه؛ هر روز هدیه‌ی بزرگ‌تری</> : "هر روز سر بزنید، هر روز هدیه‌ی بزرگ‌تری"}</p>
              <div className="cal">
                {d.days.map((day, i) => {
                  const last = i === d.days.length - 1;
                  return (
                    <div key={day.day} className={`day ${day.state} ${last ? "big" : ""}`} style={{ "--i": i, "--check": iconUrl(ui("ui.check")) } as CSSProperties}>
                      <span className="n">روز {fa(day.day)}</span>
                      <span style={{ display: "flex", alignItems: "flex-end" }}>
                        {day.chest && <Art icon={iconFor("item", day.chest.id, day.chest.emoji)} size={last ? 50 : 36} gem="bronze" />}
                        {!day.chest && <Art icon={ui(day.crystal ? "ui.crystal" : "ui.gold")} size={last ? 48 : 34} gem={day.crystal ? "sapphire" : "gold"} />}
                      </span>
                      <span className="g num">{fa(day.gold)}</span>
                      {day.state === "locked" && <Icon name={ui("ui.lock")} className="day-lock" />}
                    </div>
                  );
                })}
              </div>
              {d.ready ? (
                <button className="buy green big-buy" onClick={claim} disabled={busy}>{busy ? <span className="spinner" /> : "باز کردن هدیه امروز"}</button>
              ) : (
                <div className="gift-wait"><Icon name={ui("ui.clock")} />هدیه‌ی بعدی تا <b className="num">{duration(d.next_in)}</b> دیگر</div>
              )}
              {d.rescue && (
                <button className="gift-rescue" onClick={() => app.open("rescue")}>
                  <Art icon={ui("ui.clock")} size={30} gem="fire" />
                  <span>زنجیره‌ی {fa(d.rescue.streak)} روزه‌تان در خطر است · نجات با {fa(d.rescue.cost)} کریستال</span>
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
