"""DB-gestuetzte LDAP-Konfiguration. Loest die alte file-basierte LdapConfig
aus auth/config.py ab. Sensible Felder werden bei Bedarf entschluesselt.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..security import secrets


@dataclass
class LdapSettings:
    """Typisierter Snapshot der aktuellen LDAP-Konfiguration plus Group->Role-Mapping.

    Felder spiegeln die Spalten von models.LdapConfig wider, plus die aufgeloeste
    role_mapping (group_dn -> [role_name, ...]). service_account_password ist
    entschluesselt; ca_cert_pem bleibt im Klartext (PEM ist nicht geheim).
    """
    enabled: bool = False
    server: str = ""
    bind_user_template: str = ""
    search_base: str = ""
    group_search_base: str = ""
    group_filter: str = "(member={user_dn})"
    tls_required: bool = True
    ca_cert_pem: str | None = None
    timeout_seconds: int = 5
    service_account_dn: str | None = None
    service_account_password: str | None = None
    user_filter: str = "(uid={username})"
    attr_username: str = "uid"
    attr_display_name: str = "displayName"
    attr_email: str = "mail"
    role_mapping: dict[str, list[str]] = field(default_factory=dict)


def get_ldap_settings(db: Session) -> LdapSettings:
    cfg = db.get(models.LdapConfig, 1)
    if cfg is None:
        # Sollte durch bootstrap.ensure_singleton_configs nie passieren —
        # robust trotzdem mit Defaults antworten.
        return LdapSettings()

    role_mapping: dict[str, list[str]] = {}
    rows = db.execute(
        select(models.LdapRoleMapping.group_dn, models.Role.name)
        .join(models.Role, models.Role.id == models.LdapRoleMapping.role_id)
    ).all()
    for group_dn, role_name in rows:
        role_mapping.setdefault(group_dn, []).append(role_name)

    return LdapSettings(
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
        service_account_password=secrets.decrypt(cfg.service_account_pw_enc),
        user_filter=cfg.user_filter,
        attr_username=cfg.attr_username,
        attr_display_name=cfg.attr_display_name,
        attr_email=cfg.attr_email,
        role_mapping=role_mapping,
    )
