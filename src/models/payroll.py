"""Saisie mensuelle, résultat de calcul et cumuls."""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal

from src.calculations.money import ZERO, to_decimal

MOIS_FR = (
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
)

# Statuts d'une paie
STATUT_BROUILLON = "brouillon"
STATUT_CALCULEE = "calculee"
STATUT_CLOTUREE = "cloturee"
STATUT_REMPLACEE = "remplacee"   # version clôturée remplacée par une rectification
STATUTS_LIBELLES = {
    STATUT_BROUILLON: "Brouillon",
    STATUT_CALCULEE: "Calculée",
    STATUT_CLOTUREE: "Clôturée",
    STATUT_REMPLACEE: "Remplacée (rectifiée)",
}
STATUTS_OUVERTS = (STATUT_BROUILLON, STATUT_CALCULEE)


def _decimal_dict(obj) -> dict:
    return {f.name: str(getattr(obj, f.name)) for f in fields(obj)}


def _from_decimal_dict(cls, data: dict):
    return cls(**{f.name: to_decimal(data.get(f.name, "0")) for f in fields(cls)})


@dataclass(frozen=True)
class MonthlyInput:
    """Champs de la feuille `Saisie` (lignes 21 à 30) pour un salarié et un mois."""

    salaire_base: Decimal = ZERO
    jours_declares: Decimal = ZERO
    heures_sup: Decimal = ZERO
    prime_panier: Decimal = ZERO
    indemnite_transport: Decimal = ZERO
    indemnite_representation: Decimal = ZERO
    autre_prime: Decimal = ZERO
    conges_reliquat: Decimal = ZERO
    conges_acquis: Decimal = ZERO
    conges_pris: Decimal = ZERO

    def to_dict(self) -> dict:
        return _decimal_dict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MonthlyInput":
        return _from_decimal_dict(cls, data)


@dataclass(frozen=True)
class PayslipResult:
    """Toutes les rubriques calculées (feuille `Calcul`, lignes 6 à 40)."""

    # A. Gains
    salaire_base: Decimal
    heures_sup: Decimal
    prime_panier: Decimal
    indemnite_transport: Decimal
    indemnite_representation: Decimal
    autre_prime: Decimal
    salaire_brut: Decimal
    jours_declares: Decimal
    taux_journalier: Decimal          # informatif (PDF : « Base 209,10 »)
    # B. Assiettes
    assiette_cotisations: Decimal
    assiette_cnss_plafonnee: Decimal
    # C. Cotisations salariales
    cnss_salarie: Decimal
    amo_salarie: Decimal
    total_cotisations_salariales: Decimal
    # D. Cotisations patronales
    cnss_patronal: Decimal
    amo_patronal: Decimal
    participation_amo: Decimal
    formation_pro: Decimal
    allocations_familiales: Decimal
    total_cotisations_patronales: Decimal
    # E. Impôt sur le revenu
    revenu_brut_imposable: Decimal
    taux_frais_pro: Decimal
    frais_professionnels: Decimal
    cotisations_deduites: Decimal
    net_imposable: Decimal            # avant charges de famille (Calcul!31)
    nb_personnes_charge: Decimal
    deduction_charges_famille: Decimal
    net_imposable_apres_famille: Decimal
    ir_annuel: Decimal
    ir_mensuel: Decimal
    # F. Net
    net_avant_arrondi: Decimal
    arrondi: Decimal
    net_a_payer: Decimal
    cout_employeur: Decimal
    # Congés
    conges_reliquat: Decimal
    conges_acquis: Decimal
    conges_pris: Decimal
    conges_solde: Decimal

    def to_dict(self) -> dict:
        return _decimal_dict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PayslipResult":
        return _from_decimal_dict(cls, data)


@dataclass(frozen=True)
class Cumuls:
    """Cumuls annuels (feuilles Bulletin, ligne 41) + heures sup. (colonne du PDF)."""

    salaire_brut: Decimal = ZERO
    cotisations_salariales: Decimal = ZERO
    cotisations_patronales: Decimal = ZERO
    net_imposable: Decimal = ZERO
    ir: Decimal = ZERO
    jours_declares: Decimal = ZERO
    heures_sup: Decimal = ZERO
    net_a_payer: Decimal = ZERO

    def to_dict(self) -> dict:
        return _decimal_dict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Cumuls":
        return _from_decimal_dict(cls, data)


def period_label(year: int, month: int) -> str:
    return f"{MOIS_FR[month - 1]} {year}"


def period_key(year: int, month: int) -> str:
    """Clé triable « AAAA-MM »."""
    return f"{year:04d}-{month:02d}"
