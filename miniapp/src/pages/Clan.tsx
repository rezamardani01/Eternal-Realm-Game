// «خاندان»: the clan's banner waving over its keep, three medallions for what it owns, and its halls as doors of their
// own (the war hall burns, coins drop into the vault, the shop has an awning); below it the roster of its warriors.
// Without a clan: an empty flagpole and three ways to get a banner.
import { useQuery } from "@tanstack/react-query";
import { type CSSProperties, useState } from "react";
import { Art, Count, type Gem } from "../components/Art";
import { Button, Icon, Sheet, Skeleton } from "../components/ui";
import { call } from "../lib/api";
import { haptic } from "../lib/bale";
import { fa, ROLE_NAMES } from "../lib/format";
import { ui } from "../lib/icons";
import type { ClanPage } from "../lib/types";
import { useApp } from "../store";

const HALLS: { label: string; about: string; icon: string; screen: string; a?: string; gem: Gem; deco: string }[] = [
  { label: "جنگ خاندان‌ها", about: "نبرد با خاندان رقیب", icon: "ui.war", screen: "cwar", gem: "ruby", deco: "flame" },
  { label: "لیگ هفتگی", about: "جام هر هفته", icon: "ui.season", screen: "clanwar", gem: "amethyst", deco: "shine" },
  { label: "کمک به خزانه", about: "سکه بده، قوی‌تر شو", icon: "ui.vault", screen: "clandonate", gem: "gold", deco: "coins" },
  { label: "فروشگاه خاندان", about: "با خان‌پوینت بخر", icon: "ui.market", screen: "clanshop", gem: "emerald", deco: "awning" },
  { label: "برترین خاندان‌ها", about: "جدول افتخار", icon: "ui.trophy", screen: "clantop", gem: "gold", deco: "shine" },
  { label: "اعضا و مقام‌ها", about: "مدیریت جنگاوران", icon: "ui.people", screen: "clanmembers", a: "0", gem: "sapphire", deco: "torch" },
];

function Banner({ empty = false }: { empty?: boolean }) {
  return (
    <svg className={`clan-flag ${empty ? "empty" : ""}`} viewBox="0 0 120 150" aria-hidden>
      <defs>
        <linearGradient id="cf-cloth" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#d04050" /><stop offset="0.6" stopColor="#8a1a2a" /><stop offset="1" stopColor="#4a0812" /></linearGradient>
        <linearGradient id="cf-pole" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#8a5a14" /><stop offset="0.5" stopColor="#fbe9ad" /><stop offset="1" stopColor="#8a5a14" /></linearGradient>
      </defs>
      <rect x="12" y="6" width="6" height="140" rx="3" fill="url(#cf-pole)" />
      <circle cx="15" cy="7" r="6" fill="#f6d26a" stroke="#3a2404" strokeWidth="1.5" />
      {!empty && (
        <g className="cf-cloth">
          <path d="M18 16 C 50 10, 80 22, 112 14 L 112 96 C 84 104, 50 92, 18 100 Z" fill="url(#cf-cloth)" stroke="#3a0408" strokeWidth="2" />
          <path d="M18 24 C 50 18, 80 30, 112 22" stroke="#f6d26a" strokeWidth="3" fill="none" />
          <path d="M18 92 C 50 84, 80 96, 112 88" stroke="#f6d26a" strokeWidth="3" fill="none" />
        </g>
      )}
    </svg>
  );
}

