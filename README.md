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
│   ├── app/                    Code (Models, Routers, Workflow-Engine, Auth)
│   ├── schemas/                Beispiel-JSON-Schemas (AT 8.2 v1/v2, Vorstandsbeschluss v1)
│   ├── tests/                  Pytest-Tests
│   ├── alembic/                DB-Migrationen
│   ├── pyproject.toml          Python-Dependencies
│   └── Dockerfile
├── web/                        React-Frontend (Vite + TypeScript + Tailwind + shadcn-Stil)
│   ├── src/                    Pages, Components, Auth, API-Client
│   ├── package.json            JS-Dependencies (verwaltet via pnpm)
│   ├── nginx.conf              Reverse-Proxy zur Backend-API
│   └── Dockerfile
├── deploy/                     Container-Stack (Backend + Web; Mailpit nur Dev)
│   ├── docker-compose.yml      Prod-Basis-Stack (Backend + Web)
│   ├── docker-compose.dev.yml  Dev-Override (Mailpit-Mail-Catcher)
│   ├── dev-up.sh               Dev-Stack hochfahren (inkl. Bootstrap der Secrets)
│   ├── prod-up.sh              Prod-Basis-Stack hochfahren (ohne Mailpit)
│   ├── dev-down.sh             Stack stoppen
│   ├── bootstrap-env.sh        Secrets generieren
│   ├── backup/                 Cron-Skripte fuer SQLite-/Anhang-Backups
│   └── README.md
├── config/                     Auth-Konfiguration (per .gitignore ausgeschlossen)
└── .gitattributes              Cross-Platform-Line-Endings
```

## Schnellstart

Voraussetzungen: Docker + Docker-Compose-Plugin.

```bash
./deploy/dev-up.sh
```

Das Skript

1. erzeugt beim ersten Lauf `deploy/.env` mit echten Zufalls-Secrets
   (`JWT_SECRET`, `CONFIG_ENCRYPTION_KEY`),
2. baut und startet Backend, React-Frontend und (Dev-Override) Mailpit,
3. wartet auf den Backend-Healthcheck,
4. zeigt bei einer Erstinbetriebnahme die automatisch angelegten
   Admin-Zugangsdaten an (siehe unten).

Danach:

- **Frontend (React)**: <http://localhost:8000>
- **OpenAPI / Swagger**: <http://localhost:8000/docs>
- **Mailpit (Mail-UI)**: <http://localhost:8025>

Mailpit ist ein reiner Dev-Mail-Catcher aus `deploy/docker-compose.dev.yml`
und gehört nicht in Produktion. Für den Prod-Betrieb siehe
[`deploy/README.md`](deploy/README.md) (Abschnitt „Produktions-Härtung").

Stoppen mit `./deploy/dev-down.sh` (Volumes bleiben), oder
`./deploy/dev-down.sh --volumes` für einen frischen Start.

### Erster Login (Initial-Admin)

Bei leerer Datenbank legt der Start automatisch **einen initialen Admin-User**
an (Default-Username `admin`, steuerbar über `INITIAL_ADMIN_USERNAME` /
`INITIAL_ADMIN_PASSWORD` in `deploy/.env`). Ohne vorgegebenes Passwort wird ein
Einmal-Passwort generiert und im Container unter
`/app/data/initial-admin-password.txt` abgelegt — `dev-up.sh` und `prod-up.sh`
zeigen es nach dem Start an. Nach dem ersten Login das Passwort im Admin-Panel
ändern und die Datei löschen.

Der Initial-Admin wird **nur** angelegt, wenn weder ein Admin in der DB noch
eine Notfall-Datei (`config/emergency_users.json`) existiert — Brownfield-
Installationen bleiben unberührt, und bestehende Usernamen werden nie
überschrieben.

## Frontend-Entwicklung mit Hot-Reload

Voraussetzung: Node 20 oder neuer + pnpm (via `corepack enable`).

```bash
./deploy/dev-up.sh        # Backend laeuft im Container auf :8000

