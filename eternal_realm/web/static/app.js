"use strict";
// Everything user-controlled (player names, group titles...) is inserted with textContent only.

const NF = new Intl.NumberFormat("en-US");
const num = (n) => NF.format(Math.round(n || 0));
const $ = (id) => document.getElementById(id);
let CSRF = "";
let ITEMS = [];

function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}

function toast(text, bad = false) {
  const t = $("toast");
  t.textContent = text;
  t.className = "toast on" + (bad ? " err" : "");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (t.className = "toast"), 3200);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": CSRF },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    credentials: "same-origin",
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    document.body.replaceChildren(h("div", { class: "login" }, h("div", { class: "login-card" },
      h("div", { class: "logo" }, "🔒"), h("h1", {}, "نشست تمام شد"),
      h("p", {}, "در ربات «پنل وب» را بفرستید و لینک تازه بگیرید."))));
    throw new Error("session");
  }
  if (!res.ok) throw new Error(data.error || "خطا");
  return data;
}

const run = async (fn) => { try { return await fn(); } catch (e) { if (e.message !== "session") toast(e.message, true); } };

/* ---------- charts ---------- */
function barChart(title, rows, unit = "") {
  const W = 420, H = 150, pad = 18, max = Math.max(1, ...rows.map((r) => r.value));
  const bw = (W - pad * 2) / rows.length;
  const svgns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const defs = document.createElementNS(svgns, "defs");
  defs.innerHTML = '<linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#7c5cff"/></linearGradient>';
  svg.append(defs);
  rows.forEach((r, i) => {
    const bh = Math.max(2, ((H - 40) * r.value) / max);
    const x = pad + i * bw + 3;
    const rect = document.createElementNS(svgns, "rect");
    rect.setAttribute("class", "bar");
    rect.setAttribute("x", x); rect.setAttribute("y", H - 22 - bh);
    rect.setAttribute("width", Math.max(4, bw - 6)); rect.setAttribute("height", bh); rect.setAttribute("rx", 4);
    const tip = document.createElementNS(svgns, "title");
    tip.textContent = `${r.day}: ${num(r.value)} ${unit}`;
    rect.append(tip);
    svg.append(rect);
    if (i % 2 === 0) {
      const t = document.createElementNS(svgns, "text");
      t.setAttribute("class", "axis"); t.setAttribute("x", x + bw / 2 - 3); t.setAttribute("y", H - 8);
      t.setAttribute("text-anchor", "middle"); t.textContent = r.day;
      svg.append(t);
    }
  });
  return h("div", { class: "card chart" }, h("h3", {}, title), svg);
}

/* ---------- pages ---------- */
const PAGES = {
  dashboard: ["📊", "داشبورد"],
  players: ["👥", "بازیکنان"],
  groups: ["🏰", "گروه‌ها"],
  orders: ["💰", "فروش"],
  broadcast: ["📣", "پیام همگانی"],
  audit: ["🧾", "گزارش مدیریت"],
};

async function dashboard(main) {
  const s = await api("/api/stats");
  const cards = [
    ["👥", "کل بازیکنان", num(s.players), `${num(s.new_today)} جدید امروز`],
    ["🔥", "فعال در ۲۴ ساعت", num(s.active_24h), ""],
    ["💠", "اشتراک VIP فعال", num(s.vip), ""],
    ["🏰", "گروه‌ها", num(s.groups), ""],
    ["🏯", "خاندان‌ها", num(s.clans), ""],
    ["🛍️", "سفارش‌های موفق", num(s.orders), ""],
    ["💵", "فروش کل", num(s.revenue_toman), "تومان"],
    ["🪙", "سکه در گردش", num(s.gold), ""],
    ["💎", "کریستال در گردش", num(s.crystal), ""],
    ["⚔️", "دوئل‌های جاری", num(s.duels), ""],
    ["🐉", "باس‌های زنده", num(s.bosses), ""],
    ["⛔", "مسدودشده‌ها", num(s.banned), ""],
  ];
  main.append(
    h("h1", { class: "page" }, "داشبورد"), h("p", { class: "sub" }, "نمای کلی قلمرو در یک نگاه"),
    h("div", { class: "grid" }, cards.map(([ico, k, v, small]) =>
      h("div", { class: "card stat" }, h("span", { class: "ico" }, ico), h("div", { class: "k" }, k),
        h("div", { class: "v" }, v, small ? h("small", {}, " " + small) : null)))),
    h("div", { class: "charts" },
      barChart("بازیکنان جدید (۱۴ روز اخیر)", s.series.new, "نفر"),
      barChart("بازیکنان فعال هر روز", s.series.active, "نفر"),
      barChart("فروش هر روز (تومان)", s.series.revenue, "تومان")),
  );
}

