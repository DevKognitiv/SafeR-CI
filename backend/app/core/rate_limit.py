"""
SafeR CI — Rate limiting

Shared slowapi limiter, keyed by client IP. Imported by ``main.py`` (to wire the
limiter and its exception handler into the app) and by the route modules (to
decorate individual endpoints such as incident-create and the HA webhook).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
