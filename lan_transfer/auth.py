from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import base64
import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid


AUTH_SETTINGS_NAME = ".lan-transfer-auth.json"
PBKDF2_ITERATIONS = 600_000
SESSION_SECONDS = 12 * 60 * 60
MAX_FAILED_ATTEMPTS = 5
LOCK_SECONDS = 3 * 60 * 60
DEFAULT_PASSWORD = "12345678"
DEFAULT_ADMIN_USERNAME = "admin"
MAX_BATCH_USERS = 200
ROLE_ADMIN = "admin"
ROLE_USER = "user"
GROUP_PUBLIC = "public"
GROUP_DEFAULT = "everyone"
GROUP_LEGACY_DEFAULT = "default"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
GROUP_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class AuthError(ValueError):
    pass


class RoleRequiredError(AuthError):
    pass


class LockedOutError(AuthError):
    def __init__(self, locked_until: float):
        super().__init__("Too many password errors. This IP is locked.")
        self.locked_until = locked_until


@dataclass
class Session:
    token: str
    username: str
    created_at: float
    expires_at: float
    client_ip: str


@dataclass
class Principal:
    username: str | None
    role: str
    groups: list[str]
    display_name: str

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_authenticated(self) -> bool:
        return bool(self.username)


def guest_principal() -> Principal:
    return Principal(username=None, role="guest", groups=[GROUP_PUBLIC], display_name="Guest")


