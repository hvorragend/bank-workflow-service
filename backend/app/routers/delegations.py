"""Abwesenheits-Vertretungen (N-001) — Self-Service.

Jeder angemeldete Nutzer verwaltet seine EIGENEN Vertretungen: waehrend des
gepflegten Zeitraums erhaelt der benannte Vertreter zusaetzlich die Rollen-
Benachrichtigungen des Abwesenden.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..auth.dependencies import get_current_user
from ..auth.schemas import AuthenticatedUser
from ..database import get_db

router = APIRouter(prefix="/delegations", tags=["delegations"])


class DelegationCreate(BaseModel):
    to_username: str
    von_datum: date
    bis_datum: date


class DelegationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    from_username: str
    to_username: str
    von_datum: date
    bis_datum: date
    created_at: datetime


def _serialize(d: models.Delegation) -> DelegationOut:
    return DelegationOut.model_validate(d)


@router.get("", response_model=list[DelegationOut])
def list_own_delegations(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
):
    rows = db.scalars(
        select(models.Delegation)
        .where(models.Delegation.from_username == user.username)
        .order_by(models.Delegation.von_datum.desc())
    ).all()
    return [_serialize(d) for d in rows]


@router.post("", response_model=DelegationOut, status_code=201)
def create_delegation(
    payload: DelegationCreate,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
):
    if payload.to_username == user.username:
        raise HTTPException(400, "Man kann sich nicht selbst vertreten.")
    if payload.bis_datum < payload.von_datum:
        raise HTTPException(400, "Das Enddatum darf nicht vor dem Startdatum liegen.")
    target = db.scalar(
        select(models.User).where(models.User.username == payload.to_username)
    )
    if not target or not target.is_active:
        raise HTTPException(400, f"Vertreter {payload.to_username!r} ist kein aktiver Nutzer.")

    deleg = models.Delegation(
        from_username=user.username,
        to_username=payload.to_username,
        von_datum=payload.von_datum,
        bis_datum=payload.bis_datum,
        created_at=datetime.now(UTC),
    )
    db.add(deleg)
    db.commit()
    db.refresh(deleg)
    return _serialize(deleg)


@router.delete("/{delegation_id}", status_code=204)
def delete_delegation(
    delegation_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
):
    deleg = db.get(models.Delegation, delegation_id)
    if not deleg or deleg.from_username != user.username:
        # Kein Information-Leak ueber fremde Vertretungen.
        raise HTTPException(404, "Vertretung nicht gefunden.")
    db.delete(deleg)
    db.commit()
