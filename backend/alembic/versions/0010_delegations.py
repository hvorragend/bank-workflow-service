"""Abwesenheits-Vertretungen (delegations)

Revision ID: 0010_delegations
Revises: 0009_reminder_threshold
Create Date: 2026-07-03 14:00:00

N-001: Tabelle fuer Vertretungen. Waehrend [von_datum, bis_datum] erhaelt der
Vertreter zusaetzlich die Rollen-Benachrichtigungen des Abwesenden.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_delegations"
down_revision: Union[str, Sequence[str], None] = "0009_reminder_threshold"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "delegations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("from_username", sa.String(length=100), nullable=False),
        sa.Column("to_username", sa.String(length=100), nullable=False),
        sa.Column("von_datum", sa.Date(), nullable=False),
        sa.Column("bis_datum", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_delegations_from_username", "delegations", ["from_username"])


def downgrade() -> None:
    op.drop_index("ix_delegations_from_username", table_name="delegations")
    op.drop_table("delegations")
