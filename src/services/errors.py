"""Exceptions métier présentées telles quelles à l'utilisateur."""

from __future__ import annotations

from src.validation.validators import Issue


class PayrollError(Exception):
    """Opération refusée par une règle de gestion."""


class ValidationFailed(PayrollError):
    """La saisie contient au moins une erreur bloquante."""

    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__(" ; ".join(i.message for i in issues if i.level == "erreur"))
