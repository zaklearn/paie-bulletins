"""Moteur de calcul de la paie, indépendant de l'interface.

Chaque fonction reproduit une ligne (ou un groupe de lignes) de la feuille `Calcul` du
classeur de référence ; la formule Excel d'origine figure dans la docstring. Les arrondis
sont appliqués exactement aux mêmes étapes que dans le classeur.
"""

from __future__ import annotations

from decimal import Decimal

from src.calculations.money import ZERO, excel_round
from src.models.parameters import METHODE_TAUX_CUMULE, IRBracket, PayrollParameters
from src.models.payroll import MonthlyInput, PayslipResult

DOUZE = Decimal(12)


# --- A. Gains -----------------------------------------------------------------------

def salaire_brut(inp: MonthlyInput) -> Decimal:
    """`Calcul!12 = SUM(6:11)`."""
    return (
        inp.salaire_base + inp.heures_sup + inp.prime_panier
        + inp.indemnite_transport + inp.indemnite_representation + inp.autre_prime
    )


def taux_journalier(inp: MonthlyInput) -> Decimal:
    """Base affichée sur la ligne « Salaire de base (jours) » du PDF : ROUND(base / jours, 2).

    Informatif uniquement (absent du classeur) ; 0 si aucun jour déclaré.
    """
    if inp.jours_declares <= 0:
        return ZERO
    return excel_round(inp.salaire_base / inp.jours_declares, 2)


# --- B. Assiettes -------------------------------------------------------------------

def assiette_cotisations(inp: MonthlyInput) -> Decimal:
    """`Calcul!13 = base + heures sup. + autre prime` (indemnités exclues)."""
    return inp.salaire_base + inp.heures_sup + inp.autre_prime


def assiette_cnss_plafonnee(assiette: Decimal, params: PayrollParameters) -> Decimal:
    """`Calcul!14 = MIN(assiette, plafond CNSS)`."""
    return min(assiette, params.plafond_cnss)


# --- C/D. Cotisations ---------------------------------------------------------------

def cotisation(base: Decimal, taux: Decimal) -> Decimal:
    """`ROUND(base * taux, 2)` — chaque cotisation est arrondie séparément."""
    return excel_round(base * taux, 2)


def total_salarial(cnss: Decimal, amo: Decimal, plafonnee: Decimal, assiette: Decimal,
                   params: PayrollParameters) -> Decimal:
    """Total des cotisations salariales.

    - classeur (`Calcul!18 = 16 + 17`) : somme des lignes arrondies ;
    - PDF source (méthode « taux cumulé ») : ROUND(plafonnée × CNSS + assiette × AMO, 2).
    """
    if params.methode_totaux == METHODE_TAUX_CUMULE:
        return excel_round(plafonnee * params.cnss_salarial + assiette * params.amo_salarial, 2)
    return cnss + amo


def total_patronal(lignes: tuple[Decimal, ...], plafonnee: Decimal, assiette: Decimal,
                   params: PayrollParameters) -> Decimal:
    """Total des cotisations patronales (`Calcul!25 = SUM(20:24)` ou méthode PDF)."""
    if params.methode_totaux == METHODE_TAUX_CUMULE:
        taux_non_plafonnes = (params.amo_patronal + params.participation_amo
                              + params.formation_pro + params.allocations_familiales)
        return excel_round(plafonnee * params.cnss_patronal + assiette * taux_non_plafonnes, 2)
    return sum(lignes, ZERO)


# --- E. Impôt sur le revenu ---------------------------------------------------------

def revenu_brut_imposable(inp: MonthlyInput, params: PayrollParameters) -> Decimal:
    """`Calcul!27` : base à 100 % + Σ élément × part imposable. Non arrondi."""
    return (
        inp.salaire_base
        + inp.heures_sup * params.imposable_heures_sup
        + inp.prime_panier * params.imposable_prime_panier
        + inp.indemnite_transport * params.imposable_transport
        + inp.indemnite_representation * params.imposable_representation
        + inp.autre_prime * params.imposable_autre_prime
    )


def taux_frais_professionnels(rbi: Decimal, params: PayrollParameters) -> Decimal:
    """`Calcul!28 = IF(RBI*12 <= seuil, taux bas, taux haut)`."""
    return params.fp_taux_bas if rbi * DOUZE <= params.fp_seuil_annuel else params.fp_taux_haut


def frais_professionnels(rbi: Decimal, taux: Decimal, params: PayrollParameters) -> Decimal:
    """`Calcul!29 = ROUND(MIN(taux*RBI, plafond annuel/12), 2)`."""
    return excel_round(min(taux * rbi, params.fp_plafond_annuel / DOUZE), 2)


def deduction_charges_famille(nb_personnes: int, params: PayrollParameters) -> Decimal:
    """`Calcul!32 = ROUND(MIN(nb, max) * déduction annuelle / 12, 2)`."""
    nb = min(max(nb_personnes, 0), params.max_personnes)
    return excel_round(Decimal(nb) * params.deduction_par_personne / DOUZE, 2)


