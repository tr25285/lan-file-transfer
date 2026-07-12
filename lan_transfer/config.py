from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import ipaddress
import socket


DEFAULT_PORT = 8765


def default_save_dir() -> Path:
    downloads = Path.home() / "Downloads"
    if downloads.exists():
        return downloads / "LAN File Transfer"
    return Path.home() / "LAN File Transfer"


def is_usable_lan_ip(value: str) -> bool:
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not parsed.is_loopback and not parsed.is_link_local and parsed.is_private


def get_lan_ip() -> str:
    candidates: list[str] = []

    # UDP connect does not send application data; it asks the OS which local
    # interface would be used for a private LAN route.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.168.255.255", 9))
            ip = sock.getsockname()[0]
            if is_usable_lan_ip(ip):
                return ip
    except OSError:
        pass

    try:
        host_name = socket.gethostname()
        for info in socket.getaddrinfo(host_name, None, socket.AF_INET):
            ip = info[4][0]
            if is_usable_lan_ip(ip):
                candidates.append(ip)
    except OSError:
        pass

    if candidates:
        return sorted(set(candidates))[0]

    return "127.0.0.1"


def find_available_port(start_port: int = DEFAULT_PORT, host: str = "0.0.0.0") -> int:
    for port in range(start_port, start_port + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free TCP port found from {start_port} to {start_port + 99}.")


@dataclass
class AppConfig:
    host: str = "0.0.0.0"
    port: int = field(default_factory=lambda: find_available_port(DEFAULT_PORT))
    save_dir: Path = field(default_factory=default_save_dir)
    _lan_ip: str | None = field(default=None, init=False, repr=False)

    @property
    def lan_ip(self) -> str:
        if self._lan_ip is None:
            self._lan_ip = get_lan_ip()
        return self._lan_ip

    @property
    def base_url(self) -> str:
        return f"http://{self.lan_ip}:{self.port}"

    @property
    def access_url(self) -> str:
        return self.user_url

    @property
    def user_url(self) -> str:
        return f"{self.base_url}/"

    @property
    def admin_url(self) -> str:
        return f"{self.base_url}/admin"

    @property
    def log_dir(self) -> Path:
        return self.save_dir / ".lan-transfer-logs"
