# Funktionale Tests

Pro fachlichem Test eine Sektion: Anforderung, Vorbedingungen, Soll/Ist-Tabelle.
Die `nachweismatrix.md` verlinkt am Ende auf die Tests; hier wird der **Inhalt**
des Tests erklärt.

---

## AT 7.2 Tz. 1 — Schemaversionsbindung

**Anforderung:** Ein Antrag, der gegen eine bestimmte Maskenversion gestellt
wurde, muss auch nach Maskenänderung gegen genau diese Version renderbar und
validierbar bleiben (Audit-Wert: was wurde wann mit welcher Maske beurteilt?).

**Test:** `tests/test_versioning.py::test_old_v1_instance_stays_valid_after_v2_activation`

**Vorbedingungen:**
- Geseedete AT-8.2-Maske in zwei Versionen (v1 retired, v2 active).
- v2 hat ein zusätzliches Pflichtfeld `doraRelevanz`, das in v1 nicht existiert.

**Soll/Ist:**

| Schritt | Soll | Ist (gemessen vom Test) |
|---|---|---|
| 1 | v1 wird kurzzeitig wieder aktiviert | Status `draft → active` |
| 2 | Antrag gegen v1 anlegen | HTTP 201 |
| 3 | v2 wird wieder aktiv, v1 retired | Status `retired` für v1 |
| 4 | Alten v1-Antrag erneut lesen | HTTP 200 |
| 5 | `schema_version` des Antrags | `AT_8_2_Analyse/1.0.0` |
| 6 | v2-Pflichtfeld in Schema des Antrags | **nicht** vorhanden |

**Audit-Wert:** Beweist, dass die FK-Bindung `FormInstance.form_definition_id`
auf eine konkrete Version zeigt und nicht auf „den Typ".

---

## AT 7.2 Tz. 2 — Validierung gegen gepinnte Schema-Version

**Anforderung:** Antragsdaten werden gegen das gepinnte JSON-Schema validiert,
nicht gegen das jeweils aktuelle. Pflichtfelder neuer Versionen wirken nur
auf Neuanträge.

**Test:** `tests/test_versioning.py::test_create_instance_against_active_v2_requires_dora`

**Soll/Ist:**

| Schritt | Soll | Ist |
|---|---|---|
| 1 | POST /instances mit v2-Definition, ohne `doraRelevanz` | HTTP 422 |
| 2 | Fehlerdetail | enthält `'doraRelevanz' is a required property` |

---

## AT 4.3.1 — Mehrstufige Genehmigung mit Rollentrennung

**Anforderung:** Ein Genehmigungsverfahren durchläuft mehrere Stages mit
unterschiedlichen Rollen. Jede Stage erzeugt einen revisionssicheren Audit-
Eintrag mit Genehmiger, Rolle, Entscheidung und Zeitstempel.

**Test:** `tests/test_versioning.py::test_full_approval_chain`

**Soll/Ist:**

| Schritt | Soll | Ist |
|---|---|---|
| 1 | Antrag anlegen + einreichen | Status `in_pruefung @ fachbereich` |
| 2 | Stage „fachbereich" genehmigen | Status `in_pruefung @ risikomgmt` |
| 3 | Stage „risikomgmt" genehmigen | Status `in_pruefung @ vorstand` |
| 4 | Stage „vorstand" genehmigen | Status `genehmigt`, `aktuelle_stage=abgeschlossen` |
| 5 | Anzahl Approvals | 3 |
| 6 | Alle Approvals haben Entscheidung | `approved` |

---

## AT 4.3.1 — Rollentrennung beim Decide-Endpoint

**Anforderung:** Ein User darf eine Stage nur dann entscheiden, wenn die zur
Stage gehörende Rolle in seinem Rollen-Set ist (aus dem JWT). Die Identität
ist nicht selbst-deklariert.

**Test:** `tests/test_auth_failure.py::test_decide_with_wrong_role_returns_403`

**Soll/Ist:**

| Schritt | Soll | Ist |
|---|---|---|
| 1 | Admin (alle Rollen) treibt einen Vorstandsbeschluss bis zur Vorstand-Stage | OK |
| 2 | User mit Rolle `Fachbereichsleiter` versucht zu entscheiden | HTTP 403 |
| 3 | Detailmeldung | nennt die fehlende Rolle „Vorstand" |

---

## AT 7.2 — Sitzungssicherheit (abgelaufener Token)

**Anforderung:** Abgelaufene JWT-Tokens dürfen keinen Zugriff auf geschützte
Endpunkte mehr ermöglichen.

**Test:** `tests/test_auth_failure.py::test_protected_endpoint_with_expired_token_returns_401`

**Soll/Ist:**

| Schritt | Soll | Ist |
|---|---|---|
| 1 | Konstruktion eines Tokens mit `exp` = vor 5 Minuten | OK |
| 2 | GET /instances mit diesem Token | HTTP 401 |
| 3 | Detailmeldung | „Token abgelaufen" |

---

## AT 4.3.4 — SLA-Eskalation

**Anforderung:** Wenn ein Antrag länger als das Stage-SLA in einer Stage hängt,
wird automatisch an den Bereichsleiter eskaliert.

**Test:** `tests/test_sla.py::test_eskalation_after_sla_breach`

**Soll/Ist:**

| Schritt | Soll | Ist |
|---|---|---|
| 1 | Antrag anlegen + einreichen | OK |
| 2 | `stage_eingetreten_am` per Test-Helper auf vor 11 Tagen setzen | OK |
| 3 | `scan_once()` ausführen | mind. 1 Eskalation gemeldet |
| 4 | Ein zweiter Scan | 0 Eskalationen (Idempotenz über `eskalation_sent_at`) |

---

## AT 7.2 — Datenintegrität bei Datei-Anhängen

**Anforderung:** Hochgeladene Anhänge werden mit SHA-256-Hash und Größe
persistiert; ein Download liefert byte-identisch das Original zurück.

**Test:** `tests/test_attachments.py::test_upload_pdf_persists_metadata_and_hash`

**Soll/Ist:**

| Schritt | Soll | Ist |
|---|---|---|
| 1 | PDF (≤ 25 MB) hochladen | HTTP 201 |
| 2 | Antwort enthält `sha256` (64 hex chars) | OK |
| 3 | Download | identische Bytes wie Original |
| 4 | `Content-Disposition: attachment` | mit Originaldateiname |

---

## AT 4.3.4 — Revisionssichere Audit-Spur

**Anforderung:** Jede sicherheitsrelevante Aktion erzeugt einen Eintrag in
`audit_events`, lesbar im Admin-Bereich.

**Test:** `tests/test_attachments.py::test_audit_log_records_attachment_actions`

**Soll/Ist:**

| Schritt | Soll | Ist |
|---|---|---|
| 1 | Datei-Upload durchführen | OK |
| 2 | `GET /admin/audit?kategorie=instance` | mind. ein Eintrag mit `action=attachment.uploaded` |

---

## AT 7.2 — Kontrollierte Programm-/Schemaänderungen

**Anforderung:** Neue Maskenversionen werden nicht direkt ad-hoc aktiv,
sondern durchlaufen einen kontrollierten Upload-Aktivierungs-Schritt.

**Test:** `tests/test_admin.py::test_upload_creates_draft_definition`

**Soll/Ist:**

| Schritt | Soll | Ist |
|---|---|---|
| 1 | POST /admin/definitions/upload (Multipart, JSON-Schema + UI-Schema) | HTTP 201 |
| 2 | Status der neu erzeugten Definition | `draft` (nicht active) |
| 3 | Aktivierung | separater Schritt über `/definitions/{id}/activate` |
