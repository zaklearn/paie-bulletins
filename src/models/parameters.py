"""Paramètres de calcul de la paie (feuille `Paramètres` du classeur)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace
from decimal import Decimal

from src.calculations.money import to_decimal

# Méthodes de calcul des totaux de cotisations (voir docs/AUDIT_SOURCES.md, écarts E1/E2).
METHODE_SOMME_LIGNES = "somme_lignes"   # classeur Excel : somme des lignes arrondies
METHODE_TAUX_CUMULE = "taux_cumule"     # PDF source : ROUND(Σ assiette × taux, 2)
METHODES_TOTAUX = {
    METHODE_SOMME_LIGNES: "Somme des lignes arrondies (classeur Excel)",
    METHODE_TAUX_CUMULE: "Assiette × taux cumulé, arrondi une fois (PDF source)",
}


@dataclass(frozen=True)
class IRBracket:
    """Tranche du barème annuel de l'IR (méthode de la somme à déduire)."""

    lower: Decimal
    upper: Decimal | None
    rate: Decimal
    deduction: Decimal

    def to_dict(self) -> dict:
        return {
            "lower": str(self.lower),
            "upper": None if self.upper is None else str(self.upper),
            "rate": str(self.rate),
            "deduction": str(self.deduction),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IRBracket":
        upper = data.get("upper")
        return cls(
            lower=to_decimal(data["lower"]),
            upper=None if upper in (None, "") else to_decimal(upper),
            rate=to_decimal(data["rate"]),
            deduction=to_decimal(data["deduction"]),
        )


@dataclass(frozen=True)
class PayrollParameters:
    """Jeu complet de paramètres applicable à une période.

    Les taux sont exprimés en fraction (0.0448 pour 4,48 %).
    """

    # Cotisations sociales
    cnss_salarial: Decimal
    amo_salarial: Decimal
    plafond_cnss: Decimal
    cnss_patronal: Decimal
    amo_patronal: Decimal
    participation_amo: Decimal
    formation_pro: Decimal
    allocations_familiales: Decimal
    # Impôt sur le revenu
    fp_seuil_annuel: Decimal
    fp_taux_bas: Decimal
    fp_taux_haut: Decimal
    fp_plafond_annuel: Decimal
    deduction_par_personne: Decimal
    max_personnes: int
    # Parts imposables (le salaire de base est toujours imposable à 100 %)
    imposable_heures_sup: Decimal
    imposable_prime_panier: Decimal
    imposable_transport: Decimal
    imposable_representation: Decimal
    imposable_autre_prime: Decimal
    # Barème annuel de l'IR
    bareme: tuple[IRBracket, ...] = field(default_factory=tuple)
    # Méthode des totaux de cotisations
    methode_totaux: str = METHODE_SOMME_LIGNES

    def to_dict(self) -> dict:
        data = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name == "bareme":
                data[f.name] = [b.to_dict() for b in value]
            elif isinstance(value, Decimal):
                data[f.name] = str(value)
            else:
                data[f.name] = value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "PayrollParameters":
        kwargs = {}
        for f in fields(cls):
            if f.name not in data:
                continue
            value = data[f.name]
            if f.name == "bareme":
                kwargs[f.name] = tuple(IRBracket.from_dict(b) for b in value)
            elif f.name == "max_personnes":
                kwargs[f.name] = int(value)
            elif f.name == "methode_totaux":
                kwargs[f.name] = str(value)
            else:
                kwargs[f.name] = to_decimal(value)
        return cls(**kwargs)

    def with_changes(self, **changes) -> "PayrollParameters":
        return replace(self, **changes)


def parameters_as_flat_dict(params: PayrollParameters) -> dict:
    """Vue plate (sans barème) utile aux comparaisons et à l'affichage."""
    data = asdict(params)
    data.pop("bareme", None)
    return data
