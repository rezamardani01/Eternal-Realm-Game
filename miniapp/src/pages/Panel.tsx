// Any screen of the bot, staged: the server runs the same panel function and this page presents it as a framed
// window of the game, or (for stories and choices) as somebody speaking with the answers laid out below.
import { type CSSProperties, useCallback, useEffect, useRef, useState } from "react";
import { Art, type Gem } from "../components/Art";
import { Bar, Button, Icon, Inline, Sheet, Skeleton, iconUrl } from "../components/ui";
import { ApiError, call, openScreen } from "../lib/api";
import { haptic, openLink } from "../lib/bale";
import { fa } from "../lib/format";
import { leading, ui } from "../lib/icons";
import type { PanelButton, Shown } from "../lib/types";
import { useApp } from "../store";

const BAR = /[▰▱]{4,}/;
const RULE = /^[━─]{5,}$/;
/** Screens that tell a story or put a choice before the player: staged as a speaker with a speech bubble. */
const STORY = new Set(["stage", "wander", "wanderq", "wch", "maze", "mazego", "mazepick", "popup", "popupgo", "quest", "qgo", "qchapter", "sbossv", "dngv", "storych", "expdk", "altar", "altarpray"]);
/** Screens that have a scene of their own in the app. */
const SCENES = new Set(["wheel", "path", "sfight", "home", "profile", "adv", "daily", "premium", "prem", "vip", "deals", "top", "clantop", "exch", "exchbuy", "exchsell", "craft", "craftq", "missions", "chests", "chestshop", "open", "cbuyq"]);
const GEMS: Gem[] = ["gold", "amethyst", "sapphire", "emerald", "bronze", "fire", "ruby", "silver"];
const RAY: Partial<Record<Gem, string>> = {
  gold: "rgba(227,189,98,.18)", amethyst: "rgba(196,155,255,.18)", sapphire: "rgba(108,200,255,.18)", emerald: "rgba(91,232,158,.16)",
  bronze: "rgba(233,164,106,.18)", fire: "rgba(255,150,80,.18)", ruby: "rgba(255,106,106,.16)", silver: "rgba(220,226,240,.16)",
};
/** Every screen keeps its own colour: the same screen always gets the same jewel. */
const gemOf = (screen: string) => GEMS[Array.from(screen).reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % GEMS.length];
/** A line like "🪙 سکه: ۵۰۰" is a fact worth a tile of its own. */
const isStat = (line: string) => {
  const t = line.trim();
  const { icon, rest } = leading(t);
  const cut = rest.search(/[:：]/);
  return Boolean(icon) && cut > 0 && cut < 26 && rest.length - cut < 48 && !BAR.test(t);
};
/** The way out of a screen: a small pill at the bottom, not a big button. */
const isBack = (button: PanelButton) => /^(🔙|↩)/u.test(button.text) || /^بازگشت/.test(leading(button.text).rest);
/** Number steps (➕ ➖), level filters and other crowded rows: compact chips. */
const isChip = (button: PanelButton, crowd: boolean) => /^(➕|➖|✔)/u.test(button.text) || (crowd && leading(button.text).rest.length <= 12) || leading(button.text).rest.length <= 3;
/** Sections with a scene of their own: a backdrop, a big picture behind the screen's own, an accent jewel. */
const THEMES: { id: string; test: RegExp; art: string; gem: Gem }[] = [
  { id: "war", test: /^city(map|search|atk|revenge|reports|rep|prep|go|league)/, art: "ui.war", gem: "ruby" },
  { id: "vault", test: /^city(treas|wd|dep|stock|mine)/, art: "ui.vault", gem: "gold" },
  { id: "guard", test: /^city(def|trap|shield)/, art: "ui.shieldbig", gem: "sapphire" },
  { id: "army", test: /^city(troops|tr|people)/, art: "ui.swords", gem: "bronze" },
  { id: "build", test: /^city(build|bv|bok|queue|rush|clear)/, art: "ui.anvil", gem: "emerald" },
  { id: "city", test: /^city/, art: "ui.city", gem: "emerald" },
  { id: "forge", test: /^craft/, art: "ui.anvil", gem: "fire" },
  { id: "merchant", test: /^(shop|buy|sell|market|listing|listask|lconfirm|items?$|item$)/, art: "ui.market", gem: "emerald" },
  { id: "trip", test: /^trip$/, art: "ui.adventure", gem: "bronze" },
];
const themeOf = (screen: string) => THEMES.find((t) => t.test.test(screen)) ?? null;

