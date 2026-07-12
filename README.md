# LAN File Transfer

局域网文件传输是一个 Windows 本地桌面工具。启动后，它会在本机开启一个 FastAPI/uvicorn HTTP 服务，并通过 Tkinter 窗口显示用户地址、管理员地址和二维码。同一 Wi-Fi 或局域网内的手机、平板和电脑可以用浏览器上传、下载和打包文件。

LAN File Transfer is a local Windows desktop tool for sharing files across a LAN. It starts a FastAPI/uvicorn HTTP service from a Tkinter desktop window and shows user/admin URLs plus QR codes so phones, tablets, and computers on the same Wi-Fi or LAN can upload, download, and zip files in the browser.

## 项目类型 / Project Type

- Python desktop application: Tkinter GUI + FastAPI API + vanilla HTML/CSS/JavaScript frontend.
- Windows packaging: PyInstaller one-file windowed executable.
- Repository name selected for release: `lan-file-transfer`.
- Version: `1.0.0`.

## 功能特点 / Features

- 二进制流式保存上传文件，不压缩、不转码、不改写图片、视频、EXIF 或扩展名。
- Preserves uploaded bytes as binary streams without compression, transcoding, EXIF changes, or extension rewriting.
- 支持游客、普通用户和管理员三类身份；游客只能访问 `public` 组文件。
- Supports guest, user, and admin roles. Guests can only see files in the `public` group.
- 新保存目录自动创建默认管理员 `admin / 12345678`、`public` 组和 `everyone` 组。
- New save directories create default admin `admin / 12345678`, `public`, and `everyone`.
- 登录用户可上传文件并删除自己上传的文件；管理员可管理账户、组、文件权限、审计日志和所有文件。
- Signed-in users can upload and delete their own files. Admins can manage accounts, groups, permissions, audit logs, and all files.
- 文件列表支持搜索、排序、Raw 下载、单文件 zip 和批量 zip。
- File lists support search, sort, raw download, single-file zip, and batch zip.
- 尽量保存浏览器提供的 `File.lastModified`，Raw 下载设置 `Last-Modified`，zip entry 写入原始 mtime。
- Attempts to preserve browser `File.lastModified`; raw downloads set `Last-Modified`, and zip entries store original mtime.
- 审计日志记录登录、登出、上传、下载、删除、权限、账户和组变更，并递归脱敏 password、token、session、authorization、cookie、secret 字段。
- Audit logs cover login, logout, upload, download, delete, permission, account, and group changes, with recursive redaction for password, token, session, authorization, cookie, and secret fields.
- Web UI 默认中文，右上角可切换 English，语言状态保存到 `localStorage`。
- The web UI defaults to Chinese, can switch to English, and stores language state in `localStorage`.

## 安装方法 / Installation

### 使用发布版 / Use a Release Build

1. 从 GitHub Release 下载 `LANFileTransfer.exe` 或 `lan-file-transfer-v1.0.0-windows.zip`。
2. 如果下载 zip，解压后运行其中的 `LANFileTransfer.exe`。
3. Windows SmartScreen 可能提示未知发布者；本项目没有代码签名证书，不伪造数字签名。请只从项目 Release 页面下载。

1. Download `LANFileTransfer.exe` or `lan-file-transfer-v1.0.0-windows.zip` from GitHub Releases.
2. If you download the zip, extract it and run `LANFileTransfer.exe`.
3. Windows SmartScreen may show an unknown-publisher warning. This project does not include a code-signing certificate and does not fake a digital signature. Download only from the project Release page.

### 从源码运行 / Run from Source

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m lan_transfer.desktop
```

## 使用方法 / Usage

1. 启动桌面程序后等待状态变成 `Running`。
2. 用窗口中的 User URL 或二维码打开用户页。
3. 管理员打开 Admin URL，使用默认账户 `admin / 12345678` 登录，并在首次运行后立即修改管理员密码。
4. 管理员可创建普通用户和用户组，调整文件可见组，查看审计日志。
5. 普通用户登录后可上传文件、上传文件夹、删除自己上传的文件。
6. 手机浏览器如不能保留 Raw 下载文件的 mtime，建议使用 zip 下载并解压。

1. Start the desktop app and wait until the status is `Running`.
2. Open the user page from the User URL or QR code.
3. Open the Admin URL and sign in with `admin / 12345678`; change the admin password after first launch.
4. Admins can create users/groups, change file visibility groups, and inspect audit logs.
5. Users can upload files/folders and delete their own uploads.
6. If a mobile browser does not preserve mtime for raw downloads, use zip download and extract the archive.

## 打包说明 / Packaging

This project is a Python/Tkinter desktop app. The supported local package format in this repository is a Windows PyInstaller executable plus a zip archive. MSI is not generated because the project does not currently include a WiX/Inno/NSIS installer definition.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

The script installs dependencies, runs tests, and builds:

```text
dist\LANFileTransfer.exe
```

Release assets are prepared under `release-assets/`:

```text
LANFileTransfer.exe
lan-file-transfer-v1.0.0-windows.zip
SHA256SUMS.txt
```

## 测试 / Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
node --check .\lan_transfer\static\user.js
node --check .\lan_transfer\static\admin.js
```

Current coverage includes account permissions, batch user creation, group visibility, search/sort, upload integrity, mtime, download headers, zip behavior, path safety, duplicate filenames, audit rollback, desktop lifecycle, logging, and frontend contracts.

## 安全说明 / Security Notes

- 默认监听 `0.0.0.0`，方便局域网访问，也会向可达网络暴露服务。请只在可信局域网中运行。
- The service listens on `0.0.0.0` by default for LAN access. Run it only on trusted networks.
- 默认密码很弱，仅用于初始化。首次运行后请修改管理员密码和新建用户密码。
- The default password is intentionally simple for initialization. Change admin and user passwords after setup.
- 保存目录根部控制文件名 `manifest.json`、`manifest.json.tmp`、`.lan-transfer-auth.json`、`.lan-transfer-audit.jsonl` 会被上传路径安全逻辑保留。
- Root control filenames are reserved by upload path safety logic.
- manifest 和 auth settings 使用隐藏随机临时文件加原子替换写盘，失败时回滚内存状态并清理临时文件。
- Manifest and auth settings are written through hidden randomized temporary files plus atomic replacement; failures roll back memory state and clean temporary files.
- 审计失败时，登录、登出、改密、账户、组、上传、删除和权限变更会回滚本次状态。
- Required audit failures roll back login, logout, password, account, group, upload, delete, and permission changes.

## 作者信息 / Author

- Author: HaoXiang Huang
- Email: [didadida1688@gmail.com](mailto:didadida1688@gmail.com)
- Homepage: <https://nextweb4.github.io/>
- GitHub: <https://github.com/NextWeb4>
- Repository: <https://github.com/NextWeb4/lan-file-transfer>

## License

MIT License. See [LICENSE](LICENSE).
