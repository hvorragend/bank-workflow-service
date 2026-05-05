"""Admin-Endpunkte fuer System-Status und Schluessel-Rotation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import models
from ..auth.dependencies import require_permission
from ..auth.schemas import AuthenticatedUser
from ..bootstrap import get_emergency_users
from ..config_service.auth_mode import get_auth_mode
from ..config_service.ldap_settings import get_ldap_settings
from ..config_service.smtp_settings import get_smtp_settings
from ..database import engine, get_db
from ..escalation import scheduler
from ..security import secrets
from . import schemas
from ._helpers import audit_admin, client_ip

router = APIRouter(prefix="/admin/system", tags=["admin:system"])


@router.get("/status", response_model=schemas.SystemStatus)
def status(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.system.read")),
):
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    smtp = get_smtp_settings(db)
    ldap = get_ldap_settings(db)

    user_count = db.scalar(select(func.count(models.User.id))) or 0
    perm = db.scalar(select(models.Permission).where(models.Permission.code == "admin.users.write"))
    admin_count = 0
    if perm:
        admin_count = db.scalar(
            select(func.count(func.distinct(models.User.id)))
            .join(models.UserRole, models.UserRole.user_id == models.User.id)
            .join(models.RolePermission, models.RolePermission.role_id == models.UserRole.role_id)
            .where(
                models.RolePermission.permission_id == perm.id,
                models.User.is_active.is_(True),
            )
        ) or 0

    return schemas.SystemStatus(
        encryption_key_fingerprint=secrets.key_fingerprint(),
        db_ok=db_ok,
        scheduler_running=scheduler._scheduler is not None,  # type: ignore[attr-defined]
        smtp_enabled=smtp.enabled,
        smtp_host=smtp.host,
        ldap_enabled=ldap.enabled,
        ldap_server=ldap.server,
        auth_mode=get_auth_mode(db),
        user_count=user_count,
        admin_count=admin_count,
        emergency_users_loaded=len(get_emergency_users()),
    )


@router.post("/rekey-secrets", response_model=schemas.RekeyResult)
def rekey(
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.system.rekey")),
):
    """Re-verschluesselt alle in der DB liegenden Geheimwerte mit dem aktuellen
    CONFIG_ENCRYPTION_KEY. Nutzt die MultiFernet-Faehigkeit, alte Tokens zu
    entschluesseln, solange CONFIG_ENCRYPTION_KEY_OLD gesetzt ist.
    """
    result = {"smtp_password": False, "ldap_service_password": False}

    smtp = db.get(models.SmtpConfig, 1)
    if smtp and smtp.password_enc:
        plaintext = secrets.decrypt(smtp.password_enc)
        smtp.password_enc = secrets.encrypt(plaintext)
        result["smtp_password"] = True

    ldap = db.get(models.LdapConfig, 1)
    if ldap and ldap.service_account_pw_enc:
        plaintext = secrets.decrypt(ldap.service_account_pw_enc)
        ldap.service_account_pw_enc = secrets.encrypt(plaintext)
        result["ldap_service_password"] = True

    audit_admin(db, action="system.rekey", actor=user.username,
                target_type="System", target_id=None, ip=client_ip(request),
                payload=result)
    db.commit()
    return schemas.RekeyResult(**result)
