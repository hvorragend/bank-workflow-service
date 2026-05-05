"""Admin-Endpunkte fuer Benutzerverwaltung (lokale User in der DB)."""
from __future__ import annotations

from datetime import datetime, timezone

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..auth.dependencies import require_permission
from ..auth.schemas import AuthenticatedUser
from ..database import get_db
from . import schemas
from ._helpers import audit_admin, client_ip, user_to_out

router = APIRouter(prefix="/admin/users", tags=["admin:users"])
_hasher = PasswordHasher()


def _get_user(db: Session, user_id: str) -> models.User:
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(404, "User nicht gefunden.")
    return user


def _admin_perm() -> str:
    return "admin.users.write"


def _is_last_active_admin(db: Session, user: models.User) -> bool:
    """True, wenn das Deaktivieren/Loeschen dieses Users den letzten aktiven
    Admin-Inhaber wegnehmen wuerde. 'Admin' = irgendeine Rolle, die
    admin.users.write besitzt."""
    perm = db.scalar(select(models.Permission).where(models.Permission.code == _admin_perm()))
    if not perm:
        return False
    others = db.execute(
        select(models.User.id)
        .join(models.UserRole, models.UserRole.user_id == models.User.id)
        .join(models.RolePermission, models.RolePermission.role_id == models.UserRole.role_id)
        .where(
            models.RolePermission.permission_id == perm.id,
            models.User.is_active.is_(True),
            models.User.id != user.id,
        )
        .limit(1)
    ).first()
    return others is None


@router.get("", response_model=list[schemas.UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.users.read")),
    q: str | None = Query(None, description="Filter Username/Anzeigename (case-insensitive)"),
    auth_source: str | None = Query(None, description="local | ldap"),
    is_active: bool | None = None,
    role: str | None = Query(None, description="Filter auf Rollen-Namen"),
    limit: int = Query(200, ge=1, le=1000),
):
    stmt = select(models.User)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            (models.User.username.ilike(like)) | (models.User.display_name.ilike(like))
        )
    if auth_source:
        stmt = stmt.where(models.User.auth_source == auth_source)
    if is_active is not None:
        stmt = stmt.where(models.User.is_active.is_(is_active))
    if role:
        stmt = (
            stmt.join(models.UserRole, models.UserRole.user_id == models.User.id)
            .join(models.Role, models.Role.id == models.UserRole.role_id)
            .where(models.Role.name == role)
        )
    stmt = stmt.order_by(models.User.username).limit(limit)
    users = list(db.scalars(stmt).all())
    return [user_to_out(u) for u in users]


@router.get("/{user_id}", response_model=schemas.UserOut)
def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.users.read")),
):
    return user_to_out(_get_user(db, user_id))


@router.post("", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: schemas.UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.users.write")),
):
    if db.scalar(select(models.User).where(models.User.username == payload.username)):
        raise HTTPException(409, f"Username {payload.username!r} existiert bereits.")
    new = models.User(
        username=payload.username,
        display_name=payload.display_name,
        email=payload.email or None,
        auth_source="local",
        password_argon2=_hasher.hash(payload.password),
        is_active=True,
    )
    db.add(new)
    db.flush()
    role_ids = list(dict.fromkeys(payload.role_ids))
    for rid in role_ids:
        if not db.get(models.Role, rid):
            raise HTTPException(400, f"Rolle {rid} unbekannt.")
        db.add(models.UserRole(user_id=new.id, role_id=rid))
    audit_admin(db, action="user.created", actor=user.username,
                target_type="User", target_id=new.id, ip=client_ip(request),
                payload={"username": new.username, "roles": role_ids})
    db.commit()
    db.refresh(new)
    return user_to_out(new)


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: str,
    payload: schemas.UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.users.write")),
):
    target = _get_user(db, user_id)
    changes = payload.model_dump(exclude_unset=True)
    if "is_active" in changes and not changes["is_active"]:
        if _is_last_active_admin(db, target):
            raise HTTPException(409, "Letzter aktiver Admin kann nicht deaktiviert werden.")
    for k, v in changes.items():
        setattr(target, k, v)
    target.updated_at = datetime.now(timezone.utc)
    audit_admin(db, action="user.updated", actor=user.username,
                target_type="User", target_id=target.id, ip=client_ip(request),
                payload=changes)
    db.commit()
    db.refresh(target)
    return user_to_out(target)


@router.post("/{user_id}/password", status_code=204)
def reset_password(
    user_id: str,
    payload: schemas.UserPasswordUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.users.write")),
):
    target = _get_user(db, user_id)
    if target.auth_source != "local":
        raise HTTPException(409, "Nur lokale User haben ein Passwort.")
    target.password_argon2 = _hasher.hash(payload.password)
    target.updated_at = datetime.now(timezone.utc)
    audit_admin(db, action="user.password_reset", actor=user.username,
                target_type="User", target_id=target.id, ip=client_ip(request))
    db.commit()


@router.put("/{user_id}/roles", response_model=schemas.UserOut)
def set_roles(
    user_id: str,
    payload: schemas.UserRolesUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.users.assign_roles")),
):
    target = _get_user(db, user_id)
    desired = list(dict.fromkeys(payload.role_ids))
    for rid in desired:
        if not db.get(models.Role, rid):
            raise HTTPException(400, f"Rolle {rid} unbekannt.")

    # Prevent: removing all admin-permission roles from the last admin user
    target.roles  # warmup relationship
    existing = list(db.scalars(
        select(models.UserRole).where(models.UserRole.user_id == target.id)
    ).all())
    for link in existing:
        db.delete(link)
    db.flush()
    for rid in desired:
        db.add(models.UserRole(user_id=target.id, role_id=rid))
    db.flush()

    if _is_last_active_admin(db, target):
        # Wir sind erst nach dem Schreiben sicher, dass der User selbst noch
        # admin.users.write haelt. Wenn nicht — rollback.
        db.refresh(target)
        has_admin_write = any(
            p.code == "admin.users.write" for r in target.roles for p in r.permissions
        )
        if not has_admin_write:
            db.rollback()
            raise HTTPException(
                409, "Letzter aktiver Admin darf admin.users.write nicht verlieren."
            )

    audit_admin(db, action="user.roles_set", actor=user.username,
                target_type="User", target_id=target.id, ip=client_ip(request),
                payload={"role_ids": desired})
    db.commit()
    db.refresh(target)
    return user_to_out(target)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.users.write")),
):
    target = _get_user(db, user_id)
    if _is_last_active_admin(db, target):
        raise HTTPException(409, "Letzter aktiver Admin kann nicht geloescht werden.")
    # Soft-Delete: deaktivieren statt physisch loeschen — Audit-Bezug bleibt.
    target.is_active = False
    target.updated_at = datetime.now(timezone.utc)
    audit_admin(db, action="user.deactivated", actor=user.username,
                target_type="User", target_id=target.id, ip=client_ip(request))
    db.commit()
