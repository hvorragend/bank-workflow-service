# Beispiel-Prozessdateien

Beispiele zum Hochladen ueber `POST /admin/definitions/upload-bpmn` oder zum Importieren in einen externen Editor (Camunda Modeler, [demo.bpmn.io](https://demo.bpmn.io)).

## Dateien

- **`sample_linear.bpmn`** — Klassischer linearer 3-stufiger Workflow (Fachbereich → Risiko → Vorstand). SLA pro Task ueber `<bpmn:documentation>sla: N</bpmn:documentation>`.
- **`sample_parallel.bpmn`** — Vorstandsbeschluss mit parallelem Branch: nach der Vorbereitung pruefen Compliance und Risiko **gleichzeitig**, der Parallel-Join wartet auf beide, dann folgt der Vorstand und das Protokoll.

## Akzeptiertes BPMN-Subset

Der Server-Importer akzeptiert nur:

| BPMN-Element | Bedeutung |
|---|---|
| `bpmn:startEvent` | Genau einer pro Prozess |
| `bpmn:endEvent` | Mindestens einer |
| `bpmn:userTask` | Wartet auf Entscheidung; Rolle ist Pflicht |
| `bpmn:parallelGateway` | Wird automatisch als Split (>1 outgoing) oder Join (>1 incoming) klassifiziert |
| `bpmn:sequenceFlow` | Verbindet die Knoten |

Alles andere (`serviceTask`, `exclusiveGateway`, `boundaryEvent`, `subProcess` …) wird mit 422 abgelehnt.

## Rolle im UserTask

Reihenfolge der Quellen (erste gefundene gewinnt):

1. `camunda:assignee="<RolleName>"`
2. `<bpmn:potentialOwner><bpmn:resourceAssignmentExpression><bpmn:formalExpression>RolleName</...></...></...>`
3. `<bpmn:documentation>rolle: RolleName</bpmn:documentation>`

Die Rolle muss in der zentralen Rollenliste (`config/users.json` + LDAP-Mapping, abrufbar via `GET /admin/roles`) bekannt sein, sonst wird der Upload verweigert.
