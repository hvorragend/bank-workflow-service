"""Sammel-Mount fuer alle Admin-Sub-Router. Wird von main.py inkludiert."""
from __future__ import annotations

from fastapi import APIRouter

from . import (
    audit_router,
    auth_mode_router,
    definitions_router,
    escalation_router,
    ldap_router,
    notifications_router,
    roles_router,
    system_router,
    users_router,
)

router = APIRouter()
router.include_router(definitions_router.router)
router.include_router(audit_router.router)
router.include_router(users_router.router)
router.include_router(roles_router.router)
router.include_router(auth_mode_router.router)
router.include_router(ldap_router.router)
router.include_router(notifications_router.router)
router.include_router(escalation_router.router)
router.include_router(system_router.router)
