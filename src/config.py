"""Configuration lue dans les variables d'environnement (et un fichier `.env` facultatif).

Aucun secret n'est codé en dur : voir `.env.example`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Charge `KEY=VALUE` depuis `.env` sans écraser l'environnement existant."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    db_path: Path
    backup_dir: Path
    auth_password_hash: str
    seed_demo: bool
    allow_no_auth: bool = False

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_password_hash)

    @property
    def access_blocked(self) -> bool:
        """Aucun mot de passe et aucune dérogation explicite : l'application ne s'ouvre pas."""
        return not self.auth_enabled and not self.allow_no_auth


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "oui", "yes")


def load_settings() -> Settings:
    _load_dotenv(PROJECT_ROOT / ".env")
    return Settings(
        db_path=_resolve(os.environ.get("PAIE_DB_PATH", "data/paie.db")),
        backup_dir=_resolve(os.environ.get("PAIE_BACKUP_DIR", "data/backups")),
        auth_password_hash=os.environ.get("PAIE_AUTH_PASSWORD_HASH", "").strip(),
        seed_demo=_flag("PAIE_SEED_DEMO", "1"),
        allow_no_auth=_flag("PAIE_ALLOW_NO_AUTH", "0"),
    )
