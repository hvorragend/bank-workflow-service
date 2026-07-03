"""Regressionstest fuer Audit F-004: Approvals sind an ihren Durchlauf gebunden.

Szenario im Vorstandsbeschluss-Graph (parallele Branches rechtskonformitaet +
risikoanalyse zwischen Split und Join): Wird ein Branch in Durchlauf 1 genehmigt
und der Antrag danach zurueckgewiesen, darf diese alte Genehmigung nach der
Wiedereinreichung (Durchlauf 2) NICHT mehr zum Feuern des Joins beitragen — sonst
wuerde eine Kontrollstufe uebersprungen.
"""
from __future__ import annotations

from .test_workflow_parallel import _create_vb_instance, approve_one


def _decide(client, auth, iid, node_id, entscheidung):
    return client.post(
        f"/instances/{iid}/decide",
        json={"node_id": node_id, "entscheidung": entscheidung, "kommentar": "x"},
        headers=auth,
    )


def test_stale_approval_does_not_prematurely_fire_join(client, admin_auth):
    iid = _create_vb_instance(client, admin_auth)
    client.post(f"/instances/{iid}/submit", headers=admin_auth)  # lauf 1

    # Durchlauf 1: vorbereitung + rechtskonformitaet genehmigen ...
    approve_one(client, admin_auth, iid)  # vorbereitung -> beide Branches aktiv
    assert _decide(client, admin_auth, iid, "rechtskonformitaet", "approved").status_code == 200

    # ... dann den anderen Branch zurueckweisen -> zurueck auf entwurf.
    assert _decide(client, admin_auth, iid, "risikoanalyse", "returned").status_code == 200
    state = client.get(f"/instances/{iid}", headers=admin_auth).json()
    assert state["status"] == "entwurf"

    # Durchlauf 2: erneut einreichen, vorbereitung genehmigen -> beide Branches aktiv.
    client.post(f"/instances/{iid}/submit", headers=admin_auth)  # lauf 2
    approve_one(client, admin_auth, iid)
    state = client.get(f"/instances/{iid}", headers=admin_auth).json()
    assert {a["node_id"] for a in state["active_stages"]} == {"rechtskonformitaet", "risikoanalyse"}

    # NUR risikoanalyse in Durchlauf 2 genehmigen. Der Join darf NICHT feuern,
    # weil rechtskonformitaet in diesem Durchlauf noch offen ist (die Genehmigung
    # aus Durchlauf 1 zaehlt nicht mehr).
    assert _decide(client, admin_auth, iid, "risikoanalyse", "approved").status_code == 200
    state = client.get(f"/instances/{iid}", headers=admin_auth).json()
    actives = {a["node_id"] for a in state["active_stages"]}
    assert actives == {"rechtskonformitaet"}, (
        "Join darf mit veralteter Approval aus Durchlauf 1 nicht vorzeitig feuern."
    )

    # Erst nach erneuter Genehmigung von rechtskonformitaet feuert der Join.
    assert _decide(client, admin_auth, iid, "rechtskonformitaet", "approved").status_code == 200
    state = client.get(f"/instances/{iid}", headers=admin_auth).json()
    assert {a["node_id"] for a in state["active_stages"]} == {"vorstand"}
