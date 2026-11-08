"use strict";
// Every piece of user-controlled text (player names, group titles...) is inserted with textContent only.

const NF = new Intl.NumberFormat("en-US");
const num = (n) => NF.format(Math.round(n || 0));
const $ = (id) => document.getElementById(id);
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
let CSRF = "";
let ME = null;
let ITEMS = [];

/* ---------------------------------------------------------------- helpers */
function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") el.className = v;
    else if (k === "style") el.style.cssText = v; // CSSOM is allowed by the CSP, the style attribute is not
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const ic = (name) => h("i", { class: `ic ic-${name}` });
const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

function countUp(el, to, dur = 1100) {
  if (reduceMotion || to < 2) { el.textContent = num(to); return; }
  const t0 = performance.now();
  const step = (t) => {
    const p = Math.min(1, (t - t0) / dur);
    el.textContent = num(to * (1 - Math.pow(1 - p, 3)));
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function toast(text, bad = false) {
  const t = h("div", { class: "toast" + (bad ? " err" : "") }, ic(bad ? "alert-triangle" : "check"), h("span", {}, text));
  $("toasts").append(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .3s"; setTimeout(() => t.remove(), 320); }, 3200);
}

function ripple(e) {
  const b = e.currentTarget, r = b.getBoundingClientRect(), d = Math.max(r.width, r.height);
  const s = h("span", { class: "rip" });
  s.style.width = s.style.height = d + "px";
  s.style.left = e.clientX - r.left - d / 2 + "px";
  s.style.top = e.clientY - r.top - d / 2 + "px";
  b.append(s);
  setTimeout(() => s.remove(), 650);
}
document.addEventListener("pointerdown", (e) => { const b = e.target.closest(".btn"); if (b && !b.disabled) ripple({ currentTarget: b, clientX: e.clientX, clientY: e.clientY }); });

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": CSRF },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    credentials: "same-origin",
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) { sessionEnded(); throw new Error("session"); }
  if (!res.ok) throw new Error(data.error || "خطای نامشخص");
  return data;
}
function sessionEnded() {
  document.body.replaceChildren(h("div", { class: "login" }, h("div", { class: "login-card" },
    h("img", { src: "/static/img/logo.svg", alt: "" }), h("h1", {}, "نشست شما تمام شد"),
    h("p", {}, "در ربات «پنل وب» را بفرستید و لینک تازه بگیرید."))));
}
const run = async (fn) => { try { return await fn(); } catch (e) { if (e.message !== "session") toast(e.message, true); } };

function confirmBox({ title, text, ok = "تأیید", danger = false, icon = "triangle" }) {
  return new Promise((resolve) => {
    const done = (v) => { box.remove(); document.removeEventListener("keydown", onKey); resolve(v); };
    const onKey = (e) => { if (e.key === "Escape") done(false); };
    const box = h("div", { class: "confirm", onclick: (e) => { if (e.target === box) done(false); } },
      h("div", { class: "box" }, ic("alert-triangle"), h("h3", {}, title), h("p", { class: "muted" }, text),
        h("div", { class: "row" },
          h("button", { class: "btn ghost", onclick: () => done(false) }, "انصراف"),
          h("button", { class: "btn " + (danger ? "bad" : ""), onclick: () => done(true) }, ok))));
    document.addEventListener("keydown", onKey);
    $("layer").append(box);
  });
}

function promptBox({ title, text, placeholder = "", ok = "ارسال", multiline = false }) {
  return new Promise((resolve) => {
    const field = multiline ? h("textarea", { rows: 5, placeholder, maxlength: 1000 }) : h("input", { placeholder });
    field.style.width = "100%";
    const done = (v) => { box.remove(); document.removeEventListener("keydown", onKey); resolve(v); };
    const onKey = (e) => { if (e.key === "Escape") done(null); };
    const box = h("div", { class: "confirm", onclick: (e) => { if (e.target === box) done(null); } },
      h("div", { class: "box" }, h("h3", {}, title), h("p", { class: "muted" }, text || ""), field,
        h("div", { class: "row" }, h("button", { class: "btn ghost", onclick: () => done(null) }, "انصراف"), h("button", { class: "btn", onclick: () => done(field.value.trim()) }, ok))));
    document.addEventListener("keydown", onKey);
    $("layer").append(box);
    field.focus();
  });
}
let PETS = [];

const empty = (text) => h("div", { class: "card empty" }, h("img", { src: "/static/img/empty.svg", alt: "" }), h("p", {}, text));
const skeleton = (n = 4) => h("div", { class: "grid kpis" }, Array.from({ length: n }, () => h("div", { class: "skel" })));
const avatar = (name, id, cls = "") => h("span", { class: `av av-${id % 6} ${cls}` }, [...(name || "?")][0]);

/* ---------------------------------------------------------------- charts */
const SVGNS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs = {}) => { const e = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
const gradients = () => {
  const d = svgEl("defs");
  d.innerHTML = '<linearGradient id="lg" x1="1" y1="0" x2="0" y2="0"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#8b6bff"/></linearGradient>' +
    '<linearGradient id="ag" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8b6bff" stop-opacity=".42"/><stop offset="1" stop-color="#22d3ee" stop-opacity="0"/></linearGradient>' +
    '<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#8b6bff"/></linearGradient>';
  return d;
};

function smooth(pts) {
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const [x0, y0] = pts[i - 1] || pts[i], [x1, y1] = pts[i], [x2, y2] = pts[i + 1], [x3, y3] = pts[i + 2] || pts[i + 1];
    d += ` C${x1 + (x2 - x0) / 6},${y1 + (y2 - y0) / 6} ${x2 - (x3 - x1) / 6},${y2 - (y3 - y1) / 6} ${x2},${y2}`;
  }
  return d;
}

