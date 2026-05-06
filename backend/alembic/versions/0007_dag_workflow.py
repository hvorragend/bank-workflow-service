"""DAG-Workflow: workflow_stages -> workflow_graph + form_instance_active_stages

Schema-Aenderungen:
- form_definitions: Spalte workflow_stages (JSON) wird zu workflow_graph (JSON)
- form_instances: Spalten aktuelle_stage / stage_eingetreten_am / erinnerung_sent_at /
  eskalation_sent_at fallen weg (Stage-Tracking wandert in die neue Tabelle)
- Neue Tabelle form_instance_active_stages mit eigenem SLA-Tracking pro aktiver Stage

Datenmigration:
- Alle FormDefinition: linearer workflow_stages-Array wird zu einem linearen Graph
  (start -> n0 -> n1 -> ... -> end) konvertiert. Auch retired-Definitionen, damit
  laufende Instanzen weiter funktionieren.
- Alle FormInstance, die nicht in einem Terminalstatus sind: erhalten eine Zeile
  in form_instance_active_stages (per Mapping aktuelle_stage-Name -> Knoten-ID).
- Pre-Assertion: jede laufende Instanz muss ein Mapping haben. Sonst Migration
  bricht laut ab — keine stillen Datenverluste.

Revision ID: 0007_dag_workflow
Revises: 0006_admin_panel
Create Date: 2026-05-05 22:30:00
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_dag_workflow"
down_revision: Union[str, Sequence[str], None] = "0006_admin_panel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------- Hilfen fuer die Datenmigration ----------

def _stages_to_graph(stages: list[dict[str, Any]]) -> dict[str, Any]:
    """Linearer Stage-Array -> linearer DAG (start -> n0 -> n1 -> ... -> end).

    Knoten-IDs sind die ehemaligen Stage-Namen (eindeutig pro Definition,
    da im Originalmodell auch eindeutig). Falls ein Name leer/duplikat,
    wird ein synthetischer Suffix angehaengt.
    """
    nodes: list[dict[str, Any]] = [{"id": "start", "type": "start"}]
    edges: list[dict[str, Any]] = []
    seen_ids: set[str] = {"start", "end"}
    prev_id = "start"
    for i, s in enumerate(stages):
        raw_name = s.get("name") or f"stage_{i}"
        node_id = raw_name
        if node_id in seen_ids:
            node_id = f"{raw_name}_{i}"
        seen_ids.add(node_id)
        node: dict[str, Any] = {
            "id": node_id,
            "type": "user_task",
            "label": raw_name,
            "rolle": s.get("rolle", ""),
        }
        sla = s.get("sla_days")
        if isinstance(sla, int) and sla > 0:
            node["sla_days"] = sla
        nodes.append(node)
        edges.append({"from": prev_id, "to": node_id})
        prev_id = node_id
    nodes.append({"id": "end", "type": "end"})
    edges.append({"from": prev_id, "to": "end"})
    return {"nodes": nodes, "edges": edges, "_legacy_stage_names": [s.get("name", "") for s in stages]}


def _node_id_for_stage_name(graph: dict[str, Any], stage_name: str) -> str | None:
    """Sucht die Node-ID, die im linearen Graph zum alten Stage-Namen gehoert."""
    if not stage_name:
        return None
    legacy = graph.get("_legacy_stage_names") or []
    for n in graph["nodes"]:
        if n.get("type") == "user_task" and n.get("label") == stage_name:
            return n["id"]
    # Fallback: id == name?
    for n in graph["nodes"]:
        if n.get("id") == stage_name:
            return n["id"]
    # Fallback: legacy-Index
    if stage_name in legacy:
        idx = legacy.index(stage_name)
        user_tasks = [n for n in graph["nodes"] if n.get("type") == "user_task"]
        if 0 <= idx < len(user_tasks):
            return user_tasks[idx]["id"]
    return None


def _rolle_for_stage_name(stages: list[dict[str, Any]], stage_name: str) -> str:
    for s in stages:
        if s.get("name") == stage_name:
            return s.get("rolle", "")
    return ""


# ---------- Upgrade ----------

def upgrade() -> None:
    bind = op.get_bind()

    # 1) Neue Tabelle anlegen.
    op.create_table(
        "form_instance_active_stages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("instance_id", sa.String(length=36), sa.ForeignKey("form_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("rolle", sa.String(length=100), nullable=False),
        sa.Column("eingetreten_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("erinnerung_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eskalation_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("instance_id", "node_id", name="uq_active_stage_instance_node"),
    )
    op.create_index("ix_form_instance_active_stages_instance_id", "form_instance_active_stages", ["instance_id"])
    op.create_index("ix_form_instance_active_stages_rolle", "form_instance_active_stages", ["rolle"])

    # 2) Neue Spalte workflow_graph (nullable, wird gleich befuellt).
    op.add_column("form_definitions", sa.Column("workflow_graph", sa.JSON(), nullable=True))

    # 3) Definitionen konvertieren.
    defs_table = sa.table(
        "form_definitions",
        sa.column("id", sa.String),
        sa.column("workflow_stages", sa.JSON),
        sa.column("workflow_graph", sa.JSON),
    )
    defs = list(bind.execute(sa.select(defs_table.c.id, defs_table.c.workflow_stages)))
    graph_by_def: dict[str, dict[str, Any]] = {}
    stages_by_def: dict[str, list[dict[str, Any]]] = {}
    for row in defs:
        def_id, stages_raw = row
        stages = stages_raw or []
        if isinstance(stages, str):
            stages = json.loads(stages)
        if not isinstance(stages, list):
            stages = []
        graph = _stages_to_graph(stages)
        graph_by_def[def_id] = graph
        stages_by_def[def_id] = stages
        bind.execute(
            sa.update(defs_table)
            .where(defs_table.c.id == def_id)
            .values(workflow_graph=graph)
        )

    # 4) Pre-Assertion + Active-Stages-Migration fuer laufende Instanzen.
    inst_table = sa.table(
        "form_instances",
        sa.column("id", sa.String),
        sa.column("form_definition_id", sa.String),
        sa.column("status", sa.String),
        sa.column("aktuelle_stage", sa.String),
        sa.column("stage_eingetreten_am", sa.DateTime(timezone=True)),
        sa.column("erinnerung_sent_at", sa.DateTime(timezone=True)),
        sa.column("eskalation_sent_at", sa.DateTime(timezone=True)),
    )
    active_table = sa.table(
        "form_instance_active_stages",
        sa.column("id", sa.String),
        sa.column("instance_id", sa.String),
        sa.column("node_id", sa.String),
        sa.column("rolle", sa.String),
        sa.column("eingetreten_am", sa.DateTime(timezone=True)),
        sa.column("erinnerung_sent_at", sa.DateTime(timezone=True)),
        sa.column("eskalation_sent_at", sa.DateTime(timezone=True)),
    )

    rows = list(bind.execute(sa.select(
        inst_table.c.id, inst_table.c.form_definition_id, inst_table.c.status,
        inst_table.c.aktuelle_stage, inst_table.c.stage_eingetreten_am,
        inst_table.c.erinnerung_sent_at, inst_table.c.eskalation_sent_at,
    )))
    unmappable: list[tuple[str, str]] = []
    inserts = []
    for inst_id, def_id, status_, akt_stage, eingetreten, erin, esk in rows:
        if status_ != "in_pruefung":
            continue
        graph = graph_by_def.get(def_id)
        if not graph:
            unmappable.append((inst_id, f"keine Definition {def_id}"))
            continue
        node_id = _node_id_for_stage_name(graph, akt_stage)
        if not node_id:
            unmappable.append((inst_id, f"Stage {akt_stage!r} nicht im DAG"))
            continue
        rolle = _rolle_for_stage_name(stages_by_def.get(def_id, []), akt_stage)
        inserts.append({
            "id": str(uuid.uuid4()),
            "instance_id": inst_id,
            "node_id": node_id,
            "rolle": rolle,
            "eingetreten_am": eingetreten or datetime.utcnow(),
            "erinnerung_sent_at": erin,
            "eskalation_sent_at": esk,
        })
    if unmappable:
        raise RuntimeError(
            "Migration 0006 abgebrochen: laufende Instanzen ohne Mapping ins neue DAG-Modell:\n"
            + "\n".join(f"  - {iid}: {reason}" for iid, reason in unmappable)
        )
    if inserts:
        bind.execute(sa.insert(active_table), inserts)

    # 5) workflow_graph auf NOT NULL stellen, _legacy_stage_names wieder entfernen.
    for def_id, graph in graph_by_def.items():
        clean = {"nodes": graph["nodes"], "edges": graph["edges"]}
        bind.execute(
            sa.update(defs_table)
            .where(defs_table.c.id == def_id)
            .values(workflow_graph=clean)
        )
    with op.batch_alter_table("form_definitions") as batch:
        batch.alter_column("workflow_graph", existing_type=sa.JSON(), nullable=False)
        batch.drop_column("workflow_stages")

    # 6) Spalten von form_instances entfernen.
    with op.batch_alter_table("form_instances") as batch:
        batch.drop_column("aktuelle_stage")
        batch.drop_column("stage_eingetreten_am")
        batch.drop_column("erinnerung_sent_at")
        batch.drop_column("eskalation_sent_at")


def downgrade() -> None:
    """Downgrade ist verlustbehaftet (parallele Branches lassen sich nicht in
    ein lineares Array zurueckabbilden). Fuer Notfaelle: Original-DB-Backup
    einspielen, statt downgrade zu nutzen.
    """
    raise NotImplementedError(
        "Downgrade nicht unterstuetzt: parallele DAGs lassen sich nicht "
        "verlustfrei in lineare workflow_stages zurueckabbilden. "
        "Im Notfall via DB-Backup wiederherstellen."
    )
