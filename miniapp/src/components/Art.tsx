// Game art from the downloaded vector icons, drawn as a sticker: a dark outline, a jewel-coloured body, a gloss on top
// and a soft shadow under it. The same icon set as everywhere else, but it reads as a picture, not as a symbol.
import { type CSSProperties, useEffect, useState } from "react";
import { fa } from "../lib/format";
import { iconUrl } from "./ui";

/** A number that runs up from zero (or from where it was) to its value. */
export function Count({ to, delay = 0, ms = 900 }: { to: number; delay?: number; ms?: number }) {
  const [now, setNow] = useState(0);
  useEffect(() => {
    let frame = 0;
    const from = now;
    const begin = performance.now() + delay;
    const tick = (time: number) => {
      const t = Math.max(0, Math.min(1, (time - begin) / ms));
      setNow(Math.round(from + (to - from) * (1 - Math.pow(1 - t, 3))));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [to, delay, ms]);  // eslint-disable-line react-hooks/exhaustive-deps
  return <>{fa(now)}</>;
}

export type Gem = "gold" | "ruby" | "emerald" | "sapphire" | "amethyst" | "silver" | "bronze" | "fire" | "frost";

export function Art({ icon, size = 64, gem = "gold", className = "", style }: {
  icon: string; size?: number; gem?: Gem; className?: string; style?: CSSProperties;
}) {
  const mask = { "--icon": iconUrl(icon) } as CSSProperties;
  return (
    <span className={`art g-${gem} ${className}`} style={{ width: size, height: size, ...style }} aria-hidden>
      <span className="art-edge" style={mask} />
      <span className="art-body" style={mask} />
      <span className="art-gloss" style={mask} />
    </span>
  );
}

/** A heap of the same picture: one for a small pack, three for a big one (as treasure piles up). */
export function Pile({ icon, count, size = 58, gem = "gold" }: { icon: string; count: number; size?: number; gem?: Gem }) {
  const n = Math.max(1, Math.min(3, count));
  return (
    <span className={`pile n${n}`}>
      {Array.from({ length: n }, (_, i) => <Art key={i} icon={icon} size={size} gem={gem} className={`p${i}`} />)}
    </span>
  );
}

/** A short shower of gold and sparks over whatever was just won. */
export function Burst({ count = 26 }: { count?: number }) {
  return (
    <span className="burst" aria-hidden>
      {Array.from({ length: count }, (_, i) => {
        const angle = (i / count) * Math.PI * 2;
        const distance = 90 + ((i * 37) % 70);
        return (
          <i key={i} style={{
            "--x": `${Math.cos(angle) * distance}px`, "--y": `${Math.sin(angle) * distance}px`,
            "--r": `${(i * 47) % 360}deg`, animationDelay: `${(i % 6) * 30}ms`,
            background: ["#f8e3a1", "#e3bd62", "#b0d0ff", "#9ff0c8", "#ffb0b0"][i % 5],
          } as CSSProperties} />
        );
      })}
    </span>
  );
}
