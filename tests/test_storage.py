from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import io
import threading
import tempfile
import zipfile
from unittest.mock import patch

import pytest

from lan_transfer.security import UnsafePathError, normalize_relative_parts, sanitize_segment
from lan_transfer.storage import StorageManager, unique_archive_name, zip_datetime


def test_sanitize_windows_reserved_and_invalid_chars() -> None:
    assert sanitize_segment("CON.txt") == "_CON.txt"
    assert sanitize_segment("a<b>:c?.jpg") == "a_b__c_.jpg"
    assert sanitize_segment("...") == "file"


def test_rejects_path_traversal_and_absolute_paths() -> None:
    with pytest.raises(UnsafePathError):
        normalize_relative_parts("../secret.txt", "secret.txt")
    with pytest.raises(UnsafePathError):
        normalize_relative_parts("C:/secret.txt", "secret.txt")
    with pytest.raises(UnsafePathError):
        normalize_relative_parts("/secret.txt", "secret.txt")


def test_root_control_filenames_are_reserved() -> None:
    assert normalize_relative_parts("manifest.json", "manifest.json") == ["_manifest.json"]
    assert normalize_relative_parts("manifest.json.tmp", "manifest.json.tmp") == ["_manifest.json.tmp"]
    assert normalize_relative_parts(".lan-transfer-auth.json", ".lan-transfer-auth.json") == ["_lan-transfer-auth.json"]
    assert normalize_relative_parts(".lan-transfer-audit.jsonl", ".lan-transfer-audit.jsonl") == ["_lan-transfer-audit.jsonl"]
    assert normalize_relative_parts("folder/manifest.json", "manifest.json") == ["folder", "manifest.json"]


def test_manifest_transaction_blocks_concurrent_manifest_reads(tmp_path: Path) -> None:
    storage = StorageManager(tmp_path)
    read_finished = threading.Event()

    def list_files() -> None:
        storage.list_files()
        read_finished.set()

    with storage.manifest_transaction():
        thread = threading.Thread(target=list_files)
        thread.start()
        assert read_finished.wait(0.05) is False

    assert read_finished.wait(5) is True
    thread.join(timeout=1)


def test_unique_archive_name_avoids_duplicate_zip_entries() -> None:
    used = set()

    first = unique_archive_name("Camera Roll/photo.jpg", "Camera Roll/photo.jpg", used)
    second = unique_archive_name("Camera Roll/photo.jpg", "Camera Roll/photo (1).jpg", used)
    third = unique_archive_name("Camera Roll/photo.jpg", "Camera Roll/photo (1).jpg", used)

    assert first == "Camera Roll/photo.jpg"
    assert second == "Camera Roll/photo (1).jpg"
    assert third == "Camera Roll/photo (2).jpg"


def test_unique_archive_name_avoids_case_insensitive_zip_entries() -> None:
    used = set()

    first = unique_archive_name("Camera Roll/Photo.jpg", "Camera Roll/Photo.jpg", used)
    second = unique_archive_name("camera roll/photo.jpg", "camera roll/photo (1).jpg", used)

    assert first == "Camera Roll/Photo.jpg"
    assert second == "camera roll/photo (1).jpg"


def test_unique_target_reserves_candidate_before_manifest_write(tmp_path: Path) -> None:
    storage = StorageManager(tmp_path)

    first_path, first_name, first_relative = storage._unique_target(["photo.jpg"])
    second_path, second_name, second_relative = storage._unique_target(["photo.jpg"])

    try:
        assert first_name == "photo.jpg"
        assert first_relative == "photo.jpg"
        assert first_path.exists()
        assert second_name == "photo (1).jpg"
        assert second_relative == "photo (1).jpg"
        assert second_path.exists()
    finally:
        first_path.unlink(missing_ok=True)
        second_path.unlink(missing_ok=True)


