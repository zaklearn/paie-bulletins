"""Sauvegarde en ligne de commande (à planifier, par exemple avec cron).

    python scripts/backup_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_settings  # noqa: E402
from src.repositories.db import Database  # noqa: E402
from src.services.backup import create_backup  # noqa: E402


def main() -> None:
    settings = load_settings()
    if not settings.db_path.exists():
        sys.exit(f"Base introuvable : {settings.db_path}")
    db = Database(settings.db_path)
    db.migrate()
    print(create_backup(db, settings.backup_dir, "script", label="planifiee"))


if __name__ == "__main__":
    main()