function pager(state, total, per, reload) {
  const pages = Math.max(1, Math.ceil(total / per));
  return h("div", { class: "pager" },
    h("button", { class: "btn ghost", disabled: state.page <= 0, onclick: () => { state.page--; reload(); } }, "قبلی"),
    h("span", {}, `صفحه ${num(state.page + 1)} از ${num(pages)} · ${num(total)} مورد`),
    h("button", { class: "btn ghost", disabled: state.page + 1 >= pages, onclick: () => { state.page++; reload(); } }, "بعدی"));
}

async function players(main) {
  const state = { page: 0, q: "" };
  const holder = h("div");
  const search = h("input", { placeholder: "جستجوی نام، شناسه عددی یا یوزرنیم...", size: 34 });
  async function load() {
    const d = await api(`/api/players?page=${state.page}&q=${encodeURIComponent(state.q)}`);
    const body = h("tbody", {}, d.rows.map((p) => h("tr", { class: "click", onclick: () => run(() => openPlayer(p.id)) },
      h("td", {}, p.name), h("td", {}, num(p.level)), h("td", {}, num(p.gold)), h("td", {}, num(p.crystal)),
      h("td", {}, `${num(p.wins)} / ${num(p.losses)}`),
      h("td", {}, p.banned ? h("span", { class: "badge bad" }, "مسدود") : p.vip ? h("span", { class: "badge warn" }, "VIP") : h("span", { class: "badge good" }, "فعال")),
      h("td", {}, p.created))));
    holder.replaceChildren(
      d.rows.length ? h("div", { class: "card tablewrap" }, h("table", {},
        h("thead", {}, h("tr", {}, ["نام", "سطح", "سکه", "کریستال", "برد / باخت", "وضعیت", "ثبت‌نام"].map((x) => h("th", {}, x)))), body))
        : h("div", { class: "card empty" }, "بازیکنی پیدا نشد."),
      pager(state, d.total, d.per, load));
  }
  search.addEventListener("keydown", (e) => { if (e.key === "Enter") { state.q = search.value.trim(); state.page = 0; run(load); } });
  main.append(h("h1", { class: "page" }, "بازیکنان"), h("p", { class: "sub" }, "برای مدیریت هر بازیکن روی ردیفش بزنید"),
    h("div", { class: "toolbar" }, search, h("button", { class: "btn", onclick: () => { state.q = search.value.trim(); state.page = 0; run(load); } }, "جستجو")), holder);
  await load();
}

function field(label, input) { return h("label", {}, label, " ", input); }

