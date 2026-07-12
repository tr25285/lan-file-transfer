from __future__ import annotations

from email.utils import formatdate
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote
import logging
import mimetypes
import os

from fastapi import Cookie, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask

from .audit import AuditManager, DEFAULT_AUDIT_LIMIT, MAX_AUDIT_LIMIT
from .auth import (
    DEFAULT_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
    GROUP_DEFAULT,
    GROUP_LEGACY_DEFAULT,
    GROUP_PUBLIC,
    AccountAuthManager,
    AuthError,
    LockedOutError,
    Principal,
    ROLE_ADMIN,
    ROLE_USER,
    RoleRequiredError,
    guest_principal,
)
from .config import AppConfig
from .security import UnsafePathError
from .storage import StorageManager, safe_float_timestamp, safe_timestamp_from_last_modified_ms


LOGGER = logging.getLogger(__name__)
SESSION_COOKIE = "lan_transfer_session"


def static_dir() -> Path:
    return Path(__file__).resolve().parent / "static"


class LoginPayload(BaseModel):
    username: str
    password: str


class PasswordPayload(BaseModel):
    password: str


class ChangePasswordPayload(BaseModel):
    current_password: str
    new_password: str


class UserCreatePayload(BaseModel):
    username: str
    password: str | None = None
    display_name: str | None = None
    groups: list[str] | None = None
    role: str = ROLE_USER


class UserBatchCreatePayload(BaseModel):
    users: list[UserCreatePayload]


class UserUpdatePayload(BaseModel):
    password: str | None = None
    display_name: str | None = None
    groups: list[str] | None = None
    active: bool | None = None
    role: str | None = None


class GroupPayload(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None


class FilePermissionPayload(BaseModel):
    allowed_groups: list[str]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def session_token_from_headers(
    authorization: str | None,
    x_admin_session: str | None,
    x_user_session: str | None,
    session_cookie: str | None,
) -> str | None:
    if x_admin_session:
        return x_admin_session
    if x_user_session:
        return x_user_session
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if session_cookie:
        return session_cookie
    return None


def principal_dependency(auth: AccountAuthManager):
    async def current_principal(
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        x_admin_session: Annotated[str | None, Header(alias="X-Admin-Session")] = None,
        x_user_session: Annotated[str | None, Header(alias="X-User-Session")] = None,
        session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    ) -> Principal:
        token = session_token_from_headers(authorization, x_admin_session, x_user_session, session_cookie)
        return auth.principal_for_session(token) or guest_principal()

    return current_principal


def login_dependency(auth: AccountAuthManager):
    current = principal_dependency(auth)

    async def require_login(principal: Principal = Depends(current)) -> Principal:
        if not principal.is_authenticated:
            raise HTTPException(status_code=403, detail="Login required.")
        return principal

    return require_login


def user_dependency(auth: AccountAuthManager):
    current = principal_dependency(auth)

    async def require_user(principal: Principal = Depends(current)) -> Principal:
        if not principal.is_authenticated or principal.role != ROLE_USER:
            raise HTTPException(status_code=403, detail="User login required.")
        return principal

    return require_user


def admin_dependency(auth: AccountAuthManager):
    current = principal_dependency(auth)

    async def require_admin(principal: Principal = Depends(current)) -> Principal:
        if not principal.is_admin:
            raise HTTPException(status_code=403, detail="Admin login required.")
        return principal

    return require_admin


def auth_error_response(exc: AuthError) -> HTTPException:
    if isinstance(exc, LockedOutError):
        return HTTPException(
            status_code=423,
            detail={
                "message": str(exc),
                "locked_until": exc.locked_until,
            },
        )
    if isinstance(exc, RoleRequiredError):
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def content_disposition(filename: str) -> str:
    fallback = "".join(char if 32 <= ord(char) < 127 and char not in '";/\\' else "_" for char in filename)
    fallback = fallback or "download"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


def entry_allowed_groups(entry: dict[str, Any]) -> list[str]:
    groups = entry.get("allowed_groups")
    if isinstance(groups, list) and groups:
        cleaned: list[str] = []
        for group in groups:
            normalized = GROUP_DEFAULT if str(group) == GROUP_LEGACY_DEFAULT else str(group)
            if normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned or [GROUP_DEFAULT]
    return [GROUP_DEFAULT]


def entry_owner(entry: dict[str, Any]) -> str:
    return str(entry.get("owner_username") or ROLE_ADMIN)


def entry_is_quarantined(entry: dict[str, Any]) -> bool:
    return entry.get("audit_status") in {"failed", "pending"}


def can_view_entry(entry: dict[str, Any], principal: Principal) -> bool:
    if entry_is_quarantined(entry):
        return False
    if principal.is_admin:
        return True
    if principal.username and entry_owner(entry) == principal.username:
        return True
    return bool(set(entry_allowed_groups(entry)).intersection(principal.groups))


def can_delete_entry(entry: dict[str, Any], principal: Principal) -> bool:
    return principal.is_admin or bool(principal.username and entry_owner(entry) == principal.username)


def serialize_entry(entry: dict[str, Any], principal: Principal) -> dict[str, Any]:
    serialized = dict(entry)
    serialized.setdefault("owner_username", entry_owner(entry))
    serialized.setdefault("owner_display_name", serialized["owner_username"])
    serialized["allowed_groups"] = entry_allowed_groups(entry)
    serialized["can_delete"] = can_delete_entry(entry, principal)
    serialized["can_manage_permissions"] = principal.is_admin
    return serialized


def visible_entries(storage: StorageManager, principal: Principal) -> list[dict[str, Any]]:
    return [entry for entry in storage.list_files() if can_view_entry(entry, principal)]


def download_scope_principal(scope: str | None, principal: Principal) -> Principal:
    normalized_scope = (scope or "").strip().lower()
    if normalized_scope == "guest":
        return guest_principal()
    if normalized_scope == "user" and principal.role != ROLE_USER:
        return guest_principal()
    return principal


def searchable_text(entry: dict[str, Any]) -> str:
    values = [
        entry.get("original_filename"),
        entry.get("relative_path"),
        entry.get("saved_relative_path"),
        entry.get("owner_username"),
        entry.get("sha256"),
        " ".join(entry_allowed_groups(entry)),
    ]
    return " ".join(str(value or "") for value in values).lower()


def numeric_sort_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def sorted_entries(
    entries: list[dict[str, Any]],
    *,
    sort_by: str,
    sort_dir: str,
    search: str | None,
) -> list[dict[str, Any]]:
    allowed_sort_fields = {
        "name": lambda entry: str(entry.get("original_filename") or "").lower(),
        "size": lambda entry: numeric_sort_value(entry.get("file_size")),
        "uploaded": lambda entry: str(entry.get("uploaded_at") or ""),
        "mtime": lambda entry: numeric_sort_value(entry.get("server_mtime")),
        "owner": lambda entry: str(entry.get("owner_username") or "").lower(),
    }
    filtered = entries
    if search:
        needle = search.strip().lower()
        if needle:
            filtered = [entry for entry in entries if needle in searchable_text(entry)]
    key_func = allowed_sort_fields.get(sort_by, allowed_sort_fields["uploaded"])
    return sorted(filtered, key=key_func, reverse=sort_dir == "desc")


def zip_download_timestamp(entries: list[dict[str, Any]]) -> float | None:
    timestamps: list[float] = []
    for entry in entries:
        timestamp = safe_timestamp_from_last_modified_ms(entry.get("original_last_modified_ms"))
        if timestamp is None:
            timestamp = safe_float_timestamp(entry.get("server_mtime"))
        if timestamp is not None:
            timestamps.append(timestamp)
    return max(timestamps) if timestamps else None


def clean_allowed_groups(
    auth: AccountAuthManager,
    groups: list[str] | None,
    fallback: list[str],
    *,
    allow_public: bool = True,
) -> list[str]:
    requested = groups if groups else fallback
    return auth.normalize_groups(requested, allow_public=allow_public)


def groups_with_usage(auth: AccountAuthManager, storage: StorageManager) -> list[dict[str, Any]]:
    entries = [entry for entry in storage.list_files() if not entry_is_quarantined(entry)]
    groups = auth.list_groups()
    users = auth.list_users()
    for group in groups:
        group_id = group["id"]
        group["user_count"] = sum(1 for user in users if group_id in user.get("groups", []))
        group["file_count"] = sum(1 for entry in entries if group_id in entry_allowed_groups(entry))
    return groups


def group_in_use_error(users: list[str], files: list[dict[str, Any]]) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "message": "Group is still in use.",
            "users": users,
            "file_count": len(files),
            "files": [entry.get("original_filename") for entry in files[:20]],
        },
    )