def test_build_zip_preserves_content_and_entry_mtime(tmp_path: Path) -> None:
    storage = StorageManager(tmp_path)
    content = b"\x00Exif\x00metadata stays untouched\xff"
    file_path = tmp_path / "photo.jpg"
    file_path.write_bytes(content)

    mtime_ms = int(datetime(2024, 1, 2, 3, 4, 6).timestamp() * 1000)
    entry = {
        "id": "abc",
        "original_filename": "photo.jpg",
        "saved_filename": "photo.jpg",
        "file_size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "original_last_modified_ms": mtime_ms,
        "server_mtime": mtime_ms / 1000,
        "uploaded_at": "2024-01-02T03:04:06+00:00",
        "relative_path": "album/photo.jpg",
        "saved_relative_path": "photo.jpg",
    }
    storage._manifest["files"].append(entry)
    storage._write_manifest()

    zip_path = storage.build_zip(["abc"])
    try:
        data = zip_path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            info = archive.getinfo("album/photo.jpg")
            assert info.date_time == zip_datetime(mtime_ms / 1000)
            assert archive.read("album/photo.jpg") == content
    finally:
        zip_path.unlink(missing_ok=True)


def test_delete_entry_keeps_manifest_when_file_unlink_fails(tmp_path: Path) -> None:
    storage = StorageManager(tmp_path)
    file_path = tmp_path / "locked.txt"
    file_path.write_bytes(b"locked")
    entry = {
        "id": "locked",
        "original_filename": "locked.txt",
        "saved_filename": "locked.txt",
        "file_size": 6,
        "sha256": hashlib.sha256(b"locked").hexdigest(),
        "server_mtime": file_path.stat().st_mtime,
        "uploaded_at": "2024-01-02T03:04:06+00:00",
        "relative_path": "locked.txt",
        "saved_relative_path": "locked.txt",
    }
    storage._manifest["files"].append(entry)
    storage._write_manifest()

    with patch.object(Path, "unlink", side_effect=PermissionError("locked")):
        with pytest.raises(PermissionError):
            storage.delete_entry("locked")

    assert storage.get_entry("locked")["id"] == "locked"


