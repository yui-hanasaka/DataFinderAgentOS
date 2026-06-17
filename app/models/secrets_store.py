import os
import sqlite3

from cryptography.fernet import Fernet

_ENV_KEY = "DATAFINDER_SECRET_KEY"
_SETTING_KEY = "_fernet_key"
_PREFIX = "enc:v1:"
_FERNET_CACHE: Fernet | None = None
_WARNED = False


def _db_key() -> bytes | None:
    """Read the persisted encryption key from the database, if any.

    Import is deferred so the module can be imported before init_db() runs.
    """
    from app.models.db import get_connection

    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM sys_settings WHERE key=?", (_SETTING_KEY,)
            ).fetchone()
        if row and row["value"]:
            return row["value"].encode("utf-8")
    except (sqlite3.OperationalError, Exception):
        # Table may not exist yet (very early startup) — fall through
        pass
    return None


def _save_db_key(key: bytes) -> None:
    """Persist the encryption key to the database."""
    from app.models.db import get_connection

    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sys_settings(key, value, updated_at)"
                " VALUES(?, ?, datetime('now'))",
                (_SETTING_KEY, key.decode("utf-8")),
            )
    except (sqlite3.OperationalError, Exception):
        # Table may not exist yet — key will be ephemeral this session
        pass


def _resolve_key() -> bytes:
    """Return a stable encryption key for this process.

    Priority: 1) DATAFINDER_SECRET_KEY env var  2) persisted key in database
              3) fresh ephemeral key (saved to database for next time).
    """
    global _WARNED
    raw = os.environ.get(_ENV_KEY, "").strip()
    if raw:
        return raw.encode("utf-8")

    dev = os.environ.get("DEV", "").lower() in ("1", "true", "yes")
    if not dev and not raw:
        dev = True  # auto-dev: no key configured

    if not dev:
        raise SystemExit(
            f"FATAL: {_ENV_KEY} is required for secret encryption in production."
        )

    # Dev mode — try database-persisted key first
    db_key = _db_key()
    if db_key:
        return db_key

    # First run — generate a new key and persist it to the database
    key = Fernet.generate_key()
    _save_db_key(key)

    if not _WARNED:
        import warnings

        warnings.warn(
            "DEV mode with no DATAFINDER_SECRET_KEY — encryption key saved to"
            " database (sys_settings). Encrypted secrets will survive restarts,"
            f" but set {_ENV_KEY} for production.",
            stacklevel=2,
        )
        _WARNED = True
    return key


def _get_fernet() -> Fernet:
    global _FERNET_CACHE
    if _FERNET_CACHE is not None:
        return _FERNET_CACHE
    _FERNET_CACHE = Fernet(_resolve_key())
    return _FERNET_CACHE


def encrypt(value: str) -> str:
    if not value:
        return ""
    if value.startswith(_PREFIX):
        return value  # already encrypted
    f = _get_fernet()
    token = f.encrypt(value.encode("utf-8")).decode("utf-8")
    return _PREFIX + token


def decrypt(value: str) -> str:
    if not value:
        return ""
    if not value.startswith(_PREFIX):
        # Legacy plaintext — return as-is for backward compat
        return value
    f = _get_fernet()
    try:
        return f.decrypt(value[len(_PREFIX) :].encode("utf-8")).decode("utf-8")
    except Exception:
        # Key rotation or ephemeral key loss — old encrypted value is
        # unrecoverable. Return empty so the caller gets a clean auth failure
        # instead of a 500 crash.
        import warnings

        warnings.warn(
            "Failed to decrypt a stored secret — the encryption key may have "
            "changed. The secret will be returned as empty. Re-save the secret "
            "to re-encrypt it with the current key.",
            stacklevel=2,
        )
        return ""


def mask(value: str, show: int = 6) -> str:
    if not value:
        return "（未设置）"
    if len(value) <= show:
        return value
    return value[:show] + "****"
