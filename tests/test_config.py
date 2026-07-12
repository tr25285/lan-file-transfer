from __future__ import annotations

from pathlib import Path
import socket

from lan_transfer.config import AppConfig, find_available_port, get_lan_ip


class FakeUdpSocket:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def connect(self, address):
        self.address = address

    def getsockname(self):
        return ("192.168.1.88", 49152)


def test_get_lan_ip_prefers_route_selected_adapter(monkeypatch) -> None:
    monkeypatch.setattr("lan_transfer.config.socket.socket", lambda *args, **kwargs: FakeUdpSocket())
    monkeypatch.setattr("lan_transfer.config.socket.gethostname", lambda: "desktop")
    monkeypatch.setattr(
        "lan_transfer.config.socket.getaddrinfo",
        lambda *args, **kwargs: [
            (None, None, None, None, ("10.8.0.2", 0)),
            (None, None, None, None, ("172.20.0.3", 0)),
        ],
    )

    assert get_lan_ip() == "192.168.1.88"


class LinkLocalUdpSocket(FakeUdpSocket):
    def getsockname(self):
        return ("169.254.1.9", 49152)


def test_get_lan_ip_falls_back_to_hostname_candidates_when_route_is_not_usable(monkeypatch) -> None:
    monkeypatch.setattr("lan_transfer.config.socket.socket", lambda *args, **kwargs: LinkLocalUdpSocket())
    monkeypatch.setattr("lan_transfer.config.socket.gethostname", lambda: "desktop")
    monkeypatch.setattr(
        "lan_transfer.config.socket.getaddrinfo",
        lambda *args, **kwargs: [
            (None, None, None, None, ("127.0.0.1", 0)),
            (None, None, None, None, ("10.0.0.5", 0)),
            (None, None, None, None, ("192.168.1.20", 0)),
        ],
    )

    assert get_lan_ip() == "10.0.0.5"


def test_app_config_urls_reuse_one_resolved_lan_ip(monkeypatch, tmp_path: Path) -> None:
    resolved_ips = iter(["192.168.1.10", "192.168.1.11", "192.168.1.12"])
    monkeypatch.setattr("lan_transfer.config.get_lan_ip", lambda: next(resolved_ips))

    config = AppConfig(host="0.0.0.0", port=8765, save_dir=tmp_path)

    assert config.lan_ip == "192.168.1.10"
    assert config.base_url == "http://192.168.1.10:8765"
    assert config.user_url == "http://192.168.1.10:8765/"
    assert config.admin_url == "http://192.168.1.10:8765/admin"


def test_find_available_port_skips_already_bound_port() -> None:
    first_free = find_available_port(20000, "127.0.0.1")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", first_free))
        occupied.listen()

        next_free = find_available_port(first_free, "127.0.0.1")

    assert next_free != first_free