function lineChart(rows, unit) {
  const W = 640, H = 240, L = 10, R = 10, T = 16, B = 28, max = Math.max(1, ...rows.map((r) => r.value)) * 1.15;
  const x = (i) => L + ((W - L - R) * i) / Math.max(1, rows.length - 1);
  const y = (v) => T + (H - T - B) * (1 - v / max);
  const pts = rows.map((r, i) => [x(i), y(r.value)]);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}` });
  svg.append(gradients());
  for (let g = 0; g <= 4; g++) {
    const gy = T + ((H - T - B) * g) / 4;
    svg.append(svgEl("line", { class: "grid-line", x1: L, x2: W - R, y1: gy, y2: gy }));
    const lbl = svgEl("text", { class: "axis", x: W - R, y: gy - 4, "text-anchor": "end" });
    lbl.textContent = num(max * (1 - g / 4));
    svg.append(lbl);
  }
  const line = svgEl("path", { class: "line", d: smooth(pts) });
  line.style.setProperty("--len", "1600");
  svg.append(svgEl("path", { class: "area", d: smooth(pts) + ` L${x(rows.length - 1)},${H - B} L${x(0)},${H - B}Z` }), line);
  rows.forEach((r, i) => { if (i % 2 === 0) { const t = svgEl("text", { class: "axis", x: x(i), y: H - 8, "text-anchor": "middle" }); t.textContent = r.day; svg.append(t); } });
  const dot = svgEl("circle", { class: "dot", r: 5, cx: -50, cy: -50 });
  svg.append(dot);
  const tip = h("div", { class: "tip" });
  const wrap = h("div", { class: "chart", style: "position:relative" }, svg, tip);
  wrap.style.position = "relative";
  svg.addEventListener("pointermove", (e) => {
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    let best = 0;
    pts.forEach((p, i) => { if (Math.abs(p[0] - px) < Math.abs(pts[best][0] - px)) best = i; });
    dot.setAttribute("cx", pts[best][0]); dot.setAttribute("cy", pts[best][1]);
    tip.textContent = `${rows[best].day} · ${num(rows[best].value)} ${unit}`;
    tip.style.left = (pts[best][0] / W) * r.width + "px"; tip.style.top = (pts[best][1] / H) * r.height - 44 + "px";
    tip.style.transform = "translateX(-50%)";
    tip.classList.add("on");
  });
  svg.addEventListener("pointerleave", () => { tip.classList.remove("on"); dot.setAttribute("cx", -50); });
  return wrap;
}

function barChart(rows, unit) {
  const W = 640, H = 240, B = 28, T = 14, max = Math.max(1, ...rows.map((r) => r.value)) * 1.1, bw = (W - 20) / rows.length;
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}` });
  svg.append(gradients());
  for (let g = 0; g <= 3; g++) { const gy = T + ((H - T - B) * g) / 3; svg.append(svgEl("line", { class: "grid-line", x1: 10, x2: W - 10, y1: gy, y2: gy })); }
  const tip = h("div", { class: "tip" });
  const wrap = h("div", { class: "chart" }, svg, tip);
  wrap.style.position = "relative";
  rows.forEach((r, i) => {
    const bh = Math.max(3, ((H - T - B) * r.value) / max), x0 = 10 + i * bw + 4;
    const rect = svgEl("rect", { class: "bar", x: x0, y: H - B - bh, width: Math.max(6, bw - 8), height: bh, rx: 6 });
    rect.style.setProperty("--i", i);
    rect.addEventListener("pointerenter", () => {
      const r2 = svg.getBoundingClientRect();
      tip.textContent = `${r.day} · ${num(r.value)} ${unit}`;
      tip.style.left = ((x0 + bw / 2) / W) * r2.width + "px"; tip.style.top = ((H - B - bh) / H) * r2.height - 42 + "px";
      tip.style.transform = "translateX(-50%)"; tip.classList.add("on");
    });
    rect.addEventListener("pointerleave", () => tip.classList.remove("on"));
    svg.append(rect);
    if (i % 2 === 0) { const t = svgEl("text", { class: "axis", x: x0 + bw / 2 - 4, y: H - 8, "text-anchor": "middle" }); t.textContent = r.day; svg.append(t); }
  });
  return wrap;
}

const PALETTE = ["#8b6bff", "#22d3ee", "#f472b6", "#fbbf24", "#34d399", "#fb923c", "#60a5fa"];
function donut(rows, total) {
  const R = 60, C = 2 * Math.PI * R;
  const svg = svgEl("svg", { class: "donut", viewBox: "0 0 160 160" });
  svg.append(svgEl("circle", { cx: 80, cy: 80, r: R, stroke: "rgba(140,150,200,.15)", "stroke-width": 20, fill: "none" }));
  let acc = 0;
  rows.forEach((r, i) => {
    const len = (r.n / Math.max(1, total)) * C;
    const c = svgEl("circle", { cx: 80, cy: 80, r: R, stroke: PALETTE[i % PALETTE.length], "stroke-dasharray": `${Math.max(0, len - 3)} ${C}`, "stroke-dashoffset": -acc, "stroke-linecap": "round" });
    c.style.animationDelay = i * 120 + "ms";
    acc += len;
    svg.append(c);
  });
  const t = svgEl("text", { x: 80, y: 78, "text-anchor": "middle", fill: "currentColor", "font-size": 24, "font-weight": 800 }); t.textContent = num(total);
  const s = svgEl("text", { x: 80, y: 98, "text-anchor": "middle", fill: "var(--muted)", "font-size": 10 }); s.textContent = "بازیکن";
  svg.append(t, s);
  const legend = h("div", { class: "legend" }, rows.map((r, i) => h("div", {}, h("i", { style: "" }), h("span", {}, r.label), h("b", {}, num(r.n)))));
  legend.querySelectorAll("i").forEach((el, i) => (el.style.background = PALETTE[i % PALETTE.length]));
  return h("div", { class: "donut-wrap" }, svg, legend);
}

