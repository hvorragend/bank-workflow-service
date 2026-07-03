"""LDAP-Bulk-Sync: zieht alle User aus dem konfigurierten search_base in die
users-Tabelle und mappt deren Gruppen auf Rollen.

Ablauf:
- Service-Account-Bind (cfg.service_account_dn + entschluesseltes Passwort)
- Paged-Search ueber search_base mit user_filter (oder '(objectClass=person)')
- Pro User: upsert in users-Tabelle, Roles aus Gruppen ableiten

Status-Tracking ueber eine prozessweite JOBS-Registry, abrufbar ueber
GET /admin/ldap/sync/{job_id}. Jobs werden im Hintergrund (Thread oder
FastAPI BackgroundTasks) gestartet, der Endpoint kehrt sofort zurueck.
"""
from __future__ import annotations

import logging
import ssl
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ldap3 import ALL, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config_service.ldap_settings import LdapSettings, get_ldap_settings
from ..database import SessionLocal

log = logging.getLogger("ldap.sync")


@dataclass
class SyncJob:
    id: str
    status: str = "queued"  # queued | running | finished | error
    started_at: datetime | None = None
    finished_at: datetime | None = None
    counts: dict[str, int] = field(default_factory=lambda: {
        "scanned": 0, "created": 0, "updated": 0, "deactivated": 0, "errors": 0,
    })
    error: str | None = None
    dry_run: bool = False


_JOBS: dict[str, SyncJob] = {}
_LOCK = threading.Lock()


def list_jobs() -> list[SyncJob]:
    with _LOCK:
        return list(_JOBS.values())


def get_job(job_id: str) -> SyncJob | None:
    with _LOCK:
        return _JOBS.get(job_id)


def start_sync_job(*, dry_run: bool = False, actor: str = "system") -> SyncJob:
    """Erzeugt einen Job und startet ihn im Daemon-Thread. Sofortige Rueckgabe."""
    job = SyncJob(id=str(uuid.uuid4()), dry_run=dry_run)
    with _LOCK:
        _JOBS[job.id] = job
    t = threading.Thread(target=_run_sync, args=(job, actor), daemon=True,
                         name=f"ldap-sync-{job.id[:8]}")
    t.start()
    return job


def _run_sync(job: SyncJob, actor: str) -> None:
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    try:
        with SessionLocal() as db:
            cfg = get_ldap_settings(db)
            if not cfg.enabled or not cfg.server or not cfg.service_account_dn:
                raise RuntimeError("LDAP nicht konfiguriert (enabled, server, service_account_dn).")
            counts = _do_sync(db, cfg, job)
            job.counts.update(counts)
        job.status = "finished"
    except Exception as e:  # noqa: BLE001
        log.exception("LDAP-Sync %s fehlgeschlagen: %s", job.id, e)
        job.error = str(e)
        job.status = "error"
    finally:
        job.finished_at = datetime.now(timezone.utc)


def _do_sync(db: Session, cfg: LdapSettings, job: SyncJob) -> dict[str, int]:
    counts = {"scanned": 0, "created": 0, "updated": 0, "deactivated": 0, "errors": 0}
    tls, ca_path = _build_tls(cfg)
    try:
        server = Server(cfg.server, get_info=ALL, tls=tls, connect_timeout=cfg.timeout_seconds)
        with Connection(
            server,
            user=cfg.service_account_dn,
            password=cfg.service_account_password or "",
            auto_bind=True,
        ) as conn:
            # Alle User-Eintraege im search_base.
            if not cfg.search_base:
                raise RuntimeError("search_base ist leer — kein Sync moeglich.")
            page_size = 500
            gen = conn.extend.standard.paged_search(
                search_base=cfg.search_base,
                search_filter=cfg.user_filter.replace("{username}", "*") or "(objectClass=person)",
                search_scope=SUBTREE,
                attributes=[cfg.attr_username, cfg.attr_display_name, cfg.attr_email],
                paged_size=page_size,
                generator=True,
            )
            role_id_by_name: dict[str, str] = {
                r.name: r.id for r in db.scalars(select(models.Role)).all()
            }
            for entry in gen:
                if entry.get("type") != "searchResEntry":
                    continue
                counts["scanned"] += 1
                attrs = entry.get("attributes", {})
                username = _attr_str(attrs, cfg.attr_username)
                if not username:
                    continue
                display_name = _attr_str(attrs, cfg.attr_display_name) or username
                email = _attr_str(attrs, cfg.attr_email)
                user_dn = entry.get("dn") or ""
                try:
                    # Gruppen pro User abfragen
                    group_dns = _lookup_user_groups(conn, cfg, user_dn)
                    role_names: set[str] = set()
                    for dn in group_dns:
                        for r in cfg.role_mapping.get(dn, []):
                            role_names.add(r)
                    if job.dry_run:
                        continue
                    created = _upsert_user(db, role_id_by_name, username, display_name, email,
                                           user_dn, sorted(role_names))
                    if created:
                        counts["created"] += 1
                    else:
                        counts["updated"] += 1
                except Exception as e:  # noqa: BLE001
                    log.warning("Fehler beim Sync von %s: %s", username, e)
                    counts["errors"] += 1
            if not job.dry_run:
                db.commit()
        return counts
    finally:
        # F-043: CA-PEM-Tempdatei nach dem Sync-Bind wieder entfernen.
        if ca_path:
            Path(ca_path).unlink(missing_ok=True)


