# Bank Workflow Service

Versionierter Workflow- und Genehmigungs-Service für bankfachliche Anträge
(AT 8.2-Analysen, IKT-Risikogenehmigungen, Vorstandsbeschlüsse, Projektanträge,
Vertragsunterzeichnungen …) als FastAPI/SQLAlchemy/Pydantic-Anwendung.

## Kernidee

Jeder ausgefüllte Antrag (`FormInstance`) wird **hart an eine konkrete Schema-Version**
(`FormDefinition.id`) gebunden. Wird die Maske im Folgejahr um neue Felder ergänzt,

- erscheint die neue Version nur bei Neuanträgen,
- bleiben Altanträge mit ihrem ursprünglichen Schema renderbar,
- bleibt jederzeit nachweisbar, welcher Maskenstand zur Beurteilung herangezogen wurde
  (relevant für MaRisk AT 7.2 und DORA-Audits).

## Repo-Struktur

```
bank-workflow-service/
├── backend/                    FastAPI-Service
│   ├── app/                    Code (Models, Routers, Workflow-Engine)
│   ├── schemas/                Beispiel-JSON-Schemas (AT 8.2 v1/v2, Vorstandsbeschluss v1)
│   ├── tests/                  Pytest-Tests
│   ├── legacy_demo/            Vue-3-Single-File-Demo, erreichbar unter /legacy
│   ├── alembic/                DB-Migrationen
│   ├── alembic.ini
│   ├── pyproject.toml          Python-Dependencies
│   └── Dockerfile
├── deploy/                     Container-Stack (Postgres + Backend, später Traefik + web)
│   ├── docker-compose.dev.yml  nur Postgres + MailHog für lokale Entwicklung
│   ├── docker-compose.yml      Komplettstack
│   └── README.md
├── web/                        React-Frontend (kommt in Commit 3)
└── .gitattributes              Cross-Platform-Line-Endings
```

## Authentifizierung

Alle Endpunkte unter `/instances` sowie schreibende `/definitions`-Endpunkte sind
seit Commit 2 auth-pflichtig. Es gibt zwei Modi, gesteuert über `AUTH_MODE`:

- `local` — User kommen aus `config/users.json` (argon2id-Hashes)
- `ldap` — Bind gegen LDAPS, Rollen aus Gruppen-DN-Mapping in `config/ldap.toml`
- `both` — LDAP zuerst, Fallback auf Local nur wenn LDAP unerreichbar oder User dort
  unbekannt. **Nicht** bei „LDAP kennt User, Passwort falsch" — das wäre ein
  Credential-Stuffing-Risiko.

**Pflicht-Umgebungsvariablen:**

| Variable | Bedeutung |
|---|---|
| `JWT_SECRET` | Mindestens 32 Bytes Zufallswert, z. B. `openssl rand -hex 32` |
| `AUTH_MODE` | `local`, `ldap` oder `both` (Default: `local`) |

**Lokaler Fallback einrichten:**

```bash
cp config/users.example.json config/users.json
# Hash für jedes User-Passwort erzeugen:
python -m app.auth.hash_password
# Den ausgegebenen Hash in config/users.json beim entsprechenden User eintragen.
```

`config/users.json` und `config/ldap.toml` sind über `.gitignore` ausgeschlossen — sie
enthalten Geheimnisse und gehören nicht ins Repo.

## Quickstart

Drei Wege, je nach Vorliebe.

### A — Schnell ausprobieren (SQLite, ohne Docker)

Voraussetzung: Python 3.11 oder neuer.

**Linux/macOS:**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export JWT_SECRET=$(openssl rand -hex 32)
uvicorn app.main:app --reload
```

**Windows (cmd):**

```cmd
cd backend
python -m venv .venv
.venv\Scripts\activate.bat
pip install -e ".[dev]"
set JWT_SECRET=replace-with-openssl-rand-hex-32
uvicorn app.main:app --reload
```

**Windows (PowerShell):**

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:JWT_SECRET = "replace-with-openssl-rand-hex-32"
uvicorn app.main:app --reload
```

Dann: <http://localhost:8000/legacy> für die Vue-Demo, <http://localhost:8000/docs> für Swagger.

### B — Mit Postgres lokal (Docker für die DB, Backend nativ)

```bash
docker compose -f deploy/docker-compose.dev.yml up -d

# Linux/macOS:
export DATABASE_URL=postgresql+psycopg://bws:bws_local_dev@localhost:5432/bws

# Windows (PowerShell):
$env:DATABASE_URL = "postgresql+psycopg://bws:bws_local_dev@localhost:5432/bws"

cd backend
alembic upgrade head      # einmalig, danach läuft's automatisch beim Start
uvicorn app.main:app --reload
```

### C — Komplettstack im Container

```bash
cp deploy/.env.example deploy/.env       # Passwort eintragen
docker compose -f deploy/docker-compose.yml up -d --build
```

Dann: <http://localhost:8000>.

## Tests

```bash
cd backend
pytest                       # nutzt SQLite-Tempfile, läuft ohne weitere Einrichtung
```

## Datenbank-Migrationen (Alembic)

Schema-Änderungen werden über Alembic versioniert, **nicht** durch `create_all`-Aufrufe
in Produktionscode. Beim Container-Start wird automatisch `alembic upgrade head`
ausgeführt.

```bash
# Neue Revision aus Modelländerungen erzeugen
alembic revision --autogenerate -m "kurze beschreibung"

# Migrationen anwenden
alembic upgrade head

# Auf eine bestimmte Revision zurück
alembic downgrade <revision-id>
```

## Geseedete Demo-Daten

Beim ersten Start (leere DB) werden angelegt:

- **AT 8.2-Maske** in zwei Versionen — v1.0.0 (retired, drei Wesentlichkeitskriterien)
  und v2.0.0 (active, zusätzlich `doraRelevanz` als Pflichtfeld)
- **Vorstandsbeschluss-Maske** v1.0.0 (active) mit conditional Pflichtfeldern für
  AT 9 / AT 7.2 / DORA / NPP / AT 8.2-Relevanz
- **Drei Demo-Anträge** in verschiedenen Stadien: ein abgeschlossener AT-8.2-Antrag,
  ein Vorstandsbeschluss zur Auslagerung an Atruvia (zur Entscheidung beim Vorstand),
  ein Vorstandsbeschluss zur Mitarbeiterbeteiligung (Entwurf, NPP-Hinweis aktiv)

## Deployment

Vorgesehen für Single-Host-Deployment auf einer Linux-VM unter Proxmox. Details siehe
[`deploy/README.md`](deploy/README.md).

## Roadmap

Tracking der grossen Schritte über GitHub-Issues:

- **Phase 1 — Fundament** (#3): Monorepo, Postgres+Alembic, LDAP-Auth, React-Frontend
- **Phase 2 — Sichtbare Features** (#4): „Aktuelles"-Dashboard, Archiv, Workflow-Upload, Anhänge
- **Phase 3 — Operations** (#5): Notifications, SLA-Eskalation, Reporting, MaRisk-Testdokumentation
