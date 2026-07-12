from __future__ import annotations

from pathlib import Path
import logging
import sys

import pytest

from lan_transfer.logging_config import configure_logging


def test_configure_logging_when_windowed_exe_has_no_streams(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(sys, "stdout", None)

    log_path = configure_logging(tmp_path)
    logging.getLogger("tests").info("file logging still works")

    assert "file logging still works" in log_path.read_text(encoding="utf-8")


def test_configure_logging_closes_replaced_handlers(tmp_path: Path) -> None:
    logger = logging.getLogger()
    old_handler = logging.FileHandler(tmp_path / "old.log", encoding="utf-8")
    logger.addHandler(old_handler)

    configure_logging(tmp_path / "new")

    assert old_handler.stream is None


def test_configure_logging_keeps_existing_handlers_when_new_file_handler_fails(monkeypatch, tmp_path: Path) -> None:
    logger = logging.getLogger()
    configure_logging(tmp_path / "old")
    old_handlers = list(logger.handlers)

    def fail_file_handler(*args, **kwargs):
        raise OSError("new log unavailable")

    monkeypatch.setattr("lan_transfer.logging_config.RotatingFileHandler", fail_file_handler)

    with pytest.raises(OSError):
        configure_logging(tmp_path / "new")

    assert logger.handlers == old_handlers
    assert all(getattr(handler, "stream", object()) is not None for handler in old_handlers)
    logger.info("old logging still works after failed reconfiguration")
