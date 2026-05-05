# IDV Workflow Service — Skelett

Versionierter Workflow- und Genehmigungs-Service für bankfachliche Anträge
(AT 8.2-Analysen, IKT-Risikogenehmigungen, Vorstandsbeschlüsse, Projektanträge,
Vertragsunterzeichnungen …) als FastAPI/SQLAlchemy/Pydantic-Skelett.

## Kernidee

Jeder ausgefüllte Antrag (`FormInstance`) wird **hart an eine konkrete Schema-Version**
(`FormDefinition.id`) gebunden. Wird die Maske im Folgejahr um neue Felder ergänzt,
- erscheint die neue Version nur bei Neuanträgen,
- bleiben Altanträge mit ihrem ursprünglichen Schema renderbar,
- bleibt jederzeit nachweisbar, welcher Maskenstand zur Beurteilung herangezogen wurde
  (relevant für MaRisk AT 7.2 / DORA-Audits).

## Architektur

```
   ┌─────────────────┐        ┌─────────────────┐
   │ FormDefinition  │◄───────│  FormInstance   │
   │ (versioniert)   │   FK   │ (gepinnt!)      │
   └─────────────────┘        └────────┬────────┘
   - typ                                │
   - version (SemVer)                   │ 1:n
   - json_schema                        ▼
   - ui_schema             ┌─────────────────────┐
   - workflow_stages       │     Approval        │
   - status: draft|        │ (immutable history) │
     active|retired        │ stage, rolle,       │
                           │ entscheidung,       │
                           │ zeitstempel         │
                           └─────────────────────┘
```

- **`FormDefinition`**: versionierte Maskendefinition. Status `draft → active → retired`. Aktive Versionen sind unveränderlich (jede Änderung = neue Version).
- **`FormInstance`**: ein konkreter Antrag, mit Fremdschlüssel auf eine konkrete `FormDefinition.id` (= konkrete Version!). Validierung der `daten` erfolgt gegen genau diese Version.
- **`Approval`**: revisionssicherer Audit-Eintrag pro Stage-Entscheidung.
- **`workflow_stages`**: Liste von Genehmigungsstufen, pro `FormDefinition`-Version definiert. Erlaubt unterschiedliche Genehmigungswege je Maskentyp (und zwischen Versionen desselben Typs).

## Quickstart

```bash
cd idv-workflow
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Beim ersten Start werden Tabellen angelegt (SQLite, `idv_workflow.db`) und zwei
Beispiel-Versionen der AT 8.2-Maske geseeded:
- v1.0.0 (retired) — drei Wesentlichkeitskriterien
- v2.0.0 (active)  — zusätzlich `doraRelevanz` als Pflichtfeld

Drei Anlaufpunkte stehen dann zur Verfügung:
- **Demo-UI**:      <http://localhost:8000/demo>
- **OpenAPI-Docs**: <http://localhost:8000/docs>
- **Status (JSON)**: <http://localhost:8000/>

### Demo-UI

Die Demo (`frontend/index.html`) ist eine Single-File-Vue-3-App, die alle
relevanten Konzepte zeigt:
- links die versionierten Maskendefinitionen (active / retired / draft)
- mittig das **dynamisch aus dem JSON-Schema gerenderte Formular** —
  v1-Anträge zeigen drei Wesentlichkeitskriterien, v2-Anträge vier
- rechts die Antragsliste mit Schema-Version, Status und aktueller Stage

Workflow im Browser: aktive Maske links anklicken → Formular ausfüllen → Antrag
speichern → einreichen → durch die Stages „fachbereich → risikomgmt → vorstand"
genehmigen.

## Beispiel-Workflow gegen die API

```bash
# 1. Aktive Definition holen
curl localhost:8000/definitions?typ=AT_8_2_Analyse&nur_aktiv=true

# 2. Antrag erstellen (hart an v2.0.0 gebunden)
curl -X POST localhost:8000/instances -H 'Content-Type: application/json' -d '{
  "form_definition_id": "<id-from-step-1>",
  "antragsteller": "carsten.volmer",
  "daten": { ... }
}'

# 3. Antrag einreichen → in Stage "fachbereich"
curl -X POST localhost:8000/instances/<id>/submit

# 4. Stage genehmigen
curl -X POST localhost:8000/instances/<id>/decide -H 'Content-Type: application/json' -d '{
  "genehmiger": "user_a",
  "rolle": "Fachbereichsleiter",
  "entscheidung": "approved",
  "kommentar": "fachlich geprüft"
}'
```

## Tests

```bash
pip install pytest httpx
pytest tests/ -v
```

`tests/test_versioning.py` beweist die Versionsgarantie:
- v2-Antrag scheitert ohne `doraRelevanz`
- v1-Antrag bleibt gültig auch nach v2-Aktivierung
- Genehmigungskette läuft sauber durch alle drei Stages

## Was noch fehlt für Produktion

| Bereich | TODO |
|---|---|
| AuthN/AuthZ | Entra ID OIDC anbinden, `genehmiger`/`rolle` aus Token statt Body |
| Persistenz  | PostgreSQL statt SQLite, Alembic-Migrationen |
| Frontend    | Vue.js + JSONForms (`@jsonforms/vue` + `vue-vanilla`) |
| Audit       | Append-only-Log auf separater Tabelle/DB; ggf. Hash-Chain |
| Notifications | E-Mail/Teams-Benachrichtigung pro Stage-Übergang |
| Eskalation  | Scheduler (z. B. APScheduler) für SLA-Überschreitung |
| Anhänge     | Object-Storage (MinIO/S3) für Dokumente, gehasht referenziert |
| Reporting   | Read-only Streamlit-App auf gleicher DB für Aufsicht/Revision |

## Migration auf SpiffWorkflow / Camunda

Ist das Verzweigungsmuster komplex (parallele Genehmiger, bedingte Pfade,
Eskalationen mit BPMN-Diagrammen als Audit-Artefakte), kann `app/workflow.py`
durch eine SpiffWorkflow-Engine ersetzt werden, ohne dass das Datenmodell
geändert werden muss. Die `workflow_stages` werden dann zu einer Referenz auf
ein BPMN-Deployment.
