"""FastAPI-Einstiegspunkt.

Lokal starten:  uvicorn app.main:app --reload
Anlaufpunkte:
  http://localhost:8000/docs    — OpenAPI Swagger UI

Beim ersten Start werden Tabellen angelegt und Beispiel-Definitionen
zusammen mit drei Demo-Antraegen geseedet, damit die Demo aussagekraeftig
ist (statt mit leerer Liste zu starten).
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select, text

from . import models
from .admin import router as admin_router
from .auth import router as auth_router
from .database import Base, SessionLocal, engine
from .reporting import router as reporting_router
from .routers import attachments, definitions, delegations, instances

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

log = logging.getLogger("app")


def _configure_logging() -> None:
    """O-007: schlankes, zentrales Logging beim App-Start. Level ueber die
    Env-Variable LOG_LEVEL steuerbar (Default INFO), einheitliches Format mit
    Zeitstempel. Bewusst kein JSON-Zwang — nur damit INFO-Logs (Scheduler,
    Notifications, Auth) ueberhaupt sichtbar werden."""
    level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        force=True,  # ueberschreibt ein evtl. von uvicorn/gunicorn gesetztes Basis-Setup
    )


# ---------- Seed-Hilfen ----------

# Linearer DAG: start -> fachbereich -> risikomgmt -> vorstand -> end.
AT_8_2_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "fachbereich", "type": "user_task", "label": "Fachbereich", "rolle": "Fachbereichsleiter"},
        {"id": "risikomgmt",  "type": "user_task", "label": "Risikomanagement", "rolle": "Risikomanagement"},
        {"id": "vorstand",    "type": "user_task", "label": "Vorstand", "rolle": "Vorstand"},
        {"id": "end", "type": "end"},
    ],
    "edges": [
        {"from": "start", "to": "fachbereich"},
        {"from": "fachbereich", "to": "risikomgmt"},
        {"from": "risikomgmt", "to": "vorstand"},
        {"from": "vorstand", "to": "end"},
    ],
}

# Vorstandsbeschluss mit parallelem Branch (Compliance + Risiko parallel) als
# Demo des neuen DAG-Modells.
VORSTAND_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "vorbereitung",       "type": "user_task", "label": "Vorbereitung",
         "rolle": "Bereichsleiter", "sla_days": 5},
        {"id": "split", "type": "parallel_split"},
        {"id": "rechtskonformitaet", "type": "user_task", "label": "Compliance",
         "rolle": "Compliance", "sla_days": 7},
        {"id": "risikoanalyse",      "type": "user_task", "label": "Risikomanagement",
         "rolle": "Risikomanagement", "sla_days": 7},
        {"id": "join", "type": "parallel_join"},
        {"id": "vorstand",  "type": "user_task", "label": "Vorstand",
         "rolle": "Vorstand", "sla_days": 14},
        {"id": "protokoll", "type": "user_task", "label": "Protokoll",
         "rolle": "Vorstandssekretariat", "sla_days": 3},
        {"id": "end", "type": "end"},
    ],
    "edges": [
        {"from": "start", "to": "vorbereitung"},
        {"from": "vorbereitung", "to": "split"},
        {"from": "split", "to": "rechtskonformitaet"},
        {"from": "split", "to": "risikoanalyse"},
        {"from": "rechtskonformitaet", "to": "join"},
        {"from": "risikoanalyse", "to": "join"},
        {"from": "join", "to": "vorstand"},
        {"from": "vorstand", "to": "protokoll"},
        {"from": "protokoll", "to": "end"},
    ],
}


def _load(filename: str) -> dict[str, Any]:
    return json.loads((SCHEMAS_DIR / filename).read_text(encoding="utf-8"))


def _seed_definitions(db) -> dict[str, models.FormDefinition]:
    """Legt die drei Beispiel-Definitionen an und gibt sie nach Schluessel zurueck."""
    seeds = [
        ("at_8_2_v1",          "AT_8_2_Analyse",   "1.0.0",
         "AT 8.2 Wesentlichkeitsanalyse v1.0.0",   AT_8_2_GRAPH, "retired"),
        ("at_8_2_v2",          "AT_8_2_Analyse",   "2.0.0",
         "AT 8.2 Wesentlichkeitsanalyse v2.0.0",   AT_8_2_GRAPH, "active"),
        ("vorstandsbeschluss_v1", "Vorstandsbeschluss", "1.0.0",
         "Vorstandsbeschluss v1.0.0",              VORSTAND_GRAPH, "active"),
    ]
    out: dict[str, models.FormDefinition] = {}
    for key, typ, version, titel, graph, target_status in seeds:
        d = models.FormDefinition(
            typ=typ,
            version=version,
            titel=titel,
            json_schema=_load(f"{key}.json"),
            ui_schema=_load(f"{key}.ui.json"),
            workflow_graph=graph,
            status=target_status,
            erstellt_von="seed",
        )
        db.add(d)
        out[key] = d
    db.flush()  # damit IDs fuer Demo-Antraege verfuegbar sind
    return out


def _seed_demo_instances(db, defs: dict[str, models.FormDefinition]) -> None:
    """Drei Demo-Antraege in unterschiedlichen Stadien — damit die Demo nicht leer wirkt."""
    now = datetime.now(UTC)

    # 1) AT-8.2-Antrag, vollstaendig genehmigt (alle drei Stages)
    at82 = models.FormInstance(
        form_definition_id=defs["at_8_2_v2"].id,
        antragsteller="carsten.volmer",
        daten={
            "antragsteller": {
                "name": "Carsten Volmer",
                "abteilung": "IT-Sicherheit",
                "datum": (now - timedelta(days=12)).date().isoformat(),
            },
            "vorhaben": {
                "titel": "Einfuehrung Cloud-Storage fuer Kreditakten",
                "kategorie": "IT-System",
            },
            "wesentlichkeitskriterien": {
                "ertragsrelevanz": "mittel",
                "risikorelevanz": "hoch",
                "aufsichtsrechtlicheRelevanz": True,
                "doraRelevanz": True,
            },
            "ergebnis": {
                "wesentlich": True,
                "begruendung": (
                    "Verarbeitung kundenbezogener und besonders schutzbeduerftiger "
                    "Daten mit aufsichtsrechtlicher und DORA-Relevanz nach Art. 6 ff."
                ),
            },
        },
        status="genehmigt",
        erstellt_am=now - timedelta(days=12),
        abgeschlossen_am=now - timedelta(days=4),
    )
    db.add(at82)
    db.flush()
    for offset, (stage, rolle, gen, kommentar) in enumerate([
        ("fachbereich", "Fachbereichsleiter", "m.becker",   "Fachlich gepruef und plausibel."),
        ("risikomgmt",  "Risikomanagement",   "s.althaus",  "Risiken bewertet, Maßnahmen ausreichend."),
        ("vorstand",    "Vorstand",           "v.rehmann",  "Beschluss gefasst."),
    ], start=1):
        db.add(models.Approval(
            instance_id=at82.id, stage=stage, genehmiger=gen, rolle=rolle,
            entscheidung="approved", kommentar=kommentar,
            zeitstempel=now - timedelta(days=12 - offset * 3),
        ))

    # 2) Vorstandsbeschluss, im Vorstand zur Entscheidung — 2 von 4 Stages durch
    vb_pruefung = models.FormInstance(
        form_definition_id=defs["vorstandsbeschluss_v1"].id,
        antragsteller="bereichsleitung.it",
        daten={
            "fachbereich_kopf": {
                "entscheidungstraeger": "Vorstand",
                "verfasser": "Bereichsleitung IT",
                "weitere_beteiligte": "BL Unternehmenssteuerung, Auslagerungskoordinator, ISB",
                "betreff": "Auslagerung Rechenzentrumsbetrieb an Atruvia AG",
                "zeitliche_restriktion": "Cutover bis 01.10.2026 (Vertragsende Eigenbetrieb)",
                "umsetzung_geplant_bis": (now + timedelta(days=160)).date().isoformat(),
                "anlagen": "AT-8.2-Bewertung, Vertragsentwurf Atruvia, Risikoanalyse Auslagerung",
            },
            "antrag": {
                "antragstext": (
                    "Es wird die Freigabe der Auslagerung des Rechenzentrumsbetriebs an die "
                    "Atruvia AG zum 01.10.2026 unter den im Anhang beigefuegten Bedingungen "
                    "beantragt."
                ),
            },
            "sachverhalt": {
                "ausgangssituation": (
                    "Der Rechenzentrumsbetrieb wird derzeit im Eigenbetrieb gefuehrt. Die "
                    "Hardware ist in Teilen am Ende des Lebenszyklus, Personalressourcen sind "
                    "knapp und die Betriebskosten steigen kontinuierlich."
                ),
                "sachverhalt_beschlussantrag": (
                    "Verlagerung des operativen Rechenzentrumsbetriebs an die Atruvia AG ab dem "
                    "01.10.2026 im Rahmen einer wesentlichen Auslagerung (Hardware, Betriebssystem-"
                    "Plattformen, Backup). Geprueft wurden: Eigenbetrieb mit Modernisierung "
                    "(verworfen wegen Kosten/Personalbedarf) und Cloud-only ueber Hyperscaler "
                    "(verworfen wegen aufsichtsrechtlicher Bedenken)."
                ),
                "bewertung_veraenderungen": (
                    "Konzentration auf das Kerngeschaeft, Reduktion technischer Schuld, Hebung "
                    "von Skaleneffekten und Erhoehung der IKT-Resilience nach DORA. Erfolg "
                    "messbar an SLA-Erreichung, Anzahl Major Incidents und TCO-Verlauf. "
                    "Umsetzung in vier Phasen: Vertrag, Migration Test, Migration Prod, Hypercare."
                ),
                "fazit_empfehlung": (
                    "Empfehlung zur Genehmigung: Die Auslagerung verbessert die operative "
                    "Stabilitaet und reduziert Personal- sowie Konzentrationsrisiken."
                ),
                "naechste_schritte": (
                    "Vertragsabschluss bis Ende Q3, Aufnahme in das Auslagerungsregister, "
                    "Start der Migration Q4."
                ),
            },
            "kommunikation": {
                "erforderlich": True,
                "plan": (
                    "Mitarbeitende IT (Vorab-Info ueber Personalmanagement), Gesamthaus per "
                    "Hausmitteilung nach Vertragsabschluss, Aufsichtsrat im Rahmen der "
                    "Quartalsberichterstattung. Verantwortlich: BL IT in Abstimmung mit Vorstand."
                ),
            },
            "pflichtpruefungen": {
                "npp_neue_produkte_maerkte": False,
                "at_8_2_bewertung_erforderlich": True,
                "at_8_2_referenz": "AT-8.2-Antrag #2026-014",
                "at_9_auslagerung": True,
                "at_9_fremdbezug_dienstleistung": False,
                "at_9_fremdbezug_it_dienstleistung": False,
                "at_9_begruendung": (
                    "Wesentliche Auslagerung nach AT 9 Tz. 4 — kritische Funktion "
                    "Rechenzentrumsbetrieb mit unmittelbarer Geschaeftsrelevanz. "
                    "IKT-Drittparteienrisiko nach DORA Art. 28 ff. wird in Vertragsentwurf "
                    "abgebildet (Art. 30)."
                ),
                "neues_it_system": False,
                "it_projekt_richtlinie": True,
                "projekt_referenz": "Projektantrag #2026-IT-007",
            },
        },
        status="in_pruefung",
        erstellt_am=now - timedelta(days=6),
    )
    db.add(vb_pruefung)
    db.flush()
    # Bereits genehmigte Stages: Vorbereitung + beide Branches der Parallelitaet.
    # Aktiv ist jetzt der Vorstand (nach dem Join).
    for offset, (stage, rolle, gen, kommentar) in enumerate([
        ("vorbereitung",       "Bereichsleiter",   "k.heuer",    "Vorlage geprueft, Sachverhalt vollstaendig."),
        ("rechtskonformitaet", "Compliance",       "j.seibold",  "AT 9 / DORA korrekt eingeordnet, Vertragsanforderungen vollstaendig."),
        ("risikoanalyse",      "Risikomanagement", "s.althaus",  "Risiken bewertet, Maßnahmen ausreichend."),
    ], start=1):
        db.add(models.Approval(
            instance_id=vb_pruefung.id, stage=stage, genehmiger=gen, rolle=rolle,
            entscheidung="approved", kommentar=kommentar,
            zeitstempel=now - timedelta(days=6 - offset * 2),
        ))
    db.add(models.FormInstanceActiveStage(
        instance_id=vb_pruefung.id,
        node_id="vorstand",
        rolle="Vorstand",
        eingetreten_am=now - timedelta(days=2),
    ))

    # 3) Vorstandsbeschluss, noch im Entwurf — zum Durchklicken
    vb_entwurf = models.FormInstance(
        form_definition_id=defs["vorstandsbeschluss_v1"].id,
        antragsteller="bereichsleitung.personal",
        daten={
            "fachbereich_kopf": {
                "entscheidungstraeger": "Vorstand",
                "verfasser": "Bereichsleitung Personal",
                "betreff": "Einfuehrung neue Mitarbeiterbeteiligung 2026",
                "umsetzung_geplant_bis": (now + timedelta(days=240)).date().isoformat(),
            },
            "antrag": {
                "antragstext": (
                    "Es wird die Einfuehrung eines genossenschaftlichen Beteiligungsmodells fuer "
                    "Mitarbeitende ab Geschaeftsjahr 2026 zur Foerderung der langfristigen Bindung "
                    "beantragt."
                ),
            },
            "sachverhalt": {
                "ausgangssituation": (
                    "Aktuell besteht kein eigenstaendiges Mitarbeiterbeteiligungsmodell jenseits "
                    "der Tarifvereinbarungen."
                ),
                "sachverhalt_beschlussantrag": "",  # bewusst leer — Demo zeigt Entwurfs-Status
                "bewertung_veraenderungen": "",
                "fazit_empfehlung": "",
            },
            "kommunikation": {
                "erforderlich": False,
            },
            "pflichtpruefungen": {
                "npp_neue_produkte_maerkte": True,  # NPP-Hinweis triggert in der UI
                "npp_begruendung": (
                    "Neue Form der Mitarbeiterbeteiligung — NPP-Verfahren nach AT 8.1 ist anzustossen."
                ),
                "at_8_2_bewertung_erforderlich": False,
                "at_9_auslagerung": False,
                "at_9_fremdbezug_dienstleistung": False,
                "at_9_fremdbezug_it_dienstleistung": False,
                "neues_it_system": False,
                "it_projekt_richtlinie": False,
            },
        },
        status="entwurf",
        erstellt_am=now - timedelta(days=1),
    )
    db.add(vb_entwurf)


def _seed(db) -> None:
    """Initial-Seed, falls die DB leer ist.

    Die Schema-Definitionen (Masken-Katalog) werden immer angelegt — ohne sie
    ist die App nicht bedienbar. Die drei fiktiven Demo-Antraege sind reine
    Entwicklungs-/Demo-Daten und werden nur bei ausdruecklichem Opt-in
    (SEED_DEMO_DATA=1) geseedet — in einem revisionsrelevanten Prod-System
    haben erfundene, „genehmigte" Antraege nichts zu suchen.
    """
    if db.scalar(select(models.FormDefinition).limit(1)):
        return
    defs = _seed_definitions(db)
    if os.getenv("SEED_DEMO_DATA", "").strip().lower() in {"1", "true", "yes"}:
        _seed_demo_instances(db, defs)
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. Zentrales Logging konfigurieren, bevor irgendetwas loggt.
    _configure_logging()
    log.info("Bank Workflow Service startet (LOG_LEVEL=%s).", os.getenv("LOG_LEVEL", "INFO"))

    # 1. Verschluesselung verfuegbar? Sonst hier sofort scheitern.
    from . import bootstrap
    bootstrap.assert_encryption_available()

    # 2. Tabellen anlegen (Quickstart) und Demo-Daten seeden.
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        _seed(db)

    # 3. Permission-Katalog + Default-Rollen + Admin-Rolle + Singletons + Templates.
    with SessionLocal() as db:
        bootstrap.seed_permission_catalog(db)
        bootstrap.ensure_default_roles(db)
        bootstrap.ensure_admin_role(db)
        bootstrap.ensure_singleton_configs(db)
        bootstrap.ensure_default_templates(db)
        bootstrap.import_legacy_files_if_present(db)
        bootstrap.ensure_initial_admin(db)
        bootstrap.ensure_emergency_admin_or_die(db)

    # 4. SLA-Scheduler hochfahren — liest jetzt aus der DB.
    from .escalation import scheduler as escalation_scheduler
    escalation_scheduler.start_from_db()
    try:
        yield
    finally:
        escalation_scheduler.stop()


app = FastAPI(
    title="Bank Workflow Service",
    description=(
        "Versionierter Workflow- und Genehmigungs-Service fuer bankfachliche "
        "Antraege (AT 8.2, IKT-Risikogenehmigungen, Vorstandsbeschluesse, …). "
        "Jede FormInstance ist hart an die Schema-Version gebunden, die zum "
        "Erstellungszeitpunkt aktiv war."
    ),
    version="0.3.0",
    lifespan=lifespan,
)

# CORS: per CORS_ALLOW_ORIGINS (komma-separiert) konfigurierbar. Default ist die
# lokale Frontend-Origin — NICHT mehr Wildcard, damit Produktion nicht
# zwangslaeufig offen laeuft. Wildcard nur, wenn explizit CORS_ALLOW_ORIGINS=*
# gesetzt wird (bewusste Entscheidung des Operators).
_cors_env = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
if _cors_env:
    _cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
else:
    _cors_origins = ["http://localhost:8000", "http://localhost:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate-Limiter aus auth.rate_limit teilen — der Decorator auf /auth/login greift dann.
from .auth.rate_limit import limiter  # noqa: E402

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, auth_router.custom_rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.include_router(auth_router.router)
app.include_router(definitions.router)
app.include_router(instances.router)
app.include_router(attachments.router)
app.include_router(delegations.router)
app.include_router(admin_router.router)
app.include_router(reporting_router.router)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "name": "Bank Workflow Service",
        "docs": "/docs",
        "status": "ok",
    }


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness-Probe: nur Prozess-/HTTP-Erreichbarkeit, kein Backing-Service-Check.
    Wird vom Container/Reverse-Proxy in kurzen Intervallen aufgerufen."""
    return {"status": "ok"}


@app.get("/ready", tags=["meta"])
def ready() -> dict:
    """Readiness-Probe: prueft, ob die DB ansprechbar ist. Wird seltener aufgerufen."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        from fastapi import HTTPException
        from fastapi import status as st
        raise HTTPException(
            status_code=st.HTTP_503_SERVICE_UNAVAILABLE, detail=f"DB nicht erreichbar: {e}"
        ) from e
    return {"status": "ready"}
