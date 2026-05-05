"""Auth-Modul: LDAP-Bind + lokaler Fallback + JWT-Token.

Oeffentliche API:

    from app.auth.dependencies import get_current_user, require_role
    from app.auth.router import router as auth_router

Konfiguration ueber Umgebungsvariablen (siehe app/auth/config.py).
"""
