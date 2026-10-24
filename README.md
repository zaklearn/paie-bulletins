# Générateur de bulletins de paie (Maroc) — Streamlit

Application web qui reprend le processus du classeur Excel `paie_exemple_EXEMPLE_SARL.xlsx` et la
présentation du bulletin `HBN Etat_Bull 09-2026.pdf` : entreprise, salariés, paramètres de paie
datés, saisie mensuelle, calcul, clôture, bulletins PDF archivés, cumuls annuels, historique,
exports et sauvegardes.

> **Avertissement.** Les taux, plafonds, exonérations et le barème de l'IR sont des paramètres
> configurables repris du classeur. Ils ne sont pas certifiés : leur conformité légale doit être
> validée par un professionnel compétent. Les données de démonstration sont entièrement fictives.

## Fonctionnalités

- **Tableau de bord** : entreprise active, salariés, mois ouverts/clôturés, dernières paies, alertes.
- **Entreprise** : raison sociale, adresse, ICE, CNSS employeur, RC, IF, coordonnées, logo.
- **Salariés** : tous les champs du classeur + adresse, date de sortie, mode de paiement ;
  recherche, activation/désactivation, doublons refusés, identifiants masqués à l'écran.
- **Paramètres** : versions avec date d'effet, motif obligatoire, validation, historique ;
  jamais rétroactives sur les paies clôturées.
- **Saisie mensuelle** : tous les mois de toutes les années, préremplissage signalé, contrôles,
  prévisualisation instantanée.
- **Calcul et validation** : statuts *Brouillon → Calculée → Clôturée*, contrôles avant clôture,
  aperçu PDF provisoire, clôture confirmée, rectification tracée avec conservation des versions.
- **Bulletins PDF** A4 calqués sur le modèle, archivés en base avec empreinte SHA-256 :
  `bulletin_2026-09_0001.pdf` (`_v2` pour une rectification).
- **Cumuls annuels** depuis les seules paies clôturées, figés à l'émission.
- **Récapitulatifs et exports** CSV/Excel (sans CIN, CNSS ni coordonnées bancaires).
- **Sauvegarde / restauration** et **journal des opérations**.

## Prérequis

Python 3.10 ou plus récent (testé sous 3.10 et 3.13). Aucune autre dépendance système (SQLite est inclus dans Python,
le PDF est produit par ReportLab).

## Installation et lancement

```bash
cd paie
python3 -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # facultatif : chemins, mot de passe, démonstration
streamlit run app.py
```

Au premier lancement, la base `data/paie.db` est créée, la version initiale des paramètres
(valeurs du classeur) est enregistrée et, si `PAIE_SEED_DEMO=1`, une démonstration fictive est
chargée (juillet à septembre 2026 clôturés, montants identiques au classeur).

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
# Comparaison cellule par cellule avec le classeur source (non versionné) :
PAIE_REFERENCE_XLSX=/chemin/paie_exemple_EXEMPLE_SARL.xlsx pytest -q
```

Résultats détaillés : [`docs/TESTS.md`](docs/TESTS.md) — 162 tests réussis.

## Configuration (`.env`)

| Variable | Défaut | Rôle |
|---|---|---|
| `PAIE_DB_PATH` | `data/paie.db` | Fichier de base SQLite |
| `PAIE_BACKUP_DIR` | `data/backups` | Répertoire des sauvegardes |
| `PAIE_AUTH_PASSWORD_HASH` | vide | Hachage du mot de passe d'accès (`python scripts/hash_password.py`) ; vide = accès libre, usage local uniquement |
| `PAIE_SEED_DEMO` | `1` | Charge la démonstration fictive dans une base vide ; mettre `0` en production |

## Base de données

SQLite, une connexion courte par opération, transactions `BEGIN IMMEDIATE`, mode WAL,
migrations versionnées (`src/repositories/db.py`). Montants stockés en décimal exact. Les règles
critiques sont aussi garanties par la base : une seule paie de travail et une seule paie
clôturée en vigueur par salarié et par mois ; paies clôturées, bulletins archivés, versions de
paramètres et journal non modifiables. Chaque paie conserve une copie des paramètres, de la
fiche salarié et de la fiche entreprise appliqués. Détails : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Calcul

Moteur Python pur (`src/calculations/engine.py`), en `Decimal`, une fonction par ligne de la
feuille `Calcul`, arrondis aux mêmes étapes que le classeur (`ROUND` d'Excel = demi-unité vers
l'extérieur). Audit complet des formules : [`docs/AUDIT_SOURCES.md`](docs/AUDIT_SOURCES.md).

**Écarts classeur / PDF.** Le PDF affiche 366,42 et 1 146,56 de cotisations quand le classeur
calcule 366,43 et 1 146,57 : le logiciel du PDF arrondit le *taux cumulé* × assiette, le classeur
additionne les lignes arrondies. Écart établi au centime, avec ses conséquences (net imposable
3 167,31 / 3 167,30, arrondi 0,09 / 0,08, net identique 7 000,00). La méthode du classeur est
retenue par défaut ; celle du PDF est un paramètre explicite (« Méthode des totaux »).

## Génération des PDF

`src/pdf/bulletin.py` (ReportLab, A4 portrait, polices standard couvrant les accents) met en
forme les montants déjà calculés, sans aucun calcul. Le PDF est produit à la clôture, dans la
même transaction que celle-ci, et stocké en base : il ne peut pas être régénéré par-dessus.

## Sauvegarde des données

Interface **Sauvegardes et administration**, ou `python scripts/backup_db.py` (planifiable).
Restauration vérifiée et précédée d'une sauvegarde automatique. Procédures :
[`docs/DEPLOIEMENT.md`](docs/DEPLOIEMENT.md).

## Documentation

- [`docs/AUDIT_SOURCES.md`](docs/AUDIT_SOURCES.md) — audit du classeur et du PDF, écarts, hypothèses, décisions
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — structure, modèle de données, procédure, cumuls
- [`docs/UTILISATION.md`](docs/UTILISATION.md) — guide de l'utilisateur
- [`docs/DEPLOIEMENT.md`](docs/DEPLOIEMENT.md) — déploiement, sécurité, sauvegarde, restauration, conservation
- [`docs/TESTS.md`](docs/TESTS.md) — résultats des tests
- [`log.md`](log.md) — journal des versions et des correctifs

## Limites connues

- Mono-entreprise par base ; usage mono-poste ou petit serveur (SQLite). Pas de comptes
  individuels ni de rôles : un mot de passe partagé et un nom déclaratif pour le journal.
- Règles limitées à celles du classeur : pas de prime d'ancienneté, de CIMR calculée, de
  proratisation automatique, d'heures supplémentaires calculées à partir d'heures et de taux,
  de plafonds d'exonération par indemnité (taux d'imposabilité global par rubrique), de
  régularisation annuelle de l'IR, ni de contrôle du SMIG.
- Le reliquat de congés reste une saisie (proposé depuis le dernier mois clôturé) : la règle de
  report n'est pas définie par les sources (ambiguïté A3 de l'audit).
- Pas de chiffrement de la base au repos ni de HTTPS intégré (à assurer par l'hébergement).
- Champs numériques de saisie affichés avec un point décimal (limite de Streamlit) ; tous les
  affichages de résultats et le PDF sont au format français.

## Données personnelles

Ne versionnez jamais `.env`, une base `.db`, une sauvegarde, un bulletin ou les fichiers source
de référence : le `.gitignore` les exclut. Les tests et la démonstration n'utilisent que des
identités inventées. Voir les mesures et leurs limites dans `docs/DEPLOIEMENT.md`.
