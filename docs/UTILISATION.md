# Guide d'utilisation

Ce guide s'adresse à une personne habituée au classeur Excel. Correspondance des écrans :

| Classeur Excel | Application |
|---|---|
| Feuille `Paramètres`, cellules société | **Entreprise** |
| Feuille `Paramètres`, taux et barème | **Paramètres** (versions datées) |
| Feuille `Saisie`, haut (fiche) | **Salariés** |
| Feuille `Saisie`, colonnes de mois | **Saisie mensuelle** (un mois à la fois, tous les mois de toutes les années) |
| Feuille `Calcul` | **Saisie mensuelle** (prévisualisation) et **Calcul et validation** |
| Feuilles `Bulletin …` | **Calcul et validation** (clôture → PDF) et **Bulletins et archives** |

## 1. Mise en route

1. **Entreprise** : remplacez les données fictives de démonstration (raison sociale, adresse,
   ICE, n° CNSS employeur, RC, IF, logo facultatif).
2. **Paramètres** : vérifiez la version initiale (reprise du classeur) avec votre comptable.
   Si une valeur doit changer, créez une nouvelle version avec sa date d'effet et son motif.
3. **Salariés** : créez les fiches. Le matricule doit être unique ; les doublons de CIN et de
   n° CNSS sont refusés. Les identifiants sont masqués à l'écran par défaut.

Pour repartir d'une base vide sans démonstration : `PAIE_SEED_DEMO=0` et un nouveau
`PAIE_DB_PATH` (voir `README.md`).

## 2. Chaque mois

1. **Saisie mensuelle** : choisissez l'année, le mois et le salarié.
   - Les éléments récurrents (salaire de base, jours, panier, transport, représentation, congés
     acquis) sont **proposés** depuis le dernier mois clôturé ; heures supplémentaires, autre
     prime et congés pris repartent de zéro. Un avertissement signale toute reprise.
   - Le **reliquat de congés** proposé est le solde du dernier mois clôturé. Le classeur
     d'origine ne faisait pas ce report : si votre pratique diffère, modifiez la valeur ;
     l'application vous avertit en cas d'écart pour éviter un oubli ou un double comptage.
   - Les contrôles et la **prévisualisation** du calcul se mettent à jour à chaque modification.
   - **Enregistrer le brouillon**.
2. **Calcul et validation** : le tableau du haut montre l'état du mois pour tous les salariés.
   - **Calculer la paie** : récapitulatif complet (gains, retenues, charges patronales, IR,
     arrondi, net à payer, coût employeur, cumuls).
   - **Aperçu du bulletin** : PDF provisoire marqué « PROVISOIRE », non archivé.
   - Lisez les **contrôles avant clôture**. Les erreurs bloquent (mois antérieur non clôturé,
     données modifiées depuis le calcul…) ; les avertissements doivent être confirmés.
   - Cochez la confirmation puis **Clôturer et générer le bulletin**. La paie, les cumuls et le
     PDF sont figés et archivés ; le bouton de téléchargement apparaît.
3. Clôturez les mois **dans l'ordre chronologique** : les cumuls d'un bulletin reprennent les
   mois antérieurs clôturés de l'année.

## 3. Corriger une paie clôturée

**Calcul et validation** → paie clôturée → **Ouvrir une rectification** avec un motif.
Une version 2 est créée en brouillon : corrigez la saisie, recalculez, clôturez. La version 1
reste consultable (statut « Remplacée ») avec son PDF d'origine ; la version 2 produit
`bulletin_AAAA-MM_matricule_v2.pdf`. Si des mois postérieurs sont déjà clôturés, leurs
bulletins gardent les cumuls tels qu'émis ; l'application le signale avant la clôture.

## 4. Consulter et exporter

- **Bulletins et archives** : filtres année / mois / salarié, toutes versions, téléchargement du
  PDF archivé, montants figés et paramètres appliqués.
- **Récapitulatifs et exports** : livre de paie, totaux mensuels, totaux annuels par salarié ;
  CSV (séparateur `;`, virgule décimale) ou Excel. Les exports n'incluent ni CIN, ni n° CNSS, ni
  coordonnées bancaires.

## 5. Sauvegardes

**Sauvegardes et administration** : créer / télécharger une sauvegarde, restaurer (saisir
`RESTAURER` pour confirmer ; l'état actuel est sauvegardé automatiquement juste avant), consulter
le journal des opérations.

## 6. Points d'attention

- Les champs numériques de Streamlit affichent le point décimal (`5436.51`) ; tous les tableaux,
  récapitulatifs et le PDF utilisent le format français (`5 436,51`).
- Entrée ou sortie en cours de mois : saisissez directement le salaire de base proratisé et les
  jours déclarés ; aucune proratisation automatique (absente des sources).
- Les taux, plafonds, exonérations et le barème ne sont pas certifiés : faites-les valider.
