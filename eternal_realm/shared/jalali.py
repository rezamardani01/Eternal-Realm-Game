"""Solar Hijri (Persian) dates and Tehran time, without extra dependencies."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

TEHRAN = timedelta(hours=3, minutes=30)  # Iran no longer observes daylight saving time
WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]  # datetime.weekday() order


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    days_before = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + days_before[gm - 1]
    )
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def tehran_now(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp, UTC) + TEHRAN


def describe(timestamp: int) -> tuple[str, str, str]:
    """``(date, weekday, time)`` such as ``('1404/01/01', 'پنجشنبه', '18:42')`` in Tehran time."""
    moment = tehran_now(timestamp)
    jy, jm, jd = gregorian_to_jalali(moment.year, moment.month, moment.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d}", WEEKDAYS[moment.weekday()], moment.strftime("%H:%M")
