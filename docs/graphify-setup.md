# Graphify — graphe de connaissances pour les agents

Graphify (Graphify-Labs) transforme ce dépôt (code, docs, configs) en graphe de connaissances interrogeable, pour que les agents de code (Claude Code, Cursor, Codex, Gemini CLI...) puissent s'orienter sans tout relire.

## Installation

    uv tool install graphifyy
    graphify install          # enregistre le skill auprès de l'assistant utilisé

## Construire le graphe

    graphify update .

Génère `graphify-out/graph.json` et `graphify-out/GRAPH_REPORT.md`.

## Garder le graphe à jour automatiquement

    graphify hook install

Installe des hooks git (post-commit, post-checkout) qui reconstruisent le graphe à chaque changement.

## Interroger le graphe

    graphify query "<question>"

## Notes
- Extraction 100% locale (analyse AST), pas de clé API, rien n'est envoyé en dehors du poste.
- Chaque lien du graphe est marqué EXTRACTED (explicite dans le code) ou INFERRED (déduit par Graphify).
