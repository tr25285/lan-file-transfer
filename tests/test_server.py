from __future__ import annotations

import threading

import pytest

from lan_transfer.config import AppConfig
from lan_transfer.server import LocalServer
from lan_transfer.storage import StorageManager


class NeverStartedServer:
    def __init__(self, _config) -> None:
        self.started = False
        self.should_exit = False
        self._wake = threading.Event()

    def run(self) -> None:
        while not self.should_exit:
            self._wake.wait(0.01)


class StoppedDuringStartupServer:
    def __init__(self, _config) -> None:
        self.started = False
        self.should_exit = False

    def run(self) -> None:
        return


def test_local_server_start_raises_when_uvicorn_never_reports_ready(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeConfig:
        def __init__(self, *args, **kwargs) -> None:
            pass

    monkeypatch.setattr("lan_transfer.server.uvicorn.Config", FakeConfig)
    monkeypatch.setattr("lan_transfer.server.uvicorn.Server", NeverStartedServer)
    clock = {"now": 0.0}

    def fake_time() -> float:
        clock["now"] += 10.0
        return clock["now"]

    monkeypatch.setattr("lan_transfer.server.time.time", fake_time)

    server = LocalServer(AppConfig(host="127.0.0.1", port=9876, save_dir=tmp_path), StorageManager(tmp_path))

    with pytest.raises(RuntimeError, match="did not report ready"):
        server.start()

    assert server._server is None
    assert server._thread is None
    assert not server.is_running
    for thread in threading.enumerate():
        assert thread.name != "LANTransferHTTP" or not thread.is_alive()


def test_local_server_start_clears_refs_when_thread_stops_before_ready(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeConfig:
        def __init__(self, *args, **kwargs) -> None:
            pass

    monkeypatch.setattr("lan_transfer.server.uvicorn.Config", FakeConfig)
    monkeypatch.setattr("lan_transfer.server.uvicorn.Server", StoppedDuringStartupServer)

    server = LocalServer(AppConfig(host="127.0.0.1", port=9876, save_dir=tmp_path), StorageManager(tmp_path))

    with pytest.raises(RuntimeError, match="stopped during startup"):
        server.start()

    assert server._server is None
    assert server._thread is None
    assert not server.is_running


def test_local_server_start_timeout_preserves_live_thread_status_when_shutdown_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeConfig:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeUvicornServer:
        def __init__(self, _config) -> None:
            self.started = False
            self.should_exit = False

    class FakeThread:
        def __init__(self, *args, **kwargs) -> None:
            self.alive = False

        def start(self) -> None:
            self.alive = True

        def is_alive(self) -> bool:
            return self.alive

    monkeypatch.setattr("lan_transfer.server.uvicorn.Config", FakeConfig)
    monkeypatch.setattr("lan_transfer.server.uvicorn.Server", FakeUvicornServer)
    monkeypatch.setattr("lan_transfer.server.threading.Thread", FakeThread)
    clock = {"now": 0.0}

    def fake_time() -> float:
        clock["now"] += 10.0
        return clock["now"]

    monkeypatch.setattr("lan_transfer.server.time.time", fake_time)

    server = LocalServer(AppConfig(host="127.0.0.1", port=9876, save_dir=tmp_path), StorageManager(tmp_path))

    def fail_stop() -> None:
        raise RuntimeError("shutdown stuck")

    monkeypatch.setattr(server, "stop", fail_stop)

    with pytest.raises(RuntimeError, match="did not report ready.*shutdown stuck"):
        server.start()

    assert server.has_live_thread
    assert not server.is_running


class HungServer:
    started = True
    should_exit = False


class HungThread:
    def __init__(self) -> None:
        self.join_called = False

    def join(self, timeout=None) -> None:
        self.join_called = True

    def is_alive(self) -> bool:
        return True


def test_local_server_stop_raises_when_thread_does_not_exit(tmp_path) -> None:
    server = LocalServer(AppConfig(host="127.0.0.1", port=9876, save_dir=tmp_path), StorageManager(tmp_path))
    hung_server = HungServer()
    hung_thread = HungThread()
    server._server = hung_server
    server._thread = hung_thread  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="did not stop"):
        server.stop()

    assert hung_server.should_exit is True
    assert hung_thread.join_called is True
    assert server._server is hung_server
    assert server._thread is hung_thread
