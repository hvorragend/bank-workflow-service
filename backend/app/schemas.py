"""Pydantic schemas for the REST API. Distinct from the *form* JSON schemas
that live in the DB — these here describe the API payloads themselves.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------- FormDefinition ----------

class FormDefinitionCreate(BaseModel):
    typ: str
    version: str
    titel: str
    json_schema: dict[str, Any]
    ui_schema: dict[str, Any]
    workflow_graph: dict[str, Any]
    erstellt_von: str


class FormDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    typ: str
    version: str
    titel: str
    json_schema: dict[str, Any]
    ui_schema: dict[str, Any]
    workflow_graph: dict[str, Any]
    status: str
    gueltig_von: datetime
    gueltig_bis: datetime | None


# ---------- FormInstance ----------

class FormInstanceCreate(BaseModel):
    form_definition_id: str = Field(
        ...,
        description="Concrete FormDefinition ID — pins this instance to a schema version.",
    )
    daten: dict[str, Any]
    # Backwards-Compat: alte Clients duerfen weiter mitsenden — der Server ueberschreibt
    # den Wert aber mit dem Username aus dem JWT.
    antragsteller: str = ""


class FormInstanceUpdate(BaseModel):
    """Aenderung der Antragsdaten eines Entwurfs (PATCH /instances/{id})."""
    daten: dict[str, Any]


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    stage: str
    genehmiger: str
    rolle: str
    entscheidung: str
    kommentar: str | None
    zeitstempel: datetime


class ActiveStageOut(BaseModel):
    """Aktiver User-Task einer FormInstance — eine Zeile pro paralleler Branche."""
    model_config = ConfigDict(from_attributes=True)

    node_id: str
    rolle: str
    eingetreten_am: datetime
    erinnerung_sent_at: datetime | None
    eskalation_sent_at: datetime | None


class FormInstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    form_definition_id: str
    daten: dict[str, Any]
    antragsteller: str
    status: str
    erstellt_am: datetime
    abgeschlossen_am: datetime | None
    approvals: list[ApprovalOut]
    active_stages: list[ActiveStageOut]


class FormInstanceWithSchema(FormInstanceOut):
    """Returned on GET — bundles the originally-pinned schema for the UI to render."""
    json_schema: dict[str, Any]
    ui_schema: dict[str, Any]
    workflow_graph: dict[str, Any]
    schema_version: str


# ---------- Approval action ----------

class ApprovalAction(BaseModel):
    """Genehmigungs-Entscheidung. `genehmiger` und `rolle` werden aus dem JWT-Token
    gelesen, nicht mehr aus dem Body — die Identitaet ist nicht mehr selbst-deklariert.

    `node_id` adressiert den konkreten aktiven User-Task. Bei parallelen Branches
    kann der gleiche User mehrere Tasks gleichzeitig vor sich haben.
    """
    node_id: str
    entscheidung: Literal["approved", "rejected", "returned"]
    kommentar: str | None = None
