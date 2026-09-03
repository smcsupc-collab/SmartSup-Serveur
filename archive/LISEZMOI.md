# Archive

## Web_SMS_Sup_v2.2.html — retiré du serveur

Outil autonome identifié comme **point bloquant B8** dans l'audit initial :
fichier orphelin, servi par aucune route Flask, lié depuis aucune page.

Il reconstruisait le SMS, le rapport court et la ligne du classeur de suivi
en analysant par expressions régulières le texte d'un e-mail déjà généré
ailleurs. Une simple retouche de libellé côté serveur cassait silencieusement
l'extraction — sans erreur visible, juste un champ vide dans la ligne produite.

**Remplacé par** `db/exports.py` et la route `POST /api/v5/sorties`, qui
dérivent ces mêmes sorties des données structurées de l'incident. Il n'y a
plus de texte à analyser, donc plus de rupture silencieuse possible.

Bénéfice mesurable : les colonnes de durée, laissées vides par l'ancien outil
(elles n'étaient pas déductibles d'un texte), sont désormais calculées —
`04:26` et `266` minutes sur un incident réel de test.

Ce fichier est conservé ici à titre de référence historique. Il n'est plus
servi par l'application et peut être supprimé une fois la bascule confirmée.
