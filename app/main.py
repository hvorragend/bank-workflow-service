"""FastAPI application entrypoint.

Run locally:  uvicorn app.main:app --reload
Then visit:
  http://localhost:8000/docs   — OpenAPI Swagger UI
  http://localhost:8000/demo   — Single-file HTML demo

On first start, the lifespan creates tables and seeds two example versions
of the AT 8.2 analysis form so you can see how versioning behaves end-to-end.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select

from . import models
from .database import Base, SessionLocal, engine
from .routers import definitions, instances

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def _seed(db) -> None:
    """Seed two AT 8.2 versions if the table is empty — purely for demo purposes."""
    if db.scalar(select(models.FormDefinition).limit(1)):
        return

    seeds = [
        ("at_8_2_v1.json", "at_8_2_v1.ui.json", "1.0.0", "retired"),
        ("at_8_2_v2.json", "at_8_2_v2.ui.json", "2.0.0", "active"),
    ]
    for schema_file, ui_file, version, target_status in seeds:
        schema_path = SCHEMAS_DIR / schema_file
        ui_path = SCHEMAS_DIR / ui_file
        if not schema_path.exists():
            continue

        d = models.FormDefinition(
            typ="AT_8_2_Analyse",
            version=version,
            titel=f"AT 8.2 Wesentlichkeitsanalyse v{version}",
            json_schema=json.loads(schema_path.read_text(encoding="utf-8")),
            ui_schema=json.loads(ui_path.read_text(encoding="utf-8")),
            workflow_stages=[
                {"name": "fachbereich", "rolle": "Fachbereichsleiter"},
                {"name": "risikomgmt",  "rolle": "Risikomanagement"},
                {"name": "vorstand",    "rolle": "Vorstand"},
            ],
            status=target_status,
            erstellt_von="seed",
        )
        db.add(d)
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        _seed(db)
    yield


app = FastAPI(
    title="IDV Workflow Service",
    description=(
        "Versionierter Workflow- und Genehmigungs-Service für bankfachliche "
        "Anträge (AT 8.2, IKT-Risikogenehmigungen, Vorstandsbeschlüsse, …). "
        "Jede FormInstance ist hart an die Schema-Version gebunden, die zum "
        "Erstellungszeitpunkt aktiv war."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Permissive CORS for the local demo. In production: restrict to your frontend origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(definitions.router)
app.include_router(instances.router)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "name": "IDV Workflow Service",
        "docs": "/docs",
        "demo": "/demo",
        "status": "ok",
    }


@app.get("/demo", include_in_schema=False)
def demo() -> FileResponse:
    """Serve the single-file HTML demo (no build step required)."""
    return FileResponse(FRONTEND_DIR / "index.html")
