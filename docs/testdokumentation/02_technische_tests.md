# Technische Tests

## Coverage-Schwellen

Die folgenden Schwellwerte sind Orientierung — sie werden beim CI-Lauf
gemessen, ein Unterschreiten führt zur Build-Eskalation:

| Bereich | Schwelle |
|---|---|
| Backend gesamt (`backend/app/`) | ≥ 85 % |
| `app/workflow.py` (Audit-kritisch) | ≥ 95 % |
| `app/routers/instances.py::_validate_against_definition` | ≥ 95 % |
| `app/auth/` (Auth-Pfad) | ≥ 90 % |
| Frontend (`web/src/lib/`) | ≥ 80 % |

Coverage wird nicht in dieser Phase erzwungen, sondern dokumentiert.
In Phase 4 (Operations-Hardening) kommt der CI-Job mit `--cov-fail-under`.

## Integrationstests

Aktuelles Inventar (Backend, `backend/tests/`):

| Datei | Was wird getestet |
|---|---|
| `test_versioning.py` | Schemaversionsbindung, Validierung gegen Pin, vollständige Approval-Kette |
| `test_auth_local.py` | Login, /me, Refresh-Cookie-Rotation, Logout |
| `test_auth_failure.py` | Falsche Credentials, fehlender / abgelaufener Token, Rollen-Negativtest |
| `test_auth_ldap.py` | LDAP-Bind via `ldap3.MOCK_SYNC` (Erfolg, BadCredentials, Unreachable) |
| `test_archive_and_stats.py` | Server-Filter, Stats-Kennzahlen, CSV-Export |
| `test_admin.py` | Upload (positiv/negativ), Diff zwischen Versionen, Audit-Log, Retire |
| `test_attachments.py` | Upload mit Hash, Whitelist, Download byte-identisch, Delete-Sperre nach Submit |
| `test_sla.py` | SLA-Stufen 1 + 2, Idempotenz, Stage-Wechsel-Reset |
| `test_notifications.py` | Empfänger-Auflösung, Mail-Trigger pro Workflow-Ereignis |
| `test_notfall.py` | drei Disaster-Recovery-Szenarien |

Frontend (`web/`):

| Datei | Was wird getestet |
|---|---|
| `src/lib/schema-rules.test.ts` | JSON-Schema-Renderer-Helfer (Conditional, Pflichtfeld, Init, Pruning) |

## Performance-Budgets (geplant)

Aktuell keine Performance-Tests im Repo — die folgenden Budgets sind die
Zielwerte für Phase 4:

| Endpunkt | Budget |
|---|---|
| `POST /instances` | < 100 ms (P95) |
| `_validate_against_definition` (intern) | < 50 ms |
| `GET /instances` (Liste, ≤ 200 Einträge) | < 200 ms |
| `GET /admin/audit` (Liste, ≤ 200 Einträge) | < 200 ms |
| Frontend FCP (First Contentful Paint) | < 2 s im internen Netz |

Mess-Marker: `@pytest.mark.performance(sla_ms=100)`, der Generator schreibt
sie in den Performance-Block der `nachweismatrix.md`.

## Lokale Ausführung

```bash
# Backend
cd backend
pytest                      # alle Tests
pytest --marisk-report      # zusätzlich nachweismatrix.md neu schreiben
pytest -m fachlich          # nur fachliche Tests
pytest -m notfall           # nur DR-Szenarien

# Frontend
cd web
pnpm test
```
