// Which downloaded picture stands for what. The game's data names everything with an emoji; here each emoji (and
// each item, race, class and activity by id) is tied to a vector icon, so the page never draws an emoji as text.
import emojiMap from "../icons/emoji-map.json";
import uiMap from "../icons/ui.json";

const EMOJI = emojiMap as Record<string, string>;
const UI = uiMap as Record<string, string>;

export const EMOJI_SOURCE = "(\\p{Extended_Pictographic}\\uFE0F?(?:\\u200D\\p{Extended_Pictographic}\\uFE0F?)*|[\\u2606\\u25AB\\u25AA])";

export type Tone = "gold" | "magic" | "emerald" | "blood" | "sky" | "silver" | "muted" | "ink";

const TONES: Record<string, Tone> = {
  "cut-diamond": "sky", "crystal-shine": "sky", "crystal-growth": "sky", "hearts": "blood", "broken-heart": "blood", "check-mark": "emerald",
  "cancel": "blood", "herbs-bundle": "emerald", "clover": "emerald", "sprout": "emerald", "padlock": "muted", "death-skull": "silver",
  "sparkles": "magic", "crystal-ball": "magic", "wizard-staff": "magic", "magic-potion": "magic", "round-potion": "emerald",
  "shield": "silver", "crossed-swords": "silver", "plain-dagger": "silver", "ore": "silver", "stone-pile": "silver", "wind-slap": "sky",
  "water-drop": "sky", "snowflake-1": "sky", "ice-cube": "sky", "flame": "blood", "hazard-sign": "blood", "drop": "blood", "volcano": "blood",
  "moon": "magic", "ghost": "silver", "pine-tree": "emerald", "oak": "emerald",
};

/** The icon for one emoji ("" = drop it silently, undefined = unknown). */
export function iconOfEmoji(emoji: string): string | undefined {
  const bare = emoji.replace(/️/g, "");
  if (bare in EMOJI) return EMOJI[bare];
  const first = Array.from(bare)[0];
  return first in EMOJI ? EMOJI[first] : undefined;
}

export const ui = (key: string): string => UI[key] ?? UI["ui.fallback"];
export const toneOf = (icon: string): Tone => TONES[icon] ?? "gold";

/** The best picture for a game thing: by its id when one was chosen for it, else by its emoji. */
export function iconFor(kind: "item" | "race" | "class" | "act" | "slot", id: string, emoji = ""): string {
  return UI[`${kind}.${id}`] || (emoji && iconOfEmoji(emoji)) || UI["ui.fallback"];
}

/** Split a label like "⚔️ حمله" into its leading picture and the words. */
export function leading(text: string): { icon: string | null; rest: string } {
  const match = text.match(new RegExp("^\\s*" + EMOJI_SOURCE, "u"));
  if (!match) return { icon: null, rest: text };
  const icon = iconOfEmoji(match[1]);
  return { icon: icon || null, rest: text.slice(match[0].length).trimStart() };
}
