"""CLI-Hilfsskript: erzeugt einen argon2id-Hash fuer config/users.json.

    python -m app.auth.hash_password

Liest das Passwort interaktiv ein (echo aus), gibt den Hash auf stdout aus.
Speichert nichts auf der Disk.
"""
from __future__ import annotations

import getpass
import sys

from argon2 import PasswordHasher


def main() -> int:
    pw1 = getpass.getpass("Passwort: ")
    pw2 = getpass.getpass("Wiederholen: ")
    if pw1 != pw2:
        print("Passwoerter stimmen nicht ueberein.", file=sys.stderr)
        return 1
    if len(pw1) < 8:
        print("Mindestens 8 Zeichen.", file=sys.stderr)
        return 1
    print(PasswordHasher().hash(pw1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
