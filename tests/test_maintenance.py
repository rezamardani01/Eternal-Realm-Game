import os

from eternal_realm.bot.maintenance import KEEP, make_backup, prune
from eternal_realm.db.database import Database


async def test_backup_is_valid_and_old_ones_are_pruned(tmp_path):
    db = Database(tmp_path / "game.db")
    await db.connect()
    folder = tmp_path / "backups"
    folder.mkdir()
    for i in range(KEEP + 3):
        old = folder / f"game-2020010{i % 10}-00000{i}.db"
        old.write_bytes(b"x")
        os.utime(old, (1_000_000 + i, 1_000_000 + i))
    path = await make_backup(db, folder)
    await db.close()
    files = list(folder.glob("game-*.db"))
    assert len(files) == KEEP and path in files

    restored = Database(path)
    await restored.connect()
    async with restored.read() as tx:
        assert await tx.scalar("PRAGMA user_version") >= 7
    await restored.close()


def test_prune_keeps_the_newest(tmp_path):
    for i in range(5):
        f = tmp_path / f"game-{i}.db"
        f.write_bytes(b"x")
        os.utime(f, (100 + i, 100 + i))
    removed = prune(tmp_path, keep=2)
    assert {p.name for p in removed} == {"game-0.db", "game-1.db", "game-2.db"}
    assert {p.name for p in tmp_path.glob("game-*.db")} == {"game-3.db", "game-4.db"}
