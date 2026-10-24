"""Arithmétique monétaire exacte.

Toutes les valeurs de paie sont des `Decimal`. `excel_round` reproduit la fonction
`ROUND` d'Excel : arrondi au plus proche, demi-unité vers l'extérieur (0,005 -> 0,01 ;
-0,005 -> -0,01), ce qui correspond à `ROUND_HALF_UP` du module `decimal`.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

ZERO = Decimal("0")
CENT = Decimal("0.01")


def to_decimal(value: object) -> Decimal:
    """Convertit une saisie (str, int, float, Decimal, None) en `Decimal` exact.

    Les flottants passent par leur représentation textuelle (`repr`) pour éviter
    d'importer l'erreur binaire : 0.1 devient Decimal("0.1"), pas 0.1000000000000000055…
    """
    if value is None or value == "":
        return ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TypeError("Un booléen n'est pas un montant.")
    if isinstance(value, float):
        return Decimal(repr(value))
    try:
        return Decimal(str(value).strip().replace(" ", "").replace(" ", "").replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"Valeur numérique invalide : {value!r}") from exc


def excel_round(value: Decimal, digits: int = 2) -> Decimal:
    """Équivalent exact de `ROUND(value; digits)` d'Excel."""
    quantum = Decimal(1).scaleb(-digits)
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def money(value: Decimal) -> Decimal:
    """Normalise un montant à deux décimales pour l'affichage et le stockage."""
    return excel_round(value, 2)
