# Résultats des tests

## Version 1.2.1 — 2026-10-26

| Exécution | Résultat |
|---|---|
| Python 3.13.17 / streamlit 1.66.1, avec le classeur source | **211 réussis**, 0 échec |
| Python 3.10.20 / streamlit 1.65.0, avec le classeur source | **211 réussis**, 0 échec |
| Python 3.10.20, sans classeur | 210 réussis, 1 ignoré |
| Ruff (E, F, W, B) | aucune remarque |

Nouveau : `test_mobile_download.py` (5 tests ; les 2 tests de pages échouent sans le correctif).
Serveur réel + Chromium (Pixel 7 émulé et ordinateur) : le lien « Télécharger sur mobile » des pages
Archives et Calcul fournit un fichier d'empreinte SHA-256 identique au bulletin archivé.
Non vérifié : vrai téléphone sur Streamlit Cloud.


## Version 1.2.0 — 2026-10-26

Environnements neufs installés avec `pip install -r requirements-dev.txt`.

| Exécution | Résultat |
|---|---|
| Python 3.13.17, avec `PAIE_REFERENCE_XLSX` (classeur source local) | **206 réussis**, 0 échec, 0 ignoré |
| Python 3.10.20, avec `PAIE_REFERENCE_XLSX` | **206 réussis**, 0 échec, 0 ignoré |
| Python 3.10.20, sans classeur | 205 réussis, 1 ignoré (comparaison cellule par cellule) |
| Ruff (E, F, W, B) | aucune remarque |
| État initial (1.1.0) | 173 réussis |

Nouveaux tests : `test_access_control.py` (25) et `test_backup_integrity.py` (8). Exécutés sur le
code 1.1.0, 26 de ces 33 tests échouent (les 7 autres sont des contrôles de non-régression) : ils
détectent les défauts corrigés.

Vérifications sur un serveur Streamlit réel (Chromium) :
- sans `PAIE_AUTH_PASSWORD_HASH` ni dérogation : `/`, `/administration`, `/parametres`, `/saisie`
  affichent « Configuration incomplète », sans menu ;
- avec mot de passe : `/administration` → « Connexion » ; après connexion, « Version 1.2.0 » ;
  après « Se déconnecter » → « Connexion », puis `/administration` → « Connexion ».
- Constat résiduel : après déconnexion, le menu reste affiché jusqu'au rechargement de la page ;
  un clic sur un lien ramène à « Connexion » sans afficher de donnée.

Non vérifié : comportement sur Streamlit Community Cloud (aucun accès depuis cet environnement).

## Version 1.1.0 et antérieures

Également exécutée sous Python 3.10.20 (pandas 2.3.3, streamlit 1.65.0) : 161 réussis, 1 ignoré.

Exécution du 23/10/2026, environnement virtuel neuf installé avec `pip install -r requirements-dev.txt`
(Python 3.13, streamlit 1.66.1, reportlab 5.1.0, pandas 3.1.0, openpyxl 3.1.5, pytest 9.1.1).

```
$ pytest -q
161 passed, 1 skipped in 8.27s          # skipped : classeur source absent du dépôt

$ PAIE_REFERENCE_XLSX=/chemin/paie_exemple_EXEMPLE_SARL.xlsx pytest -q
162 passed, 1 warning in 9.16s          # warning : extension de validation x14 ignorée par openpyxl
```

