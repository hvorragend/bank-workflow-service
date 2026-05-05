"""Workflow-DAG: Datenstruktur, Validator und Hilfsfunktionen.

Eine Workflow-Definition ist ein gerichteter azyklischer Graph aus Knoten
(Start, User-Task, Parallel-Split, Parallel-Join, End) und Kanten. Die hier
gesammelten Funktionen sind reine Funktionen ohne DB-Abhaengigkeit — Aufrufer
sind sowohl der Upload-Endpoint (Validierung vor Persistierung) als auch die
Workflow-Engine (Naechster-Knoten-Bestimmung in workflow.decide).
"""
from __future__ import annotations

from collections import deque
from typing import Any, Iterable

NODE_TYPES = {"start", "end", "user_task", "parallel_split", "parallel_join"}


class GraphError(ValueError):
    """Strukturfehler im Workflow-Graph."""


# ---------- Indizes ----------

def nodes_by_id(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n["id"]: n for n in graph.get("nodes", [])}


def outgoing(graph: dict[str, Any], node_id: str) -> list[str]:
    return [e["to"] for e in graph.get("edges", []) if e["from"] == node_id]


def incoming(graph: dict[str, Any], node_id: str) -> list[str]:
    return [e["from"] for e in graph.get("edges", []) if e["to"] == node_id]


def find_start(graph: dict[str, Any]) -> str:
    for n in graph.get("nodes", []):
        if n.get("type") == "start":
            return n["id"]
    raise GraphError("Kein Start-Knoten im Graph.")


# ---------- Validator ----------

