"""attachments table for file uploads on FormInstances

Revision ID: 0003_attachments
Revises: 0002_audit_events
Create Date: 2026-05-04 19:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_attachments"
down_revision: Union[str, Sequence[str], None] = "0002_audit_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("instance_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("uploaded_by", sa.String(length=100), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["instance_id"], ["form_instances.id"], name="fk_attachments_instance"),
    )
    op.create_index("ix_attachments_instance_id", "attachments", ["instance_id"])
    op.create_index("ix_attachments_sha256",      "attachments", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_attachments_sha256",      table_name="attachments")
    op.drop_index("ix_attachments_instance_id", table_name="attachments")
    op.drop_table("attachments")
