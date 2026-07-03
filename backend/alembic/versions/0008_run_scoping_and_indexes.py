"""run-scoping (lauf) fuer Approvals + Indizes auf haeufig gefilterten Spalten

Revision ID: 0008_run_scoping_and_indexes
Revises: 0007_dag_workflow
Create Date: 2026-07-03 12:00:00

- form_instances.lauf / approvals.lauf: Durchlauf-Zaehler. Bestehende Zeilen
  bekommen lauf=1 (der laufende erste Durchlauf), damit ihre bereits erfassten
  Approvals weiterhin fuer die Join-Auswertung zaehlen (Audit F-004).
- Indizes auf form_instances.status/erstellt_am/abgeschlossen_am/antragsteller
  (Liste, Stats, Scanner, Sortierung — Audit O-006).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_run_scoping_and_indexes"
down_revision: Union[str, Sequence[str], None] = "0007_dag_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("form_instances") as batch:
        batch.add_column(sa.Column("lauf", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("approvals") as batch:
        batch.add_column(sa.Column("lauf", sa.Integer(), nullable=False, server_default="0"))

    # Bestehende, evtl. noch laufende Instanzen: als Durchlauf 1 markieren, damit
    # ihre bereits gefallenen Approvals weiter zaehlen.
    op.execute("UPDATE form_instances SET lauf = 1 WHERE status IN ('in_pruefung', 'genehmigt', 'abgelehnt')")
    op.execute("UPDATE approvals SET lauf = 1")

    op.create_index("ix_form_instances_status", "form_instances", ["status"])
    op.create_index("ix_form_instances_erstellt_am", "form_instances", ["erstellt_am"])
    op.create_index("ix_form_instances_abgeschlossen_am", "form_instances", ["abgeschlossen_am"])
    op.create_index("ix_form_instances_antragsteller", "form_instances", ["antragsteller"])


def downgrade() -> None:
    op.drop_index("ix_form_instances_antragsteller", table_name="form_instances")
    op.drop_index("ix_form_instances_abgeschlossen_am", table_name="form_instances")
    op.drop_index("ix_form_instances_erstellt_am", table_name="form_instances")
    op.drop_index("ix_form_instances_status", table_name="form_instances")
    with op.batch_alter_table("approvals") as batch:
        batch.drop_column("lauf")
    with op.batch_alter_table("form_instances") as batch:
        batch.drop_column("lauf")
