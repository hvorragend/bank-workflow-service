"""Filesystem-Storage. Schlanke Variante fuer Single-Host-Deployment.

Keys werden in zwei Ebenen gefaechert ('ab/cd1234…'), damit Verzeichnisse mit
hunderttausenden Eintraegen nicht degradieren.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .base import StorageBackend


class FilesystemStorageBackend(StorageBackend):
    def __init__(self, root: str | Path):
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _key_path(self, key: str) -> Path:
        # Annahme: key ist der SHA-256-Hex-String. Wir splitten auf 2 Ebenen.
        if len(key) < 4 or "/" in key or ".." in key:
            raise ValueError(f"Ungueltiger Storage-Key: {key!r}")
        return self._root / key[:2] / key[2:4] / key

    def put(self, key: str, data: bytes) -> None:
        path = self._key_path(key)
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        # atomic write: erst tmp, dann rename
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.rename(path)

    def get(self, key: str) -> bytes:
        path = self._key_path(key)
        if not path.exists():
            raise KeyError(key)
        return path.read_bytes()

    def stream(self, key: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        path = self._key_path(key)
        if not path.exists():
            raise KeyError(key)
        with path.open("rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    def delete(self, key: str) -> None:
        path = self._key_path(key)
        path.unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._key_path(key).exists()
