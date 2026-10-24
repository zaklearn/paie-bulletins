"""Les résultats validés ne doivent pas changer sans régénération explicite des références."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.calculations.engine import compute_payslip

from .golden_scenarios import SCENARIOS, params_for

GOLDEN = json.loads((Path(__file__).parent / "golden" / "results.json").read_text(encoding="utf-8"))


def test_golden_file_covers_all_scenarios():
    assert set(GOLDEN) == set(SCENARIOS)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_scenario_unchanged(name):
    inp, nb, method = SCENARIOS[name]
    assert compute_payslip(inp, params_for(method), nb).to_dict() == GOLDEN[name]
