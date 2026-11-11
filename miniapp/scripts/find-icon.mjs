// Usage: node scripts/find-icon.mjs dragon shield ...  -> names of game-icons that contain each word
import { createRequire } from "node:module";
const icons = createRequire(import.meta.url)("@iconify-json/game-icons/icons.json");
const names = Object.keys(icons.icons);
for (const word of process.argv.slice(2)) console.log(word + ": " + names.filter((n) => n.includes(word)).slice(0, 60).join(" "));
