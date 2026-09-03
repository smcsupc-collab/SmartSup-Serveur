"""
SMART-SUP — Sorties dérivées d'un incident
===========================================

Remplace l'outil autonome `Web_SMS_Sup_v2.2.html` (point bloquant B8 de
l'audit initial : fichier orphelin, non relié au serveur).

Cet outil reconstruisait les mêmes informations en analysant par expressions
régulières le texte d'un e-mail déjà généré ailleurs. Toute retouche d'un
libellé côté serveur cassait silencieusement l'extraction, sans erreur
visible — juste un champ vide dans la ligne Excel produite.

Ici, les trois sorties sont dérivées directement des données structurées de
l'incident. Il n'y a plus rien à analyser, donc plus rien à casser.

Gain secondaire : l'outil laissait les colonnes de durée vides (« à remplir »)
parce qu'il ne savait pas les calculer depuis du texte. Elles sont désormais
renseignées automatiquement.
"""

from __future__ import annotations

from datetime import datetime

from db.parametres import tous_parametres

# Ordre des colonnes du classeur de suivi, identique au module VBA
# Import_Incidents_OGN et à l'outil qu'on remplace.
COLONNES_LIGNE_SUIVI = [
    "N° ticket", "Priorité", "Origine", "Nom de service", "Début",
    "Fin rétablissement", "Fin réparation", "Durée rétablissement (hh:mn)",
    "Durée rétablissement (mn)", "Durée réparation (hh:mn)", "Description",
    "Cause de l'incident", "Actions correctives", "TMC", "Statut",
    "Observation", "SLA", "Exclusion", "RI", "Statut TQ",
]

# Formulations de repli, reprises telles quelles de l'outil d'origine pour ne
# pas modifier les habitudes de lecture des destinataires.
REPLIS = {
    "debut": {"cause": "Investigations en cours", "observation": "Services indisponibles"},
    "fin": {"cause": "Inconnue", "action": "Aucune", "observation": "Services disponibles"},
    "avancement": {"cause": "", "action": "", "observation": ""},
    "non_avere": {"cause": "", "observation": ""},
}


def _dt(valeur: str | None) -> datetime | None:
    if not valeur:
        return None
    txt = str(valeur).replace("T", " ").strip()
    for motif in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, motif)
        except ValueError:
            continue
    return None


def _fmt(valeur: str | None, format_sortie: str = "%d/%m/%Y %H:%M") -> str:
    d = _dt(valeur)
    return d.strftime(format_sortie) if d else (valeur or "")