def validate_graph(graph: dict[str, Any], known_roles: Iterable[str] | None = None) -> None:
    """Validiert einen Workflow-Graph und wirft GraphError mit klarer Meldung,
    wenn etwas nicht passt.

    `known_roles` ist optional. Wenn None, wird die Rollen-Existenz nicht geprueft
    (sinnvoll fuer reine Strukturpruefungen ausserhalb des Server-Kontexts).
    """
    if not isinstance(graph, dict):
        raise GraphError("Graph muss ein Objekt mit 'nodes' und 'edges' sein.")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise GraphError("'nodes' und 'edges' muessen Listen sein.")
    if not nodes:
        raise GraphError("Graph hat keine Knoten.")

    # 1) Knoten-Grundstruktur + IDs eindeutig.
    seen_ids: set[str] = set()
    for n in nodes:
        if not isinstance(n, dict):
            raise GraphError("Knoten muessen Objekte sein.")
        nid = n.get("id")
        ntype = n.get("type")
        if not isinstance(nid, str) or not nid:
            raise GraphError(f"Knoten ohne 'id': {n!r}")
        if nid in seen_ids:
            raise GraphError(f"Doppelte Knoten-ID: {nid!r}")
        seen_ids.add(nid)
        if ntype not in NODE_TYPES:
            raise GraphError(f"Unbekannter Knoten-Typ {ntype!r} bei Knoten {nid!r}.")

    by_id = nodes_by_id(graph)

    # 2) Kanten verweisen auf existierende Knoten.
    for e in edges:
        if not isinstance(e, dict) or "from" not in e or "to" not in e:
            raise GraphError(f"Kante ohne 'from'/'to': {e!r}")
        if e["from"] not in by_id or e["to"] not in by_id:
            raise GraphError(f"Kante referenziert unbekannte Knoten: {e!r}")
        if e["from"] == e["to"]:
            raise GraphError(f"Selbstkante nicht erlaubt: {e!r}")

    # 3) Genau ein Start, mindestens ein End.
    starts = [n for n in nodes if n["type"] == "start"]
    if len(starts) != 1:
        raise GraphError(f"Genau ein Start-Knoten erforderlich (gefunden: {len(starts)}).")
    if not any(n["type"] == "end" for n in nodes):
        raise GraphError("Mindestens ein End-Knoten erforderlich.")

    # 4a) Zyklus + Erreichbarkeit ZUERST — bei zyklischen oder unzusammen-
    # haengenden Graphen sind Folge-Pruefungen (Outgoing-Counts, SESE-Regions)
    # nicht mehr zuverlaessig aussagekraeftig.
    start_id = starts[0]["id"]
    cycle = _find_cycle(graph, start_id, by_id)
    if cycle:
        raise GraphError(f"Zyklus erkannt: {' -> '.join(cycle)}.")

    reachable = _bfs_reachable(graph, start_id)
    missing = seen_ids - reachable
    if missing:
        raise GraphError(f"Knoten nicht von Start erreichbar: {sorted(missing)}.")

    # 4b) Outgoing-/Incoming-Anzahl pro Knotentyp.
    out_count = {nid: 0 for nid in by_id}
    in_count = {nid: 0 for nid in by_id}
    for e in edges:
        out_count[e["from"]] += 1
        in_count[e["to"]] += 1

    for n in nodes:
        nid, t = n["id"], n["type"]
        oc, ic = out_count[nid], in_count[nid]
        if t == "start":
            if oc != 1:
                raise GraphError(f"Start {nid!r} muss genau 1 ausgehende Kante haben (hat {oc}).")
            if ic != 0:
                raise GraphError(f"Start {nid!r} darf keine eingehende Kante haben.")
        elif t == "end":
            if oc != 0:
                raise GraphError(f"End {nid!r} darf keine ausgehende Kante haben.")
            if ic < 1:
                raise GraphError(f"End {nid!r} muss mindestens eine eingehende Kante haben.")
        elif t == "user_task":
            if oc != 1:
                raise GraphError(f"User-Task {nid!r} muss genau 1 ausgehende Kante haben (hat {oc}).")
            if ic < 1:
                raise GraphError(f"User-Task {nid!r} muss mindestens eine eingehende Kante haben.")
            rolle = n.get("rolle")
            if not isinstance(rolle, str) or not rolle.strip():
                raise GraphError(f"User-Task {nid!r} braucht ein nicht-leeres Feld 'rolle'.")
            if known_roles is not None and rolle not in set(known_roles):
                raise GraphError(
                    f"User-Task {nid!r}: unbekannte Rolle {rolle!r}. "
                    f"Bekannte Rollen: {sorted(set(known_roles))}."
                )
            sla = n.get("sla_days")
            if sla is not None and not (isinstance(sla, int) and sla > 0):
                raise GraphError(f"User-Task {nid!r}: 'sla_days' muss positive Ganzzahl sein.")
        elif t == "parallel_split":
            if oc < 2:
                raise GraphError(f"Parallel-Split {nid!r} muss mindestens 2 ausgehende Kanten haben.")
            if ic < 1:
                raise GraphError(f"Parallel-Split {nid!r} muss eine eingehende Kante haben.")
        elif t == "parallel_join":
            if oc != 1:
                raise GraphError(f"Parallel-Join {nid!r} muss genau 1 ausgehende Kante haben.")
            if ic < 2:
                raise GraphError(f"Parallel-Join {nid!r} muss mindestens 2 eingehende Kanten haben.")


    # 6) Jedes Blatt (kein outgoing) ist End.
    for nid in seen_ids:
        if out_count[nid] == 0 and by_id[nid]["type"] != "end":
            raise GraphError(f"Knoten {nid!r} hat keinen Nachfolger, ist aber kein End-Knoten.")

    # 7) SESE-Bedingung fuer Parallel-Splits: jeder Split hat genau einen
    # passenden Join, und alle Branches enden dort.
    for n in nodes:
        if n["type"] == "parallel_split":
            _validate_parallel_region(graph, n["id"], by_id, out_count, in_count)


def _bfs_reachable(graph: dict[str, Any], start_id: str) -> set[str]:
    seen = {start_id}
    q = deque([start_id])
    while q:
        cur = q.popleft()
        for nxt in outgoing(graph, cur):
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    return seen


