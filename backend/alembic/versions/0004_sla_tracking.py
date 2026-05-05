"""sla tracking columns on form_instances

Revision ID: 0004_sla_tracking
Revises: 0003_attachments
Create Date: 2026-05-04 20:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_sla_tracking"
down_revision: Union[str, Sequence[str], None] = "0003_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Wann das letzte Mal die Erinnerung (Stufe 1) bzw. die Eskalation (Stufe 2)
    # fuer diese Instance verschickt wurde — Idempotenz-Anker fuer den Scheduler.
    with op.batch_alter_table("form_instances") as batch:
        batch.add_column(sa.Column("stage_eingetreten_am", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("erinnerung_sent_at",   sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("eskalation_sent_at",   sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("form_instances") as batch:
        batch.drop_column("eskalation_sent_at")
        batch.drop_column("erinnerung_sent_at")
        batch.drop_column("stage_eingetreten_am")
