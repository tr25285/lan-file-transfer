from __future__ import annotations

from lan_transfer.audit import AuditManager


def test_audit_recent_is_bounded_newest_first_and_skips_bad_lines(tmp_path):
    audit = AuditManager(tmp_path)
    for index in range(6):
        audit.record(
            action=f"event_{index}",
            actor="admin",
            role="admin",
            client_ip="127.0.0.1",
            target_type="file",
            target_id=str(index),
        )
    with audit.path.open("a", encoding="utf-8") as handle:
        handle.write("{bad json}\n")

    events = audit.recent(3)

    assert [event["action"] for event in events] == ["event_5", "event_4", "event_3"]
    assert audit.size_bytes() > 0


def test_audit_redacts_sensitive_metadata_without_removing_safe_hashes(tmp_path):
    audit = AuditManager(tmp_path)

    event = audit.record(
        action="user_updated",
        actor="admin",
        role="admin",
        client_ip="127.0.0.1",
        target_type="user",
        target_id="alice",
        metadata={
            "password": "secret-password",
            "new_password": "new-secret-password",
            "currentPassword": "current-camel-secret",
            "session_token": "session-secret",
            "sessionToken": "camel-session-secret",
            "sessionId": "session-id-secret",
            "Set-Cookie": "cookie-secret",
            "secretKey": "secret-key-value",
            "apiToken": "api-token-value",
            "sha256": "safe-file-hash",
            "nested": {
                "Authorization": "Bearer token-secret",
                "items": [
                    {
                        "x-user-session": "header-secret",
                        "XUserSession": "camel-header-secret",
                        "authCookie": "auth-cookie-secret",
                        "label": "visible",
                    }
                ],
            },
        },
    )

    assert event["metadata"]["password"] == "[redacted]"
    assert event["metadata"]["new_password"] == "[redacted]"
    assert event["metadata"]["currentPassword"] == "[redacted]"
    assert event["metadata"]["session_token"] == "[redacted]"
    assert event["metadata"]["sessionToken"] == "[redacted]"
    assert event["metadata"]["sessionId"] == "[redacted]"
    assert event["metadata"]["Set-Cookie"] == "[redacted]"
    assert event["metadata"]["secretKey"] == "[redacted]"
    assert event["metadata"]["apiToken"] == "[redacted]"
    assert event["metadata"]["sha256"] == "safe-file-hash"
    assert event["metadata"]["nested"]["Authorization"] == "[redacted]"
    assert event["metadata"]["nested"]["items"][0]["x-user-session"] == "[redacted]"
    assert event["metadata"]["nested"]["items"][0]["XUserSession"] == "[redacted]"
    assert event["metadata"]["nested"]["items"][0]["authCookie"] == "[redacted]"
    assert event["metadata"]["nested"]["items"][0]["label"] == "visible"

    audit_text = audit.path.read_text(encoding="utf-8")
    assert "secret-password" not in audit_text
    assert "new-secret-password" not in audit_text
    assert "current-camel-secret" not in audit_text
    assert "session-secret" not in audit_text
    assert "camel-session-secret" not in audit_text
    assert "session-id-secret" not in audit_text
    assert "cookie-secret" not in audit_text
    assert "secret-key-value" not in audit_text
    assert "api-token-value" not in audit_text
    assert "token-secret" not in audit_text
    assert "header-secret" not in audit_text
    assert "camel-header-secret" not in audit_text
    assert "auth-cookie-secret" not in audit_text
    assert "safe-file-hash" in audit_text
