# Déploiement, sécurité, sauvegarde et restauration

## 1. Périmètre prévu

Version mono-poste ou petit serveur interne, quelques utilisateurs de confiance. Ce n'est pas
une application multi-entreprises ni multi-rôles.

## 2. Installation sur un serveur

```bash
git clone <dépôt> && cd <dépôt>/paie
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/hash_password.py        # copier la ligne produite dans .env
# .env : PAIE_SEED_DEMO=0, supprimer la ligne PAIE_ALLOW_NO_AUTH,
#        PAIE_DB_PATH et PAIE_BACKUP_DIR sur un disque chiffré et sauvegardé
streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

Exposer l'application uniquement derrière un **reverse proxy HTTPS** (nginx, Caddy…) ou un VPN,
jamais directement sur Internet. Exemple de service systemd :

```ini
[Service]
WorkingDirectory=/opt/paie/paie
ExecStart=/opt/paie/paie/.venv/bin/streamlit run app.py --server.address 127.0.0.1
User=paie
Restart=on-failure
```

## 3. Sécurité : ce qui est fait, ce qui ne l'est pas

| Mesure | État |
|---|---|
| Mot de passe d'accès (PBKDF2-SHA256, 600 000 itérations), hachage dans `.env` ou les secrets | fait |
| Application **fermée** si aucun mot de passe n'est configuré (sauf dérogation locale `PAIE_ALLOW_NO_AUTH=1`) | fait (1.2.0) |
| Bouton « Se déconnecter » | fait (1.2.0) |
| Nom de l'opérateur enregistré dans le journal | fait (déclaratif, pas de compte individuel) |
| Secrets uniquement en variables d'environnement, `.env` ignoré par Git | fait |
| CIN, n° CNSS, compte bancaire masqués à l'écran par défaut | fait |
| Exports sans CIN, CNSS, banque, date de naissance | fait |
| Journal sans valeurs personnelles ni bancaires (noms de champs seulement) | fait |
| Paies clôturées, bulletins, journal et versions de paramètres protégés par la base | fait |
| Aucune donnée réelle dans le dépôt (sources de référence et bases exclues par `.gitignore`) | fait |
| Chiffrement de la base au repos | **non** — utiliser un disque/volume chiffré |
| HTTPS | **non** — à assurer par le reverse proxy |
| Comptes individuels, rôles, verrouillage après échecs | **non** — à prévoir pour un usage élargi |
| Limitation de débit des tentatives de connexion | **non** — une limite dans l'application serait contournable en ouvrant une nouvelle session ; à assurer par le reverse proxy |

Héberger le code sur GitHub ou une plateforme cloud ne rend pas l'application sécurisée. Ne
pas déployer sur un service public partagé (type Streamlit Community Cloud) avec des données
réelles : le système de fichiers y est éphémère et l'accès doit être maîtrisé.

### Variables à définir selon le mode

| Mode | `PAIE_AUTH_PASSWORD_HASH` | `PAIE_ALLOW_NO_AUTH` | Résultat |
|---|---|---|---|
| Hébergé (Streamlit Cloud, serveur) | **hachage obligatoire** | absent | écran de connexion, puis bouton « Se déconnecter » |
| Local, avec mot de passe | hachage | absent | idem |
| Local, sans mot de passe (choix explicite) | vide | `1` | accès direct, bandeau d'avertissement |
| Configuration oubliée | vide | absent ou `0` | **application fermée** : « Configuration incomplète », aucune page accessible |

Sur Streamlit Community Cloud, les variables se définissent dans *Settings → Secrets*, au premier
niveau du fichier TOML (elles sont alors fournies comme variables d'environnement) :

```toml
PAIE_AUTH_PASSWORD_HASH = "pbkdf2_sha256$600000$...$..."
PAIE_SEED_DEMO = "1"   # "0" pour une base sans démonstration
```

Ne jamais y définir `PAIE_ALLOW_NO_AUTH`. Après une modification des secrets, redémarrer
l'application (*Manage app → Reboot app*) : la configuration est lue au démarrage.

### Vérifier la version réellement en service

1. Sur le poste : `git log --oneline -1` donne le commit poussé ; `type src\__init__.py`
   (Windows) ou `cat src/__init__.py` donne la version.
2. Sur l'application : se connecter et lire « Version x.y.z » en bas du menu.
3. Si la version affichée diffère : *Manage app → Reboot app*, puis vérifier à nouveau.
4. Reporter le commit, la date et la vérification dans le tableau de correspondance de `log.md`.
   Ne renseigner la colonne « déployée » qu'après l'étape 2.

## 4. Sauvegarde

- Interface : **Sauvegardes et administration → Créer une sauvegarde**, puis télécharger.
- Ligne de commande (planifiable) : `python scripts/backup_db.py` ; exemple cron quotidien :
  `30 19 * * * cd /opt/paie/paie && .venv/bin/python scripts/backup_db.py`
- Une sauvegarde est un fichier `.db` autonome (référentiels, paies, journal **et** PDF archivés),
  produit par l'API de sauvegarde en ligne de SQLite (cohérent même pendant l'utilisation).
- Copier régulièrement `PAIE_BACKUP_DIR` vers un stockage externe chiffré ; tester la
  restauration au moins une fois par trimestre.

## 5. Restauration

- Interface : **Restauration**, choisir le fichier `.db`, saisir `RESTAURER`.
- Le fichier est vérifié (intégrité SQLite, tables attendues, version de schéma compatible,
  références entre tables) et **refusé si ses déclencheurs ou index d'unicité diffèrent du
  schéma** : une telle sauvegarde réintroduirait une base sans protection des paies clôturées.
- Un refus intervient avant toute action : la base actuelle n'est pas modifiée.
- L'état courant est d'abord sauvegardé (`paie_…_avant_restauration.db`), puis remplacé.
- Hors interface : arrêter l'application, remplacer le fichier `PAIE_DB_PATH` par la sauvegarde
  (en supprimant les fichiers `-wal` et `-shm` éventuels), relancer. Ce mode manuel ne passe
  pas par les contrôles ci-dessus : ne l'utiliser qu'avec une sauvegarde produite par l'application.
- Sur Streamlit Community Cloud, la sauvegarde de sécurité est écrite sur le disque éphémère de
  l'hébergement : téléchargez une sauvegarde avant toute restauration.

## 6. Conservation

Les bulletins sont remis au salarié qui doit les conserver sans limitation de durée (mention
du bulletin). Côté employeur, définir avec le conseil juridique la durée de conservation du
livre de paie et des sauvegardes ; l'application ne purge rien automatiquement et n'offre aucune
suppression de paie clôturée.

## 7. Évolution multi-utilisateurs

Pour plusieurs gestionnaires simultanés ou un accès distant élargi : PostgreSQL (mêmes
contraintes d'unicité et déclencheurs), authentification individuelle (SSO/OIDC) avec rôles
« saisie » / « validation », séparation des tâches (le valideur n'est pas le saisisseur),
sauvegardes gérées par la base, journalisation centralisée.

## 8. Passage en production : remise à zéro

Retire la démonstration (et toutes les données présentes) pour démarrer avec une société réelle.

### Sur votre ordinateur (Windows)

1. Fermez l'application : fenêtre de l'invite où tourne `streamlit run`, puis Ctrl+C.
2. Activez l'environnement : `C:\python3.10\py310_env\Scripts\activate.bat`.
3. Double-cliquez sur `reinitialiser_production.bat`, ou depuis l'invite :
   ```bat
   cd /d "D:\bulletinPaie_ezzine\paie_v1.2"
   reinitialiser_production.bat
   ```
4. Lisez l'inventaire affiché. Si la ligne « ATTENTION : la base contient des données qui ne sont
   PAS la démonstration » apparaît, vérifiez qu'il s'agit bien de la bonne base.
5. Tapez `EFFACER` pour confirmer (toute autre réponse annule).

Ce que fait le script, dans l'ordre (chaque étape arrête tout en cas d'échec) :

| Étape | Résultat |
|---|---|
| Contrôle que la base n'est pas en cours d'utilisation | sinon : « fermez l'application », rien n'est modifié |
| Sauvegarde puis vérification de la sauvegarde | `data\backups\paie_…_avant_reinitialisation.db` |
| Déplacement de l'ancienne base (rien n'est supprimé) | `data\backups\ancienne_base_AAAAMMJJ_HHMMSS\` |
| Base neuve : schéma + version initiale des paramètres | aucune entreprise, aucun salarié, aucune paie |
| `PAIE_SEED_DEMO=0` dans `.env` (autres lignes conservées) | la démonstration n'est plus rechargée au démarrage |

Ensuite : définir un mot de passe (si `.env` contient `PAIE_ALLOW_NO_AUTH=1`, le script le
signale), lancer l'application, renseigner **Entreprise**, créer les **Salariés**, faire valider
les **Paramètres** par un professionnel.

Pour annuler une remise à zéro : restaurer `paie_…_avant_reinitialisation.db` depuis la page
**Sauvegardes et administration**, puis remettre `PAIE_SEED_DEMO=1` si besoin.

Options : `--confirm EFFACER` (sans question), `--db`, `--backup-dir`, `--env-file`
(par défaut : les chemins de la configuration).

### Sur Streamlit Community Cloud

Le script ne s'y exécute pas. Dans *Settings → Secrets*, mettre `PAIE_SEED_DEMO = "0"`, puis
*Reboot app*. **Non vérifié** : la documentation de la plateforme décrit un disque éphémère, mais
aucun essai n'a confirmé qu'un redémarrage efface la base. Si la démonstration est toujours
présente après redémarrage, supprimez l'application sur Streamlit Cloud puis redéployez-la avec
`PAIE_SEED_DEMO = "0"` dans les secrets. Rappel : ce disque éphémère ne convient pas à des
données de paie réelles (section 3).

## 9. Supprimer uniquement la démonstration (données réelles déjà saisies)

À utiliser lorsque la société réelle et des salariés réels ont été saisis dans une base qui
contient encore la démonstration : les paies du salarié exemple faussent alors le livre de paie
et les récapitulatifs (totaux doublés). La désactivation ne suffit pas : les paies d'un salarié
désactivé restent, à juste titre, dans les récapitulatifs de l'année (départ en cours d'année).

1. Fermez l'application, activez l'environnement Python.
2. Lancez `supprimer_demo.bat` depuis le dossier de l'application.
3. Vérifiez la liste affichée : « À SUPPRIMER » (salarié `0001 EXEMPLE`, ses paies et bulletins)
   et « CONSERVÉ » (entreprise, autres salariés et leurs paies, paramètres, journal).
4. Tapez `EFFACER`.

Garde-fous :

| Situation | Comportement |
|---|---|
| Matricule `0001` dont le nom ou le CIN a été modifié | refus : il peut s'agir d'un salarié réel |
| Aucun salarié de démonstration | « rien à faire », aucune modification |
| Application ouverte (base en cours d'utilisation) | arrêt sans modification |
| Toute erreur pendant la suppression | annulation complète (transaction unique) |

Déroulement : sauvegarde vérifiée (`data\backups\paie_…_avant_suppression_demo.db`), puis en une
seule transaction : levée des deux protections de suppression, suppression des bulletins, des
paies et de la fiche du salarié de démonstration, rétablissement des protections à l'identique,
contrôle des protections et des références, inscription au journal. Enfin `PAIE_SEED_DEMO=0`
dans `.env`. Pour revenir en arrière : restaurer la sauvegarde depuis la page **Sauvegardes et
administration**.

