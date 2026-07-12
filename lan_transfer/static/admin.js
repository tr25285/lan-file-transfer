const SESSION_KEY = "lanTransferAdminSession";
const LANG_KEY = "lanTransferLang";
const DEFAULT_GROUP_ID = "everyone";
const PROTECTED_GROUP_IDS = new Set(["public", DEFAULT_GROUP_ID]);
const auditActionLabels = {
  zh: {
    admin_logged_in: "管理员登录",
    admin_logged_out: "管理员退出",
    admin_password_changed: "管理员改密",
    admin_password_initialized: "初始化管理员密码",
    file_deleted: "删除文件",
    file_delete_rolled_back: "删除已回滚",
    file_downloaded: "下载文件",
    file_permissions_updated: "修改文件权限",
    file_uploaded: "上传文件",
    files_downloaded: "批量下载",
    group_created: "创建组",
    group_deleted: "删除组",
    password_changed: "修改密码",
    user_created: "创建用户",
    user_deleted: "删除用户",
    user_logged_in: "用户登录",
    user_logged_out: "用户退出",
    user_updated: "更新用户",
    users_batch_created: "批量创建用户",
  },
  en: {
    admin_logged_in: "Admin login",
    admin_logged_out: "Admin logout",
    admin_password_changed: "Admin password",
    admin_password_initialized: "Admin initialized",
    file_deleted: "File deleted",
    file_delete_rolled_back: "Delete rolled back",
    file_downloaded: "File downloaded",
    file_permissions_updated: "Permissions updated",
    file_uploaded: "File uploaded",
    files_downloaded: "Files downloaded",
    group_created: "Group created",
    group_deleted: "Group deleted",
    password_changed: "Password changed",
    user_created: "User created",
    user_deleted: "User deleted",
    user_logged_in: "User login",
    user_logged_out: "User logout",
    user_updated: "User updated",
    users_batch_created: "Batch users",
  },
};

