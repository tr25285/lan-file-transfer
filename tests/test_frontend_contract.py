from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_admin_permission_editor_uses_put_endpoint_contract() -> None:
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")

    assert 'putJson(`/api/admin/files/${file.id}/permissions`, { allowed_groups: groups })' in admin_js
    assert 'postJson(`/api/admin/files/${file.id}/permissions`' not in admin_js


def test_admin_batch_csv_cannot_create_admins_by_hidden_column() -> None:
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")

    parse_batch = admin_js[admin_js.index("function parseBatchUsers") : admin_js.index("function chooseFiles")]

    assert 'role: "user"' in parse_batch
    assert "parts[3]" not in parse_batch


def test_admin_password_reset_uses_masked_dialog_not_prompt() -> None:
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")

    assert "window.prompt" not in admin_js
    assert "input.type = \"password\"" in admin_js
    assert "function askPassword" in admin_js


def test_static_pages_include_release_author_identity() -> None:
    user_html = (ROOT / "lan_transfer" / "static" / "user.html").read_text(encoding="utf-8")
    admin_html = (ROOT / "lan_transfer" / "static" / "admin.html").read_text(encoding="utf-8")
    user_js = (ROOT / "lan_transfer" / "static" / "user.js").read_text(encoding="utf-8")
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")

    for html in (user_html, admin_html):
        assert '<meta name="author" content="HaoXiang Huang" />' in html
        assert "https://nextweb4.github.io/" in html
        assert "https://github.com/NextWeb4" in html
        assert 'data-i18n="authorLine"' in html

    for script in (user_js, admin_js):
        assert "Author: HaoXiang Huang" in script
        assert "didadida1688@gmail.com" in script


def test_frontend_file_loads_ignore_stale_responses() -> None:
    user_js = (ROOT / "lan_transfer" / "static" / "user.js").read_text(encoding="utf-8")
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")

    for script in (user_js, admin_js):
        assert "fileRequestSeq" in script
        assert "const requestId = ++state.fileRequestSeq" in script
        assert "if (requestId !== state.fileRequestSeq) return" in script


def test_admin_data_loads_ignore_stale_responses() -> None:
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")
    load_admin_data = admin_js[admin_js.index("async function loadAdminData") : admin_js.index("function normalizeGroupSelection")]

    assert "adminDataRequestSeq" in admin_js
    assert "const requestId = ++state.adminDataRequestSeq" in load_admin_data
    assert "async function loadAdminData({ verifySession = true } = {})" in admin_js
    assert "if (verifySession && !(await verifyAdminSession())) return" in load_admin_data
    assert "if (requestId !== state.adminDataRequestSeq) return" in load_admin_data
    assert "catch (error)" in load_admin_data
    assert "if (requestId === state.adminDataRequestSeq) throw error" in load_admin_data


def test_frontend_status_loads_ignore_stale_responses_and_errors() -> None:
    user_js = (ROOT / "lan_transfer" / "static" / "user.js").read_text(encoding="utf-8")
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")

    for script in (user_js, admin_js):
        load_status = script[script.index("async function loadStatus") : script.index("async function loadFiles")]
        assert "statusRequestSeq" in script
        assert "const requestId = ++state.statusRequestSeq" in load_status
        assert "if (requestId !== state.statusRequestSeq) return null" in load_status
        assert "catch (error)" in load_status
        assert "throw error" in load_status


def test_user_page_rejects_admin_principals_and_omits_guest_cookies() -> None:
    user_js = (ROOT / "lan_transfer" / "static" / "user.js").read_text(encoding="utf-8")
    login_handler = user_js[
        user_js.index('els.loginForm.addEventListener("submit"') :
        user_js.index('els.logoutButton.addEventListener("click"')
    ]

    assert "function isUserPagePrincipal(user)" in user_js
    assert 'user.role === "user"' in user_js
    assert "state.user = isUserPagePrincipal(session.user) ? session.user : null" in user_js
    assert "const user = isUserPagePrincipal(response.user) ? response.user : null" in login_handler
    assert 'if (!response.session_token || !user) throw new Error(t("sessionExpired"))' in login_handler
    assert 'document.body.dataset.role = signedIn ? "user" : "guest"' in user_js
    assert 'status.role !== "user" || !status.username' in user_js
    assert 'credentials: isUserPagePrincipal(state.user) ? "same-origin" : "omit"' in user_js
    assert "async function refreshUserView()" in user_js
    assert "async function loadFiles({ validateStatus = true } = {})" in user_js
    assert "const statusCurrent = await loadStatus()" in user_js