class AccountAuthManager:
    def __init__(self, save_dir: Path):
        self.save_dir = save_dir
        self.settings_path = self.save_dir / AUTH_SETTINGS_NAME
        self._lock = threading.RLock()
        self._settings = self._load_settings()
        self._sessions: dict[str, Session] = {}
        self._failures: dict[str, dict[str, float | int]] = {}
        self._ensure_defaults()
        self._write_settings()

    def _load_settings(self) -> dict[str, Any]:
        if self.settings_path.exists():
            with self.settings_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError(f"Invalid auth settings: {self.settings_path}")
            return data

        return {"version": 2, "users": {}, "groups": {}}

    def _ensure_defaults(self) -> None:
        self._settings.setdefault("version", 2)
        self._settings.setdefault("users", {})
        self._settings.setdefault("groups", {})
        groups = self._settings["groups"]
        groups.pop(GROUP_LEGACY_DEFAULT, None)
        groups.setdefault(
            GROUP_PUBLIC,
            {
                "id": GROUP_PUBLIC,
                "name": "Public",
                "description": "Visible to guests and every signed-in account.",
                "created_at": time.time(),
            },
        )
        groups.setdefault(
            GROUP_DEFAULT,
            {
                "id": GROUP_DEFAULT,
                "name": "Everyone",
                "description": "Default signed-in user group.",
                "created_at": time.time(),
            },
        )
        users = self._settings["users"]
        for record in users.values():
            record["groups"] = self._migrate_user_groups(record.get("groups") or [GROUP_DEFAULT])
        if DEFAULT_ADMIN_USERNAME not in users:
            users[DEFAULT_ADMIN_USERNAME] = {
                "username": DEFAULT_ADMIN_USERNAME,
                "display_name": "Admin",
                "role": ROLE_ADMIN,
                "groups": [GROUP_DEFAULT],
                "password": self._password_record(DEFAULT_PASSWORD),
                "active": True,
                "created_at": time.time(),
            }
        users[DEFAULT_ADMIN_USERNAME]["role"] = ROLE_ADMIN
        users[DEFAULT_ADMIN_USERNAME]["active"] = True
        users[DEFAULT_ADMIN_USERNAME]["groups"] = self._migrate_user_groups(
            users[DEFAULT_ADMIN_USERNAME].get("groups") or [GROUP_DEFAULT]
        )

    def _write_settings(self) -> None:
        self.save_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self.save_dir / f"{AUTH_SETTINGS_NAME}.{uuid.uuid4().hex}.tmp"
        try:
            with temp_path.open("x", encoding="utf-8") as handle:
                json.dump(self._settings, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_path, self.settings_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    @property
    def is_configured(self) -> bool:
        return True

    def _password_record(self, password: str) -> dict[str, Any]:
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
        return {
            "algorithm": "pbkdf2_hmac_sha256",
            "iterations": PBKDF2_ITERATIONS,
            "salt": base64.b64encode(salt).decode("ascii"),
            "hash": base64.b64encode(digest).decode("ascii"),
            "created_at": time.time(),
        }

    def _verify_password_record(self, record: dict[str, Any], password: str) -> bool:
        salt = base64.b64decode(record["salt"])
        expected = base64.b64decode(record["hash"])
        iterations = int(record.get("iterations") or PBKDF2_ITERATIONS)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)

    def _user_record(self, username: str) -> dict[str, Any]:
        record = self._settings["users"].get(username)
        if not record:
            raise AuthError("Unknown account.")
        return record

    def _public_user(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "username": record["username"],
            "display_name": record.get("display_name") or record["username"],
            "role": record.get("role") or ROLE_USER,
            "groups": list(record.get("groups") or []),
            "active": bool(record.get("active", True)),
        }

    def _principal_for_record(self, record: dict[str, Any]) -> Principal:
        groups = list(record.get("groups") or [])
        if GROUP_PUBLIC not in groups:
            groups.append(GROUP_PUBLIC)
        return Principal(
            username=record["username"],
            role=record.get("role") or ROLE_USER,
            groups=groups,
            display_name=record.get("display_name") or record["username"],
        )

    def list_users(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(
                [self._public_user(record) for record in self._settings["users"].values()],
                key=lambda user: user["username"],
            )

    def list_groups(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(
                [dict(group) for group in self._settings["groups"].values()],
                key=lambda group: group["id"],
            )

    def group_exists(self, group_id: str) -> bool:
        with self._lock:
            return self._normalize_group_alias(group_id) in self._settings["groups"]

    def users_in_group(self, group_id: str) -> list[str]:
        with self._lock:
            normalized = self._normalize_group_alias(group_id)
            return sorted(
                username
                for username, record in self._settings["users"].items()
                if normalized in self._migrate_user_groups(record.get("groups") or [])
            )

    def get_user(self, username: str) -> dict[str, Any]:
        with self._lock:
            return self._public_user(self._user_record(username))

    def normalize_groups(self, groups: list[str], *, allow_public: bool = False) -> list[str]:
        with self._lock:
            return self._clean_groups(groups, allow_public=allow_public)

    def snapshot_state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "settings": copy.deepcopy(self._settings),
                "sessions": copy.deepcopy(self._sessions),
                "failures": copy.deepcopy(self._failures),
            }

    def state_transaction(self):
        return self._lock

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        with self._lock:
            previous_settings = self._settings
            previous_sessions = self._sessions
            previous_failures = self._failures
            settings_changed = snapshot["settings"] != previous_settings
            self._settings = copy.deepcopy(snapshot["settings"])
            self._sessions = copy.deepcopy(snapshot["sessions"])
            self._failures = copy.deepcopy(snapshot["failures"])
            if not settings_changed:
                return
            try:
                self._write_settings()
            except Exception:
                self._settings = previous_settings
                self._sessions = previous_sessions
                self._failures = previous_failures
                raise

    def create_group(self, group_id: str, name: str | None = None, description: str | None = None) -> dict[str, Any]:
        with self._lock:
            group_id = self._normalize_group_alias(group_id)
            self._validate_group_id(group_id)
            if group_id in self._settings["groups"]:
                raise AuthError("Group already exists.")
            group = {
                "id": group_id,
                "name": name or group_id,
                "description": description or "",
                "created_at": time.time(),
            }
            self._settings["groups"][group_id] = group
            try:
                self._write_settings()
            except Exception:
                self._settings["groups"].pop(group_id, None)
                raise
            return dict(group)

    def delete_group(self, group_id: str) -> dict[str, Any]:
        with self._lock:
            group_id = self._normalize_group_alias(group_id)
            self._validate_group_id(group_id)
            if group_id in {GROUP_PUBLIC, GROUP_DEFAULT}:
                raise AuthError("Built-in groups cannot be deleted.")
            if group_id not in self._settings["groups"]:
                raise AuthError("Unknown group.")
            users = self.users_in_group(group_id)
            if users:
                raise AuthError(f"Group is still assigned to users: {', '.join(users)}")
            removed = self._settings["groups"].pop(group_id)
            try:
                self._write_settings()
            except Exception:
                self._settings["groups"][group_id] = removed
                raise
            return dict(removed)

    def create_user(
        self,
        username: str,
        *,
        password: str | None = None,
        display_name: str | None = None,
        groups: list[str] | None = None,
        role: str = ROLE_USER,
    ) -> dict[str, Any]:
        with self._lock:
            self._validate_username(username)
            if username in self._settings["users"]:
                raise AuthError("Account already exists.")
            if role not in {ROLE_USER, ROLE_ADMIN}:
                raise AuthError("Invalid role.")
            group_ids = self._clean_groups(groups or [GROUP_DEFAULT])
            password_value = password or DEFAULT_PASSWORD
            self._validate_new_password(password_value)
            record = {
                "username": username,
                "display_name": display_name or username,
                "role": role,
                "groups": group_ids,
                "password": self._password_record(password_value),
                "active": True,
                "created_at": time.time(),
            }
            self._settings["users"][username] = record
            try:
                self._write_settings()
            except Exception:
                self._settings["users"].pop(username, None)
                raise
            return self._public_user(record)

    def create_users_batch(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            if not items:
                raise AuthError("No accounts to create.")
            if len(items) > MAX_BATCH_USERS:
                raise AuthError(f"Batch can create at most {MAX_BATCH_USERS} accounts.")
            seen: set[str] = set()
            prepared: list[dict[str, Any]] = []
            for item in items:
                username = str(item.get("username") or "").strip()
                self._validate_username(username)
                if username in seen or username in self._settings["users"]:
                    raise AuthError(f"Duplicate or existing account: {username}")
                role = str(item.get("role") or ROLE_USER)
                if role != ROLE_USER:
                    raise AuthError("Batch can only create user accounts.")
                groups = item.get("groups") or [GROUP_DEFAULT]
                if not isinstance(groups, list):
                    raise AuthError(f"Groups must be a list for {username}.")
                group_ids = self._clean_groups([str(group) for group in groups])
                password = str(item.get("password") or DEFAULT_PASSWORD)
                self._validate_new_password(password)
                seen.add(username)
                prepared.append(
                    {
                        "username": username,
                        "display_name": str(item.get("display_name") or username),
                        "role": role,
                        "groups": group_ids,
                        "password": password,
                    }
                )

            created: list[dict[str, Any]] = []
            for item in prepared:
                record = {
                    "username": item["username"],
                    "display_name": item["display_name"],
                    "role": item["role"],
                    "groups": item["groups"],
                    "password": self._password_record(item["password"]),
                    "active": True,
                    "created_at": time.time(),
                }
                self._settings["users"][item["username"]] = record
                created.append(self._public_user(record))
            try:
                self._write_settings()
            except Exception:
                for item in prepared:
                    self._settings["users"].pop(item["username"], None)
                raise
            return {"created": created, "count": len(created)}

    def update_user(
        self,
        username: str,
        *,
        password: str | None = None,
        display_name: str | None = None,
        groups: list[str] | None = None,
        active: bool | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            record = self._user_record(username)
            previous = dict(record)
            password_changed = password is not None
            previous_role = previous.get("role") or ROLE_USER
            if username == DEFAULT_ADMIN_USERNAME and active is False:
                raise AuthError("The built-in admin account cannot be disabled.")
            if password is not None:
                self._validate_new_password(password)
                record["password"] = self._password_record(password)
            if display_name is not None:
                record["display_name"] = display_name or username
            if groups is not None:
                record["groups"] = self._clean_groups(groups)
            if active is not None:
                record["active"] = active
            if role is not None:
                if role not in {ROLE_USER, ROLE_ADMIN}:
                    raise AuthError("Invalid role.")
                if username == DEFAULT_ADMIN_USERNAME and role != ROLE_ADMIN:
                    raise AuthError("The built-in admin account must keep admin role.")
                record["role"] = role
            role_changed = role is not None and role != previous_role
            try:
                self._write_settings()
            except Exception:
                record.clear()
                record.update(previous)
                raise
            if password_changed or active is False or role_changed:
                self._drop_user_sessions(username)
            return self._public_user(record)

    def delete_user(self, username: str) -> dict[str, Any]:
        with self._lock:
            record = self._user_record(username)
            if username == DEFAULT_ADMIN_USERNAME:
                raise AuthError("The built-in admin account cannot be deleted.")
            removed = self._settings["users"].pop(username)
            try:
                self._write_settings()
            except Exception:
                self._settings["users"][username] = removed
                raise
            self._drop_user_sessions(username)
            return self._public_user(removed)

    def change_password(
        self,
        username: str,
        current_password: str,
        new_password: str,
        client_ip: str,
        *,
        drop_sessions: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            self.assert_not_locked(client_ip)
            record = self._user_record(username)
            if not record.get("active", True):
                raise AuthError("Account is disabled.")
            if not self._verify_password_record(record["password"], current_password):
                self._record_failure(client_ip)
                locked_until = self.locked_until(client_ip)
                if locked_until:
                    raise LockedOutError(locked_until)
                raise AuthError("Invalid current password.")
            self._validate_new_password(new_password)
            previous_password = record["password"]
            record["password"] = self._password_record(new_password)
            try:
                self._write_settings()
            except Exception:
                record["password"] = previous_password
                raise
            self._clear_failures(client_ip)
            if drop_sessions:
                self._drop_user_sessions(username)
            return dict(previous_password)

    def login(
        self,
        username: str,
        password: str,
        client_ip: str,
        *,
        required_role: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self.assert_not_locked(client_ip)
            try:
                record = self._user_record(username)
            except AuthError:
                self._record_failure(client_ip)
                raise AuthError("Invalid username or password.")
            if not self._verify_password_record(record["password"], password):
                self._record_failure(client_ip)
                locked_until = self.locked_until(client_ip)
                if locked_until:
                    raise LockedOutError(locked_until)
                raise AuthError("Invalid username or password.")
            if not record.get("active", True):
                raise AuthError("Account is disabled.")
            actual_role = record.get("role") or ROLE_USER
            if required_role and actual_role != required_role:
                message = "Admin login required." if required_role == ROLE_ADMIN else "User login required."
                raise RoleRequiredError(message)
            self._clear_failures(client_ip)
            token = self.create_session(record["username"], client_ip)
            return {"session_token": token, "user": self._public_user(record)}

    def setup_password(self, password: str, client_ip: str) -> str:
        with self._lock:
            self.change_password(DEFAULT_ADMIN_USERNAME, DEFAULT_PASSWORD, password, client_ip)
            return self.create_session(DEFAULT_ADMIN_USERNAME, client_ip)

    def _failure_state(self, client_ip: str) -> dict[str, float | int]:
        return self._failures.setdefault(client_ip, {"count": 0, "locked_until": 0.0})

    def locked_until(self, client_ip: str) -> float | None:
        with self._lock:
            state = self._failures.get(client_ip)
            if not state:
                return None
            locked_until = float(state.get("locked_until") or 0)
            if locked_until > time.time():
                return locked_until
            if locked_until:
                self._failures.pop(client_ip, None)
            return None

    def assert_not_locked(self, client_ip: str) -> None:
        locked_until = self.locked_until(client_ip)
        if locked_until:
            raise LockedOutError(locked_until)

    def _record_failure(self, client_ip: str) -> None:
        state = self._failure_state(client_ip)
        count = int(state.get("count") or 0) + 1
        state["count"] = count
        if count >= MAX_FAILED_ATTEMPTS:
            state["locked_until"] = time.time() + LOCK_SECONDS

    def _clear_failures(self, client_ip: str) -> None:
        self._failures.pop(client_ip, None)

    def create_session(self, username: str, client_ip: str) -> str:
        with self._lock:
            token = secrets.token_urlsafe(32)
            now = time.time()
            self._sessions[token] = Session(
                token=token,
                username=username,
                created_at=now,
                expires_at=now + SESSION_SECONDS,
                client_ip=client_ip,
            )
            return token

    def principal_for_session(self, token: str | None) -> Principal | None:
        with self._lock:
            if not token:
                return None
            session = self._sessions.get(token)
            if not session:
                return None
            if session.expires_at <= time.time():
                self._sessions.pop(token, None)
                return None
            record = self._settings["users"].get(session.username)
            if not record or not record.get("active", True):
                self._sessions.pop(token, None)
                return None
            return self._principal_for_record(record)

    def verify_session(self, token: str | None) -> bool:
        return self.principal_for_session(token) is not None

    def logout(self, token: str | None) -> None:
        with self._lock:
            if token:
                self._sessions.pop(token, None)

    def _drop_user_sessions(self, username: str) -> None:
        for token, session in list(self._sessions.items()):
            if session.username == username:
                self._sessions.pop(token, None)

    def drop_user_sessions(self, username: str) -> None:
        with self._lock:
            self._drop_user_sessions(username)

    def _validate_new_password(self, password: str) -> None:
        if len(password) < 8:
            raise AuthError("Password must be at least 8 characters.")

    def _validate_username(self, username: str) -> None:
        if not USERNAME_RE.fullmatch(username):
            raise AuthError("Username must be 1-64 characters: letters, numbers, dot, underscore, or dash.")

    def _validate_group_id(self, group_id: str) -> None:
        if not GROUP_ID_RE.fullmatch(group_id):
            raise AuthError("Group id must be 1-64 characters: letters, numbers, dot, underscore, or dash.")

    def _normalize_group_alias(self, group_id: str) -> str:
        return GROUP_DEFAULT if group_id == GROUP_LEGACY_DEFAULT else group_id

    def _migrate_user_groups(self, groups: list[str]) -> list[str]:
        cleaned: list[str] = []
        for group_id in groups:
            normalized = self._normalize_group_alias(str(group_id))
            if normalized == GROUP_PUBLIC:
                continue
            if normalized in self._settings["groups"] and normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned or [GROUP_DEFAULT]

    def _clean_groups(self, groups: list[str], *, allow_public: bool = False) -> list[str]:
        cleaned: list[str] = []
        for group_id in groups:
            group_id = self._normalize_group_alias(group_id)
            self._validate_group_id(group_id)
            if group_id == GROUP_PUBLIC and not allow_public:
                continue
            if group_id not in self._settings["groups"]:
                raise AuthError(f"Unknown group: {group_id}")
            if group_id not in cleaned:
                cleaned.append(group_id)
        return cleaned or [GROUP_DEFAULT]


AdminAuthManager = AccountAuthManager
