// A treasure chest drawn in two parts: the base with its planks, iron bands and lock, and a curved lid hinged at the back.
// It bobs while it waits, rattles when it is about to open, and on opening the lid swings back in 3D, light pours out
// of the chest and the prizes (rendered by the caller as children) fly up out of it.
import type { CSSProperties, ReactNode } from "react";

export type ChestLook = "wood" | "magic" | "royal";
export type ChestState = "idle" | "shake" | "open";

const LOOKS: Record<ChestLook, { wood: [string, string, string]; metal: [string, string]; gem: string; glow: string }> = {
  wood: { wood: ["#c8823e", "#8a4e1e", "#4a2a0e"], metal: ["#d8dce6", "#6a7084"], gem: "#ffd25a", glow: "rgba(255, 220, 140, 0.9)" },
  magic: { wood: ["#5a6ad8", "#2a3490", "#121a4a"], metal: ["#e2c8ff", "#7a4ac0"], gem: "#7ff0ff", glow: "rgba(160, 220, 255, 0.95)" },
  royal: { wood: ["#d8404a", "#8a1424", "#40060e"], metal: ["#fff3b0", "#c9922e"], gem: "#7fff9a", glow: "rgba(255, 230, 150, 1)" },
};

/** Which look a chest item gets. */
export const lookOf = (id: string): ChestLook => (id.includes("royal") || id.includes("legend") ? "royal" : id.includes("magic") || id.includes("crystal") ? "magic" : "wood");

export function Chest({ look = "wood", state = "idle", size = 180, children }: { look?: ChestLook; state?: ChestState; size?: number; children?: ReactNode }) {
  const l = LOOKS[look];
  const id = `ch-${look}`;
  return (
    <div className={`chest3d is-${state}`} style={{ width: size, height: size * 0.92, "--glow": l.glow } as CSSProperties}>
      <span className="chest-shadow" />
      <span className="chest-beam" />
      <span className="chest-light" />
      <svg className="chest-base" viewBox="0 0 200 120" aria-hidden>
        <defs>
          <linearGradient id={`${id}-w`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={l.wood[0]} /><stop offset="0.55" stopColor={l.wood[1]} /><stop offset="1" stopColor={l.wood[2]} /></linearGradient>
          <linearGradient id={`${id}-m`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={l.metal[0]} /><stop offset="1" stopColor={l.metal[1]} /></linearGradient>
          <radialGradient id={`${id}-in`} cx="0.5" cy="0" r="0.9"><stop offset="0" stopColor="#fff6d0" /><stop offset="0.4" stopColor={l.glow} /><stop offset="1" stopColor="#2a1406" /></radialGradient>
        </defs>
        {/* the inside, seen when the lid is up */}
        <path className="chest-inside" d="M14 10 L186 10 L180 26 L20 26 Z" fill={`url(#${id}-in)`} />
        <rect x="10" y="20" width="180" height="96" rx="8" fill={`url(#${id}-w)`} stroke="#1e0e04" strokeWidth="4" />
        {[44, 72, 100].map((y) => <path key={y} d={`M14 ${y} H186`} stroke="#000" strokeOpacity="0.25" strokeWidth="2" />)}
        <path d="M18 26 H182" stroke="#fff" strokeOpacity="0.25" strokeWidth="3" />
        {[28, 160].map((x) => <rect key={x} x={x} y="20" width="14" height="96" fill={`url(#${id}-m)`} stroke="#1e0e04" strokeWidth="2.5" />)}
        {[[35, 34], [35, 100], [167, 34], [167, 100]].map(([x, y]) => <circle key={`${x}${y}`} cx={x} cy={y} r="3" fill="#fff" fillOpacity="0.8" />)}
        <rect x="10" y="104" width="180" height="12" rx="5" fill={`url(#${id}-m)`} stroke="#1e0e04" strokeWidth="2.5" />
        {/* the lock */}
        <path d="M84 22 H116 V56 Q100 70 84 56 Z" fill={`url(#${id}-m)`} stroke="#1e0e04" strokeWidth="3" />
        <circle cx="100" cy="38" r="6" fill="#1e0e04" /><path d="M97 40 H103 L101 52 H99 Z" fill="#1e0e04" />
        <circle className="chest-gem" cx="100" cy="28" r="3.5" fill={l.gem} />
      </svg>
      <div className="chest-lid-wrap">
        <svg className="chest-lid" viewBox="0 0 200 70" aria-hidden>
          <path d="M10 66 V40 Q10 6 100 6 Q190 6 190 40 V66 Z" fill={`url(#${id}-w)`} stroke="#1e0e04" strokeWidth="4" />
          <path d="M22 30 Q100 2 178 30" stroke="#fff" strokeOpacity="0.3" strokeWidth="4" fill="none" />
          <path d="M10 48 Q100 30 190 48" stroke="#000" strokeOpacity="0.2" strokeWidth="2" fill="none" />
          {[28, 160].map((x) => <path key={x} d={`M${x} 66 V30 Q${x} 14 ${x + 7} 10 Q${x + 14} 14 ${x + 14} 30 V66 Z`} fill={`url(#${id}-m)`} stroke="#1e0e04" strokeWidth="2.5" />)}
          <rect x="8" y="58" width="184" height="10" rx="4" fill={`url(#${id}-m)`} stroke="#1e0e04" strokeWidth="2.5" />
          <path d="M86 58 H114 V68 H86 Z" fill={`url(#${id}-m)`} stroke="#1e0e04" strokeWidth="2.5" />
        </svg>
      </div>
      {state === "open" && <div className="chest-out">{children}</div>}
    </div>
  );
}
