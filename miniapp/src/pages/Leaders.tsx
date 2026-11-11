// «تالار افتخار»: the leaderboards as a hall of fame. The first three stand on a podium that rises out of the floor
// (a crown over the champion, spotlights sweeping, confetti), the rest file in below, and your own place is pinned at
// the bottom of the hall.
import { useQuery } from "@tanstack/react-query";
import { type CSSProperties, useEffect, useState } from "react";
import { Art, Burst, type Gem } from "../components/Art";
import { Icon, Skeleton } from "../components/ui";
import { call } from "../lib/api";
import { haptic } from "../lib/bale";
import { fa } from "../lib/format";
import { iconFor, ui } from "../lib/icons";

interface Entry { rank: number; name: string; race: string; class: string; value: number; level: number; me: boolean; size?: number; leader?: string }
interface BoardData {
  board: string; title: string; unit: string; entries: Entry[]; my_position: number | null;
  boards: { id: string; name: string }[]; brackets: { id: string; name: string }[]; bracket: string;
}

const BOARD_ART: Record<string, [string, Gem]> = {
  level: ["ui.laurel", "gold"], rich: ["ui.gold", "gold"], wins: ["ui.swords", "silver"], rating: ["ui.rank", "ruby"],
  path: ["ui.path", "amethyst"], bosses: ["ui.boss", "fire"], clans: ["ui.clan", "ruby"],
};
const PLACE_GEM: Gem[] = ["gold", "silver", "bronze"];

function Value({ unit, value }: { unit: string; value: number }) {
  if (unit === "🪙") return <span className="lb-val num"><Icon name={ui("ui.gold")} />{fa(value)}</span>;
  return <span className="lb-val num">{fa(value)} <small>{unit}</small></span>;
}

function Champion({ entry, unit }: { entry: Entry; unit: string }) {
  const place = entry.rank - 1;
  return (
    <div className={`podium-spot p${entry.rank} ${entry.me ? "me" : ""}`}>
      {entry.rank === 1 && <span className="podium-crown"><Art icon={ui("ui.crown")} size={42} gem="gold" /></span>}
      <span className="podium-face">
        <Art icon={entry.race ? iconFor("race", entry.race) : ui("ui.clan")} size={entry.rank === 1 ? 62 : 50} gem={PLACE_GEM[place]} />
        {entry.class && <span className="podium-class"><Icon name={iconFor("class", entry.class)} tone="ink" /></span>}
      </span>
      <b className="podium-name ellipsis">{entry.name}</b>
      <Value unit={unit} value={entry.value} />
      <div className="podium-block"><span className="podium-num">{fa(entry.rank)}</span></div>
    </div>
  );
}

export default function Leaders({ start = "level", onClose }: { start?: string; onClose: () => void }) {
  const [board, setBoard] = useState(start);
  const [bracket, setBracket] = useState("all");
  const data = useQuery({
    queryKey: ["leaders", board, bracket],
    queryFn: () => call<BoardData>(`leaders?board=${board}&bracket=${bracket}`),
    placeholderData: (previous) => previous,
  });
  const d = data.data;
  const top = d?.entries.slice(0, 3) ?? [];
  const podium = [top[1], top[0], top[2]].filter(Boolean) as Entry[];
  const rest = d?.entries.slice(3) ?? [];
  const pick = (id: string) => { haptic(); setBoard(id); };
  useEffect(() => { document.querySelector(".lb-board.on")?.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" }); }, [board, d?.boards.length]);

  return (
    <div className="hall">
      <span className="hall-beam b1" /><span className="hall-beam b2" />
      <div className="g-title">
        <button className="g-back" onClick={onClose} aria-label="بستن"><Icon name={ui("ui.back")} /></button>
        <h2>تالار افتخار</h2>
      </div>
      <div className="lb-boards">
        {(d?.boards ?? Object.keys(BOARD_ART).map((id) => ({ id, name: "" }))).map((b) => {
          const [icon, gem] = BOARD_ART[b.id] ?? ["ui.trophy", "gold"];
          return (
            <button key={b.id} className={`lb-board ${board === b.id ? "on" : ""}`} onClick={() => pick(b.id)}>
              <span className="lb-medal"><Art icon={ui(icon)} size={30} gem={gem} /></span>{b.name}
            </button>
          );
        })}
      </div>
      {!!d?.brackets.length && (
        <div className="lb-brackets">
          {d.brackets.map((b) => <button key={b.id} className={`lb-bracket ${bracket === b.id ? "on" : ""}`} onClick={() => setBracket(b.id)}>{b.name}</button>)}
        </div>
      )}
      <div className="hall-body">
        {!d ? <Skeleton height={64} count={4} /> : !d.entries.length ? (
          <div className="lb-empty"><Art icon={ui("ui.trophy")} size={80} gem="silver" /><p>هنوز کسی در این جدول نیست؛ اولین نفر باشید!</p></div>
        ) : (
          <div key={`${d.board}-${d.bracket}`}>
            <div className="podium">
              <Burst count={30} />
              {podium.map((entry) => <Champion key={entry.rank} entry={entry} unit={d.unit} />)}
            </div>
            <div className="lb-list">
              {rest.map((entry, i) => (
                <div key={entry.rank} className={`lb-row ${entry.me ? "me" : ""}`} style={{ "--i": i } as CSSProperties}>
                  <span className="lb-rank num">{fa(entry.rank)}</span>
                  <span className="lb-face"><Art icon={entry.race ? iconFor("race", entry.race) : ui("ui.clan")} size={34} gem={entry.me ? "emerald" : entry.race ? "sapphire" : "ruby"} /></span>
                  <span className="grow lb-who">
                    <b className="ellipsis">{entry.name}</b>
                    <small>{entry.class ? <Icon name={iconFor("class", entry.class)} /> : <Icon name={ui("ui.people")} />}سطح {fa(entry.level)}{entry.size ? ` · ${fa(entry.size)} عضو` : ""}</small>
                  </span>
                  <Value unit={d.unit} value={entry.value} />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      {d && (
        <div className="lb-mine">
          <Art icon={ui("ui.rank")} size={34} gem="emerald" />
          <span className="grow">{d.my_position ? <>رتبه‌ی شما در این جدول</> : "شما هنوز در این جدول رتبه ندارید"}</span>
          {d.my_position && <span className="lb-mine-n num">#{fa(d.my_position)}</span>}
        </div>
      )}
    </div>
  );
}
