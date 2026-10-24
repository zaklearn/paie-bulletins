"""Formats d'affichage français (montants, taux, dates, jours, ancienneté)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.calculations.money import excel_round, to_decimal


def fmt_money(value: Decimal | str | None, blank_zero: bool = False) -> str:
    """7366.51 -> « 7 366,51 »."""
    if value is None or value == "":
        return ""
    amount = excel_round(to_decimal(value), 2)
    if blank_zero and amount == 0:
        return ""
    sign = "-" if amount < 0 else ""
    integer, decimals = f"{abs(amount):.2f}".split(".")
    groups = []
    while len(integer) > 3:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    groups.insert(0, integer)
    return f"{sign}{' '.join(groups)},{decimals}"


def fmt_mad(value: Decimal | str | None) -> str:
    return f"{fmt_money(value)} MAD"


def fmt_rate(value: Decimal | str | None) -> str:
    """Taux en pourcentage sans symbole, comme le PDF : 0.0448 -> « 4,48 »."""
    if value is None or value == "":
        return ""
    return fmt_money(to_decimal(value) * 100)


def fmt_percent(value: Decimal | str | None) -> str:
    return f"{fmt_rate(value)} %"


def fmt_days(value: Decimal | str | None) -> str:
    return fmt_money(value)


def fmt_date(value: date | str | None) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value.strftime("%d/%m/%Y")


def anciennete(date_embauche: date | str | None, year: int, month: int) -> str:
    """Ancienneté à la fin du mois de paie, « 2 an(s) 3 mois ». Affichage uniquement."""
    if not date_embauche:
        return ""
    if isinstance(date_embauche, str):
        date_embauche = date.fromisoformat(date_embauche)
    total = (year - date_embauche.year) * 12 + (month - date_embauche.month)
    if total < 0:
        return ""
    years, months = divmod(total, 12)
    if years == 0:
        return f"{months} mois"
    return f"{years} an(s) {months} mois"


def mask(value: str, visible: int = 4) -> str:
    """Masque un identifiant sensible : « XY123456 » -> « ••••3456 »."""
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) <= visible:
        return "•" * len(value)
    return "•" * (len(value) - visible) + value[-visible:]
