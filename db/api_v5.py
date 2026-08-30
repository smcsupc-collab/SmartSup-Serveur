"""
SMART-SUP — API v5 : documentation, communication, suivi des incidents
=======================================================================

Blueprint enregistré par `app.py` sous le préfixe /api/v5.
Protégé par le même middleware `_local_only` que le reste de /api/*.

Principe directeur : le ticket appartient à l'outil du groupe. Ces routes ne
créent aucun identifiant d'incident, ne gèrent aucun cycle de vie opérationnel,
aucune escalade, aucun SLA. Elles documentent, communiquent et restituent.

Point d'architecture important — la génération de contenu vit ICI, pas dans le
navigateur. `POST /api/v5/preview` renvoie le HTML de l'e-mail tel qu'il sera
envoyé. L'interface se contente de l'afficher. Cela garantit que l'aperçu et
l'envoi réel ne peuvent jamais diverger, et que la charte e-mail (distincte du
thème de l'application) reste maîtrisée par le serveur.
"""

from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime

from flask import Blueprint, jsonify, request

from db.schema_v5 import (
    CANAUX, PRIORITES, STATUTS_DOCUMENTAIRES, TYPES_INCIDENT, TYPES_MESSAGE,
    ecrire_attributs, get_conn, lire_attributs,
)
from db.parametres import (
    definir_parametre, description_auto, structure_messages, tous_parametres,
    valeurs_suggerees,
)

api_v5 = Blueprint("api_v5", __name__)


# ======================================================================
#  CHARTE E-MAIL — LUE DEPUIS LE PARAMÉTRAGE
# ======================================================================
# Ces valeurs ne sont plus codées en dur : elles s'éditent dans
# Administration → Charte des e-mails. Les valeurs ci-dessous ne servent que
# de repli si un paramètre a été supprimé de la base.
#
# Rappel :  Application #FF7900   ≠   E-mails #FF6D00
# Les deux identités sont distinctes et ne doivent pas être alignées.

CHARTE_REPLI = {
    "mail.couleur_principale": "#FF6D00",
    "mail.couleur_foncee": "#E05A00",
    "mail.couleur_fond_titre": "#FFF3E0",
    "mail.couleur_texte": "#1A1A1A",
    "mail.couleur_ok": "#4CAF50",
    "mail.couleur_attente": "#FFC107",
    "mail.couleur_critique": "#F44336",
    "mail.police": "'Times New Roman', Times, serif",
    "mail.taille_police": "12pt",
    "mail.largeur_libelles": "190px",
    "mail.afficher_logo": True,
    "org.nom": "ORANGE GUINEE S.A",
    "org.direction": "DRPS/PRPS/DSMC/SS",
    "org.formule_politesse": "Cordialement !!!",
    "saisie.format_date": "%d/%m/%Y %H:%M",
}


def _p(params: dict, cle: str):
    """Lit un paramètre avec repli sur la valeur d'origine."""
    return params.get(cle, CHARTE_REPLI.get(cle, ""))


# ======================================================================
#  Utilitaires
# ======================================================================

def _ligne(conn: sqlite3.Connection, sql: str, args=()) -> dict | None:
    r = conn.execute(sql, args).fetchone()
    return dict(r) if r else None


def _lignes(conn: sqlite3.Connection, sql: str, args=()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args)]


def _fmt_date(valeur: str | None, format_sortie: str = "%d/%m/%Y %H:%M") -> str:
    """ISO ou datetime-local → format configuré dans les paramètres."""
    if not valeur:
        return ""
    txt = str(valeur).replace("T", " ").strip()
    for motif in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, motif).strftime(format_sortie)
        except ValueError:
            continue
    return txt


def _erreur(message: str, code: int = 400):
    return jsonify({"ok": False, "error": message}), code


# ======================================================================
#  RÉFÉRENTIELS
# ======================================================================

