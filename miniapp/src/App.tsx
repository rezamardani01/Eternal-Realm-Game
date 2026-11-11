import { useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Splash } from "./components/Splash";
import { Icon, Skeleton } from "./components/ui";
import { ApiError, call } from "./lib/api";
import { haptic, onBack, openInvoice, startBale } from "./lib/bale";
import { ui } from "./lib/icons";
import type { Me, PanelButton, Shown } from "./lib/types";
import { AppContext, type AppState, type TabId } from "./store";

const Realm = lazy(() => import("./pages/Realm"));
const Hero = lazy(() => import("./pages/Hero"));
const Adventure = lazy(() => import("./pages/Adventure"));
const Clan = lazy(() => import("./pages/Clan"));
const Market = lazy(() => import("./pages/Market"));
const Panel = lazy(() => import("./pages/Panel"));
const Wheel = lazy(() => import("./pages/Wheel"));
const PathTrack = lazy(() => import("./pages/PathTrack"));
const Battle = lazy(() => import("./pages/Battle"));
const Onboarding = lazy(() => import("./pages/Onboarding"));
const Treasury = lazy(() => import("./pages/Treasury"));
const Daily = lazy(() => import("./pages/Daily"));
const Leaders = lazy(() => import("./pages/Leaders"));
const Exchange = lazy(() => import("./pages/Exchange"));
const Forge = lazy(() => import("./pages/Forge"));
const Vault = lazy(() => import("./pages/Vault"));
const Quests = lazy(() => import("./pages/Quests"));

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: "realm", label: "قلمرو", icon: "ui.realm" },
  { id: "hero", label: "قهرمان", icon: "ui.hero" },
  { id: "adventure", label: "ماجراجویی", icon: "ui.adventure" },
  { id: "clan", label: "خاندان", icon: "ui.clan" },
  { id: "market", label: "بازار", icon: "ui.market" },
];
/** Screens of the bot that have a page of their own here: tapping a button that leads to them switches the tab. */
const NATIVE: Record<string, TabId> = { home: "realm", profile: "hero", adv: "adventure" };
/** The bot's shop screens: here they all open the treasury, on the matching shelf. */
/** The bot's chest screens: here they open the chest vault. */
const CHESTS = new Set(["chests", "chestshop", "open", "cbuy", "cbuyq"]);
const SHOP = new Set(["premium", "prem", "vip", "deals"]);
const MIN_SPLASH_MS = 2400;
/** `?splash` keeps the opening picture on screen (for looking at it while designing). */
const HOLD_SPLASH = new URLSearchParams(window.location.search).has("splash");

