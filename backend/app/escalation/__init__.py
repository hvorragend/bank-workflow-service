"""SLA-Eskalation: Hintergrund-Scanner, der offene Antraege auf
Stage-Verweildauer prueft und ggf. Mahn-/Eskalations-Mails ausloest.

Konfiguration:
- ESCALATION_ENABLED         : Default False (Tests/Quickstart bleiben unbeeinflusst)
- ESCALATION_DEFAULT_SLA_DAYS: Default-SLA-Tage, wenn die Stage kein sla_days hat (14)
- ESCALATION_INTERVAL_MINUTES: Wie oft der Scanner laeuft (Default 60)
- ESCALATION_BEREICHSLEITER_ROLE: Rolle, an die nach SLA-Ablauf eskaliert wird

Pro Stage in workflow_stages kann das SLA explizit gesetzt werden:

    {"name": "vorstand", "rolle": "Vorstand", "sla_days": 14}
"""
