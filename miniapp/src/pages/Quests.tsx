// «مأموریت‌ها»: a quest board. Each mission is a parchment pinned to the wooden board with a wax seal that breaks when it
// is done; a finished one glows and its claim button throws coins. Below, the week's track: seven torches that light up
// day by day, with a chest waiting at days three, five and seven.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type CSSProperties, useState } from "react";
import { Art, Burst } from "../components/Art";
import { Chest, lookOf } from "../components/Chest";
import { Icon, Skeleton } from "../components/ui";
import { openScreen, call } from "../lib/api";
import { haptic } from "../lib/bale";
import { duration, fa } from "../lib/format";
import { iconOfEmoji, ui } from "../lib/icons";
import type { ItemInfo } from "../lib/types";
import { useApp } from "../store";

interface Quest { slot: number; emoji: string; title: string; progress: number; target: number; gold: number; claimed: boolean; done: boolean; special: boolean }
interface Week { days: number; claimed: boolean; earned: number; left: number; prizes: { days: number; crystal: number; chest: ItemInfo }[] }

export default function Quests({ onClose }: { onClose: () => void }) {
  const app = useApp();
  const client = useQueryClient();
  const data = useQuery({ queryKey: ["missions"], queryFn: () => call<{ missions: Quest[]; week: Week }>("missions") });
  const [burst, setBurst] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const claim = async (screen: string, a = "", key = -1) => {
    if (busy) return;
    setBusy(true);
    try {
      const { shown } = await openScreen(screen, a);
      haptic("success");
      setBurst(key);
      if (shown.toast) app.toast(shown.toast.replace(/\p{Extended_Pictographic}️?/gu, "").trim());
      await client.invalidateQueries({ queryKey: ["missions"] });
      void app.refresh();
      window.setTimeout(() => setBurst(null), 1400);
    } catch (error) {
      app.toast(error instanceof Error ? error.message : "نشد", true);
    } finally {
      setBusy(false);
    }
  };

  const d = data.data;
  return (
    <div className="quests">
      <div className="g-title">
        <button className="g-back" onClick={onClose} aria-label="بستن"><Icon name={ui("ui.back")} /></button>
        <h2>تخته‌ی مأموریت‌ها</h2>
        <span className="g-purse num"><Icon name={ui("ui.gold")} />{fa(app.me.player.gold)}</span>
      </div>
      <div className="quests-body">
        <p className="q-note"><Icon name={ui("ui.clock")} />مأموریت‌ها هر نیمه‌شب عوض می‌شوند</p>
        {!d ? <Skeleton height={110} count={3} /> : (
          <>
            <div className="q-board">
              {d.missions.map((m, i) => {
                const percent = Math.min(100, (100 * m.progress) / Math.max(1, m.target));
                return (
                  <div key={m.slot} className={`q-note-card ${m.claimed ? "claimed" : m.done ? "done" : ""}`} style={{ "--i": i, "--tilt": `${(i % 2 ? 1 : -1) * 1.2}deg` } as CSSProperties}>
                    <span className="q-pin" />
                    {burst === m.slot && <Burst count={24} />}
                    <span className="q-art"><Art icon={iconOfEmoji(m.emoji) || ui("ui.mission")} size={46} gem={m.special ? "amethyst" : "bronze"} /></span>
                    <div className="q-main">
                      <b>{m.title}</b>
                      <div className="q-bar"><i style={{ width: `${percent}%` }} /><span className="num">{fa(m.progress)}/{fa(m.target)}</span></div>
                      <span className="q-reward"><Icon name={ui("ui.gold")} />{fa(m.gold)} <Icon name={ui("ui.path")} />۲۰</span>
                    </div>
                    {m.claimed ? <span className="q-seal broken"><Icon name={ui("ui.check")} /></span>
                      : m.done ? <button className="g-btn green q-claim" disabled={busy} onClick={() => claim("msclaim", String(m.slot), m.slot)}>دریافت</button>
                      : <span className="q-seal"><Icon name={ui("ui.lock")} /></span>}
                  </div>
                );
              })}
            </div>

            <div className="q-week">
              {burst === -2 && <Burst count={30} />}
              <div className="q-week-head"><b>جایزه‌ی هفته</b><span className="num"><Icon name={ui("ui.clock")} />{duration(d.week.left)}</span></div>
              <div className="q-torches">
                {Array.from({ length: 7 }, (_, i) => {
                  const prize = d.week.prizes.find((p) => p.days === i + 1);
                  return (
                    <div key={i} className={`q-day ${i < d.week.days ? "lit" : ""} ${prize ? "has-prize" : ""}`} style={{ "--i": i } as CSSProperties}>
                      {prize ? <Chest look={lookOf(prize.chest.id)} state={i < d.week.days && !d.week.claimed ? "shake" : "idle"} size={40} /> : <span className="q-flame" />}
                      <small className="num">{fa(i + 1)}</small>
                    </div>
                  );
                })}
              </div>
              <div className="q-prizes">
                {d.week.prizes.map((p) => (
                  <span key={p.days} className={d.week.days >= p.days ? "got" : ""}>{fa(p.days)} روز: <Icon name={ui("ui.crystal")} tone="sky" />{fa(p.crystal)} + {p.chest.name}</span>
                ))}
              </div>
              {d.week.claimed ? <p className="q-done">جایزه‌ی این هفته را گرفته‌اید</p> : d.week.earned ? (
                <button className="g-btn big q-week-go" disabled={busy} onClick={() => claim("msweek", "", -2)}>
                  <Art icon={ui("ui.chest")} size={28} gem="gold" />{d.week.days >= 7 ? "دریافت جایزه‌ی هفته" : `دریافت جایزه‌ی ${fa(d.week.earned)} روزه`}
                </button>
              ) : <p className="q-done">هر روز همه‌ی مأموریت‌ها را تمام کنید تا مشعل‌ها روشن شوند</p>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