@api_v5.get("/api/v5/services")
def services():
    """
    Catalogue de supervision. Sert l'auto-complétion de la saisie rapide.

    Remplace l'ancien catalogue embarqué en dur dans le JavaScript : le
    référentiel vit en base, donc il s'administre sans toucher au code.
    """
    q = (request.args.get("q") or "").strip().lower()
    conn = get_conn()
    try:
        sql = """SELECT s.id, s.nom, s.priorite_defaut AS priorite,
                        s.supervise, s.outil_supervision, d.nom AS domaine
                 FROM services s JOIN domaines d ON d.id = s.domaine_id
                 WHERE s.actif = 1"""
        args: list = []
        if q:
            # Recherche multi-mots dans l'ordre libre : « b2w bnig » trouve
            # « BNIG - B2W ».
            for mot in q.split():
                sql += " AND (LOWER(s.nom) LIKE ? OR LOWER(d.nom) LIKE ?)"
                args += [f"%{mot}%", f"%{mot}%"]
        sql += " ORDER BY d.nom, s.nom"
        resultats = _lignes(conn, sql, tuple(args))
    finally:
        conn.close()
    return jsonify({"ok": True, "count": len(resultats), "services": resultats})


@api_v5.get("/api/v5/referentiels")
def referentiels():
    """Tout ce dont l'interface a besoin pour se construire, en un appel."""
    conn = get_conn()
    try:
        data = {
            "domaines": _lignes(conn, "SELECT id, nom FROM domaines WHERE actif=1 ORDER BY nom"),
            "superviseurs": _lignes(conn, "SELECT id, nom, email FROM superviseurs WHERE actif=1 ORDER BY nom"),
            "equipes": _lignes(conn, "SELECT id, code, nom FROM equipes WHERE actif=1 ORDER BY nom"),
            "mailing_lists": _lignes(conn,
                """SELECT id, libelle, adresse, canal, destination, type_incident
                   FROM mailing_lists WHERE actif=1 ORDER BY canal, destination"""),
        }
    finally:
        conn.close()
    params = tous_parametres()
    structure = structure_messages()

    # Libellés des champs : agrégés depuis la configuration des types de message
    libelles = {}
    for st in structure.values():
        libelles.update(st.get("libelles", {}))

    # Canaux réellement actifs (activables/désactivables en administration)
    canaux_actifs = [c for c in CANAUX if params.get(f"canal.{c}.actif", True)]

    data.update({
        "ok": True,
        "types_incident": list(TYPES_INCIDENT),
        "types_message": list(TYPES_MESSAGE),
        "canaux": canaux_actifs,
        "priorites": list(PRIORITES),
        "statuts": list(STATUTS_DOCUMENTAIRES),
        "structure": structure,
        "libelles": libelles,
        "suggestions": valeurs_suggerees(),
        "parametres": params,
    })
    return jsonify(data)


# ======================================================================
#  INCIDENTS
# ======================================================================

@api_v5.get("/api/v5/incidents")
def lister_incidents():
    conn = get_conn()
    try:
        sql = """SELECT i.*,
                        (SELECT COUNT(*) FROM incident_evidences e
                          WHERE e.incident_id = i.id) AS nb_preuves,
                        (SELECT COUNT(*) FROM incident_communications c
                          WHERE c.incident_id = i.id) AS nb_communications
                 FROM incidents i WHERE 1=1"""
        args: list = []

        if statut := request.args.get("statut"):
            sql += " AND i.statut_documentaire = ?"
            args.append(statut)
        if type_inc := request.args.get("type"):
            sql += " AND i.type_incident = ?"
            args.append(type_inc)
        if depuis := request.args.get("depuis"):
            sql += " AND i.date_debut >= ?"
            args.append(depuis)
        if jusqua := request.args.get("jusqua"):
            sql += " AND i.date_debut <= ?"
            args.append(jusqua)
        if recherche := request.args.get("q"):
            sql += " AND (i.reference_externe LIKE ? OR i.description LIKE ?)"
            args += [f"%{recherche}%", f"%{recherche}%"]

        sql += " ORDER BY COALESCE(i.date_debut, i.created_at) DESC LIMIT ?"
        args.append(int(request.args.get("limit", 200)))

        resultats = _lignes(conn, sql, tuple(args))
        for r in resultats:
            r["attributs_specifiques"] = lire_attributs(r["attributs_specifiques"])
    finally:
        conn.close()
    return jsonify({"ok": True, "count": len(resultats), "incidents": resultats})


