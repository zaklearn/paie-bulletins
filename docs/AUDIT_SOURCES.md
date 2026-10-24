# Audit des sources

Ce document reconstitue le fonctionnement des deux fichiers de référence fournis :

| Fichier | Rôle dans le projet |
|---|---|
| `paie_exemple_EXEMPLE_SARL.xlsx` | Référence initiale du **moteur de calcul** (formules) |
| `HBN Etat_Bull 09-2026.pdf` | Référence initiale du **rendu documentaire** (bulletin de septembre 2026) |

> **Données personnelles.** Les deux fichiers contiennent des identifiants (nom, CIN, n° CNSS,
> ICE, n° CNSS employeur, adresse) qui peuvent correspondre à des personnes ou sociétés réelles.
> Ils ne sont **pas** versionnés dans le dépôt et ce rapport les remplace par `[masqué]`.
> Seuls les montants, qui ne permettent pas d'identifier une personne, sont repris.

> **Statut juridique.** Les taux, plafonds et barèmes du classeur sont audités ici pour leur
> *cohérence interne*, pas pour leur conformité légale. Le classeur lui-même le précise
> (feuille `Paramètres`, A44 : « Hypothèses (à valider avec votre comptable) »).

---

## 1. Méthode

1. Extraction exhaustive des cellules, formules et valeurs en cache (openpyxl, deux lectures :
   formules et `data_only`).
2. Lecture du XML brut pour ce qu'openpyxl ignore : validations de données étendues `x14`,
   zones d'impression, largeurs de colonnes, couleurs de remplissage (repérage des cellules
   de saisie).
3. Extraction du texte, des polices et du rendu graphique du PDF (pdfplumber, pypdfium2).
4. Recalcul indépendant de chaque rubrique en `Decimal` et comparaison au centime avec les
   valeurs en cache du classeur et les montants du PDF.

## 2. Structure du classeur