/* ---------------------------------------------------------------- pages */
const PAGES = {
  dashboard: ["layout-dashboard", "داشبورد"],
  players: ["users", "بازیکنان"],
  groups: ["building-2", "گروه‌ها"],
  orders: ["banknote", "فروش"],
  broadcast: ["megaphone", "پیام همگانی"],
  audit: ["scroll-text", "گزارش مدیریت"],
  settings: ["settings", "تنظیمات"],
};
let current = "dashboard";
let refreshTimer = null;

function stagger(root) { [...root.children].forEach((c, i) => c.style.setProperty("--n", i)); return root; }

async function dashboard(main) {
  main.append(skeleton(8));
  const s = await api("/api/stats");
  main.replaceChildren();
  const kpis = [
    ["users", "کل بازیکنان", s.players, "c-violet", s.new_today ? `+${num(s.new_today)} امروز` : ""],
    ["flame", "فعال در ۲۴ ساعت", s.active_24h, "c-orange", ""],
    ["crown", "اشتراک VIP", s.vip, "c-gold", ""],
    ["building-2", "گروه‌ها", s.groups, "c-cyan", ""],
    ["castle", "خاندان‌ها", s.clans, "c-pink", ""],
    ["package", "سفارش موفق", s.orders, "c-green", ""],
    ["banknote", "فروش کل (تومان)", s.revenue_toman, "c-green", ""],
    ["coins", "سکه در گردش", s.gold, "c-gold", ""],
    ["gem", "کریستال در گردش", s.crystal, "c-cyan", ""],
    ["swords", "دوئل‌های جاری", s.duels, "c-rose", ""],
    ["trophy", "باس‌های زنده", s.bosses, "c-orange", ""],
    ["ban", "مسدودشده‌ها", s.banned, "c-rose", ""],
  ];
  const today = new Intl.DateTimeFormat("fa-IR", { dateStyle: "full" }).format(new Date());
  const hero = h("section", { class: "hero" },
    h("h2", {}, "خوش آمدید، فرمانده!"), h("p", {}, `${today} — وضعیت قلمرو جاودان در یک نگاه. ${num(s.active_24h)} بازیکن در ۲۴ ساعت گذشته فعال بوده‌اند.`),
    h("div", { class: "quick" },
      h("button", { class: "btn", onclick: () => go("players") }, ic("users"), "مدیریت بازیکنان"),
      h("button", { class: "btn ghost", onclick: () => go("broadcast") }, ic("megaphone"), "پیام همگانی"),
      h("button", { class: "btn ghost", onclick: () => (location.href = "/api/export/players.csv") }, ic("download"), "خروجی CSV")));

  const cards = h("div", { class: "grid kpis mt" }, kpis.map(([icon, label, value, color, delta]) => {
    const v = h("div", { class: "v" }, "0");
    countUp(v, value);
    return h("div", { class: `card kpi lift reveal ${color}` }, delta ? h("span", { class: "delta" }, delta) : null,
      h("div", { class: "ico" }, ic(icon)), h("div", { class: "k" }, label), v);
  }));
  stagger(cards);

  let metric = "new";
  const labels = { new: ["بازیکنان جدید", "نفر"], active: ["بازیکنان فعال", "نفر"] };
  const chartHolder = h("div");
  const drawLine = () => chartHolder.replaceChildren(lineChart(s.series[metric], labels[metric][1]));
  const seg = h("div", { class: "seg" }, Object.entries(labels).map(([k, [t]]) =>
    h("button", { class: k === metric ? "on" : "", onclick: (e) => { metric = k; seg.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b === e.currentTarget)); drawLine(); } }, t)));
  drawLine();

  const total = s.players || 1;
  const top = h("div", { class: "list" }, s.top.length ? s.top.map((p, i) =>
    h("div", { class: "item", role: "button", tabindex: 0, onclick: () => run(() => openPlayer(p.id)) },
      h("span", { class: "rank" }, i + 1), avatar(p.name, p.id), h("div", { class: "grow" }, h("b", {}, p.name), h("span", { class: "muted" }, p.class)),
      h("span", { class: "badge info" }, `سطح ${num(p.level)}`))) : [h("p", { class: "muted" }, "هنوز بازیکنی نیست.")]);
  const recent = h("div", { class: "list" }, s.recent_orders.length ? s.recent_orders.map((o) =>
    h("div", { class: "item" }, h("span", { class: "av av-4" }, ic("banknote")), h("div", { class: "grow" }, h("b", {}, o.name), h("span", { class: "muted" }, `${o.pack} · ${o.at}`)),
      h("span", { class: "badge " + (o.status === "delivered" ? "good" : "warn") }, `${num(o.toman)} ت`))) : [h("p", { class: "muted" }, "هنوز سفارشی ثبت نشده.")]);

  main.append(hero, cards,
    h("div", { class: "grid two mt" },
      h("div", { class: "card reveal" }, h("h3", {}, ic("trending-up"), "روند ۱۴ روز اخیر", h("span", { style: "flex:1" }), seg), chartHolder),
      h("div", { class: "card reveal" }, h("h3", {}, ic("banknote"), "فروش هر روز (تومان)"), barChart(s.series.revenue, "تومان"))),
    h("div", { class: "grid three mt" },
      h("div", { class: "card reveal" }, h("h3", {}, ic("shield"), "کلاس‌ها"), donut(s.classes, total)),
      h("div", { class: "card reveal" }, h("h3", {}, ic("sparkles"), "نژادها"), donut(s.races, total)),
      h("div", { class: "card reveal" }, h("h3", {}, ic("trophy"), "برترین بازیکنان"), top)),
    h("div", { class: "card reveal mt" }, h("h3", {}, ic("package"), "آخرین سفارش‌ها"), recent));
}

