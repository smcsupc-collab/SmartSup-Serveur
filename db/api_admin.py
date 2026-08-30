"""
SMART-SUP — API d'administration
=================================

CRUD complet sur toutes les tables de paramétrage. Corrige le point bloquant
B3 de l'audit initial : les référentiels étaient créables mais pas éditables,
le bouton « Éditer » renvoyait l'utilisateur vers l'API brute.

Principe de sécurité : les noms de tables et de colonnes proviennent
exclusivement du descripteur `TABLES` ci-dessous, jamais de la requête HTTP.
Une colonne absente de ce descripteur ne peut être ni lue ni écrite.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from db.parametres import charger_defauts, definir_parametre
from db.schema_v5 import get_conn

api_admin = Blueprint("api_admin", __name__)


# ======================================================================
#  Descripteur des tables administrables
#  Chaque entrée décrit ce que l'interface doit afficher et ce que l'API
#  accepte d'écrire. Ajouter une table administrable = ajouter une entrée.
# ======================================================================
TABLES = {
    "mailing_lists": {
        "libelle": "Listes de diffusion",
        "aide": "Qui reçoit quoi. Une ligne peut viser un canal précis, un type "
                "de message ou un type d'incident — laisser vide pour « tous ».",
        "colonnes": ["libelle", "adresse", "canal", "destination", "groupe",
                     "type_message", "type_incident", "ordre", "actif"],
        "obligatoires": ["libelle", "adresse"],
        "tri": "canal, destination, ordre, libelle",
        "champs": {
            "libelle": {"label": "Libellé", "type": "texte"},
            "adresse": {"label": "Adresse e-mail", "type": "texte"},
            "canal": {"label": "Canal", "type": "select",
                      "options": ["email", "notification_arpt", "sms", "whatsapp", "web"]},
            "destination": {"label": "Destination", "type": "select",
                            "options": ["a", "cc"]},
            "groupe": {"label": "Groupe", "type": "texte"},
            "type_message": {"label": "Type de message", "type": "select_table",
                             "source": "types_message", "vide": "Tous"},
            "type_incident": {"label": "Type d'incident", "type": "select",
                              "options": ["", "service", "ran", "nbn", "libre"],
                              "vide": "Tous"},
            "ordre": {"label": "Ordre", "type": "nombre"},
            "actif": {"label": "Actif", "type": "booleen"},
        },
    },
    "superviseurs": {
        "libelle": "Superviseurs",
        "aide": "Personnes qui signent les communications.",
        "colonnes": ["nom", "email", "trigramme", "actif"],
        "obligatoires": ["nom"],
        "tri": "nom",
        "champs": {
            "nom": {"label": "Nom", "type": "texte"},
            "email": {"label": "E-mail", "type": "texte"},
            "trigramme": {"label": "Trigramme", "type": "texte"},
            "actif": {"label": "Actif", "type": "booleen"},
        },
    },
    "types_message": {
        "libelle": "Types de message",
        "aide": "Chaque type définit son titre, son préfixe de sujet et son "
                "canal par défaut. En ajouter un ne demande aucune modification "
                "de code.",
        "cle": "code",
        "colonnes": ["code", "libelle", "titre_avis", "prefixe_sujet",
                     "inclut_reference", "salutation", "mention_bas",
                     "canal_defaut", "ordre", "actif"],
        "obligatoires": ["code", "libelle"],
        "tri": "ordre",
        "champs": {
            "code": {"label": "Code", "type": "texte"},
            "libelle": {"label": "Libellé", "type": "texte"},
            "titre_avis": {"label": "Titre dans le message", "type": "texte"},
            "prefixe_sujet": {"label": "Préfixe du sujet", "type": "texte"},
            "inclut_reference": {"label": "Inclure la référence dans le sujet",
                                 "type": "booleen"},
            "salutation": {"label": "Phrase d'introduction", "type": "long"},
            "mention_bas": {"label": "Mention de bas de message", "type": "texte"},
            "canal_defaut": {"label": "Canal par défaut", "type": "select",
                             "options": ["email", "notification_arpt", "sms", "whatsapp", "web"]},
            "ordre": {"label": "Ordre", "type": "nombre"},
            "actif": {"label": "Actif", "type": "booleen"},
        },
    },
    "champs_message": {
        "libelle": "Champs par type de message",
        "aide": "Quels champs apparaissent, dans quel ordre, et lesquels sont "
                "obligatoires. C'est ici qu'on ajoute un champ à un gabarit.",
        "colonnes": ["type_message", "champ", "libelle", "obligatoire", "ordre", "actif"],
        "obligatoires": ["type_message", "champ", "libelle"],
        "tri": "type_message, ordre",
        "champs": {
            "type_message": {"label": "Type de message", "type": "select_table",
                             "source": "types_message"},
            "champ": {"label": "Champ", "type": "select",
                      "options": ["description", "debut", "fin", "ticket", "cause",
                                  "action", "perimetre", "zone", "tmc", "observation"]},
            "libelle": {"label": "Libellé affiché", "type": "texte"},
            "obligatoire": {"label": "Obligatoire", "type": "booleen"},
            "ordre": {"label": "Ordre", "type": "nombre"},
            "actif": {"label": "Actif", "type": "booleen"},
        },
    },
    "valeurs_suggerees": {
        "libelle": "Valeurs proposées",
        "aide": "Causes, actions, observations, zones, TMC… Le bouton "
                "« proposer » de la saisie fait défiler ces valeurs.",
        "colonnes": ["liste", "valeur", "contexte", "ordre", "actif"],
        "obligatoires": ["liste", "valeur"],
        "tri": "liste, ordre",
        "champs": {
            "liste": {"label": "Liste", "type": "select",
                      "options": ["causes", "actions", "observations", "zones", "tmc"]},
            "valeur": {"label": "Valeur", "type": "texte"},
            "contexte": {"label": "Contexte", "type": "select_table",
                         "source": "types_message", "vide": "Toujours"},
            "ordre": {"label": "Ordre", "type": "nombre"},
            "actif": {"label": "Actif", "type": "booleen"},
        },
    },
    "regles_description": {
        "libelle": "Descriptions automatiques",
        "aide": "Pré-remplissage de la description selon le domaine du service. "
                "Variables : {domaine} et {service}. Un motif vide sert de repli.",
        "colonnes": ["motif_domaine", "modele", "priorite_regle", "actif"],
        "obligatoires": ["modele"],
        "tri": "priorite_regle DESC",
        "champs": {
            "motif_domaine": {"label": "Motif dans le domaine", "type": "texte"},
            "modele": {"label": "Modèle de description", "type": "long"},
            "priorite_regle": {"label": "Priorité de la règle", "type": "nombre"},
            "actif": {"label": "Actif", "type": "booleen"},
        },
    },
    "equipes": {
        "libelle": "Équipes",
        "aide": "Équipes destinataires des notifications.",
        "colonnes": ["code", "nom", "actif"],
        "obligatoires": ["code", "nom"],
        "tri": "nom",
        "champs": {
            "code": {"label": "Code", "type": "texte"},
            "nom": {"label": "Nom", "type": "texte"},
            "actif": {"label": "Actif", "type": "booleen"},
        },
    },
    "services": {
        "libelle": "Catalogue de services",
        "aide": "Référentiel alimentant l'auto-complétion. La priorité définie "
                "ici se pré-remplit automatiquement à la saisie.",
        "colonnes": ["nom", "domaine_id", "priorite_defaut", "supervise",
                     "outil_supervision", "actif"],
        "obligatoires": ["nom", "domaine_id"],
        "tri": "nom",
        "limite": 300,
        "champs": {
            "nom": {"label": "Service", "type": "texte"},
            "domaine_id": {"label": "Domaine", "type": "select_table",
                           "source": "domaines"},
            "priorite_defaut": {"label": "Priorité", "type": "select",
                                "options": ["P1", "P2", "P3"]},
            "supervise": {"label": "Supervisé", "type": "booleen"},
            "outil_supervision": {"label": "Outil", "type": "texte"},
            "actif": {"label": "Actif", "type": "booleen"},
        },
    },
    "domaines": {
        "libelle": "Domaines",
        "aide": "Regroupements métier des services.",
        "colonnes": ["nom", "actif"],
        "obligatoires": ["nom"],
        "tri": "nom",
        "champs": {
            "nom": {"label": "Domaine", "type": "texte"},
            "actif": {"label": "Actif", "type": "booleen"},
        },
    },
    "signatures": {
        "libelle": "Signatures",
        "aide": "Bloc de signature par superviseur et par langue.",
        "colonnes": ["superviseur_id", "langue", "contenu_html", "actif"],
        "obligatoires": ["superviseur_id"],
        "tri": "superviseur_id, langue",
        "champs": {
            "superviseur_id": {"label": "Superviseur", "type": "select_table",
                               "source": "superviseurs"},
            "langue": {"label": "Langue", "type": "select", "options": ["fr", "en"]},
            "contenu_html": {"label": "Contenu", "type": "long"},
            "actif": {"label": "Actif", "type": "booleen"},
        },
    },
}

# Colonne servant de libellé dans les listes déroulantes
LIBELLE_SOURCE = {
    "types_message": ("code", "libelle"),
    "superviseurs": ("id", "nom"),
    "domaines": ("id", "nom"),
    "equipes": ("id", "nom"),
}


def _cle(table: str) -> str:
    return TABLES[table].get("cle", "id")


def _valider(table: str) -> tuple[bool, str]:
    if table not in TABLES:
        return False, f"Table inconnue : {table}"
    return True, ""


# ======================================================================
#  Description de l'interface d'administration
# ======================================================================

@api_admin.get("/api/v5/admin/schema")
def schema_admin():
    """Décrit les tables administrables : l'interface se construit à partir d'ici."""
    conn = get_conn()
    try:
        sources = {}
        for src, (col_id, col_lib) in LIBELLE_SOURCE.items():
            try:
                sources[src] = [
                    {"valeur": r[col_id], "libelle": r[col_lib]}
                    for r in conn.execute(
                        f"SELECT {col_id}, {col_lib} FROM {src} ORDER BY {col_lib}")
                ]
            except Exception:
                sources[src] = []
    finally:
        conn.close()

    return jsonify({
        "ok": True,
        "tables": {
            nom: {k: v for k, v in cfg.items() if k != "tri"}
            for nom, cfg in TABLES.items()
        },
        "sources": sources,
    })


# ======================================================================
#  CRUD générique
# ======================================================================

@api_admin.get("/api/v5/admin/<table>")
def lister(table: str):
    ok, msg = _valider(table)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 404

    cfg = TABLES[table]
    colonnes = [_cle(table)] + cfg["colonnes"]
    conn = get_conn()
    try:
        sql = f"SELECT {', '.join(colonnes)} FROM {table} ORDER BY {cfg['tri']}"
        if limite := cfg.get("limite"):
            sql += f" LIMIT {int(limite)}"
        lignes = [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()
    return jsonify({"ok": True, "count": len(lignes), "lignes": lignes})


@api_admin.post("/api/v5/admin/<table>")
def creer(table: str):
    ok, msg = _valider(table)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 404

    cfg = TABLES[table]
    d = request.get_json(silent=True) or {}

    manquants = [c for c in cfg.get("obligatoires", [])
                 if not str(d.get(c, "")).strip()]
    if manquants:
        libelles = [cfg["champs"][c]["label"] for c in manquants]
        return jsonify({"ok": False,
                        "error": "Champs requis : " + ", ".join(libelles)}), 400

    # Seules les colonnes du descripteur sont acceptées.
    colonnes = [c for c in cfg["colonnes"] if c in d]
    if cfg.get("cle") and cfg["cle"] in d and cfg["cle"] not in colonnes:
        colonnes.insert(0, cfg["cle"])
    if not colonnes:
        return jsonify({"ok": False, "error": "Aucune donnée"}), 400

    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                f"INSERT INTO {table} ({', '.join(colonnes)}) "
                f"VALUES ({', '.join('?' * len(colonnes))})",
                tuple(d[c] for c in colonnes))
        return jsonify({"ok": True, "id": cur.lastrowid}), 201
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


@api_admin.put("/api/v5/admin/<table>/<identifiant>")
def modifier(table: str, identifiant: str):
    ok, msg = _valider(table)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 404

    cfg = TABLES[table]
    d = request.get_json(silent=True) or {}
    colonnes = [c for c in cfg["colonnes"] if c in d]
    if not colonnes:
        return jsonify({"ok": False, "error": "Aucun champ à modifier"}), 400

    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                f"UPDATE {table} SET {', '.join(c + ' = ?' for c in colonnes)} "
                f"WHERE {_cle(table)} = ?",
                tuple(d[c] for c in colonnes) + (identifiant,))
        if not cur.rowcount:
            return jsonify({"ok": False, "error": "Ligne introuvable"}), 404
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()


@api_admin.delete("/api/v5/admin/<table>/<identifiant>")
def supprimer(table: str, identifiant: str):
    ok, msg = _valider(table)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 404

    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                f"DELETE FROM {table} WHERE {_cle(table)} = ?", (identifiant,))
        if not cur.rowcount:
            return jsonify({"ok": False, "error": "Ligne introuvable"}), 404
        return jsonify({"ok": True})
    except Exception as e:
        # Une contrainte de clé étrangère peut légitimement bloquer : on le dit
        # clairement plutôt que de renvoyer une erreur technique brute.
        return jsonify({"ok": False,
                        "error": "Suppression impossible : cet élément est "
                                 "utilisé ailleurs. Le désactiver plutôt."}), 400
    finally:
        conn.close()


# ======================================================================
#  Paramètres généraux
# ======================================================================

@api_admin.get("/api/v5/admin/parametres/tout")
def lister_parametres():
    """Paramètres groupés par catégorie, prêts à l'affichage."""
    conn = get_conn()
    try:
        lignes = [dict(r) for r in conn.execute(
            """SELECT cle, valeur, type_valeur, categorie, libelle, aide,
                      options, ordre, modifiable
               FROM parametres ORDER BY categorie, ordre""")]
    finally:
        conn.close()

    categories: dict = {}
    for l in lignes:
        categories.setdefault(l["categorie"], []).append(l)

    return jsonify({
        "ok": True,
        "categories": categories,
        "libelles_categories": {
            "organisation": "Organisation",
            "saisie": "Saisie",
            "canaux": "Canaux de communication",
            "envoi": "Envoi",
            "charte_mail": "Charte des e-mails",
            "reporting": "Rapports",
            "interface": "Interface",
            "general": "Général",
        },
    })


@api_admin.put("/api/v5/admin/parametres")
def modifier_parametres():
    """Écrit un lot de paramètres."""
    d = request.get_json(silent=True) or {}
    modifies, refuses = [], []
    for cle, valeur in d.items():
        (modifies if definir_parametre(cle, valeur) else refuses).append(cle)
    return jsonify({"ok": True, "modifies": modifies, "refuses": refuses})


@api_admin.post("/api/v5/admin/parametres/reinitialiser")
def reinitialiser():
    """Recharge les valeurs par défaut manquantes, sans écraser l'existant."""
    return jsonify({"ok": True, "bilan": charger_defauts()})
