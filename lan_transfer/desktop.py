from __future__ import annotations

from pathlib import Path
import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from PIL import ImageTk
import qrcode

from lan_transfer import __author__, __email__, __homepage__, __version__
from lan_transfer.config import AppConfig, find_available_port
from lan_transfer.logging_config import configure_logging
from lan_transfer.server import LocalServer
from lan_transfer.storage import StorageManager


LOGGER = logging.getLogger(__name__)


def server_is_active(server: LocalServer) -> bool:
    return bool(server.is_running or getattr(server, "has_live_thread", False))


class DesktopApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("LAN File Transfer")
        self.geometry("980x560")
        self.minsize(860, 520)

        self.config_data = AppConfig()
        self.log_path = configure_logging(self.config_data.log_dir)
        self.storage = StorageManager(self.config_data.save_dir)
        self.server = LocalServer(self.config_data, self.storage)
        self.qr_photo: ImageTk.PhotoImage | None = None
        self.qr_mode = "user"
        self._status_refresh_after_id: str | None = None

        self._build_ui()
        self._refresh_values()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(200, self.start_service)
        self._schedule_status_refresh()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        shell = ttk.Frame(self, padding=18)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.columnconfigure(1, weight=0)
        shell.rowconfigure(1, weight=1)

        title = ttk.Label(shell, text="LAN File Transfer", font=("Segoe UI", 20, "bold"))
        title.grid(row=0, column=0, sticky="w")

        status_frame = ttk.Frame(shell)
        status_frame.grid(row=0, column=1, sticky="e")
        self.status_label = ttk.Label(status_frame, text="Starting...", foreground="#8a5a00")
        self.status_label.grid(row=0, column=0, padx=(0, 10))
        self.start_button = ttk.Button(status_frame, text="Start", command=self.start_service)
        self.start_button.grid(row=0, column=1, padx=3)
        self.stop_button = ttk.Button(status_frame, text="Stop", command=self.stop_service)
        self.stop_button.grid(row=0, column=2, padx=3)

        main = ttk.Frame(shell)
        main.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(18, 0))
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=0)

        details = ttk.Frame(main)
        details.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        details.columnconfigure(1, weight=1)

        labels = [
            ("LAN IP", "ip_value"),
            ("User URL", "user_url_value"),
            ("Admin URL", "admin_url_value"),
            ("Save Directory", "dir_value"),
            ("Log File", "log_value"),
            ("Security", "security_value"),
        ]
        self.value_labels: dict[str, ttk.Label] = {}
        for row, (label, key) in enumerate(labels):
            ttk.Label(details, text=label, font=("Segoe UI", 10, "bold")).grid(
                row=row, column=0, sticky="nw", pady=7, padx=(0, 12)
            )
            value = ttk.Label(details, text="", wraplength=420, justify="left")
            value.grid(row=row, column=1, sticky="ew", pady=7)
            self.value_labels[key] = value

        actions = ttk.Frame(details)
        actions.grid(row=len(labels), column=1, sticky="w", pady=(12, 0))
        ttk.Button(actions, text="Open User", command=self.open_user_browser).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Copy User", command=self.copy_user_url).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text="Open Admin", command=self.open_admin_browser).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(actions, text="Copy Admin", command=self.copy_admin_url).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(actions, text="Choose Directory", command=self.choose_directory).grid(row=0, column=4)

        qr_box = ttk.Frame(main)
        qr_box.grid(row=0, column=1, sticky="ne")
        self.qr_label = ttk.Label(qr_box)
        self.qr_label.grid(row=0, column=0)
        self.qr_caption = ttk.Label(qr_box, text="")
        self.qr_caption.grid(row=1, column=0, pady=(8, 0))
        qr_actions = ttk.Frame(qr_box)
        qr_actions.grid(row=2, column=0, pady=(8, 0))
        ttk.Button(qr_actions, text="User QR", command=lambda: self.set_qr_mode("user")).grid(
            row=0, column=0, padx=(0, 6)
        )
        ttk.Button(qr_actions, text="Admin QR", command=lambda: self.set_qr_mode("admin")).grid(row=0, column=1)

        footer = ttk.Label(
            shell,
            text=(
                "Guest users can only list public files. Signed-in users can upload and delete their own files.\n"
                f"LAN File Transfer v{__version__} | Author: {__author__} <{__email__}> | {__homepage__}"
            ),
            foreground="#555555",
        )
        footer.grid(row=2, column=0, columnspan=2, sticky="w", pady=(16, 0))

    def _refresh_values(self) -> None:
        self.value_labels["ip_value"].configure(text=self.config_data.lan_ip)
        self.value_labels["user_url_value"].configure(text=self.config_data.user_url)
        self.value_labels["admin_url_value"].configure(text=self.config_data.admin_url)
        self.value_labels["dir_value"].configure(text=str(self.config_data.save_dir))
        self.value_labels["log_value"].configure(text=str(self.log_path))
        self.value_labels["security_value"].configure(
            text="Listening on 0.0.0.0; admin password cannot be recovered if forgotten."
        )
        self._render_qr()
        self._refresh_status()

    def _server_is_active(self) -> bool:
        return server_is_active(self.server)

    def _render_qr(self) -> None:
        qr = qrcode.QRCode(border=2, box_size=8)
        qr_url = self.config_data.admin_url if self.qr_mode == "admin" else self.config_data.user_url
        qr.add_data(qr_url)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        image = image.resize((228, 228))
        self.qr_photo = ImageTk.PhotoImage(image)
        self.qr_label.configure(image=self.qr_photo)
        self.qr_caption.configure(text=f"Scan {self.qr_mode} link")

    def set_qr_mode(self, mode: str) -> None:
        self.qr_mode = mode
        self._render_qr()

    def _refresh_status(self) -> None:
        if self.server.is_running:
            self.status_label.configure(text="Running", foreground="#0a7a3f")
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
        elif server_is_active(self.server):
            self.status_label.configure(text="Service active", foreground="#8a5a00")
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
        else:
            self.status_label.configure(text="Stopped", foreground="#9b1c1c")
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")

    def _schedule_status_refresh(self) -> None:
        self._status_refresh_after_id = self.after(1000, self._poll_status)

    def _poll_status(self) -> None:
        self._refresh_status()
        self._schedule_status_refresh()

    def _cancel_status_refresh(self) -> None:
        after_id = self._status_refresh_after_id
        self._status_refresh_after_id = None
        if after_id is not None:
            self.after_cancel(after_id)

    def start_service(self) -> None:
        try:
            self.server.start()
        except Exception as exc:
            LOGGER.exception("Could not start service")
            messagebox.showerror("Service start failed", str(exc))
        self._refresh_status()

    def stop_service(self) -> None:
        try:
            self.server.stop()
        except Exception as exc:
            LOGGER.exception("Could not stop service")
            messagebox.showerror("Service stop failed", str(exc))
        finally:
            self._refresh_status()

    def open_user_browser(self) -> None:
        webbrowser.open(self.config_data.user_url)

    def open_admin_browser(self) -> None:
        webbrowser.open(self.config_data.admin_url)

    def copy_text(self, value: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(value)
        self.update()

    def copy_admin_url(self) -> None:
        self.copy_text(self.config_data.admin_url)

    def copy_user_url(self) -> None:
        self.copy_text(self.config_data.user_url)

    def choose_directory(self) -> None:
        selected = filedialog.askdirectory(initialdir=str(self.config_data.save_dir))
        if not selected:
            return

        was_active = server_is_active(self.server)
        if was_active:
            try:
                self.server.stop()
            except Exception as exc:
                LOGGER.exception("Could not stop service before switching directory")
                messagebox.showerror("Directory switch failed", str(exc))
                self._refresh_status()
                return

        previous_config = self.config_data
        previous_server = self.server
        new_log_path: Path | None = None
        new_server: LocalServer | None = None
        try:
            new_config = AppConfig(
                host=self.config_data.host,
                port=find_available_port(self.config_data.port, self.config_data.host),
                save_dir=Path(selected),
            )
            new_storage = StorageManager(new_config.save_dir)
            new_log_path = configure_logging(new_config.log_dir)
            new_server = LocalServer(new_config, new_storage)
            if was_active:
                new_server.start()
        except Exception as exc:
            LOGGER.exception("Could not switch save directory")
            failure_message = str(exc)
            if new_server is not None:
                try:
                    new_server.stop()
                except Exception as cleanup_exc:
                    LOGGER.exception("Could not stop replacement service after directory switch failure")
                    failure_message = f"{failure_message}\n\nReplacement service cleanup also failed: {cleanup_exc}"
            if new_log_path is not None:
                try:
                    configure_logging(previous_config.log_dir)
                except Exception:
                    LOGGER.exception("Could not restore logging after directory switch failure")
            if was_active:
                try:
                    previous_server.start()
                except Exception as restart_exc:
                    LOGGER.exception("Could not restart previous service after directory switch failure")
                    failure_message = f"{failure_message}\n\nPrevious service restart also failed: {restart_exc}"
            messagebox.showerror("Directory switch failed", failure_message)
            self._refresh_status()
            return

        self.config_data = new_config
        self.log_path = new_log_path
        self.storage = new_storage
        self.server = new_server
        self._refresh_values()

    def _close(self) -> None:
        try:
            self.server.stop()
        except Exception as exc:
            LOGGER.exception("Could not stop service during application close")
            messagebox.showerror("Service stop failed", str(exc))
            self._refresh_status()
            return
        self._cancel_status_refresh()
        self.destroy()


def main() -> None:
    app = DesktopApp()
    app.mainloop()


if __name__ == "__main__":
    main()
