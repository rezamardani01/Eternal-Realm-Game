// Every request of the page: the signed initData goes along, and answers come back as { ok, ... }.
import { initData, insideBale } from "./bale";
import type { PlayerInfo, Shown } from "./types";

export class ApiError extends Error {
  constructor(message: string, public needsHero = false, public away = false) {
    super(message);
  }
}

/** In the local preview (vite dev, outside Bale) the preview API accepts a plain demo user id. */
const DEV_USER = import.meta.env.DEV && !insideBale ? "1001" : "";

export async function call<T = Record<string, unknown>>(path: string, payload?: unknown): Promise<T> {
  const headers: Record<string, string> = { "X-Init-Data": initData };
  if (DEV_USER) headers["X-Dev-User"] = DEV_USER;
  if (payload !== undefined) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(`/api/${path}`, {
      method: payload === undefined ? "GET" : "POST", headers, body: payload === undefined ? undefined : JSON.stringify(payload),
    });
  } catch {
    throw new ApiError("اتصال به قلمرو برقرار نشد؛ اینترنت را بررسی کنید و دوباره تلاش کنید.");
  }
  let data: { ok?: boolean; error?: string; needs_hero?: boolean; away?: boolean } & Record<string, unknown>;
  try {
    data = await response.json();
  } catch {
    throw new ApiError("پاسخ قلمرو خوانده نشد؛ دوباره تلاش کنید.");
  }
  if (!data.ok) throw new ApiError(data.error || "خطایی پیش آمد.", Boolean(data.needs_hero), Boolean(data.away));
  return data as T;
}

export const openScreen = (s: string, a = "", b = "") => call<{ shown: Shown; player: PlayerInfo | null }>("screen", { s, a, b });
