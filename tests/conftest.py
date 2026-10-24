from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.calculations.defaults import DEFAULT_PARAMETERS  # noqa: E402
from src.repositories.db import Database  # noqa: E402
from src.services import master_data  # noqa: E402
from src.services.demo import DEMO_COMPANY, DEMO_EMPLOYEE, REFERENCE_INPUT  # noqa: E402

ACTOR = "test"


@pytest.fixture
def params():
    return DEFAULT_PARAMETERS


@pytest.fixture
def ref_input():
    """Saisie de septembre 2026 du classeur (Saisie!D21:D30)."""
    return REFERENCE_INPUT


@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(tmp_path / "paie.db")
    database.migrate()
    master_data.ensure_initial_parameters(database)
    return database


@pytest.fixture
def setup(db):
    """Base avec entreprise et un salarié embauché le 01/07/2026 (fictifs)."""
    master_data.save_company(db, ACTOR, replace(DEMO_COMPANY))
    employee_id, _ = master_data.create_employee(db, ACTOR, replace(DEMO_EMPLOYEE))
    return db, employee_id


def make_employee(matricule: str, **changes):
    base = replace(DEMO_EMPLOYEE, matricule=matricule, cin="", cnss="", id=None)
    return replace(base, **changes)


@pytest.fixture
def hired_january(db):
    master_data.save_company(db, ACTOR, replace(DEMO_COMPANY))
    employee_id, _ = master_data.create_employee(
        db, ACTOR, make_employee("0002", date_embauche=date(2025, 1, 1)))
    return db, employee_id


def money(value: str) -> D:
    return D(value)