const dict = {
  zh: {
    appTitle: "局域网文件传输",
    admin: "管理员",
    tools: "工具",
    manage: "管理",
    upload: "上传",
    chooseFiles: "选择文件",
    chooseFolder: "选择文件夹",
    account: "账户",
    currentPassword: "当前密码",
    newPassword: "新密码",
    changePassword: "修改密码",
    uploadQueue: "上传队列",
    queueEmpty: "暂无上传",
    queueCount: "队列数",
    createUser: "创建账户",
    username: "用户名",
    password: "密码",
    groups: "组",
    searchGroups: "搜索组",
    batchCreate: "批量创建",
    batchUsers: "账户列表",
    batchUsersHint: "每行一个用户名，或 username,password,display",
    groupId: "组 ID",
    groupName: "名称",
    createGroup: "创建组",
    users: "用户",
    login: "登录",
    logout: "退出",
    dropTitle: "拖拽文件到这里",
    adminDropHint: "管理员上传的文件默认给 everyone 组可见。",
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
    refresh: "刷新",
    zipSelected: "打包所选",
    zipAll: "全部打包",
    noFiles: "暂无文件。",
    noUsers: "暂无用户。",
    noGroups: "暂无组。",
    owner: "所有者",
    visibleGroups: "可见组",
    permissions: "权限",
    save: "保存",
    delete: "删除",
    raw: "原始",
    disable: "禁用",
    enable: "启用",
    resetPassword: "密码",
    waiting: "等待中",
    uploading: "上传中",
    networkError: "网络错误",
    sessionExpired: "登录已失效，请重新登录。",
    uploadSkippedAuth: "登录失效，已跳过",
    mtimeSet: "时间已设置",
    mtimeNotSet: "时间未设置",
    defaultLogin: "默认管理员：admin / 12345678",
    passwordChanged: "密码已修改，请重新登录。",
    userCreated: "账户已创建。未填密码时默认 12345678。",
    usersCreated: "批量创建完成",
    groupCreated: "组已创建。",
    userDeleted: "用户已删除，原有文件已转给管理员。",
    groupDeleted: "组已删除。",
    auditLog: "审计日志",
    noAudit: "暂无审计日志。",
    auditTarget: "对象",
    auditActor: "操作者",
    confirmDelete: "确定从 Windows 保存目录删除这个文件？",
    confirmDeleteUser: "确定删除用户 {username}？该用户上传的文件会转给管理员。",
    confirmDeleteGroup: "确定删除组 {groupId}？只有未被用户和文件使用的组可以删除。",
    groupInUse: "该组仍被用户或文件使用，不能删除。",
    userCount: "用户",
    fileCount: "文件",
    newPasswordPrompt: "新密码",
    passwordDialogCancel: "取消",
    authorLine: "作者：HaoXiang Huang · didadida1688@gmail.com · https://nextweb4.github.io/ · https://github.com/NextWeb4",
  },
  en: {
    appTitle: "LAN File Transfer",
    admin: "Admin",
    tools: "Tools",
    manage: "Manage",
    upload: "Upload",
    chooseFiles: "Files",
    chooseFolder: "Folder",
    account: "Account",
    currentPassword: "Current password",
    newPassword: "New password",
    changePassword: "Change password",
    uploadQueue: "Upload queue",
    queueEmpty: "No uploads yet.",
    queueCount: "Queue",
    createUser: "Create user",
    username: "Username",
    password: "Password",
    groups: "Groups",
    searchGroups: "Search groups",
    batchCreate: "Batch create",
    batchUsers: "Accounts",
    batchUsersHint: "One username per line, or username,password,display",
    groupId: "Group ID",
    groupName: "Name",
    createGroup: "Create group",
    users: "Users",
    login: "Login",
    logout: "Logout",
    dropTitle: "Drop files here",
    adminDropHint: "Admin uploads are visible to everyone group by default.",
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
    refresh: "Refresh",
    zipSelected: "Zip selected",
    zipAll: "Zip all",
    noFiles: "No files.",
    noUsers: "No users.",
    noGroups: "No groups.",
    owner: "Owner",
    visibleGroups: "Visible groups",
    permissions: "Permissions",
    save: "Save",
    delete: "Delete",
    raw: "Raw",
    disable: "Disable",
    enable: "Enable",
    resetPassword: "Password",
    waiting: "Waiting",
    uploading: "Uploading",
    networkError: "Network error",
    sessionExpired: "Session expired. Login again.",
    uploadSkippedAuth: "Auth failed, skipped",
    mtimeSet: "mtime set",
    mtimeNotSet: "mtime not set",
    defaultLogin: "Default admin: admin / 12345678",
    passwordChanged: "Password changed. Login again.",
    userCreated: "User created. Blank password defaults to 12345678.",
    usersCreated: "Batch create finished",
    groupCreated: "Group created.",
    userDeleted: "User deleted. Existing files were reassigned to admin.",
    groupDeleted: "Group deleted.",
    auditLog: "Audit log",
    noAudit: "No audit events.",
    auditTarget: "Target",
    auditActor: "Actor",
    confirmDelete: "Delete this file from the Windows save directory?",
    confirmDeleteUser: "Delete user {username}? Existing files uploaded by this user will be reassigned to admin.",
    confirmDeleteGroup: "Delete group {groupId}? Only groups unused by users and files can be deleted.",
    groupInUse: "This group is still used by users or files and cannot be deleted.",
    userCount: "Users",
    fileCount: "Files",
    newPasswordPrompt: "New password",
    passwordDialogCancel: "Cancel",
    authorLine: "Author: HaoXiang Huang · didadida1688@gmail.com · https://nextweb4.github.io/ · https://github.com/NextWeb4",
  },
};

const state = {
  sessionToken: localStorage.getItem(SESSION_KEY) || "",
  lang: localStorage.getItem(LANG_KEY) || "zh",
  files: [],
  fileRequestSeq: 0,
  statusRequestSeq: 0,
  adminSessionRequestSeq: 0,
  adminDataRequestSeq: 0,
  queue: [],
  users: [],
  groups: [],
  auditEvents: [],
  newUserGroups: [DEFAULT_GROUP_ID],
  batchGroups: [DEFAULT_GROUP_ID],
  newUserGroupSearch: "",
  batchGroupSearch: "",
};

