// What every page needs to know and do: who the player is, opening a panel, paying, and saying something briefly.
import { createContext, useContext } from "react";
import type { Me, PanelButton } from "./lib/types";

export type TabId = "realm" | "hero" | "adventure" | "clan" | "market";

export interface AppState {
  me: Me;
  /** Fetch the player's numbers again (after anything that may have changed them). */
  refresh: () => Promise<void>;
  tab: TabId;
  setTab: (tab: TabId) => void;
  /** Open any screen of the bot as a drawn panel. */
  open: (screen: string, a?: string, b?: string) => void;
  toast: (message: string, error?: boolean) => void;
  /** Start a real-money purchase through Bale's payment sheet. */
  pay: (buy: NonNullable<PanelButton["buy"]>) => Promise<void>;
}

export const AppContext = createContext<AppState | null>(null);

export function useApp(): AppState {
  const state = useContext(AppContext);
  if (!state) throw new Error("AppContext is missing");
  return state;
}
