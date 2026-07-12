const SESSION_KEY = "lanTransferUserSession";
const LANG_KEY = "lanTransferLang";

const dict = {
  zh: {
    appTitle: "局域网文件传输",
    tools: "工具",
    login: "登录",
    loginHint: "使用管理员创建的账号登录。",
    username: "用户名",
    password: "密码",
    account: "账户",
    currentPassword: "当前密码",
    newPassword: "新密码",
    changePassword: "修改密码",
    upload: "上传",
    chooseFiles: "选择文件",
    chooseFolder: "选择文件夹",
    uploadQueue: "上传队列",
    queueEmpty: "暂无上传",
    logout: "退出",
    refresh: "刷新",
    dropTitle: "拖拽文件到这里",
    dropHint: "登录用户可上传文件，并删除自己上传的文件。",
    files: "文件",
    searchFiles: "搜索文件",
    sortBy: "排序字段",
    sortDirection: "排序方向",
    sortUploaded: "上传时间",
    sortMtime: "修改时间",
    sortSize: "大小",
    sortName: "名称",
    sortOwner: "所有者",
    sortDesc: "降序",
    sortAsc: "升序",
    selectAll: "全选",
    clearSelection: "清除选择",
    selectedCount: "已选 {count}",
    zipSelected: "打包所选",
    zipAll: "全部打包",
    guest: "游客",
    noVisibleFiles: "暂无可见文件。",
    noPublicFiles: "暂无公开文件。登录后可查看组文件。",
    owner: "所有者",
    delete: "删除",
    raw: "原始",
    confirmDelete: "确定从 Windows 保存目录删除这个文件？",
    passwordChanged: "密码已修改，请重新登录。",
    uploading: "上传中",
    waiting: "等待中",
    networkError: "网络错误",
    sessionExpired: "登录已失效，请重新登录。",
    uploadSkippedAuth: "登录失效，已跳过",
    mtimeSet: "时间已设置",
    mtimeNotSet: "时间未设置",
    authorLine: "作者：HaoXiang Huang · didadida1688@gmail.com · https://nextweb4.github.io/ · https://github.com/NextWeb4",
  },
  en: {
    appTitle: "LAN File Transfer",
    tools: "Tools",
    login: "Login",
    loginHint: "Use the account created by admin.",
    username: "Username",
    password: "Password",
    account: "Account",
    currentPassword: "Current password",
    newPassword: "New password",
    changePassword: "Change password",
    upload: "Upload",
    chooseFiles: "Files",
    chooseFolder: "Folder",
    uploadQueue: "Upload queue",
    queueEmpty: "No uploads yet.",
    logout: "Logout",
    refresh: "Refresh",
    dropTitle: "Drop files here",
    dropHint: "Signed-in users can upload files and delete their own uploads.",
    files: "Files",
    searchFiles: "Search files",
    sortBy: "Sort by",
    sortDirection: "Sort direction",
    sortUploaded: "Uploaded",
    sortMtime: "Modified",
    sortSize: "Size",
    sortName: "Name",
    sortOwner: "Owner",
    sortDesc: "Desc",
    sortAsc: "Asc",
    selectAll: "Select all",
    clearSelection: "Clear",
    selectedCount: "{count} selected",
    zipSelected: "Zip selected",
    zipAll: "Zip all",
    guest: "Guest",
    noVisibleFiles: "No visible files.",
    noPublicFiles: "No public files. Login to see group files.",
    owner: "Owner",
    delete: "Delete",
    raw: "Raw",
    confirmDelete: "Delete this file from the Windows save directory?",
    passwordChanged: "Password changed. Login again.",
    uploading: "Uploading",
    waiting: "Waiting",
    networkError: "Network error",
    sessionExpired: "Session expired. Login again.",
    uploadSkippedAuth: "Auth failed, skipped",
    mtimeSet: "mtime set",
    mtimeNotSet: "mtime not set",
    authorLine: "Author: HaoXiang Huang · didadida1688@gmail.com · https://nextweb4.github.io/ · https://github.com/NextWeb4",
  },
};

const state = {
  sessionToken: localStorage.getItem(SESSION_KEY) || "",
  lang: localStorage.getItem(LANG_KEY) || "zh",
  files: [],
  fileRequestSeq: 0,
  statusRequestSeq: 0,
  user: null,
  queue: [],
};

