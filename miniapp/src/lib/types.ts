export interface Named { id: string; name: string; emoji: string }
export interface ItemInfo extends Named { kind: string; rarity: number; rarity_name: string }

export interface PlayerInfo {
  id: number; name: string; level: number; xp: number; xp_needed: number; energy: number; max_energy: number;
  gold: number; crystal: number; race: Named; class: Named; class2: Named | null; awakened: boolean; honor: string;
  vip: boolean; boost_left: number; wins: number; losses: number; streak: number; khan_points: number; daily_in: number;
}

export interface Mission { slot: number; emoji: string; title: string; progress: number; target: number; gold: number; claimed: boolean; done: boolean }

export interface Me {
  player: PlayerInfo;
  stats: { hp: number; atk: number; defense: number; magic: number; speed: number; luck: number };
  power: number;
  badges: string[];
  missions: Mission[];
  week: { days: number; claimed: boolean; ready: boolean };
  ready: { daily: boolean; fight: string; maze_floor: number; gifts: number; popup: { id: number; title: string; emoji: string } | null; rescue: number };
  is_admin: boolean;
  payments: boolean;
}

export interface Piece { id: number; item: ItemInfo; upgrade: number; slot: string | null; stats: string[] }
export interface HeroPage { slots: { id: string; label: string; piece: Piece | null }[]; bag: Piece[]; stacks: { item: ItemInfo; qty: number }[] }

export interface ActivityCard { id: string; title: string; emoji: string; energy: number; wait: number; danger?: boolean }
export interface ActResult {
  kind: string; title: string; emoji: string; won: boolean; text: string; gold: number; xp: number; crystal: number;
  items: { item: ItemInfo; qty: number }[]; energy: number; next_in: number; level_up: number; hp?: [number, number];
  rounds?: number; card?: { name: string; emoji: string } | null; log?: string[];
}

export interface ClanPage {
  clan: null | {
    id: number; name: string; leader: string; level: number; size: number; capacity: number; power: number; treasury: number;
    open: boolean; role: string; min_level: number; exit_fine: number;
  };
  members?: { id: number; name: string; level: number; role: string; donated: number }[];
  khan_points?: number;
  create_gold?: number;
}

export interface Listing { id: number; item: ItemInfo; qty: number; price: number; upgrade: number; seller: string; mine: boolean }

export interface PanelButton {
  text: string; style?: string; s?: string; a?: string; b?: string; url?: string; copy?: string;
  buy?: { kind: string; id: string }; bot_only?: boolean;
}
export interface Shown {
  screen: string; a: string; b: string; text: string | null; rows: PanelButton[][]; toast: string | null; alert: boolean;
  prompt?: { form: string; [key: string]: string };
}
