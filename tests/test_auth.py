from __future__ import annotations

import threading

import pytest

from lan_transfer.auth import AUTH_SETTINGS_NAME, AccountAuthManager, AuthError, DEFAULT_PASSWORD


def fail_write() -> None:
    raise OSError("settings disk full")


def usernames(auth: AccountAuthManager) -> set[str]:
    return {user["username"] for user in auth.list_users()}


def test_create_user_rolls_back_memory_when_settings_write_fails(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth = AccountAuthManager(tmp_path)
    monkeypatch.setattr(auth, "_write_settings", fail_write)

    with pytest.raises(OSError):
        auth.create_user("alice")

    assert "alice" not in usernames(auth)


def test_batch_create_users_rolls_back_memory_when_settings_write_fails(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth = AccountAuthManager(tmp_path)
    monkeypatch.setattr(auth, "_write_settings", fail_write)

    with pytest.raises(OSError):
        auth.create_users_batch([{"username": "alice"}, {"username": "bob"}])

    assert {"alice", "bob"}.isdisjoint(usernames(auth))


def test_update_user_rolls_back_memory_when_settings_write_fails(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth = AccountAuthManager(tmp_path)
    auth.create_user("alice")
    monkeypatch.setattr(auth, "_write_settings", fail_write)

    with pytest.raises(OSError):
        auth.update_user("alice", display_name="Changed")

    assert auth.get_user("alice")["display_name"] == "alice"


def test_role_change_invalidates_existing_user_session(tmp_path) -> None:
    auth = AccountAuthManager(tmp_path)
    auth.create_user("alice")
    session = auth.login("alice", DEFAULT_PASSWORD, "127.0.0.1")["session_token"]

    auth.update_user("alice", role="admin")

    assert auth.verify_session(str(session)) is False


def test_state_transaction_blocks_concurrent_auth_writes(tmp_path) -> None:
    auth = AccountAuthManager(tmp_path)
    write_finished = threading.Event()

    def create_alice() -> None:
        auth.create_user("alice")
        write_finished.set()

    with auth.state_transaction():
        thread = threading.Thread(target=create_alice)
        thread.start()
        assert write_finished.wait(0.05) is False

    assert write_finished.wait(5) is True
    thread.join(timeout=1)
    assert "alice" in usernames(auth)


def test_delete_user_rolls_back_memory_when_settings_write_fails(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth = AccountAuthManager(tmp_path)
    auth.create_user("alice")
    monkeypatch.setattr(auth, "_write_settings", fail_write)

    with pytest.raises(OSError):
        auth.delete_user("alice")

    assert auth.get_user("alice")["username"] == "alice"


def test_change_password_rolls_back_memory_when_settings_write_fails(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth = AccountAuthManager(tmp_path)
    original_writer = auth._write_settings
    monkeypatch.setattr(auth, "_write_settings", fail_write)

    with pytest.raises(OSError):
        auth.change_password("admin", DEFAULT_PASSWORD, "new-password", "127.0.0.1")

    monkeypatch.setattr(auth, "_write_settings", original_writer)
    assert auth.login("admin", DEFAULT_PASSWORD, "127.0.0.2")["user"]["username"] == "admin"
    with pytest.raises(AuthError):
        auth.login("admin", "new-password", "127.0.0.3")


def test_group_create_and_delete_roll_back_memory_when_settings_write_fails(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth = AccountAuthManager(tmp_path)
    monkeypatch.setattr(auth, "_write_settings", fail_write)

    with pytest.raises(OSError):
        auth.create_group("team-a")

    assert "team-a" not in {group["id"] for group in auth.list_groups()}

    monkeypatch.setattr(auth, "_write_settings", AccountAuthManager._write_settings.__get__(auth, AccountAuthManager))
    auth.create_group("team-b")
    monkeypatch.setattr(auth, "_write_settings", fail_write)

    with pytest.raises(OSError):
        auth.delete_group("team-b")

    assert "team-b" in {group["id"] for group in auth.list_groups()}


def test_write_settings_uses_random_temp_and_cleans_failed_replace(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth = AccountAuthManager(tmp_path)
    replace_sources: list[str] = []

    def fail_replace(source, _target) -> None:
        replace_sources.append(source.name)
        raise OSError("replace failed")

    monkeypatch.setattr("lan_transfer.auth.os.replace", fail_replace)

    with pytest.raises(OSError):
        auth.create_user("alice")

    assert replace_sources
    assert replace_sources[0].startswith(f"{AUTH_SETTINGS_NAME}.")
    assert replace_sources[0] != f"{AUTH_SETTINGS_NAME}.tmp"
    assert not (tmp_path / f"{AUTH_SETTINGS_NAME}.tmp").exists()
    assert not list(tmp_path.glob(f"{AUTH_SETTINGS_NAME}.*.tmp"))
    assert "alice" not in usernames(auth)


def test_restore_state_keeps_current_memory_when_snapshot_write_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = AccountAuthManager(tmp_path)
    snapshot = auth.snapshot_state()
    auth.create_user("alice")
    alice_session = auth.login("alice", DEFAULT_PASSWORD, "127.0.0.1")["session_token"]
    monkeypatch.setattr(auth, "_write_settings", fail_write)

    with pytest.raises(OSError):
        auth.restore_state(snapshot)

    assert "alice" in usernames(auth)
    assert auth.verify_session(str(alice_session)) is True
