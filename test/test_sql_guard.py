from app.models.sql_guard import validate_select_sql


def test_allow_simple_select() -> None:
    ok, err = validate_select_sql("SELECT * FROM watchtower_items")
    assert ok
    assert not err


def test_reject_insert() -> None:
    ok, err = validate_select_sql("INSERT INTO users VALUES(1)")
    assert not ok


def test_reject_delete() -> None:
    ok, err = validate_select_sql("DELETE FROM watchtower_items")
    assert not ok


def test_reject_sensitive_table() -> None:
    ok, err = validate_select_sql("SELECT * FROM users")
    assert not ok


def test_reject_sqlite_master() -> None:
    ok, err = validate_select_sql("SELECT * FROM sqlite_master")
    assert not ok


def test_reject_pragma() -> None:
    ok, err = validate_select_sql("PRAGMA table_info(admin_users)")
    assert not ok


def test_allow_safe_table() -> None:
    ok, err = validate_select_sql(
        "SELECT title, url FROM watchtower_items WHERE risk > 3"
    )
    assert ok


def test_reject_multi_statement() -> None:
    ok, err = validate_select_sql("SELECT 1; DROP TABLE users")
    assert not ok
