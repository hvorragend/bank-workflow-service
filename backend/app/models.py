"""ORM models. The hard rule: a FormInstance always points to a CONCRETE FormDefinition
version (by id), never to "the type". This is what makes audit-safe schema versioning work.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class FormDefinition(Base):
    """Versioned form template. Once status='active', the JSON schema MUST NOT be
    modified — any change is a new version. This guarantees that historical
    instances always render with the schema they were created against.
    """
    __tablename__ = "form_definitions"
    __table_args__ = (UniqueConstraint("typ", "version", name="uq_typ_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    typ: Mapped[str] = mapped_column(String(100), index=True)         # e.g. "AT_8_2_Analyse"
    version: Mapped[str] = mapped_column(String(20))                  # SemVer "2.0.0"
    titel: Mapped[str] = mapped_column(String(200))

    json_schema: Mapped[dict[str, Any]] = mapped_column(JSON)
    ui_schema: Mapped[dict[str, Any]] = mapped_column(JSON)
    workflow_graph: Mapped[dict[str, Any]] = mapped_column(JSON)
    # Workflow-DAG mit Knoten (start, user_task, parallel_split, parallel_join, end)
    # und Kanten {from, to}. Der Validator in app.workflow_graph.validate_graph
    # erzwingt die Strukturregeln (genau 1 Start, ≥1 End, keine Zyklen, SESE-Splits).

    gueltig_von: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    gueltig_bis: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | active | retired

    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    erstellt_von: Mapped[str] = mapped_column(String(100))


class FormInstance(Base):
    """A filled-out form, frozen against the schema version it was created with."""
    __tablename__ = "form_instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    form_definition_id: Mapped[str] = mapped_column(
        ForeignKey("form_definitions.id"), index=True
    )

    daten: Mapped[dict[str, Any]] = mapped_column(JSON)
    antragsteller: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="entwurf")
    # entwurf | in_pruefung | genehmigt | abgelehnt | zurueckgewiesen

    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    abgeschlossen_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    definition: Mapped[FormDefinition] = relationship(lazy="joined")
    approvals: Mapped[list[Approval]] = relationship(
        back_populates="instance", order_by="Approval.zeitstempel"
    )
    # Aktive Tasks (parallele Branches): null oder mehrere Eintraege, jeder
    # mit eigenem SLA-Tracking. Bei terminalem Status (genehmigt/abgelehnt)
    # ist die Liste leer.
    active_stages: Mapped[list[FormInstanceActiveStage]] = relationship(
        back_populates="instance", cascade="all, delete-orphan",
    )


class FormInstanceActiveStage(Base):
    """Aktiver User-Task einer FormInstance.

    Mit der Umstellung auf einen Workflow-DAG koennen mehrere Tasks gleichzeitig
    aktiv sein (parallele Branches). Pro aktivem Task wird hier eine Zeile gefuehrt;
    SLA-Reminder und Eskalation werden per Zeile getrackt, damit jeder Branch
    eine eigene SLA-Uhr hat.
    """
    __tablename__ = "form_instance_active_stages"
    __table_args__ = (
        UniqueConstraint("instance_id", "node_id", name="uq_active_stage_instance_node"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    instance_id: Mapped[str] = mapped_column(
        ForeignKey("form_instances.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str] = mapped_column(String(64))
    rolle: Mapped[str] = mapped_column(String(100), index=True)
    eingetreten_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    erinnerung_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    eskalation_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    instance: Mapped[FormInstance] = relationship(back_populates="active_stages")


class Approval(Base):
    """Immutable audit record per workflow step. Once written, never modified."""
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    instance_id: Mapped[str] = mapped_column(ForeignKey("form_instances.id"), index=True)
    stage: Mapped[str] = mapped_column(String(64))  # node_id im neuen DAG-Modell
    genehmiger: Mapped[str] = mapped_column(String(100))
    rolle: Mapped[str] = mapped_column(String(100))
    entscheidung: Mapped[str] = mapped_column(String(20))
    # approved | rejected | returned
    kommentar: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    zeitstempel: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    instance: Mapped[FormInstance] = relationship(back_populates="approvals")


class AuditEvent(Base):
    """Audit-Eintrag fuer Admin-Sicht (Login/Logout, Definition-Lifecycle, …).

    Doppelt gefuehrt: zusaetzlich zum strukturierten Container-Log auch in der DB,
    damit der Admin-Bereich Filter und Suche bedienen kann. Bei viel Volumen
    (Phase 3) sollte das in eine separate DB oder ein Logaggregator wandern.
    """
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    zeitstempel: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    kategorie: Mapped[str] = mapped_column(String(30), index=True)
    # Aktion in Punkt-Notation: 'login.success', 'definition.uploaded', 'definition.activated', …
    action: Mapped[str] = mapped_column(String(80))
    akteur: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    target_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Attachment(Base):
    """Datei-Anhang an einem Antrag. Inhalt liegt im Storage-Backend (Filesystem
    oder spaeter S3-kompatibel), Metadaten + SHA-256 in der DB.
    """
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    instance_id: Mapped[str] = mapped_column(ForeignKey("form_instances.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(255))
    uploaded_by: Mapped[str] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    instance: Mapped[FormInstance] = relationship()


class ApiToken(Base):
    """API-Token fuer Reporting-Endpunkte (Aufsicht / Revision).

    Klartext ist nur einmalig beim POST sichtbar — anschliessend liegt nur der
    SHA-256-Hash in der DB. Tokens haben Scopes (typischerweise ['reporting:read'])
    und koennen widerrufen werden (revoked_at gesetzt).
    """
    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    scopes: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_by: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Admin-Panel-Modelle (Phase 4)
# ---------------------------------------------------------------------------


class User(Base):
    """DB-persistierter User. Ersetzt config/users.json. Notfall-User leben weiter
    als JSON-Datei (config/emergency_users.json); sie bekommen beim Login einen
    eigenen Audit-Pfad und tauchen nicht in dieser Tabelle auf.
    """
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    auth_source: Mapped[str] = mapped_column(String(20))  # local | ldap
    password_argon2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False)
    ldap_dn: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    roles: Mapped[list[Role]] = relationship(secondary="user_roles", lazy="selectin")


class Role(Base):
    """Rolle als zuweisbare Sammlung von Permissions. 'Admin' ist `is_system=True`
    und nicht loeschbar. Workflow-Stage-Rollen (Vorstand, Compliance, ...) werden
    in der Migration als Default-Rollen geseedet.
    """
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    permissions: Mapped[list[Permission]] = relationship(secondary="role_permissions", lazy="selectin")


class Permission(Base):
    """Permission-Code aus dem Katalog (z. B. 'admin.users.write').
    Quelle ist app/auth/permission_catalog.py — beim Start re-seeded.
    """
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    area: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(500))


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    permission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True
    )


class LdapConfig(Base):
    """Single-Row-Tabelle (id=1) mit der aktuellen LDAP-Konfiguration.
    Sensible Felder (Service-Account-Passwort) liegen Fernet-verschluesselt.
    """
    __tablename__ = "ldap_config"
    __table_args__ = (CheckConstraint("id = 1", name="ck_ldap_config_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # immer 1
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    server: Mapped[str] = mapped_column(String(500), default="")
    bind_user_template: Mapped[str] = mapped_column(String(500), default="")
    search_base: Mapped[str] = mapped_column(String(500), default="")
    group_search_base: Mapped[str] = mapped_column(String(500), default="")
    group_filter: Mapped[str] = mapped_column(String(500), default="(member={user_dn})")
    tls_required: Mapped[bool] = mapped_column(Boolean, default=True)
    ca_cert_pem: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=5)
    service_account_dn: Mapped[str | None] = mapped_column(String(500), nullable=True)
    service_account_pw_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_filter: Mapped[str] = mapped_column(String(500), default="(uid={username})")
    attr_username: Mapped[str] = mapped_column(String(80), default="uid")
    attr_display_name: Mapped[str] = mapped_column(String(80), default="displayName")
    attr_email: Mapped[str] = mapped_column(String(80), default="mail")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    updated_by: Mapped[str] = mapped_column(String(150), default="system")


class LdapRoleMapping(Base):
    """N Rows: LDAP-Group-DN -> Role. Ersetzt role_mapping aus ldap.toml."""
    __tablename__ = "ldap_role_mapping"
    __table_args__ = (UniqueConstraint("group_dn", "role_id", name="uq_ldap_role_mapping"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_dn: Mapped[str] = mapped_column(String(500), index=True)
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id", ondelete="CASCADE"))


class SmtpConfig(Base):
    """Single-Row-Tabelle (id=1). Passwort liegt Fernet-verschluesselt."""
    __tablename__ = "smtp_config"
    __table_args__ = (CheckConstraint("id = 1", name="ck_smtp_config_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    host: Mapped[str] = mapped_column(String(255), default="localhost")
    port: Mapped[int] = mapped_column(Integer, default=1025)
    use_tls: Mapped[bool] = mapped_column(Boolean, default=False)
    username: Mapped[str] = mapped_column(String(255), default="")
    password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    mail_from: Mapped[str] = mapped_column(String(320), default="noreply@bws.local")
    app_url: Mapped[str] = mapped_column(String(500), default="http://localhost:8080")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    updated_by: Mapped[str] = mapped_column(String(150), default="system")


class EscalationConfig(Base):
    """Single-Row-Tabelle (id=1) fuer SLA-Eskalations-Scheduler."""
    __tablename__ = "escalation_config"
    __table_args__ = (CheckConstraint("id = 1", name="ck_escalation_config_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    default_sla_days: Mapped[int] = mapped_column(Integer, default=14)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    bereichsleiter_role_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    updated_by: Mapped[str] = mapped_column(String(150), default="system")


class RoleEmail(Base):
    """N Rows: zusaetzliche Empfaenger-Adressen pro Rolle (Gruppenpostfaecher).
    Ersetzt config/role_emails.toml. Ergaenzt — nicht ersetzt — die Mail aus den
    User-Eintraegen mit der entsprechenden Rolle.
    """
    __tablename__ = "role_emails"
    __table_args__ = (UniqueConstraint("role_id", "email", name="uq_role_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320))


class NotificationTemplate(Base):
    """E-Mail-Template, gepflegt im Admin-Panel. body verwendet $varname-Syntax
    (string.Template.safe_substitute) — bewusst kein Jinja, damit Admins kein
    Code injizieren koennen.
    """
    __tablename__ = "notification_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    # bekannte Keys: stage_review_pending | approved | rejected | returned
    #                | sla_erinnerung | sla_eskalation
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    updated_by: Mapped[str] = mapped_column(String(150), default="system")


class AppSetting(Base):
    """Kleines Key-Value-Lager fuer Runtime-Toggles (auth.mode, login_rate_limit, ...).
    Bewusst kein generischer Settings-Blob fuer typisierte Configs — diese liegen
    als getypte Single-Row-Tabellen oben.
    """
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    updated_by: Mapped[str] = mapped_column(String(150), default="system")
