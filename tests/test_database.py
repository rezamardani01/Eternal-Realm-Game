import pytest

from eternal_realm.db.database import Database

INSERT_PLAYER = (
    "INSERT INTO players (platform_user_id, display_name, race, class, energy_at, created_at)"
    " VALUES (1, 'a', 'elf', 'archer', 0, 0)"
)


async def test_migrations_applied(db):
    async with db.read() as tx:
        assert await tx.scalar("PRAGMA user_version") >= 1
        rows = await tx.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
    assert {"players", "transactions"} <= {r[0] for r in rows}


async def test_transaction_rolls_back_on_error(db):
    with pytest.raises(RuntimeError):
        async with db.transaction() as tx:
            await tx.execute(INSERT_PLAYER)
            raise RuntimeError("boom")
    async with db.read() as tx:
        assert await tx.scalar("SELECT COUNT(*) FROM players") == 0


async def test_negative_balance_is_rejected_by_schema(db):
    async with db.transaction() as tx:
        await tx.execute(INSERT_PLAYER)
    with pytest.raises(Exception):
        async with db.transaction() as tx:
            await tx.execute("UPDATE players SET gold = gold - 1 WHERE id = 1")


async def test_backup_creates_valid_copy(tmp_path):
    source = Database(tmp_path / "game.db")
    await source.connect()
    async with source.transaction() as tx:
        await tx.execute(INSERT_PLAYER)
    copy = await source.backup(tmp_path / "backups" / "copy.db")
    await source.close()
    restored = Database(copy)
    await restored.connect()
    async with restored.read() as tx:
        assert await tx.scalar("SELECT COUNT(*) FROM players") == 1
    await restored.close()
