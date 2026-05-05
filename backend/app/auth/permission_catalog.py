"""Single Source of Truth fuer alle Permission-Codes.

Jeder Eintrag = (code, area, description). Beim App-Start werden die Eintraege
idempotent in die `permissions`-Tabelle ge-upsertet, damit das Hinzufuegen
einer Permission nur eine Code-Aenderung ist (ohne neue Migration).
"""
from __future__ import annotations

from typing import NamedTuple


class PermissionDef(NamedTuple):
    code: str
    area: str
    description: str


# Reihenfolge folgt der Sidebar-Struktur des Admin-Panels.
PERMISSIONS: list[PermissionDef] = [
    # User-Verwaltung
    PermissionDef("admin.users.read", "admin.users", "User auflisten und ansehen"),
    PermissionDef("admin.users.write", "admin.users", "Lokale User anlegen, bearbeiten, deaktivieren"),
    PermissionDef("admin.users.assign_roles", "admin.users", "Rollen einem User zuweisen"),

    # Rollen & Permission-Katalog
    PermissionDef("admin.roles.read", "admin.roles", "Rollen und ihre Permissions ansehen"),
    PermissionDef("admin.roles.write", "admin.roles", "Rollen anlegen, bearbeiten, loeschen, Permissions zuweisen"),
    PermissionDef("admin.permissions.read", "admin.permissions", "Permission-Katalog ansehen"),

    # LDAP
    PermissionDef("admin.ldap.read", "admin.ldap", "LDAP-Konfiguration ansehen (Passwoerter maskiert)"),
    PermissionDef("admin.ldap.write", "admin.ldap", "LDAP-Konfiguration und Group-Mapping aendern"),
    PermissionDef("admin.ldap.test", "admin.ldap", "Test-Bind und Test-Suche gegen LDAP ausfuehren"),
    PermissionDef("admin.ldap.sync", "admin.ldap", "LDAP-Bulk-Sync starten und Status abfragen"),

    # SMTP
    PermissionDef("admin.smtp.read", "admin.smtp", "SMTP-Konfiguration ansehen (Passwort maskiert)"),
    PermissionDef("admin.smtp.write", "admin.smtp", "SMTP-Konfiguration aendern"),
    PermissionDef("admin.smtp.test", "admin.smtp", "Test-Mail versenden"),

    # Notifications
    PermissionDef("admin.notifications.templates.read", "admin.notifications", "E-Mail-Templates ansehen"),
    PermissionDef("admin.notifications.templates.write", "admin.notifications", "E-Mail-Templates bearbeiten"),
    PermissionDef("admin.notifications.role_emails.read", "admin.notifications", "Rollen-E-Mail-Mapping ansehen"),
    PermissionDef("admin.notifications.role_emails.write", "admin.notifications", "Rollen-E-Mail-Mapping bearbeiten"),

    # Eskalation / SLA-Scheduler
    PermissionDef("admin.escalation.read", "admin.escalation", "Eskalations-Konfiguration ansehen"),
    PermissionDef("admin.escalation.write", "admin.escalation", "Eskalations-Konfiguration aendern"),
    PermissionDef("admin.escalation.run_now", "admin.escalation", "Eskalations-Scan sofort ausfuehren"),

    # Audit
    PermissionDef("admin.audit.read", "admin.audit", "Audit-Log einsehen"),

    # System
    PermissionDef("admin.system.read", "admin.system", "System-Status und Diagnostik einsehen"),
    PermissionDef("admin.system.rekey", "admin.system", "Sensitive Werte mit aktuellem Schluessel re-encrypten"),

    # Auth-Mode
    PermissionDef("admin.auth_mode.read", "admin.auth_mode", "Aktuellen Auth-Modus einsehen"),
    PermissionDef("admin.auth_mode.write", "admin.auth_mode", "Auth-Modus zur Laufzeit aendern"),

    # Reporting-API-Tokens
    PermissionDef("admin.api_tokens.read", "admin.api_tokens", "Reporting-Tokens auflisten"),
    PermissionDef("admin.api_tokens.write", "admin.api_tokens", "Reporting-Tokens anlegen und widerrufen"),

    # Workflow-Definitionen
    PermissionDef("definitions.read", "definitions", "Form-Definitionen auflisten"),
    PermissionDef("definitions.upload", "definitions", "Neue Definition als Draft hochladen"),
    PermissionDef("definitions.activate", "definitions", "Definition aktivieren"),
    PermissionDef("definitions.retire", "definitions", "Definition zurueckziehen"),
    PermissionDef("definitions.diff", "definitions", "Schemas zweier Definitionen vergleichen"),

    # Antraege (Form-Instanzen)
    PermissionDef("instances.create", "instances", "Neuen Antrag anlegen"),
    PermissionDef("instances.read", "instances", "Antraege einsehen"),
    PermissionDef("instances.decide", "instances", "Antrag genehmigen oder ablehnen"),
    PermissionDef("instances.return", "instances", "Antrag zur Ueberarbeitung zurueckgeben"),
    PermissionDef("instances.reporting", "instances", "/reporting-Endpunkte nutzen"),
]


# Default-Permission-Sets pro fachlicher Default-Rolle.
# 'Admin' bekommt automatisch alle Permissions (siehe bootstrap.ensure_admin_role).
DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "Vorstand": [
        "definitions.read",
        "instances.read", "instances.decide", "instances.return",
    ],
    "Compliance": [
        "definitions.read",
        "instances.read", "instances.decide", "instances.return",
    ],
    "Risikomanagement": [
        "definitions.read",
        "instances.read", "instances.decide", "instances.return",
    ],
    "Fachbereichsleiter": [
        "definitions.read",
        "instances.create", "instances.read", "instances.decide", "instances.return",
    ],
    "Bereichsleiter": [
        "definitions.read",
        "instances.read", "instances.decide", "instances.return",
    ],
    "Vorstandssekretariat": [
        "definitions.read",
        "instances.read",
    ],
}


def all_codes() -> list[str]:
    return [p.code for p in PERMISSIONS]
