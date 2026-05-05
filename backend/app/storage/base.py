"""Abstrakte Storage-Schnittstelle. Implementierungen liegen unter app/storage/{provider}.py."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator


class StorageBackend(ABC):
    """Minimal-API fuer das Storage-Backend.

    Keys sind opake Strings (typisch <sha256>). Implementierungen muessen idempotent
    sein — `put` mit demselben Key zweimal aufzurufen darf den Inhalt nicht
    aendern (wir verwenden den SHA-256 als Key, also ist Inhalt = Key).
    """

    @abstractmethod
    def put(self, key: str, data: bytes) -> None:
        """Schreibt Bytes unter dem Key. Wenn der Key existiert, ist das ein No-op."""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Liest die Bytes. KeyError, wenn nicht vorhanden."""

    @abstractmethod
    def stream(self, key: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        """Liefert die Bytes in Chunks fuer Streaming-Antworten."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Loescht den Key, wenn er existiert. Idempotent."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...
