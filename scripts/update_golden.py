"""Régénère tests/golden/results.json (résultats de non-régression).

À n'exécuter qu'après un changement de calcul **voulu et documenté** :
    python scripts/update_golden.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.calculations.engine import compute_payslip  # noqa: E402
from tests.golden_scenarios import SCENARIOS, params_for  # noqa: E402


def main() -> None:
    results = {name: compute_payslip(inp, params_for(method), nb).to_dict()
               for name, (inp, nb, method) in SCENARIOS.items()}
    target = ROOT / "tests" / "golden" / "results.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(results)} scénarios écrits dans {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
