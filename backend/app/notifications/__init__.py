"""Notifications-Modul.

Hooks aus dem Workflow rufen `notify_stage_transition()` mit dem aktuellen
Antrag-Zustand. Empfaenger-Aufloesung und Versand laufen asynchron via
FastAPI BackgroundTasks, damit HTTP-Antworten nicht warten.

Konfiguration ueber Env-Vars (siehe app/auth/config.py).
Empfaenger-Mapping ueber config/role_emails.toml (optional).
"""
