# Initial Clean Release v1.0.0

## 中文

LAN File Transfer 是一个 Windows 本地局域网文件传输工具。它使用 Python Tkinter 提供桌面窗口，使用 FastAPI/uvicorn 提供本地 HTTP 服务，并提供原生 HTML/CSS/JavaScript 的用户页和管理员页。

### 下载说明

- `LANFileTransfer.exe`：Windows 单文件可执行程序，双击即可运行。
- `lan-file-transfer-v1.0.0-windows.zip`：包含 `LANFileTransfer.exe` 的压缩包，适合下载后解压运行或归档保存。
- `SHA256SUMS.txt`：发布文件的 SHA256 校验值。

### 主要功能

- 同一 Wi-Fi / 局域网内通过浏览器上传、下载和打包文件。
- 游客、普通用户、管理员三类权限；游客只能访问公开文件。
- 管理员可创建用户、批量创建普通用户、管理用户组、设置文件可见组和查看审计日志。
- 保留原始二进制内容，计算 SHA-256，尽量保留文件修改时间。
- Web UI 支持中文 / English 切换，并保存语言偏好。

### 作者信息

- 作者：HaoXiang Huang
- 邮箱：didadida1688@gmail.com
- 主页：https://nextweb4.github.io/
- GitHub：https://github.com/NextWeb4
- 仓库：https://github.com/NextWeb4/lan-file-transfer

### 许可协议

MIT License。

## English

LAN File Transfer is a local Windows LAN file-transfer tool. It uses a Python Tkinter desktop window, a FastAPI/uvicorn local HTTP service, and vanilla HTML/CSS/JavaScript user and admin pages.

### Downloads

- `LANFileTransfer.exe`: Windows one-file executable. Double-click to run.
- `lan-file-transfer-v1.0.0-windows.zip`: Zip archive containing `LANFileTransfer.exe`, useful for extraction or archival.
- `SHA256SUMS.txt`: SHA256 checksums for release files.

### Highlights

- Upload, download, and zip files from browsers on the same Wi-Fi / LAN.
- Guest, user, and admin permissions. Guests can only access public files.
- Admins can create users, batch-create user accounts, manage groups, set file visibility groups, and inspect audit logs.
- Preserves original binary content, records SHA-256, and attempts to preserve file modification times.
- Web UI supports Chinese / English switching and stores the language preference.

### Author

- Author: HaoXiang Huang
- Email: didadida1688@gmail.com
- Homepage: https://nextweb4.github.io/
- GitHub: https://github.com/NextWeb4
- Repository: https://github.com/NextWeb4/lan-file-transfer

### License

MIT License.