| Feuille | Plage | Rôle | Cellules de saisie (fond jaune `FFF2CC`) |
|---|---|---|---|
| `Paramètres` | A1:D48 | Société, taux sociaux, paramètres IR, parts imposables, barème | B4:B7, B10:B17, B20:B25, B28:B32, A37:D42 (sauf B) |
| `Saisie` | A1:E32 | Fiche salarié unique + saisie mensuelle en colonnes (Juillet→Octobre) | B4:B17, B20:E30 |
| `Calcul` | A1:E42 | Calcul de chaque rubrique, une colonne par mois | aucune |
| `Bulletin Juillet` | A1:J45 | Bulletin mis en page (zone d'impression A1:G45) | B6 (menu mois) |
| `Bulletin Août` | A1:J45 | Copie identique, B6 = « Août » | B6 |
| `Bulletin Septembre` | A1:J45 | Copie identique, B6 = « Septembre » | B6 |

Aucune feuille n'est protégée. Aucun nom défini hormis les trois zones d'impression.

**Validations de données** (extension `x14`, invisible pour openpyxl) : une seule liste
déroulante par feuille Bulletin, en `B6`, source `Saisie!$B$19:$D$19` (Juillet, Août,
Septembre). Aucune autre validation : les montants, jours et congés ne sont pas contrôlés.

### 2.1 Feuille `Paramètres`

| Cellule | Libellé | Valeur initiale |
|---|---|---|
| B4 | Raison sociale | `[masqué]` |
| B5 | Adresse | `[masqué]` |
| B6 | ICE | `[masqué]` |
| B7 | N° CNSS employeur | `[masqué]` |
| B10 | CNSS – part salariale | 4,48 % |
| B11 | AMO – part salariale | 2,26 % |
| B12 | Plafond mensuel CNSS | 6 000,00 |
| B13 | CNSS – part patronale | 8,98 % |
| B14 | AMO – part patronale | 2,26 % |
| B15 | Participation AMO | 1,85 % |
| B16 | Taxe de formation professionnelle | 1,60 % |
| B17 | Allocations familiales (patronal, assiette non plafonnée) | 6,40 % |
| B20 | Seuil annuel des frais professionnels | 78 000,00 |
| B21 | Taux frais pro si revenu brut imposable annuel ≤ seuil | 35 % |
| B22 | Taux frais pro si revenu brut imposable annuel > seuil | 25 % |
| B23 | Plafond annuel des frais professionnels | 35 000,00 |
| B24 | Déduction annuelle par personne à charge | 500,00 |
| B25 | Nombre maximum de personnes à charge | 6 |
| B28 | Part imposable – heures supplémentaires | 100 % |
| B29 | Part imposable – prime de panier | 0 % |
| B30 | Part imposable – indemnité de transport | 0 % |
| B31 | Part imposable – indemnité de représentation | 0 % |
| B32 | Part imposable – autre prime | 100 % |
| A33 | « Le salaire de base est toujours imposable à 100 %. » | (texte) |

Barème annuel IR (A37:D42) :

| À partir de | Jusqu'à | Taux | Somme à déduire |
|---:|---:|---:|---:|
| 0,00 | 40 000,00 | 0 % | 0,00 |
| 40 000,01 | 60 000,00 | 10 % | 4 000,00 |
| 60 000,01 | 80 000,00 | 20 % | 10 000,00 |
| 80 000,01 | 100 000,00 | 30 % | 18 000,00 |
| 100 000,01 | 180 000,00 | 34 % | 24 000,00 |
| 180 000,01 | et plus | 38 % | 40 000,00 |

Hypothèses écrites par l'auteur du classeur (A44:A48) :

- taux CNSS/AMO et barème IR « loi de finances 2025 reconduits pour 2026 » ;
- assiette des cotisations = base + heures sup. + autre prime, indemnités exclues ;
- parts imposables des indemnités « calées pour retrouver le net imposable du bulletin
  d'exemple (3 167,31 MAD en septembre) » — voir l'écart E3 : le classeur obtient en réalité
  3 167,30 ;
- données société et salarié « entièrement fictives ».

### 2.2 Feuille `Saisie`

Fiche salarié (une seule par classeur), colonne B :

| Ligne | Champ | Exemple (anonymisé) |
|---|---|---|
| 4 | Nom (prénom + nom dans un seul champ) | `[masqué]` |
| 5 | Matricule (texte) | `0001` |
| 6 | Date de naissance | `[masqué]` |
| 7 | N° CIN | `[masqué]` |
| 8 | N° CNSS | `[masqué]` |
| 9 | Situation familiale | Célibataire |
| 10 | Nombre de déductions (personnes à charge) | 0 |
| 11 | Date d'embauche | 01/07/2026 |
| 12–17 | Fonction, Département, N° CIMR, Catégorie, Banque, N° compte bancaire | « Employé », puis « - » |

Saisie mensuelle, une colonne par mois (B = Juillet, C = Août, D = Septembre, E = Octobre) :

| Ligne | Champ | Valeur identique pour les 4 mois |
|---|---|---|
| 19 | Nom du mois (texte libre, alimente les menus) | — |
| 20 | Année | 2026 |
| 21 | Salaire de base mensuel | 5 436,51 |
| 22 | Jours déclarés | 26 |
| 23 | Heures supplémentaires – montant | 0 |
| 24 | Prime de panier | 930,00 |
| 25 | Indemnité de transport – périmètre urbain | 500,00 |
| 26 | Indemnité de représentation | 500,00 |
| 27 | Autre prime | 0 |
| 28 | Reliquat de congés (j) | 0 |
| 29 | Congés acquis (j) | 1,5 |
| 30 | Congés pris (j) | 0 |

### 2.3 Feuille `Calcul` — formules reconstituées

Notation : `P!` = `Paramètres!`, `S!` = `Saisie!`, colonne `x` = mois. `ROUND` d'Excel arrondit
au plus proche, **demi-unité vers l'extérieur** (≙ `Decimal.ROUND_HALF_UP`).

| Ligne | Rubrique | Formule Excel | Formule retenue |
|---|---|---|---|
| 3 | Mois | `=S!x19` (E3 : texte « Octobre » en dur) | — |
| 4 | N° d'ordre | constantes 1, 2, 3, 4 | ordre chronologique du mois |
| 6–11 | Gains | `=S!x21`, `x23`…`x27` | valeurs saisies |
| 12 | Salaire brut | `=SUM(x6:x11)` | somme des 6 gains |
| 13 | Assiette des cotisations | `=x6+x7+x11` | base + HS + autre prime |
| 14 | Assiette CNSS plafonnée | `=MIN(x13,P!B12)` | `min(assiette, plafond)` |
| 16 | CNSS salarié | `=ROUND(x14*P!B10,2)` | arrondi 2 déc. |
| 17 | AMO salarié | `=ROUND(x13*P!B11,2)` | assiette **non** plafonnée |
| 18 | Total cotisations salariales | `=x16+x17` | **somme des lignes arrondies** |
| 20 | CNSS patronal | `=ROUND(x14*P!B13,2)` | plafonnée |
| 21 | AMO patronal | `=ROUND(x13*P!B14,2)` | non plafonnée |
| 22 | Participation AMO | `=ROUND(x13*P!B15,2)` | non plafonnée |
| 23 | Formation professionnelle | `=ROUND(x13*P!B16,2)` | non plafonnée |
| 24 | Allocations familiales | `=ROUND(x13*P!B17,2)` | non plafonnée |
| 25 | Total cotisations patronales | `=SUM(x20:x24)` | **somme des lignes arrondies** |
| 27 | Revenu brut imposable | `=x6+x7*P!B28+x8*P!B29+x9*P!B30+x10*P!B31+x11*P!B32` | base à 100 % + Σ(élément × part imposable) — **non arrondi** |
| 28 | Taux frais pro | `=IF(x27*12<=P!B20,P!B21,P!B22)` | seuil testé sur le revenu **annualisé ×12**, comparaison `≤` |
| 29 | Frais professionnels | `=ROUND(MIN(x28*x27,P!B23/12),2)` | plafond mensuel = plafond annuel / 12 (non arrondi), puis arrondi 2 déc. |
| 30 | Cotisations salariales déduites | `=x18` | total ligne 18 |
| 31 | Net imposable (avant charges de famille) | `=MAX(0,x27-x29-x30)` | **non arrondi** |
| 32 | Déduction charges de famille (mensuelle) | `=ROUND(MIN(S!$B$10,P!B25)*P!B24/12,2)` | arrondi 2 déc. ; **nombre de personnes lu sur la fiche, identique pour tous les mois** |
| 33 | Net imposable après charges de famille | `=MAX(0,x31-x32)` | non arrondi |
| 34 | IR annuel | `=MAX(0, x33*12*INDEX(taux,MATCH(x33*12,bornes_inf,1)) - INDEX(déduction,MATCH(...)))` | méthode « taux × revenu − somme à déduire » sur le revenu annualisé ; `MATCH(…,1)` = dernière borne inférieure ≤ revenu ; **non arrondi** |
| 35 | IR mensuel | `=ROUND(x34/12,2)` | arrondi 2 déc. |
| 37 | Net avant arrondi | `=x12-x18-x35` | brut − cotisations salariales − IR |
| 38 | Arrondi | `=ROUND(ROUND(x37,0)-x37,2)` | écart vers le dirham entier le plus proche |
| 39 | Net à payer | `=ROUND(x37,0)` | arrondi au dirham |
| 40 | Coût total employeur | `=x12+x25` | brut + charges patronales |

Remarques sur la feuille `Calcul` :

- **Arrondis intermédiaires** : chaque cotisation, les frais professionnels, la déduction
  familiale et l'IR mensuel sont arrondis séparément. Le revenu brut imposable, le net
  imposable et l'IR annuel ne le sont pas. Le moteur reproduit exactement ces points.
- **Assiettes** : seule la CNSS (salariale et patronale) est plafonnée. AMO, participation AMO,
  formation professionnelle et allocations familiales portent sur l'assiette entière.
- **Indemnités** (panier, transport, représentation) : hors assiette sociale, et imposables
  à 0 % dans le paramétrage initial. Le classeur ne gère pas de plafond d'exonération par
  indemnité : c'est un taux d'imposabilité global par rubrique.
- **IR annualisé** : chaque mois est traité isolément (revenu mensuel × 12), sans
  régularisation sur les cumuls de l'année.
- Pour un revenu annuel compris strictement entre 40 000,00 et 40 000,01 (etc.), `MATCH`
  retient la tranche inférieure. Comportement reproduit.

### 2.4 Feuilles `Bulletin …` — rendu et cumuls

Les trois feuilles sont des copies identiques ; seule la valeur de `B6` change.

| Zone | Contenu | Formule |
|---|---|---|
| J1 | N° du mois | `=MATCH($B$6,S!$B$19:$D$19,0)` |
| A1–A3 | Raison sociale, adresse, « ICE : … – N° CNSS employeur : … » | liens vers `Paramètres` |
| A4 | Bandeau « DOCUMENT D'EXEMPLE … » | présent en Août et Septembre, **absent en Juillet** |
| A5 | « BULLETIN DE PAIE : MOIS ANNÉE » | `UPPER(B6)` + année de `Saisie` |
| A8:E14 | Identité (nom, matricule, naissance, CIN, CNSS, CIMR, situation, catégorie, déductions, embauche, fonction, département, banque, compte) | liens vers `Saisie` |
| A16:F17 | Congés : reliquat, acquis, pris, **solde = reliquat + acquis − pris** | `INDEX(Saisie…,J1)` |
| A19:G35 | Tableau Désignation / Base / Nombre ou taux / Gain / Retenue / Taux patronal / Part patronale | `INDEX(Calcul…,J1)` |
| D34 / E34 | Arrondi : en *Gain* s'il est positif, en *Retenue* s'il est négatif | `MAX(±arrondi,0)` |
| A37:G38 | Récapitulatif du mois : brut, cot. P.S, cot. P.P, **net imposable (ligne 31, avant charges de famille)**, IR, jours, net à payer | |
| A40:G41 | Cumuls « depuis le début de l'année (jusqu'à mois) » | `SUMPRODUCT((Calcul!$B$4:$D$4<=$J$1)*Calcul!…)` |
| A43 | « Mode de paiement : Virement » | texte fixe |
| D43:G43 | NET À PAYER … MAD | |
| A45 | « Pour vous aider à faire valoir vos droits, conservez ce bulletin de paie sans limitation de durée. » | |