def test_update_entry_rolls_back_memory_when_manifest_write_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = StorageManager(tmp_path)
    entry = {
        "id": "editable",
        "original_filename": "editable.txt",
        "saved_filename": "editable.txt",
        "file_size": 0,
        "sha256": hashlib.sha256(b"").hexdigest(),
        "server_mtime": 0,
        "uploaded_at": "2024-01-02T03:04:06+00:00",
        "relative_path": "editable.txt",
        "saved_relative_path": "editable.txt",
        "allowed_groups": ["everyone"],
    }
    storage._manifest["files"].append(entry)

    monkeypatch.setattr(storage, "_write_manifest", lambda: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(OSError):
        storage.update_entry("editable", {"allowed_groups": ["team-a"]})

    assert storage.get_entry("editable")["allowed_groups"] == ["everyone"]


def test_delete_entry_restores_file_when_manifest_write_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = StorageManager(tmp_path)
    file_path = tmp_path / "keep.txt"
    file_path.write_bytes(b"keep")
    entry = {
        "id": "keep",
        "original_filename": "keep.txt",
        "saved_filename": "keep.txt",
        "file_size": 4,
        "sha256": hashlib.sha256(b"keep").hexdigest(),
        "server_mtime": file_path.stat().st_mtime,
        "uploaded_at": "2024-01-02T03:04:06+00:00",
        "relative_path": "keep.txt",
        "saved_relative_path": "keep.txt",
        "allowed_groups": ["everyone"],
    }
    storage._manifest["files"].append(entry)
    storage._write_manifest()

    monkeypatch.setattr(storage, "_write_manifest", lambda: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(OSError):
        storage.delete_entry("keep")

    assert storage.get_entry("keep")["id"] == "keep"
    assert file_path.read_bytes() == b"keep"
    assert not list(tmp_path.glob("*.delete"))


def test_unique_target_treats_manifest_paths_case_insensitively(tmp_path: Path) -> None:
    storage = StorageManager(tmp_path)
    target_dir = tmp_path / "Camera Roll"
    target_dir.mkdir()
    entry = {
        "id": "photo",
        "original_filename": "Photo.jpg",
        "saved_filename": "Photo.jpg",
        "file_size": 5,
        "sha256": hashlib.sha256(b"photo").hexdigest(),
        "server_mtime": 0,
        "uploaded_at": "2024-01-02T03:04:06+00:00",
        "relative_path": "Camera Roll/Photo.jpg",
        "saved_relative_path": "Camera Roll/Photo.jpg",
        "allowed_groups": ["everyone"],
    }
    storage._manifest["files"].append(entry)
    storage._write_manifest()

    next_path, next_name, next_relative = storage._unique_target(["Camera Roll", "photo.jpg"])

    try:
        assert next_name == "photo (1).jpg"
        assert next_relative == "Camera Roll/photo (1).jpg"
        assert next_path.exists()
    finally:
        next_path.unlink(missing_ok=True)


def test_unique_target_treats_pending_delete_tombstone_case_insensitively(tmp_path: Path) -> None:
    storage = StorageManager(tmp_path)
    file_path = tmp_path / "Photo.jpg"
    file_path.write_bytes(b"photo")
    entry = {
        "id": "photo",
        "original_filename": "Photo.jpg",
        "saved_filename": "Photo.jpg",
        "file_size": 5,
        "sha256": hashlib.sha256(b"photo").hexdigest(),
        "server_mtime": file_path.stat().st_mtime,
        "uploaded_at": "2024-01-02T03:04:06+00:00",
        "relative_path": "Photo.jpg",
        "saved_relative_path": "Photo.jpg",
        "allowed_groups": ["everyone"],
    }
    storage._manifest["files"].append(entry)
    storage._write_manifest()
    prepared = storage.prepare_delete_entry("photo")

    next_path, next_name, next_relative = storage._unique_target(["photo.jpg"])

    try:
        assert next_name == "photo (1).jpg"
        assert next_relative == "photo (1).jpg"
        assert next_path.exists()
    finally:
        next_path.unlink(missing_ok=True)
        storage.rollback_prepared_delete(prepared)

    assert file_path.read_bytes() == b"photo"


def test_path_for_entry_rejects_reserved_control_filenames(tmp_path: Path) -> None:
    storage = StorageManager(tmp_path)

    with pytest.raises(UnsafePathError, match="reserved control"):
        storage.path_for_entry({"saved_relative_path": ".lan-transfer-auth.json"})


def test_rollback_prepared_delete_keeps_memory_entry_after_file_restore_when_manifest_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = StorageManager(tmp_path)
    file_path = tmp_path / "restore.txt"
    file_path.write_bytes(b"restore")
    entry = {
        "id": "restore",
        "original_filename": "restore.txt",
        "saved_filename": "restore.txt",
        "file_size": 7,
        "sha256": hashlib.sha256(b"restore").hexdigest(),
        "server_mtime": file_path.stat().st_mtime,
        "uploaded_at": "2024-01-02T03:04:06+00:00",
        "relative_path": "restore.txt",
        "saved_relative_path": "restore.txt",
        "allowed_groups": ["everyone"],
    }
    storage._manifest["files"].append(entry)
    storage._write_manifest()
    prepared = storage.prepare_delete_entry("restore")

    monkeypatch.setattr(storage, "_write_manifest", lambda: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(OSError):
        storage.rollback_prepared_delete(prepared)

    assert storage.get_entry("restore")["id"] == "restore"
    assert file_path.read_bytes() == b"restore"
    assert not list(tmp_path.glob("*.delete"))


def test_build_zip_removes_temp_file_on_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = StorageManager(tmp_path)
    temp_paths: list[Path] = []
    real_named_temp = tempfile.NamedTemporaryFile

    def named_temp_in_tmp(*args, **kwargs):
        kwargs["dir"] = tmp_path
        handle = real_named_temp(*args, **kwargs)
        temp_paths.append(Path(handle.name))
        return handle

    monkeypatch.setattr("lan_transfer.storage.tempfile.NamedTemporaryFile", named_temp_in_tmp)
    monkeypatch.setattr(storage, "path_for_entry", lambda entry: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        storage.build_zip_for_entries([{"id": "x", "original_filename": "x.txt", "saved_filename": "x.txt"}])

    assert temp_paths
    assert all(not path.exists() for path in temp_paths)
