"""Pydantic-Schemas fuer alle Admin-Panel-Endpunkte.

In/Out-Modelle pro Bereich; Passwort-Felder werden beim GET als `null` mit
`password_set: bool` zurueckgegeben — beim PUT bedeutet `null` 'unveraendert',
`""` 'loeschen'.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------- User ----------

class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    email: str | None = None
    auth_source: str
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime
    roles: list[str] = []


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=150)
    display_name: str = Field(..., min_length=1, max_length=200)
    email: str | None = None
    password: str = Field(..., min_length=8, max_length=512)
    role_ids: list[str] = []


class UserUpdate(BaseModel):
    display_name: str | None = None
    email: str | None = None
    is_active: bool | None = None


class UserPasswordUpdate(BaseModel):
    password: str = Field(..., min_length=8, max_length=512)


class UserRolesUpdate(BaseModel):
    role_ids: list[str]


# ---------- Roles & Permissions ----------

class PermissionOut(BaseModel):
    id: str
    code: str
    area: str
    description: str


class RoleOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    is_system: bool
    permission_codes: list[str] = []


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: str | None = None
    permission_codes: list[str] = []


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class RolePermissionsUpdate(BaseModel):
    permission_codes: list[str]


# ---------- Auth-Mode ----------

class AuthModeOut(BaseModel):
    mode: Literal["local", "ldap", "both"]
    login_rate_limit: str


class AuthModeUpdate(BaseModel):
    mode: Literal["local", "ldap", "both"]
    login_rate_limit: str | None = None


# ---------- LDAP ----------

class LdapConfigOut(BaseModel):
    enabled: bool
    server: str
    bind_user_template: str
    search_base: str
    group_search_base: str
    group_filter: str
    tls_required: bool
    ca_cert_pem: str | None = None
    timeout_seconds: int
    service_account_dn: str | None = None
    service_account_password_set: bool
    user_filter: str
    attr_username: str
    attr_display_name: str
    attr_email: str
    updated_at: datetime
    updated_by: str


class LdapConfigUpdate(BaseModel):
    enabled: bool | None = None
    server: str | None = None
    bind_user_template: str | None = None
    search_base: str | None = None
    group_search_base: str | None = None
    group_filter: str | None = None
    tls_required: bool | None = None
    ca_cert_pem: str | None = None
    timeout_seconds: int | None = None
    service_account_dn: str | None = None
    # None = unveraendert. "" = loeschen. Sonst: neuer Wert.
    service_account_password: str | None = None
    user_filter: str | None = None
    attr_username: str | None = None
    attr_display_name: str | None = None
    attr_email: str | None = None


class LdapRoleMappingOut(BaseModel):
    id: str
    group_dn: str
    role_id: str
    role_name: str


class LdapRoleMappingCreate(BaseModel):
    group_dn: str = Field(..., min_length=1, max_length=500)
    role_id: str


class LdapTestBindRequest(BaseModel):
    username: str
    password: str


class LdapTestResult(BaseModel):
    ok: bool
    message: str
    roles: list[str] = []
    display_name: str | None = None
    email: str | None = None


class LdapSyncJobOut(BaseModel):
    id: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    counts: dict[str, int]
    error: str | None = None
    dry_run: bool = False


# ---------- SMTP & Notifications ----------

class SmtpConfigOut(BaseModel):
    enabled: bool
    host: str
    port: int
    use_tls: bool
    username: str
    password_set: bool
    mail_from: str
    app_url: str
    updated_at: datetime
    updated_by: str


class SmtpConfigUpdate(BaseModel):
    enabled: bool | None = None
    host: str | None = None
    port: int | None = None
    use_tls: bool | None = None
    username: str | None = None
    password: str | None = None  # None unveraendert, "" loeschen, sonst neuer Wert
    mail_from: str | None = None
    app_url: str | None = None


class SmtpTestRequest(BaseModel):
    to: str
    subject: str = "Bank Workflow Service — Test-Mail"
    body: str = "Wenn diese Mail eintrifft, ist der SMTP-Versand korrekt konfiguriert."


class NotificationTemplateOut(BaseModel):
    key: str
    subject: str
    body: str
    updated_at: datetime
    updated_by: str


class NotificationTemplateUpdate(BaseModel):
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1)


class TemplatePreviewRequest(BaseModel):
    subject: str
    body: str
    context: dict[str, str] = {}


class RoleEmailOut(BaseModel):
    id: str
    role_id: str
    role_name: str
    email: str


class RoleEmailsUpdate(BaseModel):
    emails: list[str]


# ---------- Escalation ----------

class EscalationConfigOut(BaseModel):
    enabled: bool
    default_sla_days: int
    interval_minutes: int
    reminder_percent: int
    bereichsleiter_role_id: str | None = None
    bereichsleiter_role_name: str | None = None
    updated_at: datetime
    updated_by: str
    scheduler_running: bool = False
    scheduler_interval_minutes: int | None = None


class EscalationConfigUpdate(BaseModel):
    enabled: bool | None = None
    default_sla_days: int | None = Field(None, ge=1, le=3650)
    interval_minutes: int | None = Field(None, ge=1, le=1440)
    # Vorwarn-Schwelle in Prozent der SLA-Frist (1–99).
    reminder_percent: int | None = Field(None, ge=1, le=99)
    bereichsleiter_role_id: str | None = None


# ---------- System ----------

class SystemStatus(BaseModel):
    encryption_key_fingerprint: str
    db_ok: bool
    scheduler_running: bool
    smtp_enabled: bool
    smtp_host: str
    ldap_enabled: bool
    ldap_server: str
    auth_mode: str
    user_count: int
    admin_count: int
    emergency_users_loaded: int


class RekeyResult(BaseModel):
    smtp_password: bool
    ldap_service_password: bool
