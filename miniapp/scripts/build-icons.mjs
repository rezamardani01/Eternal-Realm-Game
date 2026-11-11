// Copies every game-icons SVG the app uses (src/icons/*.json) out of the downloaded icon set into public/icons/.
// Icons: https://game-icons.net (CC BY 3.0), taken from the @iconify-json/game-icons package.
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, writeFileSync, readdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const set = createRequire(import.meta.url)("@iconify-json/game-icons/icons.json");
const names = new Set();
for (const file of readdirSync(join(root, "src/icons")).filter((f) => f.endsWith(".json"))) {
  const data = JSON.parse(readFileSync(join(root, "src/icons", file), "utf8"));
  for (const value of Object.values(data)) if (value) names.add(value);
}
const out = join(root, "public/icons");
rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
const missing = [];
for (const name of names) {
  const icon = set.icons[name];
  if (!icon) { missing.push(name); continue; }
  const size = icon.width || set.width || 512;
  writeFileSync(join(out, name + ".svg"), `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}">${icon.body.replaceAll("currentColor", "#000")}</svg>`);
}
console.log(`icons: ${names.size - missing.length} written`);
if (missing.length) {
  const all = Object.keys(set.icons);
  for (const name of missing) {
    const words = name.split("-").filter((w) => w.length > 2);
    console.log(`MISSING ${name} -> ${all.filter((n) => words.some((w) => n.includes(w))).slice(0, 14).join(" ")}`);
  }
  if (process.argv.includes("--strict")) process.exit(1);
}
