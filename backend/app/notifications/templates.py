"""Plaintext-E-Mail-Templates fuer die vier Workflow-Ereignisse.

Bewusst kein HTML — robuster, freundlich zu Mailclients, kein XSS-Risiko.
Templates sind als f-string-faehige Funktionen geschrieben, damit sie
typgepruef sind und nicht von einer Template-Engine abhaengen.
"""
from __future__ import annotations

from datetime import datetime
from typing import TypedDict


class Email(TypedDict):
    subject: str
    body: str


def _antrag_titel(daten: dict) -> str:
    return (
        daten.get("vorhaben", {}).get("titel")
        or daten.get("beschluss", {}).get("titel")
        or "(ohne Titel)"
    )


def _antrag_link(app_url: str, instance_id: str) -> str:
    return f"{app_url.rstrip('/')}/antraege/{instance_id}"


def template_stage_review_pending(*,
    app_url: str,
    instance_id: str,
    daten: dict,
    schema_version: str,
    stage: str,
    rolle: str,
    antragsteller: str,
    erstellt_am: datetime,
) -> Email:
    """An die zur naechsten Stage gehoerende Rolle: bitte um Entscheidung."""
    return {
        "subject": f"[Bank Workflow] Antrag wartet auf {rolle}-Entscheidung — {_antrag_titel(daten)}",
        "body": f"""
Sehr geehrte Empfaengerin, sehr geehrter Empfaenger,

ein Antrag wartet jetzt auf eine Entscheidung in der Stage „{stage}":

Titel:        {_antrag_titel(daten)}
Maske:        {schema_version}
Antragsteller:{antragsteller}
Erstellt am:  {erstellt_am.strftime('%d.%m.%Y %H:%M')}

Direktlink:   {_antrag_link(app_url, instance_id)}

Bitte oeffnen Sie den Antrag, pruefen Sie ihn fachlich und treffen Sie eine
Entscheidung (genehmigen, zur Ueberarbeitung zurueckweisen, ablehnen).

Diese Nachricht wurde automatisch vom Bank Workflow Service erzeugt.
""".strip(),
    }


def template_approved(*,
    app_url: str,
    instance_id: str,
    daten: dict,
    schema_version: str,
    antragsteller: str,
    abgeschlossen_am: datetime | None,
) -> Email:
    """An den Antragsteller: dein Antrag ist genehmigt."""
    return {
        "subject": f"[Bank Workflow] Genehmigt — {_antrag_titel(daten)}",
        "body": f"""
Hallo {antragsteller},

dein Antrag wurde vollstaendig genehmigt:

Titel:           {_antrag_titel(daten)}
Maske:           {schema_version}
Abgeschlossen:   {abgeschlossen_am.strftime('%d.%m.%Y %H:%M') if abgeschlossen_am else '—'}

Direktlink:      {_antrag_link(app_url, instance_id)}

Diese Nachricht wurde automatisch vom Bank Workflow Service erzeugt.
""".strip(),
    }


def template_rejected(*,
    app_url: str,
    instance_id: str,
    daten: dict,
    schema_version: str,
    antragsteller: str,
    rolle: str,
    kommentar: str | None,
) -> Email:
    """An den Antragsteller: dein Antrag wurde abgelehnt."""
    return {
        "subject": f"[Bank Workflow] Abgelehnt — {_antrag_titel(daten)}",
        "body": f"""
Hallo {antragsteller},

dein Antrag wurde von {rolle} abgelehnt:

Titel:        {_antrag_titel(daten)}
Maske:        {schema_version}

Begruendung:  {kommentar or '— keine Begruendung —'}

Direktlink:   {_antrag_link(app_url, instance_id)}

Diese Nachricht wurde automatisch vom Bank Workflow Service erzeugt.
""".strip(),
    }


def template_returned(*,
    app_url: str,
    instance_id: str,
    daten: dict,
    schema_version: str,
    antragsteller: str,
    rolle: str,
    kommentar: str | None,
) -> Email:
    """An den Antragsteller: dein Antrag wurde zur Ueberarbeitung zurueckgewiesen."""
    return {
        "subject": f"[Bank Workflow] Zur Ueberarbeitung — {_antrag_titel(daten)}",
        "body": f"""
Hallo {antragsteller},

dein Antrag wurde von {rolle} zur Ueberarbeitung zurueckgewiesen:

Titel:        {_antrag_titel(daten)}
Maske:        {schema_version}

Hinweis:      {kommentar or '— kein Hinweis —'}

Bitte ueberarbeite den Antrag und reiche ihn erneut ein:
{_antrag_link(app_url, instance_id)}

Diese Nachricht wurde automatisch vom Bank Workflow Service erzeugt.
""".strip(),
    }