def _duree(debut: str | None, fin: str | None) -> tuple[str, str]:
    """Renvoie (hh:mm, minutes) — vides si la durée n'est pas calculable."""
    d, f = _dt(debut), _dt(fin)
    if not d or not f or f < d:
        return "", ""
    minutes = int((f - d).total_seconds() // 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}", str(minutes)


def _valeur(donnees: dict, champ: str, type_message: str) -> str:
    """Valeur du champ, ou formulation de repli propre au type de message."""
    brut = (donnees.get(champ) or "").strip()
    return brut or REPLIS.get(type_message, {}).get(champ, "")


def construire_sms(donnees: dict, params: dict | None = None,
                   avec_services: bool = True) -> str:
    """Message SMS, au format attendu par WebSMS Pro."""
    params = params or tous_parametres()
    fmt = params.get("saisie.format_date", "%d/%m/%Y %H:%M")
    tm = donnees.get("type_message", "debut")

    prio = donnees.get("priorite") or "P1"
    svc = donnees.get("perimetre") or ""
    desc = (donnees.get("description") or "").replace("\n", " ").strip()
    debut = _fmt(donnees.get("date_debut"), fmt)
    fin = _fmt(donnees.get("date_fin"), fmt)
    cause = _valeur(donnees, "cause", tm)
    action = _valeur(donnees, "action", tm)
    obs = _valeur(donnees, "observation", tm)

    ligne_svc = f"\nServices impactés : {svc}" if avec_services and svc else ""

    if tm == "debut":
        return (f"Début d'incident : [{prio}][{svc}][{desc}]\n"
                f"HD : {debut}\nCause : {cause}{ligne_svc}\nObservation : {obs}")

    if tm in ("fin", "regularisation"):
        prefixe = "Régularisation — Fin d'incident" if tm == "regularisation" else "Fin d'incident"
        return (f"{prefixe} : [{prio}][{svc}][{desc}]\n"
                f"HD : {debut}\nHF : {fin}\nCause : {cause}\nAction : {action}"
                f"{ligne_svc}\nObservation : {obs}")

    if tm == "non_avere":
        return (f"Incident non avéré : [{prio}][{svc}][{desc}]\n"
                f"HD : {debut}\nCause : {cause}\nObservation : {obs}")

    # Point d'avancement et tout autre type ajouté en administration
    return (f"Update : [{prio}][{svc}][{desc}]\n"
            f"HD : {debut}" + (f"\nHF : {fin}" if fin else "") +
            f"\nCause : {cause}\nAction : {action}{ligne_svc}\nObservation : {obs}")


def construire_rapport_court(donnees: dict) -> str:
    """Bloc de synthèse « [Services] || TT » suivi des points clés."""
    tm = donnees.get("type_message", "debut")
    svc = donnees.get("perimetre") or ""
    ref = donnees.get("reference_externe") or ""

    entete = f"[{svc}] || {ref}" if svc or ref else "[]"
    parties = [entete, "", f"* Cause : {_valeur(donnees, 'cause', tm)}"]
    if tm != "non_avere":
        parties += ["", f"* Action : {_valeur(donnees, 'action', tm)}"]
    parties += ["", f"* Observation : {_valeur(donnees, 'observation', tm)}"]
    return "\n".join(parties)


def construire_ligne_suivi(donnees: dict, params: dict | None = None) -> dict:
    """
    Ligne tabulée, prête à coller dans le classeur de suivi.

    Contrairement à l'outil d'origine, les durées sont calculées : elles
    n'étaient pas déductibles d'un texte d'e-mail, elles le sont depuis les
    dates structurées.
    """
    params = params or tous_parametres()
    fmt = params.get("saisie.format_date", "%d/%m/%Y %H:%M")
    tm = donnees.get("type_message", "debut")

    debut = _fmt(donnees.get("date_debut"), fmt)
    fin = _fmt(donnees.get("date_fin"), fmt)
    duree_hhmm, duree_mn = _duree(donnees.get("date_debut"), donnees.get("date_fin"))

    statut = "Résolu" if donnees.get("date_fin") else "En cours"

    valeurs = [
        donnees.get("reference_externe") or "",
        donnees.get("priorite") or "P1",
        "Supervision",
        donnees.get("perimetre") or "",
        debut,
        fin,
        fin,                                   # fin réparation : même valeur par défaut
        duree_hhmm,                            # calculée (vide dans l'ancien outil)
        duree_mn,                              # calculée
        duree_hhmm,                            # durée réparation : même base par défaut
        (donnees.get("description") or "").replace("\n", " ").strip(),
        _valeur(donnees, "cause", tm),
        _valeur(donnees, "action", tm),
        donnees.get("tmc") or "",
        statut,
        _valeur(donnees, "observation", tm),
        "", "", "", "",                        # SLA / Exclusion / RI / Statut TQ : manuels
    ]

    return {
        "colonnes": COLONNES_LIGNE_SUIVI,
        "valeurs": valeurs,
        "ligne": "\t".join(valeurs),           # collage direct dans Excel
    }


def toutes_sorties(donnees: dict, avec_services: bool = True) -> dict:
    """Les trois sorties d'un coup, pour un seul aller-retour avec le serveur."""
    params = tous_parametres()
    ligne = construire_ligne_suivi(donnees, params)
    sms = construire_sms(donnees, params, avec_services)
    return {
        "sms": sms,
        "sms_longueur": len(sms),
        "sms_max": int(params.get("canal.sms.longueur_max", 320) or 320),
        "rapport_court": construire_rapport_court(donnees),
        "ligne_suivi": ligne["ligne"],
        "ligne_colonnes": ligne["colonnes"],
        "ligne_valeurs": ligne["valeurs"],
    }