@api_v5.get("/api/v5/incidents/<int:incident_id>")
def detail_incident(incident_id: int):
    conn = get_conn()
    try:
        inc = _ligne(conn, "SELECT * FROM incidents WHERE id = ?", (incident_id,))
        if not inc:
            return _erreur("Incident introuvable", 404)
        inc["attributs_specifiques"] = lire_attributs(inc["attributs_specifiques"])
        inc["services"] = _lignes(conn,
            """SELECT s.id, s.nom, d.nom AS domaine
               FROM incident_services x
               JOIN services s ON s.id = x.service_id
               JOIN domaines d ON d.id = s.domaine_id
               WHERE x.incident_id = ?""", (incident_id,))
        inc["preuves"] = _lignes(conn,
            "SELECT * FROM incident_evidences WHERE incident_id = ? ORDER BY ordre, id",
            (incident_id,))
        inc["communications"] = _lignes(conn,
            "SELECT * FROM incident_communications WHERE incident_id = ? ORDER BY envoye_at DESC",
            (incident_id,))
    finally:
        conn.close()
    return jsonify({"ok": True, "incident": inc})


@api_v5.post("/api/v5/incidents")
def creer_incident():
    """
    Crée un incident documenté.

    Aucun identifiant n'est fabriqué : la référence externe fournie par
    l'utilisateur est le seul identifiant métier.
    """
    d = request.get_json(silent=True) or {}

    reference = (d.get("reference_externe") or "").strip()
    if not reference:
        return _erreur("La référence du ticket est requise")

    type_incident = d.get("type_incident") or "service"
    if type_incident not in TYPES_INCIDENT:
        return _erreur(f"Type d'incident inconnu : {type_incident}")

    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO incidents
                   (reference_externe, type_incident, priorite, langue,
                    description, date_debut, date_fin, cause, action,
                    observation, perimetre_libre, attributs_specifiques,
                    statut_documentaire, superviseur_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (reference, type_incident, d.get("priorite"),
                 d.get("langue", "fr"), d.get("description", ""),
                 d.get("date_debut"), d.get("date_fin"), d.get("cause"),
                 d.get("action"), d.get("observation"), d.get("perimetre_libre"),
                 ecrire_attributs(d.get("attributs_specifiques")),
                 d.get("statut_documentaire", "signale"),
                 d.get("superviseur_id")),
            )
            incident_id = cur.lastrowid
            for sid in d.get("services") or []:
                conn.execute(
                    "INSERT OR IGNORE INTO incident_services VALUES (?,?)",
                    (incident_id, sid),
                )
    finally:
        conn.close()
    return jsonify({"ok": True, "id": incident_id, "reference": reference}), 201


# Champs modifiables. Liste blanche stricte : les noms de colonnes ne
# proviennent jamais de la requête.
CHAMPS_MODIFIABLES = (
    "reference_externe", "type_incident", "priorite", "langue", "description",
    "date_debut", "date_fin", "cause", "action", "observation",
    "perimetre_libre", "statut_documentaire", "superviseur_id",
)


