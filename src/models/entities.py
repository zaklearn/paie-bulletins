"""Entreprise et salarié."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

SITUATIONS_FAMILIALES = ("Célibataire", "Marié(e)", "Divorcé(e)", "Veuf(ve)")
MODES_PAIEMENT = ("Virement", "Chèque", "Espèces")


@dataclass
class Company:
    raison_sociale: str = ""
    adresse: str = ""
    ville: str = ""
    ice: str = ""
    cnss_employeur: str = ""
    rc: str = ""
    identifiant_fiscal: str = ""
    telephone: str = ""
    email: str = ""
    logo: bytes | None = field(default=None, repr=False)

    def snapshot(self) -> dict:
        """Copie figée dans chaque paie clôturée (sans le logo binaire)."""
        data = asdict(self)
        data.pop("logo", None)
        return data


@dataclass
class Employee:
    matricule: str
    nom: str
    prenom: str = ""
    date_naissance: date | None = None
    cin: str = ""
    cnss: str = ""
    situation_familiale: str = SITUATIONS_FAMILIALES[0]
    nb_personnes_charge: int = 0
    date_embauche: date | None = None
    date_sortie: date | None = None
    fonction: str = ""
    departement: str = ""
    cimr: str = ""
    categorie: str = ""
    banque: str = ""
    compte_bancaire: str = ""
    adresse: str = ""
    mode_paiement: str = MODES_PAIEMENT[0]
    actif: bool = True
    id: int | None = None

    @property
    def nom_complet(self) -> str:
        """« NOM Prénom », comme le bandeau du PDF de référence."""
        return f"{self.nom.upper()} {self.prenom}".strip()

    def snapshot(self) -> dict:
        """Copie figée dans la paie : la fiche peut évoluer sans altérer l'historique."""
        data = asdict(self)
        for key in ("date_naissance", "date_embauche", "date_sortie"):
            if data[key] is not None:
                data[key] = data[key].isoformat()
        return data
