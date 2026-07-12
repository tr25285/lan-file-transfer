# Open Source Audit

## 当前项目审计结论

- 项目是 Windows 本地局域网文件传输工具，核心风险是文件内容被改写、mtime 丢失、路径穿越、游客/用户绕过权限、普通用户删除他人文件和管理员密码暴力尝试。
- 技术栈采用 Python 后端、本地 Tkinter 桌面壳、原生 HTML/CSS/JS 前端。
- 运行期不需要云服务，不引入远程 SDK，不在服务端上传文件到第三方。
- 标准库覆盖 SHA-256、PBKDF2 密码哈希、mtime、zip、日志、路径、session token 和 Tkinter 基础 GUI；第三方依赖只覆盖 HTTP 框架、ASGI 服务、multipart 解析、二维码和打包。

## 方案对比

| 方案名称 | 来源 | 许可证 | 核心能力 | 优点 | 缺点 | 维护状态 | 与当前项目的契合度 | 可能冲突点 | 是否采用 | 采用方式 |
|---|---|---|---|---|---|---|---|---|---|---|
| Python + FastAPI + uvicorn + PyInstaller | [FastAPI](https://github.com/fastapi/fastapi), [uvicorn](https://github.com/encode/uvicorn), [PyInstaller](https://pyinstaller.org/en/stable/license.html) | FastAPI: MIT；uvicorn: BSD；PyInstaller: GPL with bootloader exception | 本地 HTTP API、ASGI 服务、Windows exe 打包 | 开发快，代码可读，测试容易，和标准库文件处理组合好 | exe 体积比 Rust/Tauri 大 | 已在项目中使用 | 高 | PyInstaller 许可证需要保留说明；uvicorn 监听 `0.0.0.0` 必须提示风险 | 采用 | FastAPI 提供 API，uvicorn 本地启动，PyInstaller 打包桌面入口 |
| Tauri + Rust | [Tauri](https://github.com/tauri-apps/tauri) | MIT / Apache-2.0 | 轻量桌面壳和 Rust 后端 | exe 更轻，性能好 | MVP 开发和调试成本高，Windows 文件/HTTP/multipart/GUI 一起实现更复杂 | 未纳入当前项目 | 中 | 会重写当前 Python/Tkinter/FastAPI 架构 | 不采用 | 后续需要更小体积时可重评 |
| Python 标准库 `hashlib` / `hmac` / `secrets` / `os.utime` / `zipfile` / `tkinter` | Python 标准库 | PSF | 密码哈希、session token、SHA-256、mtime、zip、GUI | 无额外依赖，离线，行为透明，测试容易 | 账户、组、session、锁定策略需要自研并测试 | 随 Python 维护 | 高 | 自研鉴权必须避免明文密码、固定 token、未限制错误次数和权限绕过 | 采用 | 用 PBKDF2-HMAC-SHA256 加盐保存密码；用内存 session 控制用户/管理员权限 |
| HTTP Content-Disposition 文件名编码 | [MDN Content-Disposition](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Disposition), RFC 5987 / RFC 6266 | 标准规范 | 下载文件名 fallback 与 UTF-8 `filename*` | 不引入依赖，浏览器兼容性更好，避免把路径分隔符暴露成文件名路径 | 只能影响响应头，不能保证目标系统落盘 mtime 或最终文件名策略 | 标准长期稳定 | 高 | 必须继续使用本地文件名清理，不能把 header 编码当作路径安全 | 采用 | 自研 `content_disposition()`，ASCII fallback 清理危险字符，`filename*` 使用 UTF-8 百分号编码且不保留 `/` |
| `qrcode` + Pillow | [python-qrcode](https://github.com/lincolnloop/python-qrcode), [Pillow](https://github.com/python-pillow/Pillow) | qrcode: BSD；Pillow: HPND | 生成二维码并在 Tkinter 显示 | 小依赖，离线生成，成熟 | Pillow 增加打包体积 | 已在项目中使用 | 高 | 需由 PyInstaller 收集 Pillow/Tk 资源 | 采用 | 仅用于桌面二维码 |
| `python-multipart` | [python-multipart](https://github.com/Kludex/python-multipart) | Apache-2.0 | FastAPI multipart 表单上传解析 | FastAPI 常用搭配，支持文件上传 | 业务代码仍必须按 chunk 保存，不能一次性读入内存 | 已在项目中使用 | 高 | 不能把 `UploadFile` 一次性 `read()` 到内存 | 采用 | 作为 FastAPI 上传依赖，业务代码按 chunk 读取 |
| Passlib / bcrypt | [passlib](https://passlib.readthedocs.io/), [bcrypt](https://github.com/pyca/bcrypt) | 多为 BSD / Apache 类宽松许可证 | 密码哈希框架和 bcrypt | 算法封装成熟 | 当前本地 LAN 工具只需要账户密码哈希；新增依赖和打包面超过收益 | 未纳入当前项目 | 中 | 需要新增依赖、更新打包和许可证说明 | 不采用 | 只借鉴“加盐慢哈希”的设计；实际使用标准库 PBKDF2 |
| File Browser | https://github.com/filebrowser/filebrowser；https://filebrowser.org/cli/filebrowser-users-rm.html；https://github.com/filebrowser/filebrowser/security/advisories/GHSA-79pf-vx4x-7jmm | Apache-2.0 | Web 文件管理、用户权限、上传下载、用户删除 | 成熟的角色/权限模型，移动端文件列表成熟；CLI/API 中有用户删除等管理能力 | Go 单体服务，直接替换会重写现有 Python/Tkinter 架构；2026 年删除权限绕过公告提示删除能力必须严格复用权限校验 | 未纳入当前项目 | 中 | 引入后会替换大量已完成代码，打包路径变化大；权限模型不能黑盒套用 | 不采用 | 只借鉴“管理员最高权限、用户可写自己文件、组可见性、用户/组管理必须有删除入口和删除权限检查”的边界 |
| 文件管理器审计日志设计 | GitHub / Google 上 File Browser、Nextcloud、Pydio 等文件管理器公开文档和实现 | 不直接复用代码 | 上传、下载、删除、权限和账户变更追溯 | 能回答“谁在什么时候对哪个对象做了什么”，有利于排错和权限审计 | 若直接引入第三方审计组件通常需要数据库或复杂权限模型 | 仅审计设计 | 高 | 不应引入数据库、云服务或记录明文密码/文件内容 | 部分借鉴 | 自研 JSONL 审计日志 `.lan-transfer-audit.jsonl`，管理员只读查看最近事件 |
| LocalSend | https://github.com/localsend/localsend | MIT | 局域网跨平台文件传输 | 局域网优先、无云服务的产品边界清晰 | Flutter/Dart 架构，不适合当前 FastAPI MVP | 未纳入当前项目 | 中 | 需要安装客户端，不符合浏览器访问目标 | 不采用 | 只借鉴局域网离线优先和移动端易操作思路 |
| 常见 Web 文件管理器交互 | GitHub / Google 上的 File Browser、Nextcloud、Pydio 等同类产品公开设计 | 不直接复用代码 | 搜索、排序、批量用户、权限选择器、折叠工具面板 | 能直接改善大量文件和大量用户场景 | 直接引入会带来大型依赖、数据库和许可证复杂度 | 仅审计设计 | 高 | 不应破坏离线单 exe、无数据库和原生 HTML/JS 约束 | 部分借鉴 | 自研轻量搜索/排序、搜索输入 debounce、批量创建和可搜索组选择器 |

## 采用说明

- 直接复用：FastAPI 路由和依赖注入、uvicorn 本地 ASGI 服务、python-multipart 上传解析、qrcode/Pillow 二维码、PyInstaller 打包。
- 直接使用标准库：`hashlib.pbkdf2_hmac`、`hmac.compare_digest`、`secrets.token_urlsafe`、`os.utime`、`zipfile`、`tkinter`。
- 只借鉴：Tauri/Rust 的轻量桌面方向，File Browser 的账户/组权限边界和用户删除管理能力，常见文件管理器的搜索/排序/批量管理/折叠工具面板/审计日志，Passlib/bcrypt 的慢哈希思想。
- 不采用：任何云存储、远程中转、图片/视频处理库、自动转码库、Passlib/bcrypt 新依赖。
- 需要适配的模块：`lan_transfer/api.py` 负责 HTTP 和权限过滤；`lan_transfer/auth.py` 负责账户、组和 session；`lan_transfer/storage.py` 负责文件流式写入、manifest、zip；`lan_transfer/desktop.py` 负责 Windows 本地 GUI 和服务启停。
- 保留的自研代码：路径安全、同名文件去重、manifest 格式、zip 条目 mtime、下载 header 组装、账户/组权限。
- 替换的自研逻辑：不自研 HTTP server、multipart parser、二维码编码器和 exe 打包器。

## 部署前冲突检查

- 技术栈：Python + Tkinter + FastAPI 兼容 Windows 本地桌面运行。
- 目录结构：后端、前端、测试、文档、脚本已分离。
- 运行方式：`python -m lan_transfer.desktop` 与 PyInstaller 桌面入口一致。
- 构建方式：`scripts/build_exe.ps1` 建立虚拟环境、安装依赖、运行 pytest、打包 exe。
- 数据库：无数据库；文件状态由保存目录下 `manifest.json` 管理，账户/组状态由 `.lan-transfer-auth.json` 管理。
- 配置系统：默认创建 `admin / 12345678`、`public` 组和 `everyone` 组；旧 `default` 组在 auth settings 和 manifest 中启动迁移，不与文件内容混写。
- 权限模型：游客只看 public；登录用户上传并删除自己的文件；用户组决定文件可见性；管理员最高权限。
- 状态接口：游客不需要本机 Windows 保存目录或默认密码，`/api/status` 只对已登录用户返回 `save_dir`，状态接口不返回 `default_password`。
- 错误响应：FastAPI 默认请求校验错误会包含无效字段的 `input`；当前项目覆盖为固定 422 文案，避免密码或 token 在错误响应中被反射。
- Session 刷新：`/api/session` 和 `/api/admin/session` 可刷新下载 cookie，但不在 JSON 中回显 session token。
- 删除模型：删除用户会把其已上传文件转给管理员，并在账户删除后再次回扫 owner，防止并发上传窗口或同名新用户继承旧文件删除权；删除组只允许删除未被用户或文件引用的非内置组，并在删除后重新检查引用，防止静默扩大或收窄文件可见性。若删除后重检发现新引用但 auth 快照恢复失败，必须返回 500，因为此时不能假装已回滚。
- UI 模式：默认中文，前端本地字典切换英文；不依赖远程翻译和字体服务。
- UI 字号：字号使用固定尺寸和媒体查询断点，不使用 viewport width 驱动 `font-size`，避免宽窄屏文字比例漂移。
- UI 背景：保持低噪声工具型界面，不使用装饰性 radial gradient / orb / bokeh 背景；当前背景仅保留细网格和纯色底。
- 批量管理：批量创建账户在 `auth.py` 内先完整校验再写入，避免半批次成功；批量接口只创建普通 `user` 账户，管理员角色必须走单个用户创建或更新接口显式设置。
- 搜索/排序：`/api/files` 先按 session 过滤可见文件，再搜索和排序，避免通过搜索泄漏无权限文件。
- 审计日志：使用保存目录内 JSONL 文件，不新增数据库；记录操作者、IP、动作、目标和必要元数据，不记录明文密码、session token、authorization、cookie、secret 或文件内容。
- 离线 / 联网模式：运行期只服务局域网 HTTP，不依赖云服务；依赖安装和打包阶段需要从 Python 包仓库下载。
- 许可证：运行依赖多为宽松许可证；PyInstaller 需保留 bootloader exception 说明；本轮未新增依赖。
- 用户需求：满足优先方案 A；不引入会压缩、转码或改写文件内容的库。

## 第一性原理审计

- 权限不变量：磁盘状态改变必须来自已登录用户或管理员。游客不能上传/删除；普通用户只能删除 owner 为自己的文件；管理员可操作所有文件。
- 删除不变量：删除账户不能删除文件内容，也不能让未来同名账户获得旧文件 owner 权限；删除用户后必须把旧文件 owner 转给管理员。删除用户审计失败时，只有账户快照恢复成功后才能把文件 owner 恢复为被删用户；如果账户恢复失败，文件必须继续归 `admin`。删除组不能改变既有文件可见性，内置组和被引用组必须拒绝删除；如果删除后重检发现新引用，先尝试恢复 auth 快照，恢复失败则返回 500。文件删除 rollback 中只要原文件已恢复，内存 manifest 也必须保留对应记录，即使最后一次 manifest 写回失败。强审计 auth 变更必须串行覆盖 snapshot、写入、审计和回滚窗口，避免失败回滚覆盖并发成功变更；同时需要碰 storage 的跨模块路径必须保持 storage lock -> auth lock 的顺序，避免和上传提交路径互锁。
- 可见性不变量：用户只能看到自己拥有的文件、自己所在组可见的文件，游客只能看到 public 文件。列表、Raw 下载、单文件 zip 和批量 zip 都必须走同一套可见性过滤。用户页原生下载带 `scope=user` / `scope=guest` 时只能收窄权限，不能因为浏览器存在管理员 cookie 扩大下载范围。
- 账户不变量：密码不能明文保存，默认密码只用于初始化。当前用 PBKDF2-HMAC-SHA256、随机 salt 和常量时间比较；同一 IP 5 次错误后锁定 3 小时。普通用户改密、管理员重置用户密码、禁用用户和变更用户角色都必须失效该用户既有 session；审计失败时必须恢复旧密码和旧 session。auth 快照恢复写盘失败时必须回到调用前内存状态，避免进程内账户/session 与磁盘 settings 分叉。
- 下载时间不变量：HTTP 服务只能传递文件内容和响应头，不能强制浏览器把落盘文件 mtime 写成原始时间。Raw 下载继续设置 `Last-Modified`；zip entry 使用原始 `lastModified`；zip 响应也设置 `Last-Modified`。旧/坏 manifest 中的非法 mtime 字段只能降级到文件系统时间或省略响应时间，不能让 zip 接口 500。zip entry 名称必须按大小写不敏感规则去重，避免 Windows 解压时 `Photo.jpg` 和 `photo.jpg` 互相覆盖。zip 构建、metadata 设置或审计失败必须尝试清理临时文件；清理失败只能写日志，不能掩盖原始 HTTP 错误。
- 下载文件名不变量：`Content-Disposition` 只能表达下载建议文件名，不能信任 manifest 中的旧文件名形态；ASCII fallback 必须清理路径分隔符、引号、分号和控制字符，UTF-8 `filename*` 必须百分号编码 `/` 等分隔符。
- 上传内容不变量：上传文件内容只能作为二进制流保存和计算 hash，不能被前端或后端转码、压缩、重命名扩展名或改写 metadata。上传 manifest 记录在审计成功前必须保持 pending 且不可见；发布为 complete 和写上传审计必须处于同一 manifest 锁窗口，发布失败不能写成功审计。权限变更必须锁住 manifest 更新、审计和回滚窗口，避免审计完成前暴露未确认的新可见性。
- zip 唯一性不变量：一个 zip 内不应出现重复 entry 名。批量 zip 使用原始相对路径，重复时使用保存路径或追加序号。
- 批量创建不变量：一批账户要么全部创建，要么全部拒绝。重复用户名、已有用户名、非法组、短密码都必须阻止整批写入。
- 搜索排序不变量：搜索和排序是可见文件集合上的展示操作，不得改变权限边界或磁盘文件内容。前端可以 debounce 搜索输入降低请求抖动，但结果集合必须继续来自后端 `/api/files`。旧/坏 manifest 中非数字的 `file_size` 或 `server_mtime` 只能影响排序位置，必须按 0 降级，不能让列表接口返回 500。
- 组选择不变量：前端只能从后端已有组列表渲染选择器；不能让管理员手写不存在的组并绕过校验。
- 审计不变量：成功的上传、下载、删除、权限修改、账户和组变更应可追溯；强审计变更在审计写入失败时必须回滚本次状态变化。已认证用户不得通过错误角色的身份接口产生未审计 session 状态变更；游客清理无效 cookie 不改变服务端状态，可以无审计。审计 metadata 必须递归脱敏密码、session token、authorization、cookie 和 secret 类字段，snake_case、kebab-case、camelCase、PascalCase 与 `Set-Cookie`、`sessionId`、`authCookie` 等复合键都要覆盖，不误删 `sha256` 等完整性哈希。
- 原生下载 session 不变量：列表、上传和状态刷新可以带自定义 session header，但浏览器原生 Raw/zip 导航不能带自定义 header；因此 `/api/status`、`/api/session` 和 `/api/admin/session` 在 header token 有效时必须刷新 same-origin cookie，且不能在 JSON 里回显 session token。
- 错误响应不变量：输入校验是“请求格式不成立”，不是业务失败；服务端不能把无效请求体原样回显到 422 响应里，尤其不能反射 password、token 或 session 类字段。
- 桌面服务状态不变量：桌面按钮触发的启动、停止、关闭窗口和保存目录切换必须把 uvicorn 线程状态、用户提示、日志 handler 和窗口状态显示保持一致；停止失败不能作为未处理 Tkinter 回调异常冒出，也不能直接销毁窗口。线程存活但未 ready 时仍要视为 active，不能显示为 stopped；服务启动后状态栏必须周期刷新，避免后台线程退出后继续显示 Running。端口探测必须跳过已绑定监听端口，不能用 socket 复用选项制造假阳性。启动线程在 ready 前退出时必须清理 lifecycle 引用；启动超时且停止失败时必须保留 live thread 语义供 UI 停止。新保存目录的端口探测、storage 初始化、日志切换、server 创建和替换服务启动必须处于同一失败回滚路径内，新服务启动成功前不能提交窗口状态。
- URL 一致性不变量：同一个 `AppConfig` 实例展示的 `lan_ip`、`base_url`、`user_url` 和 `admin_url` 必须来自同一次 LAN IP 解析，不能在同一状态响应或桌面刷新中混用不同地址。
- 控制文件不变量：保存目录根部的 `manifest.json`、`manifest.json.tmp`、`.lan-transfer-auth.json`、`.lan-transfer-audit.jsonl` 属于应用状态或历史状态临时名，用户上传同名文件必须改名，不能占用或污染控制文件。manifest 和 auth settings 写入必须使用用户上传不可到达的隐藏随机临时文件，写入、序列化或替换失败时必须清理临时文件；从 manifest 读取的 `saved_relative_path` 也必须重新校验，不能让旧/坏 manifest 指向控制文件。Windows 保存路径占用和 zip entry 去重都必须大小写不敏感，避免 `Photo.jpg` 和 `photo.jpg` 指向同一文件或解压冲突。

## 回滚方案

- 若 FastAPI/uvicorn 不适配，可保留 `storage.py`、`auth.py` 和前端协议，替换为标准库 `http.server` 或 Rust/Tauri 后端。
- 若 PyInstaller 打包失败，仍可用 `python -m lan_transfer.desktop` 运行；打包层可单独调整 spec。
- 若 qrcode/Pillow 收集失败，可临时隐藏二维码，保留 URL 文本和核心传输功能。
- 若标准库 PBKDF2 未来需要更强密码策略，可在 `auth.py` 内替换为 Passlib/bcrypt，并同步更新 `requirements.txt`、本文档和测试。

## 用户页同源 Cookie 权限边界审计

| 方案名称 | 来源 | 许可证 | 核心能力 | 优点 | 缺点 | 维护状态 | 与当前项目的契合度 | 可能冲突点 | 是否采用 | 采用方式 |
|---|---|---|---|---|---|---|---|---|---|---|
| Fetch credentials / same-origin cookie 行为 | [MDN Request.credentials](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials) | 文档参考，不引入代码 | 明确浏览器同源请求默认会携带/处理凭据的边界 | 不新增依赖；能解释管理员 cookie 为什么会影响用户页 API | 只能作为行为依据，不能替代服务端授权 | Web 标准长期稳定 | 高 | 如果用户页在游客态继续发送同源 cookie，会把管理员可见文件带入用户页 | 采用 | 用户页未确认普通用户身份时，请求状态和文件列表使用 `credentials: "omit"`；`Zip all` 提交当前可见文件 ID |
| 服务端授权与最小权限原则 | [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) | 文档参考，不引入代码 | 每个请求在服务端检查权限、按角色收敛访问范围 | 与现有 FastAPI 依赖注入契合；不改变离线模式 | 需要在用户端与管理员端 API 明确角色边界 | 持续维护 | 高 | 过度收敛不能破坏管理员页面现有 `/api/admin/*` 能力 | 采用 | `/api/login`、`/api/session`、`/api/logout`、`/api/password` 只接受普通 `user` 或游客清理无效 session；管理员继续使用 `/api/admin/*` |

本轮未采用新库。浏览器行为只作为约束来源，服务端最小授权原则落实在现有 `api.py`/`auth.py`，前端防护落实在 `user.js` 的角色判断、游客态 credentials 和可见 ID 打包策略中。
本轮同时让 `/api/status` 在有效 header token 下刷新 same-origin cookie，补齐“状态刷新成功但原生下载没有 header”的浏览器边界；响应 JSON 仍不回显 token。

## 管理员登出权限边界审计

| 方案名称 | 来源 | 许可证 | 核心能力 | 优点 | 缺点 | 维护状态 | 与当前项目的契合度 | 可能冲突点 | 是否采用 | 采用方式 |
|---|---|---|---|---|---|---|---|---|---|---|
| 服务端角色校验 | [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) | 文档参考，不引入代码 | 每个身份接口在服务端确认当前 principal 角色 | 最小改动；能阻止普通用户误调管理员登出接口造成未审计 session 删除 | 需要保留游客清理无效 cookie 的兼容行为 | 持续维护 | 高 | 不能把过期管理员本地 cookie 永久卡在前端 | 采用 | `/api/admin/logout` 对已认证非管理员返回 403；管理员才执行登出和审计；游客仍可清理本地 cookie |
| 前端隐藏管理员登出按钮 | 当前项目 `admin.js` | 项目内实现 | UI 上减少误点入口 | 不改后端 | 不能防止直接请求，也不能保证审计边界 | 当前维护 | 低 | 会把权限边界放到浏览器端 | 不采用 | 前端保留现有状态处理，权限边界放在后端 |
| 统一 `/api/logout` 端点 | 常见 Web 应用设计 | 不适用 | 所有角色共用一个登出接口 | 协议简单 | 当前项目用户端和管理员端同源 cookie 有明确角色隔离要求；统一端点容易再次混淆审计动作 | 成熟模式 | 中 | 需要重写前端和测试，并区分 audit action | 暂不采用 | 保留 `/api/logout` 与 `/api/admin/logout` 分离，只收紧错误角色行为 |

本轮未新增依赖，也未改变运行期联网行为。修复点限定在 `api.py` 的管理员登出角色边界，并补充 `tests/test_api.py` 回归测试。

## 前端重复提交防护审计

| 方案名称 | 来源 | 许可证 | 核心能力 | 优点 | 缺点 | 维护状态 | 与当前项目的契合度 | 可能冲突点 | 是否采用 | 采用方式 |
|---|---|---|---|---|---|---|---|---|---|---|
| 原生 `SubmitEvent.submitter` + 表单 `dataset` busy 标记 | [MDN SubmitEvent.submitter](https://developer.mozilla.org/en-US/docs/Web/API/SubmitEvent/submitter) | Web 标准文档参考，不引入代码 | 识别本次提交按钮，并在异步请求期间禁用提交入口 | 无依赖、离线、能覆盖登录/改密/创建账户/创建组等重复点击 | 只能防止同一页面的误操作，不替代服务端权限和唯一性校验 | Web 标准长期稳定 | 高 | 必须在 finally 中恢复按钮，避免网络失败后表单永久不可用 | 采用 | `user.js` / `admin.js` 增加 `runFormOnce()`，请求完成前用 `dataset.busy` 和 submitter disabled 阻止重复提交 |
| 原生 button disabled + `dataset` busy 标记 | [HTML button disabled attribute](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/disabled) | Web 标准文档参考，不引入代码 | 在异步状态变更期间禁用当前按钮 | 无依赖；适合删除、重置密码、启停用户、删组等非表单按钮 | 只能保护当前页面当前按钮；后端仍必须处理并发和重复请求 | Web 标准长期稳定 | 高 | 必须在 finally 中恢复按钮，避免请求失败后按钮永久不可用 | 采用 | `user.js` / `admin.js` 增加 `runButtonOnce()`，状态变更按钮请求完成前禁用自身 |
| Lodash debounce/throttle | [lodash](https://github.com/lodash/lodash) | MIT | 通用防抖/节流 | API 成熟，适合高频输入 | 为少量表单提交引入新依赖和打包体积，和当前原生前端约束不匹配 | 持续维护 | 低 | 会新增前端依赖；不能直接表达“请求完成前锁住提交” | 不采用 | 搜索输入已有原生 debounce；表单提交用本地 helper |
| 后端幂等键 | 通用 API 设计模式 | 不适用 | 以请求 ID 防止重复写入 | 可跨刷新、跨标签页防重复创建 | 当前接口没有客户端请求 ID；为本地桌面 LAN 工具增加协议复杂度超过收益 | 设计参考 | 中 | 需要改 API 协议和测试面；不能替代前端误点击反馈 | 暂不采用 | 保留现有后端唯一性和批量全量校验；如未来支持离线重试再评估 |

本轮未新增依赖。重复提交防护只改变前端交互状态，不改变 API 协议、权限模型、运行期网络边界或打包方式。

## 后端审计回滚一致性审计

| 方案名称 | 来源 | 许可证 | 核心能力 | 优点 | 缺点 | 维护状态 | 与当前项目的契合度 | 可能冲突点 | 是否采用 | 采用方式 |
|---|---|---|---|---|---|---|---|---|---|---|
| 现有 JSONL 审计 + prepare / commit / rollback | 当前项目 `audit.py`、`storage.py` | 项目内实现 | 删除前先进入 tombstone，审计成功后 commit，失败 rollback | 不新增数据库或依赖，符合本地 LAN 工具离线要求 | 需要额外处理 commit 失败后的补偿审计和 tombstone 路径占用 | 当前维护 | 高 | 若 commit 失败只留下 `file_deleted` 会与实际状态矛盾 | 采用 | 删除 commit 失败时恢复 manifest/原文件并追加 `file_delete_rolled_back`；同名上传把 `.delete` tombstone 视为占用 |
| 数据库事务 / SQLite 审计表 | SQLite 标准库模块或外部 ORM | SQLite public domain；ORM 视具体库 | 用事务同时提交 manifest/audit 状态 | 事务语义清晰 | 当前项目状态文件已是 JSON + 文件系统，迁移会扩大架构和打包测试面 | 成熟 | 中 | 不能把磁盘文件 unlink 与数据库事务真正原子化；引入迁移复杂度 | 不采用 | 保留 JSON 文件状态，局部加强回滚和隔离 |
| 后台清理队列 / quarantine 表 | 常见文件服务设计 | 不适用 | 对清理失败的文件做隔离和后续补偿 | 能避免未审计文件继续可见 | 完整队列对桌面单机工具偏重 | 设计参考 | 中 | 需要新状态机和 UI 暴露策略 | 部分采用 | 上传审计失败且物理清理失败时只标记 `audit_status=failed` 并从列表/下载/打包排除 |

本轮未新增依赖，也未改变运行期联网行为。后端改动限定在现有 `api.py` / `storage.py` 的审计一致性和路径占用边界。

## 审计日志脱敏审计

| 方案名称 | 来源 | 许可证 | 核心能力 | 优点 | 缺点 | 维护状态 | 与当前项目的契合度 | 可能冲突点 | 是否采用 | 采用方式 |
|---|---|---|---|---|---|---|---|---|---|---|
| 当前项目 key-part redaction | 当前项目 `audit.py` | 项目内实现 | 递归脱敏 JSONL 审计 metadata，按标准化 key 和 token 词表识别敏感字段 | 不新增依赖；与当前 JSONL 审计格式完全兼容；可直接覆盖 `Set-Cookie`、`sessionId`、`authCookie` 这类复合键 | 需要维护敏感字段词表，过宽会误伤统计字段 | 当前维护 | 高 | 词表过窄会漏脱敏，词表过宽会误伤非敏感统计字段 | 采用 | 继续用标准库 `re` 和递归遍历，扩展敏感 token 判断 |
| Python `logging.Filter` / formatter redaction | Python 标准库 | PSF | 对 logging record 做过滤或格式化 | 不新增依赖；可与现有 `logging` 集成 | 只覆盖 logging 记录，不适合当前 JSONL metadata 结构 | 稳定 | 中 | 不能直接修复 `audit.py` 的 JSON 元数据漏脱敏 | 不采用 | 保留项目内 JSONL 审计写入 |
| structlog processors | [structlog](https://github.com/hynek/structlog) | MIT / Apache-2.0 | 结构化日志处理链，可插入 redaction processor | 适合复杂日志流水线 | 需要新增依赖并改造现有审计写入与测试面 | 活跃维护 | 中 | 可能引入新的运行期包和配置复杂度 | 暂不采用 | 继续用标准库 + 项目内 redaction |

本轮未新增依赖，也未改变运行期联网行为。修复只扩展现有 `audit.py` 的敏感键识别，避免把日志管道重构成新框架。

## 认证会话一致性审计

| 方案名称 | 来源 | 许可证 | 核心能力 | 优点 | 缺点 | 维护状态 | 与当前项目的契合度 | 可能冲突点 | 是否采用 | 采用方式 |
|---|---|---|---|---|---|---|---|---|---|---|
| 现有内存 session + auth 快照回滚 | 当前项目 `auth.py` / `api.py` | 项目内实现 | 密码变更后失效用户 session；登录先校验密码再暴露禁用状态；审计失败时恢复旧密码和旧 session | 不新增依赖；符合本地单进程桌面工具；测试可直接覆盖内存和磁盘分叉 | session 随进程重启失效，不能跨进程共享 | 当前维护 | 高 | 回滚顺序错误会让旧 session 残留或让同名用户继承旧文件 | 采用 | `restore_state()` 仅在 settings 变化时写盘；删除用户审计失败先恢复 auth，成功后再恢复文件 owner |
| 数据库事务保存账户与审计 | SQLite / ORM 常见实现 | SQLite public domain；ORM 视具体库 | 用事务管理账户、session、审计关联状态 | 事务语义清楚 | 当前项目没有数据库；文件系统 owner 变更仍不能和 DB 完全原子 | 成熟 | 中 | 会扩大打包、迁移和离线状态管理面 | 不采用 | 保留 JSON settings + manifest，局部加强状态机和回归测试 |
| Passlib / bcrypt 统一密码管理 | [passlib](https://passlib.readthedocs.io/) / bcrypt | BSD / Apache-2.0 | 更丰富的密码哈希策略和迁移工具 | 适合多算法密码升级 | 不能解决 session 回滚顺序问题；新增依赖超过本轮收益 | 成熟但需维护依赖 | 中 | 需要改 requirements 和许可证记录 | 暂不采用 | 继续使用标准库 PBKDF2；未来提高密码策略时再评估 |

本轮未新增依赖，也未改变运行期联网行为。修复范围限定在 `auth.py` 的登录顺序、`restore_state()` 的纯 session 回滚路径、`api.py` 的删除用户回滚顺序和对应回归测试。

## 桌面生命周期一致性审计

| 方案名称 | 来源 | 许可证 | 核心能力 | 优点 | 缺点 | 维护状态 | 与当前项目的契合度 | 可能冲突点 | 是否采用 | 采用方式 |
|---|---|---|---|---|---|---|---|---|---|---|
| 现有 Tkinter + `LocalServer` 包装 | 当前项目 `desktop.py` / `server.py` | 项目内实现 | 桌面按钮管理 uvicorn 线程、目录切换和日志 handler | 不新增依赖；最小修复即可覆盖启动/停止/关闭/切目录边界 | 需要手写状态机测试 | 当前维护 | 高 | 线程 ready 前退出、切目录中途失败、关闭窗口停止失败都可能让 UI 状态误报 | 采用 | ready 前线程退出时清空 server/thread；线程存活但未 ready 时仍显示 active；切目录时先让替换服务在新配置上启动，再提交窗口状态 |
| Uvicorn Server 实例生命周期 | [Uvicorn docs](https://www.uvicorn.org/) | BSD-3-Clause | 通过 `Server` 对象启动/停止 ASGI 服务 | 已是当前依赖；无需引入服务管理框架 | `started` 和线程状态仍需本项目包装层处理 | 活跃维护 | 高 | 不应把服务线程失败静默吞掉 | 继续采用 | 只修正 `LocalServer.start()` 的失败清理，不改变依赖 |
| 缓存配置派生值 | [Python dataclasses `field`](https://docs.python.org/3/library/dataclasses.html#dataclasses.field) | Python 文档 / PSF | 在配置实例内保存一次 LAN IP 解析结果 | 标准库；保证同一状态刷新 URL 一致 | 网络切换后旧实例不会自动刷新 IP | 稳定 | 高 | 需要新建 `AppConfig` 才会刷新 LAN IP | 采用 | `AppConfig` 增加 `_lan_ip` 缓存，`base_url`、`user_url`、`admin_url` 共用 |
| 独占端口探测 | Python 标准库 `socket` | PSF | 用真实 bind 检查端口是否已被监听占用 | 不新增依赖；更接近 uvicorn 实际启动条件 | 不能避免探测后被其他进程抢占的竞态 | 稳定 | 高 | 使用 `SO_REUSEADDR` 会在 Windows 上制造假阳性 | 采用 | `find_available_port()` 不设置 `SO_REUSEADDR`，测试已绑定端口会被跳过 |
| 后台服务管理器 / watchdog | 第三方进程管理常见方案 | 视具体库 | 自动重启和监控服务 | 适合长期后台 daemon | 本项目是用户可见桌面工具，复杂度超过收益 | 成熟 | 低 | 会改变运行方式和打包模型 | 不采用 | 保留显式按钮和错误提示 |

本轮未新增依赖，也未改变运行期联网行为。桌面改动只收紧现有 Tkinter/uvicorn 生命周期边界，并把替换服务启动失败和端口探测假阳性纳入回滚路径。

## 前端身份刷新与可访问性审计

| 方案名称 | 来源 | 许可证 | 核心能力 | 优点 | 缺点 | 维护状态 | 与当前项目的契合度 | 可能冲突点 | 是否采用 | 采用方式 |
|---|---|---|---|---|---|---|---|---|---|---|
| 原生 session 刷新 + 请求序号 | 当前项目 `user.js` / `admin.js` | 项目内实现 | 渲染文件前重新确认当前角色；忽略过期成功和失败响应 | 不新增依赖；直接修正“session 失效但旧权限 UI 或旧状态行仍可见”的问题 | 只能保护当前页面状态，服务端仍必须授权每个请求 | 当前维护 | 高 | 过度刷新会增加本地请求次数，但仍在同源 LAN 内 | 采用 | 用户页文件刷新前确认 `/api/status` 仍是普通用户；管理员页文件刷新前确认 `/api/admin/session` 仍是管理员；管理员回登录态时清状态行 |
| WAI-ARIA / MDN accessible name | [MDN aria-label](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Attributes/aria-label) | Web 标准文档参考，不引入代码 | 为图标按钮、搜索框和下拉框提供可访问名称 | 原生 HTML 属性即可实现，适合当前无框架前端 | 需要随语言切换同步更新 | 标准长期稳定 | 高 | 不应把 aria-label 当作可见说明文字替代必要 UI | 采用 | 增加 `data-i18n-aria-label`，中英文切换时同步 `aria-label` |
| 避免嵌套交互控件 | [HTML content categories / interactive content](https://html.spec.whatwg.org/multipage/dom.html#interactive-content-2) | Web 标准文档参考，不引入代码 | 避免 `role="button"` 容器内再放真实按钮 | 保持键盘和辅助技术语义清晰 | 放弃整块 drop zone 键盘点击入口 | 标准长期稳定 | 高 | 上传入口必须仍可键盘操作 | 采用 | 拖拽区只负责 drag/drop，真实 `+` 按钮、文件按钮和文件夹按钮负责键盘操作 |
| 第三方无障碍/状态管理库 | axe-core、React Aria 等 | 视具体库 | 自动化规则或组件级无障碍能力 | 覆盖面广 | 当前项目是原生 HTML/JS 单页，运行期引入依赖和打包复杂度超过本轮收益 | 成熟 | 低 | 可能引入前端构建链或新运行期文件 | 不采用 | 用 contract tests 固化本轮可访问名称和嵌套交互边界 |

本轮未新增依赖，也未改变运行期联网行为。前端改动限定在静态 HTML/JS：角色刷新、过期响应忽略、accessible name 和拖拽区语义。

## Manifest 路径与原子写入审计

| 方案名称 | 来源 | 许可证 | 核心能力 | 优点 | 缺点 | 维护状态 | 与当前项目的契合度 | 可能冲突点 | 是否采用 | 采用方式 |
|---|---|---|---|---|---|---|---|---|---|---|
| Python 标准库 `os.replace` + 隐藏随机临时文件 | [Python `os.replace`](https://docs.python.org/3/library/os.html#os.replace), [Python `uuid`](https://docs.python.org/3/library/uuid.html) | PSF | 同目录临时文件写完后原子替换 manifest 和 auth settings | 不新增依赖；避开用户可上传的固定 `manifest.json.tmp`，也避免固定 auth 临时名残留 | 仍需项目自己清理失败临时文件 | 标准库长期维护 | 高 | 临时文件名必须是上传路径清理后不可到达的形态 | 采用 | `_write_manifest()` 与 auth `_write_settings()` 都写 `.<state>.<uuid>.tmp`，失败时删除临时文件 |
| OWASP 路径穿越防护原则 | [OWASP Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal) | 文档参考，不引入代码 | 拒绝绝对路径、`..` 和不可信路径逃逸 | 与现有 `security.py` 边界一致 | 需要结合 Windows 控制文件名和 manifest 兼容性落地 | 持续维护 | 高 | 不能只校验上传路径，manifest 旧路径也必须校验 | 采用 | `validate_stored_relative_parts()` 用于 manifest 保存路径读取；下载、zip、删除都经 `path_for_entry()` |
| `atomicwrites` | [python-atomicwrites](https://github.com/untitaker/python-atomicwrites) | MIT | 跨平台原子文件写入封装 | 设计成熟，减少手写临时文件逻辑 | 项目只需要一个 manifest 写入点；新增依赖、许可证记录和打包测试超过收益 | 维护状态需重评 | 中 | 可能引入不必要依赖；不能解决 manifest 路径校验 | 不采用 | 只借鉴“写临时文件后 replace”的设计，使用标准库实现 |
| 大小写敏感路径比较 | 当前旧实现 | 项目内实现 | 按字符串原样比较保存路径或 zip entry 名 | 简单 | Windows 上 `Photo.jpg` 与 `photo.jpg` 会别名，可能覆盖、指向同一文件或在解压时冲突 | 已替换 | 低 | 与目标平台文件系统语义冲突 | 不采用 | manifest 路径、tombstone 前缀和 zip entry 已用名按 NFC + `casefold()` 比较 |

本轮未新增依赖，也未改变运行期联网行为。修复范围限定在 `security.py` / `storage.py` 的保存路径校验、manifest 写入临时文件、Windows 路径占用语义和 zip entry 大小写去重；后续 auth settings 写入沿用同一标准库策略，失败时清理隐藏随机临时文件。

## GitHub Release 发布方案审计

| 方案名称 | 来源 | 许可证 | 核心能力 | 优点 | 缺点 | 维护状态 | 与当前项目的契合度 | 可能冲突点 | 是否采用 | 采用方式 |
|---|---|---|---|---|---|---|---|---|---|---|
| 本地 `gh release create` | GitHub CLI | MIT | 本机创建仓库、推送代码并上传 Release 资产 | 与用户给出的命令一致；可直接上传 exe/zip/SHA256 | 当前环境未安装 `gh`，不能直接使用用户给出的 CLI 命令 | 活跃维护 | 高 | 没有 CLI 时会阻塞命令式发布 | 暂不可用 | 若后续安装并登录 `gh`，可使用 `gh repo create` 和 `gh release create` |
| GitHub REST API 直接发布 | GitHub REST API | GitHub 平台功能 | 用本机 Git Credential Manager 中的 GitHub token 创建仓库、推送源码、创建 Release 并上传 assets | 不新增依赖；可在没有 `gh` 的环境完成发布；上传结果可通过 API 校验 | 依赖本机已有 GitHub 凭据；不得打印或提交 token；token 若缺少 scope 会阻塞对应操作 | 平台稳定 | 高 | 只允许用于发布阶段，不能引入应用运行期联网行为 | 采用 | PowerShell 调用 GitHub API 创建 `NextWeb4/lan-file-transfer`、Release `v1.0.0` 并上传 `release-assets/*` |
| GitHub Actions release workflow | `actions/checkout`、`actions/setup-python`、`softprops/action-gh-release` | MIT | tag 触发 Windows 构建、测试、PyInstaller 打包并上传 Release assets | 不需要本机 `gh`；使用 GitHub-hosted Windows runner；Release 上传使用仓库 `GITHUB_TOKEN` | 当前可用 token 没有 `workflow` scope，无法推送 `.github/workflows/release.yml` | 活跃维护 | 中 | workflow 只在 GitHub 上运行，不改变本地运行期；但缺少 `workflow` scope 会阻塞源码推送 | 不采用 | 保留设计审计，不随本次干净发布提交 |
| 手动网页上传 Release | GitHub Web UI | GitHub 平台功能 | 浏览器手动创建 Release 并上传文件 | 无需本地 CLI | 容易漏传 SHA256 或 Release Notes，不利于重复发布 | 平台稳定 | 中 | 需要人工操作，不能自动验证构建 | 仅作为兜底 | 如果 CLI 和 Actions 都不可用，保留 `release-assets/` 供手动上传 |

本轮采用 GitHub REST API 直接发布，不新增应用运行期依赖，不改变离线/LAN 运行边界。当前本机有 Git Credential Manager 凭据，可认证为 `NextWeb4` 并创建仓库；但该 token 缺少 `workflow` scope，不能推送 GitHub Actions workflow，因此不把 `.github/workflows/release.yml` 放入本次干净发布提交。

## 本轮依赖变化

- 未新增应用运行期依赖。
- 未新增 CI-only GitHub Actions 依赖；本轮使用 GitHub REST API 直接发布。
- 未引入云服务、CDN、远程中转或运行期外部网络请求。
- 未改变 PyInstaller 打包入口；`lan_transfer/static/` 仍整体打包进 exe。
- 搜索输入 debounce 使用原生 JavaScript，没有引入 lodash 或其他前端依赖。
- 字号调整仅修改 CSS，无新前端框架、字体服务或运行期网络资源。
- 背景调整仅删除装饰性 `radial-gradient`，无新资源和网络行为。
- 桌面停止失败提示继续使用现有 Tkinter `messagebox`，无许可证和架构变化。
- 本轮新增审计日志使用 Python 标准库 JSONL 文件，无许可证变化。
- Content-Disposition 文件名编码使用 Python 标准库 `urllib.parse.quote`，未新增依赖或运行期网络行为。
- FastAPI 请求校验错误处理继续使用现有异常处理机制，未新增依赖；只收敛响应内容，不改变 API 权限边界。
- 批量创建角色收敛为后端校验，不新增依赖；保留单个用户接口创建/更新管理员角色的能力。