function pager(state, total, per, reload) {
  const pages = Math.max(1, Math.ceil(total / per));
  return h("div", { class: "pager" },
    h("button", { class: "btn ghost sm", disabled: state.page <= 0, onclick: () => { state.page--; reload(); } }, ic("chevron-right"), "قبلی"),
    h("span", {}, `صفحه ${num(state.page + 1)} از ${num(pages)} · ${num(total)} مورد`),
    h("button", { class: "btn ghost sm", disabled: state.page + 1 >= pages, onclick: () => { state.page++; reload(); } }, "بعدی", ic("chevron-left")));
}

async function players(main) {
  const state = { page: 0, q: "", sort: "level", filter: "all" };
  const holder = h("div");
  const input = h("input", { placeholder: "جستجوی نام، شناسه عددی یا یوزرنیم...", autocomplete: "off" });
  const sort = h("select", { onchange: () => { state.sort = sort.value; state.page = 0; run(load); } },
    [["level", "مرتب‌سازی: سطح"], ["gold", "بیشترین سکه"], ["crystal", "بیشترین کریستال"], ["wins", "بیشترین برد"], ["new", "جدیدترین"], ["name", "نام"]].map(([v, t]) => h("option", { value: v }, t)));
  const seg = h("div", { class: "seg" }, [["all", "همه"], ["vip", "VIP"], ["banned", "مسدود"]].map(([k, t]) =>
    h("button", { class: k === "all" ? "on" : "", onclick: (e) => { state.filter = k; seg.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b === e.currentTarget)); render(); } }, t)));
  let last = null;
  function render() {
    if (!last) return;
    const rows = last.rows.filter((p) => state.filter === "all" || (state.filter === "vip" ? p.vip : p.banned));
    const tbody = h("tbody", {}, rows.map((p, i) => {
      const tr = h("tr", { class: "click", onclick: () => run(() => openPlayer(p.id)) },
        h("td", { class: "first" }, h("div", { class: "who-cell" }, avatar(p.name, p.id), h("div", {}, h("b", {}, p.name), h("div", { class: "muted", style: "font-size:12px" }, p.username ? "@" + p.username : p.uid)))),
        h("td", { "data-l": "سطح" }, num(p.level)), h("td", { "data-l": "سکه" }, num(p.gold)), h("td", { "data-l": "کریستال" }, num(p.crystal)),
        h("td", { "data-l": "برد / باخت" }, `${num(p.wins)} / ${num(p.losses)}`),
        h("td", { "data-l": "وضعیت" }, p.banned ? h("span", { class: "badge bad" }, "مسدود") : p.vip ? h("span", { class: "badge warn" }, "VIP") : h("span", { class: "badge good" }, "فعال")),
        h("td", { "data-l": "ثبت‌نام" }, h("span", { class: "muted" }, p.created)));
      tr.style.setProperty("--n", i);
      return tr;
    }));
    holder.replaceChildren(
      rows.length ? h("div", { class: "card tablewrap reveal" }, h("div", { class: "scroll" }, h("table", { class: "stack" },
        h("thead", {}, h("tr", {}, ["بازیکن", "سطح", "سکه", "کریستال", "برد / باخت", "وضعیت", "ثبت‌نام"].map((x) => h("th", {}, x)))), tbody)))
        : empty("بازیکنی با این مشخصات پیدا نشد."),
      pager(state, last.total, last.per, () => run(load)));
  }
  async function load() { holder.replaceChildren(skeleton(3)); last = await api(`/api/players?page=${state.page}&q=${encodeURIComponent(state.q)}&sort=${state.sort}`); render(); }
  const search = () => { state.q = input.value.trim(); state.page = 0; run(load); };
  input.addEventListener("input", debounce(search, 350));
  main.append(
    h("div", { class: "toolbar" },
      h("div", { class: "searchbox" }, ic("search"), input), sort, seg,
      h("button", { class: "btn ghost", onclick: () => (location.href = "/api/export/players.csv") }, ic("download"), "خروجی CSV")),
    holder);
  await load();
}

