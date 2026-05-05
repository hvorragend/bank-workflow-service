"""ORM models. The hard rule: a FormInstance always points to a CONCRETE FormDefinition
version (by id), never to "the type". This is what makes audit-safe schema versioning work.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
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
    workflow_stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    # Example workflow_stages:
    # [{"name": "fachbereich", "rolle": "Fachbereichsleiter"},
    #  {"name": "risikomgmt",  "rolle": "Risikomanagement"},
    #  {"name": "vorstand",    "rolle": "Vorstand"}]

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
    aktuelle_stage: Mapped[str] = mapped_column(String(50), default="entwurf")
    status: Mapped[str] = mapped_column(String(20), default="entwurf")
    # entwurf | in_pruefung | genehmigt | abgelehnt | zurueckgewiesen

    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    abgeschlossen_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    definition: Mapped[FormDefinition] = relationship(lazy="joined")
    approvals: Mapped[list[Approval]] = relationship(
        back_populates="instance", order_by="Approval.zeitstempel"
    )


class Approval(Base):
    """Immutable audit record per workflow step. Once written, never modified."""
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    instance_id: Mapped[str] = mapped_column(ForeignKey("form_instances.id"), index=True)
    stage: Mapped[str] = mapped_column(String(50))
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