def test_admin_page_rejects_non_admin_login_responses() -> None:
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")
    login_handler = admin_js[
        admin_js.index('els.loginForm.addEventListener("submit"') :
        admin_js.index('els.logoutButton.addEventListener("click"')
    ]

    assert "function isAdminPrincipal(user)" in admin_js
    assert 'user.role === "admin"' in admin_js
    assert 'if (!response.session_token || !isAdminPrincipal(response.user)) throw new Error(t("sessionExpired"))' in login_handler
    assert "async function verifyAdminSession()" in admin_js
    assert "async function loadFiles({ verifySession = true } = {})" in admin_js
    assert "if (status.role !== \"admin\" || !status.username)" in admin_js
    assert 'showAuthMode(t("sessionExpired"))' in admin_js
    assert "if (verifySession && !(await verifyAdminSession())) return" in admin_js


def test_admin_audit_labels_include_delete_rollback_event() -> None:
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")
    labels_block = admin_js[admin_js.index("const auditActionLabels") : admin_js.index("const dict")]

    assert 'file_delete_rolled_back: "删除已回滚"' in labels_block
    assert 'file_delete_rolled_back: "Delete rolled back"' in labels_block


def test_primary_forms_are_guarded_against_duplicate_submit() -> None:
    user_js = (ROOT / "lan_transfer" / "static" / "user.js").read_text(encoding="utf-8")
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")

    for script in (user_js, admin_js):
        assert "async function runFormOnce(event, action)" in script
        assert 'if (form.dataset.busy === "true") return' in script
        assert 'form.dataset.busy = "true"' in script
        assert "const submitter = event.submitter" in script
        assert "if (submitter) submitter.disabled = true" in script
        assert "if (submitter) submitter.disabled = false" in script

    user_form_handlers = user_js[user_js.index('els.loginForm.addEventListener("submit"') : user_js.index("els.fileButton")]
    admin_form_handlers = admin_js[admin_js.index('els.loginForm.addEventListener("submit"') : admin_js.index("els.newUserGroupSearch")]

    assert user_form_handlers.count("await runFormOnce(event") == 2
    assert admin_form_handlers.count("await runFormOnce(event") == 5


def test_mutating_row_buttons_are_guarded_against_duplicate_clicks() -> None:
    user_js = (ROOT / "lan_transfer" / "static" / "user.js").read_text(encoding="utf-8")
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")

    for script in (user_js, admin_js):
        assert "async function runButtonOnce(button, action)" in script
        assert 'button.dataset.busy === "true"' in script
        assert 'button.dataset.busy = "true"' in script
        assert "button.disabled = true" in script
        assert "button.disabled = false" in script

    user_render_files = user_js[user_js.index("function renderFiles") : user_js.index("function setQueueCount")]
    assert "runButtonOnce(event.currentTarget, () => deleteFile(file.id))" in user_render_files

    admin_render_files = admin_js[admin_js.index("function renderFiles") : admin_js.index("function renderUsers")]
    admin_render_users = admin_js[admin_js.index("function renderUsers") : admin_js.index("function renderGroups")]
    admin_render_groups = admin_js[admin_js.index("function renderGroups") : admin_js.index("function renderAuditEvents")]

    assert "runButtonOnce(event.currentTarget, () => deleteFile(file.id))" in admin_render_files
    assert "runButtonOnce(event.currentTarget, () => updateUserPassword(user))" in admin_render_users
    assert "runButtonOnce(event.currentTarget, () => updateUserActive(user))" in admin_render_users
    assert "runButtonOnce(event.currentTarget, () => deleteUser(user))" in admin_render_users
    assert "runButtonOnce(event.currentTarget, () => deleteGroup(group))" in admin_render_groups


def test_user_page_delete_and_zip_all_stay_with_visible_user_scope() -> None:
    user_js = (ROOT / "lan_transfer" / "static" / "user.js").read_text(encoding="utf-8")
    render_files = user_js[user_js.index("function renderFiles") : user_js.index("function setQueueCount")]

    assert "file.can_delete && isUserPagePrincipal(state.user) && file.owner_username === state.user.username" in render_files
    assert "zipDownload(state.files.map((file) => file.id))" in user_js
    assert "zipDownload([])" not in user_js
    assert 'function userDownloadScope()' in user_js
    assert 'return isUserPagePrincipal(state.user) ? "user" : "guest"' in user_js
    assert 'url.searchParams.set("scope", userDownloadScope())' in user_js