Valeurs en cache des cumuls :

| Jusqu'à | Brut | Cot. P.S | Cot. P.P | Net imposable | IR | Jours | Net à payer |
|---|---:|---:|---:|---:|---:|---:|---:|
| Juillet | 7 366,51 | 366,43 | 1 146,57 | 3 167,30 | 0,00 | 26 | 7 000,00 |
| Août | 14 733,02 | 732,86 | 2 293,14 | 6 334,60 | 0,00 | 52 | 14 000,00 |
| Septembre | 22 099,53 | 1 099,29 | 3 439,71 | 9 501,90 | 0,00 | 78 | 21 000,00 |

### 2.5 Limites structurelles du classeur

1. **Trois mois seulement** : `MATCH` et `SUMPRODUCT` portent sur `B:D`. La colonne
   Octobre (E) est saisie et calculée mais ne peut être ni affichée ni cumulée ; `Calcul!E3`
   est un texte en dur, non relié à `Saisie!E19`.
2. **Un seul salarié** par classeur.
3. **Pas d'historisation** : modifier la fiche salarié ou un paramètre recalcule
   rétroactivement tous les mois, y compris ceux déjà édités.
4. **Personnes à charge** : valeur unique (`$B$10`) appliquée à tous les mois.
5. **Congés** : le reliquat est une saisie libre ; aucun report automatique (voir §5).
6. **Cumuls** : fondés sur un numéro d'ordre fixe, sans notion d'année ni de paie validée.
7. Aucune validation de saisie (montants négatifs, jours > 31, etc. acceptés).

