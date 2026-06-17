import os

from cryptography.fernet import Fernet

_ENV_KEY = "DATAFINDER_SECRET_KEY"
_PREFIX = "enc:v1:"
_FERNET_CACHE: Fernet | None = None
_WARNED = False


def _get_fernet() -> Fernet:
    global _FERNET_CACHE, _WARNED
    if _FERNET_CACHE is not None:
        return _FERNET_CACHE
    raw = os.environ.get(_ENV_KEY, "").strip()
    dev = os.environ.get("DEV", "").lower() in ("1", "true", "yes")
    if raw:
        _FERNET_CACHE = Fernet(raw.encode("utf-8"))
        return _FERNET_CACHE
    if not raw and not dev:
        dev = True  # auto-dev: no DATAFINDER_SECRET_KEY set
    if dev:
        # Ephemeral dev key — encrypted values will NOT survive restart
        if not _WARNED:
            import warnings

            warnings.warn(
                "DEV mode with no DATAFINDER_SECRET_KEY — using ephemeral encryption key."
                " Encrypted secrets will be lost on restart.",
                stacklevel=2,
            )
            _WARNED = True
        _FERNET_CACHE = Fernet(Fernet.generate_key())
        return _FERNET_CACHE
    raise SystemExit(
        f"FATAL: {_ENV_KEY} is required for secret encryption in production."
    )


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
    return f.decrypt(value[len(_PREFIX) :].encode("utf-8")).decode("utf-8")


def mask(value: str, show: int = 6) -> str:
    if not value:
        return "（未设置）"
    if len(value) <= show:
        return value
    return value[:show] + "****"
