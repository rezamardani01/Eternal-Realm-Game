// «قلمرو»: the realm as a place. A floating island under a dusk sky, painted in layers (moon, mountains with a far
// castle, a lake, cliffs, meadows, tree groves, cobbled roads), with the game's buildings standing on glowing pads down
// the middle of it. Over the island sits the HUD of a strategy game: who you are, what you own, what is waiting.
import { type CSSProperties, useMemo } from "react";
import { Art, type Gem } from "../components/Art";
import { Bar, Icon } from "../components/ui";
import { fa } from "../lib/format";
import { iconFor, iconOfEmoji, ui } from "../lib/icons";
import { type TabId, useApp } from "../store";

interface Site {
  id: string; label: string; icon: string; x: number; y: number; gem: Gem; pad: string; size?: number;
  screen?: string; a?: string; tab?: TabId;
}

const LAND = 1300;
/** Where everything stands: three lanes down the middle of the island (x in percent, y in pixels from the top). */
const SITES: Site[] = [
  { id: "keep", label: "قلعه‌ی قهرمان", icon: "b.keep", x: 50, y: 440, gem: "gold", pad: "#d9a645", size: 74, tab: "hero" },
  { id: "hall", label: "تالار بزرگان", icon: "b.hall", x: 30, y: 522, gem: "silver", pad: "#8593a9", screen: "top" },
  { id: "clan", label: "دژ خاندان", icon: "b.clan", x: 70, y: 522, gem: "sapphire", pad: "#4f8cc9", tab: "clan" },
  { id: "wheel", label: "گردونه شانس", icon: "ui.wheel", x: 50, y: 600, gem: "gold", pad: "#d9a645", screen: "wheel" },
  { id: "tavern", label: "مأموریت‌ها", icon: "b.tavern", x: 30, y: 680, gem: "bronze", pad: "#b0763c", screen: "missions" },
  { id: "market", label: "بازار", icon: "b.market", x: 70, y: 680, gem: "emerald", pad: "#3fae76", tab: "market" },
  { id: "treasury", label: "خزانه قلمرو", icon: "b.treasury", x: 50, y: 758, gem: "gold", pad: "#d9a645", screen: "premium" },
  { id: "altar", label: "محراب", icon: "b.altar", x: 30, y: 838, gem: "amethyst", pad: "#8a5ad6", screen: "altar" },
  { id: "portal", label: "سفر قهرمان", icon: "b.portal", x: 70, y: 838, gem: "amethyst", pad: "#8a5ad6", screen: "trip" },
  { id: "forge", label: "کوره آهنگری", icon: "b.forge", x: 50, y: 916, gem: "fire", pad: "#d0603a", screen: "craft" },
  { id: "farm", label: "ماجراجویی", icon: "b.farm", x: 30, y: 996, gem: "emerald", pad: "#3fae76", tab: "adventure" },
  { id: "dungeon", label: "سیاه‌چال", icon: "b.dungeon", x: 70, y: 996, gem: "ruby", pad: "#c04848", screen: "dungeon" },
  { id: "tower", label: "برج بی‌پایان", icon: "b.tower", x: 50, y: 1074, gem: "silver", pad: "#8593a9", screen: "tower" },
  { id: "city", label: "فرمانروایی", icon: "b.city", x: 30, y: 1154, gem: "emerald", pad: "#3fae76", screen: "city" },
  { id: "maze", label: "هزارتوی ابدی", icon: "b.maze", x: 70, y: 1154, gem: "sapphire", pad: "#4f8cc9", screen: "maze" },
  { id: "library", label: "داستان‌ها", icon: "b.library", x: 50, y: 1232, gem: "bronze", pad: "#b0763c", screen: "quests" },
];
/** The roads: every building is joined to the ones of the next row. */
const ROADS = SITES.flatMap((site, index) =>
  SITES.slice(index + 1).filter((next) => next.y > site.y && next.y - site.y < 100).map((next) => `M${site.x} ${site.y - 14} L${next.x} ${next.y - 14}`),
).join(" ");

/** The island's outline, in the painting's own units (400 wide). */
const ISLE = "M40 372 C 6 470, 14 600, 22 760 C 28 920, 18 1080, 70 1200 C 120 1286, 280 1290, 330 1206 C 384 1110, 372 930, 380 760 C 388 600, 396 470, 360 372 C 300 334, 100 334, 40 372 Z";
/** Groves along the island's rim: [x, y, scale]. */
const GROVES: [number, number, number][] = [
  [42, 410, 1], [358, 414, 1.1], [30, 590, 1.15], [372, 600, 1], [24, 760, 1.2], [376, 772, 1.05], [30, 930, 1], [370, 940, 1.15],
  [52, 1100, 1.1], [348, 1110, 1], [110, 1240, 0.9], [290, 1244, 0.95], [200, 385, 0.7],
];

