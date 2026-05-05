"""initial schema (form_definitions, form_instances, approvals)

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-05 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # form_definitions: versionierte Maskendefinition
    op.create_table(
        "form_definitions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("typ", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("titel", sa.String(length=200), nullable=False),
        sa.Column("json_schema", sa.JSON(), nullable=False),
        sa.Column("ui_schema", sa.JSON(), nullable=False),
        sa.Column("workflow_stages", sa.JSON(), nullable=False),
        sa.Column("gueltig_von", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gueltig_bis", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("erstellt_von", sa.String(length=100), nullable=False),
        sa.UniqueConstraint("typ", "version", name="uq_typ_version"),
    )
    op.create_index("ix_form_definitions_typ", "form_definitions", ["typ"])

    # form_instances: ausgefuellter Antrag, hart an FormDefinition.id gebunden
    op.create_table(
        "form_instances",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("form_definition_id", sa.String(length=36), nullable=False),
        sa.Column("daten", sa.JSON(), nullable=False),
        sa.Column("antragsteller", sa.String(length=100), nullable=False),
        sa.Column("aktuelle_stage", sa.String(length=50), nullable=False, server_default=sa.text("'entwurf'")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'entwurf'")),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("abgeschlossen_am", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["form_definition_id"], ["form_definitions.id"], name="fk_instances_definition"
        ),
    )
    op.create_index("ix_form_instances_form_definition_id", "form_instances", ["form_definition_id"])

    # approvals: revisionssichere Audit-Eintraege pro Stage-Entscheidung
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("instance_id", sa.String(length=36), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("genehmiger", sa.String(length=100), nullable=False),
        sa.Column("rolle", sa.String(length=100), nullable=False),
        sa.Column("entscheidung", sa.String(length=20), nullable=False),
        sa.Column("kommentar", sa.String(length=2000), nullable=True),
        sa.Column("zeitstempel", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["instance_id"], ["form_instances.id"], name="fk_approvals_instance"),
    )
    op.create_index("ix_approvals_instance_id", "approvals", ["instance_id"])


def downgrade() -> None:
    op.drop_index("ix_approvals_instance_id", table_name="approvals")
    op.drop_table("approvals")
    op.drop_index("ix_form_instances_form_definition_id", table_name="form_instances")
    op.drop_table("form_instances")
    op.drop_index("ix_form_definitions_typ", table_name="form_definitions")
    op.drop_table("form_definitions")
