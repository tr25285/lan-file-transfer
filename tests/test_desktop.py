from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from lan_transfer.config import AppConfig
from lan_transfer.desktop import DesktopApp


class FailingServer:
    def stop(self) -> None:
        raise RuntimeError("still busy")


class StoppedServer:
    is_running = False


class RunningServer:
    is_running = True

    def __init__(self) -> None:
        self.stop_called = False
        self.start_called = False

    def stop(self) -> None:
        self.stop_called = True

    def start(self) -> None:
        self.start_called = True


class ActiveServer:
    is_running = False
    has_live_thread = True


class FailingStartServer:
    is_running = False
    has_live_thread = False

    def __init__(self) -> None:
        self.stop_called = False
        self.start_called = False

    def start(self) -> None:
        self.start_called = True
        raise RuntimeError("bind failed")

    def stop(self) -> None:
        self.stop_called = True


class RecordingControl:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def configure(self, **kwargs) -> None:
        self.values.update(kwargs)


def test_stop_service_reports_failure_and_refreshes_status(monkeypatch) -> None:
    shown_errors: list[tuple[str, str]] = []
    refreshes: list[bool] = []
    app = SimpleNamespace(
        server=FailingServer(),
        _refresh_status=lambda: refreshes.append(True),
    )

    monkeypatch.setattr(
        "lan_transfer.desktop.messagebox.showerror",
        lambda title, message: shown_errors.append((title, message)),
    )

    DesktopApp.stop_service(app)  # type: ignore[arg-type]

    assert shown_errors == [("Service stop failed", "still busy")]
    assert refreshes == [True]


def test_close_reports_stop_failure_and_keeps_window_open(monkeypatch) -> None:
    shown_errors: list[tuple[str, str]] = []
    refreshes: list[bool] = []
    destroyed: list[bool] = []
    app = SimpleNamespace(
        server=FailingServer(),
        _refresh_status=lambda: refreshes.append(True),
        destroy=lambda: destroyed.append(True),
    )

    monkeypatch.setattr(
        "lan_transfer.desktop.messagebox.showerror",
        lambda title, message: shown_errors.append((title, message)),
    )

    DesktopApp._close(app)  # type: ignore[arg-type]

    assert shown_errors == [("Service stop failed", "still busy")]
    assert refreshes == [True]
    assert destroyed == []


def test_refresh_status_marks_live_thread_as_active() -> None:
    app = SimpleNamespace(
        server=ActiveServer(),
        status_label=RecordingControl(),
        start_button=RecordingControl(),
        stop_button=RecordingControl(),
    )

    DesktopApp._refresh_status(app)  # type: ignore[arg-type]

    assert app.status_label.values["text"] == "Service active"
    assert app.start_button.values["state"] == "disabled"
    assert app.stop_button.values["state"] == "normal"


def test_status_poll_refreshes_and_reschedules() -> None:
    refreshes: list[bool] = []
    scheduled: list[bool] = []
    app = SimpleNamespace(
        _refresh_status=lambda: refreshes.append(True),
        _schedule_status_refresh=lambda: scheduled.append(True),
    )

    DesktopApp._poll_status(app)  # type: ignore[arg-type]

    assert refreshes == [True]
    assert scheduled == [True]


def test_schedule_status_refresh_uses_tk_after() -> None:
    scheduled: list[tuple[int, object]] = []
    app = SimpleNamespace(
        after=lambda delay, callback: scheduled.append((delay, callback)) or "after-1",
        _poll_status=lambda: None,
        _status_refresh_after_id=None,
    )

    DesktopApp._schedule_status_refresh(app)  # type: ignore[arg-type]

    assert scheduled == [(1000, app._poll_status)]
    assert app._status_refresh_after_id == "after-1"


