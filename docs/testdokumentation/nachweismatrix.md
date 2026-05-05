# Nachweismatrix

> **Hinweis:** generiert vom Pytest-Hook `--marisk-report`. Bitte nicht von Hand bearbeiten.
> Letzter Lauf: `alle Tests gruen` mit 14 relevanten Test-Markern.

## Fachliche Tests (MaRisk-/DORA-Bezug)

| Anforderung | Soll-Verhalten | Test | Ergebnis | Dauer |
|---|---|---|---|---|
| MaRisk AT 7.2 — kontrollierte Programmaenderungen | Neue Maskenversionen werden ueber den Admin-Upload als 'draft' angelegt; Aktivierung ist ein zweiter, dokumentierter Schritt. | `tests/test_admin.py::test_upload_creates_draft_definition` | OK passed | 0.02s |
| MaRisk AT 7.2 — Datenintegritaet bei Dateianhaengen | Hochgeladenes PDF wird mit SHA-256-Hash und Metadaten persistiert, byte-identisch wieder ausgeliefert. | `tests/test_attachments.py::test_upload_pdf_persists_metadata_and_hash` | OK passed | 0.033s |
| MaRisk AT 4.3.4 — revisionssichere Audit-Spur | Datei-Upload erzeugt einen audit_events-Eintrag mit Action 'attachment.uploaded'. | `tests/test_attachments.py::test_audit_log_records_attachment_actions` | OK passed | 0.028s |
| MaRisk AT 7.2 — Sitzungssicherheit | Abgelaufenes Access-Token wird mit 401 abgewiesen, kein Zugriff auf geschuetzte Endpunkte. | `tests/test_auth_failure.py::test_protected_endpoint_with_expired_token_returns_401` | OK passed | 0.002s |
| MaRisk AT 4.3.1 — Rollentrennung in Genehmigungsketten | User ohne die zur Stage gehoerende Rolle wird beim decide-Endpoint mit 403 abgewiesen. | `tests/test_auth_failure.py::test_decide_with_wrong_role_returns_403` | OK passed | 0.164s |
| MaRisk AT 7.2 — JWT-Schluesselrotation | Tokens, die mit dem alten Schluessel signiert wurden, bleiben gueltig, solange er in JWT_SECRETS steht. | `tests/test_jwt_rotation.py::test_token_signed_with_old_key_still_accepted` | OK passed | 0.022s |
| MaRisk AT 4.3.4 — separater Reporting-Zugang fuer Aufsicht | Reporting-Endpunkte sind ueber eigenen API-Token erreichbar; ein User-JWT reicht NICHT. | `tests/test_reporting.py::test_reporting_endpoint_with_jwt_only_returns_401` | OK passed | 0.003s |
| MaRisk AT 4.3.4 — Eskalation bei ueberschrittenem SLA | Antrag, der laenger als das Stage-SLA in einer Stage haengt, loest die Stufe-2-Eskalation an den Bereichsleiter aus. | `tests/test_sla.py::test_eskalation_after_sla_breach` | OK passed | 0.038s |
| MaRisk AT 7.2 Tz. 2 — Validierung gegen gepinnte Schema-Version | Antrag gegen v2 ohne doraRelevanz wird mit 422 abgewiesen. | `tests/test_versioning.py::test_create_instance_against_active_v2_requires_dora` | OK passed | 0.008s |
| MaRisk AT 7.2 Tz. 1 — Schemaversionsbindung | Altantrag (v1) bleibt nach Maskenwechsel auf v2 gegen sein urspruengliches Schema renderbar. | `tests/test_versioning.py::test_old_v1_instance_stays_valid_after_v2_activation` | OK passed | 0.061s |
| MaRisk AT 4.3.1 — mehrstufige Genehmigung mit Rollentrennung | Vollstaendige Approval-Kette laeuft durch alle drei Stages und endet mit status=genehmigt + 3 Audit-Eintraegen. | `tests/test_versioning.py::test_full_approval_chain` | OK passed | 0.065s |

## Notfallszenarien

| Szenario | Test | Ergebnis | Dauer |
|---|---|---|---|
| DR-1: Wiederanlauf nach DB-Restore (DORA Art. 11) | `tests/test_notfall.py::test_db_restore_smoke` | OK passed | 0.008s |
| DR-2: Schema-Drift — versehentlich aktivierte Version zurueckrollen | `tests/test_notfall.py::test_schema_drift_rollback` | OK passed | 0.038s |
| DR-3: Audit-Log-Wiederherstellung aus Snapshot | `tests/test_notfall.py::test_audit_log_recovery` | OK passed | 0.121s |

## Performance-Tests

| SLA (ms) | Test | Ergebnis | Dauer |
|---|---|---|---|