const els = {
  statusLine: document.querySelector("#statusLine"),
  languageSelect: document.querySelector("#languageSelect"),
  roleBadge: document.querySelector("#roleBadge"),
  loginPanel: document.querySelector("#loginPanel"),
  loginForm: document.querySelector("#loginForm"),
  usernameInput: document.querySelector("#usernameInput"),
  passwordInput: document.querySelector("#passwordInput"),
  authMessage: document.querySelector("#authMessage"),
  logoutButton: document.querySelector("#logoutButton"),
  accountPanel: document.querySelector("#accountPanel"),
  passwordForm: document.querySelector("#passwordForm"),
  currentPassword: document.querySelector("#currentPassword"),
  newPassword: document.querySelector("#newPassword"),
  accountMessage: document.querySelector("#accountMessage"),
  uploadPanel: document.querySelector("#uploadPanel"),
  dropZone: document.querySelector("#dropZone"),
  plusButton: document.querySelector("#plusButton"),
  fileInput: document.querySelector("#fileInput"),
  folderInput: document.querySelector("#folderInput"),
  fileButton: document.querySelector("#fileButton"),
  folderButton: document.querySelector("#folderButton"),
  queue: document.querySelector("#queue"),
  queueCount: document.querySelector("#queueCount"),
  refreshButton: document.querySelector("#refreshButton"),
  fileList: document.querySelector("#fileList"),
  searchInput: document.querySelector("#searchInput"),
  sortBySelect: document.querySelector("#sortBySelect"),
  sortDirSelect: document.querySelector("#sortDirSelect"),
  selectAllButton: document.querySelector("#selectAllButton"),
  clearSelectionButton: document.querySelector("#clearSelectionButton"),
  zipSelectedButton: document.querySelector("#zipSelectedButton"),
  zipAllButton: document.querySelector("#zipAllButton"),
  selectionCount: document.querySelector("#selectionCount"),
};

function t(key) {
  return dict[state.lang]?.[key] || dict.zh[key] || key;
}

function applyI18n() {
  document.documentElement.lang = state.lang === "zh" ? "zh-CN" : "en";
  els.languageSelect.value = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.placeholder = t(node.dataset.i18nPlaceholder);
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((node) => {
    node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel));
  });
  if (els.queue.classList.contains("empty")) els.queue.textContent = t("queueEmpty");
  renderSession();
  renderFiles();
}

function apiUrl(path) {
  return new URL(path, window.location.origin);
}

async function fetchJson(path, options = {}) {
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: {
      ...(state.sessionToken ? { "X-User-Session": state.sessionToken } : {}),
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail?.message || data.detail || `HTTP ${response.status}`);
  return data;
}

function errorText(detail, fallback) {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (typeof detail.message === "string") return detail.message;
  return JSON.stringify(detail);
}

