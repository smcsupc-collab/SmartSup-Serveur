"""
SMART-SUP — Couche de paramétrage
==================================

Tout ce qui était codé en dur (destinataires, formulations, structure des
messages, couleurs, signature, comportements) vit désormais en base et
s'édite depuis l'écran Administration.

Règle appliquée : *aucune modification de code* pour ajouter un destinataire,
une formulation, un type de message, ou pour activer/désactiver une option.

Le chargement initial ci-dessous ne s'exécute qu'une fois : les valeurs
existantes ne sont jamais écrasées, pour ne pas perdre le paramétrage du
superviseur à chaque redémarrage du serveur.
"""

from __future__ import annotations

import json
from pathlib import Path

from db.schema_v5 import get_conn


# ======================================================================
#  PARAMÈTRES GÉNÉRAUX
#  (cle, valeur, type, catégorie, libellé, aide, options, ordre)
# ======================================================================
PARAMETRES_DEFAUT = [

    # ---------------- Identité de l'organisation ----------------
    ("org.nom", "ORANGE GUINEE S.A", "texte", "organisation",
     "Raison sociale", "Apparaît dans la signature des communications", None, 10),
    ("org.direction", "DRPS/PRPS/DSMC/SS", "texte", "organisation",
     "Direction / service", "Ligne sous la raison sociale dans la signature", None, 20),
    ("org.formule_politesse", "Cordialement !!!", "texte", "organisation",
     "Formule de politesse", "Ligne qui introduit la signature", None, 30),
    ("org.telephone_permanence", "+224 620 691 214", "texte", "organisation",
     "Téléphone de permanence", "Affiché sous la signature si renseigné", None, 40),

    # ---------------- Comportement de saisie ----------------
    ("saisie.motif_reference", r"\d{4}[A-Za-z]\d{5}", "texte", "saisie",
     "Motif de reconnaissance des références",
     "Expression régulière servant à extraire la référence d'un collage brut. "
     "Vider ce champ pour accepter n'importe quelle saisie.", None, 10),
    ("saisie.priorite_defaut", "P1", "liste", "saisie",
     "Priorité par défaut",
     "Utilisée quand le service du catalogue n'en définit pas",
     json.dumps(["P1", "P2", "P3"]), 20),
    ("saisie.heriter_priorite_service", "1", "booleen", "saisie",
     "Hériter la priorité du service",
     "La priorité se pré-remplit depuis le catalogue à la sélection du service", None, 30),
    ("saisie.description_auto", "1", "booleen", "saisie",
     "Description automatique",
     "Pré-remplit la description selon les règles configurées", None, 40),
    ("saisie.confirmer_avant_envoi", "1", "booleen", "saisie",
     "Confirmer avant enregistrement",
     "Demande une confirmation si des champs obligatoires manquent", None, 50),
    ("saisie.format_date", "%d/%m/%Y %H:%M", "texte", "saisie",
     "Format des dates dans les messages",
     "Format d'affichage dans les communications générées", None, 60),

    # ---------------- Canaux ----------------
    ("canal.email.actif", "1", "booleen", "canaux",
     "Canal E-mail", "Active la génération de messages e-mail", None, 10),
    ("canal.notification_arpt.actif", "1", "booleen", "canaux",
     "Canal Notification / ARPT", "Active les notifications réglementaires", None, 20),
    ("canal.sms.actif", "1", "booleen", "canaux",
     "Canal SMS", "Active la génération de messages SMS", None, 30),
    ("canal.whatsapp.actif", "1", "booleen", "canaux",
     "Canal WhatsApp", "Active la génération de messages WhatsApp", None, 40),
    ("canal.web.actif", "0", "booleen", "canaux",
     "Canal Web", "Publication sur une page de consultation interne", None, 50),
    ("canal.sms.longueur_max", "320", "nombre", "canaux",
     "Longueur maximale d'un SMS", "Avertit au-delà de cette longueur", None, 60),

    # ---------------- Envoi ----------------
    ("envoi.mode", "afficher", "liste", "envoi",
     "Mode d'envoi Outlook",
     "« afficher » ouvre le message pour relecture, « envoyer » l'expédie directement",
     json.dumps(["afficher", "envoyer"]), 10),
    ("envoi.repli_eml", "1", "booleen", "envoi",
     "Repli fichier .eml",
     "Si Outlook est indisponible, produit un fichier .eml ouvrable", None, 20),
    ("envoi.journaliser", "1", "booleen", "envoi",
     "Journaliser les communications",
     "Conserve un instantané de chaque message envoyé", None, 30),
    ("envoi.copie_expediteur", "0", "booleen", "envoi",
     "Mettre l'expéditeur en copie", "Ajoute le superviseur en Cc", None, 40),

    # ---------------- Charte des e-mails ----------------
    # Distincte du thème de l'application : ne pas aligner sur #FF7900.
    ("mail.couleur_principale", "#FF6D00", "couleur", "charte_mail",
     "Orange des e-mails",
     "Charte des communications, volontairement distincte du thème de "
     "l'application (#FF7900). Ne pas aligner sans décision explicite.", None, 10),
    ("mail.couleur_foncee", "#E05A00", "couleur", "charte_mail",
     "Orange foncé", "Dégradé du bandeau d'en-tête", None, 20),
    ("mail.couleur_fond_titre", "#FFF3E0", "couleur", "charte_mail",
     "Fond du titre", "Encadré du titre d'avis", None, 30),
    ("mail.couleur_texte", "#1A1A1A", "couleur", "charte_mail",
     "Couleur du texte", None, None, 40),
    ("mail.couleur_ok", "#4CAF50", "couleur", "charte_mail",
     "Vert (résolu)", "État résolu, encadré de durée", None, 50),
    ("mail.couleur_attente", "#FFC107", "couleur", "charte_mail",
     "Ambre (en cours)", None, None, 60),
    ("mail.couleur_critique", "#F44336", "couleur", "charte_mail",
     "Rouge (critique)", None, None, 70),
    ("mail.police", "'Times New Roman', Times, serif", "texte", "charte_mail",
     "Police des e-mails", "Police utilisée dans le corps des messages", None, 80),
    ("mail.taille_police", "12pt", "texte", "charte_mail",
     "Taille de police", None, None, 90),
    ("mail.afficher_logo", "1", "booleen", "charte_mail",
     "Afficher le bandeau logo", None, None, 100),
    ("mail.largeur_libelles", "190px", "texte", "charte_mail",
     "Largeur de la colonne des libellés", None, None, 110),

    # ---------------- Reporting ----------------
    ("rapport.shifts_par_jour", "3", "nombre", "reporting",
     "Nombre de shifts par jour", "Découpage du rapport de fin de shift", None, 10),
    ("rapport.heure_debut_shift1", "06:00", "texte", "reporting",
     "Heure de début du 1er shift", None, None, 20),
    ("rapport.jour_debut_semaine", "1", "liste", "reporting",
     "Premier jour de la semaine", "Pour le découpage hebdomadaire",
     json.dumps(["1", "2", "3", "4", "5", "6", "7"]), 30),
    ("rapport.inclure_non_averes", "0", "booleen", "reporting",
     "Inclure les incidents non avérés", None, None, 40),
    ("rapport.seuil_incident_majeur", "P1", "liste", "reporting",
     "Seuil « incident majeur »", "Priorité à partir de laquelle un incident est majeur",
     json.dumps(["P1", "P2", "P3"]), 50),

    # ---------------- Interface ----------------
    ("ui.theme", "sombre", "liste", "interface",
     "Thème de l'interface",
     "Apparence de l'application. N'affecte ni les e-mails ni les rapports, "
     "qui conservent leur charte propre.",
     json.dumps(["clair", "sombre", "furtif", "noc", "auto"]), 5),
    ("ui.theme_couleur", "#FF7900", "couleur", "interface",
     "Couleur d'accent de l'application",
     "Thème de l'interface. N'affecte pas les e-mails.", None, 10),
    ("ui.afficher_jauge", "1", "booleen", "interface",
     "Afficher la jauge de complétude", None, None, 20),
    ("ui.suggestions_max", "40", "nombre", "interface",
     "Nombre maximum de suggestions", "Résultats affichés dans l'auto-complétion", None, 30),
    ("ui.apercu_auto", "1", "booleen", "interface",
     "Aperçu automatique", "Rafraîchit l'aperçu à chaque frappe", None, 40),
    ("ui.avertir_service_non_supervise", "1", "booleen", "interface",
     "Signaler les services non supervisés",
     "Affiche une mention dans les suggestions", None, 50),
]


