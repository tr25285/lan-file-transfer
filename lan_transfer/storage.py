from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from dataclasses import dataclass
from typing import Any, Callable
import hashlib
import json
import logging
import math
import os
import shutil
import tempfile
import threading
import unicodedata
import uuid
import zipfile

from fastapi import UploadFile

from .security import UnsafePathError, ensure_inside, normalize_relative_parts, safe_relative_path, validate_stored_relative_parts


CHUNK_SIZE = 1024 * 1024
MANIFEST_NAME = "manifest.json"
GROUP_DEFAULT = "everyone"
GROUP_LEGACY_DEFAULT = "default"
MAX_CLIENT_MTIME_TIMESTAMP = datetime(2107, 12, 31, 23, 59, 58, tzinfo=timezone.utc).timestamp()
LOGGER = logging.getLogger(__name__)


@dataclass
class PreparedDelete:
    entry: dict[str, Any]
    index: int
    path: Path
    tombstone_path: Path | None


def utc_iso_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def timestamp_from_last_modified_ms(value: int | None) -> float | None:
    if value is None:
        return None
    try:
        timestamp = int(value) / 1000
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Invalid last modified timestamp.") from exc
    if timestamp < 0:
        return None
    if timestamp > MAX_CLIENT_MTIME_TIMESTAMP:
        raise ValueError("Last modified timestamp is out of supported range.")
    return timestamp


def safe_float_timestamp(value: Any) -> float | None:
    try:
        timestamp = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(timestamp) or timestamp < 0:
        return None
    if timestamp > MAX_CLIENT_MTIME_TIMESTAMP:
        return None
    return timestamp


def safe_timestamp_from_last_modified_ms(value: Any) -> float | None:
    try:
        return timestamp_from_last_modified_ms(value)
    except ValueError:
        return None


def zip_datetime(timestamp: float) -> tuple[int, int, int, int, int, int]:
    safe_timestamp = safe_float_timestamp(timestamp)
    if safe_timestamp is None:
        safe_timestamp = 0
    dt = datetime.fromtimestamp(safe_timestamp)
    if dt.year < 1980:
        return (1980, 1, 1, 0, 0, 0)
    if dt.year > 2107:
        return (2107, 12, 31, 23, 59, 58)
    return dt.timetuple()[:6]


def unique_archive_name(preferred_name: str, fallback_name: str, used_names: set[str]) -> str:
    def is_used(name: str) -> bool:
        return name in used_names or stored_path_key(name) in used_names

    candidate = preferred_name
    if is_used(candidate):
        candidate = fallback_name

    path = PurePosixPath(preferred_name)
    suffix = path.suffix
    stem = str(path.with_suffix("")) if suffix else preferred_name

    index = 1
    while is_used(candidate):
        candidate = f"{stem} ({index}){suffix}"
        index += 1

    used_names.add(candidate)
    used_names.add(stored_path_key(candidate))
    return candidate


def archive_name_for_entry(entry: dict[str, Any]) -> tuple[str, str]:
    original_filename = str(entry.get("original_filename") or entry.get("saved_filename") or "file")
    preferred = safe_relative_path(str(entry.get("relative_path") or ""), original_filename)
    fallback = safe_relative_path(
        str(entry.get("saved_relative_path") or entry.get("saved_filename") or ""),
        original_filename,
    )
    return preferred, fallback


def stored_path_key(relative_path: str) -> str:
    return "/".join(unicodedata.normalize("NFC", part).casefold() for part in relative_path.replace("\\", "/").split("/"))