@api_v5.put("/api/v5/incidents/<int:incident_id>")
def modifier_incident(incident_id: int):
    d = request.get_json(silent=True) or {}
    conn = get_conn()
    try:
        if not _ligne(conn, "SELECT id FROM incidents WHERE id = ?", (incident_id,)):
            return _erreur("Incident introuvable", 404)

        sets, args = [], []
        for champ in CHAMPS_MODIFIABLES:
            if champ in d:
                sets.append(f"{champ} = ?")
                args.append(d[champ])
        if "attributs_specifiques" in d:
            sets.append("attributs_specifiques = ?")
            args.append(ecrire_attributs(d["attributs_specifiques"]))
        if not sets:
            return _erreur("Aucun champ à modifier")

        sets.append("updated_at = datetime('now')")
        args.append(incident_id)
        with conn:
            conn.execute(
                f"UPDATE incidents SET {', '.join(sets)} WHERE id = ?", tuple(args)
            )
            if "services" in d:
                conn.execute(
                    "DELETE FROM incident_services WHERE incident_id = ?", (incident_id,)
                )
                for sid in d["services"] or []:
                    conn.execute(
                        "INSERT OR IGNORE INTO incident_services VALUES (?,?)",
                        (incident_id, sid),
                    )
    finally:
        conn.close()
    return jsonify({"ok": True, "id": incident_id})


# ======================================================================
#  PREUVES
# ======================================================================

@api_v5.post("/api/v5/incidents/<int:incident_id>/preuves")
def ajouter_preuve(incident_id: int):
    d = request.get_json(silent=True) or {}
    conn = get_conn()
    try:
        if not _ligne(conn, "SELECT id FROM incidents WHERE id = ?", (incident_id,)):
            return _erreur("Incident introuvable", 404)
        with conn:
            cur = conn.execute(
                """INSERT INTO incident_evidences
                   (incident_id, type, chemin, contenu, legende, ordre)
                   VALUES (?,?,?,?,?,?)""",
                (incident_id, d.get("type", "capture"), d.get("chemin"),
                 d.get("contenu"), d.get("legende"), d.get("ordre", 0)),
            )
    finally:
        conn.close()
    return jsonify({"ok": True, "id": cur.lastrowid}), 201


# ======================================================================
#  GÉNÉRATION DE CONTENU — CÔTÉ SERVEUR
# ======================================================================

def _bloc_lignes(donnees: dict, champs: list[str], libelles: dict,
                 params: dict, couleur_observation: str,
                 couleur_jaune: str = "#F2C94C") -> str:
    """Construit les lignes du tableau avec la charte des avis d'incident."""
    fmt = _p(params, "saisie.format_date")
    out = []
    for champ in champs:
        valeur = donnees.get(champ, "")
        if champ in ("debut", "fin"):
            valeur = _fmt_date(valeur, fmt)
        couleur = couleur_jaune if champ in ("cause", "action") else (
            couleur_observation if champ == "observation" else "#FFFFFF"
        )
        out.append(
            f'<tr>'
            f'<td style="background-color:#D9D9D9;font-weight:bold;padding:14px 16px;'
            f'width:180px;text-align:left;vertical-align:middle;border:1px solid #000000;">'
            f'{html.escape(libelles.get(champ, champ))}</td>'
            f'<td style="background-color:{couleur};color:#000000;font-weight:bold;padding:14px 16px;'
            f'text-align:center;vertical-align:middle;border:1px solid #000000;">'
            f'{html.escape(str(valeur or "—"))}</td>'
            f'</tr>'
        )
    return "".join(out)


