"""BPMN-XML-Subset-Parser fuer den Workflow-Upload-Fallback.

Wir akzeptieren nur ein winziges Subset (Start-/End-Event, User-Task,
Parallel-Gateway, Sequence-Flow). Alles andere wird laut abgelehnt — die
Engine kann nichts anderes ausfuehren.

Sicherheit: Wir parsen mit defusedxml (verhindert XXE / Billion-Laughs);
die Datei kommt aus User-Upload.
"""
from __future__ import annotations

from typing import Any

from defusedxml.ElementTree import fromstring as defused_fromstring

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
CAMUNDA_NS = "http://camunda.org/schema/1.0/bpmn"

ALLOWED_TAGS = {
    f"{{{BPMN_NS}}}definitions",
    f"{{{BPMN_NS}}}process",
    f"{{{BPMN_NS}}}startEvent",
    f"{{{BPMN_NS}}}endEvent",
    f"{{{BPMN_NS}}}userTask",
    f"{{{BPMN_NS}}}parallelGateway",
    f"{{{BPMN_NS}}}sequenceFlow",
    f"{{{BPMN_NS}}}documentation",
    f"{{{BPMN_NS}}}potentialOwner",
    f"{{{BPMN_NS}}}resourceAssignmentExpression",
    f"{{{BPMN_NS}}}formalExpression",
    f"{{{BPMN_NS}}}extensionElements",
    f"{{{BPMN_NS}}}incoming",
    f"{{{BPMN_NS}}}outgoing",
}

# Tags, die auftauchen koennen, aber keine inhaltliche Bedeutung haben — wir
# uebergehen sie still. (BPMN-DI = Diagram Interchange, reines Layout.)
DI_NAMESPACES = (
    "http://www.omg.org/spec/BPMN/20100524/DI",
    "http://www.omg.org/spec/DD/20100524/DI",
    "http://www.omg.org/spec/DD/20100524/DC",
)


class BpmnImportError(ValueError):
    """Strukturfehler beim BPMN-Import."""


