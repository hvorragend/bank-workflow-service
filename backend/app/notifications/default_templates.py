"""Default-Bodies fuer die Notification-Templates.

Werden vom Bootstrap genutzt, um eine leere notification_templates-Tabelle zu
fuellen. In Produktion ueberschreibt der Admin sie ueber das Admin-Panel.

Variablen-Syntax: $varname (string.Template.safe_substitute) — bewusst kein
Jinja, damit Admins keinen ausfuehrbaren Code injizieren koennen.
"""
from __future__ import annotations

DEFAULT_TEMPLATES: dict[str, tuple[str, str]] = {
    "stage_review_pending": (
        "[Bank Workflow] Antrag wartet auf $rolle-Entscheidung — $titel",
        "Sehr geehrte Empfaengerin, sehr geehrter Empfaenger,\n\n"
        "ein Antrag wartet jetzt auf eine Entscheidung in der Stage „$stage“:\n\n"
        "Titel:        $titel\n"
        "Maske:        $schema_version\n"
        "Antragsteller:$antragsteller\n"
        "Erstellt am:  $erstellt_am\n\n"
        "Direktlink:   $link\n\n"
        "Bitte oeffnen Sie den Antrag, pruefen Sie ihn fachlich und treffen Sie eine\n"
        "Entscheidung (genehmigen, zur Ueberarbeitung zurueckweisen, ablehnen).\n\n"
        "Diese Nachricht wurde automatisch vom Bank Workflow Service erzeugt.",
    ),
    "approved": (
        "[Bank Workflow] Genehmigt — $titel",
        "Hallo $antragsteller,\n\n"
        "dein Antrag wurde vollstaendig genehmigt:\n\n"
        "Titel:           $titel\n"
        "Maske:           $schema_version\n"
        "Abgeschlossen:   $abgeschlossen_am\n\n"
        "Direktlink:      $link\n\n"
        "Diese Nachricht wurde automatisch vom Bank Workflow Service erzeugt.",
    ),
    "rejected": (
        "[Bank Workflow] Abgelehnt — $titel",
        "Hallo $antragsteller,\n\n"
        "dein Antrag wurde von $rolle abgelehnt:\n\n"
        "Titel:        $titel\n"
        "Maske:        $schema_version\n\n"
        "Begruendung:  $kommentar\n\n"
        "Direktlink:   $link\n\n"
        "Diese Nachricht wurde automatisch vom Bank Workflow Service erzeugt.",
    ),
    "returned": (
        "[Bank Workflow] Zur Ueberarbeitung — $titel",
        "Hallo $antragsteller,\n\n"
        "dein Antrag wurde von $rolle zur Ueberarbeitung zurueckgewiesen:\n\n"
        "Titel:        $titel\n"
        "Maske:        $schema_version\n\n"
        "Hinweis:      $kommentar\n\n"
        "Bitte ueberarbeite den Antrag und reiche ihn erneut ein:\n$link\n\n"
        "Diese Nachricht wurde automatisch vom Bank Workflow Service erzeugt.",
    ),
    "sla_erinnerung": (
        "[Bank Workflow] Erinnerung — wartet seit $age_days Tagen",
        "Erinnerung: der folgende Antrag wartet seit $age_days Tagen auf eine\n"
        "Entscheidung in der Stage '$stage'. Das halbe SLA ($half_sla Tage) ist erreicht.\n\n"
        "Titel:         $titel\n"
        "Antragsteller: $antragsteller\n"
        "Direktlink:    $link\n\n"
        "Bitte zeitnah pruefen — bei $sla Tagen ohne Entscheidung wird an\n"
        "den Bereichsleiter eskaliert.",
    ),
    "sla_eskalation": (
        "[Bank Workflow] ESKALATION — SLA ueberschritten",
        "ESKALATION: der folgende Antrag haengt seit $age_days Tagen in der\n"
        "Stage '$stage' — das SLA von $sla Tagen ist ueberschritten.\n\n"
        "Erforderliche Rolle: $rolle\n"
        "Titel:               $titel\n"
        "Antragsteller:       $antragsteller\n"
        "Direktlink:          $link\n\n"
        "Bitte greifen Sie ein — entweder direkt entscheiden, falls die Rolle\n"
        "das zulaesst, oder die zustaendige Person aktiv ansprechen.",
    ),
}