/** The moving parts of a themed backdrop. */
function Deco({ id }: { id: string }) {
  const bits = (n: number) => Array.from({ length: n }, (_, i) => <i key={i} style={{ "--i": i, left: `${(i * 37 + 7) % 100}%` } as CSSProperties} />);
  if (id === "forge") return <div className="th-deco"><span className="forge-fire" /><span className="embers2">{bits(14)}</span></div>;
  if (id === "merchant") return <div className="th-deco"><span className="stall-awning" /><span className="floating-coins">{bits(7)}</span></div>;
  if (id === "trip") return <div className="th-deco"><span className="map-sheet" /><span className="compass" /></div>;
  if (id === "war") return <div className="th-deco"><span className="war-smoke">{bits(6)}</span></div>;
  if (id === "vault") return <div className="th-deco"><span className="glints">{bits(10)}</span></div>;
  if (id === "guard") return <div className="th-deco"><span className="ward" /></div>;
  return <div className="th-deco"><span className="walls" /><span className="pennants">{bits(4)}</span></div>;
}
const art = (name: string) => ({ "--icon": iconUrl(name) }) as CSSProperties;

function Line({ text }: { text: string }) {
  const trimmed = text.trim();
  if (!trimmed) return <div className="gap" />;
  if (RULE.test(trimmed)) return <div className="divider" />;
  const bar = trimmed.match(BAR);
  if (bar) {
    const filled = (bar[0].match(/▰/g) || []).length;
    const rest = trimmed.replace(BAR, "").trim();
    return (
      <div className="line" style={{ alignItems: "center" }}>
        <div className="grow"><Bar value={filled} max={bar[0].length} /></div>
        {rest && <span className="small muted"><Inline text={rest} /></span>}
      </div>
    );
  }
  const { icon, rest } = leading(trimmed);
  const heading = /^\*[^*]+\*$/.test(rest);
  return (
    <div className="line">
      {icon && <Icon name={icon} />}
      <p className={`grow ${heading ? "subhead" : ""}`}><Inline text={heading ? rest.slice(1, -1) : rest} /></p>
    </div>
  );
}