async function openPlayer(id) {
  const p = await api(`/api/players/${id}`);
  if (!ITEMS.length) ITEMS = await api("/api/items");
  if (!PETS.length) PETS = await api("/api/pets");
  const sheet = $("sheet");
  const gold = h("input", { type: "number", placeholder: "سکه (±)" });
  const crystal = h("input", { type: "number", placeholder: "کریستال (±)" });
  const level = h("input", { type: "number", min: 1, value: p.level });
  const item = h("select", {}, ITEMS.map((i) => h("option", { value: i.id }, i.label)));
  const qty = h("input", { type: "number", min: 1, value: 1 });
  const vipDays = h("input", { type: "number", placeholder: "تعداد روز", value: 30 });
  const petSel = h("select", {}, PETS.map((x) => h("option", { value: x.id }, x.label)));
  const titleInput = h("input", { placeholder: "عنوان (خالی = حذف)", value: p.title || "" });
  const post = (path, body, msg) => run(async () => { await api(`/api/players/${id}/${path}`, { method: "POST", body }); toast(msg); await openPlayer(id); if (current === "players") show("players"); });

  const panes = {
    "نمای کلی": () => h("div", { class: "pane" },
      h("div", { class: "card kv" }, ...[["سطح", num(p.level)], ["تجربه", num(p.xp)], ["انرژی", num(p.energy)], ["سکه", num(p.gold)], ["کریستال", num(p.crystal)],
        ["برد / باخت", `${num(p.wins)} / ${num(p.losses)}`], ["امتیاز لیگ", num(p.rating)], ["کارت‌ها", num(p.cards)],
        ["خاندان", p.clan ? `${p.clan.name} (${p.clan.role})` : "—"], ["عنوان", p.title || "—"], ["بیداری", p.awakened ? "بله" : "خیر"],
        ["VIP", p.vip_until ? `تا ${p.vip_until}` : "—"], ["بلیط طلایی", p.ticket ? "دارد" : "ندارد"], ["ثبت‌نام", p.created]]
        .flatMap(([k, v]) => [h("span", {}, k), h("span", {}, v)]))),
    "کوله‌پشتی": () => h("div", { class: "pane" },
      h("div", { class: "card" }, h("h3", {}, ic("package"), "آیتم‌ها و منابع"), h("div", { class: "chips" }, p.items.length ? p.items.map((i) => h("span", { class: "badge" }, `${i.label} ×${num(i.qty)}`)) : h("span", { class: "muted" }, "خالی"))),
      h("div", { class: "card mt" }, h("h3", {}, ic("swords"), "تجهیزات"), h("div", { class: "chips" }, p.gear.length ? p.gear.map((g) => h("span", { class: "badge" }, `${g.label}${g.upgrade ? " +" + g.upgrade : ""}${g.worn ? " ✓" : ""}`)) : h("span", { class: "muted" }, "خالی"))),
      p.pets.length ? h("div", { class: "card mt" }, h("h3", {}, ic("sparkles"), "حیوانات"), h("div", { class: "chips" }, p.pets.map((x) => h("span", { class: "badge" }, `${x.id} · سطح ${x.level}${x.active ? " ✓" : ""}`)))) : null),
    "عملیات": () => h("div", { class: "pane" },
      h("div", { class: "card" }, h("h3", {}, ic("coins"), "سکه و کریستال"),
        h("div", { class: "row" }, gold, crystal, h("button", { class: "btn good", onclick: async () => {
          const g = +gold.value || 0, c = +crystal.value || 0;
          if (Math.abs(g) >= 100000 && !(await confirmBox({ title: "مقدار زیاد", text: `${num(g)} سکه ثبت شود؟`, ok: "ثبت" }))) return;
          post("give", { gold: g, crystal: c }, "ثبت شد"); } }, ic("check"), "اعمال"))),
      h("div", { class: "card mt" }, h("h3", {}, ic("star"), "سطح"), h("div", { class: "row" }, level, h("button", { class: "btn", onclick: () => post("level", { level: +level.value }, "سطح عوض شد") }, "تغییر سطح"))),
      h("div", { class: "card mt" }, h("h3", {}, ic("gift"), "دادن آیتم"), h("div", { class: "row" }, item, qty, h("button", { class: "btn", onclick: () => post("item", { item: item.value, qty: +qty.value }, "آیتم داده شد") }, "ارسال"))),
      h("div", { class: "card mt" }, h("h3", {}, ic("crown"), "اشتراک VIP"),
        h("p", { class: "muted" }, p.vip_until ? `فعال تا ${p.vip_until}` : "فعال نیست"),
        h("div", { class: "row" }, vipDays, h("button", { class: "btn good", onclick: () => post("vip", { days: +vipDays.value || 0 }, "اشتراک تغییر کرد") }, ic("plus"), "افزودن روز"),
          h("button", { class: "btn bad", disabled: !p.vip_until, onclick: () => post("vip", { clear: true }, "اشتراک حذف شد") }, ic("trash-2"), "حذف اشتراک"))),
      h("div", { class: "card mt" }, h("h3", {}, ic("sparkles"), "بلیط طلایی این فصل"),
        h("p", { class: "muted" }, p.ticket ? `دارد · ${num(p.path_points)} امتیاز مسیر` : `ندارد · ${num(p.path_points)} امتیاز مسیر`),
        h("div", { class: "row" }, h("button", { class: "btn good", disabled: p.ticket, onclick: () => post("ticket", { give: true }, "بلیط اهدا شد") }, ic("gift"), "اهدای بلیط"),
          h("button", { class: "btn bad", disabled: !p.ticket, onclick: () => post("ticket", { give: false }, "بلیط حذف شد") }, ic("trash-2"), "حذف بلیط"))),
      h("div", { class: "card mt" }, h("h3", {}, ic("sparkles"), "حیوان خانگی"),
        h("p", { class: "muted" }, p.pets.length ? p.pets.map((x) => `${x.id} (سطح ${x.level})`).join("، ") : "حیوانی ندارد"),
        h("div", { class: "row" }, petSel, h("button", { class: "btn good", onclick: () => post("pet", { pet: petSel.value, give: true }, "حیوان اهدا شد") }, ic("gift"), "اهدا"),
          h("button", { class: "btn bad", onclick: () => post("pet", { pet: petSel.value, give: false }, "حیوان حذف شد") }, ic("trash-2"), "حذف"))),
      h("div", { class: "card mt" }, h("h3", {}, ic("crown"), "عنوان"), h("div", { class: "row" }, titleInput, h("button", { class: "btn", onclick: () => post("title", { title: titleInput.value }, "عنوان ذخیره شد") }, "ذخیره"))),
      h("div", { class: "card mt" }, h("h3", {}, ic("zap"), "میانبرها"), h("div", { class: "row" },
        h("button", { class: "btn ghost", onclick: () => post("energy", {}, "انرژی پر شد") }, ic("zap"), "پر کردن انرژی"),
        h("button", { class: "btn ghost", onclick: () => post("cooldowns", {}, "زمان‌های انتظار پاک شد") }, ic("clock"), "پاک کردن زمان انتظار"))),
      h("div", { class: "card mt" }, h("h3", {}, ic("ban"), "دسترسی"), h("div", { class: "row" }, h("button", { class: p.banned ? "btn good" : "btn bad", onclick: async () => {
        if (await confirmBox({ title: p.banned ? "آزاد کردن بازیکن" : "مسدود کردن بازیکن", text: `${p.name} ${p.banned ? "آزاد شود؟" : "از بازی مسدود شود؟"}`, ok: p.banned ? "آزاد کن" : "مسدود کن", danger: !p.banned }))
          post("ban", { banned: !p.banned }, p.banned ? "آزاد شد" : "مسدود شد"); } }, ic("ban"), p.banned ? "آزاد کردن بازیکن" : "مسدود کردن بازیکن")))),
    "تراکنش‌ها": () => h("div", { class: "pane card tablewrap" }, h("div", { class: "scroll" }, h("table", {},
      h("thead", {}, h("tr", {}, ["زمان", "سکه", "کریستال", "دلیل"].map((x) => h("th", {}, x)))),
      h("tbody", {}, p.history.map((x) => h("tr", {}, h("td", {}, x.at), h("td", {}, num(x.gold)), h("td", {}, num(x.crystal)), h("td", {}, x.reason)))))))
  };
  const body = h("div");
  const tabs = h("div", { class: "tabs" }, Object.keys(panes).map((t, i) => h("button", { class: i ? "" : "on", onclick: (e) => {
    tabs.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b === e.currentTarget)); body.replaceChildren(panes[t]()); } }, t)));
  body.append(panes["نمای کلی"]());
  sheet.replaceChildren(
    h("div", { class: "sheet-head" }, avatar(p.name, p.id, "lg"), h("div", { class: "grow" }, h("h2", {}, p.name),
      h("div", { class: "row", style: "margin:4px 0 0" }, p.banned ? h("span", { class: "badge bad" }, "مسدود") : h("span", { class: "badge good" }, "فعال"), p.vip ? h("span", { class: "badge warn" }, "VIP") : null,
        h("span", { class: "muted", style: "font-size:12px" }, `شناسه بله ${p.uid}${p.username ? " · @" + p.username : ""}`))),
      h("button", { class: "icon-btn", onclick: closeSheet, "aria-label": "بستن" }, ic("x"))),
    tabs, body);
  $("overlay").classList.add("on"); sheet.classList.add("on");
}
function closeSheet() { $("sheet").classList.remove("on"); $("overlay").classList.remove("on"); }