| Fichier | Tests | Objet |
|---|---:|---|
| `test_reference_excel.py` | 39 | 36 rubriques de septembre 2026 = valeurs du classeur ; cumuls Juillet→Septembre des trois feuilles Bulletin ; note A47 (3 167,31) démentie ; **comparaison cellule par cellule** des 31 lignes de `Calcul` × 4 mois avec les valeurs en cache du classeur (si `PAIE_REFERENCE_XLSX` est défini) |
| `test_ecarts_pdf.py` | 7 | Écarts E1–E8 : méthode du classeur (366,43 / 1 146,57 / 3 167,30 / −0,08) et méthode du PDF (366,42 / 1 146,56 / 3 167,31 / −0,09), net identique 7 000, taux journalier 209,10, divergence avec CNSS plafonnée |
| `test_engine.py` | 40 | Arrondi Excel, conversion décimale, assiettes, plafond CNSS (y compris borne exacte), parts imposables, seuil et plafond des frais professionnels, déduction familiale plafonnée à 6, recherche de tranche équivalente à `MATCH(…;1)` (bornes 40 000 / 40 000,005 / 40 000,01…), IR par tranche, paie complète avec IR et personnes à charge, arrondi positif/négatif, congés |
| `test_workflow.py` | 35 | Création/recherche/doublons de salariés, salarié désactivé, période avant embauche, cycle brouillon → calculée → clôturée, invalidation après modification, clôture sans calcul refusée, **paie clôturée non modifiable** (service et déclencheurs SQLite), double clôture refusée, unicité des paies actives, recalcul exigé après changement de paramètres ou de fiche, historique figé (fiche, PDF), paramètres non rétroactifs et période de validité, cumuls figés = classeur, brouillons exclus et ordre chronologique imposé, mois futurs exclus, mois manquant à confirmer, **décembre → janvier**, **douze mois**, rectification avec conservation de la version antérieure, absence de double comptage, avertissement sur les bulletins postérieurs, journal sans données sensibles, préremplissage, reliquat de congés, indépendance des mois, suppression de brouillon, **persistance après redémarrage** |
| `test_pdf.py` | 9 | A4 une page, présence de toutes les rubriques et montants, lignes nulles masquées, **valeurs extrêmes sans débordement**, montants dans leurs colonnes, nom de fichier et versions, refus d'une paie non calculée, rendu depuis la copie figée, logo |
| `test_services_misc.py` | 12 | Validations (saisie, salarié, entreprise, barème avec chevauchement), livre de paie et récapitulatifs, **exports sans données sensibles**, tableau de bord, sauvegarde/restauration, fichier de restauration invalide, mot de passe, formats français, démonstration idempotente |
| `test_non_regression.py` | 7 | 6 scénarios figés dans `tests/golden/results.json` (référence, mode PDF, bas salaire, cadre IR 34 %, haut salaire IR 38 % avec 6 personnes à charge, temps partiel) |
| `test_app_smoke.py` | 13 | Exécution réelle des 9 pages Streamlit (`AppTest`), affichage de l'entreprise, paie clôturée en lecture seule, enregistrement d'un brouillon depuis l'interface, écran de connexion |

## Vérifications complémentaires effectuées

- Parcours complet dans Chromium (Playwright) sur le serveur Streamlit réel : saisie d'octobre
  préremplie → brouillon → calcul → confirmation → clôture → téléchargement de
  `bulletin_2026-10_0001.pdf` ; cumuls Juillet→Octobre = 29 466,04 de brut ; aucune exception.
- Comparaison visuelle du bulletin généré avec le PDF de référence (structure, colonnes,
  libellés, cumuls, encadré net à payer).
- Bulletin « valeurs extrêmes » (noms et libellés très longs, montants à 7 chiffres) : aucun
  chevauchement, réduction de police puis troncature « … ».
- Analyse statique `ruff` (règles E, F, W, B) : aucune anomalie.

## Anomalies trouvées et corrigées pendant les tests

1. Le validateur de barème acceptait deux tranches qui se chevauchent : contrôle ajouté.
2. Mise en page de la saisie : le salaire de base apparaissait sous les colonnes ; corrigé.
3. Tableau de bord : ordre des dernières paies instable à horodatage égal ; corrigé.

## Régénérer les références de non-régression

Uniquement après un changement de calcul voulu et documenté :
`python scripts/update_golden.py`, puis examen du diff de `tests/golden/results.json`.