async function postJson(path, payload) {
  return fetchJson(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function formatBytes(bytes) {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatDate(value) {
  if (!value) return "-";
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString(state.lang === "zh" ? "zh-CN" : "en-US");
}

function formatDateMs(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString(state.lang === "zh" ? "zh-CN" : "en-US");
}

function setSession(token) {
  state.sessionToken = token || "";
  if (state.sessionToken) localStorage.setItem(SESSION_KEY, state.sessionToken);
  else localStorage.removeItem(SESSION_KEY);
}

function isUserPagePrincipal(user) {
  return Boolean(user?.username) && user.role === "user";
}

function showAuthMessage(message, type = "") {
  els.authMessage.className = `auth-message ${type}`;
  els.authMessage.textContent = message || "";
}

function showAccountMessage(message, type = "") {
  els.accountMessage.className = `auth-message ${type}`;
  els.accountMessage.textContent = message || "";
}

function selectedIds() {
  return [...document.querySelectorAll("[data-file-select]:checked")].map((input) => input.value);
}

function fileSelectInputs() {
  return [...document.querySelectorAll("[data-file-select]")];
}

function updateSelectionButtons() {
  const boxes = fileSelectInputs();
  const selectedCount = selectedIds().length;
  els.selectAllButton.disabled = boxes.length === 0 || selectedCount === boxes.length;
  els.clearSelectionButton.disabled = selectedCount === 0;
  els.zipSelectedButton.disabled = selectedCount === 0;
  els.zipAllButton.disabled = boxes.length === 0;
  els.selectionCount.textContent = t("selectedCount").replace("{count}", String(selectedCount));
}

function setAllFileSelections(checked) {
  for (const input of fileSelectInputs()) {
    input.checked = checked;
  }
  updateSelectionButtons();
}

function userDownloadScope() {
  return isUserPagePrincipal(state.user) ? "user" : "guest";
}

function addUserDownloadScope(url) {
  url.searchParams.set("scope", userDownloadScope());
  return url;
}

function zipDownload(ids) {
  const url = addUserDownloadScope(apiUrl("/api/download.zip"));
  for (const id of ids) url.searchParams.append("ids", id);
  window.location.href = url.toString();
}

function resetFilesAfterPrincipalChange() {
  state.fileRequestSeq += 1;
  state.statusRequestSeq += 1;
  state.files = [];
  renderFiles();
}

function shortHash(hash) {
  return hash ? `${hash.slice(0, 12)}...${hash.slice(-8)}` : "-";
}

function filesQueryPath() {
  const url = apiUrl("/api/files");
  url.searchParams.set("sort_by", els.sortBySelect.value);
  url.searchParams.set("sort_dir", els.sortDirSelect.value);
  const search = els.searchInput.value.trim();
  if (search) url.searchParams.set("search", search);
  return `${url.pathname}${url.search}`;
}

async function initSession() {
  applyI18n();
  try {
    const session = await fetchJson("/api/session");
    state.user = isUserPagePrincipal(session.user) ? session.user : null;
    if (!state.user) setSession("");
  } catch {
    const hadStoredToken = Boolean(state.sessionToken);
    setSession("");
    if (hadStoredToken) {
      try {
        const session = await fetchJson("/api/session");
        state.user = isUserPagePrincipal(session.user) ? session.user : null;
        if (!state.user) setSession("");
      } catch {
        state.user = null;
      }
    } else {
      state.user = null;
    }
  }
  renderSession();
  await refreshUserView();
}

function renderSession() {
  const signedIn = isUserPagePrincipal(state.user);
  document.body.dataset.role = signedIn ? "user" : "guest";
  els.loginPanel.classList.toggle("hidden", signedIn);
  els.accountPanel.classList.toggle("hidden", !signedIn);
  els.uploadPanel.classList.toggle("hidden", !signedIn);
  els.dropZone.classList.toggle("hidden", !signedIn);
  els.logoutButton.classList.toggle("hidden", !signedIn);
  els.roleBadge.textContent = signedIn ? `${state.user.username}` : t("guest");
  const roleClass = signedIn ? "role-user" : "role-download";
  els.roleBadge.className = `role-badge ${roleClass}`;
}

async function loadStatus() {
  const requestId = ++state.statusRequestSeq;
  try {
    const status = await fetchJson("/api/status", {
      credentials: isUserPagePrincipal(state.user) ? "same-origin" : "omit",
    });
    if (requestId !== state.statusRequestSeq) return null;
    if (status.role !== "user" || !status.username) {
      if (state.user || state.sessionToken) {
        state.user = null;
        setSession("");
        resetFilesAfterPrincipalChange();
        renderSession();
      }
      els.statusLine.textContent = [status.base_url, t("guest")].filter(Boolean).join(" | ");
      return false;
    }
    const identity = status.username ? `${status.username} | ${status.groups.join(", ")}` : t("guest");
    els.statusLine.textContent = [status.base_url, identity, status.save_dir].filter(Boolean).join(" | ");
    return true;
  } catch (error) {
    if (requestId !== state.statusRequestSeq) return null;
    throw error;
  }
}

async function loadFiles({ validateStatus = true } = {}) {
  const requestId = ++state.fileRequestSeq;
  try {
    if (validateStatus && isUserPagePrincipal(state.user)) {
      const statusCurrent = await loadStatus();
      if (statusCurrent === null) return;
      if (requestId !== state.fileRequestSeq) return;
    }
    const data = await fetchJson(filesQueryPath(), {
      credentials: isUserPagePrincipal(state.user) ? "same-origin" : "omit",
    });
    if (requestId !== state.fileRequestSeq) return;
    state.files = data.files || [];
    renderFiles();
  } catch (error) {
    if (requestId === state.fileRequestSeq) throw error;
  }
}

async function refreshUserView() {
  const statusCurrent = await loadStatus();
  if (statusCurrent === null) return;
  await loadFiles({ validateStatus: false });
}

async function deleteFile(id) {
  if (!window.confirm(t("confirmDelete"))) return;
  await fetchJson(`/api/files/${id}`, { method: "DELETE" });
  await loadFiles();
}

function renderFiles() {
  if (!state.files.length) {
    els.fileList.textContent = isUserPagePrincipal(state.user) ? t("noVisibleFiles") : t("noPublicFiles");
    els.fileList.className = "file-list empty";
    updateSelectionButtons();
    return;
  }

  els.fileList.textContent = "";
  els.fileList.className = "file-list";

  for (const file of state.files) {
    const card = document.createElement("article");
    card.className = "file-card";
    const rawUrl = addUserDownloadScope(apiUrl(`/api/files/${file.id}/download`));
    const zipUrl = addUserDownloadScope(apiUrl(`/api/files/${file.id}/download.zip`));
    card.innerHTML = `
      <div class="select-cell"><input type="checkbox" data-file-select value=""></div>
      <div class="file-main">
        <div class="file-title"></div>
        <div class="file-subtitle"></div>
        <div class="file-hash"></div>
      </div>
      <div class="file-stats"><span></span><span></span><span></span></div>
      <div class="row-actions">
        <a class="primary-action" href="">ZIP</a>
        <a href=""></a>
      </div>
    `;
    const selectInput = card.querySelector("[data-file-select]");
    selectInput.value = file.id;
    selectInput.setAttribute("aria-label", `${t("files")}: ${file.original_filename}`);
    selectInput.addEventListener("change", updateSelectionButtons);
    card.querySelector(".file-title").textContent = file.original_filename;
    card.querySelector(".file-subtitle").textContent = file.relative_path || "";
    card.querySelector(".file-hash").textContent = shortHash(file.sha256);
    const stats = card.querySelectorAll(".file-stats span");
    stats[0].textContent = formatBytes(file.file_size);
    stats[1].textContent = formatDate(file.server_mtime);
    stats[2].textContent = `${t("owner")}: ${file.owner_username || "-"}`;
    const links = card.querySelectorAll("a");
    links[0].href = zipUrl;
    links[0].setAttribute("aria-label", `ZIP: ${file.original_filename}`);
    links[1].href = rawUrl;
    links[1].textContent = t("raw");
    links[1].setAttribute("aria-label", `${t("raw")}: ${file.original_filename}`);
    if (file.can_delete && isUserPagePrincipal(state.user) && file.owner_username === state.user.username) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = t("delete");
      button.addEventListener("click", (event) => {
        runButtonOnce(event.currentTarget, () => deleteFile(file.id)).catch(showPageError);
      });
      card.querySelector(".row-actions").append(button);
    }
    els.fileList.append(card);
  }
  updateSelectionButtons();
}

function setQueueCount() {
  els.queueCount.textContent = String(state.queue.length);
}

function createQueueRow(item) {
  if (els.queue.classList.contains("empty")) {
    els.queue.textContent = "";
    els.queue.classList.remove("empty");
  }

  const row = document.createElement("div");
  row.className = "queue-item";
  row.innerHTML = `
    <div><div class="file-name"></div><div class="file-meta"></div></div>
    <div class="progress-shell"><div class="progress-bar"></div></div>
    <div class="result"></div>
  `;
  row.querySelector(".file-name").textContent = item.relativePath || item.file.name;
  row.querySelector(".file-meta").textContent = `${formatBytes(item.file.size)} | ${formatDateMs(item.file.lastModified)}`;
  row.querySelector(".result").textContent = t("waiting");
  els.queue.prepend(row);
  item.row = row;
}

function updateQueueRow(item, percent, message, type = "") {
  const bar = item.row.querySelector(".progress-bar");
  const result = item.row.querySelector(".result");
  bar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  result.className = `result ${type}`;
  result.textContent = message;
}

function uploadOne(item) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", item.file, item.file.name);
    form.append("relative_path", item.relativePath || item.file.webkitRelativePath || item.file.name);
    form.append("last_modified_ms", String(item.file.lastModified));
    form.append("size", String(item.file.size));

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) updateQueueRow(item, (event.loaded / event.total) * 100, `${Math.round((event.loaded / event.total) * 100)}%`);
    });

    xhr.addEventListener("load", () => {
      let payload = {};
      try { payload = JSON.parse(xhr.responseText || "{}"); } catch { payload = {}; }
      if (xhr.status >= 200 && xhr.status < 300 && payload.file) {
        const file = payload.file;
        updateQueueRow(item, 100, `OK | ${file.sha256} | ${file.mtime_set_success ? t("mtimeSet") : t("mtimeNotSet")}`, "success");
        resolve({ ok: true, authFailed: false });
      } else {
        updateQueueRow(item, 100, errorText(payload.detail, `Upload failed (${xhr.status})`), "error");
        resolve({ ok: false, authFailed: xhr.status === 403 || xhr.status === 423 });
      }
    });

    xhr.addEventListener("error", () => {
      updateQueueRow(item, 100, t("networkError"), "error");
      resolve({ ok: false, authFailed: false });
    });

    xhr.open("POST", apiUrl("/api/upload"));
    xhr.setRequestHeader("X-User-Session", state.sessionToken);
    xhr.send(form);
  });
}

