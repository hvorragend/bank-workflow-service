"""FastAPI-Einstiegspunkt.

Lokal starten:  uvicorn app.main:app --reload
Anlaufpunkte:
  http://localhost:8000/docs    — OpenAPI Swagger UI
  http://localhost:8000/legacy  — Single-File-HTML-Demo (Vue 3 via CDN)
  http://localhost:8000/demo    — Alias auf /legacy

Beim ersten Start werden Tabellen angelegt und Beispiel-Definitionen
zusammen mit drei Demo-Antraegen geseedet, damit die Demo aussagekraeftig
ist (statt mit leerer Liste zu starten).
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select, text

from . import models
from .admin import router as admin_router
from .auth import router as auth_router
from .database import Base, SessionLocal, engine
from .routers import definitions, instances

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
LEGACY_DEMO_DIR = Path(__file__).resolve().parent.parent / "legacy_demo"


# ---------- Seed-Hilfen ----------

AT_8_2_STAGES = [
    {"name": "fachbereich", "rolle": "Fachbereichsleiter"},
    {"name": "risikomgmt",  "rolle": "Risikomanagement"},
    {"name": "vorstand",    "rolle": "Vorstand"},
]

VORSTAND_STAGES = [
    {"name": "vorbereitung",       "rolle": "Bereichsleiter"},
    {"name": "rechtskonformitaet", "rolle": "Compliance"},
    {"name": "vorstand",           "rolle": "Vorstand"},
    {"name": "protokoll",          "rolle": "Vorstandssekretariat"},
]


def _load(filename: str) -> dict[str, Any]:
    return json.loads((SCHEMAS_DIR / filename).read_text(encoding="utf-8"))


def _seed_definitions(db) -> dict[str, models.FormDefinition]:
    """Legt die drei Beispiel-Definitionen an und gibt sie nach Schluessel zurueck."""
    seeds = [
        ("at_8_2_v1",          "AT_8_2_Analyse",   "1.0.0",
         "AT 8.2 Wesentlichkeitsanalyse v1.0.0",   AT_8_2_STAGES, "retired"),
        ("at_8_2_v2",          "AT_8_2_Analyse",   "2.0.0",
         "AT 8.2 Wesentlichkeitsanalyse v2.0.0",   AT_8_2_STAGES, "active"),
        ("vorstandsbeschluss_v1", "Vorstandsbeschluss", "1.0.0",
         "Vorstandsbeschluss v1.0.0",              VORSTAND_STAGES, "active"),
    ]
    out: dict[str, models.FormDefinition] = {}
    for key, typ, version, titel, stages, target_status in seeds:
        d = models.FormDefinition(
            typ=typ,
            version=version,
            titel=titel,
            json_schema=_load(f"{key}.json"),
            ui_schema=_load(f"{key}.ui.json"),
            workflow_stages=stages,
            status=target_status,
            erstellt_von="seed",
        )
        db.add(d)
        out[key] = d
    db.flush()  # damit IDs fuer Demo-Antraege verfuegbar sind
    return out


def _seed_demo_instances(db, defs: dict[str, models.FormDefinition]) -> None:
    """Drei Demo-Antraege in unterschiedlichen Stadien — damit die Demo nicht leer wirkt."""
    now = datetime.now(timezone.utc)

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
        aktuelle_stage="abgeschlossen",
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
            "beschluss": {
                "titel": "Auslagerung Rechenzentrumsbetrieb an Atruvia AG",
                "datum": (now + timedelta(days=14)).date().isoformat(),
                "vorlagengeber": "Bereichsleitung IT",
                "kategorie": "Auslagerung",
            },
            "antrag": {
                "sachverhalt": (
                    "Verlagerung des operativen Rechenzentrumsbetriebs an die Atruvia AG "
                    "ab dem 01.10.2026 im Rahmen einer wesentlichen Auslagerung. Umfasst "
                    "Hardware, Betriebssystem-Plattformen sowie Backup-Loesungen."
                ),
                "begruendung": (
                    "Konzentration auf das Kerngeschaeft, Reduktion technischer Schuld, "
                    "Hebung von Skaleneffekten und Erhoehung der IKT-Resilience nach DORA. "
                    "Personelle Risiken werden durch die Bundelung beim Verbund-Dienstleister "
                    "gemindert."
                ),
                "alternativen": (
                    "Eigenbetrieb mit Modernisierung — verworfen wegen Kosten und Personalbedarf. "
                    "Cloud-only ueber Hyperscaler — verworfen wegen aufsichtsrechtlicher Bedenken."
                ),
            },
            "beschlussvorschlag": {
                "wortlaut": (
                    "Der Vorstand beschliesst die Auslagerung des Rechenzentrumsbetriebs an "
                    "die Atruvia AG zum 01.10.2026 unter den im Anhang beigefuegten Bedingungen."
                ),
            },
            "marisk_relevanz": {
                "at_9_auslagerung": True,
                "at_9_begruendung": (
                    "Wesentliche Auslagerung nach AT 9 Tz. 4 — kritische Funktion "
                    "Rechenzentrumsbetrieb mit unmittelbarer Geschaeftsrelevanz."
                ),
                "at_7_2_it_systeme": True,
                "at_7_2_begruendung": (
                    "Aenderung der produktiven IT-Landschaft, Cutover-Plan und Test-Strecke "
                    "gemaess AT 7.2 sind erforderlich."
                ),
                "dora_ikt_risiko": True,
                "dora_begruendung": (
                    "IKT-Drittparteienrisiko nach DORA Art. 28 ff., vertragliche Anforderungen "
                    "(Art. 30) sind in Vertragsentwurf abzubilden."
                ),
                "npp_neue_produkte": False,
                "at_8_2_wesentlich": True,
                "at_8_2_referenz": "AT-8.2-Antrag #2026-014",
            },
        },
        aktuelle_stage="vorstand",
        status="in_pruefung",
        erstellt_am=now - timedelta(days=6),
    )
    db.add(vb_pruefung)
    db.flush()
    for offset, (stage, rolle, gen, kommentar) in enumerate([
        ("vorbereitung",       "Bereichsleiter", "k.heuer",    "Vorlage geprueft, Sachverhalt vollstaendig."),
        ("rechtskonformitaet", "Compliance",     "j.seibold",  "AT 9 / DORA korrekt eingeordnet, Vertragsanforderungen vollstaendig."),
    ], start=1):
        db.add(models.Approval(
            instance_id=vb_pruefung.id, stage=stage, genehmiger=gen, rolle=rolle,
            entscheidung="approved", kommentar=kommentar,
            zeitstempel=now - timedelta(days=6 - offset * 2),
        ))

    # 3) Vorstandsbeschluss, noch im Entwurf — zum Durchklicken
    vb_entwurf = models.FormInstance(
        form_definition_id=defs["vorstandsbeschluss_v1"].id,
        antragsteller="bereichsleitung.personal",
        daten={
            "beschluss": {
                "titel": "Einfuehrung neue Mitarbeiterbeteiligung 2026",
                "datum": (now + timedelta(days=21)).date().isoformat(),
                "vorlagengeber": "Bereichsleitung Personal",
                "kategorie": "Personal",
            },
            "antrag": {
                "sachverhalt": (
                    "Einfuehrung eines genossenschaftlichen Beteiligungsmodells fuer Mitarbeitende "
                    "ab Geschaeftsjahr 2026 zur Foerderung der langfristigen Bindung."
                ),
                "begruendung": "",  # bewusst leer — Demo zeigt Entwurfs-Status
            },
            "beschlussvorschlag": {"wortlaut": ""},
            "marisk_relevanz": {
                "at_9_auslagerung": False,
                "at_7_2_it_systeme": False,
                "dora_ikt_risiko": False,
                "npp_neue_produkte": True,  # NPP-Hinweis triggert in der UI
                "npp_begruendung": (
                    "Neue Form der Mitarbeiterbeteiligung — NPP-Verfahren nach AT 8.1 ist anzustossen."
                ),
                "at_8_2_wesentlich": False,
            },
        },
        aktuelle_stage="entwurf",
        status="entwurf",
        erstellt_am=now - timedelta(days=1),
    )
    db.add(vb_entwurf)


def _seed(db) -> None:
    """Initial-Seed: Definitionen + drei Beispiel-Antraege, falls die DB leer ist."""
    if db.scalar(select(models.FormDefinition).limit(1)):
        return
    defs = _seed_definitions(db)
    _seed_demo_instances(db, defs)
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        _seed(db)
    yield


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

# Permissive CORS fuer die lokale Demo. Produktiv: auf Frontend-Origin einschraenken.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate-Limiter aus auth.rate_limit teilen — der Decorator auf /auth/login greift dann.
from .auth.rate_limit import limiter  # noqa: E402

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, auth_router.custom_rate_limit_exceeded_handler)

app.include_router(auth_router.router)
app.include_router(definitions.router)
app.include_router(instances.router)
app.include_router(admin_router.router)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "name": "Bank Workflow Service",
        "docs": "/docs",
        "legacy_demo": "/legacy",
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
        from fastapi import HTTPException, status as st
        raise HTTPException(status_code=st.HTTP_503_SERVICE_UNAVAILABLE, detail=f"DB nicht erreichbar: {e}")
    return {"status": "ready"}


@app.get("/legacy", include_in_schema=False)
def legacy_demo() -> FileResponse:
    """Liefert die Single-File-Vue-Demo aus (kein Build-Schritt erforderlich).

    Wird mit dem React-Frontend in Phase 1 / Commit 3 weiter parallel betrieben,
    damit das alte UI verfuegbar bleibt, bis das neue stabil ist.
    """
    return FileResponse(LEGACY_DEMO_DIR / "index.html")


@app.get("/demo", include_in_schema=False)
def demo_alias() -> FileResponse:
    """Alias fuer /legacy — historische URL aus dem Skelett."""
    return FileResponse(LEGACY_DEMO_DIR / "index.html")
