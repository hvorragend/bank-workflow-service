"""Admin-Endpunkte fuer SMTP, E-Mail-Templates und Rollen-Empfaenger."""
from __future__ import annotations

from datetime import UTC, datetime
from string import Template

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..auth.dependencies import require_permission
from ..auth.schemas import AuthenticatedUser
from ..config_service.templates import list_template_keys
from ..database import get_db
from ..notifications.smtp import NotificationsDisabled, send_email
from ..security import secrets
from . import schemas
from ._helpers import audit_admin, client_ip

router = APIRouter(prefix="/admin", tags=["admin:notifications"])


# -------------------- SMTP --------------------

def _smtp_row(db: Session) -> models.SmtpConfig:
    cfg = db.get(models.SmtpConfig, 1)
    if not cfg:
        cfg = models.SmtpConfig(id=1)
        db.add(cfg)
        db.flush()
    return cfg


@router.get("/smtp", response_model=schemas.SmtpConfigOut)
def get_smtp(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.smtp.read")),
):
    cfg = _smtp_row(db)
    return schemas.SmtpConfigOut(
        enabled=cfg.enabled, host=cfg.host, port=cfg.port, use_tls=cfg.use_tls,
        username=cfg.username, password_set=bool(cfg.password_enc),
        mail_from=cfg.mail_from, app_url=cfg.app_url,
        updated_at=cfg.updated_at, updated_by=cfg.updated_by,
    )


@router.put("/smtp", response_model=schemas.SmtpConfigOut)
def set_smtp(
    payload: schemas.SmtpConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.smtp.write")),
):
    cfg = _smtp_row(db)
    changes = payload.model_dump(exclude_unset=True)
    pw = changes.pop("password", None)
    for k, v in changes.items():
        setattr(cfg, k, v)
    if pw is None:
        pass
    elif pw == "":
        cfg.password_enc = None
    else:
        cfg.password_enc = secrets.encrypt(pw)
    cfg.updated_at = datetime.now(UTC)
    cfg.updated_by = user.username
    audit_admin(db, action="smtp_config.updated", actor=user.username,
                target_type="SmtpConfig", target_id="1", ip=client_ip(request),
                payload=changes)
    db.commit()
    return get_smtp(db, user)


@router.post("/smtp/test")
def smtp_test(
    payload: schemas.SmtpTestRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.smtp.test")),
):
    try:
        send_email(to=[payload.to], subject=payload.subject, body=payload.body, db=db)
    except NotificationsDisabled:
        raise HTTPException(409, "SMTP ist deaktiviert (enabled=False).") from None
    except Exception as e:  # noqa: BLE001
        audit_admin(db, action="smtp_test.failed", actor=user.username,
                    target_type="SmtpConfig", target_id="1", ip=client_ip(request),
                    payload={"to": payload.to, "error": str(e)})
        db.commit()
        raise HTTPException(502, f"Versand fehlgeschlagen: {e}") from e
    audit_admin(db, action="smtp_test.sent", actor=user.username,
                target_type="SmtpConfig", target_id="1", ip=client_ip(request),
                payload={"to": payload.to})
    db.commit()
    return {"ok": True, "message": f"Test-Mail versendet an {payload.to}."}


# -------------------- Templates --------------------

@router.get("/notifications/templates", response_model=list[schemas.NotificationTemplateOut])
def list_templates(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.notifications.templates.read")),
):
    rows = list(db.scalars(
        select(models.NotificationTemplate).order_by(models.NotificationTemplate.key)
    ).all())
    return [
        schemas.NotificationTemplateOut(
            key=r.key, subject=r.subject, body=r.body,
            updated_at=r.updated_at, updated_by=r.updated_by,
        )
        for r in rows
    ]


@router.get("/notifications/templates/{key}", response_model=schemas.NotificationTemplateOut)
def get_template(
    key: str,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.notifications.templates.read")),
):
    r = db.scalar(select(models.NotificationTemplate).where(models.NotificationTemplate.key == key))
    if not r:
        raise HTTPException(404, "Template nicht gefunden.")
    return schemas.NotificationTemplateOut(
        key=r.key, subject=r.subject, body=r.body,
        updated_at=r.updated_at, updated_by=r.updated_by,
    )


@router.put("/notifications/templates/{key}", response_model=schemas.NotificationTemplateOut)
def update_template(
    key: str,
    payload: schemas.NotificationTemplateUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.notifications.templates.write")),
):
    if key not in list_template_keys():
        raise HTTPException(400, f"Unbekannter Template-Key '{key}'.")
    r = db.scalar(select(models.NotificationTemplate).where(models.NotificationTemplate.key == key))
    if not r:
        r = models.NotificationTemplate(key=key, subject=payload.subject, body=payload.body)
        db.add(r)
    else:
        r.subject = payload.subject
        r.body = payload.body
    r.updated_at = datetime.now(UTC)
    r.updated_by = user.username
    audit_admin(db, action="notification_template.updated", actor=user.username,
                target_type="NotificationTemplate", target_id=key, ip=client_ip(request))
    db.commit()
    db.refresh(r)
    return schemas.NotificationTemplateOut(
        key=r.key, subject=r.subject, body=r.body,
        updated_at=r.updated_at, updated_by=r.updated_by,
    )


@router.post("/notifications/templates/{key}/preview")
def preview_template(
    key: str,
    payload: schemas.TemplatePreviewRequest,
    _: AuthenticatedUser = Depends(require_permission("admin.notifications.templates.read")),
):
    safe = {k: ("" if v is None else str(v)) for k, v in payload.context.items()}
    return {
        "key": key,
        "subject": Template(payload.subject).safe_substitute(safe),
        "body": Template(payload.body).safe_substitute(safe),
    }


# -------------------- Role-Emails --------------------

@router.get("/notifications/role-emails", response_model=list[schemas.RoleEmailOut])
def list_role_emails(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.notifications.role_emails.read")),
):
    rows = db.execute(
        select(
            models.RoleEmail.id, models.RoleEmail.role_id,
            models.Role.name, models.RoleEmail.email,
        ).join(models.Role, models.Role.id == models.RoleEmail.role_id)
        .order_by(models.Role.name, models.RoleEmail.email)
    ).all()
    return [
        schemas.RoleEmailOut(id=r[0], role_id=r[1], role_name=r[2], email=r[3])
        for r in rows
    ]


@router.put("/notifications/role-emails/{role_id}")
def set_role_emails(
    role_id: str,
    payload: schemas.RoleEmailsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.notifications.role_emails.write")),
):
    role = db.get(models.Role, role_id)
    if not role:
        raise HTTPException(404, "Rolle nicht gefunden.")
    new_emails = [e.strip() for e in payload.emails if e and e.strip()]
    db.query(models.RoleEmail).filter(models.RoleEmail.role_id == role_id).delete()
    db.flush()
    seen: set[str] = set()
    for addr in new_emails:
        if addr in seen:
            continue
        seen.add(addr)
        db.add(models.RoleEmail(role_id=role_id, email=addr))
    audit_admin(db, action="role_emails.set", actor=user.username,
                target_type="Role", target_id=role_id, ip=client_ip(request),
                payload={"role": role.name, "emails": new_emails})
    db.commit()
    return {"role_id": role_id, "role_name": role.name, "emails": new_emails}
