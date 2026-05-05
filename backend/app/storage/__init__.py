"""Storage-Backend fuer Datei-Anhaenge.

Aktuell genau ein Backend (Filesystem). Die Schnittstelle ist abstrakt, sodass
spaeter MinIO/S3 oder NFS als Drop-in eingehaengt werden kann, ohne dass die
Antrags-Endpunkte etwas merken.

    from app.storage import get_storage
    storage = get_storage()
    storage.put(key, data, content_type)
    storage.get(key)
"""
from __future__ import annotations

import os
from functools import lru_cache

from .base import StorageBackend
from .filesystem import FilesystemStorageBackend


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    backend = os.getenv("STORAGE_BACKEND", "filesystem")
    if backend == "filesystem":
        root = os.getenv("STORAGE_ROOT", "./data/attachments")
        return FilesystemStorageBackend(root)
    raise RuntimeError(f"Unbekanntes Storage-Backend: {backend}")


def reset_storage_cache() -> None:
    """Fuer Tests."""
    get_storage.cache_clear()
