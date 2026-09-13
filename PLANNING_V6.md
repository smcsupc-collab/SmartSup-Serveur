# SmartSup v6 — Planification des évolutions demandées

Statut : brouillon de planification — confronte les demandes d'évolution aux fonctionnalités déjà présentes en v5 (voir `README_INTEGRATION_v5.md`). À valider avec le porteur du projet avant tout développement.

Dernière mise à jour : 2026-09-13

---

## 1. Recherche de service + prise en charge d'incident

### Déjà en v5
- `GET /api/v5/services?q=` — autocomplétion sur le catalogue de services
- `GET /api/v5/referentiels` — chargement en un appel de tout ce dont l'interface a besoin
- `POST /api/v5/preview` — génération du message (pré-remplissage) par le serveur, affiché en iframe
- `POST /api/v5/incidents`, `PUT /api/v5/incidents/<id>` — création / modification
- `POST /api/v5/incidents/<id>/communications` — journalisation d'un envoi
- Section « Saisie rapide » (`templates/index.html`, `static/script.js`)
- Réglage Administration → Envoi : « afficher ou envoyer directement », repli `.eml`, journalisation, copie expéditeur

### Écarts à clarifier avec le porteur (nouveau, pas identifié en v5)
- **Validation obligatoire qui démarre un compteur et fige le statut « pris en charge / avéré »** : aucune route ni concept explicite trouvé pour ça dans l'API v5 actuelle. À vérifier si `hd`/`hf` (heure de début/fin) couvrent déjà le besoin, ou si c'est un vrai ajout (nouvel état d'incident + verrouillage de la saisie avant validation).
- **Bouton « envoi automatique » vers une plateforme externe** : v5 gère déjà plusieurs canaux (e‑mail, ARPT, SMS, WhatsApp, Web) avec un choix « afficher ou envoyer directement ». À clarifier : s'agit-il de rendre ce réglage existant plus automatique, ou d'un nouveau canal/plateforme cible à intégrer ?

---

## 2. UX/UI superviseur

### Déjà en v5
- 4 thèmes commutables (Clair / Sombre / Furtif / NOC) + mode Auto, design system à jetons sémantiques (`static/theme.css`)
- États d'incident distingués par forme de pastille (pas seulement la couleur), contrastes vérifiés WCAG
- Jauge dans le bandeau

### En attente
- Le détail demandé (« avoir le contrôle les affiches... ») reste à préciser — la phrase d'origine s'arrête en suspens. À clarifier avant de dimensionner cette partie.

---

## 3. Templates de messages vers le TMC (classés Produit > Service)

### Déjà en v5
- « TMC » existe comme valeur proposée (Administration → Valeurs proposées), pas comme axe de classement de templates
- « Types de message » + « Champs par type de message » sont administrables sans code (CRUD, `db/api_admin.py`) — c'est le mécanisme le plus proche d'un « template » aujourd'hui
- Catalogue de services importé (256 services, 19 domaines — `db/catalogue.py`, `data/Catalogue_Services_SupervisionV4.xlsx`) — à vérifier si un niveau « Produit » existe déjà au-dessus de « Service » dans ce catalogue, ou si c'est à ajouter

### Écarts à clarifier avec le porteur (nouveau)
- Un classement Produit > Service **dédié aux templates TMC**, distinct des types de message existants (ARPT, SMS...), n'existe pas encore tel quel — c'est la partie la plus nouvelle des trois demandes.
- Clarifier si « TMC » doit devenir un canal à part entière (comme ARPT) ou rester une valeur de champ, et comment il se distingue des communications existantes vers employés/clients/call center.

---

## Points à trancher avec le porteur avant tout développement

| Sujet | Question |
|---|---|
| Validation d'incident | Nouvel état + verrouillage, ou réutilisation de `hd`/`hf` ? |
| Envoi automatique | Nouveau canal/plateforme, ou automatisation du réglage « Envoi » existant ? |
| Catalogue Produit/Service | Le niveau « Produit » existe-t-il déjà dans `Catalogue_Services_SupervisionV4.xlsx` ? |
| Templates TMC | Nouveau canal distinct, ou extension du mécanisme « Types de message » existant ? |
| UX/UI | Détail encore manquant du besoin superviseur |

## Références
- `README_INTEGRATION_v5.md` — état actuel du serveur, architecture, routes, tests
- `LOCAL_AGENT.md` — agent Outlook local
- Confluence : espace TIADRA, page « SmartSup » (documentation miroir, à mettre à jour avec ce fichier)
