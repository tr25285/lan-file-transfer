from __future__ import annotations

import logging
import threading
import time

import uvicorn

from .api import create_app
from .config import AppConfig
from .storage import StorageManager


LOGGER = logging.getLogger(__name__)


class LocalServer:
    def __init__(self, config: AppConfig, storage: StorageManager):
        self.config = config
        self.storage = storage
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None

    @property
    def is_running(self) -> bool:
        return bool(self.has_live_thread and self._server and self._server.started)

    @property
    def has_live_thread(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        app = create_app(self.config, self.storage)
        uvicorn_config = uvicorn.Config(
            app,
            host=self.config.host,
            port=self.config.port,
            log_level="info",
            access_log=True,
            log_config=None,
        )
        self._server = uvicorn.Server(uvicorn_config)
        self._thread = threading.Thread(target=self._run, name="LANTransferHTTP", daemon=True)
        self._thread.start()

        deadline = time.time() + 5
        while time.time() < deadline:
            if self._server.started:
                LOGGER.info(
                    "HTTP service started. User URL: %s Admin URL: %s",
                    self.config.user_url,
                    self.config.admin_url,
                )
                return
            if not self._thread.is_alive():
                self._server = None
                self._thread = None
                raise RuntimeError("HTTP service stopped during startup.")
            time.sleep(0.05)
        timeout_error = RuntimeError("HTTP service did not report ready within 5 seconds.")
        try:
            self.stop()
        except Exception as exc:
            raise RuntimeError(
                f"{timeout_error.args[0]} Shutdown after timeout also failed: {exc}"
            ) from exc
        raise timeout_error

    def _run(self) -> None:
        assert self._server is not None
        try:
            self._server.run()
        except Exception:
            LOGGER.exception("HTTP service crashed")
            raise

    def stop(self) -> None:
        if not self._server:
            return
        self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                raise RuntimeError("HTTP service did not stop within 5 seconds.")
        self._server = None
        self._thread = None
        LOGGER.info("HTTP service stopped")
