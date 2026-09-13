# SmartSup — Guide pour les agents de code

SmartSup est un serveur Flask mono-processus (SQLite locale) qui aide les superviseurs à documenter, communiquer et reporter sur les incidents de supervision (contexte OGN). Il se lance avec `demarrer.bat` ou `python app.py`.

## Avant de travailler ici

1. Lisez `README_INTEGRATION_v5.md` — état actuel du serveur : architecture, fichiers modifiés/nouveaux, routes `/api/v5/*`, design system, tests.
2. Lisez `PLANNING_V6.md` — évolutions demandées pour la prochaine version, confrontées à l'existant v5, avec les points encore à trancher.
3. Le module v4 (`db/schema.py`) tourne encore **à côté** du v5 (`db/schema_v5.py`) — ne pas le supprimer sans lire la section « Décision d'intégration importante » de `README_INTEGRATION_v5.md`.
4. Les trois identités visuelles (application / e-mails / rapports) sont volontairement séparées et testées (`TestChartesSeparees`) — ne jamais les faire converger.
5. Si Graphify est installé sur ce dépôt (`graphify-out/graph.json` présent), interrogez le graphe avant de lire le code brut : `graphify query "<question>"`. Voir `docs/graphify-setup.md`.

## Tests

    python -m unittest discover tests -v

35 tests couvrant des défauts réellement rencontrés sur ce projet (voir README_INTEGRATION_v5.md §Tests). Toute modification touchant aux durées, aux shifts, aux chartes ou au paramétrage doit rester verte sur ces tests.
