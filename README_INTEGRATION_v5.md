# SMART‑SUP v5 — Intégration au serveur

Ce dossier **est** le serveur, pas une collection de fichiers à ranger.
Il se lance comme avant : `demarrer.bat` (ou `python app.py`), puis
`http://127.0.0.1:5000`.

L'architecture n'a pas changé : Flask mono‑processus, SQLite locale, page
unique à sections, accès restreint à 127.0.0.1, pont Outlook COM. Ce qui a
changé, c'est le **modèle de domaine** — conformément au cadrage : le ticket
appartient à l'outil du groupe, notre système documente, communique et reporte.

---

## Ce qui a été modifié, fichier par fichier

| Fichier | État | Détail |
|---|---|---|
| `app.py` | **modifié** (2 blocs, ~20 lignes) | Importe et enregistre `api_v5`, initialise la base v5, charge le catalogue au démarrage. Tout le reste est intact. |
| `db/schema.py` | **inchangé** | Conservé tel quel : le module v4 continue de tourner pendant la transition. |
| `db/schema_v5.py` | **nouveau** | Schéma `incidents` / `incident_evidences` / `incident_communications` + référentiels catalogue. |
| `db/api_v5.py` | **nouveau** | Blueprint `/api/v5/*`. Contient la génération de contenu e‑mail (voir §Chartes). |
| `db/catalogue.py` | **nouveau** | Import du Catalogue de supervision (19 domaines, 256 services). |
| `db/migration_v4_v5.py` | **nouveau** | Reprise des données v4. À lancer manuellement. |
| `db/parametres.py` | **nouveau** | Couche de paramétrage : 41 réglages + valeurs par défaut. |
| `db/api_admin.py` | **nouveau** | CRUD complet sur les 10 tables administrables. |
| `db/rapports.py` | **nouveau** | Rapports fin de shift / hebdomadaire / mensuel + export Excel. |
| `db/exports.py` | **nouveau** | SMS, rapport court, ligne de suivi — remplace `Web_SMS_Sup_v2.2.html`. |
| `archive/` | **nouveau** | `Web_SMS_Sup_v2.2.html` retiré du serveur, conservé pour référence. |
| `templates/index.html` | **modifié** | La section « Tickets » devient « Saisie rapide ». Jauge ajoutée au bandeau. |
| `static/script.js` | **modifié** | Les 446 lignes du module ticketing (Kanban, statuts, MTTR) sont remplacées par le module de saisie rapide. |
| `static/theme.css` | **nouveau** | Design System : jetons sémantiques + 4 thèmes + états d'incident. |
| `static/style.css` | **modifié** | 174 couleurs en dur migrées vers les jetons du thème. |
| `tests/test_incidents.py` | **nouveau** | 35 tests de non-régression (ferme le point B9 de l'audit). |
| `requirements.txt` | **modifié** | `openpyxl` confirmé, `apscheduler` retiré (jamais importé). |
| `data/Catalogue_Services_SupervisionV4.xlsx` | **nouveau** | Source du référentiel de services. |
| `vba_Import_Incidents_OGN_v6.bas` | **hors serveur** | S'importe dans `INCIDENT007.xlsm`, ne fait pas partie du processus Flask. |
| `Web_SMS_Sup_v2.2.html` | **retiré** | Point bloquant B8 fermé — déplacé dans `archive/`. |

---

## Décision d'intégration importante

Le plan prévoyait de **remplacer** `db/schema.py` par la version v5. À
l'intégration, cela s'est révélé impossible sans casser le démarrage :
`app.py` importe `_seed_defaults` et `migrate_sent_log` depuis ce module.

La v5 vit donc dans `db/schema_v5.py`, **à côté** de la v4 plutôt qu'à sa
place. C'est conforme au principe « améliorer sans casser » : le socle
existant continue de fonctionner pendant que le nouveau se met en place. La
suppression du module v4 interviendra une fois la bascule validée en usage
réel, dans un chantier dédié.

---

## Design System — thèmes de l'interface

Quatre thèmes commutables depuis le bandeau, plus un mode automatique.

| Thème | Usage | Fond | Accent |
|---|---|---|---|
| **Clair** | Journée, lecture confortable | `#F7F5F3` | `#FF7900` |
| **Sombre** | Usage prolongé en NOC (défaut) | `#0A0908` | `#FF7900` |
| **Furtif** | Supervision nocturne, l'interface s'efface | `#050505` | `#994900` |
| **NOC** | Grand écran, états lisibles de loin | `#06080B` | `#FF7900` |
| **Auto** | Suit le réglage du système | — | — |

### Architecture

Deux niveaux de jetons, jamais mélangés :

- **Primitifs** (`--o-500`, `--n-850`) : la palette brute. Jamais consommés
  directement par un composant.
- **Sémantiques** (`--fond`, `--texte`, `--critique`) : le rôle. C'est ce que
  les composants utilisent.

Un thème ne redéfinit que les jetons sémantiques : **aucun composant n'a besoin
d'être réécrit pour qu'un nouveau thème fonctionne**. C'est ce qui a permis de
migrer 174 couleurs codées en dur sans toucher à une seule règle de mise en page.

### Lisibilité vérifiée

Les contrastes sont testés automatiquement (`TestThemes`) contre les seuils
WCAG : 4.5 pour le texte, 3.0 pour les indicateurs d'état. Deux défauts réels
ont été trouvés et corrigés par ces tests :

- mode furtif, texte secondaire à **4.37** — remonté à 5.53 ;
- mode clair, ambre à **2.93** — assombri à 4.62.

Un thème sobre reste un thème qui doit se lire. En mode furtif, où tout est
volontairement effacé, un incident critique reste visible : c'est la contrainte
non négociable, elle aussi couverte par un test.

### États d'incident

Jamais la couleur seule. Chaque état porte une **forme de pastille distincte**
(losange, cercle, anneau, carré) et un libellé, pour rester lisible en cas de
daltonisme comme en mode furtif.

### Périmètre

Le thème n'affecte **que l'interface**. Les e-mails et les rapports sont rendus
par le serveur dans des iframes : ils conservent leur charte propre quel que
soit le thème choisi. Deux tests le vérifient explicitement.

---

## Les trois couches d'identité visuelle

C'est la règle la plus importante à ne pas enfreindre.

| | Application | E‑mails | Rapports |
|---|---|---|---|
| Couleur | thème actif (4 au choix) | `#FF6D00` | neutre |
| Où | `static/theme.css` | `db/api_v5.py` | `db/rapports.py` |
| Police | Inter | Times New Roman | Arial |
| Rendu | page | iframe | iframe |

**Les deux oranges sont volontairement différents.** L'aperçu affiché dans la
section « Saisie rapide » n'est pas construit par le navigateur : il est
généré par le serveur (`POST /api/v5/preview`) et inséré dans une **iframe**.
Le thème de l'application ne peut donc pas l'atteindre, même par accident.

Vérification automatisée dans les tests : `#FF6D00` ne doit apparaître dans
aucune règle CSS, et `#FF7900` dans aucun e‑mail généré.

---

## Mise en service

```bash
# 1. Dépendances
pip install -r requirements.txt --break-system-packages

# 2. Reprise des données v4 — simulation d'abord
python -m db.migration_v4_v5
#    puis, après lecture du rapport :
python -m db.migration_v4_v5 --appliquer

# 3. Démarrage (le catalogue s'importe automatiquement)
python app.py
```

Le module VBA s'importe séparément dans Excel :
`Alt+F11` → Fichier → Importer → `vba_Import_Incidents_OGN_v6.bas`

---

## Routes v5

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/v5/services?q=` | Auto‑complétion sur le catalogue |
| GET | `/api/v5/referentiels` | Tout ce dont l'interface a besoin, en un appel |
| GET | `/api/v5/incidents` | Liste filtrable |
| POST | `/api/v5/incidents` | Création (référence externe requise) |
| GET | `/api/v5/incidents/<id>` | Détail + preuves + communications |
| PUT | `/api/v5/incidents/<id>` | Modification |
| POST | `/api/v5/incidents/<id>/preuves` | Ajout de preuve |
| POST | `/api/v5/incidents/<id>/communications` | Journalisation d'un envoi |
| POST | `/api/v5/preview` | **Génération du message par le serveur** |
| GET | `/api/v5/stats` | Agrégations pour les rapports |

Toutes protégées par le middleware `_local_only` existant.

---

---

## Paramétrage — tout est éditable sans toucher au code

Écran **Administration**, deux niveaux.

### Paramètres généraux (41 réglages, 7 catégories)

| Catégorie | Ce qu'on y règle |
|---|---|
| Organisation | Raison sociale, direction, formule de politesse, téléphone |
| Saisie | Motif de reconnaissance des références, priorité par défaut, héritage depuis le catalogue, format des dates |
| Canaux | Activer/désactiver e‑mail, ARPT, SMS, WhatsApp, Web ; longueur max SMS |
| Envoi | Afficher ou envoyer directement, repli `.eml`, journalisation, copie expéditeur |
| Charte des e‑mails | Les 7 couleurs, police, taille, logo, largeur des libellés |
| Rapports | Shifts par jour, heure de début, premier jour de semaine, seuil « incident majeur » |
| Interface | Couleur d'accent, jauge, nombre de suggestions, aperçu automatique |

### Tables administrables (CRUD complet, 10 tables)

Listes de diffusion · Superviseurs · Types de message · Champs par type de
message · Valeurs proposées · Descriptions automatiques · Équipes · Catalogue
de services · Domaines · Signatures.

### Ce que cela permet concrètement

- **Ajouter un destinataire** et le cibler finement : seulement pour le canal
  ARPT, seulement pour les avis de fin, seulement pour les incidents NBN.
- **Créer un type de message entier** (« Escalade », « Alerte préventive »…)
  avec son titre, son préfixe de sujet et ses champs — sans développement.
- **Ajouter ou retirer un champ** d'un gabarit existant, en changer l'ordre
  ou le rendre obligatoire.
- **Changer la charte des e‑mails** sans toucher au thème de l'application.
- **Modifier les formulations proposées** (causes, actions, observations,
  zones, TMC) que le bouton « proposer » fait défiler.
- **Régler le pré-remplissage automatique** de la description par domaine.

L'écran d'administration se construit à partir du descripteur `TABLES` de
`db/api_admin.py` : rendre une nouvelle table administrable ne demande aucune
ligne de HTML ni de JavaScript, seulement une entrée dans ce descripteur.

---

---

## Rapports

Trois rapports, générés depuis les incidents déjà documentés — aucune ressaisie.

| Rapport | Période | Contenu spécifique |
|---|---|---|
| Fin de shift | Shift courant (découpage paramétrable) | Liste « à suivre » par l'équipe suivante : incidents ouverts + actions en attente |
| Hebdomadaire | Semaine calendaire | Répartitions, encore ouverts en fin de semaine, régularisations |
| Mensuel | Mois calendaire | Tendance vs mois précédent, répartition par semaine, incidents majeurs |

Trois formats pour chacun :
- **HTML** — affiché dans l'interface, imprimable (`@media print`), copiable dans un e‑mail
- **XLSX** — reprend les 21 colonnes du classeur de suivi existant (module VBA), avec totaux **en formules** pour rester justes après édition manuelle
- **JSON** — indicateurs seuls, pour l'affichage des cartes

Un incident est retenu s'il a démarré, s'est terminé **ou a fait l'objet d'une
communication** pendant la période. Sans cette troisième condition, un incident
de longue durée disparaîtrait des rapports intermédiaires — alors que c'est
précisément celui qu'il faut signaler à l'équipe suivante.

### Trois mises en forme distinctes

| | Couleur | Police | Où |
|---|---|---|---|
| Application | `#FF7900` | Inter | `static/style.css` |
| E‑mails | `#FF6D00` | Times New Roman | `db/api_v5.py` |
| Rapports | neutre, imprimable | Arial | `db/rapports.py` |

Chacune vit dans son propre fichier et s'affiche dans son propre contexte
(iframe pour les deux dernières). Aucune ne peut contaminer les autres.

---

---

## Preuves et sorties dérivées

### Captures d'écran

Zone de collage dans la saisie rapide : **Ctrl+V** colle directement une
capture, comme dans Outlook. Le dépôt de fichier fonctionne aussi.

Les captures sont téléversées immédiatement, avant même que l'incident
n'existe — on colle la preuve pendant qu'on la regarde, pas après avoir rempli
le formulaire. Elles sont rattachées à l'enregistrement.

Limites : PNG, JPEG, GIF, WebP, 8 Mo par image. Le nom de fichier servi est
validé par motif strict, ce qui interdit toute remontée de chemin.

### Trois sorties dérivées

Onglets **E-mail · SMS · Rapport court · Ligne de suivi** dans le volet
d'aperçu. Toutes produites par le serveur (`POST /api/v5/sorties`) depuis les
données structurées de l'incident.

Elles remplacent `Web_SMS_Sup_v2.2.html`, qui reconstruisait ces mêmes
informations en analysant par expressions régulières le texte d'un e-mail déjà
généré. Une retouche de libellé côté serveur cassait silencieusement
l'extraction — sans erreur visible, juste un champ vide.

**Gain mesurable** : les colonnes de durée, laissées vides par l'ancien outil
(elles n'étaient pas déductibles d'un texte), sont maintenant calculées.
Sur un incident réel de test : `04:26` et `266` minutes.

Le compteur de caractères du SMS avertit au-delà de la limite configurée.

---

---

## Tests

```bash
python -m unittest discover tests -v
```

35 tests, répartis en 8 groupes. Chacun couvre un défaut **réellement
rencontré sur ce projet**, pas une couverture théorique :

| Groupe | Ce qu'il protège |
|---|---|
| `TestCalculDurees` | Le calcul de durée, dont l'absence avait rendu le MTTR inopérant en v4 |
| `TestDecoupageShifts` | Le découpage paramétrable des shifts (2, 3, 4, 6 par jour) |
| `TestChartesSeparees` | Les trois identités visuelles ne se contaminent pas |
| `TestParametrageEffectif` | Un paramètre modifié change bien la sortie, pas seulement la base |
| `TestSortiesDerivees` | SMS, rapport court, ligne de suivi, durées calculées |
| `TestRoutesApi` | Parcours de bout en bout, gabarit ARPT, les trois rapports |
| `TestSecurite` | Loopback, remontée de chemin, injection SQL, liste blanche des tables |
| `TestMigration` | Le numéro interne v4 n'est jamais pris pour une référence externe |

Les tests utilisent des bases temporaires : ils ne touchent jamais aux données
réelles. `pyperclip` et `pywin32` sont neutralisés automatiquement, la suite
tourne donc aussi hors poste Windows.

**Vérification faite** : en réintroduisant volontairement la régression de
charte (aligner le CSS sur `#FF6D00`), `TestChartesSeparees` échoue
immédiatement. Un test qui ne peut pas échouer ne protège de rien.

---

## Migration depuis la v4

```bash
python -m db.migration_v4_v5              # simulation, aucune écriture
python -m db.migration_v4_v5 --appliquer  # après lecture du rapport
```

**Point à connaître avant de lancer** : la table `tickets` de la v4 ne comporte
aucune colonne de référence externe. Son seul identifiant est `numero`
(`TT-AAAAMMJJ-NNN`), fabriqué par l'ancien système — ce n'est **pas** la
référence du ticket groupe.

La migration ne l'utilise donc jamais comme référence. Elle le conserve dans
`attributs_specifiques.numero_interne_v4`, cherche une vraie référence dans les
champs libres (description, observation, cause), et **liste explicitement dans
son rapport les incidents à compléter à la main**. Inventer une correspondance
serait pire que de la demander.

Ce qui est repris : superviseurs (nom et prénom fusionnés), équipes, listes de
diffusion, modèles, tickets avec leur type déduit (RAN/NBN selon les liens
impactés), zone, criticité, preuves (URL et notes) et communications déjà
journalisées.

---

## Ce qui reste à faire

1. **Confirmer la liste des TMC** — seul « Orange » a été observé dans les
   communications ; les autres valeurs sont des propositions, modifiables dans
   Administration → Valeurs proposées.
2. **Vérifier les listes de diffusion** pré-chargées depuis les e‑mails réels
   (4 destinataires en « À », 7 en « Cc », 6 pour le canal ARPT).
3. **Compléter les références externes** des incidents migrés que le rapport
   de migration signale comme vides.
4. **Retirer le module v4** une fois la bascule validée en usage réel
   (`db/schema.py`, `db/api.py`, routes `/api/v4/*`).
