import os

from cryptography.fernet import Fernet

_ENV_KEY = "DATAFINDER_SECRET_KEY"
_PREFIX = "enc:v1:"


def _get_fernet() -> Fernet:
    raw = os.environ.get(_ENV_KEY, "").strip()
    dev = os.environ.get("DEV", "").lower() in ("1", "true", "yes")
    if raw:
        return Fernet(raw.encode("utf-8"))
    if dev:
        # Ephemeral dev key — encrypted values will NOT survive restart
        import warnings

        warnings.warn(
            "DEV mode with no DATAFINDER_SECRET_KEY — using ephemeral encryption key."
            " Encrypted secrets will be lost on restart.",
            stacklevel=2,
        )
        return Fernet(Fernet.generate_key())
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
