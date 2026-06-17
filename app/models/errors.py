import logging

logger = logging.getLogger("datafinder")


def safe_error(public_msg: str, exc: Exception | None = None) -> str:
    if exc:
        logger.error("SafeError: %s | detail=%s", public_msg, exc)
    return public_msg


def log_error(context: str, exc: Exception) -> None:
    logger.error("%s: %s", context, exc, exc_info=exc)
