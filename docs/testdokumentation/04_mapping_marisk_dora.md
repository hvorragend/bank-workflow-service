# Mapping MaRisk / DORA → Tests

Handgepflegte Mapping-Tabelle. Sie ist die **Single Source of Truth** für die
Frage „welche regulatorische Anforderung deckt unser System wie ab?"

Die `nachweismatrix.md` ist die maschinell aus den Test-Markern erzeugte Variante
und enthält pro Lauf das aktuelle Pass/Fail. Diese hier hingegen pflegen wir
händisch mit Bezug zum Norm-Wortlaut.

---

## MaRisk

| Anforderung | Norm-Bezug | Abdeckende Tests | Status |
|---|---|---|---|
| Schemaversionsbindung — Altanträge nutzen ihre Erstversion | AT 7.2 Tz. 1 | `test_old_v1_instance_stays_valid_after_v2_activation`, `test_db_restore_smoke` | ✓ |
| Validierung gegen gepinnte Version | AT 7.2 Tz. 2 | `test_create_instance_against_active_v2_requires_dora` | ✓ |
| Kontrollierte Programm-/Schemaänderungen, Trennung Test/Prod | AT 7.2 Tz. 4 | `test_upload_creates_draft_definition`, `test_schema_drift_rollback` | ✓ |
| Mehrstufige Genehmigung mit Rollentrennung | AT 4.3.1 | `test_full_approval_chain`, `test_decide_with_wrong_role_returns_403` | ✓ |
| Revisionssichere Audit-Spur | AT 4.3.4 | `test_audit_log_records_attachment_actions`, `test_audit_log_recovery`, jeder `decide`-Pfad legt einen `Approval` an | ✓ |
| Eskalation bei Fristüberschreitung | AT 4.3.4 | `test_eskalation_after_sla_breach`, `test_idempotenz_zweiter_scan_macht_nichts` | ✓ |
| Sitzungssicherheit, JWT-Lifecycle | AT 7.2 (allgemein) | `test_protected_endpoint_with_expired_token_returns_401`, Refresh-Cookie-Tests | ✓ |
| Auslagerung — IT-Drittparteien (NPP-Kennzeichnung im Beschluss) | AT 9 + AT 8.1 NPP | Vorstandsbeschluss-Schema mit conditional Begründungspflicht, Hinweis-Notice für NPP | ✓ Abdeckung im Schema, kein eigener Test (regulatorisches Konzept) |
| Backup und Wiederherstellbarkeit | AT 7.2 Tz. 5 + DORA Art. 11 | `test_db_restore_smoke`, Runbook in `03_notfalldokumentation.md` | ✓ Test + Doku |

---

## DORA

| Anforderung | Norm-Bezug | Abdeckende Tests | Status |
|---|---|---|---|
| IKT-Risikoidentifikation (Wesentlichkeitsanalyse) | Art. 6 | AT-8.2-Maske + `test_seeded_definitions_present` | ✓ |
| IKT-Drittparteienrisiko in Beschlüssen kennzeichnen | Art. 28 ff. | Vorstandsbeschluss-Schema (`marisk_relevanz.dora_ikt_risiko` + Begründung) | ✓ Abdeckung im Schema |
| Vertragliche Anforderungen an IKT-Dienstleister | Art. 30 | wird in Beschlussvorlage abgefragt (siehe AT-9-Begründungstext) | ✓ Abdeckung im Schema |
| Wiederanlauffähigkeit | Art. 11 | `test_db_restore_smoke`, `test_audit_log_recovery`, Runbooks | ✓ |
| Resilience-Tests (operativ) | Art. 24 ff. | außerhalb dieser Anwendung — Pen-Tests + Restore-Übungen | (extern) |

---

## DSGVO / Querbezüge

| Anforderung | Bezug | Test / Maßnahme |
|---|---|---|
| Datensparsamkeit beim Login | Art. 5 Abs. 1 lit. c | Generische 401-Fehlermeldung, kein Hinweis auf Existenz eines Users (`test_login_with_unknown_user_returns_401`) |
| Vertraulichkeit von Passwörtern | Art. 32 | argon2id-Hashes, kein Klartext im Audit, Timing-Attack-Mitigation in `app/auth/local.py` |
| Recht auf Einsicht (Audit) | Art. 15 | Admin-Audit-Log filtert nach Akteur (`/admin/audit?akteur=X`) |

---

## Wartung dieser Tabelle

Diese Datei wird **bei jedem fachlichen PR aktualisiert**, wenn:

- ein neuer Test einen Marker bekommt, dessen Anforderung hier noch nicht steht,
- eine Norm-Referenz sich ändert (z. B. nach Veröffentlichung neuer MaRisk-Versionen),
- eine Maßnahme aus dem Code entfernt wird (Tabelle muss sichtbar dokumentieren,
  was nicht mehr abgedeckt ist).

Quartalsweise prüft die Innenrevision diese Tabelle gegen die Hausliste der
aufsichtsrechtlichen Anforderungen.