def test_close_cancels_status_poll_after_successful_stop() -> None:
    cancelled: list[str] = []
    destroyed: list[bool] = []
    app = SimpleNamespace(
        server=RunningServer(),
        _status_refresh_after_id="after-1",
        after_cancel=lambda after_id: cancelled.append(after_id),
        destroy=lambda: destroyed.append(True),
    )
    app._cancel_status_refresh = lambda: DesktopApp._cancel_status_refresh(app)  # type: ignore[attr-defined]

    DesktopApp._close(app)  # type: ignore[arg-type]

    assert app.server.stop_called is True
    assert cancelled == ["after-1"]
    assert app._status_refresh_after_id is None
    assert destroyed == [True]


def test_choose_directory_does_not_switch_logging_when_storage_init_fails(monkeypatch, tmp_path: Path) -> None:
    selected_dir = tmp_path / "new"
    old_config = AppConfig(host="127.0.0.1", port=8765, save_dir=tmp_path / "old")
    shown_errors: list[tuple[str, str]] = []
    refreshes: list[bool] = []
    logging_calls: list[Path] = []
    app = SimpleNamespace(
        config_data=old_config,
        server=StoppedServer(),
        _refresh_status=lambda: refreshes.append(True),
    )

    monkeypatch.setattr(
        "lan_transfer.desktop.filedialog.askdirectory",
        lambda initialdir: str(selected_dir),
    )
    monkeypatch.setattr(
        "lan_transfer.desktop.find_available_port",
        lambda start_port, host: start_port,
    )
    monkeypatch.setattr(
        "lan_transfer.desktop.configure_logging",
        lambda log_dir: logging_calls.append(log_dir) or log_dir / "lan-transfer.log",
    )

    def fail_storage(save_dir: Path):
        raise OSError(f"{save_dir} unavailable")

    monkeypatch.setattr("lan_transfer.desktop.StorageManager", fail_storage)
    monkeypatch.setattr(
        "lan_transfer.desktop.messagebox.showerror",
        lambda title, message: shown_errors.append((title, message)),
    )

    DesktopApp.choose_directory(app)  # type: ignore[arg-type]

    assert logging_calls == []
    assert app.config_data is old_config
    assert shown_errors == [("Directory switch failed", f"{selected_dir} unavailable")]
    assert refreshes == [True]


def test_choose_directory_rolls_back_when_new_server_start_fails(monkeypatch, tmp_path: Path) -> None:
    selected_dir = tmp_path / "new"
    old_config = AppConfig(host="127.0.0.1", port=8765, save_dir=tmp_path / "old")
    old_server = RunningServer()
    shown_errors: list[tuple[str, str]] = []
    refreshes: list[bool] = []
    logging_calls: list[Path] = []
    app = SimpleNamespace(
        config_data=old_config,
        server=old_server,
        storage=SimpleNamespace(),
        log_path=old_config.log_dir / "lan-transfer.log",
        _refresh_status=lambda: refreshes.append(True),
    )

    monkeypatch.setattr(
        "lan_transfer.desktop.filedialog.askdirectory",
        lambda initialdir: str(selected_dir),
    )
    monkeypatch.setattr(
        "lan_transfer.desktop.find_available_port",
        lambda start_port, host: 9123,
    )
    monkeypatch.setattr(
        "lan_transfer.desktop.configure_logging",
        lambda log_dir: logging_calls.append(log_dir) or log_dir / "lan-transfer.log",
    )
    monkeypatch.setattr(
        "lan_transfer.desktop.StorageManager",
        lambda save_dir: SimpleNamespace(save_dir=save_dir),
    )
    created_servers: list[FailingStartServer] = []

    def build_server(*args, **kwargs):
        server = FailingStartServer()
        created_servers.append(server)
        return server

    monkeypatch.setattr("lan_transfer.desktop.LocalServer", build_server)
    monkeypatch.setattr(
        "lan_transfer.desktop.messagebox.showerror",
        lambda title, message: shown_errors.append((title, message)),
    )

    DesktopApp.choose_directory(app)  # type: ignore[arg-type]

    assert logging_calls == [selected_dir / ".lan-transfer-logs", old_config.log_dir]
    assert created_servers[0].stop_called is True
    assert old_server.stop_called is True
    assert old_server.start_called is True
    assert app.config_data is old_config
    assert app.server is old_server
    assert app.log_path == old_config.log_dir / "lan-transfer.log"
    assert shown_errors == [("Directory switch failed", "bind failed")]
    assert refreshes == [True]


