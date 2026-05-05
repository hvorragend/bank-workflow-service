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
    workflow_stages: list[dict[str, Any]]
    erstellt_von: str


class FormDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    typ: str
    version: str
    titel: str
    json_schema: dict[str, Any]
    ui_schema: dict[str, Any]
    workflow_stages: list[dict[str, Any]]
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
    antragsteller: str


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    stage: str
    genehmiger: str
    rolle: str
    entscheidung: str
    kommentar: str | None
    zeitstempel: datetime


class FormInstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    form_definition_id: str
    daten: dict[str, Any]
    antragsteller: str
    aktuelle_stage: str
    status: str
    erstellt_am: datetime
    abgeschlossen_am: datetime | None
    approvals: list[ApprovalOut]


class FormInstanceWithSchema(FormInstanceOut):
    """Returned on GET — bundles the originally-pinned schema for the UI to render."""
    json_schema: dict[str, Any]
    ui_schema: dict[str, Any]
    workflow_stages: list[dict[str, Any]]
    schema_version: str


# ---------- Approval action ----------

class ApprovalAction(BaseModel):
    genehmiger: str
    rolle: str
    entscheidung: Literal["approved", "rejected", "returned"]
    kommentar: str | None = None
