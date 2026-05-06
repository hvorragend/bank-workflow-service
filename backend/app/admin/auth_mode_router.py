"""Admin-Endpunkte fuer den Auth-Modus (local | ldap | both) und Login-Rate-Limit."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..auth.dependencies import require_permission
from ..auth.schemas import AuthenticatedUser
from ..config_service import auth_mode as auth_mode_svc
from ..database import get_db
from . import schemas
from ._helpers import audit_admin, client_ip

router = APIRouter(prefix="/admin/auth-mode", tags=["admin:auth-mode"])


@router.get("", response_model=schemas.AuthModeOut)
def get_auth_mode(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.auth_mode.read")),
):
    return schemas.AuthModeOut(
        mode=auth_mode_svc.get_auth_mode(db),
        login_rate_limit=auth_mode_svc.get_login_rate_limit(db),
    )


@router.put("", response_model=schemas.AuthModeOut)
def set_auth_mode(
    payload: schemas.AuthModeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.auth_mode.write")),
):
    auth_mode_svc.set_auth_mode(db, payload.mode, actor=user.username)
    if payload.login_rate_limit:
        auth_mode_svc.set_login_rate_limit(db, payload.login_rate_limit, actor=user.username)
    audit_admin(db, action="auth_mode.updated", actor=user.username,
                target_type="AppSetting", target_id="auth.mode", ip=client_ip(request),
                payload={"mode": payload.mode, "rate_limit": payload.login_rate_limit})
    db.commit()
    return schemas.AuthModeOut(
        mode=auth_mode_svc.get_auth_mode(db),
        login_rate_limit=auth_mode_svc.get_login_rate_limit(db),
    )
