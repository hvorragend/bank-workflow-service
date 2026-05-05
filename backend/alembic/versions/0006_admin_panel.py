"""admin panel: users, roles, permissions + DB-backed configs

Revision ID: 0006_admin_panel
Revises: 0005_api_tokens
Create Date: 2026-05-05 12:00:00

Verschiebt Konfiguration und User-Verwaltung aus Dateien/Env-Vars in die DB:
- users + roles + permissions + role_permissions + user_roles
- ldap_config (single row), ldap_role_mapping
- smtp_config (single row), notification_templates, role_emails
- escalation_config (single row)
- app_settings (auth.mode, login_rate_limit)

Optional best-effort Import bestehender config/users.json + role_emails.toml,
falls vorhanden — fuer brownfield-Upgrades.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_admin_panel"
down_revision: Union[str, Sequence[str], None] = "0005_api_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# Quelle der Wahrheit fuer den Permission-Katalog: app/auth/permission_catalog.py.
# Wir replizieren die Liste hier minimal (code, area, description) — die Migration
# darf nicht von Anwendungs-Code abhaengen, der sich spaeter aendert. Beim
# App-Start wird der Katalog idempotent re-seeded (siehe bootstrap.py).
_PERMISSION_SEED: list[tuple[str, str, str]] = [
    ("admin.users.read",                     "admin.users",         "User auflisten und ansehen"),
    ("admin.users.write",                    "admin.users",         "Lokale User anlegen, bearbeiten, deaktivieren"),
    ("admin.users.assign_roles",             "admin.users",         "Rollen einem User zuweisen"),
    ("admin.roles.read",                     "admin.roles",         "Rollen und ihre Permissions ansehen"),
    ("admin.roles.write",                    "admin.roles",         "Rollen anlegen, bearbeiten, loeschen"),
    ("admin.permissions.read",               "admin.permissions",   "Permission-Katalog ansehen"),
    ("admin.ldap.read",                      "admin.ldap",          "LDAP-Konfiguration ansehen"),
    ("admin.ldap.write",                     "admin.ldap",          "LDAP-Konfiguration aendern"),
    ("admin.ldap.test",                      "admin.ldap",          "Test-Bind/-Suche ausfuehren"),
    ("admin.ldap.sync",                      "admin.ldap",          "LDAP-Bulk-Sync starten"),
    ("admin.smtp.read",                      "admin.smtp",          "SMTP-Konfiguration ansehen"),
    ("admin.smtp.write",                     "admin.smtp",          "SMTP-Konfiguration aendern"),
    ("admin.smtp.test",                      "admin.smtp",          "Test-Mail versenden"),
    ("admin.notifications.templates.read",   "admin.notifications", "E-Mail-Templates ansehen"),
    ("admin.notifications.templates.write",  "admin.notifications", "E-Mail-Templates bearbeiten"),
    ("admin.notifications.role_emails.read", "admin.notifications", "Rollen-E-Mail-Mapping ansehen"),
    ("admin.notifications.role_emails.write","admin.notifications", "Rollen-E-Mail-Mapping bearbeiten"),
    ("admin.escalation.read",                "admin.escalation",    "Eskalations-Konfiguration ansehen"),
    ("admin.escalation.write",               "admin.escalation",    "Eskalations-Konfiguration aendern"),
    ("admin.escalation.run_now",             "admin.escalation",    "Eskalations-Scan sofort ausfuehren"),
    ("admin.audit.read",                     "admin.audit",         "Audit-Log einsehen"),
    ("admin.system.read",                    "admin.system",        "System-Status einsehen"),
    ("admin.system.rekey",                   "admin.system",        "Sensitive Werte re-encrypten"),
    ("admin.auth_mode.read",                 "admin.auth_mode",     "Auth-Modus einsehen"),
    ("admin.auth_mode.write",                "admin.auth_mode",     "Auth-Modus aendern"),
    ("admin.api_tokens.read",                "admin.api_tokens",    "Reporting-Tokens auflisten"),
    ("admin.api_tokens.write",               "admin.api_tokens",    "Reporting-Tokens anlegen/widerrufen"),
    ("definitions.read",                     "definitions",         "Form-Definitionen auflisten"),
    ("definitions.upload",                   "definitions",         "Neue Definition als Draft hochladen"),
    ("definitions.activate",                 "definitions",         "Definition aktivieren"),
    ("definitions.retire",                   "definitions",         "Definition zurueckziehen"),
    ("definitions.diff",                     "definitions",         "Schemas vergleichen"),
    ("instances.create",                     "instances",           "Neuen Antrag anlegen"),
    ("instances.read",                       "instances",           "Antraege einsehen"),
    ("instances.decide",                     "instances",           "Antrag entscheiden"),
    ("instances.return",                     "instances",           "Antrag zurueckgeben"),
    ("instances.reporting",                  "instances",           "/reporting nutzen"),
]


_DEFAULT_ROLES: dict[str, list[str]] = {
    "Vorstand":             ["definitions.read", "instances.read", "instances.decide", "instances.return"],
    "Compliance":           ["definitions.read", "instances.read", "instances.decide", "instances.return"],
    "Risikomanagement":     ["definitions.read", "instances.read", "instances.decide", "instances.return"],
    "Fachbereichsleiter":   ["definitions.read", "instances.create", "instances.read", "instances.decide", "instances.return"],
    "Bereichsleiter":       ["definitions.read", "instances.read", "instances.decide", "instances.return"],
    "Vorstandssekretariat": ["definitions.read", "instances.read"],
}


# Notification-Template-Bodies in $varname-Syntax (string.Template.safe_substitute).
# Variablen werden vom Dispatcher gefuellt (siehe notifications/dispatcher.py).
_TEMPLATE_SEED: dict[str, tuple[str, str]] = {
    "stage_review_pending": (
        "[Bank Workflow] Antrag wartet auf $rolle-Entscheidung — $titel",
        "Sehr geehrte Empfaengerin, sehr geehrter Empfaenger,\n\n"
        "ein Antrag wartet jetzt auf eine Entscheidung in der Stage „$stage“:\n\n"
        "Titel:        $titel\n"
        "Maske:        $schema_version\n"
        "Antragsteller:$antragsteller\n"
        "Erstellt am:  $erstellt_am\n\n"
        "Direktlink:   $link\n\n"
        "Bitte oeffnen Sie den Antrag, pruefen Sie ihn fachlich und treffen Sie eine\n"
        "Entscheidung (genehmigen, zur Ueberarbeitung zurueckweisen, ablehnen).\n\n"
        "Diese Nachricht wurde automatisch vom Bank Workflow Service erzeugt.",
    ),
    "approved": (
        "[Bank Workflow] Genehmigt — $titel",
        "Hallo $antragsteller,\n\n"
        "dein Antrag wurde vollstaendig genehmigt:\n\n"
        "Titel:           $titel\n"
        "Maske:           $schema_version\n"
        "Abgeschlossen:   $abgeschlossen_am\n\n"
        "Direktlink:      $link\n\n"
        "Diese Nachricht wurde automatisch vom Bank Workflow Service erzeugt.",
    ),
    "rejected": (
        "[Bank Workflow] Abgelehnt — $titel",
        "Hallo $antragsteller,\n\n"
        "dein Antrag wurde von $rolle abgelehnt:\n\n"
        "Titel:        $titel\n"
        "Maske:        $schema_version\n\n"
        "Begruendung:  $kommentar\n\n"
        "Direktlink:   $link\n\n"
        "Diese Nachricht wurde automatisch vom Bank Workflow Service erzeugt.",
    ),
    "returned": (
        "[Bank Workflow] Zur Ueberarbeitung — $titel",
        "Hallo $antragsteller,\n\n"
        "dein Antrag wurde von $rolle zur Ueberarbeitung zurueckgewiesen:\n\n"
        "Titel:        $titel\n"
        "Maske:        $schema_version\n\n"
        "Hinweis:      $kommentar\n\n"
        "Bitte ueberarbeite den Antrag und reiche ihn erneut ein:\n$link\n\n"
        "Diese Nachricht wurde automatisch vom Bank Workflow Service erzeugt.",
    ),
    "sla_erinnerung": (
        "[Bank Workflow] Erinnerung — wartet seit $age_days Tagen",
        "Erinnerung: der folgende Antrag wartet seit $age_days Tagen auf eine\n"
        "Entscheidung in der Stage '$stage'. Das halbe SLA ($half_sla Tage) ist erreicht.\n\n"
        "Titel:         $titel\n"
        "Antragsteller: $antragsteller\n"
        "Direktlink:    $link\n\n"
        "Bitte zeitnah pruefen — bei $sla Tagen ohne Entscheidung wird an\n"
        "den Bereichsleiter eskaliert.",
    ),
    "sla_eskalation": (
        "[Bank Workflow] ESKALATION — SLA ueberschritten",
        "ESKALATION: der folgende Antrag haengt seit $age_days Tagen in der\n"
        "Stage '$stage' — das SLA von $sla Tagen ist ueberschritten.\n\n"
        "Erforderliche Rolle: $rolle\n"
        "Titel:               $titel\n"
        "Antragsteller:       $antragsteller\n"
        "Direktlink:          $link\n\n"
        "Bitte greifen Sie ein — entweder direkt entscheiden, falls die Rolle\n"
        "das zulaesst, oder die zustaendige Person aktiv ansprechen.",
    ),
}


def upgrade() -> None:  # noqa: C901 — Migration ist linear und lesbarer am Stueck
    # ----- permissions / roles / users / m:n -----
    op.create_table(
        "permissions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=80), nullable=False, unique=True),
        sa.Column("area", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False, unique=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("username", sa.String(length=150), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("auth_source", sa.String(length=20), nullable=False),
        sa.Column("password_argon2", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_emergency", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ldap_dn", sa.String(length=500), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.String(length=36),
                  sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.String(length=36),
                  sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(length=36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.String(length=36),
                  sa.ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])

    # ----- ldap config (singleton) + group mapping -----
    op.create_table(
        "ldap_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("server", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("bind_user_template", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("search_base", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("group_search_base", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("group_filter", sa.String(length=500), nullable=False,
                  server_default="(member={user_dn})"),
        sa.Column("tls_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ca_cert_pem", sa.Text(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("service_account_dn", sa.String(length=500), nullable=True),
        sa.Column("service_account_pw_enc", sa.Text(), nullable=True),
        sa.Column("user_filter", sa.String(length=500), nullable=False,
                  server_default="(uid={username})"),
        sa.Column("attr_username", sa.String(length=80), nullable=False, server_default="uid"),
        sa.Column("attr_display_name", sa.String(length=80), nullable=False, server_default="displayName"),
        sa.Column("attr_email", sa.String(length=80), nullable=False, server_default="mail"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=150), nullable=False, server_default="system"),
        sa.CheckConstraint("id = 1", name="ck_ldap_config_singleton"),
    )

    op.create_table(
        "ldap_role_mapping",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("group_dn", sa.String(length=500), nullable=False),
        sa.Column("role_id", sa.String(length=36),
                  sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("group_dn", "role_id", name="uq_ldap_role_mapping"),
    )
    op.create_index("ix_ldap_role_mapping_group_dn", "ldap_role_mapping", ["group_dn"])

    # ----- smtp config (singleton) + templates + role_emails -----
    op.create_table(
        "smtp_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("host", sa.String(length=255), nullable=False, server_default="localhost"),
        sa.Column("port", sa.Integer(), nullable=False, server_default="1025"),
        sa.Column("use_tls", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("username", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("password_enc", sa.Text(), nullable=True),
        sa.Column("mail_from", sa.String(length=320), nullable=False,
                  server_default="noreply@bws.local"),
        sa.Column("app_url", sa.String(length=500), nullable=False,
                  server_default="http://localhost:8080"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=150), nullable=False, server_default="system"),
        sa.CheckConstraint("id = 1", name="ck_smtp_config_singleton"),
    )

    op.create_table(
        "notification_templates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("key", sa.String(length=80), nullable=False, unique=True),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=150), nullable=False, server_default="system"),
    )
    op.create_index("ix_notification_templates_key", "notification_templates", ["key"], unique=True)

    op.create_table(
        "role_emails",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("role_id", sa.String(length=36),
                  sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.UniqueConstraint("role_id", "email", name="uq_role_email"),
    )
    op.create_index("ix_role_emails_role_id", "role_emails", ["role_id"])

    # ----- escalation config (singleton) -----
    op.create_table(
        "escalation_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_sla_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("bereichsleiter_role_id", sa.String(length=36),
                  sa.ForeignKey("roles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=150), nullable=False, server_default="system"),
        sa.CheckConstraint("id = 1", name="ck_escalation_config_singleton"),
    )

    # ----- key/value app settings -----
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=80), primary_key=True),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=150), nullable=False, server_default="system"),
    )

    # ---------------- Seeds ----------------
    bind = op.get_bind()
    now = _utcnow()

    # Permission-Katalog
    perm_id_by_code: dict[str, str] = {}
    for code, area, desc in _PERMISSION_SEED:
        pid = _uuid()
        perm_id_by_code[code] = pid
        bind.execute(
            sa.text("INSERT INTO permissions (id, code, area, description) VALUES (:id, :c, :a, :d)"),
            {"id": pid, "c": code, "a": area, "d": desc},
        )

    # Admin-Rolle (alle Permissions)
    admin_role_id = _uuid()
    bind.execute(
        sa.text(
            "INSERT INTO roles (id, name, description, is_system, created_at) "
            "VALUES (:id, :n, :d, :sys, :ts)"
        ),
        {"id": admin_role_id, "n": "Admin",
         "d": "System-Rolle. Alle Permissions. Nicht loeschbar.",
         "sys": True, "ts": now},
    )
    for pid in perm_id_by_code.values():
        bind.execute(
            sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p)"),
            {"r": admin_role_id, "p": pid},
        )

    # Default-Rollen
    role_id_by_name: dict[str, str] = {"Admin": admin_role_id}
    for role_name, perm_codes in _DEFAULT_ROLES.items():
        rid = _uuid()
        role_id_by_name[role_name] = rid
        bind.execute(
            sa.text(
                "INSERT INTO roles (id, name, description, is_system, created_at) "
                "VALUES (:id, :n, :d, :sys, :ts)"
            ),
            {"id": rid, "n": role_name, "d": f"Default-Rolle {role_name}",
             "sys": False, "ts": now},
        )
        for code in perm_codes:
            pid = perm_id_by_code.get(code)
            if pid:
                bind.execute(
                    sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p)"),
                    {"r": rid, "p": pid},
                )

    # Single-Row-Configs. Wir schreiben Boolean-Werte als :enabled-Bind-Parameter,
    # damit SQLAlchemy sie pro Dialekt korrekt umsetzt (Postgres: TRUE/FALSE,
    # SQLite: 0/1).
    bind.execute(
        sa.text(
            "INSERT INTO ldap_config (id, enabled, server, bind_user_template, search_base, "
            "group_search_base, group_filter, tls_required, timeout_seconds, user_filter, "
            "attr_username, attr_display_name, attr_email, updated_at, updated_by) "
            "VALUES (1, :enabled, '', '', '', '', '(member={user_dn})', :tls, 5, "
            "'(uid={username})', 'uid', 'displayName', 'mail', :ts, 'system')"
        ),
        {"enabled": False, "tls": True, "ts": now},
    )
    bind.execute(
        sa.text(
            "INSERT INTO smtp_config (id, enabled, host, port, use_tls, username, "
            "mail_from, app_url, updated_at, updated_by) "
            "VALUES (1, :enabled, 'localhost', 1025, :tls, '', "
            "'noreply@bws.local', 'http://localhost:8080', :ts, 'system')"
        ),
        {"enabled": False, "tls": False, "ts": now},
    )
    bind.execute(
        sa.text(
            "INSERT INTO escalation_config (id, enabled, default_sla_days, interval_minutes, "
            "bereichsleiter_role_id, updated_at, updated_by) "
            "VALUES (1, :enabled, 14, 60, :rid, :ts, 'system')"
        ),
        {"enabled": False, "rid": role_id_by_name.get("Bereichsleiter"), "ts": now},
    )

    # Notification-Templates
    for key, (subject, body) in _TEMPLATE_SEED.items():
        bind.execute(
            sa.text(
                "INSERT INTO notification_templates (id, key, subject, body, updated_at, updated_by) "
                "VALUES (:id, :k, :s, :b, :ts, 'system')"
            ),
            {"id": _uuid(), "k": key, "s": subject, "b": body, "ts": now},
        )

    # App-Settings (Defaults)
    for key, value in [("auth.mode", "local"), ("auth.login_rate_limit", "5/minute")]:
        bind.execute(
            sa.text(
                "INSERT INTO app_settings (key, value, updated_at, updated_by) "
                "VALUES (:k, :v, :ts, 'system')"
            ),
            {"k": key, "v": value, "ts": now},
        )

    # ---------------- Best-Effort Legacy-Import ----------------
    # Brownfield: bestehende config/users.json + role_emails.toml in die DB heben.
    _try_import_users_json(bind, role_id_by_name, now)
    _try_import_role_emails_toml(bind, role_id_by_name)


def _try_import_users_json(bind, role_id_by_name: dict[str, str], now: datetime) -> None:
    path = Path(os.getenv("USERS_CONFIG_PATH", "config/users.json"))
    if not path.exists():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    seen_usernames: set[str] = set()
    for entry in raw.get("users", []):
        username = entry.get("username")
        if not username or username in seen_usernames:
            continue
        seen_usernames.add(username)
        # Wir importieren keine Notfall-User in die regulaere User-Tabelle.
        if entry.get("is_emergency"):
            continue
        uid = _uuid()
        bind.execute(
            sa.text(
                "INSERT INTO users (id, username, display_name, email, auth_source, "
                "password_argon2, is_active, is_emergency, created_at, updated_at) "
                "VALUES (:id, :u, :n, :e, 'local', :pw, :active, :emerg, :ts, :ts)"
            ),
            {"id": uid, "u": username, "n": entry.get("name") or username,
             "e": entry.get("email") or None, "pw": entry.get("password_argon2"),
             "active": True, "emerg": False, "ts": now},
        )
        seen_pairs: set[tuple[str, str]] = set()
        for role_name in entry.get("roles", []):
            rid = role_id_by_name.get(role_name)
            if rid and (uid, rid) not in seen_pairs:
                seen_pairs.add((uid, rid))
                bind.execute(
                    sa.text("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r)"),
                    {"u": uid, "r": rid},
                )


def _try_import_role_emails_toml(bind, role_id_by_name: dict[str, str]) -> None:
    path = Path(os.getenv("ROLE_EMAILS_PATH", "config/role_emails.toml"))
    if not path.exists():
        return
    try:
        import tomllib
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except Exception:
        return
    section = raw.get("role_emails", {})
    seen: set[tuple[str, str]] = set()
    for role_name, addrs in section.items():
        rid = role_id_by_name.get(role_name)
        if not rid or not isinstance(addrs, list):
            continue
        for addr in addrs:
            if not isinstance(addr, str) or not addr.strip():
                continue
            key = (rid, addr.strip())
            if key in seen:
                continue
            seen.add(key)
            bind.execute(
                sa.text(
                    "INSERT INTO role_emails (id, role_id, email) VALUES (:id, :r, :e)"
                ),
                {"id": _uuid(), "r": rid, "e": addr.strip()},
            )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("escalation_config")
    op.drop_index("ix_role_emails_role_id", table_name="role_emails")
    op.drop_table("role_emails")
    op.drop_index("ix_notification_templates_key", table_name="notification_templates")
    op.drop_table("notification_templates")
    op.drop_table("smtp_config")
    op.drop_index("ix_ldap_role_mapping_group_dn", table_name="ldap_role_mapping")
    op.drop_table("ldap_role_mapping")
    op.drop_table("ldap_config")
    op.drop_index("ix_user_roles_user_id", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_index("ix_role_permissions_role_id", table_name="role_permissions")
    op.drop_table("role_permissions")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_roles_name", table_name="roles")
    op.drop_table("roles")
    op.drop_index("ix_permissions_code", table_name="permissions")
    op.drop_table("permissions")
