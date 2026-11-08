"""Ranked duel leagues, from bronze up to legend, driven by an Elo-style rating."""

from __future__ import annotations

from dataclasses import dataclass

START_RATING = 1000
K_FACTOR = 28


@dataclass(frozen=True)
class League:
    id: str
    emoji: str
    name: str
    min_rating: int


LEAGUES: tuple[League, ...] = (
    League("bronze", "🥉", "برنز", 0),
    League("silver", "🥈", "نقره", 1100),
    League("gold", "🥇", "طلا", 1250),
    League("diamond", "💎", "الماس", 1450),
    League("legend", "👑", "اسطوره‌ای", 1700),
)


def league_of(rating: int) -> League:
    found = LEAGUES[0]
    for league in LEAGUES:
        if rating >= league.min_rating:
            found = league
    return found


def next_league(rating: int) -> League | None:
    for league in LEAGUES:
        if league.min_rating > rating:
            return league
    return None


def new_ratings(winner: int, loser: int) -> tuple[int, int]:
    """Standard Elo: beating a stronger opponent is worth more. Ratings never drop below zero."""
    expected = 1 / (1 + 10 ** ((loser - winner) / 400))
    delta = max(1, round(K_FACTOR * (1 - expected)))
    return winner + delta, max(0, loser - delta)
