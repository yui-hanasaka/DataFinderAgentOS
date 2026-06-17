from app.models.validators import parse_bool, parse_float, parse_int, is_valid_url


def test_parse_int_valid() -> None:
    assert parse_int("5", 0) == 5
    assert parse_int("0", 10) == 0


def test_parse_int_default() -> None:
    assert parse_int("", 42) == 42
    assert parse_int("abc", 1) == 1


def test_parse_int_bounds() -> None:
    assert parse_int("100", 0, max_value=50) == 50
    assert parse_int("-5", 0, min_value=1) == 1


def test_parse_float() -> None:
    assert parse_float("3.14", 0.0) == 3.14
    assert parse_float("", 1.0) == 1.0


def test_parse_bool() -> None:
    assert parse_bool(True)
    assert parse_bool("1")
    assert not parse_bool("0")
    assert parse_bool("true")
    assert not parse_bool("false")


def test_valid_url() -> None:
    assert is_valid_url("https://example.com")
    assert is_valid_url("http://localhost:8080/path")
    assert not is_valid_url("ftp://example.com")
    assert not is_valid_url("")
