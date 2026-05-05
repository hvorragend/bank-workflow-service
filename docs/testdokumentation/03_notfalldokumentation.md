# Notfalldokumentation (DORA Art. 11)

Drei Szenarien mit Runbook + automatisiertem Smoke-Test. Bei jedem Release
sollten die Smoke-Tests grün sein; eine Disaster-Recovery-Übung pro Quartal
prüft die manuellen Runbook-Schritte.

---

## DR-1 — Wiederanlauf nach DB-Restore

**Szenario:** Die DB-Datei (SQLite) bzw. der DB-Cluster (Postgres) ist beschädigt
oder verloren. Wir spielen das letzte `pg_dump` zurück und prüfen, dass alle
Antragsdaten vollständig wiederhergestellt sind und die Versions-Garantie weiter gilt.

**Smoke-Test:** `tests/test_notfall.py::test_db_restore_smoke`

**Manuelles Runbook:**

1. Backend-Container stoppen:
   ```bash
   docker compose -f deploy/docker-compose.yml stop backend
   ```
2. Postgres-Volume oder DB-Datei aus dem letzten Backup wiederherstellen:
   ```bash
   # Postgres (im Container)
   docker compose -f deploy/docker-compose.yml exec postgres pg_restore --clean -U bws -d bws /backups/letzter-dump.sql
   # SQLite (Single-Host-Demo)
   cp /backups/bank_workflow.db.snapshot /var/lib/bws/bank_workflow.db
   ```
3. Migrationen erneut ausführen (idempotent — falls die Backup-Version älter war):
   ```bash
   docker compose -f deploy/docker-compose.yml run --rm backend alembic upgrade head
   ```
4. Backend starten:
   ```bash
   docker compose -f deploy/docker-compose.yml start backend
   ```
5. Verifikation per `/auth/login` + `/instances?status=in_pruefung` → mind. die
   bekannten offenen Anträge sichtbar.

**Akzeptanzkriterien (vom Smoke-Test geprüft):**
- Alle drei Demo-Definitionen wieder vorhanden (AT 8.2 v1, v2, Vorstandsbeschluss v1).
- Bestehende `FormInstance`-Einträge haben weiterhin `form_definition_id` gesetzt
  (Versions-Pin ist erhalten — Audit-Wert!).

---

## DR-2 — Schema-Drift / fehlerhaft aktivierte Version

**Szenario:** Eine v3-Maskenversion wurde versehentlich aktiviert und enthält
einen fachlichen Fehler. Wir setzen sie auf `retired`, ohne Anträge zu verlieren,
und aktivieren die zuletzt korrekte Version.

**Smoke-Test:** `tests/test_notfall.py::test_schema_drift_rollback`

**Manuelles Runbook:**

1. Admin meldet sich an, öffnet **Admin → Maskenverwaltung**.
2. v3 markieren, **Retire** klicken (UI fragt zur Bestätigung).
3. Die zuletzt korrekte Version (z. B. v2) ist bereits retired → erst per
   Datenbank-Override auf `draft` setzen (siehe SQL-Snippet im Repo unter
   `docs/runbooks/`), dann **Aktivieren** im UI.
4. Audit-Log prüfen: `kategorie=definition`, `action=definition.retired` und
   `definition.activated` müssen mit dem Admin-Account auftauchen.

**Wichtig:** Anträge, die fälschlich gegen v3 gestellt wurden, bleiben an v3
gepinnt. Sie sind weiterhin lesbar (Schema in DB), aber nicht mehr neu erstellbar.
Bei Bedarf wird pro Antrag eine Korrektur-Aktion durchgeführt — niemals
nachträgliche Schema-Manipulation.

---

## DR-3 — Audit-Log-Wiederherstellung

**Szenario:** Die `audit_events`-Tabelle wurde durch einen Bedienfehler oder
einen Hardware-Defekt beschädigt. Wir spielen einen Snapshot zurück und prüfen,
dass die alten Einträge wieder lesbar sind.

**Smoke-Test:** `tests/test_notfall.py::test_audit_log_recovery`

**Manuelles Runbook:**

1. Backend stoppen.
2. Aus dem letzten `pg_dump --table=audit_events` wiederherstellen:
   ```bash
   docker compose -f deploy/docker-compose.yml exec postgres psql -U bws -d bws -c "TRUNCATE audit_events;"
   docker compose -f deploy/docker-compose.yml exec postgres pg_restore --table=audit_events ...
   ```
3. Backend starten.
4. UI öffnen, **Admin → Audit**: Filter „Kategorie: auth" → mind. die letzten
   Logins der vergangenen 30 Tage müssen wieder sichtbar sein.

**Hinweis MaRisk AT 4.3.4:** Audit-Daten sind revisionssicher zu führen.
Daher **niemals** ohne dokumentierten Restore-Vorgang Einträge ergänzen oder
ändern. Bei Verlust ist der Zeitraum, in dem keine Auditdaten vorliegen,
explizit zu protokollieren und der Innenrevision zu melden.

---

## Backup-Strategie (Kurzform)

| Schicht | Frequenz | Aufbewahrung |
|---|---|---|
| `pg_dump` (volle Logik-DB) | täglich 02:00 Uhr | 30 Tage am Host, 90 Tage auf Proxmox Backup Server |
| Object-Storage (Anhänge-Volume) | täglich 02:30 Uhr | wie oben |
| Proxmox-VM-Snapshot | wöchentlich Sonntag 03:00 Uhr | 8 Wochen |

**Restore-Übung:** einmal pro Quartal aus einem ≥ 30 Tage alten Backup,
Protokoll an die Innenrevision.
