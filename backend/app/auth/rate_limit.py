"""Geteilter slowapi-Limiter, damit Decorator und App-Setup denselben Zaehler nutzen."""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Pro IP. In Produktion hinter Reverse-Proxy: X-Forwarded-For muss vom Proxy
# zuverlaessig gesetzt werden, sonst zaehlen alle Requests gegen die Proxy-IP.
limiter = Limiter(key_func=get_remote_address)
