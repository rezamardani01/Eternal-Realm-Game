// The first thing a player sees: the crest of the realm over a dragon and a castle, the name, and a bar that fills
// as the fonts, the pictures and the player's data arrive.
import { type CSSProperties, useMemo } from "react";
import { fa } from "../lib/format";
import { ui } from "../lib/icons";
import { iconUrl } from "./ui";

const HINTS = ["دروازه‌های قلمرو باز می‌شود...", "شمشیرها صیقل می‌خورند...", "اژدها بیدار می‌شود...", "قهرمان شما فراخوانده می‌شود..."];

const art = (key: string) => ({ "--icon": iconUrl(ui(key)) }) as CSSProperties;

export function Splash({ progress, leaving }: { progress: number; leaving: boolean }) {
  const embers = useMemo(
    () => Array.from({ length: 18 }, (_, i) => ({
      left: `${(i * 53) % 100}%`, animationDuration: `${5 + (i % 5)}s`, animationDelay: `${(i * 0.37) % 5}s`, "--dx": `${((i * 29) % 60) - 30}px`,
    }) as CSSProperties),
    [],
  );
  const percent = Math.round(Math.max(0, Math.min(1, progress)) * 100);
  return (
    <div className={`splash ${leaving ? "leaving" : ""}`}>
      <div className="rays" />
      <div className="dragon" style={art("ui.boss")} />
      <div className="skyline" style={art("ui.castle")} />
      <div className="embers">{embers.map((style, i) => <i key={i} style={style} />)}</div>
      <div className="crest">
        <div className="glow" />
        <svg className="crest-art" viewBox="0 0 240 270" aria-hidden>
          <defs>
            <linearGradient id="c-gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fff6c8" /><stop offset="0.35" stopColor="#f6d26a" /><stop offset="0.7" stopColor="#d49a2a" /><stop offset="1" stopColor="#8a5a10" /></linearGradient>
            <linearGradient id="c-rim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#fff3c0" /><stop offset="0.5" stopColor="#c99232" /><stop offset="1" stopColor="#6a420a" /></linearGradient>
            <radialGradient id="c-field" cx="0.5" cy="0.35" r="0.75"><stop offset="0" stopColor="#8a2a5a" /><stop offset="0.55" stopColor="#122c52" /><stop offset="1" stopColor="#081932" /></radialGradient>
            <linearGradient id="c-steel" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#8a90a8" /><stop offset="0.5" stopColor="#ffffff" /><stop offset="1" stopColor="#7a8098" /></linearGradient>
            <linearGradient id="c-sheen" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#fff" stopOpacity="0" /><stop offset="0.5" stopColor="#fff" stopOpacity="0.55" /><stop offset="1" stopColor="#fff" stopOpacity="0" /></linearGradient>
            <radialGradient id="c-ruby" cx="0.35" cy="0.3"><stop offset="0" stopColor="#ffd0d0" /><stop offset="0.5" stopColor="#e0283c" /><stop offset="1" stopColor="#5a0610" /></radialGradient>
            <radialGradient id="c-sapph" cx="0.35" cy="0.3"><stop offset="0" stopColor="#dff4ff" /><stop offset="0.5" stopColor="#2a8ae0" /><stop offset="1" stopColor="#0a2a60" /></radialGradient>
            <radialGradient id="c-emer" cx="0.35" cy="0.3"><stop offset="0" stopColor="#dfffe8" /><stop offset="0.5" stopColor="#22b86a" /><stop offset="1" stopColor="#064a26" /></radialGradient>
            <linearGradient id="c-velvet" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#e0405a" /><stop offset="1" stopColor="#5a0618" /></linearGradient>
            <radialGradient id="c-halo"><stop offset="0" stopColor="#fff2b0" stopOpacity="0.75" /><stop offset="0.5" stopColor="#ffd060" stopOpacity="0.25" /><stop offset="1" stopColor="#ffd060" stopOpacity="0" /></radialGradient>
            <linearGradient id="c-crowngold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#ffe9a0" /><stop offset="0.5" stopColor="#f2c34a" /><stop offset="1" stopColor="#d49a22" /></linearGradient>
            <clipPath id="c-shield"><path d="M120 62 L194 86 C194 162 170 210 120 238 C70 210 46 162 46 86 Z" /></clipPath>
          </defs>
          {/* two crossed swords behind the shield */}
          {[["left", -38, "url(#c-ruby)"], ["right", 38, "url(#c-sapph)"]].map(([side, angle, gem]) => (
            <g key={side} className={`c-sword ${side}`}><g transform={`rotate(${angle} 120 150)`}>
              <rect x="115" y="30" width="10" height="190" rx="3" fill="url(#c-steel)" /><path d="M115 30 L120 14 L125 30 Z" fill="#fff" />
              <rect x="96" y="214" width="48" height="9" rx="4" fill="url(#c-gold)" /><rect x="116" y="222" width="8" height="26" rx="3" fill="#5a3010" /><circle cx="120" cy="252" r="7" fill={gem as string} />
            </g></g>
          ))}
          {/* the shield: shadow, golden rim, royal field, inner line, rivets, a passing gleam */}
          <g className="c-shield">
            <path d="M120 58 L200 84 C200 166 174 216 120 246 C66 216 40 166 40 84 Z" fill="#000" opacity="0.5" transform="translate(0 8)" />
            <path d="M120 50 L204 78 C204 166 176 220 120 252 C64 220 36 166 36 78 Z" fill="url(#c-rim)" stroke="#3a2404" strokeWidth="3" />
            <path d="M120 62 L194 86 C194 162 170 210 120 238 C70 210 46 162 46 86 Z" fill="url(#c-field)" />
            <path d="M120 72 L184 92 C184 160 162 202 120 226 C78 202 56 160 56 92 Z" fill="none" stroke="#f6d26a" strokeWidth="2" opacity="0.7" />
            <path d="M120 62 V238 M46 130 H194" stroke="#f6d26a" strokeWidth="1.2" opacity="0.18" />
            {[[120, 56], [200, 84], [40, 84], [188, 168], [52, 168], [120, 246]].map(([x, y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r="4.5" fill="url(#c-gold)" stroke="#3a2404" strokeWidth="1.2" />)}
            <g clipPath="url(#c-shield)"><rect className="c-gleam" x="-60" y="40" width="50" height="220" fill="url(#c-sheen)" /></g>
          </g>
          {/* the crown, landing on the shield */}
          <g className="c-crown">
            {/* a plain crown of one gold: five points and a band */}
            <path d="M62 60 L56 16 L84 36 L100 6 L120 30 L140 6 L156 36 L184 16 L178 60 Z" fill="url(#c-crowngold)" stroke="#7a4e0a" strokeWidth="2.5" strokeLinejoin="round" />
            <rect x="58" y="54" width="124" height="16" rx="5" fill="url(#c-crowngold)" stroke="#7a4e0a" strokeWidth="2.5" />
            {[[56, 16], [100, 6], [140, 6], [184, 16]].map(([x, y]) => <circle key={x} cx={x} cy={y} r="5" fill="url(#c-crowngold)" stroke="#7a4e0a" strokeWidth="2" />)}
          </g>
        </svg>
        <span className="crest-beast" style={art("ui.dragon")} />
      </div>
      <h1 className="name">قلمرو جاودان</h1>
      <p className="tagline">افسانه‌ی شما از همین‌جا آغاز می‌شود</p>
      <div className="loader">
        <div className="track"><div className="fill" style={{ width: `${Math.max(4, percent)}%` }} /></div>
        <div className="hint">{HINTS[Math.min(HINTS.length - 1, Math.floor(percent / 26))]} <span className="num">{fa(percent)}٪</span></div>
      </div>
    </div>
  );
}