const els = {
  statusLine: document.querySelector("#statusLine"),
  languageSelect: document.querySelector("#languageSelect"),
  authPanel: document.querySelector("#authPanel"),
  adminApp: document.querySelector("#adminApp"),
  adminToolsMenu: document.querySelector("#adminToolsMenu"),
  manageMenu: document.querySelector("#manageMenu"),
  authTitle: document.querySelector("#authTitle"),
  loginForm: document.querySelector("#loginForm"),
  loginUsername: document.querySelector("#loginUsername"),
  loginPassword: document.querySelector("#loginPassword"),
  authMessage: document.querySelector("#authMessage"),
  logoutButton: document.querySelector("#logoutButton"),
  dropZone: document.querySelector("#dropZone"),
  plusButton: document.querySelector("#plusButton"),
  fileInput: document.querySelector("#fileInput"),
  folderInput: document.querySelector("#folderInput"),
  fileButton: document.querySelector("#fileButton"),
  folderButton: document.querySelector("#folderButton"),
  refreshButton: document.querySelector("#refreshButton"),
  passwordForm: document.querySelector("#passwordForm"),
  currentPassword: document.querySelector("#currentPassword"),
  newPassword: document.querySelector("#newPassword"),
  adminMessage: document.querySelector("#adminMessage"),
  queue: document.querySelector("#queue"),
  queueCount: document.querySelector("#queueCount"),
  fileList: document.querySelector("#fileList"),
  searchInput: document.querySelector("#searchInput"),
  sortBySelect: document.querySelector("#sortBySelect"),
  sortDirSelect: document.querySelector("#sortDirSelect"),
  selectAllButton: document.querySelector("#selectAllButton"),
  clearSelectionButton: document.querySelector("#clearSelectionButton"),
  zipSelectedButton: document.querySelector("#zipSelectedButton"),
  zipAllButton: document.querySelector("#zipAllButton"),
  selectionCount: document.querySelector("#selectionCount"),
  userForm: document.querySelector("#userForm"),
  newUsername: document.querySelector("#newUsername"),
  newUserPassword: document.querySelector("#newUserPassword"),
  newUserGroupSearch: document.querySelector("#newUserGroupSearch"),
  newUserGroupsPicker: document.querySelector("#newUserGroupsPicker"),
  batchUserForm: document.querySelector("#batchUserForm"),
  batchUsersText: document.querySelector("#batchUsersText"),
  batchGroupSearch: document.querySelector("#batchGroupSearch"),
  batchGroupsPicker: document.querySelector("#batchGroupsPicker"),
  userList: document.querySelector("#userList"),
  groupForm: document.querySelector("#groupForm"),
  newGroupId: document.querySelector("#newGroupId"),
  newGroupName: document.querySelector("#newGroupName"),
  groupList: document.querySelector("#groupList"),
  auditRefreshButton: document.querySelector("#auditRefreshButton"),
  auditList: document.querySelector("#auditList"),
};

function t(key) {
  return dict[state.lang]?.[key] || dict.zh[key] || key;
}

function textWithValues(key, values) {
  return t(key).replace(/\{(\w+)\}/g, (_, name) => values[name] ?? "");
}

function auditActionLabel(action) {
  return auditActionLabels[state.lang]?.[action] || action || "-";
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
  renderFiles();
  renderUsers();
  renderGroups();
  renderAuditEvents();
  renderStaticGroupPickers();
}

function apiUrl(path) {
  return new URL(path, window.location.origin);
}

