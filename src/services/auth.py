"""Contrôle d'accès minimal par mot de passe partagé (PBKDF2-SHA256, bibliothèque standard).

Le hachage est fourni par la variable `PAIE_AUTH_PASSWORD_HASH` (voir
`scripts/hash_password.py`). Ce mécanisme ne remplace ni des comptes individuels, ni HTTPS,
ni un contrôle d'accès réseau : voir docs/DEPLOIEMENT.md.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    if len(password) < 10:
        raise ValueError("Le mot de passe doit contenir au moins 10 caractères.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join((ALGORITHM, str(iterations), base64.b64encode(salt).decode(),
                     base64.b64encode(digest).decode()))


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, digest = encoded.split("$")
        if algorithm != ALGORITHM:
            return False
        computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                       base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(computed, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False
