"""Unit-Tests fuer den Workflow-Graph-Validator.

Pure-Function-Tests ohne DB. Decken die kritischen Strukturregeln ab:
- Genau 1 Start, mind. 1 End
- Keine Zyklen
- Parallel-Splits muessen einen passenden Join haben (SESE)
- User-Tasks brauchen eine Rolle (und die Rolle muss bekannt sein)
- Outgoing-/Incoming-Anzahl pro Knotentyp
- Erreichbarkeit
"""
from __future__ import annotations

import pytest

from app.workflow_graph import GraphError, validate_graph


KNOWN_ROLES = ["Fachbereichsleiter", "Risikomanagement", "Compliance", "Vorstand"]


def _linear_graph() -> dict:
    return {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "t1", "type": "user_task", "label": "Pruefung", "rolle": "Fachbereichsleiter"},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"from": "start", "to": "t1"},
            {"from": "t1", "to": "end"},
        ],
    }


def _parallel_graph() -> dict:
    return {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "split", "type": "parallel_split"},
            {"id": "a", "type": "user_task", "label": "Risiko", "rolle": "Risikomanagement"},
            {"id": "b", "type": "user_task", "label": "Compliance", "rolle": "Compliance"},
            {"id": "join", "type": "parallel_join"},
            {"id": "vorstand", "type": "user_task", "label": "Vorstand", "rolle": "Vorstand"},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"from": "start", "to": "split"},
            {"from": "split", "to": "a"},
            {"from": "split", "to": "b"},
            {"from": "a", "to": "join"},
            {"from": "b", "to": "join"},
            {"from": "join", "to": "vorstand"},
            {"from": "vorstand", "to": "end"},
        ],
    }


def test_valid_linear_graph():
    validate_graph(_linear_graph(), known_roles=KNOWN_ROLES)


def test_valid_parallel_graph():
    validate_graph(_parallel_graph(), known_roles=KNOWN_ROLES)


def test_no_start_node_rejected():
    g = _linear_graph()
    g["nodes"] = [n for n in g["nodes"] if n["type"] != "start"]
    g["edges"] = [e for e in g["edges"] if e["from"] != "start"]
    with pytest.raises(GraphError, match="Start"):
        validate_graph(g, known_roles=KNOWN_ROLES)


def test_two_start_nodes_rejected():
    g = _linear_graph()
    g["nodes"].append({"id": "start2", "type": "start"})
    g["edges"].append({"from": "start2", "to": "t1"})
    with pytest.raises(GraphError, match="Genau ein Start"):
        validate_graph(g, known_roles=KNOWN_ROLES)


def test_no_end_node_rejected():
    g = _linear_graph()
    g["nodes"] = [n for n in g["nodes"] if n["type"] != "end"]
    g["edges"] = [e for e in g["edges"] if e["to"] != "end"]
    with pytest.raises(GraphError):
        validate_graph(g, known_roles=KNOWN_ROLES)


def test_cycle_detected():
    g = _linear_graph()
    g["nodes"].append({"id": "t2", "type": "user_task", "label": "x", "rolle": "Risikomanagement"})
    g["edges"] = [
        {"from": "start", "to": "t1"},
        {"from": "t1", "to": "t2"},
        {"from": "t2", "to": "t1"},  # Zyklus
        {"from": "t2", "to": "end"},
    ]
    with pytest.raises(GraphError, match="Zyklus"):
        validate_graph(g, known_roles=KNOWN_ROLES)


def test_user_task_without_rolle_rejected():
    g = _linear_graph()
    g["nodes"][1].pop("rolle")
    with pytest.raises(GraphError, match="rolle"):
        validate_graph(g, known_roles=KNOWN_ROLES)


def test_user_task_with_unknown_rolle_rejected():
    g = _linear_graph()
    g["nodes"][1]["rolle"] = "Astrologe"
    with pytest.raises(GraphError, match="unbekannte Rolle"):
        validate_graph(g, known_roles=KNOWN_ROLES)