def test_admin_zip_all_uses_current_visible_file_ids() -> None:
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")

    assert "zipDownload(state.files.map((file) => file.id))" in admin_js
    assert "els.zipAllButton.addEventListener(\"click\", () => zipDownload([]))" not in admin_js


def test_file_rows_have_accessible_selection_and_download_labels() -> None:
    user_js = (ROOT / "lan_transfer" / "static" / "user.js").read_text(encoding="utf-8")
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")

    for script in (user_js, admin_js):
        render_files = script[script.index("function renderFiles") : script.index("function renderUsers") if "function renderUsers" in script else script.index("function setQueueCount")]
        assert 'selectInput.setAttribute("aria-label"' in render_files
        assert 'links[0].setAttribute("aria-label"' in render_files
        assert 'links[1].setAttribute("aria-label"' in render_files


def test_static_controls_keep_accessible_names_after_language_switch() -> None:
    user_html = (ROOT / "lan_transfer" / "static" / "user.html").read_text(encoding="utf-8")
    admin_html = (ROOT / "lan_transfer" / "static" / "admin.html").read_text(encoding="utf-8")
    user_js = (ROOT / "lan_transfer" / "static" / "user.js").read_text(encoding="utf-8")
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")

    for script in (user_js, admin_js):
        assert 'document.querySelectorAll("[data-i18n-aria-label]")' in script
        assert 'node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel))' in script

    for html in (user_html, admin_html):
        assert 'id="searchInput"' in html and 'data-i18n-aria-label="searchFiles"' in html
        assert 'id="sortBySelect"' in html and 'data-i18n-aria-label="sortBy"' in html
        assert 'id="sortDirSelect"' in html and 'data-i18n-aria-label="sortDirection"' in html
        assert 'id="plusButton"' in html and 'data-i18n-aria-label="chooseFiles"' in html

    assert 'id="newUserGroupSearch"' in admin_html and 'data-i18n-aria-label="searchGroups"' in admin_html
    assert 'id="batchGroupSearch"' in admin_html and 'data-i18n-aria-label="searchGroups"' in admin_html


def test_drop_zone_is_not_a_nested_interactive_button() -> None:
    user_html = (ROOT / "lan_transfer" / "static" / "user.html").read_text(encoding="utf-8")
    admin_html = (ROOT / "lan_transfer" / "static" / "admin.html").read_text(encoding="utf-8")
    user_js = (ROOT / "lan_transfer" / "static" / "user.js").read_text(encoding="utf-8")
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")

    for html in (user_html, admin_html):
        drop_zone_open = re.search(r"<section[^>]+id=\"dropZone\"[^>]*>", html)
        assert drop_zone_open is not None
        assert "role=" not in drop_zone_open.group(0)
        assert "tabindex=" not in drop_zone_open.group(0)

    for script in (user_js, admin_js):
        assert 'els.dropZone.addEventListener("click"' not in script
        assert 'els.dropZone.addEventListener("keydown"' not in script


def test_file_search_inputs_are_debounced() -> None:
    user_js = (ROOT / "lan_transfer" / "static" / "user.js").read_text(encoding="utf-8")
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")

    for script in (user_js, admin_js):
        assert "function debounce(callback, delayMs = 250)" in script
        assert "const debouncedFileSearch = debounce(" in script
        assert 'els.searchInput.addEventListener("input", debouncedFileSearch)' in script


def test_mobile_popovers_are_viewport_fixed() -> None:
    styles = (ROOT / "lan_transfer" / "static" / "styles.css").read_text(encoding="utf-8")
    mobile_block = styles[styles.index("@media (max-width: 760px)") :]

    assert "position: fixed;" in mobile_block
    assert "left: 9px;" in mobile_block
    assert "right: 9px;" in mobile_block


def test_font_sizes_do_not_scale_with_viewport_width() -> None:
    styles = (ROOT / "lan_transfer" / "static" / "styles.css").read_text(encoding="utf-8")
    font_size_lines = [line for line in styles.splitlines() if "font-size:" in line]

    assert all("vw" not in line and "vh" not in line for line in font_size_lines)


def test_background_avoids_decorative_gradient_orbs() -> None:
    styles = (ROOT / "lan_transfer" / "static" / "styles.css").read_text(encoding="utf-8")

    assert "radial-gradient" not in styles