## 3. Analyse du PDF de référence

PDF 1 page A4 portrait (595 × 842 pt), produit par WinDev 30, police Calibri, aucune image.

| Zone | Contenu observé |
|---|---|
| En-tête | Nom de société « TEST 2 » en gras italique, sans adresse ni ICE |
| Bandeau | Bloc gauche « BULLETIN DE PAIE : SEPTEMBRE » (sans année) ; bloc droit NOM PRÉNOM en majuscules |
| Identité | ADRESSE, Matricule, N° CIN, N° CNSS (« 0 »), Situation familiale, Date de naissance (« . . . . »), Date d'embauche (« . . . . »), Nombre déductions, Département, **ANCIENNETÉ**, Fonction, N° CIMR, Catégorie, Banque, N° compte bancaire. Plusieurs champs vides : la fiche du logiciel source n'était pas renseignée |
| Congés | 4 cases : RELIQUAT 0,00 · ACQUIS 1,50 · PRIS 0,00 · SOLDE 1,50 « Jour (s) » |
| Tableau | Colonnes Désignation / Base / Nombre ou taux / Part salariale (Gain, Retenu) / Part patronale (Taux, Retenu). Taux affichés en pourcentage sans symbole (« 2,26 ») |
| Gains | Salaire de base (jours) : **Base 209,10** (taux journalier = 5 436,51 / 26), Nombre 26,00, Gain 5 436,51 ; Prime de panier 930,00 ; Indemnité de transport 500,00 ; Indemnité de représentation 500,00 ; **les lignes à zéro (HS, autre prime) sont masquées** ; Salaire brut 7 366,51 |
| Cotisations | AMO 2,26 → 122,87 / 2,26 → 122,87 ; Participation AMO 1,85 → 100,58 ; CNSS 4,48 → 243,56 / 8,98 → 488,20 ; Formation prof. 1,60 → 86,98 ; Alloc. fam. 6,40 → 347,94 ; **Total 366,42 / 1 146,56** |
| IR | Ligne « Impôt sur le revenu », Base 3 167,31, aucun montant (IR nul) |
| Arrondi | **0,09** en retenue |
| Net | Salaire net 7 000,00 |
| Cumuls | Deux lignes : « SEPTEMBR » (mois) et « 2026 » (année) — colonnes Salaire brut, Cot. P.S, Cot. P.P, IR, Net imposable, Jours déclarés, Heures supplém., Mode de paiement (vide) — **cumul annuel = mois seul** |
| Net à payer | Encadré « NET À PAYER 7 000,00 » |
| Pied | Mention de conservation + bandeau décoratif bleu |

