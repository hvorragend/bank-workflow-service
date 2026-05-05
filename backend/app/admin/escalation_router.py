"""Admin-Endpunkte fuer SLA-Eskalations-Scheduler."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models
from ..auth.dependencies import require_permission
from ..auth.schemas import AuthenticatedUser
from ..database import get_db
from ..escalation import scanner, scheduler
from . import schemas
from ._helpers import audit_admin, client_ip

router = APIRouter(prefix="/admin/escalation", tags=["admin:escalation"])


def _row(db: Session) -> models.EscalationConfig:
    cfg = db.get(models.EscalationConfig, 1)
    if not cfg:
        cfg = models.EscalationConfig(id=1)
        db.add(cfg)
        db.flush()
    return cfg


def _to_out(db: Session, cfg: models.EscalationConfig) -> schemas.EscalationConfigOut:
    role_name = None
    if cfg.bereichsleiter_role_id:
        role = db.get(models.Role, cfg.bereichsleiter_role_id)
        role_name = role.name if role else None
    return schemas.EscalationConfigOut(
        enabled=cfg.enabled,
        default_sla_days=cfg.default_sla_days,
        interval_minutes=cfg.interval_minutes,
        bereichsleiter_role_id=cfg.bereichsleiter_role_id,
        bereichsleiter_role_name=role_name,
        updated_at=cfg.updated_at,
        updated_by=cfg.updated_by,
        scheduler_running=scheduler._scheduler is not None,  # type: ignore[attr-defined]
        scheduler_interval_minutes=scheduler._current_interval,  # type: ignore[attr-defined]
    )


@router.get("", response_model=schemas.EscalationConfigOut)
def get_config(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.escalation.read")),
):
    return _to_out(db, _row(db))


@router.put("", response_model=schemas.EscalationConfigOut)
def set_config(
    payload: schemas.EscalationConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.escalation.write")),
):
    cfg = _row(db)
    changes = payload.model_dump(exclude_unset=True)
    if "bereichsleiter_role_id" in changes and changes["bereichsleiter_role_id"]:
        if not db.get(models.Role, changes["bereichsleiter_role_id"]):
            raise HTTPException(400, "Rolle unbekannt.")
    for k, v in changes.items():
        setattr(cfg, k, v)
    cfg.updated_at = datetime.now(timezone.utc)
    cfg.updated_by = user.username
    audit_admin(db, action="escalation_config.updated", actor=user.username,
                target_type="EscalationConfig", target_id="1", ip=client_ip(request),
                payload=changes)
    db.commit()
    # Scheduler neu konfigurieren — liest die frisch persistierten Werte aus der DB.
    scheduler.reload_from_db()
    return _to_out(db, _row(db))


@router.post("/run-now")
def run_now(
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.escalation.run_now")),
):
    counts = scanner.scan_once()
    audit_admin(db, action="escalation.run_now", actor=user.username,
                target_type="EscalationConfig", target_id="1", ip=client_ip(request),
                payload=counts)
    db.commit()
    return {"counts": counts}
