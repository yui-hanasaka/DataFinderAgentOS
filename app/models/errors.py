import logging

logger = logging.getLogger("datafinder")


def log_error(context: str, exc: Exception) -> None:
    logger.error("%s: %s", context, exc, exc_info=exc)
