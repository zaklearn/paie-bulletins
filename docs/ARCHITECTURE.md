# Architecture

## Vue d'ensemble

```
app.py                         point d'entrée Streamlit : authentification + navigation
pages/                         une page par écran (interface uniquement, aucune règle métier)
  dashboard.py  entreprise.py  salaries.py  saisie.py  calcul.py
  archives.py   exports.py     parametres.py  administration.py
src/
  config.py                    variables d'environnement (.env facultatif)
  formatting.py                formats français (montants, taux, dates, ancienneté, masquage)
  models/
    parameters.py              PayrollParameters, IRBracket, méthodes de totaux
    payroll.py                 MonthlyInput, PayslipResult, Cumuls, statuts, mois
    entities.py                Company, Employee (+ copies figées « snapshot »)
  calculations/                moteur pur, sans Streamlit ni base de données
    money.py                   Decimal, excel_round (ROUND d'Excel)
    defaults.py                valeurs initiales de la feuille Paramètres (seul endroit)
    engine.py                  une fonction par ligne de la feuille Calcul
    cumuls.py                  addition des paies faisant foi
  validation/validators.py     contrôles bloquants (erreurs) et non bloquants (avertissements)
  repositories/
    db.py                      SQLite : connexion, transactions, migrations, déclencheurs
    repos.py                   lecture/écriture des tables (SQL paramétré)
  services/                    règles de gestion et transactions
    master_data.py             entreprise, salariés, versions de paramètres
    payroll.py                 procédure mensuelle : brouillon → calcul → clôture → rectification
    reporting.py               tableau de bord, livre de paie, récapitulatifs, exports, journal
    backup.py                  sauvegarde / restauration (API de sauvegarde SQLite)
    auth.py                    mot de passe d'accès (PBKDF2-SHA256)
    demo.py                    données fictives de démonstration
  pdf/bulletin.py              rendu ReportLab du bulletin (mise en forme uniquement)
  ui/                          composants Streamlit partagés
tests/                         pytest : moteur, références, écarts, procédure, PDF, UI, non-régression
scripts/                       hachage du mot de passe, sauvegarde planifiable, références de non-régression
docs/                          audit des sources, architecture, utilisation, déploiement, tests
data/                          base et sauvegardes locales (non versionnées)
```

Dépendances autorisées : `pages → ui → services → (calculations, repositories, pdf, validation) → models`.
Le moteur (`calculations`) ne dépend que de `models` : il est testable isolément et réutilisable
hors Streamlit.

## Modèle de données (SQLite)

| Table | Rôle | Contraintes principales |
|---|---|---|
| `company` | Entreprise (une ligne, `id = 1`) | — |
| `employees` | Fiches salariés courantes | `matricule` unique ; CIN et CNSS uniques s'ils sont renseignés ; jamais supprimées (désactivation) |
| `parameter_sets` | Versions de paramètres (`valid_from` = « AAAA-MM ») | `valid_from` unique ; **immuables** (déclencheur) |
| `payslips` | Une ligne par version de paie (salarié × année × mois × version) | `UNIQUE(employee, année, mois, version)` ; **au plus une version de travail** (`brouillon`/`calculee`) et **au plus une version clôturée en vigueur** par salarié et mois (index uniques partiels) ; versions clôturées **non modifiables et non supprimables** (déclencheurs), seule la transition `cloturee → remplacee` est admise |
| `documents` | Bulletins PDF archivés (contenu binaire + SHA-256) | un document par version ; non modifiables, non supprimables |
| `audit_log` | Journal des opérations | ajout seul |
| `schema_version` | Version du schéma | migrations ordonnées dans `db.py` |

Chaque paie calculée conserve en JSON : la saisie, le résultat complet, les cumuls, une
**copie des paramètres appliqués**, une copie de la fiche salarié et de la fiche entreprise.
Une paie clôturée est donc explicable et reproductible même si les référentiels changent.

Les montants sont stockés sous forme de texte décimal exact (`"5436.51"`), jamais en flottant.

## Procédure mensuelle

```
 Saisie mensuelle                           Calcul et validation
 ───────────────                            ────────────────────
 1 période  2 salarié                       6 calcul (paramètres en vigueur, fiche, cumuls)
 3 fiche + paramètres en vigueur            7 récapitulatif gains / retenues / charges / net
 4 préremplissage (dernier mois clôturé)    8 contrôles de clôture
 5 saisie + contrôles + prévisualisation    10 clôture (confirmation)  → 11 PDF → 12 archivage
 9 brouillon                                13 cumuls figés            14 consultation / téléchargement
```

| Transition | Service | Garde-fous |
|---|---|---|
| saisie → brouillon | `payroll.save_draft` | validation ; période ≥ embauche et ≤ sortie ; salarié actif ; refus si le mois est clôturé sans rectification ouverte |
| brouillon/calculée → calculée | `payroll.calculate` | entreprise renseignée ; paramètres en vigueur pour la période |
| modification d'une paie calculée | `payroll.save_draft` | résultat invalidé, retour en brouillon |
| calculée → clôturée | `payroll.close` | recalcul de contrôle identique au calcul affiché (sinon « recalculez ») ; mois antérieurs de l'année sans paie ouverte ; mois manquants et bulletins postérieurs déjà clôturés signalés et à confirmer ; PDF généré et archivé **dans la même transaction** |
| clôturée → rectification | `payroll.open_rectification` | motif obligatoire ; une seule rectification ouverte |
| clôture d'une rectification | `payroll.close` | ancienne version → `remplacee` (conservée avec son PDF) ; nouvelle → `cloturee` |

## Cumuls

`cumuls(mois M) = Σ résultats des paies clôturées en vigueur de la même année et des mois < M
+ paie du mois M`. Les versions remplacées et les brouillons sont exclus ; l'année civile remet
les cumuls à zéro. Les cumuls sont **figés à la clôture** : un bulletin émis n'est jamais
modifié a posteriori. Une rectification d'un mois antérieur est signalée lors de sa clôture et
se répercute sur les bulletins suivants non encore clôturés.

## Concurrence et limites de SQLite

- Transactions `BEGIN IMMEDIATE` (verrou d'écriture dès le début), mode WAL, délai d'attente
  de 10 s : adapté à un poste unique ou à quelques utilisateurs simultanés sur le même serveur.
- Pas de verrouillage optimiste d'un formulaire à l'autre : deux personnes modifiant la même
  paie en même temps verront la dernière écriture l'emporter (la clôture, elle, revérifie tout).
- Pour un usage multi-utilisateurs réel : PostgreSQL (les contraintes et déclencheurs se
  transposent), comptes individuels avec rôles, et un service d'API séparé de l'interface.
  Voir `docs/DEPLOIEMENT.md`.
