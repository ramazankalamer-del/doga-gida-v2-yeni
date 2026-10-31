import importlib.util
from pathlib import Path
import socket
import sqlite3

spec = importlib.util.spec_from_file_location('launcher', Path(__file__).resolve().parents[2] / 'baslat.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_backup_includes_committed_wal_data(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    path = tmp_path / 'live.db'
    with sqlite3.connect(path) as source:
        source.execute('PRAGMA journal_mode=WAL')
        source.execute('CREATE TABLE sample(value TEXT)')
        source.execute("INSERT INTO sample VALUES('korundu')")
        source.commit()
        launcher.backup(path)
        saved = list((tmp_path / 'yedekler').glob('*.db'))
        assert len(saved) == 1
        with sqlite3.connect(saved[0]) as copy:
            assert copy.execute('SELECT value FROM sample').fetchone()[0] == 'korundu'
        assert source.execute('SELECT COUNT(*) FROM sample').fetchone()[0] == 1


def test_busy_port_is_preserved():
    with socket.socket() as existing:
        existing.bind(('127.0.0.1', 0))
        existing.listen()
        busy = existing.getsockname()[1]
        assert launcher.available_port(busy) != busy
        assert existing.getsockname()[1] == busy