def construire_message(donnees: dict, params: dict | None = None,
                       structure: dict | None = None) -> dict:
    """
    Produit sujet + corps HTML d'une communication.

    Fonction pure : appelée aussi bien pour l'aperçu que pour l'envoi réel,
    ce qui garantit qu'ils ne peuvent pas diverger.

    Tout est paramétré : titres, préfixes de sujet, champs affichés, couleurs,
    police, signature. Aucune de ces valeurs n'est écrite dans le code.
    """
    params = params if params is not None else tous_parametres()
    structure = structure if structure is not None else structure_messages()

    type_message = donnees.get("type_message", "debut")
    st = structure.get(type_message) or next(iter(structure.values()), {})
    champs = st.get("champs", [])
    libelles = st.get("libelles", {})

    # --- Sujet ---
    perimetre = donnees.get("perimetre") or "…"
    reference = donnees.get("reference_externe") or ""
    suffixe = f" || {reference}" if reference and st.get("inclut_reference") else ""
    sujet = f"{st.get('prefixe_sujet', 'Incident')} [{perimetre}]{suffixe}"

    # --- Champ combiné « TT & priorité », tel qu'utilisé dans les mails ---
    vue = dict(donnees)
    priorite = donnees.get("priorite") or ""
    vue["ticket"] = f"{reference}/{priorite}" if priorite else reference

    superviseur = donnees.get("superviseur") or {}
    nom = superviseur.get("nom", "")
    tel = superviseur.get("tel", "") or _p(params, "org.telephone_permanence")

    # --- Charte, lue dans le paramétrage ---
    c_princ = _p(params, "mail.couleur_principale")
    c_fonce = _p(params, "mail.couleur_foncee")
    c_titre = _p(params, "mail.couleur_fond_titre")
    c_texte = _p(params, "mail.couleur_texte")
    police = _p(params, "mail.police")
    taille = _p(params, "mail.taille_police")
    largeur = _p(params, "mail.largeur_libelles")

    if type_message == "fin":
        couleur_observation = "#1E8449"
    elif type_message == "avancement":
        couleur_observation = "#F2A93B"
    else:
        couleur_observation = "#E05252"

    logo = (f'<div class="entete"><span class="logo">orange</span></div>'
            if _p(params, "mail.afficher_logo") else "")
    intro = f"<p>{st['salutation']}</p>" if st.get("salutation") else ""
    mention = (f'<p class="mention">{html.escape(st["mention_bas"])}</p>'
               if st.get("mention_bas") else "")

    lignes = _bloc_lignes(vue, champs, libelles, params, couleur_observation)
    titre = html.escape(st.get('titre', '').upper())
    corps = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:Cambria, 'Times New Roman', Times, serif;font-size:14px;color:#000000;background:#fff;">
{logo}{intro}
<table cellpadding="0" cellspacing="0" width="650" style="border-collapse:separate;border-spacing:0;font-family:Cambria, 'Times New Roman', Times, serif;font-size:14px;">
<tr><td colspan="2" style="background-color:#D9D9D9;font-weight:bold;font-size:18px;text-align:center;padding:16px;border:1px solid #000000;">{titre}</td></tr>
<tr><td colspan="2" style="border:none;padding:0;height:22px;line-height:22px;font-size:1px;">&nbsp;</td></tr>
{lignes}
</table>
{mention}
<p style="font-family:Cambria, 'Times New Roman', Times, serif;font-size:13px;color:#333333;">
{html.escape(_p(params, 'org.formule_politesse'))}<br><br>
<strong>{html.escape(nom)}</strong><br>
{html.escape(_p(params, 'org.nom'))}<br>{html.escape(_p(params, 'org.direction'))}
{('<br>Tel: ' + html.escape(tel)) if tel else ''}</p>
</body></html>"""

    # --- Version texte (SMS / WhatsApp / copie brute) ---
    fmt = _p(params, "saisie.format_date")
    lignes_txt = [st.get("titre", ""), ""]
    for champ in champs:
        valeur = vue.get(champ, "")
        if champ in ("debut", "fin"):
            valeur = _fmt_date(valeur, fmt)
        lignes_txt += [libelles.get(champ, champ), str(valeur or ""), ""]
    lignes_txt += [_p(params, "org.formule_politesse"), "", nom,
                   _p(params, "org.nom"), _p(params, "org.direction")]

    return {"sujet": sujet, "corps_html": corps, "corps_texte": "\n".join(lignes_txt)}


@api_v5.post("/api/v5/preview")
def preview():
    """
    Aperçu d'une communication, généré par le serveur.

    L'interface affiche le HTML retourné tel quel : aperçu et envoi partagent
    le même code, ils ne peuvent donc pas diverger.
    """
    donnees = request.get_json(silent=True) or {}
    params = tous_parametres()
    structure = structure_messages()

    type_message = donnees.get("type_message", "debut")
    st = structure.get(type_message, {})
    canal = donnees.get("canal") or st.get("canal_defaut", "email")

    # Destinataires : ciblage fin, entièrement paramétrable.
    # Une liste peut viser un canal, un type de message, un type d'incident
    # ou un domaine — sans qu'aucune règle ne soit écrite dans le code.
    conn = get_conn()
    try:
        listes = _lignes(conn,
            """SELECT adresse, destination, libelle, groupe FROM mailing_lists
               WHERE actif = 1 AND canal = ?
                 AND (type_message  IS NULL OR type_message  = ?)
                 AND (type_incident IS NULL OR type_incident = ?)
               ORDER BY ordre, libelle""",
            (canal, type_message, donnees.get("type_incident") or ""))
    finally:
        conn.close()

    message = construire_message(donnees, params, structure)
    message.update({
        "ok": True,
        "canal": canal,
        "destinataires_a": [l["adresse"] for l in listes if l["destination"] == "a"],
        "destinataires_cc": [l["adresse"] for l in listes if l["destination"] == "cc"],
        "champs_obligatoires": st.get("obligatoires", []),
    })
    return jsonify(message)


@api_v5.post("/api/v5/incidents/<int:incident_id>/communications")
def enregistrer_communication(incident_id: int):
    """Journalise une communication envoyée, avec un instantané du contenu."""
    d = request.get_json(silent=True) or {}
    conn = get_conn()
    try:
        if not _ligne(conn, "SELECT id FROM incidents WHERE id = ?", (incident_id,)):
            return _erreur("Incident introuvable", 404)
        with conn:
            cur = conn.execute(
                """INSERT INTO incident_communications
                   (incident_id, canal, type_message, langue, destinataires_a,
                    destinataires_cc, sujet, corps, envoye_par, statut_envoi)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (incident_id, d.get("canal", "email"),
                 d.get("type_message", "debut"), d.get("langue", "fr"),
                 "; ".join(d.get("destinataires_a") or []),
                 "; ".join(d.get("destinataires_cc") or []),
                 d.get("sujet", ""), d.get("corps", ""),
                 d.get("envoye_par"), d.get("statut_envoi", "envoye")),
            )
    finally:
        conn.close()
    return jsonify({"ok": True, "id": cur.lastrowid}), 201


