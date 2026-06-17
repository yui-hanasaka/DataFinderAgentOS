import sys

from loguru import logger


def setup_logging() -> None:
    """Configure loguru with console + file sinks."""
    logger.remove()  # Remove default stderr handler
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
        level="DEBUG",
        colorize=True,
    )
    logger.add(
        "database/datafinder.log",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        level="INFO",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )


def log_error(context: str, exc: Exception) -> None:
    logger.opt(exception=exc).error("{} — {}", context, exc)