def test_logout_handlers_keep_local_session_when_server_rejects_logout() -> None:
    user_js = (ROOT / "lan_transfer" / "static" / "user.js").read_text(encoding="utf-8")
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")

    user_logout = user_js[user_js.index('els.logoutButton.addEventListener("click"') : user_js.index("els.passwordForm")]
    admin_logout = admin_js[admin_js.index('els.logoutButton.addEventListener("click"') : admin_js.index("els.passwordForm")]

    for logout_block in (user_logout, admin_logout):
        assert "runButtonOnce(event.currentTarget" in logout_block
        assert "catch (error)" in logout_block
        assert "return;" in logout_block
        assert "catch {}" not in logout_block


def test_admin_logout_clears_stale_status_line_after_success() -> None:
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")
    admin_logout = admin_js[admin_js.index('els.logoutButton.addEventListener("click"') : admin_js.index("els.passwordForm")]

    assert 'els.statusLine.textContent = ""' in admin_logout


def test_admin_auth_mode_clears_stale_status_line() -> None:
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")
    auth_mode = admin_js[admin_js.index("function showAuthMode") : admin_js.index("function showAdminApp")]

    assert 'els.statusLine.textContent = ""' in auth_mode


def test_admin_auth_mode_invalidates_and_rerenders_stale_data() -> None:
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")
    invalidator = admin_js[admin_js.index("function invalidateAdminViewRequests") : admin_js.index("function showAuthMode")]
    auth_mode = admin_js[admin_js.index("function showAuthMode") : admin_js.index("function showAdminApp")]

    for field in ("fileRequestSeq", "statusRequestSeq", "adminSessionRequestSeq", "adminDataRequestSeq"):
        assert f"state.{field} += 1" in invalidator
    for call in ("renderFiles();", "renderUsers();", "renderGroups();", "renderAuditEvents();"):
        assert call in auth_mode


def test_admin_refresh_stops_when_status_is_not_admin() -> None:
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")
    refresh_all = admin_js[admin_js.index("async function refreshAll") : admin_js.index("async function loadStatus")]

    assert "if (statusCurrent !== true) return" in refresh_all


def test_login_refresh_failures_restore_logged_out_ui() -> None:
    user_js = (ROOT / "lan_transfer" / "static" / "user.js").read_text(encoding="utf-8")
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")
    user_login = user_js[
        user_js.index('els.loginForm.addEventListener("submit"') :
        user_js.index('els.logoutButton.addEventListener("click"')
    ]
    admin_login = admin_js[
        admin_js.index('els.loginForm.addEventListener("submit"') :
        admin_js.index('els.logoutButton.addEventListener("click"')
    ]

    assert "resetFilesAfterPrincipalChange();" in user_login
    assert "renderSession();" in user_login[user_login.index("catch (error)") :]
    assert "showAuthMode(error.message || String(error));" in admin_login


def test_inline_group_editor_closes_other_open_pickers() -> None:
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")
    inline_editor = admin_js[admin_js.index("function inlineGroupEditor") : admin_js.index("function renderFiles")]

    assert 'document.querySelectorAll(".inline-picker[open]")' in inline_editor
    assert "openDetails.open = false" in inline_editor


def test_inline_group_editors_have_contextual_accessible_names() -> None:
    admin_js = (ROOT / "lan_transfer" / "static" / "admin.js").read_text(encoding="utf-8")
    inline_editor = admin_js[admin_js.index("function inlineGroupEditor") : admin_js.index("function renderFiles")]
    render_files = admin_js[admin_js.index("function renderFiles") : admin_js.index("function renderUsers")]
    render_users = admin_js[admin_js.index("function renderUsers") : admin_js.index("function renderGroups")]

    assert "label = \"\"" in inline_editor
    assert 'summary.setAttribute("aria-label", label || t("groups"))' in inline_editor
    assert 'label: `${t("visibleGroups")}: ${file.original_filename}`' in render_files
    assert 'label: `${t("groups")}: ${user.username}`' in render_users


def test_panels_do_not_clip_inline_permission_popovers() -> None:
    styles = (ROOT / "lan_transfer" / "static" / "styles.css").read_text(encoding="utf-8")
    panel_block = styles[styles.index(".panel {") : styles.index(".panel-title {")]

    assert "overflow: visible;" in panel_block
    assert "overflow: hidden;" not in panel_block
