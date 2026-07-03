"""Workflow-Engine fuer DAG-basierte Definitionen mit parallelen Branches.

Eine FormInstance kann mehrere `active_stages`-Eintraege haben — jeder
entspricht einem User-Task, der gerade auf eine Entscheidung wartet. Beim
Submit werden initial alle vom Start aus erreichbaren User-Tasks aktiviert
(bei einem direkten Parallel-Split: alle Branches gleichzeitig). Beim
Approven eines Tasks wird der Nachfolger aktiviert; trifft eine Branche
einen Parallel-Join, wartet die Engine auf alle Branches, bevor der
Nachfolger des Joins aktiv wird.

Rejection / Returned in einem Branch kassiert die ganze Instance — das
vermeidet Deadlocks am Join und entspricht der bisherigen Semantik.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from . import models
from . import workflow_graph as wg


class WorkflowError(Exception):
    """Raised when an action is invalid for the current state."""


# Per-Instanz-Lock: serialisiert konkurrierende Entscheidungen auf demselben
# Antrag innerhalb des Prozesses. Ohne das koennen zwei parallele Approvals der
# letzten Branches beide eine veraltete Sicht sehen, den Join verpassen und die
# Instanz dauerhaft haengen lassen (F-003). Gilt fuer den dokumentierten
# Single-Worker-Betrieb (S-007); bei Multi-Prozess-Betrieb waere zusaetzlich ein
# DB-Lock noetig.
_instance_locks: dict[str, threading.Lock] = {}
_instance_locks_guard = threading.Lock()


def instance_lock(instance_id: str) -> threading.Lock:
    with _instance_locks_guard:
        lock = _instance_locks.get(instance_id)
        if lock is None:
            lock = threading.Lock()
            _instance_locks[instance_id] = lock
        return lock


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------- Submit ----------

def submit(instance: models.FormInstance) -> list[models.FormInstanceActiveStage]:
    """Schiebt eine Instance vom Entwurf in die erste Pruefung. Gibt die
    Liste der initial aktivierten Tasks zurueck (1 oder mehr bei direktem
    Parallel-Split)."""
    if instance.status != "entwurf":
        raise WorkflowError(f"Antrag ist nicht im Entwurfsstatus (aktuell: {instance.status}).")

    graph = instance.definition.workflow_graph
    if not graph or not graph.get("nodes"):
        raise WorkflowError("Diese Formulardefinition hat keinen Workflow-Graph.")

    initial = wg.initial_active_tasks(graph)
    if not initial:
        raise WorkflowError("Workflow-Graph hat keine User-Tasks — Submit nicht moeglich.")

    instance.status = "in_pruefung"
    # Jeder Submit startet einen neuen Durchlauf. Approvals dieses Durchlaufs
    # zaehlen fuer die Join-Auswertung; Genehmigungen aus einem frueheren
    # (zurueckgewiesenen) Durchlauf bleiben als Audit erhalten, wirken aber nicht
    # mehr auf den aktuellen Ablauf (F-004).
    instance.lauf = (instance.lauf or 0) + 1
    activated: list[models.FormInstanceActiveStage] = []
    for task in initial:
        a = models.FormInstanceActiveStage(
            instance_id=instance.id,
            node_id=task["id"],
            rolle=task["rolle"],
            eingetreten_am=_utcnow(),
        )
        instance.active_stages.append(a)
        activated.append(a)
    return activated


# ---------- Decide ----------

def decide(
    db: Session,
    instance: models.FormInstance,
    *,
    node_id: str,
    genehmiger: str,
    user_roles: list[str],
    entscheidung: str,
    kommentar: str | None,
) -> tuple[models.Approval, list[models.FormInstanceActiveStage]]:
    """Wendet eine Entscheidung auf den angegebenen aktiven Task an.

    Returns (approval, newly_activated_tasks). Bei rejected/returned sind keine
    neuen Tasks aktiviert; alle bisher aktiven werden geleert.
    """
    if instance.status != "in_pruefung":
        raise WorkflowError(
            f"Antrag ist nicht in Pruefung (aktuell: {instance.status}). "
            "Genehmigung nicht moeglich."
        )

    graph = instance.definition.workflow_graph
    by_id = wg.nodes_by_id(graph)

    active_by_node = {a.node_id: a for a in instance.active_stages}
    if node_id not in active_by_node:
        raise WorkflowError(
            f"Stage {node_id!r} ist nicht aktiv. Aktive Stages: {sorted(active_by_node)}."
        )
    active_row = active_by_node[node_id]

    node = by_id.get(node_id)
    if not node or node.get("type") != "user_task":
        raise WorkflowError(f"Knoten {node_id!r} ist kein User-Task.")
    expected_rolle = node["rolle"]
    if expected_rolle not in user_roles:
        raise WorkflowError(
            f"Erforderliche Rolle nicht vorhanden. Benoetigt: '{expected_rolle}', "
            f"vorhanden: {sorted(user_roles)}."
        )

    if entscheidung not in {"approved", "rejected", "returned"}:
        raise WorkflowError(f"Unbekannte Entscheidung: {entscheidung}.")

    # Audit-Eintrag wird IMMER geschrieben — auch bei Ablehnung. Stage = Knoten-ID.
    approval = models.Approval(
        instance_id=instance.id,
        stage=node_id,
        lauf=instance.lauf,
        genehmiger=genehmiger,
        rolle=expected_rolle,
        entscheidung=entscheidung,
        kommentar=kommentar,
    )
    db.add(approval)

    if entscheidung == "rejected":
        instance.status = "abgelehnt"
        instance.abgeschlossen_am = _utcnow()
        _clear_active(instance)
        return approval, []

    if entscheidung == "returned":
        instance.status = "entwurf"
        instance.abgeschlossen_am = None
        _clear_active(instance)
        return approval, []

    # ---- approved ----
    # Den entschiedenen Task entfernen.
    instance.active_stages.remove(active_row)
    db.delete(active_row)
    db.flush()

    # Approvals des AKTUELLEN Durchlaufs zur Arrival-Berechnung sammeln — nicht
    # die historischen aus einem zurueckgewiesenen Vorlauf (F-004).
    approved_node_ids = {
        ap.stage for ap in instance.approvals
        if ap.entscheidung == "approved" and ap.lauf == instance.lauf
    }
    approved_node_ids.add(node_id)  # gerade hinzugefuegt, evtl. noch nicht reflected

    newly_activated: list[models.FormInstanceActiveStage] = []
    out_edges = wg.outgoing(graph, node_id)
    if not out_edges:
        # Sollte vom Validator ausgeschlossen sein — defensive.
        if not instance.active_stages:
            instance.status = "genehmigt"
            instance.abgeschlossen_am = _utcnow()
        return approval, newly_activated

    for succ_id in out_edges:
        newly_activated += _activate(db, instance, graph, succ_id, approved_node_ids)

    # Wenn nichts mehr aktiv ist und das Ende erreicht wurde: Genehmigt.
    if not instance.active_stages:
        instance.status = "genehmigt"
        instance.abgeschlossen_am = _utcnow()

    return approval, newly_activated


def _clear_active(instance: models.FormInstance) -> None:
    for a in list(instance.active_stages):
        instance.active_stages.remove(a)


def _activate(
    db: Session,
    instance: models.FormInstance,
    graph: dict,
    node_id: str,
    approved_node_ids: set[str],
) -> list[models.FormInstanceActiveStage]:
    """Aktiviert den naechsten Knoten ab `node_id`. Folgt Splits/Joins/Ends.

    Gibt die Liste der neu erzeugten User-Task-Aktivierungen zurueck (fuer
    Notification-Dispatch im Caller).
    """
    by_id = wg.nodes_by_id(graph)
    node = by_id[node_id]
    t = node["type"]
    new_active: list[models.FormInstanceActiveStage] = []

    if t == "user_task":
        # Idempotenz: gleichen Knoten nicht doppelt aktivieren.
        if any(a.node_id == node_id for a in instance.active_stages):
            return new_active
        a = models.FormInstanceActiveStage(
            instance_id=instance.id,
            node_id=node_id,
            rolle=node["rolle"],
            eingetreten_am=_utcnow(),
        )
        instance.active_stages.append(a)
        new_active.append(a)
        return new_active

    if t == "parallel_split":
        for nxt in wg.outgoing(graph, node_id):
            new_active += _activate(db, instance, graph, nxt, approved_node_ids)
        return new_active

    if t == "parallel_join":
        if not wg.join_ready(graph, node_id, approved_node_ids):
            # Andere Branches noch ausstehend.
            return new_active
        for nxt in wg.outgoing(graph, node_id):
            new_active += _activate(db, instance, graph, nxt, approved_node_ids)
        return new_active

    if t == "end":
        # End-Knoten: keine Aktivierung. Caller setzt Status, sobald nichts mehr aktiv ist.
        return new_active

    if t == "start":
        # Sollte nur vom Submit erreichbar sein — defensive.
        for nxt in wg.outgoing(graph, node_id):
            new_active += _activate(db, instance, graph, nxt, approved_node_ids)
        return new_active

    raise WorkflowError(f"Unbekannter Knotentyp beim Aktivieren: {t!r}")
