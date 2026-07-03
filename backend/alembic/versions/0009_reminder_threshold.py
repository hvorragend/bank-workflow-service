"""konfigurierbare SLA-Vorwarnschwelle (reminder_percent) auf escalation_config

Revision ID: 0009_reminder_threshold
Revises: 0008_run_scoping_and_indexes
Create Date: 2026-07-03 13:00:00

N-002: Die Erinnerung (Stufe 1) feuert ab reminder_percent % der verbrauchten
SLA-Frist. Default 80 % (kurz vor Bruch) statt der frueheren festen 50 %.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_reminder_threshold"
down_revision: Union[str, Sequence[str], None] = "0008_run_scoping_and_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("escalation_config") as batch:
        batch.add_column(sa.Column("reminder_percent", sa.Integer(), nullable=False, server_default="80"))


def downgrade() -> None:
    with op.batch_alter_table("escalation_config") as batch:
        batch.drop_column("reminder_percent")
