// The small building blocks every page shares: icons, emblems, bars, buttons, sheets.
import { type CSSProperties, type ReactNode, useState } from "react";
import { haptic } from "../lib/bale";
import { fa } from "../lib/format";
import { EMOJI_SOURCE, iconOfEmoji, leading, toneOf, type Tone, ui } from "../lib/icons";

const BASE = import.meta.env.BASE_URL;
export const iconUrl = (name: string) => `url("${BASE}icons/${name}.svg")`;

export function Icon({ name, size, tone, className = "" }: { name: string; size?: number; tone?: Tone; className?: string }) {
  const style = { "--icon": iconUrl(name), ...(size ? { width: size, height: size } : {}) } as CSSProperties;
  return <span className={`icon t-${tone ?? toneOf(name)} ${className}`} style={style} aria-hidden />;
}

/** A framed medallion with a picture: the "portrait" of an item, a hero, a monster. */
export function Emblem({ icon, size = 56, rarity = 1, round = false, badge, tone }: {
  icon: string; size?: number; rarity?: number; round?: boolean; badge?: ReactNode; tone?: Tone;
}) {
  return (
    <span className={`emblem r-${rarity} ${round ? "round" : ""}`} style={{ width: size, height: size }}>
      <Icon name={icon} size={Math.round(size * 0.6)} tone={tone} />
      {badge != null && <span className="badge num">{badge}</span>}
    </span>
  );
}

export function Bar({ value, max, tone = "", thin = false }: { value: number; max: number; tone?: string; thin?: boolean }) {
  const percent = max > 0 ? Math.max(0, Math.min(100, (100 * value) / max)) : 0;
  return <div className={`bar ${tone} ${thin ? "thin" : ""}`}><i style={{ width: `${percent}%` }} /></div>;
}

/** Text that came from the game with emojis and *bold* marks: emojis become icons, marks become emphasis. */
export function Inline({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  const pattern = new RegExp(`${EMOJI_SOURCE}|\\*([^*\\n]+)\\*|\\[([^\\]]+)\\]\\(uid:\\d+\\)`, "gu");
  let last = 0;
  let key = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index! > last) parts.push(text.slice(last, match.index));
    if (match[1]) {
      const icon = iconOfEmoji(match[1]);
      if (icon) parts.push(<Icon key={key++} name={icon} />);
    } else if (match[2]) {
      parts.push(<b key={key++}><Inline text={match[2]} /></b>);
    } else if (match[3]) {
      parts.push(<b key={key++}>{match[3]}</b>);
    }
    last = match.index! + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
}

/** A label that starts with an emoji, drawn as picture + words. */
export function Label({ text, size }: { text: string; size?: number }) {
  const { icon, rest } = leading(text);
  return <>{icon && <Icon name={icon} size={size} />}<span><Inline text={rest} /></span></>;
}

export function Button({ children, kind = "", onClick, busy = false, disabled = false, small = false }: {
  children: ReactNode; kind?: string; onClick?: () => void | Promise<void>; busy?: boolean; disabled?: boolean; small?: boolean;
}) {
  const [working, setWorking] = useState(false);
  const run = async () => {
    if (working || busy || !onClick) return;  // one tap, one action
    haptic("tap");
    try {
      setWorking(true);
      await onClick();
    } finally {
      setWorking(false);
    }
  };
  return (
    <button className={`btn ${kind} ${small ? "small-btn" : ""}`} onClick={run} disabled={disabled || working || busy}>
      {working || busy ? <span className="spinner" /> : children}
    </button>
  );
}

export function Sheet({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  return (
    <div className="scrim" onClick={onClose}>
      <div className="sheet" onClick={(event) => event.stopPropagation()}>
        <div className="grip" />
        {children}
      </div>
    </div>
  );
}

export function Money({ gold, crystal }: { gold?: number; crystal?: number }) {
  return (
    <>
      {gold !== undefined && <span className="pill gold num"><Icon name={ui("ui.gold")} />{fa(gold)}</span>}
      {crystal !== undefined && <span className="pill gold num"><Icon name={ui("ui.crystal")} />{fa(crystal)}</span>}
    </>
  );
}

export function Skeleton({ height = 90, count = 3 }: { height?: number; count?: number }) {
  return <div className="stack">{Array.from({ length: count }, (_, i) => <div key={i} className="skel" style={{ height }} />)}</div>;
}

export function Empty({ icon, text }: { icon: string; text: string }) {
  return (
    <div className="card" style={{ textAlign: "center", padding: "26px 16px" }}>
      <Icon name={icon} size={46} tone="muted" />
      <p className="muted" style={{ marginTop: 8 }}>{text}</p>
    </div>
  );
}