# ======================================================================
#  TYPES DE MESSAGE ET LEURS CHAMPS
# ======================================================================
TYPES_MESSAGE_DEFAUT = [
    # code, libellé, titre, préfixe sujet, réf?, salutation, mention, canal, ordre
    ("debut", "Avis de début", "AVIS DE DÉBUT D'INCIDENT",
     "Avis de début d'incident", 1, None, None, "email", 10),
    ("avancement", "Point d'avancement", "POINT D'AVANCEMENT",
     "Point d'avancement", 1, None, None, "email", 20),
    ("fin", "Avis de fin", "AVIS DE FIN D'INCIDENT",
     "Avis de fin d'incident", 1, None, None, "email", 30),
    ("regularisation", "Régularisation", "[RÉGULARISATION] AVIS DE FIN D'INCIDENT",
     "[Régularisation] Avis de fin d'incident", 1, None, None, "email", 40),
    ("notification", "Notification ARPT", "AVIS DE FIN D'INCIDENT",
     "Notification d'incident", 0,
     "Bonjour,<br>Merci de recevoir la notification d'incident ci-dessous.",
     "Copie ARPT", "notification_arpt", 50),
    ("non_avere", "Incident non avéré", "INCIDENT NON AVÉRÉ",
     "Incident non avéré", 1, None, None, "email", 60),
]