export default function Panel({ start, preset, onClose }: { start: { s: string; a: string; b: string }; preset?: Shown; onClose: () => void }) {
  const app = useApp();
  const [shown, setShown] = useState<Shown | null>(preset ?? null);
  const [failed, setFailed] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<Shown["prompt"] | null>(null);
  const [value, setValue] = useState("");
  const body = useRef<HTMLDivElement>(null);

  const go = useCallback(async (s: string, a = "", b = "") => {
    if (busy) return;
    setBusy(true);
    try {
      const { shown: next } = await openScreen(s, a, b);
      if (next.toast) app.toast(next.toast.replace(/\p{Extended_Pictographic}️?/gu, "").trim());
      if (next.rows.some((row) => row.some((button) => button.s === "sact"))) return app.open("sfight");  // a fight began: to the battlefield
      if (next.text !== null) {
        setShown(next);
        setFailed("");
        setForm(next.prompt ?? null);
        setValue("");
        body.current?.scrollTo({ top: 0 });
      }
    } catch (error) {
      const message = (error instanceof ApiError ? error.message : "خطایی پیش آمد.").replace(/\p{Extended_Pictographic}️?/gu, "").trim();
      if (shown) app.toast(message, true);
      else setFailed(message);
    } finally {
      setBusy(false);
    }
  }, [app, busy, shown]);

  useEffect(() => { if (!preset) void go(start.s, start.a, start.b); }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const press = async (button: PanelButton) => {
    if (button.url) return openLink(button.url);
    if (button.copy) {
      await navigator.clipboard?.writeText(button.copy).catch(() => {});
      return app.toast("کپی شد");
    }
    if (button.buy) return app.pay(button.buy);
    if (button.bot_only || !button.s) return app.toast("این کار داخل گفتگوی ربات انجام می‌شود.", true);
    if (button.s === "noop") return;
    if (SCENES.has(button.s)) return app.open(button.s, button.a, button.b);
    await go(button.s, button.a, button.b);
  };

  const submit = async () => {
    if (!form) return;
    const text = value.trim();
    if (!text) return app.toast("چیزی بنویسید.", true);
    if (form.form === "listing") {  // the price of a market listing: straight to the confirmation of the same listing
      const price = text.replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d))).replace(/[^\d]/g, "");
      if (!price) return app.toast("قیمت را با عدد بنویسید.", true);
      return go("lconfirm", form.kind, `${form.ref}~${price}`);
    }
    setBusy(true);
    try {
      const { shown: next } = await call<{ shown: Shown }>("prompt", { kind: form.form, text });
      setShown(next);
      setForm(null);
    } catch (error) {
      app.toast(error instanceof Error ? error.message : "نشد", true);
    } finally {
      setBusy(false);
    }
  };

  const lines = (shown?.text ?? "").split("\n");
  const head = leading((lines[0] ?? "").replace(/\*/g, ""));
  const title = head.rest || "قلمرو جاودان";
  const picture = head.icon || ui("ui.emblem");
  const story = shown ? STORY.has(shown.screen) : false;
  const rest = lines.slice(1).filter((line, index, all) => !(RULE.test(line.trim()) && index < 2) && !(line.trim() === "" && (all[index - 1] ?? "").trim() === ""));

  const buttons = shown?.rows ?? [];
  const theme = shown && !story ? themeOf(shown.screen) : null;
  /** The screen's own way back (the bot puts it as a last button): the title bar's medallion takes it. */
  const backTo = story ? undefined : buttons.flat().find(isBack);
  return (
    <div className={`overlay ${theme ? `th th-${theme.id}` : ""}`}>
      {theme && <Deco id={theme.id} />}
      <div className="topbar">
        <button className="round-btn" onClick={() => (backTo?.s && !SCENES.has(backTo.s) ? void press(backTo) : onClose())} aria-label="بازگشت"><Icon name={ui("ui.back")} /></button>
        <h2 className="ellipsis">{title}</h2>
        <span className="pill gold num small"><Icon name={ui("ui.gold")} />{fa(app.me.player.gold)}</span>
      </div>
      <div className="body" ref={body}>
        {!shown && !failed && <Skeleton height={110} />}
        {failed && (
          <div className="window" style={{ textAlign: "center" }}>
            <Icon name={ui("ui.lock")} size={48} tone="muted" />
            <p style={{ margin: "10px 0 14px" }}>{failed}</p>
            <Button kind="gold" onClick={onClose}>بازگشت</Button>
          </div>
        )}
        {shown && story && (
          <div style={{ opacity: busy ? 0.6 : 1, transition: "opacity .15s" }} key={shown.text}>
            <div className="stage">
              <div className="backdrop" />
              <div className="spot" />
              <div className="speaker">
                <span className="shade" />
                <span className="fig-wrap"><span className="figure" style={{ ...art(picture), display: "block" }} /></span>
              </div>
            </div>
            <div className="bubble-say rich">
              {rest.map((line, index) => <Line key={index} text={line} />)}
            </div>
            <div className="choices">
              {buttons.flat().map((button, index) => {
                const { icon, rest: label } = leading(button.text);
                const backish = ["trip", "home", "quests", "story", "maze", "expd", "sbosses", "dng"].includes(button.s ?? "") && buttons.flat().length > 1 && index === buttons.flat().length - 1;
                return (
                  <button key={index} className={`choice-btn ${button.style === "danger" ? "danger" : backish ? "plain" : ""}`} disabled={busy} onClick={() => press(button)}>
                    <Icon name={icon || ui("ui.pointer")} /><span className="grow"><Inline text={label} /></span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
        {shown && !story && (() => {
          const stats = rest.filter(isStat);
          const prose = rest.filter((line) => !isStat(line));
          const hasProse = prose.some((line) => line.trim() && !RULE.test(line.trim()));
          const flat = buttons.flatMap((row) => row.map((button) => ({ button, alone: row.length === 1, crowd: row.length >= 3 })));
          const backs = flat.filter(({ button }) => isBack(button));
          const chips = flat.filter(({ button, crowd }) => !isBack(button) && isChip(button, crowd));
          const tiles = flat.filter(({ button, crowd }) => !isBack(button) && !isChip(button, crowd));
          let n = 0;
          return (
            <div style={{ opacity: busy ? 0.6 : 1, transition: "opacity .15s" }} key={shown.text}>
              <div className="gp-head" style={{ "--ray": RAY[gemOf(shown.screen)] } as CSSProperties}>
                <div className="rays" />
                <div className="orbit">{Array.from({ length: 5 }, (_, i) => <i key={i} style={{ transform: `rotate(${i * 72}deg) translateX(70px) scale(${i % 2 ? 0.6 : 1})` }} />)}</div>
                <span className="gp-pic"><Art icon={picture} size={96} gem={theme?.gem ?? gemOf(shown.screen)} /></span>
              </div>
              <div className="gp-title">{title}</div>
              {stats.length > 0 && (
                <div className="gp-stats">
                  {stats.map((line, index) => {
                    const { icon, rest: words } = leading(line.trim());
                    const cut = words.search(/[:：]/);
                    const inner = leading(words.slice(0, cut).replace(/\*/g, "").trim());  // "✅ 🐉 فلس اژدها": a mark, then the thing
                    const label = inner.rest;
                    const value = words.slice(cut + 1).trim();
                    const mark = inner.icon ? icon : null;
                    return (
                      <div key={index} className={`gp-stat ${value.length > 16 ? "wide" : ""}`} style={{ "--i": index } as CSSProperties}>
                        <Art icon={inner.icon || icon || ui("ui.star")} size={32} gem={GEMS[index % GEMS.length]} />
                        <span className="grow"><small>{label}</small><b><Inline text={value} /></b></span>
                        {mark && <Icon name={mark} size={20} />}
                      </div>
                    );
                  })}
                </div>
              )}
              {hasProse && (
                <div className="gp-scroll rich">
                  {prose.map((line, index) => <div key={index} style={{ "--i": index } as CSSProperties}><Line text={line} /></div>)}
                </div>
              )}
              {(() => {
                // the screen's main actions (a lone coloured button, or the only button) are wide, centred buttons;
                // the rest are picture tiles two to a row, and an odd last one takes the whole row
                const kindOf = (b: PanelButton) => (b.buy ? "gold" : b.style ?? "");
                const mains = tiles.filter((t) => t.alone && (tiles.length === 1 || Boolean(kindOf(t.button))));
                const grid = tiles.filter((t) => !mains.includes(t));
                return (
                  <>
                    {grid.length > 0 && (
                      <div className="gp-tiles">
                        {grid.map(({ button }, index) => {
                          const { icon, rest: label } = leading(button.text);
                          const kind = kindOf(button);
                          const wide = grid.length % 2 === 1 && index === grid.length - 1;
                          const gem: Gem = kind === "success" ? "emerald" : kind === "danger" ? "ruby" : kind === "primary" ? "sapphire" : kind === "gold" ? "gold" : GEMS[index % GEMS.length];
                          return (
                            <button key={index} className={`gp-tile ${kind} ${wide ? "wide" : ""}`} style={{ "--i": n++ } as CSSProperties} onClick={() => { haptic(); void press(button); }} disabled={busy || button.s === "noop"}>
                              <Art icon={icon || ui("ui.pointer")} size={wide ? 38 : 46} gem={gem} />
                              <span><Inline text={label} /></span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                    {mains.length > 0 && (
                      <div className="gp-mains">
                        {mains.map(({ button }, index) => {
                          const { icon, rest: label } = leading(button.text);
                          const kind = kindOf(button);
                          const tone = kind === "danger" ? "red" : kind === "success" ? "green" : kind === "primary" ? "blue" : "";
                          return (
                            <button key={index} className={`g-btn big ${tone}`} style={{ "--i": n++ } as CSSProperties} onClick={() => { haptic(); void press(button); }} disabled={busy || button.s === "noop"}>
                              <Art icon={icon || ui("ui.pointer")} size={30} gem={kind === "danger" ? "ruby" : kind === "success" ? "emerald" : "gold"} />
                              <span><Inline text={label} /></span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </>
                );
              })()}
              {chips.length > 0 && (
                <div className="gp-chips">
                  {chips.map(({ button }, index) => {
                    const { icon, rest: label } = leading(button.text);
                    const on = button.text.startsWith("✔");
                    return (
                      <button key={index} className={`gp-chip ${on ? "on" : ""}`} style={{ "--i": n++ } as CSSProperties} onClick={() => { haptic(); void press(button); }} disabled={busy || button.s === "noop"}>
                        {icon && !on && <Icon name={icon} />}<Inline text={label} />
                      </button>
                    );
                  })}
                </div>
              )}
              {backs.map(({ button }, index) => (
                <button key={index} className="gp-back" onClick={() => void press(button)} disabled={busy}>
                  <Icon name={ui("ui.back")} /><Inline text={leading(button.text).rest} />
                </button>
              ))}
            </div>
          );
        })()}
      </div>
      {form && (
        <Sheet onClose={() => setForm(null)}>
          <h3 className="title gold-text" style={{ textAlign: "center", marginBottom: 12 }}>
            {form.form === "listing" ? "قیمت فروش (سکه)" : "نام شهر"}
          </h3>
          <input
            className="field" autoFocus value={value} inputMode={form.form === "listing" ? "numeric" : "text"}
            onChange={(event) => setValue(event.target.value)} placeholder={form.form === "listing" ? "مثلاً ۵۰۰۰" : "مثلاً آذرگان"}
          />
          <div style={{ marginTop: 12 }}><Button kind="gold" onClick={submit}>تأیید</Button></div>
        </Sheet>
      )}
    </div>
  );
}
