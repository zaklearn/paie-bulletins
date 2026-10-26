# Journal des versions

Historique des changements du générateur de bulletins de paie.

- **Numérotation** `MAJEUR.MINEUR.CORRECTIF` :
  - *majeur* : changement incompatible (schéma de base, règle de calcul modifiée) ;
  - *mineur* : nouvelle fonctionnalité compatible ;
  - *correctif* : correction sans changement de fonctionnalité.
- **Version en cours** : `src/__init__.py` (`__version__`), affichée en bas du menu de l'application.
- **Commits** : identifiants de la session de développement (branche `claude/keen-einstein-d9w1iz` du
  dépôt `suivitangerinecentral`). Les commits du dépôt `zaklearn/paie-bulletins` ont d'autres
  identifiants : voir le tableau de correspondance en fin de fichier.
- **Calculs** : toute modification d'un résultat de paie doit figurer ici, avec la régénération des
  références de non-régression (`python scripts/update_golden.py`).

---

## [1.2.1] — 2026-10-26

**Type :** correctif (téléchargement sur mobile).

### Corrigé
- **Bouton « Télécharger bulletin… » sans effet sur Android** (Samsung A52, Chrome et Firefox),
  alors qu'il fonctionne sur ordinateur.
  - *Diagnostic :* en local, le téléchargement fonctionne en Android émulé. Sur Streamlit Cloud,
    l'hébergeur fait ouvrir le fichier par `st.download_button` dans un nouvel onglet
    (option `enforceDownloadInNewTab` du code Streamlit), ouverture que les navigateurs mobiles
    bloquent sans message.
  - *Confirmation :* sur le téléphone, l'adresse sans le cadre de Streamlit Cloud
    (`…/~/+/`) ouvre le PDF.
  - *Correctif :* sous le bouton existant, un lien « 📱 Télécharger sur mobile » qui télécharge
    sur place le **même PDF archivé** (données intégrées, `target="_self"`), affiché par `st.iframe`
    dans un cadre où Streamlit autorise les téléchargements. Pages Archives et Calcul (paie
    clôturée). Le bouton d'origine est conservé.
  - *Écartés :* lien dans `st.markdown` (Streamlit impose un nouvel onglet), `st.html` (adresse du
    fichier supprimée par sécurité), `components.html` (obsolète selon Streamlit).

### Modifié
- `requirements.txt` : `streamlit>=1.65` (nécessaire pour `st.iframe` ; versions testées 1.65.0 et
  1.66.1, Streamlit Cloud installe 1.66.1).

