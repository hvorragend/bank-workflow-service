"""audit_events table for Admin-Audit-Log

Revision ID: 0002_audit_events
Revises: 0001_initial_schema
Create Date: 2026-05-04 18:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_audit_events"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("zeitstempel", sa.DateTime(timezone=True), nullable=False),
        # Kategorie: auth, definition, instance, admin
        sa.Column("kategorie", sa.String(length=30), nullable=False),
        # Action: login.success, login.failure, definition.created, definition.activated, ...
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("akteur", sa.String(length=100), nullable=True),
        sa.Column("target_type", sa.String(length=60), nullable=True),
        sa.Column("target_id", sa.String(length=36), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
    )
    op.create_index("ix_audit_events_zeitstempel", "audit_events", ["zeitstempel"])
    op.create_index("ix_audit_events_kategorie",   "audit_events", ["kategorie"])
    op.create_index("ix_audit_events_akteur",      "audit_events", ["akteur"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_akteur",      table_name="audit_events")
    op.drop_index("ix_audit_events_kategorie",   table_name="audit_events")
    op.drop_index("ix_audit_events_zeitstempel", table_name="audit_events")
    op.drop_table("audit_events")
