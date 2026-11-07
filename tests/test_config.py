import pytest

from eternal_realm.config import ConfigError, parse_settings


def test_valid_config():
    s = parse_settings(
        {
            "bot": {"token": "abc", "owner_id": 42, "admin_ids": [7]},
            "balance": {"max_level": 50},
            "commands": {"fish": ["ماهی"]},
        }
    )
    assert s.token == "abc"
    assert s.is_admin(42) and s.is_admin(7) and not s.is_admin(1)
    assert s.balance.max_level == 50
    assert s.command_overrides["fish"] == ("ماهی",)


def test_missing_token_rejected():
    with pytest.raises(ConfigError):
        parse_settings({"bot": {"token": "", "owner_id": 1}})


def test_missing_owner_rejected():
    with pytest.raises(ConfigError):
        parse_settings({"bot": {"token": "x"}})


def test_unknown_balance_key_rejected():
    with pytest.raises(ConfigError):
        parse_settings({"bot": {"token": "x", "owner_id": 1}, "balance": {"nope": 1}})