def _build_tls(cfg: LdapSettings) -> tuple[Tls | None, str | None]:
    """Wie in ldap_bind: gibt zusaetzlich den Pfad der ggf. erzeugten CA-PEM-
    Tempdatei zurueck, damit der Aufrufer sie nach Gebrauch loeschen kann (F-043)."""
    if not cfg.server.startswith("ldaps://"):
        return None, None
    if cfg.ca_cert_pem:
        f = tempfile.NamedTemporaryFile(prefix="bws-ldap-ca-", suffix=".pem", delete=False)
        try:
            f.write(cfg.ca_cert_pem.encode("utf-8"))
            f.flush()
            ca_path = f.name
        finally:
            f.close()
        return Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=ca_path), ca_path
    return Tls(validate=ssl.CERT_REQUIRED), None


def _lookup_user_groups(conn: Connection, cfg: LdapSettings, user_dn: str) -> list[str]:
    if not cfg.group_search_base or not cfg.group_filter:
        return []
    # F-021: user_dn stammt aus dem LDAP-Eintrag, wird aber in einen Suchfilter
    # eingesetzt -> escape_filter_chars gegen Filter-Injection.
    flt = cfg.group_filter.format(user_dn=escape_filter_chars(user_dn))
    try:
        conn.search(cfg.group_search_base, flt, search_scope=SUBTREE, attributes=["dn"])
    except LDAPException:
        return []
    return [str(e.entry_dn) for e in conn.entries]


def _attr_str(attrs: dict[str, Any], key: str) -> str:
    v = attrs.get(key)
    if v is None:
        return ""
    if isinstance(v, list) and v:
        v = v[0]
    return str(v)


def _upsert_user(
    db: Session,
    role_id_by_name: dict[str, str],
    username: str,
    display_name: str,
    email: str,
    user_dn: str,
    role_names: list[str],
) -> bool:
    """True wenn neu angelegt, False wenn aktualisiert."""
    user = db.scalar(select(models.User).where(models.User.username == username))
    is_new = user is None
    if user is None:
        user = models.User(
            username=username,
            display_name=display_name,
            email=email or None,
            auth_source="ldap",
            is_active=True,
            ldap_dn=user_dn,
        )
        db.add(user)
        db.flush()
    else:
        user.display_name = display_name or user.display_name
        if email:
            user.email = email
        user.ldap_dn = user_dn
        user.auth_source = "ldap"
        user.is_active = True

    # Rollen synchronisieren: ersetze die LDAP-zugewiesenen Rollen vollstaendig.
    desired_role_ids = {role_id_by_name[r] for r in role_names if r in role_id_by_name}
    existing_links = list(db.scalars(
        select(models.UserRole).where(models.UserRole.user_id == user.id)
    ).all())
    existing_ids = {link.role_id for link in existing_links}
    for link in existing_links:
        if link.role_id not in desired_role_ids:
            db.delete(link)
    for rid in desired_role_ids - existing_ids:
        db.add(models.UserRole(user_id=user.id, role_id=rid))
    return is_new


def upsert_ldap_user_after_login(
    db: Session,
    *,
    username: str,
    display_name: str,
    email: str,
    user_dn: str,
    role_names: list[str],
) -> None:
    """Wird beim erfolgreichen LDAP-Login aufgerufen. Idempotent."""
    role_id_by_name: dict[str, str] = {
        r.name: r.id for r in db.scalars(select(models.Role)).all()
    }
    _upsert_user(db, role_id_by_name, username, display_name, email, user_dn, role_names)
    db.commit()