cd web
pnpm install
pnpm dev                   # Vite-Dev-Server auf :5173 mit HMR
```

Der Vite-Dev-Server proxiert API-Requests auf das laufende Backend.

## Konfiguration: `.env` und Umgebungsvariablen

Es gibt **kein** doppeltes Konfigurations-System:

- `deploy/.env` wird ausschließlich von Docker Compose gelesen (natives Feature)
  und an die Container weitergereicht. Dort sind es ganz normale Umgebungs­variablen.
- `bootstrap-env.sh` generiert die Pflicht-Secrets idempotent — bestehende Werte
  werden nie überschrieben.
- Der Python-Code liest `os.getenv(...)`. Es gibt keine zusätzliche `.env`-Library.

Pflicht-Variablen:

| Variable | Bedeutung |
|---|---|
| `JWT_SECRET` | 32 Bytes Zufall (`openssl rand -hex 32`) — wird auto-generiert |
| `CONFIG_ENCRYPTION_KEY` | Fernet-Schlüssel für SMTP-/LDAP-Service-Passwörter in der DB — wird auto-generiert |
| `CONFIG_ENCRYPTION_KEY_OLD` | *Optional* — alter Schlüssel als Decrypt-Fallback während einer Rotation |
| `INITIAL_ADMIN_USERNAME` | *Optional* — Username des Initial-Admins bei Erstinbetriebnahme (Default `admin`) |
| `INITIAL_ADMIN_PASSWORD` | *Optional* — festes Passwort für den Initial-Admin; leer = Einmal-Passwort wird generiert |

## Authentifizierung

Alle Endpunkte unter `/instances` sowie schreibende `/definitions`-Endpunkte sind
auth-pflichtig. Es gibt drei Modi (`AUTH_MODE`):

- `local` — User aus der DB (argon2id-Hashes, gepflegt im Admin-Panel)
- `ldap` — Bind gegen LDAPS, Rollen aus Gruppen-DN-Mapping
- `both` — LDAP zuerst, Fallback auf Local nur wenn LDAP unerreichbar oder User dort
  unbekannt. **Nicht** bei „LDAP kennt User, Passwort falsch" — das wäre ein
  Credential-Stuffing-Risiko.

**Auth-Modus, lokale User, LDAP, SMTP, Notification-Templates, Rollen-Empfänger
und SLA-Eskalation werden komplett in der DB gepflegt** und über `/admin`
konfiguriert. Lokale Dateien dienen nur dem Bootstrap und der Notfall­wiederherstellung.

### Notfall-Admin (Break-Glass)

```bash
cp config/emergency_users.example.json config/emergency_users.json
# Hash fuer das Notfall-Passwort erzeugen:
python -m app.auth.hash_password
# Den Hash in config/emergency_users.json eintragen.
```

Der Notfall-User wird **nur** geladen, wenn (a) die DB unerreichbar ist
oder (b) kein aktiver Admin in der `users`-Tabelle existiert. Jeder
Login über diesen Pfad erscheint im Audit-Log als `auth.login.emergency`.

Brownfield-Upgrades importieren bestehende `config/users.json` und
`config/role_emails.toml` einmalig in die DB; danach werden die
Dateien nicht mehr gelesen und können entfernt werden.

## Tests

```bash
# Backend (pytest, SQLite-Tempdatei pro Lauf)
cd backend
pip install -e ".[dev]"
pytest

# Frontend (Vitest)
cd web
pnpm test
```

## Datenbank

SQLite, Datei unter `/app/data/bank_workflow.db` im Backend-Container
(persistiert via Docker-Volume `bws-data`). Schema-Änderungen werden über
Alembic versioniert; beim Container-Start läuft automatisch `alembic upgrade head`.

```bash
# Neue Revision aus Modelländerungen erzeugen
cd backend && alembic revision --autogenerate -m "kurze beschreibung"

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
[`deploy/README.md`](deploy/README.md) — insbesondere die Checkliste
„Produktions-Härtung".

Wichtig: Der Service läuft mit **genau einem** uvicorn-Worker. Der
SLA-Eskalations-Scheduler (APScheduler) ist ein In-Process-Singleton; mehrere
Worker würden Eskalationen doppelt auslösen. Nicht horizontal skalieren.
