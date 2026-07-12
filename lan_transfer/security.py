from __future__ import annotations

from pathlib import Path
import re
import unicodedata


WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

INVALID_WINDOWS_CHARS = '<>:"/\\|?*'
DRIVE_PREFIX_RE = re.compile(r"^[a-zA-Z]:")
RESERVED_ROOT_FILENAMES = {
    "manifest.json",
    "manifest.json.tmp",
    "lan-transfer-auth.json",
    "lan-transfer-audit.jsonl",
}


class UnsafePathError(ValueError):
    """Raised when a browser-provided path could escape the save directory."""


def sanitize_segment(segment: str, fallback: str = "file") -> str:
    segment = unicodedata.normalize("NFC", segment)
    cleaned = []
    for char in segment:
        if char in INVALID_WINDOWS_CHARS or ord(char) < 32:
            cleaned.append("_")
        else:
            cleaned.append(char)

    value = "".join(cleaned).strip().strip(".")
    value = re.sub(r"\s+", " ", value)
    value = value[:180].rstrip(" .")

    if not value:
        value = fallback

    stem = value.split(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        value = f"_{value}"

    return value


def reserved_root_key(filename: str) -> str:
    return unicodedata.normalize("NFC", filename).strip().strip(".").casefold()


def is_reserved_root_filename(filename: str) -> bool:
    return reserved_root_key(filename) in RESERVED_ROOT_FILENAMES


def normalize_relative_parts(relative_path: str | None, filename: str | None) -> list[str]:
    raw = relative_path or filename or "file"
    raw = raw.replace("\\", "/")

    if raw.startswith("/") or raw.startswith("//") or DRIVE_PREFIX_RE.match(raw):
        raise UnsafePathError("Absolute paths are not allowed.")

    parts: list[str] = []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise UnsafePathError("Parent directory segments are not allowed.")
        parts.append(sanitize_segment(part))

    if not parts:
        parts = [sanitize_segment(filename or "file")]
    if len(parts) == 1 and is_reserved_root_filename(parts[0]):
        parts[0] = f"_{parts[0]}"

    return parts


def validate_stored_relative_parts(relative_path: str | None) -> list[str]:
    raw = str(relative_path or "")
    raw = unicodedata.normalize("NFC", raw).replace("\\", "/")

    if not raw:
        raise UnsafePathError("Manifest path is empty.")
    if raw.startswith("/") or raw.startswith("//") or DRIVE_PREFIX_RE.match(raw):
        raise UnsafePathError("Manifest path must be relative.")

    parts: list[str] = []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise UnsafePathError("Parent directory segments are not allowed.")
        parts.append(part)

    if not parts:
        raise UnsafePathError("Manifest path is empty.")
    if len(parts) == 1 and is_reserved_root_filename(parts[0]):
        raise UnsafePathError("Manifest path points at a reserved control filename.")
    for part in parts:
        if sanitize_segment(part) != part:
            raise UnsafePathError("Manifest path contains an unsafe segment.")

    return parts


def ensure_inside(base_dir: Path, candidate: Path) -> Path:
    base = base_dir.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise UnsafePathError("Resolved path escapes the save directory.") from exc
    return resolved


def safe_relative_path(relative_path: str | None, filename: str | None) -> str:
    return "/".join(normalize_relative_parts(relative_path, filename))