async function openPlayer(id) {
  const p = await api(`/api/players/${id}`);
  if (!ITEMS.length) ITEMS = await api("/api/items");
  const gold = h("input", { type: "number", placeholder: "سکه (±)" });
  const crystal = h("input", { type: "number", placeholder: "کریستال (±)" });
  const level = h("input", { type: "number", min: 1, placeholder: "سطح تازه", value: p.level });
  const item = h("select", {}, ITEMS.map((i) => h("option", { value: i.id }, i.label)));
  const qty = h("input", { type: "number", min: 1, value: 1 });
  const done = (msg) => { toast(msg); closeModal(); if (current === "players") show("players"); };
  const doPost = (path, body, msg) => run(async () => { await api(`/api/players/${id}/${path}`, { method: "POST", body }); done(msg); });

  const modal = $("modal");
  modal.replaceChildren(
    h("div", { class: "row" }, h("h2", {}, p.name), p.banned ? h("span", { class: "badge bad" }, "مسدود") : null,
      p.vip ? h("span", { class: "badge warn" }, "VIP") : null, h("span", { class: "grow" }),
      h("button", { class: "btn ghost", onclick: closeModal }, "بستن")),
    h("div", { class: "sub" }, `شناسه بله: ${p.uid}${p.username ? " · @" + p.username : ""}`),
    h("div", { class: "cols" },
      h("div", { class: "card kv" },
        ...[["سطح", num(p.level)], ["تجربه", num(p.xp)], ["انرژی", num(p.energy)], ["سکه", num(p.gold)], ["کریستال", num(p.crystal)],
          ["برد / باخت", `${num(p.wins)} / ${num(p.losses)}`], ["امتیاز لیگ", num(p.rating)], ["کارت‌ها", num(p.cards)],
          ["خاندان", p.clan ? `${p.clan.name} (${p.clan.role})` : "—"], ["عنوان", p.title || "—"], ["ثبت‌نام", p.created]]
          .flatMap(([k, v]) => [h("span", {}, k), h("span", {}, v)])),
      h("div", { class: "card" }, h("b", {}, "منابع و آیتم‌ها"),
        h("div", { class: "chips" }, p.items.length ? p.items.map((i) => h("span", { class: "badge" }, `${i.label} ×${num(i.qty)}`)) : h("span", { class: "sub" }, "خالی")),
        h("b", {}, "تجهیزات"),
        h("div", { class: "chips" }, p.gear.length ? p.gear.map((g) => h("span", { class: "badge" }, `${g.label}${g.upgrade ? " +" + g.upgrade : ""}${g.worn ? " ✓" : ""}`)) : h("span", { class: "sub" }, "خالی")))),
    h("div", { class: "card" }, h("b", {}, "عملیات مدیریتی"),
      h("div", { class: "row" }, gold, crystal,
        h("button", { class: "btn good", onclick: () => doPost("give", { gold: +gold.value || 0, crystal: +crystal.value || 0 }, "ثبت شد ✅") }, "اضافه / کم کردن")),
      h("div", { class: "row" }, level, h("button", { class: "btn", onclick: () => doPost("level", { level: +level.value }, "سطح عوض شد") }, "تغییر سطح")),
      h("div", { class: "row" }, item, qty, h("button", { class: "btn", onclick: () => doPost("item", { item: item.value, qty: +qty.value }, "آیتم داده شد") }, "دادن آیتم")),
      h("div", { class: "row" }, h("button", { class: p.banned ? "btn good" : "btn bad",
        onclick: () => { if (confirm(p.banned ? "آزاد شود؟" : "این بازیکن مسدود شود؟")) doPost("ban", { banned: !p.banned }, p.banned ? "آزاد شد" : "مسدود شد"); } },
        p.banned ? "آزاد کردن بازیکن" : "مسدود کردن بازیکن"))),
    h("div", { class: "card tablewrap" }, h("b", {}, "۲۰ تراکنش آخر"),
      h("table", {}, h("thead", {}, h("tr", {}, ["زمان", "سکه", "کریستال", "دلیل"].map((x) => h("th", {}, x)))),
        h("tbody", {}, p.history.map((x) => h("tr", {}, h("td", {}, x.at), h("td", {}, num(x.gold)), h("td", {}, num(x.crystal)), h("td", {}, x.reason)))))));
  $("modalBack").classList.add("on");
}

function closeModal() { $("modalBack").classList.remove("on"); }

async function groups(main) {
  const rows = await api("/api/groups");
  main.append(h("h1", { class: "page" }, "گروه‌ها"), h("p", { class: "sub" }, `${num(rows.length)} گروه ثبت شده`),
    rows.length ? h("div", { class: "card tablewrap" }, h("table", {},
      h("thead", {}, h("tr", {}, ["نام گروه", "اعضای بازیکن", "وضعیت", "آخرین فعالیت", "ثبت"].map((x) => h("th", {}, x)))),
      h("tbody", {}, rows.map((g) => h("tr", {}, h("td", {}, g.title), h("td", {}, num(g.members)),
        h("td", {}, h("span", { class: "badge " + (g.enabled ? "good" : "bad") }, g.enabled ? "فعال" : "غیرفعال")), h("td", {}, g.seen), h("td", {}, g.created))))))
      : h("div", { class: "card empty" }, "هنوز گروهی ثبت نشده."));
}