def test_user_task_with_unknown_rolle_passes_when_no_known_roles():
    """Wenn known_roles=None, wird Rolle nicht gegen ein Verzeichnis geprueft."""
    g = _linear_graph()
    g["nodes"][1]["rolle"] = "Astrologe"
    validate_graph(g, known_roles=None)


def test_unreachable_node_rejected():
    g = _linear_graph()
    g["nodes"].append({"id": "orphan", "type": "user_task", "label": "x", "rolle": "Risikomanagement"})
    with pytest.raises(GraphError, match="nicht von Start erreichbar"):
        validate_graph(g, known_roles=KNOWN_ROLES)


def test_split_with_missing_join_rejected():
    g = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "split", "type": "parallel_split"},
            {"id": "a", "type": "user_task", "label": "x", "rolle": "Risikomanagement"},
            {"id": "b", "type": "user_task", "label": "y", "rolle": "Compliance"},
            {"id": "end_a", "type": "end"},
            {"id": "end_b", "type": "end"},
        ],
        "edges": [
            {"from": "start", "to": "split"},
            {"from": "split", "to": "a"},
            {"from": "split", "to": "b"},
            {"from": "a", "to": "end_a"},
            {"from": "b", "to": "end_b"},
        ],
    }
    with pytest.raises(GraphError, match="endet ohne Join|keinen Parallel-Join"):
        validate_graph(g, known_roles=KNOWN_ROLES)


def test_direct_split_to_join_edge_rejected():
    """F-029: eine Direktkante Split->Join (ohne User-Task dazwischen) wuerde zur
    Laufzeit blockieren — der Validator muss sie ablehnen."""
    g = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "split", "type": "parallel_split"},
            {"id": "a", "type": "user_task", "label": "x", "rolle": "Risikomanagement"},
            {"id": "join", "type": "parallel_join"},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"from": "start", "to": "split"},
            {"from": "split", "to": "a"},
            {"from": "split", "to": "join"},  # Direktkante Split->Join
            {"from": "a", "to": "join"},
            {"from": "join", "to": "end"},
        ],
    }
    with pytest.raises(GraphError, match="Direktkante Split->Join|muss aber 'user_task'"):
        validate_graph(g, known_roles=KNOWN_ROLES)


def test_user_task_with_two_outgoing_edges_rejected():
    """Tasks haben genau 1 ausgehende Kante. Mehrere Branches gehen ueber einen Split."""
    g = _linear_graph()
    g["nodes"].append({"id": "t2", "type": "user_task", "label": "y", "rolle": "Compliance"})
    g["edges"].append({"from": "t1", "to": "t2"})  # t1 hat jetzt 2 outgoing
    g["edges"].append({"from": "t2", "to": "end"})
    with pytest.raises(GraphError, match="genau 1 ausgehende Kante"):
        validate_graph(g, known_roles=KNOWN_ROLES)


def test_self_edge_rejected():
    g = _linear_graph()
    g["edges"].append({"from": "t1", "to": "t1"})
    with pytest.raises(GraphError, match="Selbstkante"):
        validate_graph(g, known_roles=KNOWN_ROLES)


def test_duplicate_node_id_rejected():
    g = _linear_graph()
    g["nodes"].append({"id": "t1", "type": "user_task", "label": "dupe", "rolle": "Risikomanagement"})
    with pytest.raises(GraphError, match="Doppelte"):
        validate_graph(g, known_roles=KNOWN_ROLES)


def test_unknown_node_type_rejected():
    g = _linear_graph()
    g["nodes"][1]["type"] = "service_task"
    with pytest.raises(GraphError, match="Unbekannter Knoten-Typ"):
        validate_graph(g, known_roles=KNOWN_ROLES)


def test_edge_to_unknown_node_rejected():
    g = _linear_graph()
    g["edges"].append({"from": "t1", "to": "phantom"})
    with pytest.raises(GraphError, match="unbekannte Knoten"):
        validate_graph(g, known_roles=KNOWN_ROLES)
