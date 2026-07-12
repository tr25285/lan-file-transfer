from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_release_identity_is_consistent_across_metadata_files() -> None:
    required = {
        "HaoXiang Huang",
        "didadida1688@gmail.com",
        "https://nextweb4.github.io/",
        "https://github.com/NextWeb4",
    }
    files = [
        "README.md",
        "RELEASE_NOTES.md",
        "lan_transfer/__init__.py",
        "lan_transfer/static/user.html",
        "lan_transfer/static/admin.html",
        "lan_transfer/static/user.js",
        "lan_transfer/static/admin.js",
    ]

    for file_path in files:
        text = read_text(file_path)
        for value in required:
            assert value in text, f"{value!r} missing from {file_path}"


def test_windows_exe_version_resource_and_spec_are_release_ready() -> None:
    version_info = read_text("version_info.txt")
    spec = read_text("LANFileTransfer.spec")

    assert 'StringStruct("CompanyName", "HaoXiang Huang")' in version_info
    assert 'StringStruct("ProductName", "LAN File Transfer")' in version_info
    assert 'StringStruct("FileVersion", "1.0.0")' in version_info
    assert 'StringStruct("ProductVersion", "1.0.0")' in version_info
    assert "Email: didadida1688@gmail.com" in version_info
    assert "Homepage: https://nextweb4.github.io/" in version_info
    assert "version=str(VERSION_FILE)" in spec


def test_release_publish_method_is_documented_without_runtime_dependency() -> None:
    audit = read_text("docs/OPEN_SOURCE_AUDIT.md")

    assert "GitHub REST API 直接发布" in audit
    assert "采用" in audit
    assert "release-assets/*" in audit
    assert "未新增应用运行期依赖" in audit
    assert "缺少 `workflow` scope" in audit


def test_readme_contains_required_bilingual_release_sections() -> None:
    readme = read_text("README.md")

    for heading in (
        "项目类型 / Project Type",
        "功能特点 / Features",
        "安装方法 / Installation",
        "使用方法 / Usage",
        "打包说明 / Packaging",
        "作者信息 / Author",
        "License",
    ):
        assert heading in readme

    assert "lan-file-transfer-v1.0.0-windows.zip" in readme
    assert "MIT License. See [LICENSE](LICENSE)." in readme
