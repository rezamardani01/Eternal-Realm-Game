// «گنجینه»: the hero's chests on a glowing pedestal. Pick one from the shelf below; buy another with gold or crystals;
// open it and it rattles, the lid swings back, light pours out and the prizes fly up out of it one by one.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type CSSProperties, useState } from "react";
import { Art, Burst, Count } from "../components/Art";
import { Chest, type ChestState, lookOf } from "../components/Chest";
import { Icon, Skeleton } from "../components/ui";
import { call } from "../lib/api";
import { haptic } from "../lib/bale";
import { fa } from "../lib/format";
import { iconFor, ui } from "../lib/icons";
import type { ItemInfo } from "../lib/types";
import { useApp } from "../store";

interface ChestRow { item: ItemInfo; owned: number; price: { currency: "gold" | "crystal"; amount: number } | null }
interface Opened { gold: number; crystal: number; qty: number; item: ItemInfo | null }

export default function Vault({ start = "", onClose }: { start?: string; onClose: () => void }) {
  const app = useApp();
  const client = useQueryClient();
  const data = useQuery({ queryKey: ["chests"], queryFn: () => call<{ chests: ChestRow[]; gold: number; crystal: number }>("chests") });
  const [picked, setPicked] = useState(start);
  const [state, setState] = useState<ChestState>("idle");
  const [prize, setPrize] = useState<Opened | null>(null);
  const [busy, setBusy] = useState(false);
  const rows = data.data?.chests ?? [];
  const row = rows.find((r) => r.item.id === picked) ?? rows.find((r) => r.owned) ?? rows[0];

  const reload = async () => { await client.invalidateQueries({ queryKey: ["chests"] }); void app.refresh(); };
  const open = async () => {
    if (!row || busy || !row.owned) return;
    setBusy(true);
    setPrize(null);
    setState("shake");
    haptic("tap");
    const began = performance.now();
    try {
      const got = await call<Opened>("chests", { open: row.item.id });
      await new Promise((done) => window.setTimeout(done, Math.max(0, 1100 - (performance.now() - began))));
      haptic("success");
      setPrize(got);
      setState("open");
      await reload();
    } catch (error) {
      setState("idle");
      app.toast(error instanceof Error ? error.message : "باز نشد", true);
    } finally {
      setBusy(false);
    }
  };
  const buy = async () => {
    if (!row?.price || busy) return;
    setBusy(true);
    try {
      await call("chests", { buy: row.item.id });
      haptic("success");
      app.toast(`${row.item.name} به گنجینه اضافه شد`);
      setState("idle");
      setPrize(null);
      await reload();
    } catch (error) {
      app.toast(error instanceof Error ? error.message : "خرید نشد", true);
    } finally {
      setBusy(false);
    }
  };
  const pick = (id: string) => { haptic(); setPicked(id); setState("idle"); setPrize(null); };

  const loot = prize ? [
    ...(prize.gold ? [{ k: "g", icon: ui("ui.gold"), n: prize.gold, name: "سکه" }] : []),
    ...(prize.crystal ? [{ k: "c", icon: ui("ui.crystal"), n: prize.crystal, name: "کریستال" }] : []),
    ...(prize.item ? [{ k: "i", icon: iconFor("item", prize.item.id, prize.item.emoji), n: prize.qty, name: prize.item.name }] : []),
  ] : [];
  const spots = loot.length === 1 ? [[0, -150]] : loot.length === 2 ? [[-70, -130], [70, -130]] : [[-95, -120], [0, -160], [95, -120]];

  return (
    <div className="vault">
      <div className="g-title">
        <button className="g-back" onClick={onClose} aria-label="بستن"><Icon name={ui("ui.back")} /></button>
        <h2>گنجینه‌ی صندوقچه‌ها</h2>
        <span className="g-purse num"><Icon name={ui("ui.gold")} />{fa(data.data?.gold ?? app.me.player.gold)}</span>
      </div>
      {!row ? <div style={{ padding: 16 }}><Skeleton height={220} count={1} /></div> : (
        <>
          <div className="pedestal-stage">
            <span className="vault-rays" />
            {state === "open" && <Burst count={40} />}
            <div className="pedestal-chest" key={row.item.id}>
              <Chest look={lookOf(row.item.id)} state={state} size={210}>
                {loot.map((p, i) => (
                  <span key={p.k} className="loot-coin" style={{ "--i": i, "--x": `${spots[i][0]}px`, "--y": `${spots[i][1]}px` } as CSSProperties}>
                    <Art icon={p.icon} size={54} gem={p.k === "c" ? "sapphire" : p.k === "g" ? "gold" : "amethyst"} />
                    <b className="num">×<Count to={p.n} delay={500 + i * 180} /></b>
                  </span>
                ))}
              </Chest>
            </div>
            <div className="pedestal"><span /></div>
          </div>
          <div className="vault-name">
            <b>{row.item.name}</b>
            <span className="num">{row.owned ? `در گنجینه: ${fa(row.owned)}` : "ندارید"}</span>
          </div>
          {prize && (
            <div className="vault-won">
              <Art icon={ui("ui.star")} size={26} gem="gold" />
              <span>این گنج را یافتید: {loot.map((p) => `${p.name} ×${fa(p.n)}`).join(" · ")}</span>
            </div>
          )}
          <div className="vault-acts">
            <button className="g-btn green big" disabled={busy || !row.owned} onClick={open}>
              <Art icon={ui("ui.chest")} size={30} gem="gold" />{row.owned ? (state === "open" && row.owned ? "باز کردن یکی دیگر" : "باز کن") : "صندوقچه ندارید"}
            </button>
            {row.price && (
              <button className="g-btn gold" disabled={busy} onClick={buy}>
                خرید <span className="num">{fa(row.price.amount)}</span><Icon name={ui(row.price.currency === "gold" ? "ui.gold" : "ui.crystal")} />
              </button>
            )}
            <button className="g-btn ghost" onClick={() => app.open("odds", row.item.id)}><Icon name={ui("ui.luck")} />شانس‌ها</button>
          </div>
          <div className="shelf">
            {rows.map((r, i) => (
              <button key={r.item.id} className={`shelf-slot r-${r.item.rarity} ${r.item.id === row.item.id ? "on" : ""}`} style={{ "--i": i } as CSSProperties} onClick={() => pick(r.item.id)}>
                <Chest look={lookOf(r.item.id)} state="idle" size={62} />
                {r.owned > 0 && <span className="slot-count num">{fa(r.owned)}</span>}
                <small className="ellipsis">{r.item.name}</small>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