def parse_bpmn_to_graph(xml_bytes: bytes) -> dict[str, Any]:
    """Liest BPMN-XML und mappt das akzeptierte Subset auf den Workflow-DAG.

    Wirft `BpmnImportError`, wenn unbekannte Elemente auftauchen oder
    Strukturen unvollstaendig sind. Die strukturelle Korrektheit (Zyklen,
    SESE-Splits etc.) wird vom Aufrufer ueber `workflow_graph.validate_graph`
    nachgelagert geprueft.
    """
    try:
        root = defused_fromstring(xml_bytes)
    except Exception as e:  # defusedxml wirft ParseError o.ae.
        raise BpmnImportError(f"BPMN-XML kann nicht geparst werden: {e}") from e

    if root.tag != f"{{{BPMN_NS}}}definitions":
        raise BpmnImportError(
            f"Wurzelelement muss bpmn:definitions sein (gefunden: {root.tag})."
        )

    process = None
    for child in root:
        if child.tag == f"{{{BPMN_NS}}}process":
            if process is not None:
                raise BpmnImportError("Mehrere bpmn:process-Elemente — nur eines unterstuetzt.")
            process = child
        elif _is_di(child.tag):
            continue
        else:
            raise BpmnImportError(f"Unerwartetes Element auf Definitions-Ebene: {_clean_tag(child.tag)}")

    if process is None:
        raise BpmnImportError("Kein bpmn:process gefunden.")

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    gateway_outgoing: dict[str, int] = {}
    gateway_incoming: dict[str, int] = {}

    # Erster Durchlauf: Sequence-Flows zaehlen (fuer Gateway-Klassifikation).
    for el in process:
        if el.tag == f"{{{BPMN_NS}}}sequenceFlow":
            src = el.get("sourceRef")
            tgt = el.get("targetRef")
            if not src or not tgt:
                raise BpmnImportError(f"sequenceFlow ohne sourceRef/targetRef: id={el.get('id')!r}")
            gateway_outgoing[src] = gateway_outgoing.get(src, 0) + 1
            gateway_incoming[tgt] = gateway_incoming.get(tgt, 0) + 1
            edges.append({"from": src, "to": tgt})

    # Zweiter Durchlauf: Knoten.
    for el in process:
        tag = el.tag
        if _is_di(tag):
            continue
        if tag == f"{{{BPMN_NS}}}sequenceFlow":
            continue  # bereits behandelt
        if tag == f"{{{BPMN_NS}}}startEvent":
            nodes.append({"id": _require_id(el), "type": "start"})
        elif tag == f"{{{BPMN_NS}}}endEvent":
            nodes.append({"id": _require_id(el), "type": "end"})
        elif tag == f"{{{BPMN_NS}}}userTask":
            nid = _require_id(el)
            rolle = _extract_rolle(el)
            if not rolle:
                raise BpmnImportError(
                    f"userTask {nid!r} ohne Rolle: bitte camunda:assignee oder "
                    f"potentialOwner/formalExpression setzen, oder bpmn:documentation "
                    f"mit 'rolle: <Name>' versehen."
                )
            label = el.get("name") or nid
            node: dict[str, Any] = {"id": nid, "type": "user_task", "label": label, "rolle": rolle}
            sla = _extract_sla(el)
            if sla:
                node["sla_days"] = sla
            nodes.append(node)
        elif tag == f"{{{BPMN_NS}}}parallelGateway":
            nid = _require_id(el)
            out = gateway_outgoing.get(nid, 0)
            inc = gateway_incoming.get(nid, 0)
            if out > 1 and inc <= 1:
                nodes.append({"id": nid, "type": "parallel_split"})
            elif inc > 1 and out <= 1:
                nodes.append({"id": nid, "type": "parallel_join"})
            else:
                raise BpmnImportError(
                    f"parallelGateway {nid!r} laesst sich nicht eindeutig als Split "
                    f"oder Join klassifizieren (incoming={inc}, outgoing={out})."
                )
        elif tag in ALLOWED_TAGS:
            # Hilfsknoten innerhalb von Tasks — kein eigener DAG-Knoten.
            continue
        else:
            raise BpmnImportError(f"Unerlaubtes BPMN-Element: {_clean_tag(tag)}")

    if not nodes:
        raise BpmnImportError("BPMN enthaelt keine Knoten.")

    return {"nodes": nodes, "edges": edges}


# ---------- Helfer ----------

def _require_id(el) -> str:
    nid = el.get("id")
    if not nid:
        raise BpmnImportError(f"Element ohne id: {_clean_tag(el.tag)}")
    return nid


def _is_di(tag: str) -> bool:
    return any(tag.startswith(f"{{{ns}}}") for ns in DI_NAMESPACES)


def _clean_tag(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _extract_rolle(user_task) -> str:
    """Reihenfolge:
    1. camunda:assignee-Attribut
    2. potentialOwner/resourceAssignmentExpression/formalExpression-Text
    3. bpmn:documentation-Text mit Prefix 'rolle:'
    """
    # 1) camunda:assignee
    val = user_task.get(f"{{{CAMUNDA_NS}}}assignee")
    if val:
        return val.strip()
    # 2) potentialOwner -> formalExpression
    for po in user_task.findall(f"{{{BPMN_NS}}}potentialOwner"):
        for rae in po.findall(f"{{{BPMN_NS}}}resourceAssignmentExpression"):
            for fe in rae.findall(f"{{{BPMN_NS}}}formalExpression"):
                if fe.text and fe.text.strip():
                    return fe.text.strip()
    # 3) documentation
    for doc in user_task.findall(f"{{{BPMN_NS}}}documentation"):
        text = (doc.text or "").strip()
        if text.lower().startswith("rolle:"):
            return text.split(":", 1)[1].strip()
    return ""


def _extract_sla(user_task) -> int | None:
    """Sucht in <bpmn:documentation> nach einem 'sla:<n>'-Eintrag."""
    for doc in user_task.findall(f"{{{BPMN_NS}}}documentation"):
        text = (doc.text or "").strip().lower()
        if text.startswith("sla:"):
            try:
                v = int(text.split(":", 1)[1].strip())
                if v > 0:
                    return v
            except ValueError:
                return None
    return None