def tranche_bareme(revenu_annuel: Decimal, bareme: tuple[IRBracket, ...]) -> IRBracket:
    """Équivalent de `MATCH(revenu, bornes_inférieures, 1)` : dernière borne ≤ revenu."""
    if not bareme:
        raise ValueError("Le barème de l'IR est vide.")
    retenue = bareme[0]
    for tranche in bareme:
        if tranche.lower <= revenu_annuel:
            retenue = tranche
        else:
            break
    return retenue


def ir_annuel(net_imposable_mensuel: Decimal, params: PayrollParameters) -> Decimal:
    """`Calcul!34 = MAX(0, NI*12*taux - somme à déduire)`. Non arrondi."""
    annuel = net_imposable_mensuel * DOUZE
    tranche = tranche_bareme(annuel, params.bareme)
    return max(ZERO, annuel * tranche.rate - tranche.deduction)


# --- F. Net -------------------------------------------------------------------------

def arrondi_net(net_avant_arrondi: Decimal) -> tuple[Decimal, Decimal]:
    """`Calcul!38 = ROUND(ROUND(net,0) - net, 2)` et `Calcul!39 = ROUND(net, 0)`."""
    net_a_payer = excel_round(net_avant_arrondi, 0)
    return excel_round(net_a_payer - net_avant_arrondi, 2), net_a_payer


def solde_conges(inp: MonthlyInput) -> Decimal:
    """Bulletin!F17 : reliquat + acquis − pris."""
    return inp.conges_reliquat + inp.conges_acquis - inp.conges_pris


# --- Orchestration ------------------------------------------------------------------

def compute_payslip(inp: MonthlyInput, params: PayrollParameters,
                    nb_personnes_charge: int) -> PayslipResult:
    """Calcule toutes les rubriques d'une paie mensuelle."""
    brut = salaire_brut(inp)
    assiette = assiette_cotisations(inp)
    plafonnee = assiette_cnss_plafonnee(assiette, params)

    cnss_sal = cotisation(plafonnee, params.cnss_salarial)
    amo_sal = cotisation(assiette, params.amo_salarial)
    tot_sal = total_salarial(cnss_sal, amo_sal, plafonnee, assiette, params)

    cnss_pat = cotisation(plafonnee, params.cnss_patronal)
    amo_pat = cotisation(assiette, params.amo_patronal)
    part_amo = cotisation(assiette, params.participation_amo)
    fp = cotisation(assiette, params.formation_pro)
    af = cotisation(assiette, params.allocations_familiales)
    tot_pat = total_patronal((cnss_pat, amo_pat, part_amo, fp, af), plafonnee, assiette, params)

    rbi = revenu_brut_imposable(inp, params)
    taux_fp = taux_frais_professionnels(rbi, params)
    frais = frais_professionnels(rbi, taux_fp, params)
    net_imp = max(ZERO, rbi - frais - tot_sal)
    deduction = deduction_charges_famille(nb_personnes_charge, params)
    net_imp_famille = max(ZERO, net_imp - deduction)
    ir_an = ir_annuel(net_imp_famille, params)
    ir_mois = excel_round(ir_an / DOUZE, 2)

    net_avant = brut - tot_sal - ir_mois
    arrondi, net_a_payer = arrondi_net(net_avant)

    return PayslipResult(
        salaire_base=inp.salaire_base,
        heures_sup=inp.heures_sup,
        prime_panier=inp.prime_panier,
        indemnite_transport=inp.indemnite_transport,
        indemnite_representation=inp.indemnite_representation,
        autre_prime=inp.autre_prime,
        salaire_brut=brut,
        jours_declares=inp.jours_declares,
        taux_journalier=taux_journalier(inp),
        assiette_cotisations=assiette,
        assiette_cnss_plafonnee=plafonnee,
        cnss_salarie=cnss_sal,
        amo_salarie=amo_sal,
        total_cotisations_salariales=tot_sal,
        cnss_patronal=cnss_pat,
        amo_patronal=amo_pat,
        participation_amo=part_amo,
        formation_pro=fp,
        allocations_familiales=af,
        total_cotisations_patronales=tot_pat,
        revenu_brut_imposable=rbi,
        taux_frais_pro=taux_fp,
        frais_professionnels=frais,
        cotisations_deduites=tot_sal,
        net_imposable=net_imp,
        nb_personnes_charge=Decimal(nb_personnes_charge),
        deduction_charges_famille=deduction,
        net_imposable_apres_famille=net_imp_famille,
        ir_annuel=ir_an,
        ir_mensuel=ir_mois,
        net_avant_arrondi=net_avant,
        arrondi=arrondi,
        net_a_payer=net_a_payer,
        cout_employeur=brut + tot_pat,
        conges_reliquat=inp.conges_reliquat,
        conges_acquis=inp.conges_acquis,
        conges_pris=inp.conges_pris,
        conges_solde=solde_conges(inp),
    )