async function orders(main) {
  const state = { page: 0 };
  const holder = h("div");
  async function load() {
    const d = await api(`/api/orders?page=${state.page}`);
    const cls = { delivered: "good", paid: "warn", pending: "", failed: "bad", refunded: "bad" };
    const txt = { delivered: "تحویل شد", paid: "پرداخت شد", pending: "در انتظار", failed: "ناموفق", refunded: "بازگشت" };
    holder.replaceChildren(
      d.rows.length ? h("div", { class: "card tablewrap" }, h("table", {},
        h("thead", {}, h("tr", {}, ["#", "بازیکن", "محصول", "مبلغ (تومان)", "وضعیت", "زمان"].map((x) => h("th", {}, x)))),
        h("tbody", {}, d.rows.map((o) => h("tr", {}, h("td", {}, num(o.id)), h("td", {}, o.name), h("td", {}, o.pack), h("td", {}, num(o.toman)),
          h("td", {}, h("span", { class: "badge " + (cls[o.status] || "") }, txt[o.status] || o.status)), h("td", {}, o.at))))))
        : h("div", { class: "card empty" }, "هنوز سفارشی ثبت نشده."),
      pager(state, d.total, d.per, load));
  }
  main.append(h("h1", { class: "page" }, "فروش"), h("p", { class: "sub" }, "سفارش‌های خزانه (جدیدترین اول)"), holder);
  await load();
}

async function broadcast(main) {
  const text = h("textarea", { rows: 6, maxlength: 1000, placeholder: "متن پیام برای همه‌ی گروه‌های فعال..." });
  text.style.width = "100%";
  main.append(h("h1", { class: "page" }, "پیام همگانی"), h("p", { class: "sub" }, "این پیام به همه‌ی گروه‌های فعال ربات فرستاده می‌شود"),
    h("div", { class: "card" }, text, h("div", { class: "row" },
      h("button", { class: "btn", onclick: () => {
        const t = text.value.trim();
        if (t.length < 3) return toast("متن را بنویسید", true);
        if (!confirm("این پیام به همه‌ی گروه‌ها فرستاده شود؟")) return;
        run(async () => { const r = await api("/api/broadcast", { method: "POST", body: { text: t } }); toast(`ارسال شد به ${num(r.sent)} گروه (${num(r.failed)} ناموفق)`); text.value = ""; });
      } }, "ارسال به همه"))));
}

async function audit(main) {
  const rows = await api("/api/audit");
  main.append(h("h1", { class: "page" }, "گزارش مدیریت"), h("p", { class: "sub" }, "همه‌ی کارهای مدیران ثبت می‌شود"),
    rows.length ? h("div", { class: "card tablewrap" }, h("table", {},
      h("thead", {}, h("tr", {}, ["زمان", "مدیر", "کار", "جزئیات"].map((x) => h("th", {}, x)))),
      h("tbody", {}, rows.map((r) => h("tr", {}, h("td", {}, r.at), h("td", {}, r.admin), h("td", {}, r.action), h("td", {}, r.detail))))))
      : h("div", { class: "card empty" }, "هنوز چیزی ثبت نشده."));
}

let current = "dashboard";
const VIEWS = { dashboard, players, groups, orders, broadcast, audit };

async function show(name) {
  current = name;
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("on", b.dataset.page === name));
  const main = $("main");
  main.replaceChildren();
  await run(() => VIEWS[name](main));
}

async function boot() {
  const me = await api("/api/me");
  CSRF = me.csrf;
  $("me").textContent = `مدیر ${me.admin_id}`;
  $("nav").replaceChildren(...Object.entries(PAGES).map(([key, [ico, label]]) =>
    h("button", { "data-page": key, onclick: () => show(key) }, h("span", {}, ico), h("span", {}, label))));
  $("logout").addEventListener("click", () => run(async () => { await api("/api/logout", { method: "POST" }); location.reload(); }));
  $("modalBack").addEventListener("click", (e) => { if (e.target.id === "modalBack") closeModal(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
  await show("dashboard");
}

boot().catch(() => {});