async function groups(main) {
  main.append(skeleton(3));
  const rows = await api("/api/groups");
  const kinds = [["", "رویداد تصادفی"], ["mystery_chest", "صندوقچه‌ی اسرارآمیز"], ["merchant", "تاجر دوره‌گرد"], ["double_xp", "تجربه‌ی دوبرابر"], ["hidden_boss", "باس مخفی"]];
  const card = (g, i) => {
    const kind = h("select", {}, kinds.map(([v, t]) => h("option", { value: v }, t)));
    const reload = () => show("groups");
    return h("div", { class: "card lift reveal" },
      h("div", { class: "who-cell" }, h("span", { class: `av av-${i % 6}` }, ic("building-2")),
        h("div", {}, h("b", {}, g.title), h("div", { class: "muted", style: "font-size:12px" }, `آخرین فعالیت ${g.seen}`))),
      h("div", { class: "row" }, h("span", { class: "badge " + (g.enabled ? "good" : "bad") }, g.enabled ? "فعال" : "غیرفعال"), h("span", { class: "badge info" }, `${num(g.members)} بازیکن`),
        h("span", { class: "muted", style: "font-size:12px" }, `ثبت ${g.created}`)),
      h("div", { class: "row" },
        h("button", { class: "btn sm " + (g.enabled ? "bad" : "good"), onclick: () => run(async () => { await api(`/api/groups/${g.id}/toggle`, { method: "POST", body: { enabled: !g.enabled } }); toast(g.enabled ? "گروه غیرفعال شد" : "گروه فعال شد"); reload(); }) }, g.enabled ? "غیرفعال کردن" : "فعال کردن"),
        h("button", { class: "btn sm ghost", onclick: () => run(async () => {
          const t = await promptBox({ title: `پیام به «${g.title}»`, placeholder: "متن پیام...", multiline: true });
          if (t) { await api(`/api/groups/${g.id}/message`, { method: "POST", body: { text: t } }); toast("پیام ارسال شد"); } }) }, ic("send"), "پیام")),
      h("div", { class: "row" }, kind,
        h("button", { class: "btn sm", onclick: () => run(async () => { const r = await api(`/api/groups/${g.id}/event`, { method: "POST", body: { kind: kind.value } }); toast(`رویداد «${r.kind}» ساخته شد`); }) }, ic("sparkles"), "ساخت رویداد")));
  };
  main.replaceChildren(
    h("p", { class: "sub" }, `${num(rows.length)} گروه در قلمرو ثبت شده است`),
    rows.length ? stagger(h("div", { class: "grid three" }, rows.map(card))) : empty("هنوز گروهی ثبت نشده است."));
}

async function orders(main) {
  const state = { page: 0 };
  const holder = h("div");
  const cls = { delivered: "good", paid: "warn", pending: "info", failed: "bad", refunded: "bad" };
  const txt = { delivered: "تحویل شد", paid: "پرداخت شد", pending: "در انتظار", failed: "ناموفق", refunded: "بازگشت" };
  async function load() {
    holder.replaceChildren(skeleton(2));
    const d = await api(`/api/orders?page=${state.page}`);
    holder.replaceChildren(
      d.rows.length ? h("div", { class: "card tablewrap reveal" }, h("div", { class: "scroll" }, h("table", { class: "stack" },
        h("thead", {}, h("tr", {}, ["شماره", "بازیکن", "محصول", "مبلغ (تومان)", "وضعیت", "زمان"].map((x) => h("th", {}, x)))),
        h("tbody", {}, d.rows.map((o, i) => { const tr = h("tr", {}, h("td", { class: "first" }, `#${num(o.id)} · ${o.name}`), h("td", { "data-l": "محصول" }, o.pack), h("td", { "data-l": "مبلغ" }, num(o.toman)),
          h("td", { "data-l": "وضعیت" }, h("span", { class: "badge " + (cls[o.status] || "") }, txt[o.status] || o.status)), h("td", { "data-l": "زمان" }, h("span", { class: "muted" }, o.at))); tr.style.setProperty("--n", i); return tr; })))))
        : empty("هنوز سفارشی ثبت نشده است."),
      pager(state, d.total, d.per, () => run(load)));
  }
  main.append(h("p", { class: "sub" }, "سفارش‌های خزانه، جدیدترین اول"), holder);
  await load();
}