export default function Clan() {
  const { me, open, toast, refresh } = useApp();
  const page = useQuery({ queryKey: ["clan"], queryFn: () => call<ClanPage>("clan") });
  const [founding, setFounding] = useState(false);
  const [name, setName] = useState("");

  if (!page.data) return <div className="page"><Skeleton height={160} count={2} /></div>;
  const clan = page.data.clan;
  const go = (screen: string, a?: string) => { haptic(); open(screen, a); };

  if (!clan) {
    const found = async () => {
      try {
        await call("screen", { s: "clancreate", a: name.trim() });
        toast("خاندان شما ساخته شد!");
        setFounding(false);
        await refresh();
      } catch (error) {
        toast(error instanceof Error ? error.message : "نشد", true);
      }
    };
    return (
      <div className="page clan">
        <div className="keep-hero lonely">
          <span className="keep-rays" />
          <Banner empty />
          <h1 className="keep-name">هنوز پرچمی ندارید</h1>
          <p className="keep-sub">قهرمانان کنار هم می‌مانند، خزانه‌ی مشترک می‌سازند و با خاندان‌های دیگر می‌جنگند.</p>
        </div>
        <div className="clan-doors">
          <button className="door g-gold wide" style={{ "--i": 0 } as CSSProperties} onClick={() => setFounding(true)}>
            <span className="door-arch" /><Art icon={ui("ui.crown")} size={48} gem="gold" />
            <b>ساخت خاندان</b><small className="num">{fa(page.data.create_gold ?? 0)} سکه</small>
          </button>
          <button className="door g-sapphire" style={{ "--i": 1 } as CSSProperties} onClick={() => go("clanlist", "0")}>
            <span className="door-arch" /><Art icon={ui("ui.search")} size={44} gem="sapphire" /><b>فهرست خاندان‌ها</b><small>پیوستن به یکی</small>
          </button>
          <button className="door g-gold" style={{ "--i": 2 } as CSSProperties} onClick={() => go("clantop")}>
            <span className="door-arch" /><Art icon={ui("ui.trophy")} size={44} gem="gold" /><b>برترین‌ها</b><small>قوی‌ترین پرچم‌ها</small>
          </button>
        </div>
        {founding && (
          <Sheet onClose={() => setFounding(false)}>
            <div style={{ display: "grid", placeItems: "center" }}><Banner /></div>
            <h3 className="title gold-text" style={{ textAlign: "center", margin: "4px 0 12px" }}>نام خاندان</h3>
            <input className="field" autoFocus value={name} maxLength={24} onChange={(event) => setName(event.target.value)} placeholder="مثلاً شیرهای شمال" />
            <p className="small muted" style={{ textAlign: "center", margin: "8px 0 12px" }}>هزینه‌ی ساخت {fa(page.data.create_gold ?? 0)} سکه است · موجودی شما {fa(me.player.gold)}</p>
            <Button kind="gold" onClick={found} disabled={name.trim().length < 2}>بنیان‌گذاری</Button>
          </Sheet>
        )}
      </div>
    );
  }

  const canManage = clan.role === "leader" || clan.role === "deputy";
  const members = page.data.members ?? [];
  const topGift = Math.max(1, ...members.map((m) => m.donated));
  return (
    <div className="page clan">
      <div className="keep-hero">
        <span className="keep-rays" />
        <div className="keep-flag"><Banner /><span className="keep-crest"><Art icon={ui("ui.clan")} size={44} gem="gold" /></span></div>
        <span className="keep-level num">{fa(clan.level)}<small>سطح</small></span>
        <h1 className="keep-name ellipsis">{clan.name}</h1>
        <div className="keep-tags">
          <span className="ktag lord"><Icon name={ui("ui.crown")} />{clan.leader}</span>
          <span className="ktag">{ROLE_NAMES[clan.role] ?? clan.role}</span>
          <span className={`ktag ${clan.open ? "open" : "shut"}`}><Icon name={ui(clan.open ? "ui.check" : "ui.lock")} />{clan.open ? "در باز" : "فقط با دعوت"}</span>
        </div>
      </div>

      <div className="medals">
        <div className="medal-card" style={{ "--i": 0 } as CSSProperties}><Art icon={ui("ui.vault")} size={40} gem="gold" /><b className="num"><Count to={clan.treasury} /></b><small>خزانه</small></div>
        <div className="medal-card" style={{ "--i": 1 } as CSSProperties}><Art icon={ui("ui.power")} size={40} gem="ruby" /><b className="num"><Count to={clan.power} /></b><small>قدرت</small></div>
        <div className="medal-card" style={{ "--i": 2 } as CSSProperties}><Art icon={ui("ui.crown")} size={40} gem="amethyst" /><b className="num"><Count to={page.data.khan_points ?? 0} /></b><small>خان‌پوینت شما</small></div>
      </div>

      <div className="seats">
        <div className="seats-head"><span><Icon name={ui("ui.people")} /> جنگاوران</span><b className="num">{fa(clan.size)} / {fa(clan.capacity)}</b></div>
        <div className="seats-row">
          {Array.from({ length: Math.min(clan.capacity, 30) }, (_, i) => (
            <span key={i} className={`seat ${i < clan.size ? "taken" : ""}`} style={{ "--i": i } as CSSProperties} />
          ))}
        </div>
      </div>

      {me.ready.gifts > 0 && (
        <div className="clan-gift"><Art icon={ui("ui.gift")} size={36} gem="ruby" /><span>{fa(me.ready.gifts)} هدیه‌ی خاندان در پیام‌های ربات منتظر باز شدن است.</span></div>
      )}

      <h3 className="section-title"><Icon name={ui("ui.castle")} />تالارهای خاندان</h3>
      <div className="clan-doors">
        {HALLS.map((hall, i) => (
          <button key={hall.screen} className={`door g-${hall.gem} d-${hall.deco}`} style={{ "--i": i } as CSSProperties} onClick={() => go(hall.screen, hall.a)}>
            <span className="door-arch" />
            {hall.deco === "awning" && <span className="awning" />}
            {hall.deco === "flame" && <span className="flames"><i /><i /><i /></span>}
            {hall.deco === "coins" && <span className="coin-drop"><i /><i /><i /></span>}
            {hall.deco === "torch" && <span className="torches"><i /><i /></span>}
            <Art icon={ui(hall.icon)} size={46} gem={hall.gem} />
            <b>{hall.label}</b><small>{hall.about}</small>
          </button>
        ))}
      </div>

      <h3 className="section-title"><Icon name={ui("ui.people")} />جنگاوران<button className="more" onClick={() => go("clanmembers", "0")}>مدیریت</button></h3>
      <div className="roster">
        {members.map((member, index) => (
          <button key={member.id} className={`warrior r-${member.role}`} style={{ "--i": index } as CSSProperties} onClick={() => go("clanmember", String(member.id))}>
            <span className="w-rank num">{fa(index + 1)}</span>
            <Art icon={ui(member.role === "leader" ? "ui.crown" : member.role === "member" ? "ui.hero" : "ui.shieldbig")} size={38} gem={member.role === "leader" ? "gold" : member.role === "member" ? "silver" : "sapphire"} />
            <span className="grow w-who">
              <b className="ellipsis">{member.name}</b>
              <small>سطح {fa(member.level)} · <Icon name={ui("ui.gold")} />{fa(member.donated)}</small>
              <span className="w-bar"><i style={{ width: `${(100 * member.donated) / topGift}%` }} /></span>
            </span>
            <span className="w-role">{ROLE_NAMES[member.role] ?? member.role}</span>
          </button>
        ))}
      </div>

      <div className="clan-foot">
        {canManage && <button className="pill-btn" onClick={() => go("clanset")}><Icon name={ui("ui.admin")} />تنظیمات خاندان</button>}
        <button className="pill-btn red" onClick={() => go("clanleaveq")}><Icon name={ui("ui.flee")} />خروج از خاندان</button>
      </div>
    </div>
  );
}