async function uploadItems(items) {
  if (!items.length) return;
  if (!isUserPagePrincipal(state.user)) {
    showAuthMessage(t("sessionExpired"), "error");
    return;
  }
  for (const item of items) {
    state.queue.push(item);
    createQueueRow(item);
  }
  setQueueCount();
  for (const [index, item] of items.entries()) {
    updateQueueRow(item, 0, t("uploading"));
    const result = await uploadOne(item);
    state.queue = state.queue.filter((queued) => queued !== item);
    setQueueCount();
    if (result.authFailed) {
      for (const skipped of items.slice(index + 1)) {
        updateQueueRow(skipped, 0, t("uploadSkippedAuth"), "error");
        state.queue = state.queue.filter((queued) => queued !== skipped);
      }
      setSession("");
      state.user = null;
      renderSession();
      showAuthMessage(t("sessionExpired"), "error");
      setQueueCount();
      break;
    }
  }
  await loadFiles();
}

function filesFromInput(fileList) {
  return [...fileList].map((file) => ({ file, relativePath: file.webkitRelativePath || file.name }));
}

function readAllDirectoryEntries(reader) {
  return new Promise((resolve) => {
    const entries = [];
    function readBatch() {
      reader.readEntries((batch) => {
        if (!batch.length) return resolve(entries);
        entries.push(...batch);
        readBatch();
      });
    }
    readBatch();
  });
}