export default function App() {
  const client = useQueryClient();
  const [tab, setTab] = useState<TabId>("realm");
  const [panel, setPanel] = useState<{ s: string; a: string; b: string; key: number; preset?: Shown } | null>(null);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);
  const [clock, setClock] = useState(0);  // 0..1: how much of the shortest splash time has passed
  const [fontsReady, setFontsReady] = useState(false);
  const [splash, setSplash] = useState<"on" | "leaving" | "off">("on");
  const noteTimer = useRef<number>();

  const me = useQuery({ queryKey: ["me"], queryFn: () => call<Me>("me"), retry: false, staleTime: 15_000 });
  const needsHero = me.error instanceof ApiError && me.error.needsHero;

  useEffect(() => {
    startBale();
    document.fonts.ready.then(() => setFontsReady(true), () => setFontsReady(true));
    const started = performance.now();
    const timer = window.setInterval(() => {
      const passed = Math.min(1, (performance.now() - started) / MIN_SPLASH_MS);
      setClock(passed);
      if (passed >= 1) window.clearInterval(timer);
    }, 60);
    return () => window.clearInterval(timer);
  }, []);

  // the bar is honest: time, fonts and the first answer of the server each fill a part of it
  const settled = me.isSuccess || me.isError;
  const progress = clock * 0.5 + (fontsReady ? 0.2 : 0) + (settled ? 0.3 : 0);
  useEffect(() => {
    if (splash === "on" && progress >= 0.999 && !HOLD_SPLASH) {
      setSplash("leaving");
      window.setTimeout(() => setSplash("off"), 650);
    }
  }, [progress, splash]);

  const toast = useCallback((text: string, error = false) => {
    setNote({ text, error });
    haptic(error ? "error" : "success");
    window.clearTimeout(noteTimer.current);
    noteTimer.current = window.setTimeout(() => setNote(null), error ? 4200 : 2800);
  }, []);

  const refresh = useCallback(async () => {
    await client.invalidateQueries();
  }, [client]);

  const open = useCallback((s: string, a = "", b = "") => {
    if (s in NATIVE) {
      setPanel(null);
      setTab(NATIVE[s]);
      return;
    }
    setPanel({ s, a, b, key: Date.now() });
  }, []);

  const pay = useCallback(async (buy: NonNullable<PanelButton["buy"]>) => {
    try {
      const order = await call<{ invoice: unknown }>("buy", buy);
      const status = await openInvoice(order.invoice);
      if (status === "unsupported") {  // an old client: the invoice goes to the chat with the bot instead
        await call("buy", { ...buy, via: "chat" });
        toast("فاکتور پرداخت در گفتگوی ربات برایتان فرستاده شد؛ همان‌جا پرداخت کنید.");
      } else if (status === "paid") {
        toast("پرداخت انجام شد؛ خریدتان تا چند لحظه‌ی دیگر به کیفتان می‌رسد.");
        window.setTimeout(() => void refresh(), 2500);
      } else if (status === "failed") {
        toast("پرداخت انجام نشد؛ پولی از شما کم نشده است.", true);
      }
    } catch (error) {
      toast(error instanceof Error ? error.message : "پرداخت شروع نشد.", true);
    }
  }, [refresh, toast]);

  // Bale's own back button closes the open panel
  useEffect(() => onBack(panel ? () => setPanel(null) : null), [panel]);

  const state = useMemo<AppState | null>(
    () => (me.data ? { me: me.data, refresh, tab, setTab, open, toast, pay } : null),
    [me.data, refresh, tab, open, toast, pay],
  );

  const Page = { realm: Realm, hero: Hero, adventure: Adventure, clan: Clan, market: Market }[tab];
  return (
    <div className="app">
      {splash === "off" || state || needsHero ? (
        <Suspense fallback={<div className="page"><Skeleton height={120} /></div>}>
          {needsHero ? (
            <Onboarding onDone={() => void me.refetch()} toast={toast} />
          ) : state ? (
            <AppContext.Provider value={state}>
              <Page key={tab} />
              <nav className="tabbar">
                {TABS.map((item) => (
                  <button key={item.id} className={`tab ${tab === item.id ? "on" : ""}`} onClick={() => { haptic(); setTab(item.id); }}>
                    <span className="medal"><Icon name={ui(item.icon)} /></span>
                    {item.label}
                  </button>
                ))}
              </nav>
              {panel && (() => {
                const close = () => { setPanel(null); void refresh(); };
                if (panel.s === "wheel") return <Wheel key={panel.key} onClose={close} />;
                if (panel.s === "path") return <PathTrack key={panel.key} onClose={close} />;
                if (panel.s === "missions") return <Quests key={panel.key} onClose={close} />;
                if (panel.s.startsWith("craft")) return <Forge key={panel.key} onClose={close} />;
                if (CHESTS.has(panel.s)) return <Vault key={panel.key} start={panel.s === "open" || panel.s.startsWith("cbuy") ? panel.a : ""} onClose={close} />;
                if (panel.s === "top" || panel.s === "clantop") return <Leaders key={panel.key} start={panel.s === "clantop" ? "clans" : panel.a || "level"} onClose={close} />;
                if (panel.s.startsWith("exch")) return <Exchange key={panel.key} onClose={close} />;
                if (panel.s === "daily") return <Daily key={panel.key} onClose={close} />;
                if (SHOP.has(panel.s)) return <Treasury key={panel.key} start={panel.s === "prem" ? panel.a : panel.s === "premium" ? "deals" : panel.s} onClose={close} />;
                if (panel.s === "sfight" && !panel.preset) {
                  return <Battle key={panel.key} onClose={close} onFinish={(shown) => { void refresh(); setPanel({ s: "sfight", a: "", b: "", key: Date.now(), preset: shown }); }} />;
                }
                return <Panel key={panel.key} start={panel} preset={panel.preset} onClose={close} />;
              })()}
            </AppContext.Provider>
          ) : (
            <div className="page" style={{ display: "grid", placeItems: "center", textAlign: "center" }}>
              <div className="card gilded" style={{ maxWidth: 340 }}>
                <Icon name={ui("ui.castle")} size={54} />
                <p style={{ margin: "10px 0 14px" }}>{me.error instanceof Error ? me.error.message : "در حال اتصال به قلمرو..."}</p>
                <button className="btn gold" onClick={() => void me.refetch()}>تلاش دوباره</button>
              </div>
            </div>
          )}
        </Suspense>
      ) : null}
      {note && <div className={`toast ${note.error ? "error" : ""}`} onClick={() => setNote(null)}>{note.text}</div>}
      {splash !== "off" && <Splash progress={progress} leaving={splash === "leaving"} />}
    </div>
  );
}