function seeded(n: number) {
  let s = n;
  return () => ((s = (s * 9301 + 49297) % 233280) / 233280);
}

export default function Realm() {
  const { me, open, setTab } = useApp();
  const p = me.player;
  const ready = me.ready;

  const paint = useMemo(() => {
    const rnd = seeded(7);
    const stars = Array.from({ length: 34 }, () => [rnd() * 400, rnd() * 230, 0.5 + rnd() * 1.1, rnd() * 4] as const);
    const tufts = Array.from({ length: 90 }, () => [60 + rnd() * 280, 420 + rnd() * 820, rnd()] as const);
    const flowers = Array.from({ length: 46 }, () => [50 + rnd() * 300, 430 + rnd() * 800, rnd() > 0.5 ? "#ffd6f0" : "#fff0a8"] as const);
    const flies = Array.from({ length: 14 }, (_, i) => ({ left: `${8 + rnd() * 84}%`, top: 420 + rnd() * 820, animationDelay: `${-i * 0.7}s`, animationDuration: `${7 + rnd() * 6}s` }));
    return { stars, tufts, flowers, flies };
  }, []);

  const openMission = me.missions.find((m) => m.done && !m.claimed) ?? me.missions.find((m) => !m.claimed);
  const claimable = me.missions.filter((m) => m.done && !m.claimed).length;
  /** What floats over a building: a picture when something is waiting there. */
  const flags: Record<string, { icon: string; alert?: boolean }> = {};
  if (claimable || me.week.ready) flags.tavern = { icon: ui("ui.gift") };
  if (ready.maze_floor) flags.maze = { icon: ui("ui.swords") };
  if (ready.gifts) flags.clan = { icon: ui("ui.gift") };
  if (ready.fight) flags.portal = { icon: ui("ui.swords"), alert: true };

  const enter = (site: Site) => (site.tab ? setTab(site.tab) : open(site.screen!, site.a));

  return (
    <>
      <div className="valley">
        <div className="valley-land" style={{ height: LAND }}>
          <svg className="paint" viewBox={`0 0 400 ${LAND}`} preserveAspectRatio="xMidYMin slice" aria-hidden>
            <defs>
              <linearGradient id="v-sky" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#09172d" /><stop offset="0.45" stopColor="#1d3d6d" /><stop offset="0.8" stopColor="#9a4a78" /><stop offset="1" stopColor="#f2a35e" />
              </linearGradient>
              <radialGradient id="v-moon" cx="0.38" cy="0.35"><stop offset="0" stopColor="#fffbe6" /><stop offset="0.65" stopColor="#f6dc98" /><stop offset="1" stopColor="#d4a548" /></radialGradient>
              <radialGradient id="v-halo"><stop offset="0" stopColor="#ffe7a8" stopOpacity="0.55" /><stop offset="1" stopColor="#ffe7a8" stopOpacity="0" /></radialGradient>
              <linearGradient id="v-far" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#4c6ea1" /><stop offset="1" stopColor="#2a4368" /></linearGradient>
              <linearGradient id="v-near" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#283e5e" /><stop offset="1" stopColor="#1c1b3c" /></linearGradient>
              <linearGradient id="v-lake" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#3a3f7a" /><stop offset="0.2" stopColor="#1d2c5a" /><stop offset="1" stopColor="#0a1028" /></linearGradient>
              <linearGradient id="v-cliff" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#8a5f38" /><stop offset="0.5" stopColor="#5a3b22" /><stop offset="1" stopColor="#2a1a0e" /></linearGradient>
              <radialGradient id="v-grass" cx="0.5" cy="0.42" r="0.62">
                <stop offset="0" stopColor="#8fcf5e" /><stop offset="0.45" stopColor="#5fa848" /><stop offset="0.85" stopColor="#3b7e3a" /><stop offset="1" stopColor="#2a5e2e" />
              </radialGradient>
              <radialGradient id="v-sun" cx="0.5" cy="0.25" r="0.5"><stop offset="0" stopColor="#fff2b0" stopOpacity="0.5" /><stop offset="1" stopColor="#fff2b0" stopOpacity="0" /></radialGradient>
              <radialGradient id="v-tree" cx="0.35" cy="0.3"><stop offset="0" stopColor="#7fd06a" /><stop offset="0.6" stopColor="#2f8a45" /><stop offset="1" stopColor="#14502c" /></radialGradient>
              <radialGradient id="v-pond" cx="0.4" cy="0.35"><stop offset="0" stopColor="#8fe0ff" /><stop offset="0.6" stopColor="#3a9ad0" /><stop offset="1" stopColor="#1d5a8a" /></radialGradient>
              <filter id="v-soft"><feGaussianBlur stdDeviation="14" /></filter>
              <filter id="v-blur2"><feGaussianBlur stdDeviation="2" /></filter>
              <clipPath id="v-isle"><path d={ISLE} /></clipPath>
            </defs>

            {/* sky, stars and moon */}
            <rect width="400" height="340" fill="url(#v-sky)" />
            {paint.stars.map(([x, y, r, d], i) => <circle key={i} className="v-star" cx={x} cy={y} r={r} fill="#fff" style={{ animationDelay: `${d}s` }} />)}
            <circle cx="300" cy="150" r="78" fill="url(#v-halo)" />
            <circle cx="300" cy="150" r="30" fill="url(#v-moon)" />
            <circle cx="290" cy="142" r="5" fill="#e8c97a" opacity="0.6" /><circle cx="310" cy="160" r="3.5" fill="#e8c97a" opacity="0.5" />
            <g className="v-cloud" opacity="0.5" fill="#f7c9d8">
              <ellipse cx="80" cy="200" rx="46" ry="9" /><ellipse cx="104" cy="194" rx="26" ry="9" /><ellipse cx="330" cy="236" rx="40" ry="7" />
            </g>

            {/* far mountains with a castle on the high peak */}
            <path d="M0 340 L0 262 L34 226 L62 250 L104 196 L150 246 L188 214 L232 258 L270 222 L318 266 L360 232 L400 258 L400 340 Z" fill="url(#v-far)" />
            <path d="M104 196 L116 210 L108 212 Z M270 222 L280 234 L272 235 Z" fill="#b6d3ff" opacity="0.45" />
            <g fill="#1d314e">
              <rect x="94" y="180" width="20" height="22" /><rect x="90" y="172" width="7" height="16" /><rect x="111" y="172" width="7" height="16" />
              <path d="M90 172 L93.5 162 L97 172 Z M111 172 L114.5 162 L118 172 Z M100 180 L104 168 L108 180 Z" />
            </g>
            <circle cx="104" cy="190" r="1.6" fill="#ffd27a" className="v-window" />
            <path d="M0 340 L0 292 Q40 262 82 290 Q120 312 160 282 Q206 252 250 286 Q296 314 336 280 Q370 258 400 280 L400 340 Z" fill="url(#v-near)" />

            {/* the lake the island floats over */}
            <rect y="330" width="400" height={LAND - 330} fill="url(#v-lake)" />
            <rect y="326" width="400" height="16" fill="#f2a35e" opacity="0.35" filter="url(#v-blur2)" />
            {[360, 470, 640, 820, 1010, 1180].map((y, i) => (
              <g key={y} stroke="#b9c8ff" strokeWidth="1.3" strokeLinecap="round" opacity={0.28 - i * 0.03}>
                <path className="water-shine" d={`M${8 + (i % 2) * 12} ${y} h30 M${350 - (i % 3) * 6} ${y + 14} h34`} strokeDasharray="14 10" />
              </g>
            ))}

            {/* the island: its cliff, its meadow, light and shade on the grass */}
            <path d={ISLE} fill="url(#v-cliff)" transform="translate(0 34)" />
            <path d={ISLE} fill="#1b0f08" opacity="0.4" transform="translate(0 48) scale(1 1)" filter="url(#v-blur2)" />
            <path d={ISLE} fill="url(#v-grass)" />
            <g clipPath="url(#v-isle)">
              <ellipse cx="140" cy="520" rx="110" ry="60" fill="#b6e47a" opacity="0.35" filter="url(#v-soft)" />
              <ellipse cx="290" cy="760" rx="100" ry="70" fill="#b6e47a" opacity="0.3" filter="url(#v-soft)" />
              <ellipse cx="120" cy="980" rx="100" ry="60" fill="#b6e47a" opacity="0.28" filter="url(#v-soft)" />
              <ellipse cx="300" cy="560" rx="70" ry="50" fill="#1f5a2c" opacity="0.35" filter="url(#v-soft)" />
              <ellipse cx="90" cy="760" rx="60" ry="80" fill="#1f5a2c" opacity="0.3" filter="url(#v-soft)" />
              <ellipse cx="290" cy="1080" rx="80" ry="60" fill="#1f5a2c" opacity="0.32" filter="url(#v-soft)" />
              <ellipse cx="200" cy="420" rx="200" ry="140" fill="url(#v-sun)" />
              <path d={ISLE} fill="none" stroke="#c6f08a" strokeWidth="5" opacity="0.5" />
              {paint.tufts.map(([x, y, r], i) => (
                <path key={i} d={`M${x} ${y} l-2.5 -6 M${x} ${y} l0 -7.5 M${x} ${y} l2.5 -6`} stroke={r > 0.5 ? "#3e8a3a" : "#9fd86a"} strokeWidth="1.4" strokeLinecap="round" opacity="0.75" />
              ))}
              {paint.flowers.map(([x, y, c], i) => <circle key={i} cx={x} cy={y} r="1.8" fill={c} opacity="0.9" />)}
              {/* two ponds */}
              <ellipse cx="352" cy="676" rx="30" ry="15" fill="#1d4a2a" opacity="0.6" />
              <ellipse cx="350" cy="672" rx="27" ry="13" fill="url(#v-pond)" />
              <path className="water-shine" d="M336 670 h14 M352 676 h10" stroke="#e8fbff" strokeWidth="1.2" strokeDasharray="6 5" strokeLinecap="round" />
              <ellipse cx="48" cy="1036" rx="26" ry="13" fill="#1d4a2a" opacity="0.6" />
              <ellipse cx="50" cy="1032" rx="23" ry="11" fill="url(#v-pond)" />
              <path className="water-shine" d="M38 1030 h12 M52 1036 h8" stroke="#e8fbff" strokeWidth="1.2" strokeDasharray="6 5" strokeLinecap="round" />
              {/* rocks */}
              {[[24, 680], [372, 860], [70, 1170], [330, 1170], [372, 480]].map(([x, y]) => (
                <g key={`${x}-${y}`}><ellipse cx={x} cy={y + 4} rx="11" ry="4" fill="#173a1e" opacity="0.5" /><path d={`M${x - 10} ${y + 3} Q${x - 8} ${y - 9} ${x} ${y - 10} Q${x + 10} ${y - 8} ${x + 10} ${y + 3} Z`} fill="#9a9ab0" /><path d={`M${x - 6} ${y - 3} Q${x - 3} ${y - 8} ${x + 3} ${y - 8}`} stroke="#e6e6f2" strokeWidth="1.6" fill="none" strokeLinecap="round" /></g>
              ))}
            </g>

            {/* groves of round trees on the rim */}
            {GROVES.map(([x, y, s], i) => (
              <g key={i} transform={`translate(${x} ${y}) scale(${s})`} className="v-grove" style={{ animationDelay: `${-i * 0.6}s` }}>
                <ellipse cx="0" cy="16" rx="30" ry="8" fill="#123a1e" opacity="0.5" />
                <rect x="-2.5" y="2" width="5" height="12" rx="2" fill="#5a3a1e" />
                <circle cx="-14" cy="2" r="13" fill="url(#v-tree)" /><circle cx="14" cy="4" r="12" fill="url(#v-tree)" /><circle cx="0" cy="-8" r="16" fill="url(#v-tree)" />
                <circle cx="-5" cy="-14" r="5" fill="#c4f59a" opacity="0.45" />
              </g>
            ))}
          </svg>

          {/* the cobbled roads between the buildings */}
          <svg className="v-roads" viewBox={`0 0 100 ${LAND}`} preserveAspectRatio="none" aria-hidden>
            <path d={ROADS} fill="none" stroke="#4a3018" strokeWidth="17" strokeLinecap="round" vectorEffect="non-scaling-stroke" opacity="0.55" />
            <path d={ROADS} fill="none" stroke="#e2c58a" strokeWidth="12" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            <path d={ROADS} fill="none" stroke="#b8945a" strokeWidth="5" strokeLinecap="round" strokeDasharray="3 7" vectorEffect="non-scaling-stroke" />
            <path d={ROADS} fill="none" stroke="#fff3cf" strokeWidth="1.2" strokeLinecap="round" vectorEffect="non-scaling-stroke" strokeDasharray="2 24" className="v-march" />
          </svg>

          {paint.flies.map((style, i) => <i key={i} className="firefly" style={style} />)}

          {SITES.map((site, index) => (
            <button key={site.id} className="site" style={{ left: `${site.x}%`, top: site.y, zIndex: site.y, "--pad": site.pad, "--in": `${index * 45}ms` } as CSSProperties} onClick={() => enter(site)}>
              <span className="ring" />
              <span className="pad" />
              {flags[site.id] && <span className={`flag ${flags[site.id].alert ? "alert" : ""}`}><Icon name={flags[site.id].icon} /></span>}
              <Art icon={ui(site.icon)} size={site.size ?? 58} gem={site.gem} />
              <span className="label">{site.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="hud-top">
        <button className="avatar" onClick={() => setTab("hero")}>
          <Icon name={iconFor("race", p.race.id, p.race.emoji)} size={42} />
          <span className="lvl num">{fa(p.level)}</span>
        </button>
        <div className="hud-id">
          <div className="nameplate"><span className="ellipsis">{p.name}</span>{p.vip && <span className="tag green">VIP</span>}</div>
          <div><span className="powerplate num"><Icon name={ui("ui.power")} />{fa(me.power)}</span></div>
          <div className="minibar" style={{ width: 120 }}><i style={{ width: `${Math.min(100, (100 * p.xp) / p.xp_needed)}%` }} /></div>
        </div>
        <div className="res">
          <button className="chip num" onClick={() => open("prem", "coins")}><Icon name={ui("ui.gold")} />{fa(p.gold)}<span className="add">+</span></button>
          <button className="chip num" onClick={() => open("prem", "crystals")}><Icon name={ui("ui.crystal")} />{fa(p.crystal)}<span className="add">+</span></button>
          <button className="chip num" onClick={() => open("rest")}><Icon name={ui("ui.energy")} />{fa(p.energy)}/{fa(p.max_energy)}</button>
        </div>
      </div>

      <div className="side start">
        <button className={`orb ${ready.daily ? "gold" : ""}`} onClick={() => open("daily")}>
          <span className="disc"><Icon name={ui("ui.chest")} /></span>{ready.daily && <span className="pip">!</span>}روزانه
        </button>
        <button className="orb gold" onClick={() => open("chests")}><span className="disc"><Icon name={ui("ui.gift")} /></span>صندوق‌ها</button>
        <button className="orb" onClick={() => open("path")}><span className="disc"><Icon name={ui("ui.path")} /></span>مسیر</button>
        <button className="orb" onClick={() => open("rseason")}><span className="disc"><Icon name={ui("ui.season")} /></span>فصل</button>
        <button className="orb gold" onClick={() => open("vip")}><span className="disc"><Icon name={ui("ui.crown")} /></span>VIP</button>
      </div>
      <div className="side end">
        {ready.fight && (
          <button className="orb red" onClick={() => open("sfight")}><span className="disc"><Icon name={ui("ui.swords")} tone="silver" /></span><span className="pip">!</span>نبرد</button>
        )}
        {ready.rescue > 0 && (
          <button className="orb red" onClick={() => open("rescue")}><span className="disc"><Icon name={ui("ui.clock")} tone="silver" /></span><span className="pip">!</span>زنجیره</button>
        )}
        {ready.popup && (
          <button className="orb gold" onClick={() => open("popup", String(ready.popup!.id))}>
            <span className="disc"><Icon name={iconOfEmoji(ready.popup.emoji) || ui("ui.gift")} /></span><span className="pip">!</span>اتفاق
          </button>
        )}
        <button className="orb" onClick={() => open("ach")}><span className="disc"><Icon name={ui("ui.trophy")} /></span>دستاورد</button>
        <button className="orb" onClick={() => open("contests")}><span className="disc"><Icon name={ui("ui.rank")} /></span>مسابقه</button>
        <button className="orb" onClick={() => open("friends")}><span className="disc"><Icon name={ui("ui.friends")} /></span>دوستان</button>
        {me.is_admin && <button className="orb red" onClick={() => open("adm")}><span className="disc"><Icon name={ui("ui.admin")} tone="silver" /></span>مدیریت</button>}
      </div>

      {openMission && (
        <button className="quest-strip" onClick={() => open("missions")}>
          <Icon name={iconOfEmoji(openMission.emoji) || ui("ui.mission")} size={26} />
          <div className="grow">
            <div className="small ellipsis" style={{ fontWeight: 700 }}>{openMission.title}</div>
            <Bar value={openMission.progress} max={openMission.target} tone="emerald" thin />
          </div>
          <span className={`tag ${openMission.done ? "green" : "gold"} num`}>
            {openMission.done ? "دریافت پاداش" : <>{fa(openMission.progress)}/{fa(openMission.target)}</>}
          </span>
        </button>
      )}
    </>
  );
}