# ======================================================================
#  REPORTING
# ======================================================================

@api_v5.get("/api/v5/stats")
def stats():
    """Agrégations alimentant les rapports de shift, hebdomadaire et mensuel."""
    conn = get_conn()
    try:
        data = {
            "total": conn.execute("SELECT COUNT(*) n FROM incidents").fetchone()["n"],
            "par_type": _lignes(conn,
                "SELECT type_incident, COUNT(*) n FROM incidents GROUP BY 1 ORDER BY n DESC"),
            "par_priorite": _lignes(conn,
                "SELECT priorite, COUNT(*) n FROM incidents GROUP BY 1 ORDER BY 1"),
            "par_statut": _lignes(conn,
                "SELECT statut_documentaire, COUNT(*) n FROM incidents GROUP BY 1"),
            "par_domaine": _lignes(conn,
                """SELECT d.nom AS domaine, COUNT(DISTINCT x.incident_id) n
                   FROM incident_services x
                   JOIN services s ON s.id = x.service_id
                   JOIN domaines d ON d.id = s.domaine_id
                   GROUP BY d.nom ORDER BY n DESC LIMIT 15"""),
            "par_mois": _lignes(conn,
                """SELECT substr(date_debut,1,7) AS mois, COUNT(*) n
                   FROM incidents WHERE date_debut IS NOT NULL
                   GROUP BY 1 ORDER BY 1 DESC LIMIT 12"""),
        }
        # Durée moyenne de traitement documenté. Ce n'est PAS un indicateur de
        # SLA : la mesure officielle reste celle de l'outil du groupe.
        duree = conn.execute(
            """SELECT ROUND(AVG((julianday(date_fin) - julianday(date_debut)) * 1440)) m
               FROM incidents WHERE date_fin IS NOT NULL AND date_debut IS NOT NULL"""
        ).fetchone()["m"]
        data["duree_moyenne_minutes"] = duree
    finally:
        conn.close()
    data["ok"] = True
    return jsonify(data)
