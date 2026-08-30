"""
Backend Flask — Outil de Communication Incidents / Orange Guinée
Routes :
  GET  /                           → interface principale
  GET  /api/services               → liste des services (autocomplétion)
  GET  /api/service/<nom>          → détails d'un service
  POST /api/send-mail              → envoie le mail via Outlook (win32com)
  POST /api/open-in-outlook        → ouvre dans Outlook pour révision
  POST /api/copy-sms               → copie le SMS dans le presse-papiers
  POST /api/preview                → retourne HTML + SMS pour preview live
  GET  /api/config                 → lecture config
  POST /api/config                 → sauvegarde config
  POST /api/reload-catalog         → recharge le catalogue Excel
  GET  /api/stats                  → KPIs du catalogue (XXL #4)
  POST /api/log-sent               → journal des incidents envoyés (XXL #1)
  GET  /api/sent-log               → lecture du journal (XXL #1)
"""

import html as _html
import json
import os
import re
import sys
import tempfile
import threading
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pyperclip
from flask import Flask, jsonify, render_template, request

from data_loader import build_service_catalog

# ── SmartSup v4 — DB + API ────────────────────────────────────
from db.schema import init_db, _seed_defaults, migrate_sent_log, DB_PATH
from db.api    import api_v4
from db.tmc    import send_tmc_notification

# ── Module v5 : documentation / communication / reporting ─────────────────────
# Cohabite avec le module v4 pendant la migration (« améliorer sans casser ») :
# le socle v4 continue de fonctionner tant que la bascule n'est pas validée.
from db.schema_v5 import init_db as init_db_v5, DB_PATH as DB_PATH_V5
from db.api_v5    import api_v5
from db.api_admin import api_admin

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
EXAMPLE_PATH = BASE_DIR / "config.example.json"
LOG_PATH    = BASE_DIR / "sent_log.jsonl"

_DEFAULT_CONFIG = {
    "signature": {
        "nom": "Prénom NOM",
        "fonction": "Ingénieur Supervision",
        "entite": "Orange Guinée — NOC",
        "telephone": "+224 6XX XX XX XX"
    },
    "recipients_to": [],
    "recipients_cc": [],
    "recipients_notif": [],
    "recipients_notif_cc": [],
    "excel_skip_sheets": [
        "Plan d'action", "Suivi Perfomances", "Objectifs_2022",
        "Synthese_2018", "objectifs_Semestre_2_2018"
    ],
    "templates": []
}