async function fetchJson(path, options = {}) {
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: {
      ...(state.sessionToken ? { "X-Admin-Session": state.sessionToken } : {}),
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

function putJson(path, payload) {
  return fetchJson(path, {
    method: "PUT",
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

function isAdminPrincipal(user) {
  return Boolean(user?.username) && user.role === "admin";
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

function zipDownload(ids) {
  const url = apiUrl("/api/download.zip");
  for (const id of ids) url.searchParams.append("ids", id);
  window.location.href = url.toString();
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

function showAuthMessage(message, type = "") {
  els.authMessage.className = `auth-message ${type}`;
  els.authMessage.textContent = message || "";
}

function showAdminMessage(message, type = "") {
  els.adminMessage.className = `auth-message ${type}`;
  els.adminMessage.textContent = message || "";
}

function invalidateAdminViewRequests() {
  state.fileRequestSeq += 1;
  state.statusRequestSeq += 1;
  state.adminSessionRequestSeq += 1;
  state.adminDataRequestSeq += 1;
}

function showAuthMode(message = "") {
  invalidateAdminViewRequests();
  els.authPanel.classList.remove("hidden");
  els.adminApp.classList.add("hidden");
  els.adminToolsMenu.classList.add("hidden");
  els.manageMenu.classList.add("hidden");
  els.loginForm.classList.remove("hidden");
  els.logoutButton.classList.add("hidden");
  state.files = [];
  state.users = [];
  state.groups = [];
  state.auditEvents = [];
  els.statusLine.textContent = "";
  els.authTitle.textContent = state.lang === "zh" ? "管理员登录" : "Admin Login";
  renderFiles();
  renderUsers();
  renderGroups();
  renderAuditEvents();
  showAuthMessage(message);
}

function showAdminApp() {
  els.authPanel.classList.add("hidden");
  els.adminApp.classList.remove("hidden");
  els.adminToolsMenu.classList.remove("hidden");
  els.manageMenu.classList.remove("hidden");
  els.logoutButton.classList.remove("hidden");
}

function lockMessage(lockedUntil) {
  if (!lockedUntil) return "This IP is locked.";
  return `This IP is locked until ${formatDate(lockedUntil)}.`;
}

async function initAuth() {
  applyI18n();
  if (state.sessionToken) {
    try {
      await fetchJson("/api/admin/session");
      showAdminApp();
      await refreshAll();
      return;
    } catch {
      setSession("");
    }
  }
  try {
    await fetchJson("/api/admin/session");
    showAdminApp();
    await refreshAll();
    return;
  } catch {}

  const status = await fetchJson("/api/admin/status");
  if (status.locked) {
    showAuthMode(lockMessage(status.locked_until));
    return;
  }
  showAuthMode(t("defaultLogin"));
}

async function refreshAll() {
  if (!(await verifyAdminSession())) return;
  const statusCurrent = await loadStatus();
  if (statusCurrent !== true) return;
  await Promise.all([loadFiles({ verifySession: false }), loadAdminData({ verifySession: false })]);
}

async function loadStatus() {
  const requestId = ++state.statusRequestSeq;
  try {
    const status = await fetchJson("/api/status");
    if (requestId !== state.statusRequestSeq) return null;
    if (status.role !== "admin" || !status.username) {
      if (state.sessionToken) {
        setSession("");
        showAuthMode(t("sessionExpired"));
      }
      return false;
    }
    els.statusLine.textContent = [status.base_url, status.username || "guest", status.save_dir].filter(Boolean).join(" | ");
    return true;
  } catch (error) {
    if (requestId !== state.statusRequestSeq) return null;
    throw error;
  }
}

async function verifyAdminSession() {
  const requestId = ++state.adminSessionRequestSeq;
  try {
    const session = await fetchJson("/api/admin/session");
    if (requestId !== state.adminSessionRequestSeq) return false;
    if (!isAdminPrincipal(session.user)) throw new Error(t("sessionExpired"));
    return true;
  } catch (error) {
    if (requestId !== state.adminSessionRequestSeq) return false;
    setSession("");
    showAuthMode(t("sessionExpired"));
    return false;
  }
}

async function loadFiles({ verifySession = true } = {}) {
  const requestId = ++state.fileRequestSeq;
  try {
    if (verifySession && !(await verifyAdminSession())) return;
    if (requestId !== state.fileRequestSeq) return;
    const data = await fetchJson(filesQueryPath());
    if (requestId !== state.fileRequestSeq) return;
    state.files = data.files || [];
    renderFiles();
  } catch (error) {
    if (requestId === state.fileRequestSeq) throw error;
  }
}

async function loadAdminData({ verifySession = true } = {}) {
  const requestId = ++state.adminDataRequestSeq;
  try {
    if (verifySession && !(await verifyAdminSession())) return;
    if (requestId !== state.adminDataRequestSeq) return;
    const [users, groups, auditData] = await Promise.all([
      fetchJson("/api/admin/users"),
      fetchJson("/api/admin/groups"),
      fetchJson("/api/admin/audit?limit=80"),
    ]);
    if (requestId !== state.adminDataRequestSeq) return;
    state.users = users.users || [];
    state.groups = groups.groups || [];
    state.auditEvents = auditData.events || [];
    state.newUserGroups = normalizeGroupSelection(state.newUserGroups, { includePublic: false });
    state.batchGroups = normalizeGroupSelection(state.batchGroups, { includePublic: false });
    renderStaticGroupPickers();
    renderUsers();
    renderGroups();
    renderAuditEvents();
  } catch (error) {
    if (requestId === state.adminDataRequestSeq) throw error;
  }
}

function normalizeGroupSelection(selection, { includePublic = true } = {}) {
  const validGroups = new Set(
    state.groups
      .filter((group) => includePublic || group.id !== "public")
      .map((group) => group.id),
  );
  const cleaned = [...new Set(selection || [])].filter((groupId) => validGroups.has(groupId));
  return cleaned.length ? cleaned : [DEFAULT_GROUP_ID];
}

function filteredGroups(search, { includePublic = true } = {}) {
  const needle = (search || "").trim().toLowerCase();
  return state.groups.filter((group) => {
    if (!includePublic && group.id === "public") return false;
    const text = `${group.id} ${group.name || ""} ${group.description || ""}`.toLowerCase();
    return !needle || text.includes(needle);
  });
}

function toggleGroup(selection, groupId, checked) {
  const next = new Set(selection);
  if (checked) next.add(groupId);
  else next.delete(groupId);
  const cleaned = [...next].filter(Boolean);
  return cleaned.length ? cleaned : [DEFAULT_GROUP_ID];
}

function renderGroupPicker(container, selection, search, onChange, { includePublic = true } = {}) {
  container.textContent = "";
  const groups = filteredGroups(search, { includePublic });
  if (!groups.length) {
    container.className = "group-picker empty";
    container.textContent = t("noGroups");
    return;
  }
  container.className = "group-picker";
  for (const group of groups) {
    const label = document.createElement("label");
    label.className = "check-row";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = selection.includes(group.id);
    input.addEventListener("change", () => onChange(group.id, input.checked));
    const span = document.createElement("span");
    span.textContent = group.id;
    label.append(input, span);
    container.append(label);
  }
}

function renderStaticGroupPickers() {
  if (!els.newUserGroupsPicker || !els.batchGroupsPicker) return;
  renderGroupPicker(els.newUserGroupsPicker, state.newUserGroups, state.newUserGroupSearch, (groupId, checked) => {
    state.newUserGroups = toggleGroup(state.newUserGroups, groupId, checked);
    renderStaticGroupPickers();
  }, { includePublic: false });
  renderGroupPicker(els.batchGroupsPicker, state.batchGroups, state.batchGroupSearch, (groupId, checked) => {
    state.batchGroups = toggleGroup(state.batchGroups, groupId, checked);
    renderStaticGroupPickers();
  }, { includePublic: false });
}

function inlineGroupEditor(currentGroups, onSave, { includePublic = true, label = "" } = {}) {
  const details = document.createElement("details");
  details.className = "inline-picker";
  details.addEventListener("toggle", () => {
    if (!details.open) return;
    document.querySelectorAll(".inline-picker[open]").forEach((openDetails) => {
      if (openDetails !== details) openDetails.open = false;
    });
  });
  const summary = document.createElement("summary");
  summary.textContent = t("groups");
  summary.setAttribute("aria-label", label || t("groups"));
  details.append(summary);

  const panel = document.createElement("div");
  panel.className = "inline-picker-panel";
  const search = document.createElement("input");
  search.className = "compact-input";
  search.type = "search";
  search.placeholder = t("searchGroups");
  search.setAttribute("aria-label", t("searchGroups"));
  const picker = document.createElement("div");
  let selection = normalizeGroupSelection(currentGroups || [DEFAULT_GROUP_ID], { includePublic });
  const render = () => {
    renderGroupPicker(picker, selection, search.value, (groupId, checked) => {
      selection = toggleGroup(selection, groupId, checked);
      render();
    }, { includePublic });
  };
  search.addEventListener("input", render);
  const save = document.createElement("button");
  save.type = "button";
  save.textContent = t("save");
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      await onSave(selection);
      details.open = false;
    } catch (error) {
      showAdminError(error);
    } finally {
      save.disabled = false;
    }
  });
  panel.append(search, picker, save);
  details.append(panel);
  render();
  return details;
}

async function deleteFile(id) {
  if (!window.confirm(t("confirmDelete"))) return;
  await fetchJson(`/api/files/${id}`, { method: "DELETE" });
  await refreshAll();
}

async function deleteUser(user) {
  if (!window.confirm(textWithValues("confirmDeleteUser", { username: user.username }))) return;
  await fetchJson(`/api/admin/users/${encodeURIComponent(user.username)}`, { method: "DELETE" });
  showAdminMessage(t("userDeleted"), "success");
  await refreshAll();
}

async function deleteGroup(group) {
  if (!window.confirm(textWithValues("confirmDeleteGroup", { groupId: group.id }))) return;
  await fetchJson(`/api/admin/groups/${encodeURIComponent(group.id)}`, { method: "DELETE" });
  showAdminMessage(t("groupDeleted"), "success");
  await refreshAll();
}

function renderFiles() {
  if (!state.files.length) {
    els.fileList.textContent = t("noFiles");
    els.fileList.className = "file-list empty";
    updateSelectionButtons();
    return;
  }

  els.fileList.textContent = "";
  els.fileList.className = "file-list";
  for (const file of state.files) {
    const card = document.createElement("article");
    card.className = "file-card";
    const rawUrl = apiUrl(`/api/files/${file.id}/download`);
    const zipUrl = apiUrl(`/api/files/${file.id}/download.zip`);
    card.innerHTML = `
      <div class="select-cell"><input type="checkbox" data-file-select value=""></div>
      <div class="file-main"><div class="file-title"></div><div class="file-subtitle"></div><div class="file-hash"></div></div>
      <div class="file-stats"><span></span><span></span><span></span></div>
      <div class="row-actions"><a class="primary-action" href="">ZIP</a><a href=""></a></div>
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
    stats[2].textContent = `${t("owner")}: ${file.owner_username || "-"} | ${t("visibleGroups")}: ${(file.allowed_groups || []).join(", ")}`;
    const links = card.querySelectorAll("a");
    links[0].href = zipUrl;
    links[0].setAttribute("aria-label", `ZIP: ${file.original_filename}`);
    links[1].href = rawUrl;
    links[1].textContent = t("raw");
    links[1].setAttribute("aria-label", `${t("raw")}: ${file.original_filename}`);
    const actions = card.querySelector(".row-actions");
    actions.append(
      inlineGroupEditor(file.allowed_groups || [DEFAULT_GROUP_ID], async (groups) => {
        await putJson(`/api/admin/files/${file.id}/permissions`, { allowed_groups: groups });
        await refreshAll();
      }, { label: `${t("visibleGroups")}: ${file.original_filename}` }),
    );
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.textContent = t("delete");
    deleteButton.addEventListener("click", (event) => {
      runButtonOnce(event.currentTarget, () => deleteFile(file.id)).catch(showAdminError);
    });
    actions.append(deleteButton);
    els.fileList.append(card);
  }
  updateSelectionButtons();
}

function renderUsers() {
  if (!state.users.length) {
    els.userList.textContent = t("noUsers");
    els.userList.className = "admin-list empty";
    return;
  }
  els.userList.textContent = "";
  els.userList.className = "admin-list";
  for (const user of state.users) {
    const row = document.createElement("div");
    row.className = "admin-list-row";
    row.innerHTML = `<div><div class="file-title"></div><div class="file-subtitle"></div></div><div class="row-actions"></div>`;
    row.querySelector(".file-title").textContent = `${user.username} (${user.role})`;
    row.querySelector(".file-subtitle").textContent = `${user.active ? "active" : "disabled"} | ${(user.groups || []).join(", ") || "-"}`;
    const actions = row.querySelector(".row-actions");
    actions.append(inlineGroupEditor(user.groups || [DEFAULT_GROUP_ID], async (groups) => {
      await putJson(`/api/admin/users/${encodeURIComponent(user.username)}`, { groups });
      await loadAdminData();
    }, { includePublic: false, label: `${t("groups")}: ${user.username}` }));
    const passwordButton = document.createElement("button");
    passwordButton.type = "button";
    passwordButton.textContent = t("resetPassword");
    passwordButton.addEventListener("click", (event) => {
      runButtonOnce(event.currentTarget, () => updateUserPassword(user)).catch(showAdminError);
    });
    const activeButton = document.createElement("button");
    activeButton.type = "button";
    activeButton.textContent = user.active ? t("disable") : t("enable");
    activeButton.addEventListener("click", (event) => {
      runButtonOnce(event.currentTarget, () => updateUserActive(user)).catch(showAdminError);
    });
    actions.append(passwordButton, activeButton);
    if (user.username !== "admin") {
      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.textContent = t("delete");
      deleteButton.addEventListener("click", (event) => {
        runButtonOnce(event.currentTarget, () => deleteUser(user)).catch(showAdminError);
      });
      actions.append(deleteButton);
    }
    els.userList.append(row);
  }
}

function renderGroups() {
  if (!state.groups.length) {
    els.groupList.textContent = t("noGroups");
    els.groupList.className = "admin-list empty";
    return;
  }
  els.groupList.textContent = "";
  els.groupList.className = "admin-list";
  for (const group of state.groups) {
    const row = document.createElement("div");
    row.className = "admin-list-row";
    row.innerHTML = `<div><div class="file-title"></div><div class="file-subtitle"></div></div><div class="row-actions"></div>`;
    row.querySelector(".file-title").textContent = group.id;
    const usage = `${t("userCount")}: ${group.user_count || 0} | ${t("fileCount")}: ${group.file_count || 0}`;
    row.querySelector(".file-subtitle").textContent = [group.description || group.name || "", usage].filter(Boolean).join(" | ");
    const actions = row.querySelector(".row-actions");
    if (!PROTECTED_GROUP_IDS.has(group.id)) {
      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.textContent = t("delete");
      if ((group.user_count || 0) > 0 || (group.file_count || 0) > 0) {
        deleteButton.disabled = true;
        deleteButton.title = t("groupInUse");
      } else {
        deleteButton.addEventListener("click", (event) => {
          runButtonOnce(event.currentTarget, () => deleteGroup(group)).catch(showAdminError);
        });
      }
      actions.append(deleteButton);
    }
    els.groupList.append(row);
  }
}

function renderAuditEvents() {
  if (!els.auditList) return;
  if (!state.auditEvents.length) {
    els.auditList.textContent = t("noAudit");
    els.auditList.className = "admin-list empty";
    return;
  }
  els.auditList.textContent = "";
  els.auditList.className = "admin-list audit-list";
  for (const event of state.auditEvents) {
    const row = document.createElement("div");
    row.className = "admin-list-row audit-row";
    row.innerHTML = `<div><div class="file-title"></div><div class="file-subtitle"></div><div class="file-hash"></div></div>`;
    const title = row.querySelector(".file-title");
    const subtitle = row.querySelector(".file-subtitle");
    const hash = row.querySelector(".file-hash");
    title.textContent = `${auditActionLabel(event.action)} | ${formatDate(event.timestamp)}`;
    subtitle.textContent = `${t("auditActor")}: ${event.actor || "-"} (${event.role || "-"}) | ${event.client_ip || "-"}`;
    hash.textContent = `${t("auditTarget")}: ${event.target_type || "-"} ${event.target_name || event.target_id || "-"}`;
    els.auditList.append(row);
  }
}

function askPassword(defaultValue = "") {
  return new Promise((resolve) => {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    const form = document.createElement("form");
    form.className = "password-dialog";
    const label = document.createElement("label");
    const labelText = document.createElement("span");
    labelText.textContent = t("newPasswordPrompt");
    const input = document.createElement("input");
    input.type = "password";
    input.minLength = 8;
    input.required = true;
    input.autocomplete = "new-password";
    input.value = defaultValue;
    label.append(labelText, input);
    const actions = document.createElement("div");
    actions.className = "dialog-actions";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = t("passwordDialogCancel");
    const save = document.createElement("button");
    save.type = "submit";
    save.textContent = t("save");
    actions.append(cancel, save);
    form.append(label, actions);
    backdrop.append(form);

    const close = (value) => {
      document.removeEventListener("keydown", onKeydown);
      backdrop.remove();
      resolve(value);
    };
    const onKeydown = (event) => {
      if (event.key === "Escape") close(null);
    };
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      close(input.value);
    });
    cancel.addEventListener("click", () => close(null));
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) close(null);
    });
    document.addEventListener("keydown", onKeydown);
    document.body.append(backdrop);
    input.focus();
    input.select();
  });
}

async function updateUserPassword(user) {
  const value = await askPassword("12345678");
  if (value === null) return;
  await putJson(`/api/admin/users/${encodeURIComponent(user.username)}`, { password: value });
  await loadAdminData();
}

async function updateUserActive(user) {
  await putJson(`/api/admin/users/${encodeURIComponent(user.username)}`, { active: !user.active });
  await loadAdminData();
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
  row.innerHTML = `<div><div class="file-name"></div><div class="file-meta"></div></div><div class="progress-shell"><div class="progress-bar"></div></div><div class="result"></div>`;
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
        updateQueueRow(item, 100, `OK | ${payload.file.sha256} | ${payload.file.mtime_set_success ? t("mtimeSet") : t("mtimeNotSet")}`, "success");
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
    xhr.setRequestHeader("X-Admin-Session", state.sessionToken);
    xhr.send(form);
  });
}

async function uploadItems(items) {
  if (!items.length) return;
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
      showAuthMode(t("sessionExpired"));
      setQueueCount();
      break;
    }
  }
  await refreshAll();
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

function parseBatchUsers(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split(",").map((part) => part.trim());
      return {
        username: parts[0],
        password: parts[1] || undefined,
        display_name: parts[2] || undefined,
        role: "user",
        groups: state.batchGroups,
      };
    });
}

function chooseFiles() {
  els.fileInput.click();
}

function showAdminError(error) {
  showAdminMessage(error.message || String(error), "error");
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

const debouncedFileSearch = debounce(() => loadFiles().catch(showAdminError));

els.languageSelect.addEventListener("change", () => {
  state.lang = els.languageSelect.value;
  localStorage.setItem(LANG_KEY, state.lang);
  applyI18n();
  loadStatus().catch(showAdminError);
});

els.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runFormOnce(event, async () => {
    try {
      const response = await postJson("/api/admin/login", {
        username: els.loginUsername.value,
        password: els.loginPassword.value,
      });
      if (!response.session_token || !isAdminPrincipal(response.user)) throw new Error(t("sessionExpired"));
      setSession(response.session_token);
      els.loginPassword.value = "";
      invalidateAdminViewRequests();
      showAdminApp();
      await refreshAll();
    } catch (error) {
      setSession("");
      showAuthMode(error.message || String(error));
      showAuthMessage(error.message || String(error), "error");
    }
  });
});

els.logoutButton.addEventListener("click", async (event) => {
  await runButtonOnce(event.currentTarget, async () => {
    try {
      await fetchJson("/api/admin/logout", { method: "POST" });
    } catch (error) {
      showAdminError(error);
      return;
    }
    setSession("");
    showAuthMode();
    els.statusLine.textContent = "";
  });
});

els.passwordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runFormOnce(event, async () => {
    try {
      await postJson("/api/admin/password", { current_password: els.currentPassword.value, new_password: els.newPassword.value });
      els.currentPassword.value = "";
      els.newPassword.value = "";
      setSession("");
      showAuthMode(t("passwordChanged"));
    } catch (error) {
      showAdminMessage(error.message || String(error), "error");
    }
  });
});

els.userForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runFormOnce(event, async () => {
    try {
      await postJson("/api/admin/users", {
        username: els.newUsername.value,
        password: els.newUserPassword.value || undefined,
        groups: state.newUserGroups,
      });
      els.newUsername.value = "";
      els.newUserPassword.value = "";
      showAdminMessage(t("userCreated"), "success");
      await loadAdminData();
    } catch (error) {
      showAdminError(error);
    }
  });
});

els.batchUserForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runFormOnce(event, async () => {
    try {
      const users = parseBatchUsers(els.batchUsersText.value);
      const response = await postJson("/api/admin/users/batch", { users });
      els.batchUsersText.value = "";
      showAdminMessage(`${t("usersCreated")}: ${response.count}`, "success");
      await loadAdminData();
    } catch (error) {
      showAdminError(error);
    }
  });
});

els.groupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runFormOnce(event, async () => {
    try {
      await postJson("/api/admin/groups", { id: els.newGroupId.value, name: els.newGroupName.value });
      els.newGroupId.value = "";
      els.newGroupName.value = "";
      showAdminMessage(t("groupCreated"), "success");
      await loadAdminData();
    } catch (error) {
      showAdminError(error);
    }
  });
});

els.newUserGroupSearch.addEventListener("input", () => {
  state.newUserGroupSearch = els.newUserGroupSearch.value;
  renderStaticGroupPickers();
});
els.batchGroupSearch.addEventListener("input", () => {
  state.batchGroupSearch = els.batchGroupSearch.value;
  renderStaticGroupPickers();
});

els.fileButton.addEventListener("click", chooseFiles);
els.folderButton.addEventListener("click", () => els.folderInput.click());
els.plusButton.addEventListener("click", (event) => {
  event.stopPropagation();
  chooseFiles();
});
els.refreshButton.addEventListener("click", () => refreshAll().catch(showAdminError));
els.auditRefreshButton.addEventListener("click", () => loadAdminData().catch(showAdminError));
els.searchInput.addEventListener("input", debouncedFileSearch);
els.sortBySelect.addEventListener("change", () => loadFiles().catch(showAdminError));
els.sortDirSelect.addEventListener("change", () => loadFiles().catch(showAdminError));
els.selectAllButton.addEventListener("click", () => setAllFileSelections(true));
els.clearSelectionButton.addEventListener("click", () => setAllFileSelections(false));
els.fileInput.addEventListener("change", () => {
  uploadItems(filesFromInput(els.fileInput.files)).catch(showAdminError);
  els.fileInput.value = "";
});
els.folderInput.addEventListener("change", () => {
  uploadItems(filesFromInput(els.folderInput.files)).catch(showAdminError);
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
  uploadItems(await filesFromDrop(event)).catch(showAdminError);
});
els.zipSelectedButton.addEventListener("click", () => {
  const ids = selectedIds();
  if (ids.length) zipDownload(ids);
});
els.zipAllButton.addEventListener("click", () => zipDownload(state.files.map((file) => file.id)));

initAuth().catch((error) => showAuthMode(error.message || String(error)));