# type_message, champ, libellé, obligatoire, ordre
CHAMPS_DEFAUT = [
    ("debut", "description", "Description", 1, 10),
    ("debut", "debut", "Début", 1, 20),
    ("debut", "ticket", "TT & priorité", 1, 30),
    ("debut", "cause", "Cause", 1, 40),
    ("debut", "perimetre", "Service impacté", 1, 50),
    ("debut", "observation", "Observation", 0, 60),

    ("avancement", "description", "Description", 1, 10),
    ("avancement", "debut", "Début", 1, 20),
    ("avancement", "ticket", "TT & priorité", 1, 30),
    ("avancement", "cause", "Cause", 1, 40),
    ("avancement", "action", "Action", 1, 50),
    ("avancement", "perimetre", "Service impacté", 1, 60),
    ("avancement", "observation", "Observation", 0, 70),

    ("fin", "description", "Description", 1, 10),
    ("fin", "debut", "Début", 1, 20),
    ("fin", "fin", "Fin", 1, 30),
    ("fin", "ticket", "TT & priorité", 1, 40),
    ("fin", "cause", "Cause", 1, 50),
    ("fin", "action", "Action", 1, 60),
    ("fin", "perimetre", "Service impacté", 1, 70),
    ("fin", "observation", "Observation", 0, 80),

    ("regularisation", "description", "Description", 1, 10),
    ("regularisation", "debut", "Début", 1, 20),
    ("regularisation", "fin", "Fin", 1, 30),
    ("regularisation", "ticket", "TT & priorité", 1, 40),
    ("regularisation", "cause", "Cause", 1, 50),
    ("regularisation", "action", "Action", 1, 60),
    ("regularisation", "perimetre", "Service impacté", 1, 70),
    ("regularisation", "observation", "Observation", 0, 80),

    # Gabarit ARPT : ni dates ni référence, mais zone et TMC.
    ("notification", "description", "Description", 1, 10),
    ("notification", "cause", "Cause", 1, 20),
    ("notification", "action", "Action", 1, 30),
    ("notification", "zone", "Zone impactée", 1, 40),
    ("notification", "tmc", "TMC", 1, 50),
    ("notification", "observation", "Observation", 0, 60),

    ("non_avere", "description", "Description", 1, 10),
    ("non_avere", "debut", "Début", 1, 20),
    ("non_avere", "ticket", "TT & priorité", 1, 30),
    ("non_avere", "cause", "Cause", 0, 40),
    ("non_avere", "perimetre", "Service impacté", 1, 50),
    ("non_avere", "observation", "Observation", 0, 60),
]


