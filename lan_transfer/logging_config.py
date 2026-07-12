from __future__ import annotations

from logging.handlers import RotatingFileHandler
from pathlib import Path
import logging
import sys


def configure_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "lan-transfer.log"

    logger = logging.getLogger()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    new_handlers: list[logging.Handler] = [file_handler]
    stream = sys.stderr or sys.stdout
    if stream is not None:
        stream_handler = logging.StreamHandler(stream)
        stream_handler.setFormatter(formatter)
        new_handlers.append(stream_handler)

    old_handlers = list(logger.handlers)
    logger.setLevel(logging.INFO)
    for handler in old_handlers:
        logger.removeHandler(handler)
    for handler in new_handlers:
        logger.addHandler(handler)
    for handler in old_handlers:
        handler.close()

    return log_path
