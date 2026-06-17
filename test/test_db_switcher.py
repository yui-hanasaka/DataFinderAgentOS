"""Tests for DatabaseSwitcher."""

import gc
import os
import tempfile
import threading
from collections.abc import Generator

import pytest

import app.models.db as db_module
from app.models.db_switcher import DatabaseSwitcher, DatabaseSwitchError


@pytest.fixture()
def tmp_db() -> Generator[None, None, None]:
    path = tempfile.mktemp(suffix=".db")
    db_module.DB_PATH = path
    os.environ.setdefault("COOKIE_SECRET", "test-cookie-secret-for-testing-32chars")
    os.environ.setdefault("DATAFINDER_SECRET_KEY", "test-secret-for-encryption-32chr")
    os.environ.setdefault("ADMIN_INITIAL_PASSWORD", "admin888")
    os.environ.setdefault("DEV", "1")
    db_module.init_db()
    yield
    gc.collect()
    try:
        if os.path.exists(path):
            os.remove(path)
    except PermissionError:
        pass


@pytest.fixture()
def _reset_state() -> None:
    """Ensure module state is reset before each test."""
    db_module._active_db_type = "sqlite"
    db_module._mysql_params = {}
    try:
        db_module._switch_lock.release()
    except RuntimeError:
        pass


def test_preflight_sqlite_succeeds(tmp_db: None, _reset_state: None) -> None:
    switcher = DatabaseSwitcher("sqlite")
    switcher.preflight()  # should not raise


def test_preflight_mysql_bad_params_fails(tmp_db: None, _reset_state: None) -> None:
    switcher = DatabaseSwitcher(
        "mysql",
        {
            "host": "192.0.2.1",
            "port": 3306,
            "user": "nobody",
            "password": "wrong",
            "database": "nonexistent",
        },
    )
    with pytest.raises(DatabaseSwitchError):
        switcher.preflight()


def test_preflight_invalid_target(tmp_db: None, _reset_state: None) -> None:
    with pytest.raises(ValueError, match="Unknown target"):
        DatabaseSwitcher("postgresql")  # type: ignore[arg-type]


def test_switch_updates_active_db_type(tmp_db: None, _reset_state: None) -> None:
    """Switch from sqlite to sqlite updates state."""
    switcher = DatabaseSwitcher("sqlite")
    switcher.lock()
    try:
        switcher.migrate()
        switcher.switch()
    finally:
        if switcher._locked:
            switcher.unlock()
    assert db_module._active_db_type == "sqlite"


def test_lock_blocks_other_threads(tmp_db: None, _reset_state: None) -> None:
    """A thread trying get_connection() during lock should block."""
    result = {"acquired": False}

    def worker() -> None:
        conn = db_module.get_connection()
        conn.close()
        result["acquired"] = True

    switcher = DatabaseSwitcher("sqlite")
    switcher.lock()
    try:
        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=0.3)
        assert not result["acquired"]
    finally:
        switcher.unlock()
    t.join(timeout=2)
    assert result["acquired"]


def test_migration_preserves_row_counts(tmp_db: None, _reset_state: None) -> None:
    """After a sqlite→sqlite migration, row counts should match."""
    with db_module.get_connection() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, salt) VALUES(?,?,?)",
            ("testuser", "hash", "salt"),
        )

    with db_module.get_connection() as conn:
        before = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"]

    switcher = DatabaseSwitcher("sqlite")
    switcher.lock()
    try:
        switcher.migrate()
        switcher.switch()
    finally:
        if switcher._locked:
            switcher.unlock()

    with db_module.get_connection() as conn:
        after = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"]

    assert before == after
    assert before >= 1


def test_rollback_after_lock_releases(tmp_db: None, _reset_state: None) -> None:
    """rollback() should release the lock without changing state."""
    original = db_module._active_db_type
    switcher = DatabaseSwitcher("sqlite")
    switcher.lock()
    switcher.rollback()
    assert db_module._active_db_type == original
    conn = db_module.get_connection()
    conn.close()
