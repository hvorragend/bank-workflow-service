# Testdokumentation — Lesereihenfolge für Auditoren

Dieses Verzeichnis dokumentiert die Test-Strategie des Bank Workflow Service
und ist so aufgebaut, dass die Wirtschaftsprüfung / Innenrevision /
externe Aufsicht es **in dieser Reihenfolge** lesen kann:

| Datei | Inhalt |
|---|---|
| `00_README.md` | dieses Dokument |
| `01_funktionale_tests.md` | Soll/Ist-Tabellen pro fachlich relevantem Test, mit MaRisk-/DORA-Bezug |
| `02_technische_tests.md` | Coverage-Schwellwerte, Integrationstests, Performance |
| `03_notfalldokumentation.md` | Drei Wiederanlauf-Szenarien als Runbook + Smoke-Tests |
| `04_mapping_marisk_dora.md` | handgepflegte Mapping-Tabelle Anforderung ↔ Test |
| `nachweismatrix.md` | **generiert** vom Pytest-Hook `--marisk-report`, jeden Lauf neu |

## Wie die Matrix entsteht

Die Datei `nachweismatrix.md` ist nicht handgepflegt. Sie entsteht durch
einen Pytest-Lauf mit dem CLI-Flag:

```bash
cd backend
pytest --marisk-report
```

Der Hook (`tests/conftest.py`, Funktion `pytest_terminal_summary`) sammelt
alle Tests mit den Markern `@pytest.mark.fachlich`, `@pytest.mark.notfall`
oder `@pytest.mark.performance` und schreibt eine Markdown-Tabelle. Jede Zeile
verbindet die Anforderung (z. B. „MaRisk AT 7.2 Tz. 1") mit einem konkreten
Test-Nodeid und dem Ergebnis (passed / failed / skipped) inkl. Laufzeit.

Bei jedem Release sollte ein frischer `--marisk-report`-Lauf passieren und
die resultierende `nachweismatrix.md` zusammen mit dem Release-Tag versioniert
werden.

## Test-Marker

```python
@pytest.mark.fachlich(
    anforderung="MaRisk AT 7.2 Tz. 1 — Schemaversionsbindung",
    soll="Altantrag bleibt nach Maskenaenderung gegen sein urspruengliches Schema validierbar.",
)
def test_old_v1_instance_stays_valid_after_v2_activation(...): ...

@pytest.mark.notfall(szenario="DR-1: Wiederanlauf nach DB-Restore")
def test_db_restore_smoke(...): ...

@pytest.mark.performance(sla_ms=100)
def test_validate_under_100ms(...): ...
```

## Was nicht in dieser Doku steht

- Klassische Code-Reviews und Pull-Request-Disziplin (gehört in die
  Entwicklungsrichtlinie der Volksbank Gronau-Ahaus eG, nicht hierher).
- Berechtigungen von Personen — die kommen aus LDAP-Gruppen, das Mapping
  liegt in `config/ldap.toml` bzw. `config/users.json`.
- Externe Pen-Tests — werden separat dokumentiert.
