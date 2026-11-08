"""Loading and validation of ``config.toml``."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any


class ConfigError(RuntimeError):
    """The configuration file is missing or invalid."""


@dataclass(frozen=True)
class Balance:
    """Every tunable number of the game. Override any of them under ``[balance]``."""

    max_level: int = 100
    base_energy: int = 100
    energy_per_level: int = 2
    energy_regen_seconds: int = 90
    xp_base: int = 100
    xp_exponent: float = 1.4
    start_gold: int = 500
    start_energy_potions: int = 2
    rest_energy: int = 25
    rest_cooldown_seconds: int = 1800
    daily_gold: int = 300
    daily_gold_per_level: int = 20
    daily_streak_cap: int = 7
    duel_turn_seconds: int = 90
    duel_invite_seconds: int = 180
    duel_max_rounds: int = 15
    duel_pair_daily_limit: int = 5
    duel_win_xp: int = 40
    duel_lose_xp: int = 12
    duel_win_gold: int = 60
    duel_daily_reward_cap: int = 10
    transfer_daily_limit: int = 50_000
    transfer_min: int = 10
    market_fee_percent: int = 5
    market_max_listings: int = 10
    market_max_price: int = 10_000_000
    command_gap_seconds: float = 1.0
    #: pause between the steps of «در حال شکار...»-style animations (0 turns them off)
    animation_seconds: float = 1.0
    event_interval_seconds: int = 7200
    event_min_active: int = 2
    clan_create_gold: int = 1000
    second_class_level: int = 15
    second_class_gold: int = 3000
    awaken_level: int = 20
    awaken_gold: int = 5000
    awaken_crystal: int = 20
    #: waiting time after the 1st, 2nd, 3rd ... use of the same activity in one day (seconds; the last repeats)
    cooldown_ladder: str = "300,900,1800,3600,7200"
    boss_summon_gold: int = 200
    boss_min_level: int = 3
    boss_cooldown_seconds: int = 7200
    boss_min_players: int = 3
    boss_max_players: int = 10
    boss_recruit_seconds: int = 120
    boss_round_seconds: int = 5
    boss_report_seconds: int = 15
    boss_fight_seconds: int = 600
    group_flood_window: int = 10
    group_flood_max: int = 25


def cooldown_ladder(balance: Balance) -> tuple[int, ...]:
    steps = tuple(int(x) for x in balance.cooldown_ladder.replace(" ", "").split(",") if x)
    return steps or (300,)


@dataclass(frozen=True)
class Settings:
    token: str
    owner_id: int
    admin_ids: frozenset[int] = frozenset()
    db_path: Path = Path("data/game.db")
    payments_enabled: bool = True
    provider_token: str = "WALLET-TEST-1111111111111111"
    balance: Balance = field(default_factory=Balance)
    command_overrides: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def is_admin(self, user_id: int) -> bool:
        return user_id == self.owner_id or user_id in self.admin_ids


def _build_balance(raw: dict[str, Any]) -> Balance:
    known = {f.name: f for f in fields(Balance)}
    kwargs: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in known:
            raise ConfigError(f"[balance] کلید ناشناخته: {key}")
        default = getattr(Balance, key)
        if isinstance(default, str):
            kwargs[key] = str(value)
            continue
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ConfigError(f"[balance] مقدار {key} نامعتبر است")
        kwargs[key] = type(default)(value)
    return Balance(**kwargs)


def parse_settings(data: dict[str, Any]) -> Settings:
    bot = data.get("bot", {})
    token = str(bot.get("token", "")).strip()
    if not token:
        raise ConfigError("توکن ربات در config.toml بخش [bot] خالی است.")
    owner_id = int(bot.get("owner_id", 0) or 0)
    if owner_id <= 0:
        raise ConfigError("owner_id در config.toml بخش [bot] باید شناسه عددی مالک باشد.")
    payments = data.get("payments", {})
    overrides = {
        name: tuple(str(a) for a in aliases)
        for name, aliases in data.get("commands", {}).items()
        if isinstance(aliases, list)
    }
    return Settings(
        token=token,
        owner_id=owner_id,
        admin_ids=frozenset(int(i) for i in bot.get("admin_ids", [])),
        db_path=Path(data.get("database", {}).get("path", "data/game.db")),
        payments_enabled=bool(payments.get("enabled", True)),
        provider_token=str(payments.get("provider_token", "WALLET-TEST-1111111111111111")),
        balance=_build_balance(data.get("balance", {})),
        command_overrides=overrides,
    )


def load_settings(path: str | Path = "config.toml") -> Settings:
    file = Path(path)
    if not file.exists():
        raise ConfigError(
            f"فایل {file} پیدا نشد. فایل config.example.toml را با نام config.toml کپی و پر کنید."
        )
    try:
        data = tomllib.loads(file.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"فایل تنظیمات خراب است: {exc}") from exc
    return parse_settings(data)
