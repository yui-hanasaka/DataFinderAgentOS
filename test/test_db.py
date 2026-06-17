import gc
import os
import tempfile
from collections.abc import Generator

import pytest
import app.models.db as db_module


@pytest.fixture()
def tmp_db() -> Generator[None, None, None]:
    path = tempfile.mktemp(suffix=".db")
    db_module.DB_PATH = path
    db_module.init_db()
    yield
    gc.collect()
    try:
        if os.path.exists(path):
            os.remove(path)
    except PermissionError:
        pass


def test_tables_created(tmp_db: None) -> None:
    expected = [
        "users", "admin_roles", "admin_users", "admin_menus",
        "admin_role_menus", "ai_models", "ai_model_usage",
        "digital_employees", "skills", "chat_sessions", "chat_messages",
        "watchtower_sources", "watchtower_items", "deep_tasks",
        "api_keys", "data_warehouse", "sys_settings",
    ]
    with db_module.get_connection() as conn:
        tables = [r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
    for t in expected:
        assert t in tables, f"Table '{t}' not found"


def test_seed_admin_user(tmp_db: None) -> None:
    with db_module.get_connection() as conn:
        row = conn.execute("SELECT * FROM admin_users WHERE username='admin'").fetchone()
    assert row is not None
    assert row["is_super"] == 1


def test_seed_builtin_skills(tmp_db: None) -> None:
    with db_module.get_connection() as conn:
        codes = [r["code"] for r in conn.execute("SELECT code FROM skills").fetchall()]
    for code in ("weather", "music", "campus", "websearch"):
        assert code in codes


def test_sys_settings_defaults(tmp_db: None) -> None:
    with db_module.get_connection() as conn:
        row = conn.execute("SELECT value FROM sys_settings WHERE key='db_type'").fetchone()
    assert row is not None
    assert row["value"] == "sqlite"
