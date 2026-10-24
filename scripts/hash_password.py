"""Génère la valeur de PAIE_AUTH_PASSWORD_HASH à placer dans le fichier .env.

    python scripts/hash_password.py
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.auth import hash_password  # noqa: E402


def main() -> None:
    password = getpass.getpass("Mot de passe (10 caractères minimum) : ")
    if password != getpass.getpass("Confirmation : "):
        sys.exit("Les deux saisies diffèrent.")
    print(f"PAIE_AUTH_PASSWORD_HASH={hash_password(password)}")


if __name__ == "__main__":
    main()