async function broadcast(main) {
  const text = h("textarea", { maxlength: 1000, placeholder: "متن پیام برای همه‌ی گروه‌های فعال..." });
  const counter = h("span", { class: "muted" }, "۰ / ۱۰۰۰");
  const meter = h("i");
  const bubble = h("div", { class: "bubble" }, h("div", { class: "by" }, "قلمرو جاودان"), h("span", { class: "muted" }, "پیش‌نمایش پیام شما اینجا دیده می‌شود"));
  const body = bubble.lastChild;
  text.addEventListener("input", () => {
    const t = text.value; body.textContent = t.trim() || "پیش‌نمایش پیام شما اینجا دیده می‌شود";
    counter.textContent = `${num(t.length)} / ۱,۰۰۰`; meter.style.width = (t.length / 10) + "%";
  });
  const send = h("button", { class: "btn", onclick: async () => {
    const t = text.value.trim();
    if (t.length < 3) return toast("متن را بنویسید", true);
    if (!(await confirmBox({ title: "ارسال همگانی", text: "این پیام به همه‌ی گروه‌های فعال فرستاده می‌شود. ادامه می‌دهید؟", ok: "ارسال کن" }))) return;
    send.disabled = true;
    await run(async () => { const r = await api("/api/broadcast", { method: "POST", body: { text: t } }); toast(`به ${num(r.sent)} گروه ارسال شد (${num(r.failed)} ناموفق)`); text.value = ""; text.dispatchEvent(new Event("input")); });
    send.disabled = false;
  } }, ic("send"), "ارسال به همه");
  main.append(h("p", { class: "sub" }, "پیام شما در همه‌ی گروه‌های فعال ربات منتشر می‌شود"),
    h("div", { class: "composer" },
      h("div", { class: "card reveal" }, h("h3", {}, ic("megaphone"), "نوشتن پیام"), text, h("div", { class: "meter" }, meter), h("div", { class: "row" }, counter, h("span", { style: "flex:1" }), send)),
      h("div", { class: "phone reveal" }, h("div", { class: "muted", style: "font-size:12px;margin-bottom:10px" }, "پیش‌نمایش"), bubble)));
}

async function audit(main) {
  main.append(skeleton(2));
  const rows = await api("/api/audit");
  const icons = { give_currency: "coins", give_item: "gift", ban: "ban", unban: "check", set_level: "star", broadcast: "megaphone", export_players: "download" };
  main.replaceChildren(h("p", { class: "sub" }, "همه‌ی کارهای مدیران اینجا ثبت می‌شود"),
    rows.length ? stagger(h("div", { class: "timeline" }, rows.map((r) =>
      h("div", { class: "tl reveal" }, h("div", { class: "row", style: "margin:0" }, ic(icons[r.action] || "activity"), h("b", {}, r.action), h("span", { style: "flex:1" }), h("span", { class: "muted", style: "font-size:12px" }, r.at)),
        h("div", { class: "muted", style: "margin-top:4px" }, r.detail || "—"), h("div", { class: "muted", style: "font-size:12px" }, `مدیر ${r.admin}`))))) : empty("هنوز چیزی ثبت نشده است."));
}

async function settings(main) {
  main.append(skeleton(2));
  const cfg = await api("/api/membership");
  const state = { enabled: cfg.enabled, channels: cfg.channels.map((c) => ({ ...c })) };
  const list = h("div", { class: "grid" });
  const sw = h("button", { class: "btn " + (state.enabled ? "good" : "ghost"), onclick: () => { state.enabled = !state.enabled; paint(); } });
  function paint() {
    sw.className = "btn " + (state.enabled ? "good" : "ghost");
    sw.replaceChildren(ic(state.enabled ? "check" : "lock"), state.enabled ? "عضویت اجباری فعال است" : "عضویت اجباری خاموش است");
    list.replaceChildren(...state.channels.map((c, i) => {
      const chat = h("input", { placeholder: "@mychannel یا شناسه عددی", value: c.chat, oninput: () => (c.chat = chat.value.trim()) });
      const title = h("input", { placeholder: "نام نمایشی (مثلاً کانال ما)", value: c.title, oninput: () => (c.title = title.value) });
      const link = h("input", { placeholder: "لینک دعوت https://ble.ir/...", value: c.link, oninput: () => (c.link = link.value.trim()) });
      const probe = h("button", { class: "btn ghost sm", onclick: () => run(async () => {
        const r = await api("/api/membership/probe", { method: "POST", body: { chat: c.chat } });
        if (r.title && !c.title) { c.title = r.title; title.value = r.title; }
        toast(`کانال «${r.title || c.chat}» پیدا شد · وضعیت ربات: ${r.bot_status}`); }) }, ic("search"), "بررسی");
      return h("div", { class: "card reveal" }, h("h3", {}, ic("link"), `کانال ${num(i + 1)}`),
        h("div", { class: "grid two" }, chat, title), h("div", { class: "row" }, link, probe,
          h("button", { class: "btn bad sm", onclick: () => { state.channels.splice(i, 1); paint(); } }, ic("trash-2"), "حذف")));
    }));
    if (!state.channels.length) list.append(empty("هنوز کانالی تنظیم نشده است."));
  }
  paint();
  main.replaceChildren(
    h("p", { class: "sub" }, "بازیکنان باید قبل از بازی در این کانال‌ها عضو شوند. ربات باید در هر کانال ادمین باشد تا عضویت را ببیند."),
    h("div", { class: "card reveal" }, h("h3", {}, ic("lock"), "عضویت اجباری"), h("div", { class: "row" }, sw,
      h("button", { class: "btn ghost", onclick: () => { if (state.channels.length >= 5) return toast("حداکثر ۵ کانال", true); state.channels.push({ chat: "", title: "", link: "" }); paint(); } }, ic("plus"), "افزودن کانال"),
      h("button", { class: "btn", onclick: () => run(async () => { await api("/api/membership", { method: "POST", body: { enabled: state.enabled, channels: state.channels } }); toast("تنظیمات ذخیره شد"); }) }, ic("check"), "ذخیره‌ی تنظیمات"))),
    h("div", { class: "mt" }, list));
}