# ======================================================================
#  VALEURS SUGGÉRÉES (relevées dans les communications réelles)
# ======================================================================
VALEURS_DEFAUT = [
    # (liste, valeur, contexte)
    ("causes", "Investigation en cours", None),
    ("causes", "En attente du retour", None),
    ("causes", "Coupure de fibre", None),
    ("causes", "Problème d'énergie sur le site", None),
    ("causes", "Souci énergétique sur le site", None),
    ("causes", "Dysfonctionnement du GE", None),
    ("causes", "Souci de communication avec le partenaire", None),
    ("causes", "Double coupure de fibre", None),

    ("actions", "Investigation en cours", None),
    ("actions", "En attente du retour", None),
    ("actions", "En attente du retour du GNOC", None),
    ("actions", "En attente du retour du partenaire", None),
    ("actions", "Soudure de fibre", None),
    ("actions", "Remise en service du groupe électrogène", None),
    ("actions", "Basculement du VPN", None),
    ("actions", "Rétablissement de l'énergie", None),

    ("observations", "Sites Down", "debut"),
    ("observations", "Sites instables", "debut"),
    ("observations", "Liens Down", "debut"),
    ("observations", "Service indisponible", "debut"),
    ("observations", "Investigation en cours", "avancement"),
    ("observations", "Sites instables", "avancement"),
    ("observations", "Sites UP", "fin"),
    ("observations", "Liens UP", "fin"),
    ("observations", "Lien UP", "fin"),
    ("observations", "Service disponible", "fin"),
    ("observations", "Sites UP", "regularisation"),
    ("observations", "Liens UP", "regularisation"),
    ("observations", "Service disponible", "regularisation"),
    ("observations", "Sites UP", "notification"),
    ("observations", "Sites instables", "notification"),
    ("observations", "Incident non avéré", "non_avere"),

    # Régions administratives de Guinée
    ("zones", "Conakry", None),
    ("zones", "Boké", None),
    ("zones", "Kindia", None),
    ("zones", "Mamou", None),
    ("zones", "Labé", None),
    ("zones", "Faranah", None),
    ("zones", "Kankan", None),
    ("zones", "N'Zérékoré", None),

    # Seul « Orange » a été observé dans les communications fournies.
    # Les suivants sont des propositions, à ajuster en administration.
    ("tmc", "Orange", None),
    ("tmc", "Huawei", None),
    ("tmc", "Ericsson", None),
    ("tmc", "Nokia", None),
    ("tmc", "ZTE", None),
    ("tmc", "Autre", None),
]


# ======================================================================
#  RÈGLES DE DESCRIPTION AUTOMATIQUE
#  (remplacent les conditions codées dans le JavaScript)
# ======================================================================
REGLES_DESCRIPTION_DEFAUT = [
    ("bank to wallet", "Indisponibilité du service {domaine} / {service}", 30),
    ("orange money", "Impossible d'effectuer des opérations {service}", 20),
    ("voix", "Perturbation du service {service}", 20),
    ("nimba", "Dysfonctionnement du service {service}", 20),
    ("", "Indisponibilité du service {service}", 0),   # règle de repli
]


# ======================================================================
#  LISTES DE DIFFUSION (adresses relevées dans les e-mails réels)
# ======================================================================
# Convention observée : les partenaires qui doivent agir/relayer sont en
# « à », les équipes internes Orange en « cc ».
DIFFUSION_DEFAUT = [
    # (libellé, adresse, canal, destination, type_message, groupe, ordre)
    ("Remontées réseau Conakry", "RemonteesreseauGConakry1@orange-sonatel.com",
     "email", "a", None, "Partenaires", 10),
    ("PCCI Guinée", "TeamPCCIGuinee_OGC@pcci.sn",
     "email", "a", None, "Partenaires", 20),
    ("Teranga Consulting", "teamteranga@teranga-consulting.com",
     "email", "a", None, "Partenaires", 30),
    ("CallMe Guinée", "teamcallme@callmeguinee.com",
     "email", "a", None, "Partenaires", 40),

    ("Hotline B2B", "Plateau_Hotline_B2B_OGN@orange-sonatel.com",
     "email", "cc", None, "Interne", 50),
    ("Remontées Orange Money", "RemonteesOrangeMoneyGuinee@orange-sonatel.com",
     "email", "cc", None, "Interne", 60),
    ("Back Office Service Client", "BO_SERVICE_CLIENT_OGN@orange-sonatel.com",
     "email", "cc", None, "Interne", 70),
    ("SSOOM DREC", "SSOOM_DREC@orange-sonatel.com",
     "email", "cc", None, "Interne", 80),
    ("SCD DREC", "SCD_DREC@orange-sonatel.com",
     "email", "cc", None, "Interne", 90),
    ("Responsables Applications", "RA_OGC@orange-sonatel.com",
     "email", "cc", None, "Interne", 100),
    ("Responsables Zone", "RZ_OGC@orange-sonatel.com",
     "email", "cc", None, "Interne", 110),

    # Canal réglementaire : destinataires ARPT
    ("ARPT — D. Kamano", "kamano.dominiqueEdouard@arpt.gov.gn",
     "notification_arpt", "a", None, "ARPT", 10),
    ("ARPT — O. Traoré", "traore.ousmane@arpt.gov.gn",
     "notification_arpt", "a", None, "ARPT", 20),
    ("ARPT — A. Condé", "conde.adama@arpt.gov.gn",
     "notification_arpt", "cc", None, "ARPT", 30),
    ("Direction — K. Camara", "kerfallamarie.camara@orange-sonatel.com",
     "notification_arpt", "cc", None, "Direction", 40),
    ("Direction — C. Diallo", "cheickat.diallo@orange-sonatel.com",
     "notification_arpt", "cc", None, "Direction", 50),
    ("Direction — M. Diallo", "marlyatou.diallo@orange-sonatel.com",
     "notification_arpt", "cc", None, "Direction", 60),
]