async function traverseEntry(entry, prefix = "") {
  if (entry.isFile) {
    return new Promise((resolve) => {
      entry.file((file) => resolve([{ file, relativePath: `${prefix}${file.name}` }]), () => resolve([]));
    });
  }
  if (entry.isDirectory) {
    const children = await readAllDirectoryEntries(entry.createReader());
    const nested = await Promise.all(children.map((child) => traverseEntry(child, `${prefix}${entry.name}/`)));
    return nested.flat();
  }
  return [];
}

async function filesFromDrop(event) {
  const items = [...(event.dataTransfer.items || [])];
  const entries = items.map((item) => (item.webkitGetAsEntry ? item.webkitGetAsEntry() : null)).filter(Boolean);
  if (entries.length) return (await Promise.all(entries.map((entry) => traverseEntry(entry)))).flat();
  return filesFromInput(event.dataTransfer.files || []);
}

function chooseFiles() {
  els.fileInput.click();
}

function showPageError(error) {
  els.statusLine.textContent = error.message || String(error);
}

function debounce(callback, delayMs = 250) {
  let timeoutId = 0;
  return (...args) => {
    window.clearTimeout(timeoutId);
    timeoutId = window.setTimeout(() => callback(...args), delayMs);
  };
}

async function runFormOnce(event, action) {
  const form = event.currentTarget;
  if (form.dataset.busy === "true") return;
  form.dataset.busy = "true";
  const submitter = event.submitter;
  if (submitter) submitter.disabled = true;
  try {
    await action();
  } finally {
    delete form.dataset.busy;
    if (submitter) submitter.disabled = false;
  }
}

