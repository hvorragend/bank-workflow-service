"""End-to-End-Tests fuer parallele Branches im Workflow-DAG.

Testet die Engine via API gegen den geseedeten Vorstandsbeschluss-Graph,
der nach Vorbereitung in zwei parallele Branches (Compliance + Risiko)
aufteilt und nach dem Join wieder zum Vorstand-Task zusammengefuehrt wird.
"""
from __future__ import annotations

import pytest

from .conftest import approve_all_active, approve_one, auth_header, login_as, reject_one

VORSTAND_DATEN = {
    "fachbereich_kopf": {
        "entscheidungstraeger": "Vorstand",
        "verfasser": "Test",
        "betreff": "Test-Beschluss fuer Parallel-Branches",
    },
    "antrag": {
        "antragstext": (
            "Reiner Testfall fuer die Pruefung paralleler Branches. Wir wollen "
            "sehen, dass nach der Vorbereitung Compliance und Risikomanagement "
            "gleichzeitig aktiv werden und der Join erst dann den Vorstand "
            "aktiviert, wenn beide Branches genehmigt haben."
        ),
    },
    "sachverhalt": {
        "ausgangssituation": "Reiner Testfall, kein realer Ist-Zustand.",
        "sachverhalt_beschlussantrag": (
            "Ein Testfall, der die Korrektheit des Join-Wartens nachweist und "
            "verhindert, dass die Engine versehentlich nach dem ersten Branch "
            "weiter zum Vorstand schaltet."
        ),
        "bewertung_veraenderungen": "Keine — reiner Test.",
        "fazit_empfehlung": "Test laeuft erfolgreich durch.",
    },
    "kommunikation": {"erforderlich": False},
    "pflichtpruefungen": {
        "npp_neue_produkte_maerkte": False,
        "at_8_2_bewertung_erforderlich": False,
        "at_9_auslagerung": False,
        "at_9_fremdbezug_dienstleistung": False,
        "at_9_fremdbezug_it_dienstleistung": False,
        "neues_it_system": False,
        "it_projekt_richtlinie": False,
    },
}