# Superviseurs relevés dans les signatures des communications réelles.
SUPERVISEURS_DEFAUT = [
    ("Mohamed SYLLA", "mohamed.sylla@orange-sonatel.com"),
    ("Abdourahmane BARRY", "abdourahmane.barry@orange-sonatel.com"),
    ("Youssouf SYLLA", "youssouf.sylla@orange-sonatel.com"),
    ("Souleymane BAH", "souleymane.bah@orange-sonatel.com"),
    ("Bangaly CONDÉ", "bangaly.conde@orange-sonatel.com"),
]


# ======================================================================
#  Chargement initial (sans écraser l'existant)
# ======================================================================

def charger_defauts(db_path: Path | str | None = None) -> dict:
    """
    Installe les valeurs par défaut si elles sont absentes.

    `INSERT OR IGNORE` partout : le paramétrage du superviseur survit à
    chaque redémarrage du serveur et à chaque mise à jour du code.
    """
    conn = get_conn(db_path) if db_path else get_conn()
    bilan = {k: 0 for k in
             ("parametres", "types_message", "champs", "valeurs",
              "regles", "diffusion", "superviseurs")}
    try:
        with conn:
            for p in PARAMETRES_DEFAUT:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO parametres
                       (cle, valeur, type_valeur, categorie, libelle, aide, options, ordre)
                       VALUES (?,?,?,?,?,?,?,?)""", p)
                bilan["parametres"] += cur.rowcount

            for t in TYPES_MESSAGE_DEFAUT:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO types_message
                       (code, libelle, titre_avis, prefixe_sujet, inclut_reference,
                        salutation, mention_bas, canal_defaut, ordre)
                       VALUES (?,?,?,?,?,?,?,?,?)""", t)
                bilan["types_message"] += cur.rowcount

            for c in CHAMPS_DEFAUT:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO champs_message
                       (type_message, champ, libelle, obligatoire, ordre)
                       VALUES (?,?,?,?,?)""", c)
                bilan["champs"] += cur.rowcount

            for i, v in enumerate(VALEURS_DEFAUT):
                existe = conn.execute(
                    """SELECT 1 FROM valeurs_suggerees
                       WHERE liste=? AND valeur=? AND IFNULL(contexte,'')=IFNULL(?,'')""",
                    v).fetchone()
                if not existe:
                    conn.execute(
                        """INSERT INTO valeurs_suggerees (liste, valeur, contexte, ordre)
                           VALUES (?,?,?,?)""", (*v, i * 10))
                    bilan["valeurs"] += 1

            for r in REGLES_DESCRIPTION_DEFAUT:
                existe = conn.execute(
                    "SELECT 1 FROM regles_description WHERE motif_domaine = ?",
                    (r[0],)).fetchone()
                if not existe:
                    conn.execute(
                        """INSERT INTO regles_description
                           (motif_domaine, modele, priorite_regle) VALUES (?,?,?)""", r)
                    bilan["regles"] += 1

            for d in DIFFUSION_DEFAUT:
                existe = conn.execute(
                    "SELECT 1 FROM mailing_lists WHERE adresse = ? AND canal = ?",
                    (d[1], d[2])).fetchone()
                if not existe:
                    conn.execute(
                        """INSERT INTO mailing_lists
                           (libelle, adresse, canal, destination, type_message, groupe, ordre)
                           VALUES (?,?,?,?,?,?,?)""", d)
                    bilan["diffusion"] += 1

            for nom, email in SUPERVISEURS_DEFAUT:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO superviseurs (nom, email) VALUES (?,?)",
                    (nom, email))
                bilan["superviseurs"] += cur.rowcount
    finally:
        conn.close()
    return bilan


# ======================================================================
#  Lecture / écriture
# ======================================================================

def _convertir(valeur: str, type_valeur: str):
    if type_valeur == "booleen":
        return valeur in ("1", "true", "True", "oui")
    if type_valeur == "nombre":
        try:
            return float(valeur) if "." in valeur else int(valeur)
        except ValueError:
            return 0
    if type_valeur in ("liste", "json"):
        try:
            return json.loads(valeur)
        except (json.JSONDecodeError, TypeError):
            return valeur
    return valeur


def tous_parametres(db_path=None) -> dict:
    """Tous les paramètres, convertis dans leur type, indexés par clé."""
    conn = get_conn(db_path) if db_path else get_conn()
    try:
        return {
            r["cle"]: _convertir(r["valeur"], r["type_valeur"])
            for r in conn.execute("SELECT cle, valeur, type_valeur FROM parametres")
        }
    finally:
        conn.close()


def parametre(cle: str, defaut=None, db_path=None):
    """Lit un paramètre unique."""
    conn = get_conn(db_path) if db_path else get_conn()
    try:
        r = conn.execute(
            "SELECT valeur, type_valeur FROM parametres WHERE cle = ?", (cle,)
        ).fetchone()
        return _convertir(r["valeur"], r["type_valeur"]) if r else defaut
    finally:
        conn.close()


def definir_parametre(cle: str, valeur, db_path=None) -> bool:
    """Écrit un paramètre. Renvoie False si la clé n'est pas modifiable."""
    if isinstance(valeur, bool):
        valeur = "1" if valeur else "0"
    elif isinstance(valeur, (list, dict)):
        valeur = json.dumps(valeur, ensure_ascii=False)
    else:
        valeur = str(valeur)

    conn = get_conn(db_path) if db_path else get_conn()
    try:
        r = conn.execute(
            "SELECT modifiable FROM parametres WHERE cle = ?", (cle,)
        ).fetchone()
        if not r or not r["modifiable"]:
            return False
        with conn:
            conn.execute(
                "UPDATE parametres SET valeur = ?, updated_at = datetime('now') WHERE cle = ?",
                (valeur, cle))
        return True
    finally:
        conn.close()