def audit_actor(principal: Principal) -> str:
    return principal.username or "guest"


def record_audit(
    audit: AuditManager,
    request: Request,
    principal: Principal,
    *,
    action: str,
    target_type: str,
    target_id: str | None = None,
    target_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        audit.record(
            action=action,
            actor=audit_actor(principal),
            role=principal.role,
            client_ip=client_ip(request),
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            metadata=metadata,
        )
    except Exception:
        LOGGER.exception("Failed to write audit event %s for %s", action, target_name or target_id or target_type)
        raise HTTPException(status_code=500, detail="Audit log write failed.")


def restore_auth_snapshot(auth: AccountAuthManager, snapshot: dict[str, Any], context: str) -> bool:
    try:
        auth.restore_state(snapshot)
        return True
    except Exception:
        LOGGER.exception("Failed to roll back auth state after %s", context)
        return False


def cleanup_temp_file(path: str | Path, context: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        LOGGER.exception("Failed to remove temporary file after %s: %s", context, path)


def principal_from_public_user(user: dict[str, Any]) -> Principal:
    return Principal(
        username=str(user.get("username") or ""),
        role=str(user.get("role") or ROLE_USER),
        groups=[str(group) for group in user.get("groups", [])],
        display_name=str(user.get("display_name") or user.get("username") or ""),
    )


def session_json_response(payload: dict[str, Any], cookie_token: str | None = None) -> JSONResponse:
    response = JSONResponse(payload)
    token = cookie_token if cookie_token is not None else payload.get("session_token")
    if isinstance(token, str) and token:
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=12 * 60 * 60,
            httponly=True,
            samesite="lax",
        )
    return response


def clear_session_response(payload: dict[str, Any] | None = None) -> JSONResponse:
    response = JSONResponse(payload or {"ok": True})
    response.delete_cookie(SESSION_COOKIE)
    return response


def create_app(
    config: AppConfig,
    storage: StorageManager | None = None,
    auth: AccountAuthManager | None = None,
    audit: AuditManager | None = None,
) -> FastAPI:
    storage = storage or StorageManager(config.save_dir)
    auth = auth or AccountAuthManager(config.save_dir)
    audit = audit or AuditManager(config.save_dir)
    current_principal = principal_dependency(auth)
    require_login = login_dependency(auth)
    require_user = user_dependency(auth)
    require_admin = admin_dependency(auth)

    app = FastAPI(title="LAN File Transfer", version="1.0.0")
    app.state.config = config
    app.state.storage = storage
    app.state.auth = auth
    app.state.audit = audit

    app.mount("/static", StaticFiles(directory=static_dir()), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        index_path = static_dir() / "user.html"
        return HTMLResponse(index_path.read_text(encoding="utf-8"))

    @app.get("/admin", response_class=HTMLResponse)
    async def admin() -> HTMLResponse:
        admin_path = static_dir() / "admin.html"
        return HTMLResponse(admin_path.read_text(encoding="utf-8"))

    @app.get("/api/status")
    async def status(
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        x_admin_session: Annotated[str | None, Header(alias="X-Admin-Session")] = None,
        x_user_session: Annotated[str | None, Header(alias="X-User-Session")] = None,
        session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
        principal: Principal = Depends(current_principal),
    ) -> JSONResponse:
        payload = {
            "host": config.host,
            "port": config.port,
            "lan_ip": config.lan_ip,
            "base_url": config.base_url,
            "user_url": config.user_url,
            "admin_url": config.admin_url,
            "role": principal.role,
            "username": principal.username,
            "display_name": principal.display_name,
            "groups": principal.groups,
            "can_upload": principal.is_authenticated,
            "can_delete": principal.is_authenticated,
            "is_admin": principal.is_admin,
            "admin_configured": auth.is_configured,
            "save_dir": str(config.save_dir) if principal.is_authenticated else None,
            "security_note": (
                "Guests see only public files. Signed-in users can upload and delete their own files. "
                "Admins can manage every account, group, file, and permission."
            ),
        }
        token = session_token_from_headers(authorization, x_admin_session, x_user_session, session_cookie)
        if principal.is_authenticated:
            return session_json_response(payload, cookie_token=token)
        return JSONResponse(payload)

    @app.get("/api/files")
    async def list_files(
        sort_by: str = "uploaded",
        sort_dir: str = "desc",
        search: str | None = None,
        principal: Principal = Depends(current_principal),
    ) -> dict[str, object]:
        entries = sorted_entries(
            visible_entries(storage, principal),
            sort_by=sort_by,
            sort_dir=sort_dir,
            search=search,
        )
        return {"files": [serialize_entry(entry, principal) for entry in entries]}

    @app.get("/api/session")
    async def user_session(
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        x_admin_session: Annotated[str | None, Header(alias="X-Admin-Session")] = None,
        x_user_session: Annotated[str | None, Header(alias="X-User-Session")] = None,
        session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
        principal: Principal = Depends(require_user),
    ) -> JSONResponse:
        token = session_token_from_headers(authorization, x_admin_session, x_user_session, session_cookie)
        return session_json_response({"ok": True, "user": principal.__dict__}, cookie_token=token)

    @app.post("/api/login")
    async def login(payload: LoginPayload, request: Request) -> JSONResponse:
        with auth.state_transaction():
            auth_snapshot = auth.snapshot_state()
            try:
                result = auth.login(payload.username, payload.password, client_ip(request), required_role=ROLE_USER)
            except AuthError as exc:
                raise auth_error_response(exc) from exc
            login_principal = principal_from_public_user(result["user"])
            try:
                record_audit(
                    audit,
                    request,
                    login_principal,
                    action="user_logged_in",
                    target_type="user",
                    target_id=result["user"]["username"],
                    target_name=result["user"]["username"],
                )
            except HTTPException:
                restore_auth_snapshot(auth, auth_snapshot, "user login audit failure")
                raise
        return session_json_response(result)

    @app.post("/api/logout")
    async def logout(
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        x_admin_session: Annotated[str | None, Header(alias="X-Admin-Session")] = None,
        x_user_session: Annotated[str | None, Header(alias="X-User-Session")] = None,
        session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
        principal: Principal = Depends(current_principal),
    ) -> JSONResponse:
        token = session_token_from_headers(authorization, x_admin_session, x_user_session, session_cookie)
        if principal.is_admin:
            raise HTTPException(status_code=403, detail="User login required.")
        with auth.state_transaction():
            auth_snapshot = auth.snapshot_state()
            auth.logout(token)
            if principal.is_authenticated:
                try:
                    record_audit(
                        audit,
                        request,
                        principal,
                        action="user_logged_out",
                        target_type="user",
                        target_id=principal.username,
                        target_name=principal.username,
                    )
                except HTTPException:
                    restore_auth_snapshot(auth, auth_snapshot, "user logout audit failure")
                    raise
        return clear_session_response()

    @app.post("/api/password")
    async def change_password(
        payload: ChangePasswordPayload,
        request: Request,
        principal: Principal = Depends(require_user),
    ) -> dict[str, object]:
        with auth.state_transaction():
            auth_snapshot = auth.snapshot_state()
            try:
                auth.change_password(
                    principal.username or "",
                    payload.current_password,
                    payload.new_password,
                    client_ip(request),
                    drop_sessions=False,
                )
            except AuthError as exc:
                raise auth_error_response(exc) from exc
            try:
                record_audit(
                    audit,
                    request,
                    principal,
                    action="password_changed",
                    target_type="user",
                    target_id=principal.username,
                    target_name=principal.username,
                )
            except HTTPException:
                restore_auth_snapshot(auth, auth_snapshot, "password change audit failure")
                raise
            auth.drop_user_sessions(principal.username or "")
        return {"ok": True}

    @app.get("/api/admin/status")
    async def admin_status(request: Request) -> dict[str, object]:
        locked_until = auth.locked_until(client_ip(request))
        return {
            "configured": auth.is_configured,
            "locked": bool(locked_until),
            "locked_until": locked_until,
            "max_failed_attempts": 5,
            "lock_seconds": 3 * 60 * 60,
            "default_admin_username": "admin",
        }

    @app.get("/api/admin/session")
    async def admin_session(
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        x_admin_session: Annotated[str | None, Header(alias="X-Admin-Session")] = None,
        x_user_session: Annotated[str | None, Header(alias="X-User-Session")] = None,
        session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
        principal: Principal = Depends(require_admin),
    ) -> JSONResponse:
        token = session_token_from_headers(authorization, x_admin_session, x_user_session, session_cookie)
        return session_json_response({"ok": True, "user": principal.__dict__}, cookie_token=token)

    @app.get("/api/admin/audit")
    async def audit_events(
        limit: int = DEFAULT_AUDIT_LIMIT,
        _: Principal = Depends(require_admin),
    ) -> dict[str, object]:
        bounded_limit = max(1, min(int(limit or DEFAULT_AUDIT_LIMIT), MAX_AUDIT_LIMIT))
        return {
            "events": audit.recent(bounded_limit),
            "limit": bounded_limit,
            "max_limit": MAX_AUDIT_LIMIT,
            "size_bytes": audit.size_bytes(),
        }

    @app.post("/api/admin/setup")
    async def setup_admin(payload: PasswordPayload, request: Request) -> dict[str, object]:
        if auth.is_configured:
            raise HTTPException(status_code=403, detail="Setup is disabled. Login as admin and change password.")
        with auth.state_transaction():
            auth_snapshot = auth.snapshot_state()
            try:
                session_token = auth.setup_password(payload.password, client_ip(request))
            except AuthError as exc:
                raise auth_error_response(exc) from exc
            setup_principal = Principal(
                username=DEFAULT_ADMIN_USERNAME,
                role=ROLE_ADMIN,
                groups=[GROUP_DEFAULT, GROUP_PUBLIC],
                display_name="Admin",
            )
            try:
                record_audit(
                    audit,
                    request,
                    setup_principal,
                    action="admin_password_initialized",
                    target_type="user",
                    target_id=DEFAULT_ADMIN_USERNAME,
                    target_name=DEFAULT_ADMIN_USERNAME,
                )
            except HTTPException:
                restore_auth_snapshot(auth, auth_snapshot, "admin setup audit failure")
                raise
        return session_json_response({"ok": True, "session_token": session_token})

    @app.post("/api/admin/login")
    async def login_admin(payload: LoginPayload, request: Request) -> JSONResponse:
        with auth.state_transaction():
            auth_snapshot = auth.snapshot_state()
            try:
                result = auth.login(payload.username, payload.password, client_ip(request), required_role=ROLE_ADMIN)
            except AuthError as exc:
                raise auth_error_response(exc) from exc
            login_principal = principal_from_public_user(result["user"])
            try:
                record_audit(
                    audit,
                    request,
                    login_principal,
                    action="admin_logged_in",
                    target_type="user",
                    target_id=result["user"]["username"],
                    target_name=result["user"]["username"],
                )
            except HTTPException:
                restore_auth_snapshot(auth, auth_snapshot, "admin login audit failure")
                raise
        return session_json_response(result)

    @app.post("/api/admin/logout")
    async def logout_admin(
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        x_admin_session: Annotated[str | None, Header(alias="X-Admin-Session")] = None,
        x_user_session: Annotated[str | None, Header(alias="X-User-Session")] = None,
        session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
        principal: Principal = Depends(current_principal),
    ) -> JSONResponse:
        token = session_token_from_headers(authorization, x_admin_session, x_user_session, session_cookie)
        if principal.is_authenticated and not principal.is_admin:
            raise HTTPException(status_code=403, detail="Admin login required.")
        with auth.state_transaction():
            auth_snapshot = auth.snapshot_state()
            auth.logout(token)
            if principal.is_admin:
                try:
                    record_audit(
                        audit,
                        request,
                        principal,
                        action="admin_logged_out",
                        target_type="user",
                        target_id=principal.username,
                        target_name=principal.username,
                    )
                except HTTPException:
                    restore_auth_snapshot(auth, auth_snapshot, "admin logout audit failure")
                    raise
        return clear_session_response()

    @app.post("/api/admin/password")
    async def change_admin_password(
        payload: ChangePasswordPayload,
        request: Request,
        principal: Principal = Depends(require_admin),
    ) -> dict[str, object]:
        with auth.state_transaction():
            auth_snapshot = auth.snapshot_state()
            try:
                auth.change_password(
                    principal.username or "",
                    payload.current_password,
                    payload.new_password,
                    client_ip(request),
                    drop_sessions=False,
                )
            except AuthError as exc:
                raise auth_error_response(exc) from exc
            try:
                record_audit(
                    audit,
                    request,
                    principal,
                    action="admin_password_changed",
                    target_type="user",
                    target_id=principal.username,
                    target_name=principal.username,
                )
            except HTTPException:
                restore_auth_snapshot(auth, auth_snapshot, "admin password change audit failure")
                raise
            auth.drop_user_sessions(principal.username or "")
        return {"ok": True}

    @app.get("/api/admin/users")
    async def list_users(_: Principal = Depends(require_admin)) -> dict[str, object]:
        return {"users": auth.list_users()}

    @app.post("/api/admin/users")
    async def create_user(
        payload: UserCreatePayload,
        request: Request,
        principal: Principal = Depends(require_admin),
    ) -> dict[str, object]:
        with auth.state_transaction():
            auth_snapshot = auth.snapshot_state()
            try:
                user = auth.create_user(
                    payload.username,
                    password=payload.password,
                    display_name=payload.display_name,
                    groups=payload.groups,
                    role=payload.role,
                )
            except AuthError as exc:
                raise auth_error_response(exc) from exc
            try:
                record_audit(
                    audit,
                    request,
                    principal,
                    action="user_created",
                    target_type="user",
                    target_id=user["username"],
                    target_name=user["username"],
                    metadata={"role": user["role"], "groups": user["groups"]},
                )
            except HTTPException:
                restore_auth_snapshot(auth, auth_snapshot, "user create audit failure")
                raise
        return {"ok": True, "user": user, "default_password": DEFAULT_PASSWORD}

    @app.post("/api/admin/users/batch")
    async def create_users_batch(
        payload: UserBatchCreatePayload,
        request: Request,
        principal: Principal = Depends(require_admin),
    ) -> dict[str, object]:
        with auth.state_transaction():
            auth_snapshot = auth.snapshot_state()
            try:
                result = auth.create_users_batch([item.model_dump() for item in payload.users])
            except AuthError as exc:
                raise auth_error_response(exc) from exc
            created_usernames = [user["username"] for user in result["created"]]
            try:
                record_audit(
                    audit,
                    request,
                    principal,
                    action="users_batch_created",
                    target_type="user_batch",
                    metadata={
                        "count": result["count"],
                        "users": created_usernames[:100],
                        "truncated": len(created_usernames) > 100,
                    },
                )
            except HTTPException:
                restore_auth_snapshot(auth, auth_snapshot, "user batch create audit failure")
                raise
        return {"ok": True, **result, "default_password": DEFAULT_PASSWORD}

    @app.put("/api/admin/users/{username}")
    async def update_user(
        username: str,
        payload: UserUpdatePayload,
        request: Request,
        principal: Principal = Depends(require_admin),
    ) -> dict[str, object]:
        with auth.state_transaction():
            auth_snapshot = auth.snapshot_state()
            try:
                user = auth.update_user(
                    username,
                    password=payload.password,
                    display_name=payload.display_name,
                    groups=payload.groups,
                    active=payload.active,
                    role=payload.role,
                )
            except AuthError as exc:
                raise auth_error_response(exc) from exc
            changed_fields = [
                field
                for field in ("password", "display_name", "groups", "active", "role")
                if getattr(payload, field) is not None
            ]
            try:
                record_audit(
                    audit,
                    request,
                    principal,
                    action="user_updated",
                    target_type="user",
                    target_id=user["username"],
                    target_name=user["username"],
                    metadata={
                        "changed_fields": changed_fields,
                        "role": user["role"],
                        "active": user["active"],
                        "groups": user["groups"],
                    },
                )
            except HTTPException:
                restore_auth_snapshot(auth, auth_snapshot, "user update audit failure")
                raise
        return {"ok": True, "user": user}

    @app.delete("/api/admin/users/{username}")
    async def delete_user(
        username: str,
        request: Request,
        principal: Principal = Depends(require_admin),
    ) -> dict[str, object]:
        auth_snapshot: dict[str, Any] | None = None
        user: dict[str, Any] | None = None
        reassigned_file_ids: list[str] = []
        with storage.manifest_transaction():
            with auth.state_transaction():
                try:
                    if username == DEFAULT_ADMIN_USERNAME:
                        raise AuthError("The built-in admin account cannot be deleted.")
                    auth_snapshot = auth.snapshot_state()
                    user = auth.get_user(username)
                    reassigned_file_ids = storage.reassign_owner_with_ids(username, ROLE_ADMIN, "Admin")
                    try:
                        removed = auth.delete_user(username)
                        late_reassigned_file_ids = storage.reassign_owner_with_ids(username, ROLE_ADMIN, "Admin")
                        if late_reassigned_file_ids:
                            reassigned_file_ids = list(dict.fromkeys([*reassigned_file_ids, *late_reassigned_file_ids]))
                    except Exception:
                        if reassigned_file_ids:
                            try:
                                storage.reassign_owner_for_ids(
                                    reassigned_file_ids,
                                    username,
                                    str(user.get("display_name") or username),
                                )
                            except Exception:
                                LOGGER.exception("Failed to roll back file owner reassignment for %s", username)
                        if auth_snapshot is not None:
                            restore_auth_snapshot(auth, auth_snapshot, "user delete failure")
                        raise
                    reassigned_files = len(reassigned_file_ids)
                except AuthError as exc:
                    raise auth_error_response(exc) from exc
                try:
                    record_audit(
                        audit,
                        request,
                        principal,
                        action="user_deleted",
                        target_type="user",
                        target_id=removed["username"],
                        target_name=removed["username"],
                        metadata={"reassigned_files": reassigned_files, "groups": removed["groups"]},
                    )
                except HTTPException:
                    auth_restored = True
                    if auth_snapshot is not None:
                        auth_restored = restore_auth_snapshot(auth, auth_snapshot, "user delete audit failure")
                    if auth_restored and reassigned_file_ids and user is not None:
                        try:
                            storage.reassign_owner_for_ids(
                                reassigned_file_ids,
                                username,
                                str(user.get("display_name") or username),
                            )
                        except Exception:
                            LOGGER.exception("Failed to roll back file owner reassignment after audit failure for %s", username)
                    raise
        return {"ok": True, "user": removed, "reassigned_files": reassigned_files}

    @app.get("/api/admin/groups")
    async def list_groups(_: Principal = Depends(require_admin)) -> dict[str, object]:
        return {"groups": groups_with_usage(auth, storage)}

    @app.post("/api/admin/groups")
    async def create_group(
        payload: GroupPayload,
        request: Request,
        principal: Principal = Depends(require_admin),
    ) -> dict[str, object]:
        with auth.state_transaction():
            auth_snapshot = auth.snapshot_state()
            try:
                group = auth.create_group(payload.id, name=payload.name, description=payload.description)
            except AuthError as exc:
                raise auth_error_response(exc) from exc
            try:
                record_audit(
                    audit,
                    request,
                    principal,
                    action="group_created",
                    target_type="group",
                    target_id=group["id"],
                    target_name=group["name"],
                )
            except HTTPException:
                restore_auth_snapshot(auth, auth_snapshot, "group create audit failure")
                raise
        return {"ok": True, "group": group}

    @app.delete("/api/admin/groups/{group_id}")
    async def delete_group(
        group_id: str,
        request: Request,
        principal: Principal = Depends(require_admin),
    ) -> dict[str, object]:
        normalized_group_id = GROUP_DEFAULT if group_id == GROUP_LEGACY_DEFAULT else group_id
        if normalized_group_id in {GROUP_PUBLIC, GROUP_DEFAULT}:
            raise auth_error_response(AuthError("Built-in groups cannot be deleted."))
        users = auth.users_in_group(group_id)
        files = [
            entry
            for entry in storage.list_files()
            if normalized_group_id in entry_allowed_groups(entry)
        ]
        if users or files:
            raise group_in_use_error(users, files)
        with storage.manifest_transaction():
            with auth.state_transaction():
                auth_snapshot = auth.snapshot_state()
                try:
                    group = auth.delete_group(group_id)
                    users = auth.users_in_group(group_id)
                    files = [
                        entry
                        for entry in storage.list_files()
                        if normalized_group_id in entry_allowed_groups(entry)
                    ]
                    if users or files:
                        if not restore_auth_snapshot(auth, auth_snapshot, "group delete reference recheck"):
                            raise HTTPException(status_code=500, detail="Could not restore group after reference check failed.")
                        raise group_in_use_error(users, files)
                except AuthError as exc:
                    raise auth_error_response(exc) from exc
                try:
                    record_audit(
                        audit,
                        request,
                        principal,
                        action="group_deleted",
                        target_type="group",
                        target_id=group["id"],
                        target_name=group["name"],
                    )
                except HTTPException:
                    restore_auth_snapshot(auth, auth_snapshot, "group delete audit failure")
                    raise
        return {"ok": True, "group": group}

    @app.post("/api/upload")
    async def upload_file(
        request: Request,
        file: Annotated[UploadFile, File()],
        relative_path: Annotated[str | None, Form()] = None,
        last_modified_ms: Annotated[int | None, Form()] = None,
        size: Annotated[int | None, Form()] = None,
        allowed_groups: Annotated[list[str] | None, Form()] = None,
        principal: Principal = Depends(require_login),
    ) -> JSONResponse:
        def validate_upload_commit(upload_groups: list[str]) -> None:
            owner_username = principal.username or ROLE_ADMIN
            owner = auth.get_user(owner_username)
            if not owner.get("active", True):
                raise AuthError("Account is disabled.")
            current_groups = auth.normalize_groups(upload_groups, allow_public=True)
            if current_groups != upload_groups:
                raise AuthError("Upload groups changed before the file could be saved.")
            current_is_admin = owner.get("role") == ROLE_ADMIN
            owner_groups = set(owner.get("groups") or [])
            owner_groups.add(GROUP_PUBLIC)
            if not current_is_admin and not set(upload_groups).issubset(owner_groups):
                raise AuthError("You can only publish to your own groups.")

        try:
            upload_groups = clean_allowed_groups(
                auth,
                allowed_groups,
                [group for group in principal.groups if group != GROUP_PUBLIC] or [GROUP_DEFAULT],
            )
            if not principal.is_admin and not set(upload_groups).issubset(set(principal.groups)):
                raise HTTPException(status_code=403, detail="You can only publish to your own groups.")
            entry = await storage.save_upload(
                file,
                relative_path=relative_path,
                last_modified_ms=last_modified_ms,
                expected_size=size,
                owner_username=principal.username or ROLE_ADMIN,
                owner_display_name=principal.display_name,
                allowed_groups=upload_groups,
                before_commit=lambda: validate_upload_commit(upload_groups),
            )
        except AuthError as exc:
            raise auth_error_response(exc) from exc
        except UnsafePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            LOGGER.exception("Upload failed due to an OS error")
            raise HTTPException(status_code=500, detail="Upload failed due to a filesystem error.") from exc
        with storage.manifest_transaction():
            try:
                entry = storage.update_entry(entry["id"], {"audit_status": "complete"})
            except Exception as exc:
                LOGGER.exception("Failed to publish upload before audit: %s", entry["id"])
                try:
                    storage.delete_entry(entry["id"])
                except Exception:
                    LOGGER.exception("Failed to clean up unpublished upload: %s", entry["id"])
                raise HTTPException(status_code=500, detail="Upload could not be published.") from exc
            try:
                record_audit(
                    audit,
                    request,
                    principal,
                    action="file_uploaded",
                    target_type="file",
                    target_id=entry["id"],
                    target_name=entry["relative_path"],
                    metadata={
                        "size": entry["file_size"],
                        "sha256": entry["sha256"],
                        "allowed_groups": entry["allowed_groups"],
                    },
                )
            except HTTPException:
                try:
                    storage.delete_entry(entry["id"])
                except Exception:
                    LOGGER.exception("Failed to roll back upload after audit write failure: %s", entry["id"])
                    try:
                        storage.update_entry(
                            entry["id"],
                            {
                                "audit_status": "failed",
                                "audit_error": "upload_audit_failed",
                            },
                        )
                    except Exception:
                        LOGGER.exception("Failed to quarantine upload after audit rollback failure: %s", entry["id"])
                raise
        return JSONResponse({"ok": True, "file": serialize_entry(entry, principal)})

    @app.get("/api/files/{file_id}/download")
    async def download_file(
        file_id: str,
        request: Request,
        scope: Annotated[str | None, Query()] = None,
        principal: Principal = Depends(current_principal),
    ) -> FileResponse:
        principal = download_scope_principal(scope, principal)
        try:
            entry = storage.get_entry(file_id)
            if not can_view_entry(entry, principal):
                raise KeyError(file_id)
            path = storage.path_for_entry(entry)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="File not found.") from exc
        except UnsafePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if not path.exists():
            raise HTTPException(status_code=404, detail="File is listed in manifest but missing on disk.")

        media_type = mimetypes.guess_type(entry["original_filename"])[0] or "application/octet-stream"
        stat = path.stat()
        headers = {
            "Content-Disposition": content_disposition(entry["original_filename"]),
            "Content-Length": str(stat.st_size),
            "Last-Modified": formatdate(stat.st_mtime, usegmt=True),
            "ETag": f"\"sha256-{entry['sha256']}\"",
            "X-Original-Mtime": str(entry.get("original_last_modified_ms") or ""),
        }
        record_audit(
            audit,
            request,
            principal,
            action="file_downloaded",
            target_type="file",
            target_id=entry["id"],
            target_name=entry.get("relative_path") or entry.get("original_filename"),
            metadata={"size": stat.st_size, "mode": "raw"},
        )
        return FileResponse(path, media_type=media_type, headers=headers)

    @app.get("/api/files/{file_id}/download.zip")
    async def download_file_zip(
        file_id: str,
        request: Request,
        scope: Annotated[str | None, Query()] = None,
        principal: Principal = Depends(current_principal),
    ) -> FileResponse:
        principal = download_scope_principal(scope, principal)
        try:
            entry = storage.get_entry(file_id)
            if not can_view_entry(entry, principal):
                raise KeyError(file_id)
            zip_path = storage.build_zip_for_entries([entry])
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="File not found.") from exc
        except UnsafePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            zip_name = f"{Path(entry['original_filename']).stem or 'file'}.zip"
            timestamp = zip_download_timestamp([entry])
            if timestamp is not None:
                os.utime(zip_path, (timestamp, timestamp))
            headers = {
                "Content-Disposition": content_disposition(zip_name),
                "Content-Length": str(os.path.getsize(zip_path)),
            }
            if timestamp is not None:
                headers["Last-Modified"] = formatdate(timestamp, usegmt=True)
        except Exception as exc:
            cleanup_temp_file(zip_path, "single zip metadata failure")
            raise HTTPException(status_code=500, detail="Zip download could not be prepared.") from exc
        try:
            record_audit(
                audit,
                request,
                principal,
                action="file_downloaded",
                target_type="file",
                target_id=entry["id"],
                target_name=entry.get("relative_path") or entry.get("original_filename"),
                metadata={"size": entry.get("file_size"), "mode": "zip"},
            )
        except HTTPException:
            cleanup_temp_file(zip_path, "single zip audit failure")
            raise
        return FileResponse(
            zip_path,
            media_type="application/zip",
            headers=headers,
            background=BackgroundTask(lambda: cleanup_temp_file(zip_path, "single zip response cleanup")),
        )

    @app.get("/api/download.zip")
    async def download_zip(
        request: Request,
        ids: Annotated[list[str] | None, Query()] = None,
        scope: Annotated[str | None, Query()] = None,
        principal: Principal = Depends(current_principal),
    ) -> FileResponse:
        principal = download_scope_principal(scope, principal)
        requested_ids = set(ids or [])
        entries = [
            entry
            for entry in visible_entries(storage, principal)
            if not requested_ids or entry["id"] in requested_ids
        ]
        try:
            zip_path = storage.build_zip_for_entries(entries)
        except UnsafePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            timestamp = zip_download_timestamp(entries)
            if timestamp is not None:
                os.utime(zip_path, (timestamp, timestamp))
            headers = {
                "Content-Disposition": content_disposition("lan-transfer-files.zip"),
                "Content-Length": str(os.path.getsize(zip_path)),
            }
            if timestamp is not None:
                headers["Last-Modified"] = formatdate(timestamp, usegmt=True)
        except Exception as exc:
            cleanup_temp_file(zip_path, "batch zip metadata failure")
            raise HTTPException(status_code=500, detail="Zip download could not be prepared.") from exc
        try:
            record_audit(
                audit,
                request,
                principal,
                action="files_downloaded",
                target_type="file_batch",
                metadata={
                    "count": len(entries),
                    "requested_count": len(requested_ids),
                    "mode": "zip",
                },
            )
        except HTTPException:
            cleanup_temp_file(zip_path, "batch zip audit failure")
            raise
        return FileResponse(
            zip_path,
            media_type="application/zip",
            headers=headers,
            background=BackgroundTask(lambda: cleanup_temp_file(zip_path, "batch zip response cleanup")),
        )

    @app.put("/api/admin/files/{file_id}/permissions")
    async def update_file_permissions(
        file_id: str,
        payload: FilePermissionPayload,
        request: Request,
        principal: Principal = Depends(require_admin),
    ) -> dict[str, object]:
        with storage.manifest_transaction():
            try:
                previous = storage.get_entry(file_id)
                groups = clean_allowed_groups(auth, payload.allowed_groups, [GROUP_DEFAULT])
                updated = storage.update_entry(file_id, {"allowed_groups": groups})
            except AuthError as exc:
                raise auth_error_response(exc) from exc
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="File not found.") from exc
            try:
                record_audit(
                    audit,
                    request,
                    principal,
                    action="file_permissions_updated",
                    target_type="file",
                    target_id=updated["id"],
                    target_name=updated.get("relative_path") or updated.get("original_filename"),
                    metadata={
                        "previous_groups": entry_allowed_groups(previous),
                        "new_groups": groups,
                    },
                )
            except HTTPException:
                try:
                    storage.update_entry(file_id, {"allowed_groups": entry_allowed_groups(previous)})
                except Exception:
                    LOGGER.exception("Failed to roll back file permission update after audit write failure: %s", file_id)
                raise
        return {"ok": True, "file": serialize_entry(updated, principal)}

    @app.delete("/api/files/{file_id}")
    async def delete_file(
        file_id: str,
        request: Request,
        principal: Principal = Depends(require_login),
    ) -> dict[str, object]:
        prepared_delete = None
        try:
            entry = storage.get_entry(file_id)
            if not can_delete_entry(entry, principal):
                raise HTTPException(status_code=403, detail="You can only delete files you uploaded.")
            prepared_delete = storage.prepare_delete_entry(file_id)
            if not can_delete_entry(prepared_delete.entry, principal):
                try:
                    storage.rollback_prepared_delete(prepared_delete)
                except Exception as rollback_exc:
                    LOGGER.exception("Failed to roll back file delete after stale authorization check: %s", file_id)
                    raise HTTPException(
                        status_code=409,
                        detail="File could not be deleted due to a filesystem error.",
                    ) from rollback_exc
                raise HTTPException(status_code=403, detail="You can only delete files you uploaded.")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="File not found.") from exc
        except UnsafePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            LOGGER.exception("File delete failed due to an OS error")
            raise HTTPException(status_code=409, detail="File could not be deleted due to a filesystem error.") from exc
        try:
            record_audit(
                audit,
                request,
                principal,
                action="file_deleted",
                target_type="file",
                target_id=prepared_delete.entry["id"],
                target_name=prepared_delete.entry.get("relative_path") or prepared_delete.entry.get("original_filename"),
                metadata={
                    "size": prepared_delete.entry.get("file_size"),
                    "sha256": prepared_delete.entry.get("sha256"),
                    "owner": prepared_delete.entry.get("owner_username"),
                    "allowed_groups": entry_allowed_groups(prepared_delete.entry),
                },
            )
        except HTTPException:
            try:
                storage.rollback_prepared_delete(prepared_delete)
            except Exception:
                LOGGER.exception("Failed to roll back file delete after audit write failure: %s", file_id)
            raise
        try:
            removed = storage.commit_prepared_delete(prepared_delete)
        except OSError as exc:
            LOGGER.exception("File delete failed due to an OS error")
            try:
                record_audit(
                    audit,
                    request,
                    principal,
                    action="file_delete_rolled_back",
                    target_type="file",
                    target_id=prepared_delete.entry["id"],
                    target_name=prepared_delete.entry.get("relative_path")
                    or prepared_delete.entry.get("original_filename"),
                    metadata={
                        "reason": "commit_failed",
                        "size": prepared_delete.entry.get("file_size"),
                        "sha256": prepared_delete.entry.get("sha256"),
                    },
                )
            except HTTPException:
                LOGGER.exception("Failed to write file delete rollback audit event: %s", file_id)
            raise HTTPException(status_code=409, detail="File could not be deleted due to a filesystem error.") from exc
        return {"ok": True, "file": serialize_entry(removed, principal)}

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"detail": "Invalid request."}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled_error(_: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception("Unhandled API error")
        return JSONResponse({"detail": "Internal server error."}, status_code=500)

    return app