Défauts de rendu du PDF source (non reproduits) : accents corrompus
(« IndemnitÉ de transport - pÉrimÈtre urbain »), coquille « Côtisation », libellé de mois
tronqué « SEPTEMBR ».

## 4. Écarts entre le classeur et le PDF

| # | Rubrique (sept. 2026) | Classeur | PDF | Origine établie |
|---|---|---:|---:|---|
| E1 | Total cotisations salariales | 366,43 | 366,42 | Classeur : 243,56 + 122,87 (somme des lignes arrondies). PDF : `ROUND(5 436,51 × (4,48 % + 2,26 %), 2)` = ROUND(366,420774) = **366,42**. Les lignes du PDF (243,56 et 122,87) ne totalisent donc pas son propre total. |
| E2 | Total cotisations patronales | 1 146,57 | 1 146,56 | Même mécanisme : `ROUND(5 436,51 × 21,09 %, 2)` = ROUND(1 146,559959) = **1 146,56**, alors que 488,20 + 122,87 + 100,58 + 86,98 + 347,94 = 1 146,57. |
| E3 | Net imposable | 3 167,30 | 3 167,31 | Conséquence de E1 : 5 436,51 − 1 902,78 − 366,42 = 3 167,31. La note A47 du classeur affirme retrouver 3 167,31 : c'est inexact, le classeur donne 3 167,30. |
| E4 | Arrondi | 0,08 (retenue) | 0,09 (retenue) | Conséquence de E1 : 7 366,51 − 366,42 = 7 000,09 dans le PDF contre 7 000,08 dans le classeur. |
| E5 | Net à payer | 7 000,00 | 7 000,00 | Identique : l'arrondi au dirham absorbe l'écart. |
| E6 | Coût employeur | 8 513,08 | non affiché | PDF : 7 366,51 + 1 146,56 = 8 513,07 implicitement. |
| E7 | Cumuls annuels | Juil.→Sept. (22 099,53 de brut…) | = mois seul (7 366,51) | Le logiciel source ne contenait que la paie de septembre. Ce n'est pas une règle de calcul différente. |
| E8 | « Base » du salaire de base | vide | 209,10 | Taux journalier = ROUND(5 436,51 / 26, 2), purement informatif. |
| E9 | Lignes de gains nulles | affichées (« - ») | masquées | Présentation. |
| E10 | Champs d'identité | 14 champs | + Adresse salarié, Ancienneté | Présentation ; pas d'incidence de calcul (pas de prime d'ancienneté dans le PDF). |
| E11 | Année dans le titre | « SEPTEMBRE 2026 » | « SEPTEMBRE » | Présentation. |

Les écarts E1 à E4 ne proviennent ni des taux, ni des assiettes : ce sont deux **méthodes
d'arrondi des totaux** différentes, vérifiées au centime.

## 5. Congés

- Règle du classeur et du PDF : **Solde = Reliquat + Acquis − Pris**, les trois termes étant
  saisis chaque mois.
- Le classeur ne reporte pas le solde : en août et septembre, le reliquat saisi vaut 0 alors
  que le solde du mois précédent est 1,50. Il est impossible de savoir si « reliquat » désigne
  le report du mois précédent (et la saisie d'exemple est alors incomplète) ou un reliquat
  d'exercice antérieur (et le solde n'est alors qu'un solde mensuel). **Ambiguïté A3.**

## 6. Hypothèses non vérifiables

| # | Hypothèse | Pourquoi non vérifiable |
|---|---|---|
| A1 | La méthode exacte de WinDev pour des assiettes différentes (CNSS plafonnée ≠ assiette AMO) | Le PDF n'a qu'un cas, où les deux assiettes sont égales. Le mode « taux cumulé » est reconstitué par `ROUND(Σ assiette_i × taux_i, 2)` |
| A2 | Le net imposable du récapitulatif est-il avant ou après charges de famille ? | Le classeur prend la ligne 31 (avant) ; le PDF a 0 personne à charge, donc les deux coïncident |
| A3 | Sémantique du reliquat de congés | voir §5 |
| A4 | Conformité légale des taux, plafonds, exonérations et du barème | hors du périmètre d'un audit de fichiers |
| A5 | Arrondi Excel sur nombres binaires | Excel calcule en double précision ; le moteur calcule en décimal exact. Les deux coïncident pour tous les cas de référence ; un écart d'un centime reste théoriquement possible sur une valeur se terminant exactement par 5 au 3ᵉ décimale après erreur de représentation binaire |

## 7. Décisions de conception

| # | Décision | Justification |
|---|---|---|
| D1 | Le moteur reproduit les formules du classeur ; mode par défaut des totaux = **somme des lignes arrondies** (`methode_totaux = "somme_lignes"`) | Le classeur est la référence de calcul ; ce mode garantit que les lignes affichées totalisent le total |
| D2 | Le mode du PDF est disponible comme paramètre explicite (`methode_totaux = "taux_cumule"`), daté et historisé comme tout paramètre | Permet de reproduire le PDF au centime si un professionnel le valide ; jamais appliqué silencieusement |
| D3 | Récapitulatif et cumul « Net imposable » = ligne 31 (avant charges de famille), comme le classeur ; la base affichée sur la ligne IR est le net imposable **après** charges de famille (assiette réelle du barème) | Fidélité au classeur pour les montants ; lisibilité pour la ligne IR (identique au PDF sur l'exemple) |
| D4 | Personnes à charge : prises sur la fiche salarié **figée dans la paie** au moment du calcul | Corrige la limite 2.5-4 sans changer la formule |
| D5 | Congés : règle du classeur conservée (trois saisies mensuelles). L'application **propose** le solde du dernier mois clôturé comme reliquat, sans l'imposer, et avertit si le reliquat saisi en diffère | Résout A3 sans trancher silencieusement ni compter deux fois |
| D6 | Cumuls = paies **clôturées** de l'année civile, mois < mois courant, + paie courante ; versions remplacées exclues ; cumuls figés à la clôture | Reproduit `SUMPRODUCT(n° ≤ mois)` en le fiabilisant |
| D7 | Clôture interdite si un mois antérieur de l'année a une paie non clôturée ; mois manquants après l'embauche signalés et à confirmer | Évite des cumuls figés faux |
| D8 | Taux journalier (Base 209,10) calculé par le moteur, champ informatif | Rendu du PDF sans calcul dans le code PDF |
| D9 | Lignes de gains nulles masquées sur le bulletin (sauf salaire de base) | Rendu du PDF |
| D10 | Ajout de l'adresse salarié et de l'ancienneté (calculée, affichage seul) | Champs du PDF ; **aucune prime d'ancienneté** car absente des deux sources |
| D11 | Pas de proratisation automatique (entrée/sortie en cours de mois) : la base et les jours sont saisis | Aucune règle dans les sources |
| D12 | Arrondi `ROUND_HALF_UP` sur `Decimal` | Équivaut à `ROUND` d'Excel (demi-unité vers l'extérieur) |
| D13 | Données de démonstration entièrement inventées (« SOCIÉTÉ EXEMPLE SARL », salarié « EXEMPLE ») avec les montants du classeur | Aucune donnée potentiellement réelle dans le dépôt |
| D14 | Jours déclarés : bloquant au-delà de 31, avertissement au-delà de 26 | Le classeur n'a aucun contrôle ; 26 jours est le maximum déclaré dans l'exemple |

## 8. Tests de référence

Implémentés dans `tests/test_reference_excel.py` et `tests/test_ecarts_pdf.py`.

| Cas | Attendu (mode classeur) | Attendu (mode taux cumulé) |
|---|---:|---:|
| Salaire brut | 7 366,51 | 7 366,51 |
| CNSS salariale / AMO salariale | 243,56 / 122,87 | 243,56 / 122,87 |
| Total cotisations salariales | 366,43 | 366,42 |
| Total cotisations patronales | 1 146,57 | 1 146,56 |
| Frais professionnels (35 %) | 1 902,78 | 1 902,78 |
| Net imposable | 3 167,30 | 3 167,31 |
| IR | 0,00 | 0,00 |
| Arrondi | −0,08 | −0,09 |
| Net à payer | 7 000,00 | 7 000,00 |
| Coût employeur | 8 513,08 | 8 513,07 |
| Taux journalier | 209,10 | 209,10 |
| Cumuls Juil.→Sept. | 22 099,53 / 1 099,29 / 3 439,71 / 9 501,90 / 0 / 78 / 21 000 | — |

Tests complémentaires : barème (bornes, passage de tranche), frais professionnels (seuil,
plafond), plafond CNSS, déduction familiale (plafonnement à 6), parts imposables, arrondi
positif et négatif, congés, cumuls avec rectification, passage décembre → janvier.
