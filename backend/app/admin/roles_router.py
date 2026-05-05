"""Admin-Endpunkte fuer Rollen und Permission-Katalog."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..auth.dependencies import require_permission
from ..auth.schemas import AuthenticatedUser
from ..database import get_db
from . import schemas
from ._helpers import audit_admin, client_ip, role_to_out

router = APIRouter(prefix="/admin", tags=["admin:roles"])


# ---------- Permissions ----------

@router.get("/permissions", response_model=list[schemas.PermissionOut])
def list_permissions(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.permissions.read", "admin.roles.read")),
):
    rows = list(db.scalars(select(models.Permission).order_by(models.Permission.code)).all())
    return [
        schemas.PermissionOut(id=r.id, code=r.code, area=r.area, description=r.description)
        for r in rows
    ]


# ---------- Roles ----------

@router.get("/roles", response_model=list[schemas.RoleOut])
def list_roles(
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.roles.read")),
):
    roles = list(db.scalars(select(models.Role).order_by(models.Role.name)).all())
    return [role_to_out(r) for r in roles]


@router.get("/roles/{role_id}", response_model=schemas.RoleOut)
def get_role(
    role_id: str,
    db: Session = Depends(get_db),
    _: AuthenticatedUser = Depends(require_permission("admin.roles.read")),
):
    role = db.get(models.Role, role_id)
    if not role:
        raise HTTPException(404, "Rolle nicht gefunden.")
    return role_to_out(role)


@router.post("/roles", response_model=schemas.RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: schemas.RoleCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.roles.write")),
):
    if db.scalar(select(models.Role).where(models.Role.name == payload.name)):
        raise HTTPException(409, f"Rolle {payload.name!r} existiert bereits.")
    role = models.Role(name=payload.name, description=payload.description, is_system=False)
    db.add(role)
    db.flush()
    _set_permissions_by_codes(db, role, payload.permission_codes)
    audit_admin(db, action="role.created", actor=user.username,
                target_type="Role", target_id=role.id, ip=client_ip(request),
                payload={"name": role.name, "permissions": payload.permission_codes})
    db.commit()
    db.refresh(role)
    return role_to_out(role)


@router.patch("/roles/{role_id}", response_model=schemas.RoleOut)
def update_role(
    role_id: str,
    payload: schemas.RoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.roles.write")),
):
    role = db.get(models.Role, role_id)
    if not role:
        raise HTTPException(404, "Rolle nicht gefunden.")
    if role.is_system and payload.name and payload.name != role.name:
        raise HTTPException(409, "System-Rolle kann nicht umbenannt werden.")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(role, k, v)
    audit_admin(db, action="role.updated", actor=user.username,
                target_type="Role", target_id=role.id, ip=client_ip(request),
                payload=changes)
    db.commit()
    db.refresh(role)
    return role_to_out(role)


@router.delete("/roles/{role_id}", status_code=204)
def delete_role(
    role_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.roles.write")),
):
    role = db.get(models.Role, role_id)
    if not role:
        raise HTTPException(404, "Rolle nicht gefunden.")
    if role.is_system:
        raise HTTPException(409, "System-Rolle kann nicht geloescht werden.")
    in_use = db.scalar(
        select(models.UserRole.user_id).where(models.UserRole.role_id == role.id).limit(1)
    )
    if in_use:
        raise HTTPException(409, "Rolle ist noch zugewiesen — bitte zuerst von Usern entfernen.")
    audit_admin(db, action="role.deleted", actor=user.username,
                target_type="Role", target_id=role.id, ip=client_ip(request),
                payload={"name": role.name})
    db.delete(role)
    db.commit()


@router.put("/roles/{role_id}/permissions", response_model=schemas.RoleOut)
def set_permissions(
    role_id: str,
    payload: schemas.RolePermissionsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("admin.roles.write")),
):
    role = db.get(models.Role, role_id)
    if not role:
        raise HTTPException(404, "Rolle nicht gefunden.")

    # Lockout-Schutz: wir duerfen 'admin.users.write' nicht von der letzten
    # Rolle entfernen, die sie tragen.
    if "admin.users.write" not in payload.permission_codes:
        was_carrier = any(p.code == "admin.users.write" for p in role.permissions)
        if was_carrier:
            other = db.execute(
                select(models.Role.id)
                .join(models.RolePermission, models.RolePermission.role_id == models.Role.id)
                .join(models.Permission, models.Permission.id == models.RolePermission.permission_id)
                .where(models.Permission.code == "admin.users.write", models.Role.id != role.id)
                .limit(1)
            ).first()
            if not other:
                raise HTTPException(
                    409,
                    "Letzte Rolle mit 'admin.users.write' kann diese Permission nicht verlieren.",
                )

    _set_permissions_by_codes(db, role, payload.permission_codes)
    audit_admin(db, action="role.permissions_set", actor=user.username,
                target_type="Role", target_id=role.id, ip=client_ip(request),
                payload={"permissions": sorted(payload.permission_codes)})
    db.commit()
    db.refresh(role)
    return role_to_out(role)


def _set_permissions_by_codes(db: Session, role: models.Role, codes: list[str]) -> None:
    desired_codes = list(dict.fromkeys(codes))
    perms = list(db.scalars(
        select(models.Permission).where(models.Permission.code.in_(desired_codes))
    ).all())
    found = {p.code for p in perms}
    missing = set(desired_codes) - found
    if missing:
        raise HTTPException(400, f"Unbekannte Permissions: {sorted(missing)}")
    db.query(models.RolePermission).filter(models.RolePermission.role_id == role.id).delete()
    db.flush()
    for p in perms:
        db.add(models.RolePermission(role_id=role.id, permission_id=p.id))
    db.flush()