def structure_messages(db_path=None) -> dict:
    """
    Reconstruit la structure des messages depuis la base.

    Remplace le dictionnaire STRUCTURE_MESSAGE qui était codé en dur : ajouter
    un type de message ou déplacer un champ se fait désormais en base.
    """
    conn = get_conn(db_path) if db_path else get_conn()
    try:
        out = {}
        for t in conn.execute(
            "SELECT * FROM types_message WHERE actif = 1 ORDER BY ordre"
        ):
            champs = conn.execute(
                """SELECT champ, libelle, obligatoire FROM champs_message
                   WHERE type_message = ? AND actif = 1 ORDER BY ordre""",
                (t["code"],)).fetchall()
            out[t["code"]] = {
                "libelle": t["libelle"],
                "titre": t["titre_avis"],
                "prefixe_sujet": t["prefixe_sujet"],
                "inclut_reference": bool(t["inclut_reference"]),
                "salutation": t["salutation"],
                "mention_bas": t["mention_bas"],
                "canal_defaut": t["canal_defaut"],
                "champs": [c["champ"] for c in champs],
                "libelles": {c["champ"]: c["libelle"] for c in champs},
                "obligatoires": [c["champ"] for c in champs if c["obligatoire"]],
            }
        return out
    finally:
        conn.close()


def valeurs_suggerees(db_path=None) -> dict:
    """Valeurs de saisie assistée, groupées par liste puis par contexte."""
    conn = get_conn(db_path) if db_path else get_conn()
    try:
        out: dict = {}
        for r in conn.execute(
            "SELECT liste, valeur, contexte FROM valeurs_suggerees WHERE actif = 1 ORDER BY liste, ordre"
        ):
            if r["contexte"]:
                out.setdefault(r["liste"], {}).setdefault(r["contexte"], []).append(r["valeur"])
            else:
                out.setdefault(r["liste"], [])
                if isinstance(out[r["liste"]], list):
                    out[r["liste"]].append(r["valeur"])
        return out
    finally:
        conn.close()


def description_auto(domaine: str, service: str, db_path=None) -> str:
    """Applique la première règle de description dont le motif correspond."""
    conn = get_conn(db_path) if db_path else get_conn()
    try:
        cible = (domaine or "").lower()
        for r in conn.execute(
            """SELECT motif_domaine, modele FROM regles_description
               WHERE actif = 1 ORDER BY priorite_regle DESC"""
        ):
            motif = (r["motif_domaine"] or "").lower()
            if not motif or motif in cible:
                return (r["modele"]
                        .replace("{domaine}", domaine or "")
                        .replace("{service}", service or ""))
        return service or ""
    finally:
        conn.close()
