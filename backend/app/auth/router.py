"""Auth-Endpunkte: /auth/login, /auth/logout, /auth/refresh, /auth/me."""
from __future__ import annotations

import logging
from datetime import datetime

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .config import get_settings
from .dependencies import get_current_user
from .jwt_handler import decode_token, issue_access_token, issue_refresh_token
from .rate_limit import limiter
from .ldap_bind import (
    LdapBadCredentials,
    LdapServerUnreachable,
    LdapUserUnknown,
    authenticate_ldap,
)
from .local import LocalAuthError, authenticate_local, is_local_user
from .schemas import AuthenticatedUser, LoginRequest, MeResponse, TokenResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, refresh_token: str, max_age: int) -> None:
    s = get_settings()
    response.set_cookie(
        key=s.refresh_cookie_name,
        value=refresh_token,
        max_age=max_age,
        httponly=True,
        secure=s.refresh_cookie_secure,
        samesite="lax",
        path="/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(s.refresh_cookie_name, path="/auth")


def _audit(action: str, username: str, source: str, ip: str, success: bool, reason: str = "") -> None:
    """Strukturierter Auth-Audit-Eintrag — separates Logger-Topic."""
    audit_log = logging.getLogger("auth.audit")
    audit_log.info(
        "auth_event",
        extra={
            "auth_action": action,
            "auth_username": username,
            "auth_source": source,
            "auth_ip": ip,
            "auth_success": success,
            "auth_reason": reason,
        },
    )


def _try_authenticate(username: str, password: str) -> AuthenticatedUser:
    """Implementiert das AUTH_MODE-Verhalten (local | ldap | both).

    Bei 'both': erst LDAP, Fallback auf Local NUR wenn Server unerreichbar
    oder User dort unbekannt — niemals bei „Passwort falsch" gegen LDAP.
    """
    s = get_settings()
    mode = s.auth_mode

    if mode == "local":
        return authenticate_local(username, password)

    if mode == "ldap":
        try:
            return authenticate_ldap(username, password)
        except LdapBadCredentials as e:
            raise LocalAuthError(str(e)) from e
        except (LdapServerUnreachable, LdapUserUnknown) as e:
            raise LocalAuthError(f"LDAP-Login nicht moeglich: {e}") from e

    # mode == "both"
    try:
        return authenticate_ldap(username, password)
    except LdapBadCredentials as e:
        # Wichtig: KEIN Fallback. Sonst Credential-Stuffing-Risiko.
        raise LocalAuthError(str(e)) from e
    except (LdapServerUnreachable, LdapUserUnknown) as ldap_err:
        log.info("LDAP nicht verfuegbar, Fallback auf Local: %s", ldap_err)
        if is_local_user(username):
            return authenticate_local(username, password)
        raise LocalAuthError("User unbekannt (LDAP und Local).") from ldap_err


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(payload: LoginRequest, request: Request, response: Response) -> TokenResponse:
    """Login mit Username/Passwort. Rate-Limit: 5 Versuche pro Minute pro IP."""
    ip = get_remote_address(request)
    try:
        user = _try_authenticate(payload.username, payload.password)
    except LocalAuthError as e:
        _audit("login", payload.username, "?", ip, success=False, reason=str(e))
        # Bewusst generische Fehlermeldung — keine Hinweise, ob User existiert.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Anmeldedaten ungueltig.",
        ) from None

    access_token, access_seconds = issue_access_token(user)
    refresh_token, refresh_seconds = issue_refresh_token(user)
    _set_refresh_cookie(response, refresh_token, refresh_seconds)
    _audit("login", user.username, user.auth_source, ip, success=True)
    return TokenResponse(access_token=access_token, expires_in=access_seconds)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    bws_refresh: str | None = Cookie(default=None),
) -> TokenResponse:
    """Tauscht den Refresh-Cookie gegen einen neuen Access-Token. Rotiert dabei den Cookie."""
    ip = get_remote_address(request)
    if not bws_refresh:
        _audit("refresh", "?", "?", ip, success=False, reason="Kein Refresh-Cookie.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Keine aktive Session."
        )

    try:
        user, _ = decode_token(bws_refresh, expected_type="refresh")
    except jwt.PyJWTError as e:
        _audit("refresh", "?", "?", ip, success=False, reason=str(e))
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh-Token ungueltig."
        ) from None

    access_token, access_seconds = issue_access_token(user)
    new_refresh, refresh_seconds = issue_refresh_token(user)
    _set_refresh_cookie(response, new_refresh, refresh_seconds)
    _audit("refresh", user.username, user.auth_source, ip, success=True)
    return TokenResponse(access_token=access_token, expires_in=access_seconds)


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, str]:
    """Loescht den Refresh-Cookie. Phase 1: keine serverseitige Token-Blacklist."""
    ip = get_remote_address(request)
    _clear_refresh_cookie(response)
    _audit("logout", "?", "?", ip, success=True)
    return {"status": "abgemeldet"}


@router.get("/me", response_model=MeResponse)
def me(user: AuthenticatedUser = Depends(get_current_user)) -> MeResponse:
    """Aktuell eingeloggte Identitaet plus Token-Ablauf."""
    # Wir kennen exp aus dem Token via decode_token; hier rekonstruieren wir es.
    # Alternativ koennte get_current_user exp mitgeben — pragmatisch lassen
    # wir die Lifetime auf Settings basieren, das ist fuer UX gut genug.
    s = get_settings()
    from datetime import timedelta, timezone
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.jwt_access_lifetime_minutes)
    return MeResponse(
        username=user.username,
        name=user.name,
        email=user.email,
        roles=user.roles,
        auth_source=user.auth_source,
        token_expires_at=exp,
    )


def custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Saubere 429-Antwort mit Retry-Hint."""
    return Response(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content='{"detail":"Zu viele Login-Versuche. Bitte spaeter erneut versuchen."}',
        media_type="application/json",
        headers={"Retry-After": "60"},
    )