async function runButtonOnce(button, action) {
  if (!button || button.dataset.busy === "true" || button.disabled) return;
  button.dataset.busy = "true";
  button.disabled = true;
  try {
    await action();
  } finally {
    delete button.dataset.busy;
    button.disabled = false;
  }
}

const debouncedFileSearch = debounce(() => loadFiles().catch(showPageError));

els.languageSelect.addEventListener("change", () => {
  state.lang = els.languageSelect.value;
  localStorage.setItem(LANG_KEY, state.lang);
  applyI18n();
  loadStatus().catch(showPageError);
});

els.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runFormOnce(event, async () => {
    try {
      const response = await postJson("/api/login", { username: els.usernameInput.value, password: els.passwordInput.value });
      const user = isUserPagePrincipal(response.user) ? response.user : null;
      if (!response.session_token || !user) throw new Error(t("sessionExpired"));
      setSession(response.session_token);
      state.user = user;
      els.passwordInput.value = "";
      showAuthMessage("");
      resetFilesAfterPrincipalChange();
      renderSession();
      await refreshUserView();
    } catch (error) {
      setSession("");
      state.user = null;
      resetFilesAfterPrincipalChange();
      renderSession();
      showAuthMessage(error.message || String(error), "error");
    }
  });
});

els.logoutButton.addEventListener("click", async (event) => {
  await runButtonOnce(event.currentTarget, async () => {
    try {
      await fetchJson("/api/logout", { method: "POST" });
    } catch (error) {
      showAuthMessage(error.message || String(error), "error");
      return;
    }
    setSession("");
    state.user = null;
    resetFilesAfterPrincipalChange();
    renderSession();
    await loadStatus().catch(showPageError);
    await loadFiles().catch(showPageError);
  });
});

els.passwordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runFormOnce(event, async () => {
    try {
      await postJson("/api/password", { current_password: els.currentPassword.value, new_password: els.newPassword.value });
      els.currentPassword.value = "";
      els.newPassword.value = "";
      setSession("");
      state.user = null;
      resetFilesAfterPrincipalChange();
      renderSession();
      showAuthMessage(t("passwordChanged"), "success");
      await refreshUserView();
    } catch (error) {
      showAccountMessage(error.message || String(error), "error");
    }
  });
});

els.fileButton.addEventListener("click", chooseFiles);
els.folderButton.addEventListener("click", () => els.folderInput.click());
els.plusButton.addEventListener("click", (event) => {
  event.stopPropagation();
  chooseFiles();
});
els.fileInput.addEventListener("change", () => {
  uploadItems(filesFromInput(els.fileInput.files)).catch(showPageError);
  els.fileInput.value = "";
});
els.folderInput.addEventListener("change", () => {
  uploadItems(filesFromInput(els.folderInput.files)).catch(showPageError);
  els.folderInput.value = "";
});
els.dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  els.dropZone.classList.add("dragging");
});
els.dropZone.addEventListener("dragleave", () => els.dropZone.classList.remove("dragging"));
els.dropZone.addEventListener("drop", async (event) => {
  event.preventDefault();
  els.dropZone.classList.remove("dragging");
  uploadItems(await filesFromDrop(event)).catch(showPageError);
});

els.refreshButton.addEventListener("click", () => refreshUserView().catch(showPageError));
els.searchInput.addEventListener("input", debouncedFileSearch);
els.sortBySelect.addEventListener("change", () => loadFiles().catch(showPageError));
els.sortDirSelect.addEventListener("change", () => loadFiles().catch(showPageError));
els.selectAllButton.addEventListener("click", () => setAllFileSelections(true));
els.clearSelectionButton.addEventListener("click", () => setAllFileSelections(false));
els.zipSelectedButton.addEventListener("click", () => {
  const ids = selectedIds();
  if (ids.length) zipDownload(ids);
});
els.zipAllButton.addEventListener("click", () => zipDownload(state.files.map((file) => file.id)));

initSession().catch(showPageError);
