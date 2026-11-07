from datetime import UTC, datetime

from eternal_realm.shared.jalali import describe, gregorian_to_jalali


def test_known_conversions():
    assert gregorian_to_jalali(2025, 3, 21) == (1404, 1, 1)
    assert gregorian_to_jalali(2024, 3, 20) == (1403, 1, 1)
    assert gregorian_to_jalali(2024, 12, 31) == (1403, 10, 11)
    assert gregorian_to_jalali(2000, 1, 1) == (1378, 10, 11)


def test_describe_uses_tehran_time():
    ts = int(datetime(2025, 3, 21, 20, 45, tzinfo=UTC).timestamp())  # 00:15 next day in Tehran
    date, weekday, clock = describe(ts)
    assert (date, clock) == ("1404/01/02", "00:15")
    assert weekday == "شنبه"
