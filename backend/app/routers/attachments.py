"""Datei-Anhaenge an FormInstances.

POST   /instances/{id}/attachments         — Multipart-Upload, Whitelist + Groessenlimit
GET    /instances/{id}/attachments         — Metadaten-Liste
GET    /instances/{id}/attachments/{att}   — Download (Stream)
DELETE /instances/{id}/attachments/{att}   — nur erlaubt, solange Antrag im Status 'entwurf'
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, models
from ..auth.dependencies import get_current_user, require_permission
from ..auth.schemas import AuthenticatedUser
from ..database import get_db
from ..storage import get_storage
from .instances import _assert_can_view

router = APIRouter(prefix="/instances", tags=["attachments"])


def _safe_content_disposition(filename: str) -> str:
    """Baut einen Content-Disposition-Header ohne Header-Injection.

    Der Upload-Dateiname ist nutzerkontrolliert; Anfuehrungszeichen/CRLF/
    Steuerzeichen wuerden sonst den Header manipulieren (F-023). Wir liefern
    einen bereinigten ASCII-Fallback plus RFC-5987-`filename*` fuer Unicode.
    """
    from urllib.parse import quote

    ascii_fallback = "".join(
        c for c in filename if 32 <= ord(c) < 127 and c not in '"\\'
    ) or "download"
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


MAX_BYTES = int(os.getenv("ATTACHMENT_MAX_BYTES", str(25 * 1024 * 1024)))  # 25 MB Default

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "image/png",
    "image/jpeg",
}

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".docx", ".png", ".jpg", ".jpeg"}


def _ext(filename: str) -> str:
    _, ext = os.path.splitext(filename or "")
    return ext.lower()


@router.post("/{instance_id}/attachments", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    instance_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("instances.read")),
) -> dict:
    instance = db.get(models.FormInstance, instance_id)
    if not instance:
        raise HTTPException(404, "Antrag nicht gefunden.")
    _assert_can_view(user, instance)
    # Anhaenge nur waehrend Erfassung/Pruefung — an abgeschlossene Antraege
    # (genehmigt/abgelehnt) darf nichts mehr angehaengt werden, sonst bricht die
    # Unveraenderlichkeit der Audit-Spur (F-020).
    if instance.status not in ("entwurf", "in_pruefung"):
        raise HTTPException(
            409,
            f"An einen Antrag im Status '{instance.status}' koennen keine Anhaenge "
            "mehr hochgeladen werden.",
        )

    # Inhalt einlesen + groesse pruefen + sha256 berechnen.
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(400, "Leere Datei.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"Datei zu gross. Maximal {MAX_BYTES // (1024 * 1024)} MB erlaubt.")

    ext = _ext(file.filename or "")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, f"Dateiendung nicht erlaubt: {ext}. Erlaubt: {sorted(ALLOWED_EXTENSIONS)}")
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, f"Content-Type nicht erlaubt: {file.content_type}")

    sha = hashlib.sha256(data).hexdigest()

    # Im Storage-Backend ablegen (idempotent: gleicher Key = gleicher Inhalt).
    storage = get_storage()
    storage.put(sha, data)

    # Metadaten in DB persistieren.
    att = models.Attachment(
        id=str(uuid.uuid4()),
        instance_id=instance.id,
        filename=file.filename or f"unbenannt{ext}",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        sha256=sha,
        storage_key=sha,
        uploaded_by=user.username,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(att)
    audit.write_event(
        db,
        kategorie="instance",
        action="attachment.uploaded",
        akteur=user.username,
        target_type="FormInstance",
        target_id=instance.id,
        payload={"filename": att.filename, "size_bytes": att.size_bytes, "sha256": sha},
        commit=False,
    )
    db.commit()
    db.refresh(att)
    return _serialize(att)


@router.get("/{instance_id}/attachments")
def list_attachments(
    instance_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("instances.read")),
) -> list[dict]:
    instance = db.get(models.FormInstance, instance_id)
    if not instance:
        raise HTTPException(404, "Antrag nicht gefunden.")
    _assert_can_view(user, instance)
    rows = list(
        db.scalars(
            select(models.Attachment)
            .where(models.Attachment.instance_id == instance_id)
            .order_by(models.Attachment.uploaded_at.desc())
        ).all()
    )
    return [_serialize(a) for a in rows]


@router.get("/{instance_id}/attachments/{attachment_id}")
def download_attachment(
    instance_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("instances.read")),
):
    instance = db.get(models.FormInstance, instance_id)
    if not instance:
        raise HTTPException(404, "Antrag nicht gefunden.")
    _assert_can_view(user, instance)
    att = _get_attachment(db, instance_id, attachment_id)
    storage = get_storage()
    if not storage.exists(att.storage_key):
        raise HTTPException(410, "Datei nicht mehr im Storage. Bitte Admin informieren.")
    return StreamingResponse(
        storage.stream(att.storage_key),
        media_type=att.content_type,
        headers={
            "Content-Disposition": _safe_content_disposition(att.filename),
            # Verhindert MIME-Sniffing des Browsers auf hochgeladenen Inhalt.
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{instance_id}/attachments/{attachment_id}", status_code=204)
def delete_attachment(
    instance_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("instances.read")),
):
    instance = db.get(models.FormInstance, instance_id)
    if not instance:
        raise HTTPException(404, "Antrag nicht gefunden.")
    _assert_can_view(user, instance)
    att = _get_attachment(db, instance_id, attachment_id)
    # Nur im Entwurf darf geloescht werden — sobald der Antrag in Pruefung
    # geht, sind Anhaenge unveraendlicher Bestandteil der Audit-Spur.
    if instance.status != "entwurf":
        raise HTTPException(
            409,
            f"Anhaenge koennen nur im Entwurfsstatus geloescht werden (aktuell: {instance.status}).",
        )

    # Sind andere Attachments mit demselben Hash da? Dann Blob behalten.
    other = db.scalar(
        select(models.Attachment.id).where(
            models.Attachment.sha256 == att.sha256,
            models.Attachment.id != att.id,
        )
    )
    storage_key = att.storage_key
    delete_blob = other is None

    db.delete(att)
    audit.write_event(
        db,
        kategorie="instance",
        action="attachment.deleted",
        akteur=user.username,
        target_type="FormInstance",
        target_id=instance_id,
        payload={"filename": att.filename, "sha256": att.sha256},
        commit=False,
    )
    # Erst die DB-Aenderung festschreiben, DANN den Blob entfernen (F-020): faellt
    # der Commit aus, bleibt die Datei erhalten statt einer DB, die auf ein
    # geloeschtes Blob zeigt. Ein verwaistes Blob nach erfolgreichem Commit ist
    # dagegen harmlos (dedupliziertes, content-adressiertes Storage).
    db.commit()
    if delete_blob:
        get_storage().delete(storage_key)


def _get_attachment(db: Session, instance_id: str, attachment_id: str) -> models.Attachment:
    att = db.get(models.Attachment, attachment_id)
    if not att or att.instance_id != instance_id:
        raise HTTPException(404, "Anhang nicht gefunden.")
    return att


def _serialize(a: models.Attachment) -> dict:
    return {
        "id": a.id,
        "instance_id": a.instance_id,
        "filename": a.filename,
        "content_type": a.content_type,
        "size_bytes": a.size_bytes,
        "sha256": a.sha256,
        "uploaded_by": a.uploaded_by,
        "uploaded_at": a.uploaded_at,
    }