def _find_cycle(graph: dict[str, Any], start_id: str, by_id: dict[str, dict]) -> list[str] | None:
    """DFS mit Coloring. Gibt einen Zyklus als Knotenpfad zurueck, falls vorhanden."""
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {nid: WHITE for nid in by_id}
    parent: dict[str, str | None] = {nid: None for nid in by_id}

    def dfs(u: str) -> list[str] | None:
        color[u] = GREY
        for v in outgoing(graph, u):
            if color[v] == WHITE:
                parent[v] = u
                cyc = dfs(v)
                if cyc:
                    return cyc
            elif color[v] == GREY:
                # Zyklus: rekonstruiere Pfad v -> ... -> u -> v
                path = [v, u]
                cur = parent[u]
                while cur is not None and cur != v:
                    path.append(cur)
                    cur = parent[cur]
                if cur == v:
                    path.append(v)
                path.reverse()
                return path
        color[u] = BLACK
        return None

    return dfs(start_id)


def _validate_parallel_region(
    graph: dict[str, Any],
    split_id: str,
    by_id: dict[str, dict],
    out_count: dict[str, int],
    in_count: dict[str, int],
) -> None:
    """Stellt sicher, dass der Split genau einen passenden Join hat. Jeder vom
    Split startende Branch muss diesen Join treffen, ohne dazwischenliegende
    End-Knoten oder Re-Joins ueber andere Splits."""
    branch_starts = outgoing(graph, split_id)
    join_id: str | None = None
    branch_visited: list[set[str]] = []

    for b_start in branch_starts:
        seen_branch: set[str] = set()
        q = deque([b_start])
        local_join: str | None = None
        while q:
            cur = q.popleft()
            if cur in seen_branch:
                continue
            seen_branch.add(cur)
            t = by_id[cur]["type"]
            if t == "end":
                raise GraphError(
                    f"Branch nach Parallel-Split {split_id!r} endet ohne Join "
                    f"(Knoten {cur!r}). Branches muessen vor dem End wieder zusammengefuehrt werden."
                )
            if t == "parallel_join":
                local_join = cur
                continue  # Pfad endet hier — nicht weiter expandieren
            for nxt in outgoing(graph, cur):
                q.append(nxt)
        if local_join is None:
            raise GraphError(
                f"Branch ab Knoten {b_start!r} (Parallel-Split {split_id!r}) erreicht keinen Parallel-Join."
            )
        if join_id is None:
            join_id = local_join
        elif join_id != local_join:
            raise GraphError(
                f"Parallel-Split {split_id!r} hat mehrere unterschiedliche Joins "
                f"({join_id!r} vs. {local_join!r}). Genau ein Join je Split erforderlich."
            )
        branch_visited.append(seen_branch)

    if join_id is None:
        raise GraphError(f"Parallel-Split {split_id!r} hat keinen passenden Parallel-Join.")
    # Anzahl eingehender Kanten am Join muss zur Anzahl Branches passen.
    if in_count[join_id] != len(branch_starts):
        raise GraphError(
            f"Parallel-Join {join_id!r} hat {in_count[join_id]} eingehende Kanten, "
            f"erwartet {len(branch_starts)} (= Anzahl Branches des zugehoerigen Splits)."
        )


# ---------- Hilfen fuer die Engine ----------