def _create_vb_instance(client, headers) -> str:
    defs = client.get("/definitions", headers=headers).json()
    vb = next(d for d in defs if d["typ"] == "Vorstandsbeschluss" and d["status"] == "active")
    r = client.post("/instances", json={"form_definition_id": vb["id"], "daten": VORSTAND_DATEN}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_submit_activates_first_user_task(client, admin_auth):
    iid = _create_vb_instance(client, admin_auth)
    r = client.post(f"/instances/{iid}/submit", headers=admin_auth)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "in_pruefung"
    actives = {a["node_id"] for a in body["active_stages"]}
    assert actives == {"vorbereitung"}


def test_split_activates_both_branches(client, admin_auth):
    iid = _create_vb_instance(client, admin_auth)
    client.post(f"/instances/{iid}/submit", headers=admin_auth)
    r = approve_one(client, admin_auth, iid)
    assert r.status_code == 200
    state = client.get(f"/instances/{iid}", headers=admin_auth).json()
    actives = {a["node_id"] for a in state["active_stages"]}
    # Nach Approve von Vorbereitung muessen beide Branches gleichzeitig aktiv sein.
    assert actives == {"rechtskonformitaet", "risikoanalyse"}


def test_join_waits_for_all_branches(client, admin_auth):
    iid = _create_vb_instance(client, admin_auth)
    client.post(f"/instances/{iid}/submit", headers=admin_auth)
    approve_one(client, admin_auth, iid)  # vorbereitung -> beide Branches aktiv

    # Nur einen Branch genehmigen -> Vorstand darf NOCH NICHT aktiv sein.
    r = client.post(
        f"/instances/{iid}/decide",
        json={"node_id": "rechtskonformitaet", "entscheidung": "approved"},
        headers=admin_auth,
    )
    assert r.status_code == 200
    state = client.get(f"/instances/{iid}", headers=admin_auth).json()
    actives = {a["node_id"] for a in state["active_stages"]}
    assert actives == {"risikoanalyse"}, "Vorstand darf vor Join nicht aktiv werden."

    # Zweiten Branch genehmigen -> jetzt feuert der Join, Vorstand wird aktiv.
    r = client.post(
        f"/instances/{iid}/decide",
        json={"node_id": "risikoanalyse", "entscheidung": "approved"},
        headers=admin_auth,
    )
    assert r.status_code == 200
    state = client.get(f"/instances/{iid}", headers=admin_auth).json()
    actives = {a["node_id"] for a in state["active_stages"]}
    assert actives == {"vorstand"}


@pytest.mark.fachlich(
    anforderung="MaRisk AT 4.3.1 — parallele Pruefungen mit Synchronisationspunkt",
    soll="Workflow-Engine wartet am Parallel-Join, bis alle Branches genehmigt haben, bevor der Folge-Task aktiviert wird.",
)
def test_full_parallel_chain_to_genehmigt(client, admin_auth):
    iid = _create_vb_instance(client, admin_auth)
    client.post(f"/instances/{iid}/submit", headers=admin_auth)

    # vorbereitung
    approve_one(client, admin_auth, iid)
    # parallele Branches gemeinsam abarbeiten
    approve_all_active(client, admin_auth, iid)
    # vorstand
    approve_one(client, admin_auth, iid)
    # protokoll
    approve_one(client, admin_auth, iid)

    final = client.get(f"/instances/{iid}", headers=admin_auth).json()
    assert final["status"] == "genehmigt"
    assert final["active_stages"] == []
    # 5 Approvals: vorbereitung, compliance, risiko, vorstand, protokoll
    assert len(final["approvals"]) == 5


def test_reject_in_one_branch_rejects_whole_instance(client, admin_auth):
    """Ablehnung in einem parallelen Branch verwirft die gesamte Instanz —
    keine Deadlocks am Join, klare Semantik fuer Antragsteller."""
    iid = _create_vb_instance(client, admin_auth)
    client.post(f"/instances/{iid}/submit", headers=admin_auth)
    approve_one(client, admin_auth, iid)  # vorbereitung -> beide Branches aktiv

    state = client.get(f"/instances/{iid}", headers=admin_auth).json()
    assert len(state["active_stages"]) == 2

    # Compliance lehnt ab — der gesamte Antrag muss abgelehnt sein.
    r = client.post(
        f"/instances/{iid}/decide",
        json={"node_id": "rechtskonformitaet", "entscheidung": "rejected", "kommentar": "passt nicht"},
        headers=admin_auth,
    )
    assert r.status_code == 200
    final = client.get(f"/instances/{iid}", headers=admin_auth).json()
    assert final["status"] == "abgelehnt"
    assert final["active_stages"] == []  # auch Risiko-Branch wurde geleert


def test_decide_with_wrong_node_id_returns_409(client, admin_auth):
    """Wenn der genannte Knoten nicht aktiv ist, gibt es 409."""
    iid = _create_vb_instance(client, admin_auth)
    client.post(f"/instances/{iid}/submit", headers=admin_auth)
    r = client.post(
        f"/instances/{iid}/decide",
        json={"node_id": "vorstand", "entscheidung": "approved"},  # vorstand ist noch nicht aktiv
        headers=admin_auth,
    )
    assert r.status_code == 409
    assert "nicht aktiv" in r.json()["detail"]


def test_returned_resets_to_entwurf_clears_active(client, admin_auth):
    iid = _create_vb_instance(client, admin_auth)
    client.post(f"/instances/{iid}/submit", headers=admin_auth)
    approve_one(client, admin_auth, iid)  # split aktiv

    r = client.post(
        f"/instances/{iid}/decide",
        json={"node_id": "rechtskonformitaet", "entscheidung": "returned",
              "kommentar": "Bitte nachschaerfen."},
        headers=admin_auth,
    )
    assert r.status_code == 200
    state = client.get(f"/instances/{iid}", headers=admin_auth).json()
    assert state["status"] == "entwurf"
    assert state["active_stages"] == []