/* ---------------------------------------------------------------- shell */
const VIEWS = { dashboard, players, groups, orders, broadcast, audit, settings };
function go(name) { location.hash = "#/" + name; }

async function show(name) {
  if (!VIEWS[name]) name = "dashboard";
  current = name;
  clearInterval(refreshTimer);
  document.querySelectorAll("#nav button, #bottom button").forEach((b) => b.classList.toggle("on", b.dataset.page === name));
  $("pageTitle").textContent = PAGES[name][1];
  document.title = `${PAGES[name][1]} · پنل قلمرو جاودان`;
  $("side").classList.remove("on"); $("overlay").classList.remove("on"); $("sheet").classList.remove("on");
  const main = $("main");
  main.replaceChildren();
  window.scrollTo({ top: 0 });
  await run(() => VIEWS[name](main));
  if (name === "dashboard") refreshTimer = setInterval(() => { if (!document.hidden && current === "dashboard") show("dashboard"); }, 60000);
}

/* command palette */
function openPalette() {
  const input = h("input", { placeholder: "برو به صفحه، بازیکن را پیدا کن، یا دستور بده...", autocomplete: "off" });
  const res = h("div", { class: "res" });
  const layer = h("div", { class: "palette", onclick: (e) => { if (e.target === layer) close(); } }, h("div", { class: "box" }, input, res,
    h("div", { class: "hint" }, "↑ ↓ برای حرکت · Enter برای انتخاب · Esc برای بستن")));
  let opts = [], idx = 0;
  const close = () => { layer.remove(); document.removeEventListener("keydown", key, true); };
  const commands = [
    ...Object.entries(PAGES).map(([k, [icon, label]]) => ({ icon, label: `رفتن به ${label}`, run: () => go(k) })),
    { icon: "download", label: "دانلود خروجی بازیکنان (CSV)", run: () => (location.href = "/api/export/players.csv") },
    { icon: "moon", label: "تغییر تم تیره / روشن", run: toggleTheme },
    { icon: "refresh-cw", label: "تازه‌سازی صفحه", run: () => show(current) },
    { icon: "log-out", label: "خروج از پنل", run: logout },
  ];
  function paint() {
    res.replaceChildren(...opts.map((o, i) => h("div", { class: "opt" + (i === idx ? " on" : ""), onclick: () => { close(); o.run(); } },
      o.av ? avatar(o.label, o.id) : ic(o.icon), h("span", {}, o.label), o.hint ? h("span", { class: "muted", style: "margin-inline-start:auto;font-size:12px" }, o.hint) : null)));
    if (!opts.length) res.append(h("div", { class: "empty" }, "چیزی پیدا نشد"));
  }
  const refresh = debounce(async (q) => {
    let found = [];
    if (q.length >= 2) { try { found = (await api(`/api/players?q=${encodeURIComponent(q)}`)).rows.slice(0, 6).map((p) => ({ av: true, id: p.id, label: p.name, hint: `سطح ${num(p.level)}`, run: () => run(() => openPlayer(p.id)) })); } catch { /* ignore */ } }
    opts = [...commands.filter((c) => !q || c.label.includes(q)), ...found]; idx = 0; paint();
  }, 180);
  input.addEventListener("input", () => refresh(input.value.trim()));
  function key(e) {
    if (e.key === "Escape") { e.stopPropagation(); close(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); idx = Math.min(opts.length - 1, idx + 1); paint(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); idx = Math.max(0, idx - 1); paint(); }
    else if (e.key === "Enter" && opts[idx]) { e.preventDefault(); const o = opts[idx]; close(); o.run(); }
  }
  document.addEventListener("keydown", key, true);
  $("layer").append(layer); opts = commands; paint(); input.focus();
}

function applyTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  const b = $("themeBtn"); if (b) b.replaceChildren(ic(t === "light" ? "sun" : "moon"));
  store.set("er-theme", t);
}
function toggleTheme() { applyTheme(document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light"); }
async function logout() { await run(async () => { await api("/api/logout", { method: "POST" }); location.reload(); }); }

async function boot() {
  applyTheme(store.get("er-theme") || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));
  ME = await api("/api/me");
  CSRF = ME.csrf;
  $("me").textContent = `مدیر ${ME.admin_id}`;
  const navBtn = (key, [icon, label]) => h("button", { "data-page": key, onclick: () => go(key) }, ic(icon), h("span", {}, label));
  $("nav").replaceChildren(...Object.entries(PAGES).map(([k, v]) => navBtn(k, v)));
  $("bottom").replaceChildren(...["dashboard", "players", "orders", "broadcast", "audit"].map((k) => navBtn(k, PAGES[k])));
  $("logout").addEventListener("click", logout);
  $("themeBtn").addEventListener("click", toggleTheme);
  $("searchBtn").addEventListener("click", openPalette);
  $("refreshBtn").addEventListener("click", async () => { const b = $("refreshBtn"); b.classList.add("spin"); await show(current); b.classList.remove("spin"); });
  $("menuBtn").addEventListener("click", () => { $("side").classList.add("on"); $("overlay").classList.add("on"); });
  $("overlay").addEventListener("click", () => { $("side").classList.remove("on"); closeSheet(); });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); }
    else if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); openPalette(); }
    else if (e.key === "Escape") closeSheet();
  });
  window.addEventListener("hashchange", () => show(location.hash.replace("#/", "")));
  await show(location.hash.replace("#/", "") || "dashboard");
}

boot().catch(() => {});