### Tests
- `tests/test_mobile_download.py` (5) : octets identiques au document archivé, nom de fichier,
  `target="_self"`, nom et libellé échappés (pas d'injection), aucun lien pour une paie non
  clôturée. Sans le correctif des pages, les 2 tests de pages échouent.
- Serveur réel, Chromium (Pixel 7 émulé et ordinateur), pages Archives et Calcul : fichier reçu,
  empreinte SHA-256 identique à celle du bulletin archivé.
- Non vérifié : vrai téléphone sur Streamlit Cloud (inaccessible depuis l'environnement de test).

### Fichiers
`src/ui/common.py`, `views/archives.py`, `views/calcul.py`, `requirements.txt`, `src/__init__.py`,
`tests/test_mobile_download.py`, `log.md`, `docs/TESTS.md`, `docs/UTILISATION.md`

### Calculs
Aucun changement.

### Limites
Les autres boutons de téléchargement (aperçu provisoire, CSV/Excel, sauvegardes) n'ont pas de
lien mobile ; sur téléphone, utiliser l'adresse `…/~/+/` ou un ordinateur.

---

## [1.2.0] — 2026-10-26

**Type :** évolution mineure — **correctifs de sécurité et d'intégrité**, changement de
comportement de la configuration. Audit contrôlé (Étapes A à E), correctifs C1 à C4.

### Corrigé
- **C1 — Ouverture silencieuse sans mot de passe.** Si `PAIE_AUTH_PASSWORD_HASH` était vide,
  l'application s'ouvrait à tous (`src/config.py`, `require_login`). Elle reste désormais **fermée**
  (« Configuration incomplète », aucune page exécutée), sauf dérogation explicite
  `PAIE_ALLOW_NO_AUTH=1` réservée à l'usage local.
- **C2 — Restauration d'une sauvegarde altérée.** Une sauvegarde dont les déclencheurs
  d'immuabilité avaient été supprimés était acceptée ; après restauration, une paie clôturée
  pouvait être modifiée et son PDF archivé supprimé, et `migrate()` ne recréait pas les
  protections. `validate_backup_file` compare maintenant déclencheurs et index au schéma issu des
  migrations (absents, modifiés ou ajoutés → refus) et contrôle les références entre tables
  (`PRAGMA foreign_key_check`). Le refus intervient avant toute action sur la base.

### Ajouté
- **C3 — Bouton « Se déconnecter »** dans le menu lorsqu'un mot de passe est configuré.
- **C4 — Traçabilité** : procédure « Vérifier la version réellement en service »
  (`docs/DEPLOIEMENT.md`) ; tableau de correspondance limité aux éléments vérifiés.
- Variable `PAIE_ALLOW_NO_AUTH` (défaut `0`), documentée dans `.env.example`, `README.md` et
  `docs/DEPLOIEMENT.md`.

### Tests
- `tests/test_access_control.py` (25) : configuration sûre par défaut, application et 9 pages
  bloquées sans secret, mode local explicite, connexion valide/invalide, nom obligatoire,
  nouvelle session, déconnexion, navigation.
- `tests/test_backup_integrity.py` (8) : 5 altérations de schéma refusées sans toucher à la base
  actuelle, références incohérentes refusées, restauration valide conservant protections et PDF,
  base de l'application conforme.
- `tests/test_app_smoke.py` : le mode sans mot de passe y est déclaré explicitement
  (`PAIE_ALLOW_NO_AUTH=1`) ; le test des pages vérifie désormais le titre de chaque page (il
  passait auparavant même lorsque l'application était bloquée).
- Preuve : sur le code 1.1.0, 26 des 33 nouveaux tests échouent ; les 7 autres sont des contrôles
  de non-régression.

### Fichiers
`src/config.py`, `src/ui/common.py`, `src/services/backup.py`, `src/__init__.py`, `.env.example`,
`README.md`, `docs/DEPLOIEMENT.md`, `docs/TESTS.md`, `docs/UTILISATION.md`, `log.md`,
`tests/test_access_control.py`,
`tests/test_backup_integrity.py`, `tests/test_app_smoke.py`

### Calculs
Aucun changement. Modules de calcul, modèles, schéma SQL et références `golden` non modifiés.

### Action requise au déploiement
Vérifier que `PAIE_AUTH_PASSWORD_HASH` est défini dans les secrets Streamlit Cloud **avant** de
pousser : sinon l'application affichera « Configuration incomplète ». En local, copier
`.env.example` en `.env` (il contient `PAIE_ALLOW_NO_AUTH=1`) ou définir un mot de passe.

---

## [1.1.0] — 2026-10-24

**Type :** évolution mineure (suivi des versions).

### Ajouté
- Le numéro de version est affiché en bas du menu de l'application, ce qui permet de vérifier
  quelle version est déployée sur Streamlit Cloud.
- Ce journal (`log.md`).
- Test : la version affichée doit figurer dans ce journal.

### Fichiers
`src/__init__.py`, `app.py`, `log.md`, `tests/test_app_smoke.py`

### Calculs
Aucun changement.

---

## [1.0.4] — 2026-10-24 — commit `52a3c97`

**Type :** correctif de **sécurité**. Mise à jour impérative pour tout déploiement protégé par mot
de passe.

### Corrigé
- **Contournement de l'authentification.** Avant la connexion, l'application ne construit pas son
  menu. Streamlit fabriquait alors un menu automatique à partir du dossier `pages/` (« app »,
  « administration », « archives »…) et chaque page s'ouvrait **sans mot de passe**. Constaté sur
  `ezzinepaie.streamlit.app` depuis un téléphone, puis reproduit sur un serveur de test.

### Modifié
- Le dossier `pages/` devient `views/` : Streamlit ne crée plus de menu automatique.
- `app.py` et les liens internes pointent vers `views/`.
- `docs/ARCHITECTURE.md` explique pourquoi ce dossier ne doit pas s'appeler `pages`.

### Tests
- Un test échoue si un dossier `pages/` réapparaît ; il a été vérifié en échec avec l'ancien dossier.
- 9 tests vérifient que, sans connexion, chaque page renvoie vers l'écran « Connexion ».
- Vérification sur un serveur réel avec mot de passe : `/`, `/administration` et `/parametres`
  renvoient vers « Connexion », sans menu ; après connexion, le menu normal de 9 pages apparaît.
- Résultat : 171 réussis, 1 ignoré.

### Mise à jour d'un dépôt existant
L'ancien dossier doit être supprimé, pas seulement remplacé : `git rm -r pages`, puis
`git add .`, `git commit`, `git push`.

### Calculs
Aucun changement.

---

## [1.0.3] — 2026-10-24 — commit `7d4620b`

**Type :** correctif (déploiement).

### Corrigé
- Journal de Streamlit Cloud saturé par 949 erreurs `OSError: [Errno 24] inotify instance limit
  reached`. Streamlit tentait de surveiller chaque dossier du projet pour recharger l'application ;
  le conteneur limite le nombre de surveillances. Ces erreurs n'avaient pas d'effet sur les calculs.

### Modifié
- `.streamlit/config.toml` : `fileWatcherType = "none"`. En développement local, le rechargement
  automatique reste possible : `streamlit run app.py --server.fileWatcherType auto`.

### Calculs
Aucun changement.

---

## [1.0.2] — 2026-10-24 — commit `9d36c1b`

**Type :** correctif (interface).

### Corrigé
- Message `ArrowInvalid … Conversion failed for column Version` sur la page « Calcul et
  validation ». La colonne *Version* du tableau mensuel mélangeait des nombres et des textes vides
  (salariés sans saisie) ; Streamlit corrigeait le tableau de lui-même mais affichait l'erreur.
- Même risque corrigé dans le tableau des dernières paies du tableau de bord.

### Fichiers
`views/calcul.py`, `views/dashboard.py` (à l'époque `pages/`)

### Calculs
Aucun changement.

---

## [1.0.1] — 2026-10-24 — commit `1dfaff4`

**Type :** documentation.

### Modifié
- Version minimale de Python ramenée de 3.11 à **3.10**, après exécution de toute la suite de tests
  sous Python 3.10.20 (pandas 2.3.3, streamlit 1.65.0) : 161 réussis, 1 ignoré.
- `README.md`, `requirements.txt`, `docs/TESTS.md`.

### Calculs
Aucun changement.

---

## [1.0.0] — 2026-10-23 — commit `35ef5c8`

**Type :** version initiale.

### Ajouté
- **Audit des sources** (`docs/AUDIT_SOURCES.md`) : feuilles, formules reconstituées, écarts entre
  le classeur et le PDF, hypothèses, décisions de conception.
- **Moteur de calcul** en `Decimal` : une fonction par ligne de la feuille `Calcul`, arrondis aux
  mêmes étapes que le classeur.
- **Persistance SQLite** : migrations, transactions, unicité des paies, paies clôturées et bulletins
  protégés par des déclencheurs, journal en ajout seul.
- **Procédure mensuelle** : brouillon → calculée → clôturée, rectification avec motif et conservation
  de la version antérieure.
- **Paramètres** en versions datées, jamais appliqués rétroactivement aux paies clôturées.
- **Cumuls annuels** calculés sur les seules paies clôturées, figés à l'émission du bulletin.
- **Bulletin PDF** (ReportLab, A4) calqué sur le modèle, archivé en base avec son empreinte SHA-256.
- **Interface Streamlit** de 9 pages, exports CSV/Excel, sauvegarde et restauration, mot de passe
  d'accès, données de démonstration fictives.
- **Documentation** : README, architecture, utilisation, déploiement, tests.
- **Tests** : 162, dont une comparaison cellule par cellule avec le classeur source.

### Écarts classeur / PDF établis (pas des anomalies)
| Rubrique | Classeur | PDF | Origine |
|---|---:|---:|---|
| Total cotisations salariales | 366,43 | 366,42 | somme des lignes arrondies / taux cumulé arrondi une fois |
| Total cotisations patronales | 1 146,57 | 1 146,56 | même mécanisme |
| Net imposable | 3 167,30 | 3 167,31 | conséquence de l'écart sur les cotisations salariales |
| Arrondi | 0,08 | 0,09 | même conséquence |
| Net à payer | 7 000,00 | 7 000,00 | identique |

Méthode du classeur appliquée par défaut ; méthode du PDF disponible comme paramètre
(« Méthode des totaux de cotisations »).

### Corrigé pendant le développement (avant la version 1.0.0)
- Le contrôle du barème acceptait des tranches de l'IR qui se chevauchent : contrôle ajouté.
- Saisie mensuelle : le salaire de base s'affichait sous les autres champs ; replacé en tête.
- Tableau de bord : l'ordre des dernières paies était instable à horodatage égal ; tri complété.
- Un numéro de CIN issu des sources servait d'exemple de masquage : remplacé par une valeur inventée.
- Paramètre de `zip` rendu explicite dans le rendu PDF (analyse statique).

---

## Correspondance avec le dépôt `zaklearn/paie-bulletins`

À compléter à chaque `git push` depuis votre ordinateur (`git log --oneline -1` donne l'identifiant).

Ne renseigner que ce qui est vérifié. La colonne « déployée » se remplit après lecture de la
version affichée dans l'application (procédure : `docs/DEPLOIEMENT.md`, « Vérifier la version
réellement en service »).

| Version | Commit `paie-bulletins` | Vérification du contenu | Déployée sur Streamlit Cloud |
|---|---|---|---|
| 1.0.x | `b3e6001`, `db693d1`, `bb2479a`, `b111bed`, `1cf98a4` | non vérifiée (états intermédiaires) | non vérifié |
| 1.1.0 | `afc8a81` (2026-10-24 15:13) | identique fichier par fichier à `659b9c9`, comparaison du 2026-10-26 ; 173 tests réussis sur ce clone | non vérifié |
| 1.2.0 | non poussée séparément | | |
| 1.2.1 | à compléter après votre push | | |

## Modèle pour une prochaine version

```
## [x.y.z] — AAAA-MM-JJ — commit `xxxxxxx`

**Type :** correctif | évolution | majeure

### Ajouté / Modifié / Corrigé / Supprimé
- …

### Fichiers
…

### Calculs
Aucun changement. | Changement : rubriques concernées, exemple avant/après, validation par …
```

Pensez aussi à mettre à jour `__version__` dans `src/__init__.py`.