def _load_config() -> dict:
    """Charge config.json ; si absent, crée depuis example ou depuis le défaut."""
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if EXAMPLE_PATH.exists():
        cfg = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return cfg
    CONFIG_PATH.write_text(json.dumps(_DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
    return dict(_DEFAULT_CONFIG)

CONFIG = _load_config()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # 4 MB (pièces jointes)

# ── Init base de données v4 ───────────────────────────────────
init_db()
_seed_defaults()
app.register_blueprint(api_v4)

# ── Init base v5 ──────────────────────────────────────────────────────────────
init_db_v5()
app.register_blueprint(api_v5)
app.register_blueprint(api_admin)

# Paramétrage : installe les valeurs par défaut manquantes sans jamais
# écraser celles que le superviseur a modifiées.
try:
    from db.parametres import charger_defauts
    _bilan_param = charger_defauts(DB_PATH_V5)
    _nb = sum(_bilan_param.values())
    if _nb:
        print(f"[v5] paramétrage : {_nb} valeur(s) par défaut installée(s)")
except Exception as _e:
    print(f"[v5] paramétrage non chargé : {_e}")

# Le catalogue de supervision alimente l'auto-complétion de la saisie rapide.
# Import silencieux : son absence ne doit pas empêcher le serveur de démarrer.
try:
    from db.catalogue import importer_catalogue, creer_equipes_depuis_domaines
    _cat_xlsx = BASE_DIR / "data" / "Catalogue_Services_SupervisionV4.xlsx"
    if _cat_xlsx.exists():
        _bilan = importer_catalogue(_cat_xlsx, DB_PATH_V5)
        creer_equipes_depuis_domaines(DB_PATH_V5)
        if _bilan["services_crees"]:
            print(f"[v5] catalogue : {_bilan['services_crees']} service(s) importé(s)")
except Exception as _e:
    print(f"[v5] catalogue non chargé : {_e}")

# Migration historique sent_log.jsonl → ticket_comms
_migrated = migrate_sent_log(BASE_DIR / "sent_log.jsonl")
if _migrated:
    print(f"[v4] {_migrated} entrées migrées depuis sent_log.jsonl")

# ── Restriction réseau local uniquement ───────────────────────────────────────
@app.before_request
def _local_only():
    """Refuse les requêtes non-locales sur les routes API (sécurité réseau)."""
    if request.path.startswith("/api/"):
        remote = request.remote_addr
        if remote not in ("127.0.0.1", "::1", "localhost"):
            return jsonify({"error": "Accès refusé — interface locale uniquement"}), 403

# ── Catalogue (thread-safe) ───────────────────────────────────────────────────
_CATALOG: dict | None = None
_CATALOG_LOCK = threading.Lock()

def catalog() -> dict:
    global _CATALOG
    with _CATALOG_LOCK:
        if _CATALOG is None:
            _CATALOG = build_service_catalog(
                skip_sheets=set(CONFIG.get("excel_skip_sheets", []))
            )
        return _CATALOG

# ── Helpers HTML mail ─────────────────────────────────────────────────────────
_LABEL_BG   = "#CCCCCC"
_LABEL_TEXT = "#333333"
_YELLOW     = "#FFC107"
_RED        = "#F44336"
_GREEN      = "#4CAF50"
_AMBER      = "#FF9800"
_WHITE      = "#FFFFFF"
_TEXT_WHITE = "#FFFFFF"
_TEXT_DARK  = "#212121"
_FONT       = "'Times New Roman', Times, serif"


def _row(label: str, value: str, bg: str = _WHITE, text_color: str = _TEXT_DARK) -> str:
    safe = _html.escape(str(value))
    return (
        f'<tr>'
        f'<td width="180" style="padding:8px 14px;border:1px solid #000000;font-weight:bold;'
        f'font-family:{_FONT};font-size:13px;'
        f'background-color:{_LABEL_BG};color:{_LABEL_TEXT};white-space:nowrap;">{label}</td>'
        f'<td style="padding:8px 14px;border:1px solid #000000;text-align:center;'
        f'font-family:{_FONT};font-size:13px;'
        f'background-color:{bg};color:{text_color};">{safe}</td>'
        f'</tr>'
    )


def _title_table(title: str) -> str:
    return (
        '<table border="1" cellpadding="0" cellspacing="0" width="600" '
        f'style="border-collapse:collapse;font-family:{_FONT};font-size:13px;margin-bottom:12px;">'
        f'<tr><td style="padding:14px 16px;border:1px solid #000000;'
        f'text-align:center;font-weight:bold;font-family:{_FONT};font-size:16px;'
        f'background-color:{_LABEL_BG};color:{_LABEL_TEXT};letter-spacing:2px;">'
        f'{title.upper()}'
        f'</td></tr></table>'
    )


def _sig_html() -> str:
    sig = CONFIG["signature"]
    return (
        "<br><br>"
        f'<p style="font-family:{_FONT};font-size:13px;color:#444444;margin:0;">'
        f'Cordialement,<br>'
        f'<strong>{_html.escape(sig["nom"])}</strong><br>'
        f'{_html.escape(sig["fonction"])}<br>'
        f'{_html.escape(sig["entite"])}<br>'
        f'Tél&nbsp;: {_html.escape(sig["telephone"])}'
        f'</p>'
    )

#---------------- MOODER

_FONT = "Cambria, 'Times New Roman', Times, serif"
_RED = "#E05252"
_AMBER = "#F2A93B"
_GREEN = "#1E8449"
_YELLOW = "#F2C94C"
_TEXT_DARK = "#000000"
_LABEL_BG = "#D9D9D9"
_BORDER = "1px solid #000000"
 
 
def _row(label, value, bg=None, text_color=None):
    bg = bg or "#FFFFFF"
    color = text_color or _TEXT_DARK
    return (
        f'<tr>'
        f'<td style="background-color:{_LABEL_BG};font-weight:bold;padding:14px 16px;'
        f'width:180px;text-align:left;vertical-align:middle;border:{_BORDER};">{label}</td>'
        f'<td style="background-color:{bg};color:{color};font-weight:bold;padding:14px 16px;'
        f'text-align:center;vertical-align:middle;border:{_BORDER};">{value}</td>'
        f'</tr>'
    )
 
 
def _title_row(title_text, colspan=2):
    """Remplace l'ancienne _title_table() : maintenant une <tr> du MEME tableau,
    plus un <table> a part."""
    return (
        f'<tr><td colspan="{colspan}" style="background-color:{_LABEL_BG};'
        f'font-weight:bold;font-size:18px;text-align:center;padding:16px;'
        f'border:{_BORDER};">{title_text.upper()}</td></tr>'
    )
 
 
def _spacer_row(colspan=2, height=22):
    """La ligne fantome : aucune bordure -> cree l'espace blanc visible,
    sans etre un deuxieme tableau."""
    return (
        f'<tr><td colspan="{colspan}" style="border:none;padding:0;'
        f'height:{height}px;line-height:{height}px;font-size:1px;">&nbsp;</td></tr>'
    )
 
 
def _sig_html():
    return (
        f'<br><p style="font-family:{_FONT};font-size:13px;color:#333333;">'
        f'Cordialement,<br>L&#39;équipe GNOC</p>'
    )
 
 
def build_html_body(data: dict) -> str:
    t = data["type"]
    is_fin        = (t == "fin")
    is_avancement = (t == "avancement")
    is_non_avere  = (t == "non_avere")
 
    if is_fin:
        title_text          = "Avis de fin d'incident"
        obs_bg, obs_default = _GREEN, "Service Disponible"
    elif is_avancement:
        title_text          = "Point d'avancement"
        obs_bg, obs_default = _AMBER, "Service disponible / Nous continuons à observer"
    elif is_non_avere:
        title_text          = "Incident non avéré"
        obs_bg, obs_default = _GREEN, "Services disponibles"
    else:
        title_text          = "Avis de début d'incident"
        obs_bg, obs_default = _RED, "Service Indisponible"
 
    rows = [_row("Description", data["description"])]
    rows.append(_row("Début", data["hd"]))
    if is_fin:
        rows.append(_row("Fin", data["hf"]))
    rows.append(_row("TT &amp; priorité", f'{data["ticket"]}/{data["priority"]}'))
    rows.append(_row("Cause", data["cause"], bg=_YELLOW, text_color=_TEXT_DARK))
    if is_fin:
        rows.append(_row("Action", data["action"], bg=_YELLOW, text_color=_TEXT_DARK))
    rows.append(_row("Service impacté", data["service"]))
    rows.append(_row("Observation", data.get("observation") or obs_default,
                     bg=obs_bg, text_color=_TEXT_DARK))
 
    # --- LE FIX ---
    # Avant : _title_table(title_text) + table_html  -> 2 <table> distincts
    # Maintenant : tout dans le MEME <table>, titre + spacer + donnees en <tr>
    all_rows = [_title_row(title_text), _spacer_row()] + rows
    table_html = (
        '<table cellpadding="0" cellspacing="0" width="650" '
        f'style="border-collapse:separate;border-spacing:0;font-family:{_FONT};font-size:14px;">'
        + "".join(all_rows) + "</table>"
    )
    return (
        f'<html><body style="font-family:{_FONT};">'
        + table_html + _sig_html()
        + '</body></html>'
    )
#-------------------- ------------------------------------------------------------MOODER

def build_subject(data: dict) -> str:
    t = data["type"]
    labels = {
        "fin": "Avis de fin d'incident",
        "avancement": "Point d'avancement",
        "non_avere": "Incident non avéré"
    }
    label = labels.get(t, "Avis de début d'incident")
    return f'{label} [{data["service"]}] || {data["ticket"]}'


# ── Helpers RAN/NBN ───────────────────────────────────────────────────────────
def _obs_default_ran_nbn(t: str, sub: str, kind: str) -> str:
    if t == "avancement":
        return ""
    if t in ("fin", "non_avere"):
        if sub == "ran":
            return "Site Stable" if kind == "instabilite" else "Sites Up"
        return "Lien Up"
    if sub == "ran":
        return "Site Instable" if kind == "instabilite" else "Sites Down"
    return "Lien Down"


def build_html_body_ran_nbn(data: dict) -> str:
    t      = data["type"]
    is_fin = (t == "fin")
    sub    = data.get("sub_type", "nbn")
    kind   = data.get("incident_kind", "coupure")

    if is_fin:
        title_text = "Avis de fin d'incident"; obs_bg = _GREEN
    elif t == "avancement":
        title_text = "Point d'avancement";     obs_bg = _AMBER
    elif t == "non_avere":
        title_text = "Incident non avéré";     obs_bg = _GREEN
    else:
        title_text = "Avis de début d'incident"; obs_bg = _RED

    obs_default = _obs_default_ran_nbn(t, sub, kind)

    rows = [_row("Description", data["description"])]
    rows.append(_row("Début", data["hd"]))
    if is_fin:
        rows.append(_row("Fin", data["hf"]))
    rows.append(_row("TT &amp; priorité", f'{data["ticket"]}/{data["priority"]}'))
    rows.append(_row("Cause", data["cause"], bg=_YELLOW, text_color=_TEXT_DARK))
    if is_fin:
        rows.append(_row("Action", data["action"], bg=_YELLOW, text_color=_TEXT_DARK))
    if sub == "nbn":
        rows.append(_row("Lien Impacté", data.get("lien_impacte", "")))
    else:
        if data.get("services"):
            rows.append(_row("Services impactés", data["services"]))
    rows.append(_row("Observation", data.get("observation") or obs_default,
                     bg=obs_bg, text_color=_TEXT_DARK))

    table_html = (
        '<table border="1" cellpadding="0" cellspacing="0" width="600" '
        f'style="border-collapse:collapse;font-family:{_FONT};font-size:13px;">'
        + "".join(rows) + "</table>"
    )
    return (
        f'<html><body style="font-family:{_FONT};">'
        + _title_table(title_text) + table_html + _sig_html()
        + '</body></html>'
    )


def build_subject_ran_nbn(data: dict) -> str:
    t      = data["type"]
    lien   = data.get("lien_impacte", "")
    ticket = data.get("ticket", "")
    sub    = data.get("sub_type", "nbn")
    kind   = data.get("incident_kind", "coupure")

    labels = {"fin": "Avis de fin d'incident", "avancement": "Point d'avancement",
              "non_avere": "Incident non avéré"}
    type_label = labels.get(t, "Avis de début d'incident")

    if sub == "ran":
        kind_label = "Instabilité du site" if kind == "instabilite" else "Coupure de site"
        return f'{type_label} [{kind_label} {lien}] || {ticket}'
    return f'{type_label} [NBN {lien}] || {ticket}'


_RATTACHES_RE = re.compile(r"\s*\+\s*\d+\s*sites?\s+rattach[ée]s?\s*$", re.IGNORECASE)

def _site_id_only(lien: str) -> str:
    return _RATTACHES_RE.sub("", lien).strip()

def _nbn_links_label(lien: str) -> str:
    liens = [l.strip() for l in lien.split(",") if l.strip()]
    return ", ".join(f"NBN {l}" for l in liens)

def _join_services_fr(services: str) -> str:
    items = [s.strip() for s in services.split("/") if s.strip()]
    if not items: return ""
    if len(items) == 1: return items[0]
    return ", ".join(items[:-1]) + " et " + items[-1]


def build_sms_text_ran_nbn(data: dict) -> str:
    t      = data["type"]
    lien   = data.get("lien_impacte", "")
    sub    = data.get("sub_type", "nbn")
    kind   = data.get("incident_kind", "coupure")
    is_fin = (t == "fin")

    _TYPE_LABELS = {
        "fin": "Fin d'incident", "avancement": "Point d'avancement",
        "non_avere": "Incident non avéré",
    }
    type_label = _TYPE_LABELS.get(t, "Début d'incident")
    bracket = _site_id_only(lien) if sub == "ran" else _nbn_links_label(lien)

    desc = data.get("description", "")
    lines = [f"{type_label} : [{data.get('priority','')}][{bracket}][{desc}]"]
    lines.append(f"HD : {data.get('hd','')}")
    if is_fin and data.get("hf"):
        lines.append(f"HF : {data.get('hf','')}")
    lines.append(f"Cause : {data.get('cause','')}")
    if is_fin and data.get("action"):
        lines.append(f"Action : {data.get('action','')}")
    obs_default = _obs_default_ran_nbn(t, sub, kind)
    lines.append(f"Observation : {data.get('observation') or obs_default}")
    return "\n".join(lines)


def build_whatsapp_text_ran_nbn(data: dict) -> str:
    t      = data["type"]
    sub    = data.get("sub_type", "nbn")
    zone   = data.get("zone_impactee", "").strip()
    zone_label = f"*{zone}*" if zone else "(zone impactée non précisée)"
    services_label = _join_services_fr(data.get("services", ""))

    if sub == "ran":
        kind = data.get("incident_kind", "coupure")
        site_label = f"*{data.get('lien_impacte', '')}*"
        cause = data.get("cause", "").strip()
        cause_clause = f" due à {cause}" if cause else ""
        incident_word = "Instabilité" if kind == "instabilite" else "Coupure"

        if t == "fin":
            return (
                f"Bonjour à tous,\n\n"
                f"Nous enregistrons le rétablissement du site {site_label}{cause_clause}.\n\n"
                f"Cet incident avait entraîné une dégradation des services {services_label} "
                f"dans la zone de {zone_label}.\n\n"
                f"Nous vous tiendrons informés de l'évolution de la situation.\n"
                f"Merci pour votre compréhension."
            )
        if t == "debut":
            return (
                f"Bonjour à tous,\n\n"
                f"Nous enregistrons une {incident_word} du site {site_label}\n\n"
                f"Cet incident entraîne une dégradation des services {services_label} "
                f"dans la zone de {zone_label}.\n\n"
                f"Les équipes techniques sont actuellement mobilisées et à pied d'œuvre pour "
                f"identifier la cause et rétablir le service dans les meilleurs délais.\n\n"
                f"Nous vous tiendrons informés de l'évolution de la situation.\n"
                f"Merci pour votre compréhension."
            )
        return ""

    # NBN
    kind      = data.get("nbn_kind", "coupure")
    lien      = data.get("lien_impacte", "")
    nb_liens  = len([l for l in lien.split(",") if l.strip()])
    liens_label = f"*{_nbn_links_label(lien)}*"

    if t == "fin":
        liaison_word = "liaisons" if nb_liens > 1 else "liaison"
        verbe = "le rétablissement du débit de" if kind == "baisse_debit" else "le rétablissement de"
        return (
            f"Bonjour à tous,\n\n"
            f"Nous enregistrons {verbe} la {liaison_word} {liens_label} .\n"
            f"Nous restons en observation et vous tiendrons informés de toute évolution.\n\n"
            f"Merci pour votre compréhension."
        )
    if t == "debut":
        lien_word = "liens" if nb_liens > 1 else "lien"
        if kind == "baisse_debit":
            action = "une baisse de débit des" if nb_liens > 1 else "une baisse de débit du"
        else:
            action = "la coupure des" if nb_liens > 1 else "la coupure du"
        return (
            f"Bonjour à tous.\n\n"
            f"Nous enregistrons {action} {lien_word} {liens_label} .\n\n"
            f"Cet incident entraîne une dégradation de la {services_label} "
            f"dans la zone de {zone_label}\n\n"
            f"Les différentes équipes techniques sont actuellement mobilisées et à pied d'œuvre "
            f"afin de corriger l'incident dans les meilleurs délais.\n"
            f"Nous restons en observation et vous tiendrons informés de toute évolution.\n\n"
            f"Merci pour votre compréhension."
        )
    return ""


# ── Helpers Notification ───────────────────────────────────────────────────────
_SALMON = "#E57373"

def build_html_body_notification(data: dict) -> str:
    t      = data["type"]
    is_fin = (t == "fin")

    if is_fin:
        title_text = "Avis de fin d'incident";  obs_bg, obs_default = _GREEN, "Site Stable"
    elif t == "avancement":
        title_text = "Point d'avancement";       obs_bg, obs_default = _AMBER, "Site Instable / En cours d'observation"
    elif t == "non_avere":
        title_text = "Incident non avéré";       obs_bg, obs_default = _GREEN, "Fausse Alerte"
    else:
        title_text = "Avis de début d'incident"; obs_bg, obs_default = _SALMON, "Site Instable"

    rows = [
        _row("Description",   data["description"]),
        _row("Cause",         data["cause"]),
        _row("Zone impactée", data.get("zone", "")),
        _row("TMC",           data.get("tmc_notif", "")),
        _row("Observation",   data.get("observation") or obs_default,
             bg=obs_bg, text_color=_TEXT_DARK),
    ]
    table_html = (
        '<table border="1" cellpadding="0" cellspacing="0" width="600" '
        f'style="border-collapse:collapse;font-family:{_FONT};font-size:13px;">'
        + "".join(rows) + "</table>"
    )
    sig = CONFIG["signature"]
    sig_html = (
        "<br><br>"
        f'<p style="font-family:{_FONT};font-size:13px;color:#444444;margin:0;">'
        f'Copie ATPT<br><br>Cordialement,<br>'
        f'<strong>{_html.escape(sig["nom"])}</strong><br>'
        f'{_html.escape(sig["fonction"])}<br>{_html.escape(sig["entite"])}<br>'
        f'Tél&nbsp;: {_html.escape(sig["telephone"])}</p>'
    )
    return f'<html><body style="font-family:{_FONT};">' + _title_table(title_text) + table_html + sig_html + '</body></html>'


def build_subject_notification(data: dict) -> str:
    t, zone = data["type"], data.get("zone", "")
    labels = {"fin": "Avis de fin d'incident", "avancement": "Point d'avancement",
              "non_avere": "Incident non avéré"}
    label = labels.get(t, "Avis de début d'incident")
    return f'{label} — {zone}' if zone else label


def build_sms_text_notification(data: dict) -> str:
    t, zone = data["type"], data.get("zone", "")
    lines = []
    if t == "avancement":   lines.append(f'Update : {zone}')
    elif t == "fin":        lines.append(f"Fin d'incident : {zone}")
    elif t == "non_avere":  lines.append(f'Incident non avéré : {zone}')
    else:                   lines.append(f"Début d'incident : {zone}")
    lines.extend([
        data["description"],
        f'Cause : {data["cause"]}',
        f'Zone impactée : {zone}',
        f'TMC : {data.get("tmc_notif", "")}',
        f'Observation : {data.get("observation") or ("Site Stable" if t == "fin" else "Site Instable")}',
    ])
    return "\n".join(lines)


# ── Helpers SMS Services ───────────────────────────────────────────────────────
def build_sms_text(data: dict) -> str:
    t      = data["type"]
    is_fin = (t == "fin")
    lines  = []

    if t == "avancement":
        lines.append(f'Update : [{data["priority"]}][{data["service"]}]')
    elif is_fin:
        lines.append(f'Fin d\'incident : [{data["priority"]}][{data["service"]}]')
    elif t == "non_avere":
        lines.append(f'Incident non avéré : [{data["priority"]}][{data["service"]}]')
    else:
        lines.append(f'Début d\'incident : [{data["priority"]}][{data["service"]}]')

    lines.append(data["description"])
    lines.append(f'HD : {data["hd"]}')
    if is_fin:
        lines.append(f'HF : {data["hf"]}')
    lines.append(f'Cause : {data["cause"]}')
    if is_fin:
        lines.append(f'Action : {data["action"]}')

    if t == "avancement":
        obs_default = "Service disponible / Nous continuons à observer"
    elif is_fin:
        obs_default = "Service disponible"
    else:
        obs_default = "Services indisponibles"

    lines.append(f'Observation : {data.get("observation") or obs_default}')
    return "\n".join(lines)




# ── WhatsApp Services (XXL #2) ──────────────────────────────────────────────
def build_whatsapp_text_services(data: dict) -> str:
    """
    Message WhatsApp pour incidents de type Services.
    Format narratif : Bonjour → constat → impact → actions → suivi → remerciement.
    """
    t       = data.get("type", "debut")
    service = data.get("service", "")
    cause   = data.get("cause", "").strip()
    action  = data.get("action", "").strip()
    obs     = data.get("observation", "").strip()

    cause_clause  = f" suite à {cause}" if cause  else ""
    action_clause = f"\n\nAction corrective : {action}" if action else ""

    if t == "debut":
        obs_default = "Services Indisponibles"
        return (
            f"Bonjour à tous,\n\n"
            f"Nous enregistrons une perturbation sur le service *{service}*{cause_clause}.\n\n"
            f"Nos équipes techniques sont mobilisées et travaillent activement "
            f"pour identifier la cause et rétablir le service dans les meilleurs délais.\n\n"
            f"Observation : {obs or obs_default}\n\n"
            f"Nous vous tiendrons informés de l'évolution.\n"
            f"Merci pour votre compréhension."
        )
    if t == "avancement":
        return (
            f"Bonjour à tous,\n\n"
            f"Point d'avancement — service *{service}*.\n\n"
            f"Nos équipes techniques poursuivent les investigations.{action_clause}\n\n"
            f"Observation : {obs or 'En cours d\'investigation'}\n\n"
            f"Nous restons mobilisés et vous tiendrons informés.\n"
            f"Merci pour votre compréhension."
        )
    if t == "fin":
        obs_default = "Service Disponible"
        return (
            f"Bonjour à tous,\n\n"
            f"Nous avons le plaisir de vous informer du rétablissement du service *{service}*{cause_clause}.{action_clause}\n\n"
            f"Observation : {obs or obs_default}\n\n"
            f"Nous restons en observation et vous tiendrons informés de toute évolution.\n"
            f"Merci pour votre compréhension et votre patience."
        )
    if t == "non_avere":
        return (
            f"Bonjour à tous,\n\n"
            f"Suite à nos investigations, l'incident signalé sur le service *{service}* "
            f"s'avère non avéré. Les services sont disponibles.\n\n"
            f"Observation : {obs or 'Services Disponibles'}\n\n"
            f"Merci pour votre vigilance."
        )
    return ""

# ── Dispatch ──────────────────────────────────────────────────────────────────
def _dispatch(data: dict):
    mode = data.get("mode", "services")
    if mode == "ran_nbn":
        return build_subject_ran_nbn, build_html_body_ran_nbn, build_sms_text_ran_nbn
    if mode == "notification":
        return build_subject_notification, build_html_body_notification, build_sms_text_notification
    return build_subject, build_html_body, build_sms_text


def _validate_incident(data: dict) -> str | None:
    mode = data.get("mode", "services")
    if mode == "notification":
        missing = [f for f in ("type", "description", "cause") if not data.get(f)]
    elif mode == "ran_nbn":
        missing = [f for f in ("type", "ticket", "hd", "description",
                                "cause", "priority", "lien_impacte") if not data.get(f)]
    else:
        missing = [f for f in ("type", "service", "ticket", "hd", "description",
                                "cause", "priority") if not data.get(f)]
    if missing:
        return f"Champs manquants : {', '.join(missing)}"
    if data.get("type") not in ("debut", "fin", "avancement", "non_avere"):
        return "Type d'avis invalide (debut | fin | avancement | non_avere)"
    if mode != "notification" and data["type"] == "fin" and not data.get("hf"):
        return "Heure de fin (HF) requise pour un Avis de Fin"
    return None


# ── Payload dérivés ───────────────────────────────────────────────────────────
def _ran_nbn_to_notif(data: dict) -> dict:
    sub  = data.get("sub_type", "nbn")
    t    = data.get("type", "debut")
    kind = data.get("incident_kind", "coupure")
    notif = {
        "mode":        "notification",
        "type":        t,
        "description": data.get("description", ""),
        "cause":       "Investigation en cours",
        "zone":        data.get("zone_impactee", ""),
        "tmc_notif":   "Orange",
        "observation": data.get("observation") or _obs_default_ran_nbn(t, sub, kind),
    }
    if data.get("custom_notif_html_body"):
        notif["custom_html_body"] = data["custom_notif_html_body"]
    if data.get("custom_notif_subject"):
        notif["custom_subject"] = data["custom_notif_subject"]
    return notif


def _services_to_notif(data: dict) -> dict:
    t = data.get("type", "debut")
    obs_defaults = {"fin": "Site Stable", "non_avere": "Fausse Alerte",
                    "avancement": "Site Instable / En cours d'observation"}
    obs_default = obs_defaults.get(t, "Site Instable")
    notif = {
        "mode":        "notification",
        "type":        t,
        "description": data.get("description", ""),
        "cause":       data.get("cause", "Investigation en cours"),
        "zone":        data.get("notif_zone", ""),
        "tmc_notif":   data.get("tmc", "Orange"),
        "observation": data.get("notif_observation") or data.get("observation") or obs_default,
    }
    if data.get("custom_notif_html_body"):
        notif["custom_html_body"] = data["custom_notif_html_body"]
    if data.get("custom_notif_subject"):
        notif["custom_subject"] = data["custom_notif_subject"]
    return notif


# ── Email helpers ─────────────────────────────────────────────────────────────
def _open_cross_platform(path: str):
    """Ouvre un fichier avec l'application par défaut (Windows, macOS, Linux)."""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        import subprocess
        subprocess.run(["open", path], check=False)
    else:
        import subprocess
        subprocess.run(["xdg-open", path], check=False)


def _open_as_eml(data: dict) -> str:
    fn_subject, fn_html, _ = _dispatch(data)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = fn_subject(data)
    msg["To"]      = "; ".join(a.strip() for a in CONFIG.get("recipients_to", []) if a.strip())
    cc_list        = [a.strip() for a in CONFIG.get("recipients_cc", []) if a.strip()]
    if cc_list:
        msg["Cc"] = "; ".join(cc_list)
    msg.attach(MIMEText(fn_html(data), "html", "utf-8"))

    tmp = tempfile.NamedTemporaryFile(
        mode="wb", suffix=".eml", prefix="smartsup_", delete=False
    )
    tmp.write(msg.as_bytes())
    tmp.close()
    _open_cross_platform(tmp.name)
    # Nettoyage différé : 30s après l'ouverture (le client mail a eu le temps de lire)
    def _cleanup(p):
        time.sleep(30)
        try:
            os.unlink(p)
        except OSError:
            pass
    threading.Thread(target=_cleanup, args=(tmp.name,), daemon=True).start()
    return tmp.name


def _build_outlook_mail(data: dict, display: bool = False) -> dict:
    fn_subject, fn_html, _ = _dispatch(data)
    subject   = data.get("custom_subject")   or fn_subject(data)
    html_body = data.get("custom_html_body") or fn_html(data)

    try:
        import win32com.client as win32
        outlook = win32.Dispatch("Outlook.Application")
        mail    = outlook.CreateItem(0)
        mail.Subject  = subject
        mail.HTMLBody = html_body
        for addr in CONFIG.get("recipients_to", []):
            if addr.strip():
                mail.Recipients.Add(addr.strip()).Type = 1
        for addr in CONFIG.get("recipients_cc", []):
            if addr.strip():
                r = mail.Recipients.Add(addr.strip())
                r.Type = 2
        mail.Recipients.ResolveAll()
        if display:
            mail.Display()
        else:
            mail.Send()
        return {"method": "outlook", "subject": subject}
    except Exception as com_err:
        try:
            eml_path = _open_as_eml(data)
            return {"method": "eml", "subject": subject, "file": eml_path}
        except Exception as eml_err:
            raise RuntimeError(
                f"Outlook COM : {com_err} | Fallback EML : {eml_err}"
            ) from eml_err




# ── Templates sauvegardables (XXL #5) ────────────────────────────────────────
TEMPLATES_PATH = BASE_DIR / "templates_data.json"

def _load_templates() -> list:
    if TEMPLATES_PATH.exists():
        try:
            return json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def _save_templates(templates: list):
    tmp = TEMPLATES_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(templates, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(TEMPLATES_PATH)


@app.get("/api/templates")
def api_get_templates():
    return jsonify({"templates": _load_templates()})


@app.post("/api/templates")
def api_save_template():
    """Sauvegarde un nouveau template ou met à jour par id."""
    tpl = request.get_json(force=True)
    if not tpl.get("name") or not tpl.get("payload"):
        return jsonify({"error": "name et payload sont requis"}), 400
    templates = _load_templates()
    # Mettre à jour si même nom
    existing = next((i for i, t in enumerate(templates) if t.get("name") == tpl["name"]), None)
    entry = {
        "id":      tpl.get("id") or str(int(datetime.now().timestamp() * 1000)),
        "name":    tpl["name"],
        "mode":    tpl.get("mode", "services"),
        "payload": tpl["payload"],
        "created": tpl.get("created") or datetime.now().isoformat(timespec="seconds"),
        "updated": datetime.now().isoformat(timespec="seconds"),
    }
    if existing is not None:
        templates[existing] = entry
    else:
        templates.append(entry)
    _save_templates(templates)
    return jsonify({"status": "ok", "template": entry})


@app.delete("/api/templates/<template_id>")
def api_delete_template(template_id: str):
    templates = _load_templates()
    templates = [t for t in templates if t.get("id") != template_id]
    _save_templates(templates)
    return jsonify({"status": "ok"})

# ── Journal des incidents envoyés (XXL #1) ────────────────────────────────────
def _log_sent(data: dict, method: str, subject: str):
    """Ajoute une entrée dans sent_log.jsonl."""
    try:
        entry = {
            "ts":       datetime.now().isoformat(timespec="seconds"),
            "method":   method,
            "mode":     data.get("mode", "services"),
            "type":     data.get("type", ""),
            "service":  data.get("service") or data.get("lien_impacte", ""),
            "ticket":   data.get("ticket", ""),
            "subject":  subject,
        }
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # Le journal n'est pas critique




# ── Routes TMC — Signalisation back-office (J4) ───────────────────────────────
@app.post("/api/tmc/signaler")
def api_tmc_signaler():
    """
    Envoie la notification au TMC pour un ticket donné.
    Body JSON :
      numero               : numéro du ticket (requis)
      statut_type          : debut | fin | avancement (défaut: debut)
      destinataires        : [liste d'adresses override, optionnel]
      display_only         : bool (défaut: True = ouvrir Outlook)
      preuve_url           : URL à inclure (optionnel)
    """
    d = request.get_json(force=True)
    if not d.get("numero"):
        return jsonify({"error": "numero requis"}), 400

    # Charger le ticket complet
    from db.schema import get_conn as _gc
    conn = _gc()
    row = conn.execute("""
        SELECT t.*,
               ti.libelle_fr, ti.libelle_en, ti.langue as type_langue,
               e.nom as equipe_nom, e.email_list,
               s.nom as sup_nom, s.prenom as sup_prenom
        FROM tickets t
        LEFT JOIN types_incident ti ON ti.id=t.type_incident_id
        LEFT JOIN equipes_tmc e    ON e.id=t.equipe_tmc_id
        LEFT JOIN superviseurs s   ON s.id=t.superviseur_id
        WHERE t.numero=?
    """, (d["numero"],)).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"Ticket {d['numero']} non trouvé"}), 404

    ticket = dict(row)
    if d.get("preuve_url"):
        ticket["preuve_url"] = d["preuve_url"]

    try:
        result = send_tmc_notification(
            ticket       = ticket,
            statut_type  = d.get("statut_type", "debut"),
            destinataires_override = d.get("destinataires"),
            display_only = d.get("display_only", True),
        )
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/tmc/preview/<numero>")
def api_tmc_preview(numero):
    """Retourne le sujet + HTML de la notification TMC sans l'envoyer."""
    from db.schema import get_conn as _gc
    from db.tmc import _build_html_tmc, _build_subject_tmc
    statut_type = request.args.get("type", "debut")

    conn = _gc()
    row = conn.execute("""
        SELECT t.*,
               ti.libelle_fr, ti.langue as type_langue,
               e.nom as equipe_nom, e.email_list,
               s.nom as sup_nom, s.prenom as sup_prenom
        FROM tickets t
        LEFT JOIN types_incident ti ON ti.id=t.type_incident_id
        LEFT JOIN equipes_tmc e    ON e.id=t.equipe_tmc_id
        LEFT JOIN superviseurs s   ON s.id=t.superviseur_id
        WHERE t.numero=?
    """, (numero,)).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Ticket non trouvé"}), 404

    ticket  = dict(row)
    langue  = ticket.get("langue") or ticket.get("type_langue") or "fr"
    subject = _build_subject_tmc(ticket, statut_type, langue)
    body    = _build_html_tmc(ticket, statut_type, langue)
    return jsonify({"subject": subject, "html_body": body, "langue": langue})


@app.get("/api/tmc/routing/<int:type_incident_id>")
def api_tmc_routing(type_incident_id):
    """Retourne l'équipe TMC et la mailing list pour un type d'incident."""
    from db.schema import get_conn as _gc
    conn = _gc()
    rule = conn.execute("""
        SELECT r.*, e.nom as equipe_nom, e.domaine, e.email_list,
               ti.langue, ti.priorite_defaut
        FROM routing_rules r
        JOIN equipes_tmc e ON e.id=r.equipe_tmc_id
        JOIN types_incident ti ON ti.id=r.type_incident_id
        WHERE r.type_incident_id=? AND r.actif=1
        ORDER BY r.niveau_escalade LIMIT 1
    """, (type_incident_id,)).fetchone()

    if not rule:
        conn.close()
        return jsonify({"equipe": None, "mailing_list": None})

    ml = conn.execute("""
        SELECT adresses FROM mailing_lists
        WHERE equipe_tmc_id=? AND niveau=1 AND type_canal='email'
        ORDER BY niveau LIMIT 1
    """, (rule["equipe_tmc_id"],)).fetchone()
    conn.close()

    return jsonify({
        "equipe_id":    rule["equipe_tmc_id"],
        "equipe_nom":   rule["equipe_nom"],
        "domaine":      rule["domaine"],
        "email_list":   ml["adresses"] if ml else rule["email_list"] or "",
        "langue":       rule["langue"],
        "delai_escalade_min": rule["delai_escalade_min"],
    })

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/services")
def api_services():
    return jsonify({"services": sorted(catalog().keys())})


@app.post("/api/reload-catalog")
def api_reload_catalog():
    global _CATALOG
    try:
        new_cat = build_service_catalog(
            skip_sheets=set(CONFIG.get("excel_skip_sheets", []))
        )
        with _CATALOG_LOCK:
            _CATALOG = new_cat
        return jsonify({"status": "ok", "services_count": len(_CATALOG)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/service/<service_name>")
def api_service(service_name: str):
    entry = catalog().get(service_name)
    if entry is None:
        return jsonify({"error": "Service non trouvé"}), 404
    return jsonify(entry)


@app.post("/api/send-mail")
def api_send_mail():
    data = request.get_json(force=True)
    err  = _validate_incident(data)
    if err:
        return jsonify({"error": err}), 400
    try:
        result = _build_outlook_mail(data, display=False)
        _log_sent(data, result.get("method", "unknown"), result.get("subject", ""))
        return jsonify({"status": "ok", **result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/open-in-outlook")
def api_open_in_outlook():
    data = request.get_json(force=True)
    err  = _validate_incident(data)
    if err:
        return jsonify({"error": err}), 400
    try:
        result = _build_outlook_mail(data, display=True)
        _log_sent(data, result.get("method", "unknown"), result.get("subject", ""))
        return jsonify({"status": "ok", **result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/config")
def api_get_config():
    return jsonify(CONFIG)


@app.post("/api/config")
def api_save_config():
    new_cfg  = request.get_json(force=True)
    required = {"recipients_to", "recipients_cc", "signature"}
    if not required.issubset(new_cfg.keys()):
        return jsonify({"error": "Structure de config invalide"}), 400
    CONFIG.update(new_cfg)
    tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
    try:
        tmp_path.write_text(json.dumps(CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(CONFIG_PATH)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        return jsonify({"error": f"Échec sauvegarde config : {exc}"}), 500
    return jsonify({"status": "ok"})


@app.post("/api/copy-sms")
def api_copy_sms():
    data = request.get_json(force=True)
    _, _, fn_sms = _dispatch(data)
    sms  = fn_sms(data)
    try:
        pyperclip.copy(sms)
        copied = True
    except Exception:
        copied = False
    return jsonify({"status": "ok", "copied": copied, "text": sms})


@app.post("/api/open-notif-outlook")
def api_open_notif_outlook():
    data  = request.get_json(force=True)
    notif = _ran_nbn_to_notif(data)
    try:
        result = _build_outlook_mail(notif, display=True)
        return jsonify({"status": "ok", **result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/copy-notif-sms")
def api_copy_notif_sms():
    data  = request.get_json(force=True)
    notif = _ran_nbn_to_notif(data)
    sms   = build_sms_text_notification(notif)
    try:
        pyperclip.copy(sms)
        copied = True
    except Exception:
        copied = False
    return jsonify({"status": "ok", "copied": copied, "text": sms})


@app.post("/api/preview")
def api_preview():
    data = request.get_json(force=True)
    fn_subject, fn_html, fn_sms = _dispatch(data)
    try:
        result = {
            "subject":   fn_subject(data),
            "html_body": fn_html(data),
            "sms_text":  fn_sms(data),
        }
        if data.get("mode") == "ran_nbn":
            notif = _ran_nbn_to_notif(data)
            result["notif_subject"]   = build_subject_notification(notif)
            result["notif_html_body"] = build_html_body_notification(notif)
            result["notif_sms_text"]  = build_sms_text_notification(notif)
            wa = build_whatsapp_text_ran_nbn(data)
            result["whatsapp_text"]      = wa
            result["whatsapp_available"] = bool(wa)
        elif data.get("mode") == "services":
            notif = _services_to_notif(data)
            result["notif_subject"]   = build_subject_notification(notif)
            result["notif_html_body"] = build_html_body_notification(notif)
            result["notif_sms_text"]  = build_sms_text_notification(notif)
            # XXL #2 : WhatsApp Services
            wa_svc = build_whatsapp_text_services(data)
            result["whatsapp_text"]      = wa_svc
            result["whatsapp_available"] = bool(wa_svc)
        return jsonify(result)
    except KeyError as exc:
        return jsonify({"error": f"Champ manquant : {exc}"}), 400


@app.post("/api/copy-whatsapp")
def api_copy_whatsapp():
    data = request.get_json(force=True)
    text = data.get("custom_whatsapp_text") or build_whatsapp_text_ran_nbn(data)
    try:
        pyperclip.copy(text)
        copied = True
    except Exception:
        copied = False
    return jsonify({"status": "ok", "copied": copied, "text": text})


@app.post("/api/open-services-notif-outlook")
def api_open_services_notif_outlook():
    data  = request.get_json(force=True)
    notif = _services_to_notif(data)
    try:
        result = _build_outlook_mail(notif, display=True)
        return jsonify({"status": "ok", **result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/copy-services-notif-sms")
def api_copy_services_notif_sms():
    data  = request.get_json(force=True)
    notif = _services_to_notif(data)
    sms   = build_sms_text_notification(notif)
    try:
        pyperclip.copy(sms)
        copied = True
    except Exception:
        copied = False
    return jsonify({"status": "ok", "copied": copied, "text": sms})




# ── Boucle mail Notification (séparée) ───────────────────────────────────────
@app.post("/api/send-notification-mail")
def api_send_notification_mail():
    """
    Envoi direct du mail de notification (build_html_body_notification).
    Utilise la liste de destinataires 'recipients_notif' si définie dans config,
    sinon bascule sur 'recipients_to'.
    """
    data = request.get_json(force=True)
    notif_data = _ran_nbn_to_notif(data) if data.get("mode") == "ran_nbn" else _services_to_notif(data)

    # Permettre surcharge du corps via custom_
    subject   = data.get("custom_notif_subject")   or build_subject_notification(notif_data)
    html_body = data.get("custom_notif_html_body") or build_html_body_notification(notif_data)

    # Destinataires notification dédiés (config optionnelle)
    to_list = CONFIG.get("recipients_notif") or CONFIG.get("recipients_to", [])
    cc_list = CONFIG.get("recipients_notif_cc") or CONFIG.get("recipients_cc", [])

    display = data.get("display", True)  # True = ouvrir, False = envoyer direct

    try:
        import win32com.client as win32
        outlook = win32.Dispatch("Outlook.Application")
        mail    = outlook.CreateItem(0)
        mail.Subject  = subject
        mail.HTMLBody = html_body
        for addr in to_list:
            if addr.strip():
                mail.Recipients.Add(addr.strip()).Type = 1
        for addr in cc_list:
            if addr.strip():
                r = mail.Recipients.Add(addr.strip())
                r.Type = 2
        mail.Recipients.ResolveAll()
        if display:
            mail.Display()
        else:
            mail.Send()
        _log_sent(data, "outlook-notif", subject)
        return jsonify({"status": "ok", "method": "outlook-notif", "subject": subject})
    except Exception as com_err:
        # Fallback EML
        try:
            from email.mime.multipart import MIMEMultipart as MMP
            from email.mime.text import MIMEText as MMT
            msg = MMP("alternative")
            msg["Subject"] = subject
            msg["To"]      = "; ".join(a.strip() for a in to_list if a.strip())
            msg.attach(MMT(html_body, "html", "utf-8"))
            tmp = tempfile.NamedTemporaryFile(mode="wb", suffix=".eml",
                                              prefix="smartsup_notif_", delete=False)
            tmp.write(msg.as_bytes()); tmp.close()
            _open_cross_platform(tmp.name)
            threading.Thread(target=lambda p: (time.sleep(30), os.unlink(p)),
                             args=(tmp.name,), daemon=True).start()
            _log_sent(data, "eml-notif", subject)
            return jsonify({"status": "ok", "method": "eml-notif", "subject": subject})
        except Exception as eml_err:
            return jsonify({"error": f"Outlook: {com_err} | EML: {eml_err}"}), 500

# ── Journal (XXL #1) ──────────────────────────────────────────────────────────
@app.get("/api/sent-log")
def api_sent_log():
    """Retourne les N dernières entrées du journal."""
    limit = min(int(request.args.get("limit", 50)), 200)
    entries = []
    if LOG_PATH.exists():
        lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
        for line in reversed(lines[-limit:]):
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return jsonify({"entries": entries})




# ── Export PDF rapport de clôture (XXL #7) ───────────────────────────────────
@app.post("/api/export-pdf")
def api_export_pdf():
    """
    Génère un rapport PDF de clôture d'incident.
    Utilise html2pdf via pdfkit (wkhtmltopdf) en priorité,
    sinon génère un HTML standalone téléchargeable.
    """
    data = request.get_json(force=True)

    sig        = CONFIG["signature"]
    service    = data.get("service", "—")
    ticket     = data.get("ticket",  "—")
    hd_raw     = data.get("hd",      "—")
    hf_raw     = data.get("hf",      "—")
    cause      = data.get("cause",   "—")
    action     = data.get("action",  "—")
    desc       = data.get("description", "—")
    priority   = data.get("priority", "—")
    mode_label = {"services": "Services", "ran_nbn": "RAN/NBN",
                  "notification": "Notification"}.get(data.get("mode", ""), "—")

    # Calcul durée
    duration_str = "—"
    try:
        from datetime import datetime as _dt
        fmt = "%Y-%m-%dT%H:%M"
        d1  = _dt.strptime(hd_raw[:16], fmt)
        d2  = _dt.strptime(hf_raw[:16], fmt)
        diff = int((d2 - d1).total_seconds())
        if diff > 0:
            h, m = divmod(diff // 60, 60)
            duration_str = f"{h}h {m:02d}min" if h else f"{m}min"
    except Exception:
        pass

    ts_now = datetime.now().strftime("%d/%m/%Y à %H:%M")

    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 20mm 18mm 18mm 18mm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Times New Roman', Times, serif; font-size: 12pt; color: #1A1A1A; background: #fff; }}

  .header {{ display: flex; align-items: center; justify-content: space-between;
             border-bottom: 3px solid #FF6D00; padding-bottom: 10px; margin-bottom: 18px; }}
  .logo-block {{ display: flex; align-items: center; gap: 10px; }}
  .logo-circle {{ width: 42px; height: 42px; border-radius: 50%;
                  background: linear-gradient(135deg, #E05A00, #FF6D00);
                  display: flex; align-items: center; justify-content: center;
                  color: #fff; font-weight: 900; font-size: 15pt; font-family: Arial; }}
  .logo-text {{ font-size: 16pt; font-weight: 700; color: #FF6D00; font-family: Arial; }}
  .logo-sub  {{ font-size: 8pt; color: #666; font-family: Arial; }}
  .header-right {{ text-align: right; font-size: 8.5pt; color: #555; font-family: Arial; }}

  h1 {{ font-size: 15pt; font-weight: 700; text-align: center; color: #1A1A1A;
       background: #FFF3E0; border: 2px solid #FF6D00; border-radius: 6px;
       padding: 10px 16px; margin-bottom: 18px; letter-spacing: .5px; }}

  table {{ width: 100%; border-collapse: collapse; margin-bottom: 14px; }}
  th, td {{ border: 1px solid #ccc; padding: 7px 10px; font-size: 10.5pt; }}
  th {{ background: #CCCCCC; color: #333; font-weight: 700; width: 38%; text-align: left; }}
  td {{ background: #fff; }}
  .td-orange {{ background: #FF6D00; color: #fff; font-weight: 700; }}
  .td-yellow {{ background: #FFC107; color: #1A1A1A; }}
  .td-green  {{ background: #4CAF50; color: #fff; font-weight: 700; }}
  .td-red    {{ background: #F44336; color: #fff; font-weight: 700; }}

  .section-title {{ font-size: 10pt; font-weight: 700; color: #FF6D00; text-transform: uppercase;
                    letter-spacing: 1px; border-left: 4px solid #FF6D00;
                    padding-left: 8px; margin: 14px 0 8px 0; }}

  .duration-box {{ display: inline-block; background: #E8F5E9; border: 1.5px solid #4CAF50;
                   border-radius: 6px; padding: 5px 14px; font-size: 12pt; font-weight: 700;
                   color: #2E7D32; }}

  .sig-block {{ margin-top: 24px; border-top: 1px solid #ddd; padding-top: 12px;
                font-size: 9.5pt; color: #555; }}
  .sig-name  {{ font-weight: 700; color: #1A1A1A; font-size: 10.5pt; }}

  .footer {{ position: fixed; bottom: 8mm; left: 18mm; right: 18mm;
             border-top: 1px solid #ddd; padding-top: 4px;
             font-size: 7.5pt; color: #999; text-align: center; font-family: Arial; }}
</style>
</head>
<body>

<div class="header">
  <div class="logo-block">
    <div class="logo-circle">O</div>
    <div>
      <div class="logo-text">SmartSup</div>
      <div class="logo-sub">Orange Guinée — NOC</div>
    </div>
  </div>
  <div class="header-right">
    Rapport généré le {ts_now}<br>
    Référence : {_html.escape(ticket)}
  </div>
</div>

<h1>RAPPORT DE CLÔTURE D'INCIDENT</h1>

<div class="section-title">Identification de l'incident</div>
<table>
  <tr><th>N° Ticket / Priorité</th><td class="td-orange">{_html.escape(ticket)} / {_html.escape(priority)}</td></tr>
  <tr><th>Mode</th><td>{_html.escape(mode_label)}</td></tr>
  <tr><th>Service / Lien impacté</th><td><strong>{_html.escape(service)}</strong></td></tr>
  <tr><th>Description</th><td>{_html.escape(desc)}</td></tr>
</table>

<div class="section-title">Chronologie</div>
<table>
  <tr><th>Heure de début (HD)</th><td><strong>{_html.escape(hd_raw)}</strong></td></tr>
  <tr><th>Heure de fin (HF)</th><td><strong>{_html.escape(hf_raw)}</strong></td></tr>
  <tr><th>Durée totale</th><td><span class="duration-box">{_html.escape(duration_str)}</span></td></tr>
</table>

<div class="section-title">Analyse technique</div>
<table>
  <tr><th>Cause identifiée</th><td class="td-yellow">{_html.escape(cause)}</td></tr>
  <tr><th>Action corrective</th><td class="td-yellow">{_html.escape(action)}</td></tr>
  <tr><th>Observation finale</th><td class="td-green">Service rétabli</td></tr>
</table>

<div class="sig-block">
  <p>Rédigé par :</p>
  <p class="sig-name">{_html.escape(sig["nom"])}</p>
  <p>{_html.escape(sig["fonction"])} — {_html.escape(sig["entite"])}</p>
  <p>Tél : {_html.escape(sig["telephone"])}</p>
</div>

<div class="footer">
  SmartSup v3.3 — Orange Guinée NOC — Document confidentiel interne
</div>

</body></html>"""

    # Essayer pdfkit/wkhtmltopdf
    try:
        import pdfkit
        pdf_bytes = pdfkit.from_string(html_content, False,
                                       options={"encoding": "UTF-8",
                                                "page-size": "A4",
                                                "margin-top": "20mm",
                                                "margin-bottom": "18mm"})
        from flask import Response
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        fname = f"rapport_incident_{ts}.pdf"
        return Response(pdf_bytes,
                        mimetype="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{fname}"'})
    except Exception:
        pass

    # Fallback : HTML téléchargeable (s'ouvre dans le navigateur, imprimable en PDF)
    from flask import Response
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    fname = f"rapport_incident_{ts}.html"
    return Response(html_content.encode("utf-8"),
                    mimetype="text/html",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})

# ── Statistiques (XXL #4) ─────────────────────────────────────────────────────
@app.get("/api/stats")
def api_stats():
    """Retourne des KPIs agrégés depuis le catalogue."""
    cat = catalog()
    if not cat:
        return jsonify({"error": "Catalogue vide"}), 404

    # Top 10 services par nombre de causes historiques connues
    by_volume = sorted(
        ((name, len(entry.get("causes", []))) for name, entry in cat.items()),
        key=lambda x: x[1], reverse=True
    )[:10]

    # Top 10 causes toutes catégories
    from collections import Counter
    all_causes: Counter = Counter()
    for entry in cat.values():
        for c in entry.get("causes", []):
            all_causes[c] += 1
    top_causes = all_causes.most_common(10)

    return jsonify({
        "services_count": len(cat),
        "top_services_by_history": [{"name": n, "incidents": v} for n, v in by_volume],
        "top_causes": [{"cause": c, "count": n} for c, n in top_causes],
    })


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import webbrowser
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(debug=False, port=5000)
