// «بازار»: a bazaar street. A striped awning over the coin purse, three shop fronts with swinging signs (the treasury,
// the item shop, today's deals), a row of trade stalls, and the players' board where every listing is an item in a
// rarity frame with a hanging price tag.
import { useQuery } from "@tanstack/react-query";
import { type CSSProperties, useState } from "react";
import { Art, type Gem } from "../components/Art";
import { Chest } from "../components/Chest";
import { Icon, Skeleton } from "../components/ui";
import { call } from "../lib/api";
import { haptic } from "../lib/bale";
import { fa } from "../lib/format";
import { iconFor, ui } from "../lib/icons";
import type { Listing } from "../lib/types";
import { useApp } from "../store";

const SORTS = [
  { id: "new", label: "تازه‌ترین" },
  { id: "cheap", label: "ارزان‌ترین" },
  { id: "expensive", label: "گران‌ترین" },
  { id: "rare", label: "کمیاب‌ترین" },
];
const FRONTS: { label: string; about: string; icon: string; screen: string; gem: Gem; tone: string }[] = [
  { label: "خزانه قلمرو", about: "سکه، کریستال، بسته‌ها و VIP", icon: "ui.treasury", screen: "premium", gem: "gold", tone: "gold" },
  { label: "فروشگاه آیتم", about: "سلاح، زره و معجون", icon: "ui.market", screen: "shop", gem: "emerald", tone: "green" },
  { label: "تخفیف امروز", about: "هر روز عوض می‌شود", icon: "ui.gift", screen: "deals", gem: "ruby", tone: "red" },
];
const STALLS: { label: string; icon: string; screen: string; gem: Gem }[] = [
  { label: "فروش کالا", icon: "ui.gold", screen: "msell", gem: "gold" },
  { label: "آگهی‌های من", icon: "ui.mission", screen: "mine", gem: "bronze" },
  { label: "مبادله", icon: "ui.exchange", screen: "exch", gem: "sapphire" },
  { label: "آهنگری", icon: "ui.anvil", screen: "craft", gem: "fire" },
  { label: "گردونه", icon: "ui.wheel", screen: "wheel", gem: "gold" },
  { label: "VIP", icon: "ui.crown", screen: "vip", gem: "amethyst" },
  { label: "آلبوم کارت", icon: "ui.cards", screen: "album", gem: "emerald" },
];
const GEM_BY_RARITY: Gem[] = ["silver", "silver", "emerald", "sapphire", "amethyst", "gold", "ruby"];

export default function Market() {
  const { me, open } = useApp();
  const [sort, setSort] = useState("new");
  const [page, setPage] = useState(0);
  const board = useQuery({
    queryKey: ["market", sort, page],
    queryFn: () => call<{ listings: Listing[]; more: boolean }>(`market?sort=${sort}&page=${page}`),
  });
  const go = (screen: string, a?: string) => { haptic(); open(screen, a); };

  return (
    <div className="page bazaar">
      <div className="bz-awning" />
      <div className="bz-purse">
        <span className="bz-coin"><Art icon={ui("ui.gold")} size={30} gem="gold" /><b className="num">{fa(me.player.gold)}</b></span>
        <span className="bz-coin"><Art icon={ui("ui.crystal")} size={30} gem="sapphire" /><b className="num">{fa(me.player.crystal)}</b></span>
      </div>

      <div className="bz-fronts">
        {FRONTS.map((f, i) => (
          <button key={f.screen} className={`bz-front t-${f.tone}`} style={{ "--i": i } as CSSProperties} onClick={() => go(f.screen)}>
            <span className="bz-sign"><b>{f.label}</b></span>
            <span className="bz-door"><Art icon={ui(f.icon)} size={i === 0 ? 62 : 50} gem={f.gem} /></span>
            <small>{f.about}</small>
          </button>
        ))}
      </div>

      <button className="bz-chests" onClick={() => go("chests")}>
        <Chest look="royal" state="idle" size={84} />
        <span className="grow"><b>گنجینه‌ی صندوقچه‌ها</b><small>بخرید، باز کنید، گنج بیابید</small></span>
        <span className="g-btn" style={{ padding: "8px 14px" }}>ورود</span>
      </button>

      <h3 className="section-title"><Icon name={ui("ui.exchange")} />غرفه‌های داد و ستد</h3>
      <div className="bz-stalls">
        {STALLS.map((s, i) => (
          <button key={s.screen} className="bz-stall" style={{ "--i": i } as CSSProperties} onClick={() => go(s.screen)}>
            <span className="bz-roof" />
            <Art icon={ui(s.icon)} size={40} gem={s.gem} />
            <span>{s.label}</span>
          </button>
        ))}
      </div>

      <h3 className="section-title"><Icon name={ui("ui.market")} />تخته‌ی بازار بازیکنان</h3>
      <div className="bz-sorts">
        {SORTS.map((option) => (
          <button key={option.id} className={`lb-bracket ${sort === option.id ? "on" : ""}`} onClick={() => { setSort(option.id); setPage(0); }}>{option.label}</button>
        ))}
      </div>
      {!board.data ? <Skeleton height={110} count={2} /> : board.data.listings.length === 0 ? (
        <div className="lb-empty"><Art icon={ui("ui.market")} size={70} gem="silver" /><p>الان آگهی فعالی روی تخته‌ی بازار نیست.</p></div>
      ) : (
        <>
          <div className="bz-board">
            {board.data.listings.map((listing, i) => (
              <button key={listing.id} className={`bz-item r-${listing.item.rarity} ${listing.mine ? "mine" : ""}`} style={{ "--i": i } as CSSProperties} onClick={() => go("listing", String(listing.id))}>
                <span className="bz-slot"><Art icon={iconFor("item", listing.item.id, listing.item.emoji)} size={46} gem={GEM_BY_RARITY[listing.item.rarity] ?? "silver"} />
                  {(listing.qty > 1 || listing.upgrade > 0) && <i className="num">{listing.qty > 1 ? `×${fa(listing.qty)}` : `+${fa(listing.upgrade)}`}</i>}
                </span>
                <b className="ellipsis">{listing.item.name}</b>
                <small className="ellipsis">{listing.mine ? "آگهی شما" : listing.seller}</small>
                <span className="bz-tag num"><Icon name={ui("ui.gold")} />{fa(listing.price)}</span>
              </button>
            ))}
          </div>
          <div className="bz-pages">
            {page > 0 && <button className="g-btn ghost" onClick={() => setPage(page - 1)}>صفحه‌ی قبل</button>}
            {board.data.more && <button className="g-btn ghost" onClick={() => setPage(page + 1)}>صفحه‌ی بعد</button>}
          </div>
        </>
      )}
    </div>
  );
}
