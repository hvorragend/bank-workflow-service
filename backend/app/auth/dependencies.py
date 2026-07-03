"""FastAPI-Dependencies fuer geschuetzte Endpunkte.

    @router.post("/foo")
    def foo(user: AuthenticatedUser = Depends(get_current_user)):
        ...

    @router.post("/admin/users")
    def create_user(user: AuthenticatedUser = Depends(require_permission("admin.users.write"))):
        ...

`require_role` bleibt als Alias bestehen — uebersetzt einen Rollennamen
intern auf eine Permission-Pruefung gegen den JWT-Permissions-Claim, damit
nicht migrierte Aufrufer weiter funktionieren.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .jwt_handler import decode_token
from .schemas import AuthenticatedUser

log = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthenticatedUser:
    """Validiert das Bearer-Access-Token und gibt den eingeloggten User zurueck.

    401 bei fehlendem oder ungueltigem Token.
    """
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentifizierung erforderlich.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user, _ = decode_token(creds.credentials, expected_type="access")
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token abgelaufen.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Ungueltiges Token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return user


def require_permission(*required: str) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Dependency-Factory: User braucht mindestens eine der genannten Permissions
    (any-of-Semantik). Permissions stehen im JWT-Claim 'permissions', der beim
    Login aus den Rollen aufgeloest wird.
    """
    needed = set(required)

    def _check(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not needed.intersection(user.permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Erforderliche Permission nicht vorhanden. Benoetigt (eine davon): "
                    f"{sorted(needed)}."
                ),
            )
        return user

    return _check


def require_role(*required: str) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Backwards-Compat-Wrapper: pruefen anhand des roles-Claim. Neue Endpunkte
    sollten require_permission verwenden.
    """
    needed = set(required)

    def _check(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not needed.intersection(user.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Erforderliche Rolle nicht vorhanden. Benoetigt: {sorted(needed)}, "
                    f"vorhanden: {sorted(user.roles)}."
                ),
            )
        return user

    return _check
