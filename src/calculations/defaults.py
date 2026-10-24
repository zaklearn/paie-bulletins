"""Valeurs initiales relevées dans la feuille `Paramètres` du classeur de référence.

Ce sont des **paramètres de départ à auditer**, pas des valeurs légales certifiées.
Ils ne sont utilisés qu'une fois, pour créer la première version de paramètres en base ;
le moteur de calcul reçoit toujours les paramètres explicitement.
"""

from decimal import Decimal as D

from src.models.parameters import METHODE_SOMME_LIGNES, IRBracket, PayrollParameters

DEFAULT_PARAMETERS = PayrollParameters(
    cnss_salarial=D("0.0448"),            # Paramètres!B10
    amo_salarial=D("0.0226"),             # Paramètres!B11
    plafond_cnss=D("6000"),               # Paramètres!B12
    cnss_patronal=D("0.0898"),            # Paramètres!B13
    amo_patronal=D("0.0226"),             # Paramètres!B14
    participation_amo=D("0.0185"),        # Paramètres!B15
    formation_pro=D("0.016"),             # Paramètres!B16
    allocations_familiales=D("0.064"),    # Paramètres!B17
    fp_seuil_annuel=D("78000"),           # Paramètres!B20
    fp_taux_bas=D("0.35"),                # Paramètres!B21
    fp_taux_haut=D("0.25"),               # Paramètres!B22
    fp_plafond_annuel=D("35000"),         # Paramètres!B23
    deduction_par_personne=D("500"),      # Paramètres!B24
    max_personnes=6,                      # Paramètres!B25
    imposable_heures_sup=D("1"),          # Paramètres!B28
    imposable_prime_panier=D("0"),        # Paramètres!B29
    imposable_transport=D("0"),           # Paramètres!B30
    imposable_representation=D("0"),      # Paramètres!B31
    imposable_autre_prime=D("1"),         # Paramètres!B32
    bareme=(                              # Paramètres!A37:D42
        IRBracket(D("0"), D("40000"), D("0"), D("0")),
        IRBracket(D("40000.01"), D("60000"), D("0.1"), D("4000")),
        IRBracket(D("60000.01"), D("80000"), D("0.2"), D("10000")),
        IRBracket(D("80000.01"), D("100000"), D("0.3"), D("18000")),
        IRBracket(D("100000.01"), D("180000"), D("0.34"), D("24000")),
        IRBracket(D("180000.01"), None, D("0.38"), D("40000")),
    ),
    methode_totaux=METHODE_SOMME_LIGNES,
)