def test_choose_directory_reports_previous_restart_failure(monkeypatch, tmp_path: Path) -> None:
    selected_dir = tmp_path / "new"
    old_config = AppConfig(host="127.0.0.1", port=8765, save_dir=tmp_path / "old")
    shown_errors: list[tuple[str, str]] = []
    refreshes: list[bool] = []
    app = SimpleNamespace(
        config_data=old_config,
        server=RunningServer(),
        storage=SimpleNamespace(),
        log_path=old_config.log_dir / "lan-transfer.log",
        _refresh_status=lambda: refreshes.append(True),
    )

    monkeypatch.setattr(
        "lan_transfer.desktop.filedialog.askdirectory",
        lambda initialdir: str(selected_dir),
    )
    monkeypatch.setattr(
        "lan_transfer.desktop.find_available_port",
        lambda start_port, host: 9123,
    )
    monkeypatch.setattr(
        "lan_transfer.desktop.configure_logging",
        lambda log_dir: log_dir / "lan-transfer.log",
    )
    monkeypatch.setattr(
        "lan_transfer.desktop.StorageManager",
        lambda save_dir: SimpleNamespace(save_dir=save_dir),
    )

    class FailingRestartServer(RunningServer):
        is_running = True

        def start(self) -> None:
            self.start_called = True
            raise RuntimeError("restart failed")

    created_servers: list[FailingStartServer] = []

    def build_server(*args, **kwargs):
        server = FailingStartServer()
        created_servers.append(server)
        return server

    monkeypatch.setattr("lan_transfer.desktop.LocalServer", build_server)
    monkeypatch.setattr(
        "lan_transfer.desktop.messagebox.showerror",
        lambda title, message: shown_errors.append((title, message)),
    )
    restart_server = FailingRestartServer()
    app.server = restart_server

    DesktopApp.choose_directory(app)  # type: ignore[arg-type]

    assert created_servers[0].stop_called is True
    assert restart_server.stop_called is True
    assert restart_server.start_called is True
    assert app.server is restart_server
    assert "bind failed" in shown_errors[0][1]
    assert "Previous service restart also failed: restart failed" in shown_errors[0][1]
    assert refreshes == [True]


def test_choose_directory_restarts_previous_server_when_port_probe_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    selected_dir = tmp_path / "new"
    old_config = AppConfig(host="127.0.0.1", port=8765, save_dir=tmp_path / "old")
    old_server = RunningServer()
    shown_errors: list[tuple[str, str]] = []
    refreshes: list[bool] = []
    app = SimpleNamespace(
        config_data=old_config,
        server=old_server,
        _refresh_status=lambda: refreshes.append(True),
    )

    monkeypatch.setattr(
        "lan_transfer.desktop.filedialog.askdirectory",
        lambda initialdir: str(selected_dir),
    )
    monkeypatch.setattr(
        "lan_transfer.desktop.find_available_port",
        lambda start_port, host: (_ for _ in ()).throw(RuntimeError("no free port")),
    )
    monkeypatch.setattr(
        "lan_transfer.desktop.messagebox.showerror",
        lambda title, message: shown_errors.append((title, message)),
    )

    DesktopApp.choose_directory(app)  # type: ignore[arg-type]

    assert old_server.stop_called is True
    assert old_server.start_called is True
    assert app.config_data is old_config
    assert app.server is old_server
    assert shown_errors == [("Directory switch failed", "no free port")]
    assert refreshes == [True]