class StorageManager:
    def __init__(self, save_dir: Path):
        self.save_dir = save_dir
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.save_dir / MANIFEST_NAME
        self._lock = threading.RLock()
        self._manifest = self._load_manifest()
        self._write_manifest()

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"version": 1, "files": []}
        with self.manifest_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict) or not isinstance(data.get("files"), list):
            raise ValueError(f"Invalid manifest format: {self.manifest_path}")
        data.setdefault("version", 1)
        self._migrate_manifest_groups(data)
        return data

    def _migrate_manifest_groups(self, data: dict[str, Any]) -> None:
        for entry in data.get("files", []):
            groups = entry.get("allowed_groups")
            if not isinstance(groups, list):
                continue
            migrated: list[str] = []
            for group_id in groups:
                normalized = GROUP_DEFAULT if str(group_id) == GROUP_LEGACY_DEFAULT else str(group_id)
                if normalized not in migrated:
                    migrated.append(normalized)
            entry["allowed_groups"] = migrated

    def _write_manifest(self) -> None:
        with self._lock:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            temp_path = self.save_dir / f".{MANIFEST_NAME}.{uuid.uuid4().hex}.tmp"
            try:
                with temp_path.open("x", encoding="utf-8") as handle:
                    json.dump(self._manifest, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                os.replace(temp_path, self.manifest_path)
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise

    def list_files(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(
                [dict(item) for item in self._manifest["files"]],
                key=lambda item: item.get("uploaded_at", ""),
                reverse=True,
            )

    def manifest_transaction(self):
        return self._lock

    def get_entry(self, file_id: str) -> dict[str, Any]:
        with self._lock:
            for entry in self._manifest["files"]:
                if entry["id"] == file_id:
                    return dict(entry)
        raise KeyError(file_id)

    def update_entry(self, file_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            for entry in self._manifest["files"]:
                if entry["id"] == file_id:
                    previous = dict(entry)
                    entry.update(updates)
                    try:
                        self._write_manifest()
                    except Exception:
                        entry.clear()
                        entry.update(previous)
                        raise
                    return dict(entry)
        raise KeyError(file_id)

    def reassign_owner_with_ids(self, old_username: str, new_username: str, new_display_name: str) -> list[str]:
        with self._lock:
            previous_entries = [dict(entry) for entry in self._manifest["files"]]
            changed_ids: list[str] = []
            for entry in self._manifest["files"]:
                if entry.get("owner_username") != old_username:
                    continue
                entry["owner_username"] = new_username
                entry["owner_display_name"] = new_display_name
                changed_ids.append(str(entry["id"]))
            if changed_ids:
                try:
                    self._write_manifest()
                except Exception:
                    self._manifest["files"] = previous_entries
                    raise
            return changed_ids

    def reassign_owner_for_ids(self, file_ids: list[str], new_username: str, new_display_name: str) -> int:
        with self._lock:
            selected_ids = set(file_ids)
            previous_entries = [dict(entry) for entry in self._manifest["files"]]
            changed = 0
            for entry in self._manifest["files"]:
                if entry.get("id") not in selected_ids:
                    continue
                entry["owner_username"] = new_username
                entry["owner_display_name"] = new_display_name
                changed += 1
            if changed:
                try:
                    self._write_manifest()
                except Exception:
                    self._manifest["files"] = previous_entries
                    raise
            return changed

    def reassign_owner(self, old_username: str, new_username: str, new_display_name: str) -> int:
        return len(self.reassign_owner_with_ids(old_username, new_username, new_display_name))

    def path_for_entry(self, entry: dict[str, Any]) -> Path:
        saved_relative_path = entry.get("saved_relative_path") or entry["saved_filename"]
        relative_parts = validate_stored_relative_parts(str(saved_relative_path))
        path = self.save_dir.joinpath(*relative_parts)
        return ensure_inside(self.save_dir, path)

    def _unique_target(self, relative_parts: list[str]) -> tuple[Path, str, str]:
        target_dir = self.save_dir.joinpath(*relative_parts[:-1])
        ensure_inside(self.save_dir, target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            used_relative_paths = {
                stored_path_key(str(entry.get("saved_relative_path") or entry.get("saved_filename") or ""))
                for entry in self._manifest["files"]
            }

        original_name = relative_parts[-1]
        stem = Path(original_name).stem or "file"
        suffix = Path(original_name).suffix

        def has_pending_delete(candidate_name: str) -> bool:
            prefix = f"{unicodedata.normalize('NFC', candidate_name).casefold()}."
            return any(
                child.name.casefold().startswith(prefix) and child.name.casefold().endswith(".delete")
                for child in target_dir.iterdir()
            )

        candidate_name = original_name
        for index in range(1, 10000):
            candidate = target_dir / candidate_name
            ensure_inside(self.save_dir, candidate)
            saved_relative_parts = [*relative_parts[:-1], candidate_name]
            saved_relative_path = "/".join(saved_relative_parts)
            saved_relative_key = stored_path_key(saved_relative_path)
            if not candidate.exists() and not has_pending_delete(candidate_name) and saved_relative_key not in used_relative_paths:
                try:
                    with candidate.open("xb"):
                        pass
                except FileExistsError:
                    pass
                else:
                    return candidate, candidate_name, saved_relative_path
            candidate_name = f"{stem} ({index}){suffix}"

        raise RuntimeError("Could not create a non-conflicting filename.")

    async def save_upload(
        self,
        upload: UploadFile,
        *,
        relative_path: str | None,
        last_modified_ms: int | None,
        expected_size: int | None,
        owner_username: str,
        owner_display_name: str,
        allowed_groups: list[str],
        before_commit: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        client_filename = (upload.filename or "file").replace("\\", "/").split("/")[-1] or "file"
        relative_parts = normalize_relative_parts(relative_path, client_filename)
        safe_relative_path = "/".join(relative_parts)
        last_modified_timestamp = timestamp_from_last_modified_ms(last_modified_ms)
        target_path, saved_filename, saved_relative_path = self._unique_target(relative_parts)
        part_path = target_path.with_name(f"{target_path.name}.{uuid.uuid4().hex}.part")
        ensure_inside(self.save_dir, part_path)

        sha256 = hashlib.sha256()
        total_size = 0
        mtime_set = False
        mtime_error: str | None = None

        try:
            with part_path.open("xb") as output:
                while True:
                    chunk = await upload.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    output.write(chunk)
                    sha256.update(chunk)
                    total_size += len(chunk)

            disk_size = part_path.stat().st_size
            if disk_size != total_size:
                raise IOError(f"Disk size mismatch: wrote {total_size}, stat returned {disk_size}.")
            if expected_size is not None and expected_size != total_size:
                raise ValueError(f"Browser reported {expected_size} bytes, server received {total_size}.")

            if last_modified_timestamp is not None:
                try:
                    os.utime(part_path, (last_modified_timestamp, last_modified_timestamp))
                    observed = part_path.stat().st_mtime
                    mtime_set = abs(observed - last_modified_timestamp) <= 2
                except OSError as exc:
                    mtime_error = str(exc)

            os.replace(part_path, target_path)
            if last_modified_timestamp is not None:
                try:
                    os.utime(target_path, (last_modified_timestamp, last_modified_timestamp))
                    observed = target_path.stat().st_mtime
                    mtime_set = abs(observed - last_modified_timestamp) <= 2
                except OSError as exc:
                    mtime_error = str(exc)

            server_mtime = target_path.stat().st_mtime
            entry = {
                "id": uuid.uuid4().hex,
                "original_filename": client_filename,
                "saved_filename": saved_filename,
                "file_size": total_size,
                "sha256": sha256.hexdigest(),
                "original_last_modified_ms": last_modified_ms,
                "original_last_modified_iso": (
                    utc_iso_from_timestamp(last_modified_timestamp)
                    if last_modified_timestamp is not None
                    else None
                ),
                "server_mtime": server_mtime,
                "server_mtime_iso": utc_iso_from_timestamp(server_mtime),
                "mtime_set_success": mtime_set,
                "mtime_error": mtime_error,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "relative_path": safe_relative_path,
                "saved_relative_path": saved_relative_path,
                "owner_username": owner_username,
                "owner_display_name": owner_display_name,
                "allowed_groups": list(dict.fromkeys(allowed_groups)),
                "audit_status": "pending",
            }

            with self._lock:
                if before_commit is not None:
                    before_commit()
                self._manifest["files"].append(entry)
                try:
                    self._write_manifest()
                except Exception:
                    self._manifest["files"] = [
                        item for item in self._manifest["files"] if item.get("id") != entry["id"]
                    ]
                    raise

            LOGGER.info("Saved upload %s (%s bytes) as %s", client_filename, total_size, saved_relative_path)
            return dict(entry)
        except Exception:
            if part_path.exists():
                part_path.unlink()
            if target_path.exists():
                target_path.unlink()
            LOGGER.exception("Upload failed for %s", client_filename)
            raise
        finally:
            await upload.close()

    def prepare_delete_entry(self, file_id: str) -> PreparedDelete:
        with self._lock:
            for index, entry in enumerate(self._manifest["files"]):
                if entry["id"] != file_id:
                    continue
                path = self.path_for_entry(entry)
                tombstone_path: Path | None = None
                if path.exists():
                    tombstone_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.delete")
                    ensure_inside(self.save_dir, tombstone_path)
                    os.replace(path, tombstone_path)
                removed = self._manifest["files"].pop(index)
                try:
                    self._write_manifest()
                except Exception:
                    self._manifest["files"].insert(index, removed)
                    if tombstone_path and tombstone_path.exists() and not path.exists():
                        os.replace(tombstone_path, path)
                    raise
                return PreparedDelete(entry=dict(removed), index=index, path=path, tombstone_path=tombstone_path)
        raise KeyError(file_id)

    def rollback_prepared_delete(self, prepared: PreparedDelete) -> None:
        with self._lock:
            existing_ids = {entry.get("id") for entry in self._manifest["files"]}
            inserted = False
            if prepared.entry.get("id") not in existing_ids:
                index = min(max(prepared.index, 0), len(self._manifest["files"]))
                self._manifest["files"].insert(index, dict(prepared.entry))
                inserted = True
            file_restored = prepared.tombstone_path is None or prepared.path.exists()
            try:
                if prepared.tombstone_path and prepared.tombstone_path.exists() and not prepared.path.exists():
                    os.replace(prepared.tombstone_path, prepared.path)
                file_restored = True
                self._write_manifest()
            except Exception:
                if inserted and not file_restored:
                    self._manifest["files"] = [
                        entry for entry in self._manifest["files"] if entry.get("id") != prepared.entry.get("id")
                    ]
                raise

    def commit_prepared_delete(self, prepared: PreparedDelete) -> dict[str, Any]:
        with self._lock:
            if prepared.tombstone_path:
                try:
                    prepared.tombstone_path.unlink()
                except Exception:
                    if prepared.tombstone_path.exists() and not prepared.path.exists():
                        os.replace(prepared.tombstone_path, prepared.path)
                    self._manifest["files"].insert(prepared.index, dict(prepared.entry))
                    try:
                        self._write_manifest()
                    except Exception:
                        self._manifest["files"] = [
                            entry for entry in self._manifest["files"] if entry.get("id") != prepared.entry.get("id")
                        ]
                        raise
                    raise
            LOGGER.info("Deleted file %s", prepared.entry.get("saved_relative_path"))
            return dict(prepared.entry)

    def delete_entry(self, file_id: str) -> dict[str, Any]:
        prepared = self.prepare_delete_entry(file_id)
        return self.commit_prepared_delete(prepared)

    def build_zip(self, file_ids: list[str] | None = None) -> Path:
        selected_ids = set(file_ids or [])
        entries = [
            entry
            for entry in self.list_files()
            if not selected_ids or entry["id"] in selected_ids
        ]
        return self.build_zip_for_entries(entries)

    def build_zip_for_entries(self, entries: list[dict[str, Any]]) -> Path:
        if not entries:
            raise ValueError("No files selected for zip download.")

        temp = tempfile.NamedTemporaryFile(prefix="lan-transfer-", suffix=".zip", delete=False)
        temp_path = Path(temp.name)
        temp.close()

        try:
            used_archive_names: set[str] = set()
            written_count = 0
            with zipfile.ZipFile(temp_path, "w", allowZip64=True) as archive:
                for entry in entries:
                    file_path = self.path_for_entry(entry)
                    if not file_path.exists():
                        LOGGER.warning("Skipping missing file during zip build: %s", file_path)
                        continue

                    preferred_name, fallback_name = archive_name_for_entry(entry)
                    archive_name = unique_archive_name(preferred_name, fallback_name, used_archive_names)
                    timestamp = safe_timestamp_from_last_modified_ms(entry.get("original_last_modified_ms"))
                    if timestamp is None:
                        timestamp = safe_float_timestamp(entry.get("server_mtime"))
                    if timestamp is None:
                        timestamp = file_path.stat().st_mtime

                    info = zipfile.ZipInfo(archive_name, date_time=zip_datetime(timestamp))
                    info.compress_type = zipfile.ZIP_STORED
                    info.file_size = file_path.stat().st_size

                    with file_path.open("rb") as source, archive.open(info, "w") as target:
                        shutil.copyfileobj(source, target, CHUNK_SIZE)
                    written_count += 1

            if written_count == 0:
                raise ValueError("Selected files are missing on disk.")
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        return temp_path
