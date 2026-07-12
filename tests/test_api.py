from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import io
import json
import threading
import zipfile
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi import Request
from fastapi.responses import JSONResponse

from lan_transfer.api import cleanup_temp_file, content_disposition, create_app
from lan_transfer.auth import AuthError, DEFAULT_PASSWORD
from lan_transfer.config import AppConfig
from lan_transfer.storage import zip_datetime


def make_client(tmp_path: Path) -> TestClient:
    config = AppConfig(
        host="127.0.0.1",
        port=9876,
        save_dir=tmp_path,
    )
    return TestClient(create_app(config))


def login(client: TestClient, username: str, password: str = DEFAULT_PASSWORD, admin: bool = False) -> dict[str, object]:
    path = "/api/admin/login" if admin else "/api/login"
    response = client.post(path, json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def session_headers(session: dict[str, object], admin: bool = False) -> dict[str, str]:
    header = "X-Admin-Session" if admin else "X-User-Session"
    return {header: str(session["session_token"])}


def admin_headers(client: TestClient) -> dict[str, str]:
    return session_headers(login(client, "admin", admin=True), admin=True)


def test_content_disposition_sanitizes_fallback_and_percent_encodes_filename_star() -> None:
    header = content_disposition('reports/Q2 "final";表.csv')

    assert 'filename="reports_Q2 _final___.csv"' in header
    assert "filename*=UTF-8''reports%2FQ2%20%22final%22%3B%E8%A1%A8.csv" in header
    assert "reports/Q2" not in header


def create_group(client: TestClient, headers: dict[str, str], group_id: str) -> None:
    response = client.post("/api/admin/groups", headers=headers, json={"id": group_id, "name": group_id})
    assert response.status_code == 200, response.text


def create_user(client: TestClient, headers: dict[str, str], username: str, groups: list[str]) -> None:
    response = client.post(
        "/api/admin/users",
        headers=headers,
        json={"username": username, "groups": groups},
    )
    assert response.status_code == 200, response.text


def upload_sample(
    client: TestClient,
    content: bytes,
    mtime_ms: int,
    headers: dict[str, str],
    filename: str = "photo.jpg",
):
    return client.post(
        "/api/upload",
        headers=headers,
        files={"file": (filename, content, "image/jpeg")},
        data={
            "relative_path": f"Camera Roll/{filename}",
            "last_modified_ms": str(mtime_ms),
            "size": str(len(content)),
        },
    )


def test_guest_page_has_login_and_guest_cannot_write(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    user_page = client.get("/")
    assert user_page.status_code == 200
    assert "loginForm" in user_page.text
    assert "/static/user.js" in user_page.text

    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["role"] == "guest"
    assert status.json()["can_upload"] is False
    assert status.json()["save_dir"] is None
    assert "default_password" not in status.json()

    listed = client.get("/api/files")
    assert listed.status_code == 200
    assert listed.json()["files"] == []

    denied = client.post(
        "/api/upload",
        files={"file": ("blocked.txt", b"blocked", "text/plain")},
        data={"relative_path": "blocked.txt", "last_modified_ms": "0", "size": "7"},
    )
    assert denied.status_code == 403

    admin = admin_headers(client)
    signed_in_status = client.get("/api/status", headers=admin)
    assert signed_in_status.json()["save_dir"] == str(tmp_path)
    admin_status = client.get("/api/admin/status")
    assert "default_password" not in admin_status.json()


def test_validation_errors_do_not_echo_sensitive_request_body(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/login",
        json={"username": "admin", "password": {"nested": "secret-in-invalid-body"}},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request."}
    assert "secret-in-invalid-body" not in response.text


def test_default_admin_can_login_and_manage_accounts_and_groups(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    session = login(client, "admin", admin=True)
    headers = session_headers(session, admin=True)

    admin_session = client.get("/api/admin/session", headers=headers)
    assert admin_session.status_code == 200
    assert admin_session.json()["user"]["role"] == "admin"

    groups = client.get("/api/admin/groups", headers=headers).json()["groups"]
    assert {group["id"] for group in groups} >= {"public", "everyone"}

    create_group(client, headers, "team-a")
    create_user(client, headers, "alice", ["team-a"])

    users = client.get("/api/admin/users", headers=headers).json()["users"]
    alice = next(user for user in users if user["username"] == "alice")
    assert alice["groups"] == ["team-a"]

    alice_login = client.post("/api/login", json={"username": "alice", "password": DEFAULT_PASSWORD})
    assert alice_login.status_code == 200


def test_role_change_invalidates_old_user_session_before_admin_access(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    alice = session_headers(login(client, "alice"))

    updated = client.put("/api/admin/users/alice", headers=admin, json={"role": "admin"})
    assert updated.status_code == 200, updated.text

    denied = client.get("/api/admin/users", headers=alice)
    assert denied.status_code == 403


def test_auth_audit_rollback_does_not_clobber_concurrent_auth_write(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    original_record = client.app.state.audit.record
    bob_finished = threading.Event()
    bob_errors: list[Exception] = []
    blocked_during_audit: list[bool] = []

    def create_bob() -> None:
        try:
            client.app.state.auth.create_user("bob")
        except Exception as exc:  # pragma: no cover - surfaced by assertion below
            bob_errors.append(exc)
        finally:
            bob_finished.set()

    def fail_alice_audit(*args, **kwargs):
        if kwargs.get("action") == "user_created" and kwargs.get("target_id") == "alice":
            thread = threading.Thread(target=create_bob)
            thread.start()
            blocked_during_audit.append(not bob_finished.wait(0.05))
            raise OSError("audit disk full")
        return original_record(*args, **kwargs)

    with patch.object(client.app.state.audit, "record", side_effect=fail_alice_audit):
        created = client.post("/api/admin/users", headers=admin, json={"username": "alice"})

    assert created.status_code == 500
    assert bob_finished.wait(5) is True
    assert blocked_during_audit == [True]
    assert bob_errors == []
    users = {user["username"] for user in client.app.state.auth.list_users()}
    assert "alice" not in users
    assert "bob" in users


def test_user_delete_waiting_for_manifest_lock_does_not_block_auth_writes(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    delete_finished = threading.Event()
    bob_finished = threading.Event()
    delete_result: list[int] = []
    bob_errors: list[Exception] = []

    def delete_alice() -> None:
        response = client.delete("/api/admin/users/alice", headers=admin)
        delete_result.append(response.status_code)
        delete_finished.set()

    def create_bob() -> None:
        try:
            client.app.state.auth.create_user("bob")
        except Exception as exc:  # pragma: no cover - surfaced by assertion below
            bob_errors.append(exc)
        finally:
            bob_finished.set()

    with client.app.state.storage.manifest_transaction():
        delete_thread = threading.Thread(target=delete_alice)
        delete_thread.start()
        assert delete_finished.wait(0.05) is False
        bob_thread = threading.Thread(target=create_bob)
        bob_thread.start()
        assert bob_finished.wait(5) is True

    assert delete_finished.wait(5) is True
    delete_thread.join(timeout=1)
    bob_thread.join(timeout=1)
    assert delete_result == [200]
    assert bob_errors == []
    assert "bob" in {user["username"] for user in client.app.state.auth.list_users()}


def test_non_admin_admin_login_does_not_create_session(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    create_user(client, headers, "alice", ["everyone"])

    denied = client.post("/api/admin/login", json={"username": "alice", "password": DEFAULT_PASSWORD})
    assert denied.status_code == 403
    auth = client.app.state.auth
    assert len(auth._sessions) == 1


def test_disabled_user_login_hides_status_until_password_is_valid(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])

    disabled = client.put("/api/admin/users/alice", headers=admin, json={"active": False})
    assert disabled.status_code == 200, disabled.text

    wrong = client.post("/api/login", json={"username": "alice", "password": "wrong-password"})
    assert wrong.status_code == 400
    assert wrong.json()["detail"] == "Invalid username or password."

    correct = client.post("/api/login", json={"username": "alice", "password": DEFAULT_PASSWORD})
    assert correct.status_code == 400
    assert correct.json()["detail"] == "Account is disabled."

    for _ in range(3):
        response = client.post("/api/login", json={"username": "alice", "password": "wrong-password"})
        assert response.status_code == 400

    locked = client.post("/api/login", json={"username": "alice", "password": "wrong-password"})
    assert locked.status_code == 423
    assert locked.json()["detail"]["locked_until"] > 0


def test_admin_cannot_enter_user_session_or_user_login(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    denied_login = client.post("/api/login", json={"username": "admin", "password": DEFAULT_PASSWORD})
    assert denied_login.status_code == 403
    assert client.app.state.auth._sessions == {}

    admin_session = login(client, "admin", admin=True)
    admin = session_headers(admin_session, admin=True)

    assert client.get("/api/session", headers=admin).status_code == 403
    assert client.get("/api/session").status_code == 403
    assert client.get("/api/admin/session", headers=admin).status_code == 200


def test_admin_cannot_use_user_logout_endpoint(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin_session = login(client, "admin", admin=True)
    admin = session_headers(admin_session, admin=True)

    denied_logout = client.post("/api/logout", headers=admin)

    assert denied_logout.status_code == 403
    assert client.get("/api/admin/session", headers=admin).status_code == 200


def test_user_cannot_use_admin_logout_endpoint(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    alice = session_headers(login(client, "alice"))

    denied_logout = client.post("/api/admin/logout", headers=alice)

    assert denied_logout.status_code == 403
    assert client.get("/api/session", headers=alice).status_code == 200


def test_admin_setup_endpoint_is_disabled_after_default_accounts_exist(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    setup = client.post("/api/admin/setup", json={"password": "attacker-pass"})
    assert setup.status_code == 403
    assert client.post("/api/admin/login", json={"username": "admin", "password": DEFAULT_PASSWORD}).status_code == 200
    assert client.post("/api/admin/login", json={"username": "admin", "password": "attacker-pass"}).status_code == 400


def test_legacy_default_group_is_migrated_to_everyone(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)

    auth_path = tmp_path / ".lan-transfer-auth.json"
    settings = json.loads(auth_path.read_text(encoding="utf-8"))
    settings["groups"]["default"] = settings["groups"].pop("everyone")
    settings["groups"]["default"]["id"] = "default"
    settings["users"]["admin"]["groups"] = ["default"]
    auth_path.write_text(json.dumps(settings), encoding="utf-8")

    file_path = tmp_path / "legacy.txt"
    file_path.write_bytes(b"legacy")
    manifest = {
        "version": 1,
        "files": [
            {
                "id": "legacy-file",
                "original_filename": "legacy.txt",
                "saved_filename": "legacy.txt",
                "file_size": 6,
                "sha256": hashlib.sha256(b"legacy").hexdigest(),
                "server_mtime": file_path.stat().st_mtime,
                "uploaded_at": "2024-01-02T03:04:06+00:00",
                "relative_path": "legacy.txt",
                "saved_relative_path": "legacy.txt",
                "owner_username": "admin",
                "owner_display_name": "Admin",
                "allowed_groups": ["default"],
            }
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    migrated_client = make_client(tmp_path)
    migrated_headers = admin_headers(migrated_client)
    groups = migrated_client.get("/api/admin/groups", headers=migrated_headers).json()["groups"]
    assert "everyone" in {group["id"] for group in groups}
    assert "default" not in {group["id"] for group in groups}
    session = migrated_client.get("/api/admin/session", headers=migrated_headers).json()["user"]
    assert session["groups"] == ["everyone", "public"]
    files = migrated_client.get("/api/files", headers=migrated_headers).json()["files"]
    assert files[0]["allowed_groups"] == ["everyone"]


def test_manifest_without_allowed_groups_fails_closed_to_signed_in_users(tmp_path: Path) -> None:
    file_path = tmp_path / "legacy-private.txt"
    file_path.write_bytes(b"legacy private")
    manifest = {
        "version": 1,
        "files": [
            {
                "id": "legacy-private",
                "original_filename": "legacy-private.txt",
                "saved_filename": "legacy-private.txt",
                "file_size": len(b"legacy private"),
                "sha256": hashlib.sha256(b"legacy private").hexdigest(),
                "server_mtime": file_path.stat().st_mtime,
                "uploaded_at": "2024-01-02T03:04:06+00:00",
                "relative_path": "legacy-private.txt",
                "saved_relative_path": "legacy-private.txt",
                "owner_username": "admin",
                "owner_display_name": "Admin",
            }
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    client = make_client(tmp_path)
    admin = admin_headers(client)

    client.cookies.clear()
    guest_files = client.get("/api/files").json()["files"]
    assert guest_files == []
    assert client.get("/api/files/legacy-private/download").status_code == 404

    admin_files = client.get("/api/files", headers=admin).json()["files"]
    assert admin_files[0]["allowed_groups"] == ["everyone"]
    admin_download = client.get("/api/files/legacy-private/download", headers=admin)
    assert admin_download.status_code == 200
    assert admin_download.content == b"legacy private"


def test_admin_can_batch_create_accounts_atomically(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    create_group(client, headers, "batch")

    response = client.post(
        "/api/admin/users/batch",
        headers=headers,
        json={
            "users": [
                {"username": "u1", "groups": ["batch"]},
                {"username": "u2", "password": "custom-pass", "display_name": "User Two", "groups": ["batch"]},
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["count"] == 2
    assert client.post("/api/login", json={"username": "u1", "password": DEFAULT_PASSWORD}).status_code == 200
    assert client.post("/api/login", json={"username": "u2", "password": "custom-pass"}).status_code == 200

    duplicate = client.post(
        "/api/admin/users/batch",
        headers=headers,
        json={"users": [{"username": "u3"}, {"username": "u3"}]},
    )
    assert duplicate.status_code == 400
    users = client.get("/api/admin/users", headers=headers).json()["users"]
    assert "u3" not in {user["username"] for user in users}


def test_admin_batch_create_rejects_admin_roles(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)

    response = client.post(
        "/api/admin/users/batch",
        headers=headers,
        json={"users": [{"username": "batch-admin", "role": "admin"}]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Batch can only create user accounts."
    assert client.post("/api/admin/login", json={"username": "batch-admin", "password": DEFAULT_PASSWORD}).status_code == 400


def test_admin_batch_create_has_reasonable_limit(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    payload = {"users": [{"username": f"user{i}"} for i in range(201)]}

    response = client.post("/api/admin/users/batch", headers=headers, json=payload)

    assert response.status_code == 400
    assert "at most 200" in response.json()["detail"]


def test_admin_audit_logs_state_changes_without_passwords(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.get("/api/admin/audit").status_code == 403
    admin = admin_headers(client)

    create_group(client, admin, "audit-team")
    response = client.post(
        "/api/admin/users",
        headers=admin,
        json={"username": "audited", "password": "secret-pass", "groups": ["audit-team"]},
    )
    assert response.status_code == 200, response.text
    user_headers = session_headers(login(client, "audited", "secret-pass"))
    mtime_ms = int(datetime(2024, 1, 2, 3, 4, 6).timestamp() * 1000)
    uploaded = upload_sample(client, b"audit bytes", mtime_ms, user_headers).json()["file"]
    downloaded = client.get(f"/api/files/{uploaded['id']}/download", headers=user_headers)
    assert downloaded.status_code == 200
    deleted = client.delete(f"/api/files/{uploaded['id']}", headers=user_headers)
    assert deleted.status_code == 200, deleted.text

    audit = client.get("/api/admin/audit?limit=20", headers=admin)
    assert audit.status_code == 200, audit.text
    events = audit.json()["events"]
    actions = [event["action"] for event in events]
    assert "file_deleted" in actions
    assert "file_downloaded" in actions
    assert "file_uploaded" in actions
    assert "user_logged_in" in actions
    assert "user_created" in actions
    assert "group_created" in actions
    assert "admin_logged_in" in actions

    audit_text = (tmp_path / ".lan-transfer-audit.jsonl").read_text(encoding="utf-8")
    assert "secret-pass" not in audit_text
    assert uploaded["sha256"] in audit_text


def test_required_audit_failure_does_not_return_success(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)

    with patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")):
        response = upload_sample(client, b"audit required", 0, headers)

    assert response.status_code == 500
    assert response.json()["detail"] == "Audit log write failed."
    assert client.app.state.storage.list_files() == []
    assert not (tmp_path / "Camera Roll" / "photo.jpg").exists()


def test_permission_audit_failure_rolls_back_visibility_change(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    create_group(client, headers, "private")
    uploaded = upload_sample(client, b"visible", 0, headers).json()["file"]

    with patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")):
        response = client.put(
            f"/api/admin/files/{uploaded['id']}/permissions",
            headers=headers,
            json={"allowed_groups": ["private"]},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Audit log write failed."
    restored = client.app.state.storage.get_entry(uploaded["id"])
    assert restored["allowed_groups"] == ["everyone"]


def test_login_audit_failure_does_not_leave_session(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])

    with (
        patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")),
        patch.object(client.app.state.auth, "_write_settings", side_effect=OSError("settings disk full")),
    ):
        response = client.post("/api/login", json={"username": "alice", "password": DEFAULT_PASSWORD})

    assert response.status_code == 500
    assert response.json()["detail"] == "Audit log write failed."
    assert all(session.username != "alice" for session in client.app.state.auth._sessions.values())
    assert client.post("/api/login", json={"username": "alice", "password": DEFAULT_PASSWORD}).status_code == 200


def test_logout_audit_failure_restores_session(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    headers = session_headers(login(client, "alice"))

    with patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")):
        response = client.post("/api/logout", headers=headers)

    assert response.status_code == 500
    assert response.json()["detail"] == "Audit log write failed."
    assert client.get("/api/session", headers=headers).status_code == 200


def test_password_audit_failure_rolls_back_password_and_session(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    alice = session_headers(login(client, "alice"))

    with patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")):
        changed = client.post(
            "/api/password",
            headers=alice,
            json={"current_password": DEFAULT_PASSWORD, "new_password": "new-secret-pass"},
        )

    assert changed.status_code == 500
    assert changed.json()["detail"] == "Audit log write failed."
    assert client.get("/api/session", headers=alice).status_code == 200
    assert client.post("/api/login", json={"username": "alice", "password": DEFAULT_PASSWORD}).status_code == 200
    assert client.post("/api/login", json={"username": "alice", "password": "new-secret-pass"}).status_code == 400


def test_admin_password_reset_invalidates_existing_user_session(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    alice = session_headers(login(client, "alice"))

    changed = client.put(
        "/api/admin/users/alice",
        headers=admin,
        json={"password": "reset-secret-pass"},
    )

    assert changed.status_code == 200, changed.text
    assert client.get("/api/session", headers=alice).status_code == 403
    assert client.post("/api/login", json={"username": "alice", "password": DEFAULT_PASSWORD}).status_code == 400
    assert client.post("/api/login", json={"username": "alice", "password": "reset-secret-pass"}).status_code == 200


def test_admin_password_reset_audit_failure_restores_password_and_session(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    alice = session_headers(login(client, "alice"))

    with patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")):
        changed = client.put(
            "/api/admin/users/alice",
            headers=admin,
            json={"password": "reset-secret-pass"},
        )

    assert changed.status_code == 500
    assert changed.json()["detail"] == "Audit log write failed."
    assert client.get("/api/session", headers=alice).status_code == 200
    assert client.post("/api/login", json={"username": "alice", "password": DEFAULT_PASSWORD}).status_code == 200
    assert client.post("/api/login", json={"username": "alice", "password": "reset-secret-pass"}).status_code == 400


def test_admin_user_audit_failure_rolls_back_auth_mutations(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)

    with patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")):
        created = client.post("/api/admin/users", headers=admin, json={"username": "rollback-create"})

    assert created.status_code == 500
    assert client.post("/api/login", json={"username": "rollback-create", "password": DEFAULT_PASSWORD}).status_code == 400

    with patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")):
        batch = client.post(
            "/api/admin/users/batch",
            headers=admin,
            json={"users": [{"username": "rollback-batch-a"}, {"username": "rollback-batch-b"}]},
        )

    assert batch.status_code == 500
    assert client.post("/api/login", json={"username": "rollback-batch-a", "password": DEFAULT_PASSWORD}).status_code == 400
    assert client.post("/api/login", json={"username": "rollback-batch-b", "password": DEFAULT_PASSWORD}).status_code == 400

    create_user(client, admin, "alice", ["everyone"])
    alice = session_headers(login(client, "alice"))
    with patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")):
        updated = client.put("/api/admin/users/alice", headers=admin, json={"active": False, "display_name": "Blocked"})

    assert updated.status_code == 500
    assert client.get("/api/session", headers=alice).status_code == 200
    alice_record = client.app.state.auth.get_user("alice")
    assert alice_record["active"] is True
    assert alice_record["display_name"] == "alice"


def test_admin_group_audit_failure_rolls_back_auth_mutations(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)

    with patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")):
        created = client.post("/api/admin/groups", headers=admin, json={"id": "rollback-group"})

    assert created.status_code == 500
    groups = {group["id"] for group in client.get("/api/admin/groups", headers=admin).json()["groups"]}
    assert "rollback-group" not in groups

    create_group(client, admin, "keep-group")
    with patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")):
        deleted = client.delete("/api/admin/groups/keep-group", headers=admin)

    assert deleted.status_code == 500
    groups = {group["id"] for group in client.get("/api/admin/groups", headers=admin).json()["groups"]}
    assert "keep-group" in groups


def test_delete_user_audit_failure_rolls_back_account_and_file_owner(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    alice = session_headers(login(client, "alice"))
    uploaded = upload_sample(client, b"alice file", 0, alice).json()["file"]

    with patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")):
        deleted = client.delete("/api/admin/users/alice", headers=admin)

    assert deleted.status_code == 500
    assert deleted.json()["detail"] == "Audit log write failed."
    assert client.post("/api/login", json={"username": "alice", "password": DEFAULT_PASSWORD}).status_code == 200
    restored = client.app.state.storage.get_entry(uploaded["id"])
    assert restored["owner_username"] == "alice"


def test_delete_user_audit_failure_with_auth_rollback_failure_keeps_files_with_admin(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    alice = session_headers(login(client, "alice"))
    uploaded = upload_sample(client, b"alice file", 0, alice).json()["file"]

    with (
        patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")),
        patch.object(client.app.state.auth, "restore_state", side_effect=OSError("settings disk full")),
    ):
        deleted = client.delete("/api/admin/users/alice", headers=admin)

    assert deleted.status_code == 500
    assert client.post("/api/login", json={"username": "alice", "password": DEFAULT_PASSWORD}).status_code == 400
    retained = client.app.state.storage.get_entry(uploaded["id"])
    assert retained["owner_username"] == "admin"

    create_user(client, admin, "alice", ["everyone"])
    new_alice = session_headers(login(client, "alice"))
    listed = client.get("/api/files", headers=new_alice).json()["files"]
    visible_file = next(file for file in listed if file["id"] == uploaded["id"])
    assert visible_file["owner_username"] == "admin"
    assert visible_file["can_delete"] is False


def test_delete_file_audit_failure_rolls_back_file_and_manifest(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    uploaded = upload_sample(client, b"keep after audit failure", 0, headers).json()["file"]
    saved_path = tmp_path / "Camera Roll" / "photo.jpg"

    with patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")):
        deleted = client.delete(f"/api/files/{uploaded['id']}", headers=headers)

    assert deleted.status_code == 500
    assert deleted.json()["detail"] == "Audit log write failed."
    assert saved_path.read_bytes() == b"keep after audit failure"
    listed = client.get("/api/files", headers=headers).json()["files"]
    assert uploaded["id"] in {file["id"] for file in listed}


def test_admin_can_delete_user_and_reassign_owned_files(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    alice = session_headers(login(client, "alice"))

    mtime_ms = int(datetime(2024, 1, 2, 3, 4, 6).timestamp() * 1000)
    uploaded = upload_sample(client, b"alice file", mtime_ms, alice).json()["file"]

    deleted = client.delete("/api/admin/users/alice", headers=admin)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["reassigned_files"] == 1
    assert client.post("/api/login", json={"username": "alice", "password": DEFAULT_PASSWORD}).status_code == 400

    create_user(client, admin, "alice", ["everyone"])
    new_alice = session_headers(login(client, "alice"))
    files = client.get("/api/files", headers=admin).json()["files"]
    reowned = next(file for file in files if file["id"] == uploaded["id"])
    assert reowned["owner_username"] == "admin"
    assert client.delete(f"/api/files/{uploaded['id']}", headers=new_alice).status_code == 403


def test_delete_user_rolls_back_file_reassignment_when_account_delete_fails(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    alice = session_headers(login(client, "alice"))
    uploaded = upload_sample(client, b"alice file", 0, alice).json()["file"]

    with patch.object(client.app.state.auth, "delete_user", side_effect=AuthError("settings write failed")):
        deleted = client.delete("/api/admin/users/alice", headers=admin)

    assert deleted.status_code == 400
    assert deleted.json()["detail"] == "settings write failed"
    files = client.get("/api/files", headers=admin).json()["files"]
    restored = next(file for file in files if file["id"] == uploaded["id"])
    assert restored["owner_username"] == "alice"
    assert client.post("/api/login", json={"username": "alice", "password": DEFAULT_PASSWORD}).status_code == 200


def test_delete_user_reassigns_file_owned_during_delete_window(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    late_owned = upload_sample(client, b"late owner", 0, admin, filename="late-owner.jpg").json()["file"]
    original_delete_user = client.app.state.auth.delete_user

    def delete_user_then_late_owner(username: str):
        removed = original_delete_user(username)
        client.app.state.storage.update_entry(
            late_owned["id"],
            {"owner_username": username, "owner_display_name": username},
        )
        return removed

    with patch.object(client.app.state.auth, "delete_user", side_effect=delete_user_then_late_owner):
        deleted = client.delete("/api/admin/users/alice", headers=admin)

    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["reassigned_files"] == 1
    retained = client.app.state.storage.get_entry(late_owned["id"])
    assert retained["owner_username"] == "admin"


def test_admin_can_delete_unused_groups_and_blocks_protected_or_used_groups(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)

    unused = client.post("/api/admin/groups", headers=admin, json={"id": "unused", "name": "Unused"})
    assert unused.status_code == 200
    deleted = client.delete("/api/admin/groups/unused", headers=admin)
    assert deleted.status_code == 200
    groups = client.get("/api/admin/groups", headers=admin).json()["groups"]
    assert "unused" not in {group["id"] for group in groups}

    assert client.delete("/api/admin/groups/public", headers=admin).status_code == 400
    assert client.delete("/api/admin/groups/everyone", headers=admin).status_code == 400
    assert client.delete("/api/admin/groups/default", headers=admin).status_code == 400

    create_group(client, admin, "team-a")
    create_user(client, admin, "alice", ["team-a"])
    used_by_user = client.delete("/api/admin/groups/team-a", headers=admin)
    assert used_by_user.status_code == 409

    create_group(client, admin, "files-only")
    mtime_ms = int(datetime(2024, 1, 2, 3, 4, 6).timestamp() * 1000)
    uploaded = upload_sample(client, b"admin file", mtime_ms, admin).json()["file"]
    changed = client.put(
        f"/api/admin/files/{uploaded['id']}/permissions",
        headers=admin,
        json={"allowed_groups": ["files-only"]},
    )
    assert changed.status_code == 200
    used_by_file = client.delete("/api/admin/groups/files-only", headers=admin)
    assert used_by_file.status_code == 409


def test_delete_group_rechecks_file_usage_after_delete_window(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_group(client, admin, "late-group")
    uploaded = upload_sample(client, b"group race", 0, admin, filename="group-race.jpg").json()["file"]
    original_delete_group = client.app.state.auth.delete_group

    def delete_group_then_late_file(group_id: str):
        group = original_delete_group(group_id)
        client.app.state.storage.update_entry(uploaded["id"], {"allowed_groups": ["late-group"]})
        return group

    with patch.object(client.app.state.auth, "delete_group", side_effect=delete_group_then_late_file):
        deleted = client.delete("/api/admin/groups/late-group", headers=admin)

    assert deleted.status_code == 409
    assert deleted.json()["detail"]["message"] == "Group is still in use."
    groups = {group["id"] for group in client.get("/api/admin/groups", headers=admin).json()["groups"]}
    assert "late-group" in groups


def test_delete_group_recheck_restore_failure_reports_server_error(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_group(client, admin, "late-group")
    uploaded = upload_sample(client, b"group race", 0, admin, filename="group-race.jpg").json()["file"]
    original_delete_group = client.app.state.auth.delete_group

    def delete_group_then_late_file(group_id: str):
        group = original_delete_group(group_id)
        client.app.state.storage.update_entry(uploaded["id"], {"allowed_groups": ["late-group"]})
        return group

    with (
        patch.object(client.app.state.auth, "delete_group", side_effect=delete_group_then_late_file),
        patch.object(client.app.state.auth, "restore_state", side_effect=OSError("settings disk full")),
    ):
        deleted = client.delete("/api/admin/groups/late-group", headers=admin)

    assert deleted.status_code == 500
    assert deleted.json()["detail"] == "Could not restore group after reference check failed."


def test_user_uploads_deletes_own_files_and_cannot_delete_others(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    create_user(client, admin, "bob", ["everyone"])
    alice = session_headers(login(client, "alice"))
    bob = session_headers(login(client, "bob"))

    mtime_ms = int(datetime(2024, 1, 2, 3, 4, 6).timestamp() * 1000)
    uploaded = upload_sample(client, b"alice file", mtime_ms, alice).json()["file"]
    assert uploaded["owner_username"] == "alice"
    assert uploaded["can_delete"] is True

    bob_delete = client.delete(f"/api/files/{uploaded['id']}", headers=bob)
    assert bob_delete.status_code == 403

    alice_delete = client.delete(f"/api/files/{uploaded['id']}", headers=alice)
    assert alice_delete.status_code == 200


def test_delete_file_reports_conflict_when_disk_delete_fails(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    mtime_ms = int(datetime(2024, 1, 2, 3, 4, 6).timestamp() * 1000)
    uploaded = upload_sample(client, b"locked", mtime_ms, headers).json()["file"]

    with patch.object(Path, "unlink", side_effect=PermissionError("locked")):
        deleted = client.delete(f"/api/files/{uploaded['id']}", headers=headers)

    assert deleted.status_code == 409
    assert deleted.json()["detail"] == "File could not be deleted due to a filesystem error."
    assert "locked" not in deleted.text
    listed = client.get("/api/files", headers=headers).json()["files"]
    assert uploaded["id"] in {file["id"] for file in listed}
    assert (tmp_path / "Camera Roll" / "photo.jpg").read_bytes() == b"locked"
    rollback_events = [
        event
        for event in client.app.state.audit.recent(20)
        if event["target_id"] == uploaded["id"] and event["action"] == "file_delete_rolled_back"
    ]
    assert rollback_events
    assert rollback_events[0]["metadata"]["reason"] == "commit_failed"


def test_delete_file_rechecks_permission_after_prepare(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    alice = session_headers(login(client, "alice"))
    uploaded = upload_sample(client, b"alice file", 0, alice).json()["file"]
    storage = client.app.state.storage
    original_prepare = storage.prepare_delete_entry

    def reassign_before_prepare(file_id: str):
        storage.update_entry(file_id, {"owner_username": "admin", "owner_display_name": "admin"})
        return original_prepare(file_id)

    with patch.object(storage, "prepare_delete_entry", side_effect=reassign_before_prepare):
        deleted = client.delete(f"/api/files/{uploaded['id']}", headers=alice)

    assert deleted.status_code == 403
    restored = storage.get_entry(uploaded["id"])
    assert restored["owner_username"] == "admin"
    assert (tmp_path / "Camera Roll" / "photo.jpg").read_bytes() == b"alice file"


def test_upload_audit_cleanup_failure_quarantines_file(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)

    with (
        patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")),
        patch.object(Path, "unlink", side_effect=PermissionError("locked")),
    ):
        response = upload_sample(client, b"unaudited", 0, headers)

    assert response.status_code == 500
    entries = client.app.state.storage.list_files()
    assert len(entries) == 1
    assert entries[0]["audit_status"] == "failed"
    listed = client.get("/api/files", headers=headers).json()["files"]
    assert entries[0]["id"] not in {file["id"] for file in listed}
    assert client.get(f"/api/files/{entries[0]['id']}/download", headers=headers).status_code == 404


def test_upload_publish_failure_does_not_write_success_audit(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    storage = client.app.state.storage
    original_update = storage.update_entry
    audit_actions: list[str] = []

    def fail_publish(file_id: str, updates: dict[str, object]):
        if updates == {"audit_status": "complete"}:
            raise OSError("manifest write failed")
        return original_update(file_id, updates)

    def record_audit(*args, **kwargs):
        audit_actions.append(str(kwargs.get("action")))
        return client.app.state.audit.__class__.record(client.app.state.audit, *args, **kwargs)

    with (
        patch.object(storage, "update_entry", side_effect=fail_publish),
        patch.object(client.app.state.audit, "record", side_effect=record_audit),
    ):
        response = upload_sample(client, b"publish failed", 0, headers, filename="publish.txt")

    assert response.status_code == 500
    assert response.json()["detail"] == "Upload could not be published."
    assert "file_uploaded" not in audit_actions
    assert all(entry.get("original_filename") != "publish.txt" for entry in storage.list_files())


def test_upload_filesystem_error_does_not_echo_internal_path_and_rolls_back(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    storage = client.app.state.storage

    with patch.object(storage, "_write_manifest", side_effect=OSError("secret path C:/private/manifest.json")):
        response = client.post(
            "/api/upload",
            headers=headers,
            files={"file": ("leak.bin", b"content", "application/octet-stream")},
            data={"relative_path": "leak.bin", "last_modified_ms": "0", "size": "7"},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Upload failed due to a filesystem error."
    assert "secret path" not in response.text
    assert storage.list_files() == []
    assert not (tmp_path / "leak.bin").exists()
    assert not list(tmp_path.glob("*.part"))


def test_upload_revalidates_owner_before_manifest_commit(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    alice = session_headers(login(client, "alice"))

    with patch.object(client.app.state.auth, "get_user", side_effect=AuthError("Unknown account.")):
        response = client.post(
            "/api/upload",
            headers=alice,
            files={"file": ("late.bin", b"content", "application/octet-stream")},
            data={"relative_path": "late.bin", "last_modified_ms": "0", "size": "7"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown account."
    assert client.app.state.storage.list_files() == []
    assert not (tmp_path / "late.bin").exists()
    assert not list(tmp_path.glob("*.part"))


def test_session_endpoint_refreshes_cookie_for_native_downloads(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    alice_session = login(client, "alice")
    alice = session_headers(alice_session)

    mtime_ms = int(datetime(2024, 1, 2, 3, 4, 6).timestamp() * 1000)
    uploaded = upload_sample(client, b"cookie refresh", mtime_ms, alice).json()["file"]

    client.cookies.clear()
    assert client.get(f"/api/files/{uploaded['id']}/download").status_code == 404

    session = client.get("/api/session", headers=alice)
    assert session.status_code == 200
    assert "lan_transfer_session=" in session.headers["set-cookie"]
    assert "session_token" not in session.json()
    refreshed_download = client.get(f"/api/files/{uploaded['id']}/download")
    assert refreshed_download.status_code == 200
    assert refreshed_download.content == b"cookie refresh"


def test_status_endpoint_refreshes_cookie_for_native_downloads(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    alice_session = login(client, "alice")
    alice = session_headers(alice_session)

    mtime_ms = int(datetime(2024, 1, 2, 3, 4, 6).timestamp() * 1000)
    uploaded = upload_sample(client, b"status cookie refresh", mtime_ms, alice).json()["file"]

    client.cookies.clear()
    assert client.get(f"/api/files/{uploaded['id']}/download").status_code == 404

    status = client.get("/api/status", headers=alice)
    assert status.status_code == 200
    assert status.json()["role"] == "user"
    assert "lan_transfer_session=" in status.headers["set-cookie"]
    assert "session_token" not in status.json()
    refreshed_download = client.get(f"/api/files/{uploaded['id']}/download")
    assert refreshed_download.status_code == 200
    assert refreshed_download.content == b"status cookie refresh"


def test_file_list_sort_and_search(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    old_ms = int(datetime(2024, 1, 1, 1, 1, 0).timestamp() * 1000)
    new_ms = int(datetime(2024, 1, 2, 1, 1, 0).timestamp() * 1000)

    small = upload_sample(client, b"1", old_ms, headers, filename="small.txt").json()["file"]
    large = upload_sample(client, b"123456789", new_ms, headers, filename="large.txt").json()["file"]

    by_size = client.get("/api/files?sort_by=size&sort_dir=desc", headers=headers).json()["files"]
    assert [item["id"] for item in by_size[:2]] == [large["id"], small["id"]]

    by_mtime = client.get("/api/files?sort_by=mtime&sort_dir=asc", headers=headers).json()["files"]
    assert [item["id"] for item in by_mtime[:2]] == [small["id"], large["id"]]

    searched = client.get("/api/files?search=large", headers=headers).json()["files"]
    assert [item["id"] for item in searched] == [large["id"]]


def test_file_list_sort_handles_corrupt_numeric_manifest_fields(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    good = upload_sample(client, b"123456", 0, headers, filename="good.txt").json()["file"]
    corrupt = upload_sample(client, b"1", 0, headers, filename="corrupt.txt").json()["file"]

    storage = client.app.state.storage
    for entry in storage._manifest["files"]:
        if entry["id"] == corrupt["id"]:
            entry["file_size"] = "not-a-number"
            entry["server_mtime"] = "not-a-time"

    by_size = client.get("/api/files?sort_by=size&sort_dir=asc", headers=headers)
    assert by_size.status_code == 200, by_size.text
    assert by_size.json()["files"][0]["id"] == corrupt["id"]

    by_mtime = client.get("/api/files?sort_by=mtime&sort_dir=desc", headers=headers)
    assert by_mtime.status_code == 200, by_mtime.text
    assert {item["id"] for item in by_mtime.json()["files"]} >= {good["id"], corrupt["id"]}


def test_group_visibility_controls_list_download_and_zip(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_group(client, admin, "team-a")
    create_group(client, admin, "team-b")
    create_user(client, admin, "alice", ["team-a"])
    create_user(client, admin, "bob", ["team-b"])
    alice = session_headers(login(client, "alice"))
    bob = session_headers(login(client, "bob"))

    content = b"group filtered content"
    mtime_ms = int(datetime(2024, 2, 3, 4, 5, 6).timestamp() * 1000)
    uploaded = upload_sample(client, content, mtime_ms, alice).json()["file"]
    assert uploaded["allowed_groups"] == ["team-a"]

    client.cookies.clear()
    guest_files = client.get("/api/files").json()["files"]
    assert uploaded["id"] not in {file["id"] for file in guest_files}

    bob_files = client.get("/api/files", headers=bob).json()["files"]
    assert uploaded["id"] not in {file["id"] for file in bob_files}
    assert client.get(f"/api/files/{uploaded['id']}/download", headers=bob).status_code == 404

    admin_files = client.get("/api/files", headers=admin).json()["files"]
    assert uploaded["id"] in {file["id"] for file in admin_files}

    changed = client.put(
        f"/api/admin/files/{uploaded['id']}/permissions",
        headers=admin,
        json={"allowed_groups": ["team-b"]},
    )
    assert changed.status_code == 200
    assert changed.json()["file"]["allowed_groups"] == ["team-b"]

    bob_download = client.get(f"/api/files/{uploaded['id']}/download", headers=bob)
    assert bob_download.status_code == 200
    assert bob_download.content == content

    bob_zip = client.get(f"/api/download.zip?ids={uploaded['id']}", headers=bob)
    assert bob_zip.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bob_zip.content), "r") as archive:
        assert archive.read("Camera Roll/photo.jpg") == content


def test_permission_update_is_not_visible_until_audit_succeeds(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_group(client, admin, "team-a")
    create_group(client, admin, "team-b")
    create_user(client, admin, "alice", ["team-a"])
    create_user(client, admin, "bob", ["team-b"])
    alice = session_headers(login(client, "alice"))
    bob = session_headers(login(client, "bob"))
    uploaded = upload_sample(client, b"permission audit", 0, alice, filename="permission.txt").json()["file"]
    original_record = client.app.state.audit.record
    bob_list_finished = threading.Event()
    blocked_during_audit: list[bool] = []
    bob_seen_after_audit: list[bool] = []

    def list_as_bob() -> None:
        files = client.get("/api/files", headers=bob).json()["files"]
        bob_seen_after_audit.append(uploaded["id"] in {file["id"] for file in files})
        bob_list_finished.set()

    def inspect_permission_audit_window(*args, **kwargs):
        if kwargs.get("action") == "file_permissions_updated":
            thread = threading.Thread(target=list_as_bob)
            thread.start()
            blocked_during_audit.append(not bob_list_finished.wait(0.05))
        return original_record(*args, **kwargs)

    with patch.object(client.app.state.audit, "record", side_effect=inspect_permission_audit_window):
        changed = client.put(
            f"/api/admin/files/{uploaded['id']}/permissions",
            headers=admin,
            json={"allowed_groups": ["team-b"]},
        )

    assert changed.status_code == 200, changed.text
    assert blocked_during_audit == [True]
    assert bob_list_finished.wait(5) is True
    assert bob_seen_after_audit == [True]


def test_user_page_scoped_downloads_do_not_inherit_admin_cookie(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    uploaded = upload_sample(client, b"admin private", 0, admin, filename="private.txt").json()["file"]

    ambient_admin_download = client.get(f"/api/files/{uploaded['id']}/download")
    assert ambient_admin_download.status_code == 200

    guest_scoped_download = client.get(f"/api/files/{uploaded['id']}/download?scope=guest")
    assert guest_scoped_download.status_code == 404

    user_scoped_download = client.get(f"/api/files/{uploaded['id']}/download?scope=user")
    assert user_scoped_download.status_code == 404

    guest_scoped_zip = client.get(f"/api/download.zip?scope=guest&ids={uploaded['id']}")
    assert guest_scoped_zip.status_code == 400
    assert guest_scoped_zip.json()["detail"] == "No files selected for zip download."


def test_upload_is_hidden_until_required_audit_succeeds(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    original_record = client.app.state.audit.record
    list_finished = threading.Event()
    blocked_during_audit: list[bool] = []
    visible_after_audit: list[bool] = []

    def list_files_during_audit() -> None:
        files = client.get("/api/files", headers=admin).json()["files"]
        visible_after_audit.append(any(file["original_filename"] == "pending.txt" for file in files))
        list_finished.set()

    def inspect_visibility_during_upload_audit(*args, **kwargs):
        if kwargs.get("action") == "file_uploaded":
            thread = threading.Thread(target=list_files_during_audit)
            thread.start()
            blocked_during_audit.append(not list_finished.wait(0.05))
        return original_record(*args, **kwargs)

    with patch.object(client.app.state.audit, "record", side_effect=inspect_visibility_during_upload_audit):
        uploaded = upload_sample(client, b"pending audit", 0, admin, filename="pending.txt")

    assert uploaded.status_code == 200, uploaded.text
    assert blocked_during_audit == [True]
    assert list_finished.wait(5) is True
    assert visible_after_audit == [True]
    listed = client.get("/api/files", headers=admin).json()["files"]
    uploaded_id = uploaded.json()["file"]["id"]
    listed_file = next(file for file in listed if file["id"] == uploaded_id)
    assert listed_file["audit_status"] == "complete"


def test_upload_writes_binary_manifest_and_download_headers(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    content = b"\xff\xd8\xff\xe1Exif\x00\x00raw metadata\x00\xfe"
    mtime_ms = int(datetime(2024, 3, 4, 5, 6, 8).timestamp() * 1000)

    response = upload_sample(client, content, mtime_ms, headers)
    assert response.status_code == 200, response.text
    file_info = response.json()["file"]

    saved_path = tmp_path / "Camera Roll" / "photo.jpg"
    assert saved_path.read_bytes() == content
    assert saved_path.stat().st_size == len(content)
    assert saved_path.suffix == ".jpg"
    assert abs(saved_path.stat().st_mtime - (mtime_ms / 1000)) <= 2

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifest_entry = manifest["files"][0]
    assert manifest_entry["original_filename"] == "photo.jpg"
    assert manifest_entry["file_size"] == len(content)
    assert manifest_entry["sha256"] == hashlib.sha256(content).hexdigest()
    assert manifest_entry["original_last_modified_ms"] == mtime_ms
    assert manifest_entry["owner_username"] == "admin"
    assert manifest_entry["allowed_groups"] == ["everyone"]
    assert manifest_entry["mtime_set_success"] is True

    download = client.get(f"/api/files/{file_info['id']}/download", headers=headers)
    assert download.status_code == 200
    assert download.content == content
    assert download.headers["content-length"] == str(len(content))
    assert "Last-Modified" in download.headers
    assert download.headers["etag"] == f'"sha256-{hashlib.sha256(content).hexdigest()}"'
    assert download.headers["x-original-mtime"] == str(mtime_ms)
    assert "attachment" in download.headers["content-disposition"]
    assert "photo.jpg" in download.headers["content-disposition"]
    assert download.headers["content-type"].startswith("image/jpeg")


def test_upload_size_mismatch_removes_part_file(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    response = client.post(
        "/api/upload",
        headers=headers,
        files={"file": ("bad.bin", b"1234", "application/octet-stream")},
        data={"relative_path": "bad.bin", "last_modified_ms": "0", "size": "999"},
    )
    assert response.status_code == 400
    assert not list(tmp_path.glob("*.part"))
    assert not (tmp_path / "bad.bin").exists()


def test_upload_rejects_extreme_last_modified_without_leftover_files(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    response = client.post(
        "/api/upload",
        headers=headers,
        files={"file": ("future.bin", b"1234", "application/octet-stream")},
        data={
            "relative_path": "future.bin",
            "last_modified_ms": "999999999999999999999999999",
            "size": "4",
        },
    )

    assert response.status_code == 400
    assert "timestamp" in response.json()["detail"]
    assert client.app.state.storage.list_files() == []
    assert not list(tmp_path.glob("*.part"))
    assert not (tmp_path / "future.bin").exists()


def test_same_name_does_not_overwrite(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    mtime_ms = int(datetime(2024, 4, 5, 6, 7, 8).timestamp() * 1000)

    first = upload_sample(client, b"first", mtime_ms, headers)
    second = upload_sample(client, b"second", mtime_ms, headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert (tmp_path / "Camera Roll" / "photo.jpg").read_bytes() == b"first"
    assert (tmp_path / "Camera Roll" / "photo (1).jpg").read_bytes() == b"second"


def test_same_name_does_not_reuse_manifest_path_when_file_missing(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    mtime_ms = int(datetime(2024, 4, 5, 6, 7, 8).timestamp() * 1000)

    first = upload_sample(client, b"first", mtime_ms, headers).json()["file"]
    (tmp_path / "Camera Roll" / "photo.jpg").unlink()

    second = upload_sample(client, b"second", mtime_ms, headers).json()["file"]

    assert first["saved_relative_path"] == "Camera Roll/photo.jpg"
    assert second["saved_relative_path"] == "Camera Roll/photo (1).jpg"
    assert not (tmp_path / "Camera Roll" / "photo.jpg").exists()
    assert (tmp_path / "Camera Roll" / "photo (1).jpg").read_bytes() == b"second"


def test_manifest_temp_filename_upload_is_renamed_and_manifest_survives(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    mtime_ms = int(datetime(2024, 4, 5, 6, 7, 8).timestamp() * 1000)

    uploaded = client.post(
        "/api/upload",
        headers=headers,
        files={"file": ("manifest.json.tmp", b"user bytes", "application/octet-stream")},
        data={
            "relative_path": "manifest.json.tmp",
            "last_modified_ms": str(mtime_ms),
            "size": "10",
        },
    )
    assert uploaded.status_code == 200, uploaded.text
    file_info = uploaded.json()["file"]

    assert file_info["saved_relative_path"] == "_manifest.json.tmp"
    assert (tmp_path / "_manifest.json.tmp").read_bytes() == b"user bytes"
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["files"]

    downloaded = client.get(f"/api/files/{file_info['id']}/download", headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.content == b"user bytes"

    second = client.post(
        "/api/upload",
        headers=headers,
        files={"file": ("normal.txt", b"normal", "text/plain")},
        data={
            "relative_path": "normal.txt",
            "last_modified_ms": str(mtime_ms),
            "size": "6",
        },
    )
    assert second.status_code == 200, second.text
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["files"]


def test_manifest_entry_cannot_point_at_root_control_file(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    auth_path = tmp_path / ".lan-transfer-auth.json"
    assert auth_path.exists()

    storage = client.app.state.storage
    storage._manifest["files"].append(
        {
            "id": "auth-leak",
            "original_filename": ".lan-transfer-auth.json",
            "saved_filename": ".lan-transfer-auth.json",
            "file_size": auth_path.stat().st_size,
            "sha256": hashlib.sha256(auth_path.read_bytes()).hexdigest(),
            "server_mtime": auth_path.stat().st_mtime,
            "uploaded_at": "2024-01-02T03:04:06+00:00",
            "relative_path": ".lan-transfer-auth.json",
            "saved_relative_path": ".lan-transfer-auth.json",
            "owner_username": "admin",
            "allowed_groups": ["public"],
        }
    )

    raw = client.get("/api/files/auth-leak/download")
    zipped = client.get("/api/download.zip?ids=auth-leak")
    deleted = client.delete("/api/files/auth-leak", headers=headers)

    assert raw.status_code == 400
    assert "reserved control" in raw.json()["detail"]
    assert zipped.status_code == 400
    assert "reserved control" in zipped.json()["detail"]
    assert deleted.status_code == 400
    assert auth_path.exists()


def test_zip_download_preserves_binary_entry_mtime_and_response_mtime(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    content = b"original bytes\x00\x01\x02"
    mtime_ms = int(datetime(2024, 5, 6, 7, 8, 10).timestamp() * 1000)
    uploaded = upload_sample(client, content, mtime_ms, headers).json()["file"]

    response = client.get(f"/api/download.zip?ids={uploaded['id']}", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert "Last-Modified" in response.headers

    with zipfile.ZipFile(io.BytesIO(response.content), "r") as archive:
        info = archive.getinfo("Camera Roll/photo.jpg")
        assert info.date_time == zip_datetime(mtime_ms / 1000)
        assert archive.read("Camera Roll/photo.jpg") == content


def test_zip_download_handles_corrupt_manifest_mtime_fields(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    content = b"zip tolerates bad legacy mtime"
    uploaded = upload_sample(client, content, 0, headers, filename="bad-mtime.txt").json()["file"]

    storage = client.app.state.storage
    for entry in storage._manifest["files"]:
        if entry["id"] == uploaded["id"]:
            entry["original_last_modified_ms"] = "not-a-time"
            entry["server_mtime"] = "not-a-time"

    response = client.get(f"/api/download.zip?ids={uploaded['id']}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/zip")

    with zipfile.ZipFile(io.BytesIO(response.content), "r") as archive:
        assert archive.read("Camera Roll/bad-mtime.txt") == content


def test_zip_metadata_failure_cleans_temp_and_returns_fixed_error(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    uploaded = upload_sample(client, b"zip metadata", 0, headers, filename="metadata.txt").json()["file"]
    cleanup_contexts: list[str] = []

    def cleanup_and_record(path, context: str) -> None:
        cleanup_contexts.append(context)
        cleanup_temp_file(path, context)

    with (
        patch("lan_transfer.api.os.utime", side_effect=OSError("mtime failed")),
        patch("lan_transfer.api.cleanup_temp_file", side_effect=cleanup_and_record),
    ):
        response = client.get(f"/api/download.zip?ids={uploaded['id']}", headers=headers)

    assert response.status_code == 500
    assert response.json()["detail"] == "Zip download could not be prepared."
    assert cleanup_contexts == ["batch zip metadata failure"]


def test_zip_audit_cleanup_failure_does_not_mask_audit_error(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    uploaded = upload_sample(client, b"zip audit", 0, headers, filename="audit.txt").json()["file"]
    cleanup_paths: list[Path] = []
    original_unlink = Path.unlink

    def fail_cleanup(path: Path, *args, **kwargs):
        cleanup_paths.append(path)
        raise PermissionError("zip temp locked")

    with (
        patch.object(client.app.state.audit, "record", side_effect=OSError("audit disk full")),
        patch.object(Path, "unlink", fail_cleanup),
    ):
        response = client.get(f"/api/files/{uploaded['id']}/download.zip", headers=headers)

    for path in cleanup_paths:
        original_unlink(path, missing_ok=True)

    assert response.status_code == 500
    assert response.json()["detail"] == "Audit log write failed."


def test_zip_download_rejects_when_selected_files_are_missing(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    content = b"file that will be removed"
    mtime_ms = int(datetime(2024, 5, 6, 7, 8, 10).timestamp() * 1000)
    uploaded = upload_sample(client, content, mtime_ms, headers).json()["file"]
    (tmp_path / "Camera Roll" / "photo.jpg").unlink()

    response = client.get(f"/api/download.zip?ids={uploaded['id']}", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "Selected files are missing on disk."


def test_zip_download_rejects_unsafe_manifest_path(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    storage = client.app.state.storage
    storage._manifest["files"].append(
        {
            "id": "unsafe",
            "original_filename": "unsafe.txt",
            "saved_filename": "unsafe.txt",
            "file_size": 1,
            "sha256": "0" * 64,
            "server_mtime": 0,
            "uploaded_at": "2024-01-02T03:04:06+00:00",
            "relative_path": "unsafe.txt",
            "saved_relative_path": "../unsafe.txt",
            "owner_username": "admin",
            "allowed_groups": ["everyone"],
        }
    )

    response = client.get("/api/download.zip?ids=unsafe", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "Parent directory segments are not allowed."


def test_zip_download_rejects_unsafe_manifest_archive_name(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    (tmp_path / "safe.txt").write_bytes(b"x")
    storage = client.app.state.storage
    storage._manifest["files"].append(
        {
            "id": "unsafe-archive",
            "original_filename": "safe.txt",
            "saved_filename": "safe.txt",
            "file_size": 1,
            "sha256": hashlib.sha256(b"x").hexdigest(),
            "server_mtime": 0,
            "uploaded_at": "2024-01-02T03:04:06+00:00",
            "relative_path": "../evil.txt",
            "saved_relative_path": "safe.txt",
            "owner_username": "admin",
            "allowed_groups": ["everyone"],
        }
    )

    response = client.get("/api/download.zip?ids=unsafe-archive", headers=headers)

    assert response.status_code == 400
    assert "Parent directory" in response.json()["detail"]


def test_single_file_zip_download_preserves_entry_mtime(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    headers = admin_headers(client)
    content = b"single zip keeps file timestamp"
    mtime_ms = int(datetime(2024, 6, 7, 8, 9, 10).timestamp() * 1000)
    uploaded = upload_sample(client, content, mtime_ms, headers).json()["file"]

    response = client.get(f"/api/files/{uploaded['id']}/download.zip", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert "Last-Modified" in response.headers

    with zipfile.ZipFile(io.BytesIO(response.content), "r") as archive:
        info = archive.getinfo("Camera Roll/photo.jpg")
        assert info.date_time == zip_datetime(mtime_ms / 1000)
        assert archive.read("Camera Roll/photo.jpg") == content


def test_wrong_password_locks_ip_after_five_attempts(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    for _ in range(4):
        response = client.post("/api/login", json={"username": "admin", "password": "wrong-password"})
        assert response.status_code == 400

    locked = client.post("/api/login", json={"username": "admin", "password": "wrong-password"})
    assert locked.status_code == 423
    assert locked.json()["detail"]["locked_until"] > 0

    correct_password_during_lockout = client.post("/api/login", json={"username": "admin", "password": DEFAULT_PASSWORD})
    assert correct_password_during_lockout.status_code == 423


def test_unhandled_errors_do_not_echo_internal_details(tmp_path: Path) -> None:
    config = AppConfig(host="127.0.0.1", port=9876, save_dir=tmp_path)
    client = TestClient(create_app(config), raise_server_exceptions=False)

    async def boom(_: Request) -> JSONResponse:
        raise RuntimeError("secret internal path C:/private/file.txt")

    client.app.add_api_route("/boom", boom, methods=["GET"])
    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error."
    assert "secret internal path" not in response.text


def test_password_change_invalidates_existing_session(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = admin_headers(client)
    create_user(client, admin, "alice", ["everyone"])
    alice = session_headers(login(client, "alice"))

    changed = client.post(
        "/api/password",
        headers=alice,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "new-secret-pass"},
    )
    assert changed.status_code == 200, changed.text

    old_session = client.get("/api/session", headers=alice)
    assert old_session.status_code == 403
    assert client.post("/api/login", json={"username": "alice", "password": DEFAULT_PASSWORD}).status_code == 400
    assert client.post("/api/login", json={"username": "alice", "password": "new-secret-pass"}).status_code == 200
