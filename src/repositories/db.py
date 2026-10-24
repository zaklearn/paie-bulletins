"""Connexion SQLite, transactions et migrations du schéma.

Choix : SQLite (bibliothèque standard), adapté à un usage mono-poste ou à faible
concurrence. Les montants sont stockés en TEXT (représentation décimale exacte).
Les règles d'intégrité critiques sont aussi portées par la base (contraintes d'unicité,
déclencheurs d'immuabilité) pour ne pas dépendre uniquement du code applicatif.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS: list[tuple[int, str]] = [
    (1, """
    CREATE TABLE company (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        raison_sociale TEXT NOT NULL,
        adresse TEXT NOT NULL DEFAULT '',
        ville TEXT NOT NULL DEFAULT '',
        ice TEXT NOT NULL DEFAULT '',
        cnss_employeur TEXT NOT NULL DEFAULT '',
        rc TEXT NOT NULL DEFAULT '',
        identifiant_fiscal TEXT NOT NULL DEFAULT '',
        telephone TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '',
        logo BLOB,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE employees (
        id INTEGER PRIMARY KEY,
        matricule TEXT NOT NULL UNIQUE,
        nom TEXT NOT NULL,
        prenom TEXT NOT NULL DEFAULT '',
        date_naissance TEXT,
        cin TEXT NOT NULL DEFAULT '',
        cnss TEXT NOT NULL DEFAULT '',
        situation_familiale TEXT NOT NULL,
        nb_personnes_charge INTEGER NOT NULL DEFAULT 0 CHECK (nb_personnes_charge >= 0),
        date_embauche TEXT,
        date_sortie TEXT,
        fonction TEXT NOT NULL DEFAULT '',
        departement TEXT NOT NULL DEFAULT '',
        cimr TEXT NOT NULL DEFAULT '',
        categorie TEXT NOT NULL DEFAULT '',
        banque TEXT NOT NULL DEFAULT '',
        compte_bancaire TEXT NOT NULL DEFAULT '',
        adresse TEXT NOT NULL DEFAULT '',
        mode_paiement TEXT NOT NULL DEFAULT 'Virement',
        actif INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE UNIQUE INDEX ux_employees_cin ON employees(cin) WHERE cin <> '';
    CREATE UNIQUE INDEX ux_employees_cnss ON employees(cnss) WHERE cnss <> '';

    CREATE TABLE parameter_sets (
        id INTEGER PRIMARY KEY,
        valid_from TEXT NOT NULL UNIQUE,          -- 'AAAA-MM'
        label TEXT NOT NULL DEFAULT '',
        data TEXT NOT NULL,                       -- JSON PayrollParameters
        comment TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        created_by TEXT NOT NULL DEFAULT ''
    );
    CREATE TRIGGER trg_parameter_sets_immutable BEFORE UPDATE ON parameter_sets
    BEGIN
        SELECT RAISE(ABORT, 'Une version de paramètres est immuable : créer une nouvelle version.');
    END;

    CREATE TABLE payslips (
        id INTEGER PRIMARY KEY,
        employee_id INTEGER NOT NULL REFERENCES employees(id),
        year INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
        month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
        version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
        status TEXT NOT NULL CHECK (status IN ('brouillon', 'calculee', 'cloturee', 'remplacee')),
        inputs TEXT NOT NULL,
        result TEXT,
        cumuls TEXT,
        parameter_set_id INTEGER REFERENCES parameter_sets(id),
        parameters TEXT,
        employee_snapshot TEXT,
        company_snapshot TEXT,
        replaces_id INTEGER REFERENCES payslips(id),
        rectification_reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        calculated_at TEXT,
        closed_at TEXT,
        closed_by TEXT NOT NULL DEFAULT '',
        UNIQUE (employee_id, year, month, version)
    );
    -- Au plus une version de travail et une version clôturée faisant foi par salarié et mois.
    CREATE UNIQUE INDEX ux_payslips_open ON payslips(employee_id, year, month)
        WHERE status IN ('brouillon', 'calculee');
    CREATE UNIQUE INDEX ux_payslips_closed ON payslips(employee_id, year, month)
        WHERE status = 'cloturee';
    CREATE INDEX ix_payslips_period ON payslips(year, month);

    -- Une paie clôturée est figée ; seule la transition cloturee -> remplacee est admise,
    -- sans aucune autre modification.
    CREATE TRIGGER trg_payslips_closed_immutable BEFORE UPDATE ON payslips
    WHEN OLD.status IN ('cloturee', 'remplacee') AND NOT (
        OLD.status = 'cloturee' AND NEW.status = 'remplacee'
        AND NEW.inputs IS OLD.inputs AND NEW.result IS OLD.result
        AND NEW.cumuls IS OLD.cumuls AND NEW.parameters IS OLD.parameters
        AND NEW.employee_snapshot IS OLD.employee_snapshot
        AND NEW.company_snapshot IS OLD.company_snapshot
        AND NEW.closed_at IS OLD.closed_at AND NEW.version IS OLD.version
        AND NEW.year IS OLD.year AND NEW.month IS OLD.month
        AND NEW.employee_id IS OLD.employee_id
    )
    BEGIN
        SELECT RAISE(ABORT, 'Paie clôturée : modification interdite (passer par une rectification).');
    END;
    CREATE TRIGGER trg_payslips_closed_nodelete BEFORE DELETE ON payslips
    WHEN OLD.status IN ('cloturee', 'remplacee')
    BEGIN
        SELECT RAISE(ABORT, 'Paie clôturée : suppression interdite.');
    END;

    CREATE TABLE documents (
        id INTEGER PRIMARY KEY,
        payslip_id INTEGER NOT NULL UNIQUE REFERENCES payslips(id),
        filename TEXT NOT NULL,
        content BLOB NOT NULL,
        sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TRIGGER trg_documents_immutable BEFORE UPDATE ON documents
    BEGIN
        SELECT RAISE(ABORT, 'Bulletin archivé : modification interdite.');
    END;
    CREATE TRIGGER trg_documents_nodelete BEFORE DELETE ON documents
    BEGIN
        SELECT RAISE(ABORT, 'Bulletin archivé : suppression interdite.');
    END;

    CREATE TABLE audit_log (
        id INTEGER PRIMARY KEY,
        ts TEXT NOT NULL,
        actor TEXT NOT NULL DEFAULT '',
        action TEXT NOT NULL,
        entity TEXT NOT NULL DEFAULT '',
        entity_id TEXT NOT NULL DEFAULT '',
        details TEXT NOT NULL DEFAULT ''
    );
    CREATE TRIGGER trg_audit_append_only BEFORE UPDATE ON audit_log
    BEGIN
        SELECT RAISE(ABORT, 'Journal en ajout seul.');
    END;
    """),
]

SCHEMA_VERSION = MIGRATIONS[-1][0]


class Database:
    """Accès à un fichier SQLite. Une connexion courte par opération."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Transaction `BEGIN IMMEDIATE` : tout ou rien, verrou d'écriture dès le début."""
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    def migrate(self) -> int:
        """Applique les migrations manquantes ; renvoie la version finale du schéma."""
        conn = self.connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
            current = row["v"] or 0
            for version, sql in MIGRATIONS:
                if version <= current:
                    continue
                conn.execute("BEGIN IMMEDIATE")
                try:
                    for statement in _split_sql(sql):
                        conn.execute(statement)
                    conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
                    conn.execute("COMMIT")
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
                current = version
            return current
        finally:
            conn.close()


def _split_sql(script: str) -> list[str]:
    """Découpe un script en instructions en respectant les blocs BEGIN…END des déclencheurs."""
    statements, buffer = [], []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        candidate = "\n".join(buffer)
        if stripped.endswith(";") and sqlite3.complete_statement(candidate):
            statements.append(candidate.strip())
            buffer = []
    if buffer:
        statements.append("\n".join(buffer).strip())
    return statements
