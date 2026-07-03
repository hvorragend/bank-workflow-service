"""Admin-Endpunkte fuer LDAP-Konfiguration, Group-Mapping, Test-Bind und Sync."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..auth import ldap_bind, ldap_sync
from ..auth.dependencies import require_permission
from ..auth.schemas import AuthenticatedUser
from ..config_service.ldap_settings import get_ldap_settings
from ..database import get_db
from ..security import secrets
from . import schemas
from ._helpers import audit_admin, client_ip

router = APIRouter(prefix="/admin/ldap", tags=["admin:ldap"])


def _row(db: Session) -> models.LdapConfig:
    cfg = db.get(models.LdapConfig, 1)
    if not cfg:
        cfg = models.LdapConfig(id=1)
        db.add(cfg)
        db.flush()
    return cfg


@router.get("", response_model=schemas.LdapConfigOut)
def get_config(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.ldap.read")),
):
    cfg = _row(db)
    return schemas.LdapConfigOut(
        enabled=cfg.enabled,
        server=cfg.server,
        bind_user_template=cfg.bind_user_template,
        search_base=cfg.search_base,
        group_search_base=cfg.group_search_base,
        group_filter=cfg.group_filter,
        tls_required=cfg.tls_required,
        ca_cert_pem=cfg.ca_cert_pem,
        timeout_seconds=cfg.timeout_seconds,
        service_account_dn=cfg.service_account_dn,
        service_account_password_set=bool(cfg.service_account_pw_enc),
        user_filter=cfg.user_filter,
        attr_username=cfg.attr_username,
        attr_display_name=cfg.attr_display_name,
        attr_email=cfg.attr_email,
        updated_at=cfg.updated_at,
        updated_by=cfg.updated_by,
    )


@router.put("", response_model=schemas.LdapConfigOut)
def update_config(
    payload: schemas.LdapConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.ldap.write")),
):
    cfg = _row(db)
    changes = payload.model_dump(exclude_unset=True)
    pw_change = changes.pop("service_account_password", None)

    for k, v in changes.items():
        setattr(cfg, k, v)

    if pw_change is None:
        pass  # unveraendert
    elif pw_change == "":
        cfg.service_account_pw_enc = None
    else:
        cfg.service_account_pw_enc = secrets.encrypt(pw_change)

    cfg.updated_at = datetime.now(UTC)
    cfg.updated_by = user.username
    audit_admin(db, action="ldap_config.updated", actor=user.username,
                target_type="LdapConfig", target_id="1", ip=client_ip(request),
                payload={k: v for k, v in changes.items() if k != "ca_cert_pem"})
    db.commit()
    return get_config(db, user)  # reuse for shape


@router.get("/role-mapping", response_model=list[schemas.LdapRoleMappingOut])
def list_mappings(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.ldap.read")),
):
    rows = db.execute(
        select(
            models.LdapRoleMapping.id,
            models.LdapRoleMapping.group_dn,
            models.LdapRoleMapping.role_id,
            models.Role.name,
        ).join(models.Role, models.Role.id == models.LdapRoleMapping.role_id)
        .order_by(models.LdapRoleMapping.group_dn)
    ).all()
    return [
        schemas.LdapRoleMappingOut(id=r[0], group_dn=r[1], role_id=r[2], role_name=r[3])
        for r in rows
    ]


@router.post("/role-mapping", response_model=schemas.LdapRoleMappingOut, status_code=201)
def create_mapping(
    payload: schemas.LdapRoleMappingCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.ldap.write")),
):
    role = db.get(models.Role, payload.role_id)
    if not role:
        raise HTTPException(400, "Rolle unbekannt.")
    existing = db.scalar(
        select(models.LdapRoleMapping).where(
            models.LdapRoleMapping.group_dn == payload.group_dn,
            models.LdapRoleMapping.role_id == payload.role_id,
        )
    )
    if existing:
        raise HTTPException(409, "Mapping existiert bereits.")
    m = models.LdapRoleMapping(group_dn=payload.group_dn, role_id=payload.role_id)
    db.add(m)
    audit_admin(db, action="ldap_role_mapping.created", actor=user.username,
                target_type="LdapRoleMapping", target_id=m.id, ip=client_ip(request),
                payload={"group_dn": payload.group_dn, "role": role.name})
    db.commit()
    db.refresh(m)
    return schemas.LdapRoleMappingOut(
        id=m.id, group_dn=m.group_dn, role_id=m.role_id, role_name=role.name,
    )


@router.delete("/role-mapping/{mapping_id}", status_code=204)
def delete_mapping(
    mapping_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.ldap.write")),
):
    m = db.get(models.LdapRoleMapping, mapping_id)
    if not m:
        raise HTTPException(404, "Mapping nicht gefunden.")
    audit_admin(db, action="ldap_role_mapping.deleted", actor=user.username,
                target_type="LdapRoleMapping", target_id=mapping_id, ip=client_ip(request),
                payload={"group_dn": m.group_dn})
    db.delete(m)
    db.commit()


@router.post("/test-bind", response_model=schemas.LdapTestResult)
def test_bind(
    payload: schemas.LdapTestBindRequest,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.ldap.test")),
):
    cfg = get_ldap_settings(db)
    try:
        user = ldap_bind.authenticate_ldap(cfg, payload.username, payload.password)
        return schemas.LdapTestResult(
            ok=True, message="Bind erfolgreich.",
            roles=user.roles, display_name=user.name, email=user.email,
        )
    except ldap_bind.LdapBadCredentials as e:
        return schemas.LdapTestResult(ok=False, message=f"Passwort falsch: {e}")
    except ldap_bind.LdapUserUnknown as e:
        return schemas.LdapTestResult(ok=False, message=f"User unbekannt: {e}")
    except ldap_bind.LdapServerUnreachable as e:
        return schemas.LdapTestResult(ok=False, message=f"Server nicht erreichbar: {e}")


@router.post("/sync", response_model=schemas.LdapSyncJobOut, status_code=status.HTTP_202_ACCEPTED)
def start_sync(
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.ldap.sync")),
    dry_run: bool = False,
):
    cfg = get_ldap_settings(db)
    if not cfg.enabled or not cfg.server or not cfg.service_account_dn:
        raise HTTPException(409, "LDAP nicht vollstaendig konfiguriert (enabled, server, service_account_dn).")
    job = ldap_sync.start_sync_job(dry_run=dry_run, actor=user.username)
    audit_admin(db, action="ldap_sync.started", actor=user.username,
                target_type="LdapSyncJob", target_id=job.id, ip=client_ip(request),
                payload={"dry_run": dry_run})
    db.commit()
    return _job_to_out(job)


@router.get("/sync", response_model=list[schemas.LdapSyncJobOut])
def list_sync_jobs(
    _: AuthenticatedUser = Depends(require_permission("admin.ldap.sync")),
):
    return [_job_to_out(j) for j in ldap_sync.list_jobs()]


@router.get("/sync/{job_id}", response_model=schemas.LdapSyncJobOut)
def get_sync_job(
    job_id: str,
    _: AuthenticatedUser = Depends(require_permission("admin.ldap.sync")),
):
    job = ldap_sync.get_job(job_id)
    if not job:
        raise HTTPException(404, "Sync-Job nicht gefunden.")
    return _job_to_out(job)


def _job_to_out(j) -> schemas.LdapSyncJobOut:
    return schemas.LdapSyncJobOut(
        id=j.id, status=j.status,
        started_at=j.started_at, finished_at=j.finished_at,
        counts=j.counts, error=j.error, dry_run=j.dry_run,
    )