def initial_active_tasks(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Bestimmt die initial aktivierten User-Tasks beim Submit eines Antrags.

    Folgt vom Start aus, expandiert Splits, sammelt User-Tasks. Joins/Ends
    werden im Submit nicht erreicht (Joins brauchen ankommende Approvals,
    End nur wenn alle Branches abgeschlossen sind).
    """
    return [by_id_node(graph, nid) for nid in _expand_to_tasks(graph, find_start(graph))]


def successors_after_approval(graph: dict[str, Any], node_id: str) -> list[dict[str, Any]]:
    """Welche User-Tasks werden aktiviert, nachdem `node_id` (ein User-Task)
    genehmigt wurde? Folgt der ausgehenden Kante, expandiert Splits/Joins,
    sammelt User-Tasks.

    WICHTIG: Joins werden hier NICHT automatisch gefeuert — die Engine prueft
    arrival-counting separat (siehe join_ready). Diese Funktion betrachtet
    nur die "lokale" Fortschaltung von einem Task aus.
    """
    out = outgoing(graph, node_id)
    if not out:
        return []
    return [by_id_node(graph, nid) for nid in _expand_to_tasks(graph, out[0], stop_at_join=True)]


def successors_after_join(graph: dict[str, Any], join_id: str) -> list[dict[str, Any]]:
    """Wenn ein Parallel-Join gefeuert hat: welche User-Tasks werden danach aktiv?"""
    out = outgoing(graph, join_id)
    if not out:
        return []
    return [by_id_node(graph, nid) for nid in _expand_to_tasks(graph, out[0])]


def by_id_node(graph: dict[str, Any], node_id: str) -> dict[str, Any]:
    return nodes_by_id(graph)[node_id]


def _expand_to_tasks(
    graph: dict[str, Any], start_id: str, *, stop_at_join: bool = False
) -> list[str]:
    """Geht vom Start-Knoten aus vorwaerts, bis User-Tasks oder End/Join
    erreicht werden. Splits werden expandiert. Mehrfach-Besuche werden
    entdupliziert (relevant, falls zwei Branches kurz vor dem Join wieder
    auf denselben Knoten treffen — kommt im aktuellen Modell nicht vor,
    aber Defense-in-Depth)."""
    by_id = nodes_by_id(graph)
    out: list[str] = []
    seen: set[str] = set()
    q = deque([start_id])
    while q:
        cur = q.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        t = by_id[cur]["type"]
        if t == "user_task":
            out.append(cur)
        elif t == "parallel_split":
            for nxt in outgoing(graph, cur):
                q.append(nxt)
        elif t == "parallel_join":
            if stop_at_join:
                # Engine ruft `successors_after_join` separat auf.
                continue
            # Falls nicht stop_at_join: expandiere weiter (relevant fuer initial_active_tasks
            # nur, wenn ein Join direkt nach Start steht — pathologisch, aber Robustheit).
            for nxt in outgoing(graph, cur):
                q.append(nxt)
        elif t == "end":
            continue
        elif t == "start":
            for nxt in outgoing(graph, cur):
                q.append(nxt)
    return out


def join_ready(
    graph: dict[str, Any],
    join_id: str,
    arrived_node_ids: set[str],
) -> bool:
    """Hat der Join alle eingehenden Branches gesehen?

    `arrived_node_ids` ist die Menge der Knoten, fuer die bereits eine
    `Approval` (entscheidung='approved') vorliegt. Der Join ist ready, wenn
    fuer jede eingehende Kante mindestens einer der vorgelagerten Knoten
    angekommen ist.

    Vereinfachte Heuristik: incoming(join) sind die unmittelbar vorgelagerten
    User-Tasks (per Validator-Bedingung — Joins haben keine direkt vorgelagerten
    Splits/Joins ohne Tasks dazwischen). Damit reicht der direkte Set-Vergleich.
    """
    pre = set(incoming(graph, join_id))
    return pre.issubset(arrived_node_ids)


def reaches_end_only(graph: dict[str, Any], node_id: str) -> bool:
    """True, wenn alle vom Knoten aus erreichbaren User-Tasks bereits hinter
    uns liegen — also der naechste 'echte' Knoten ein End ist. Wird genutzt,
    um nach der letzten Genehmigung den Status auf 'genehmigt' zu setzen."""
    out = outgoing(graph, node_id)
    if not out:
        return False
    by_id = nodes_by_id(graph)
    cur = out[0]
    # Springe ueber Joins (die direkt nach dem letzten Task feuern duerfen).
    while by_id[cur]["type"] == "parallel_join":
        nxt = outgoing(graph, cur)
        if not nxt:
            return False
        cur = nxt[0]
    return by_id[cur]["type"] == "end"
