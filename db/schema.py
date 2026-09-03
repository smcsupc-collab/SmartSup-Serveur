"""
SmartSup v4 — Schéma SQLite
Tables :
  superviseurs   — utilisateurs du système
  types_incident — référentiel des types (catégories)
  equipes_tmc    — équipes back-office (TMC)
  routing_rules  — règles service/type → équipe + langue
  mailing_lists  — listes de diffusion par équipe/niveau
  tickets        — incidents créés
  ticket_events  — timeline de chaque incident
  ticket_comms   — communications émises (mail, SMS, WA)
  signatures     — signatures multi-superviseur, bilingues
  email_templates— modèles d'e-mail dynamiques
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "incidents.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Crée toutes les tables si elles n'existent pas encore."""
    conn = get_conn()
    c = conn.cursor()

    # ── Superviseurs ──────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS superviseurs (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        nom       TEXT NOT NULL,
        prenom    TEXT NOT NULL,
        fonction  TEXT,
        telephone TEXT,
        email     TEXT,
        actif     INTEGER DEFAULT 1,
        created   TEXT DEFAULT (datetime('now'))
    )""")

    # ── Types d'incident (référentiel) ────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS types_incident (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        code        TEXT UNIQUE NOT NULL,
        libelle_fr  TEXT NOT NULL,
        libelle_en  TEXT NOT NULL,
        categorie   TEXT NOT NULL,
        langue      TEXT NOT NULL DEFAULT 'fr',
        priorite_defaut TEXT DEFAULT 'P2',
        actif       INTEGER DEFAULT 1
    )""")

    # ── Équipes TMC ───────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS equipes_tmc (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        code        TEXT UNIQUE NOT NULL,
        nom         TEXT NOT NULL,
        domaine     TEXT NOT NULL,
        email_list  TEXT,
        telephone   TEXT,
        actif       INTEGER DEFAULT 1
    )""")

    # ── Règles de routage type_incident → équipe TMC ─────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS routing_rules (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        type_incident_id INTEGER REFERENCES types_incident(id),
        equipe_tmc_id    INTEGER REFERENCES equipes_tmc(id),
        niveau_escalade  INTEGER DEFAULT 1,
        delai_escalade_min INTEGER DEFAULT 30,
        actif            INTEGER DEFAULT 1
    )""")

    # ── Listes de diffusion ───────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS mailing_lists (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        equipe_tmc_id INTEGER REFERENCES equipes_tmc(id),
        niveau        INTEGER DEFAULT 1,
        nom           TEXT NOT NULL,
        adresses      TEXT NOT NULL,
        type_canal    TEXT DEFAULT 'email'
    )""")

    # ── Tickets d'incident ────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        numero           TEXT UNIQUE NOT NULL,
        type_incident_id INTEGER REFERENCES types_incident(id),
        superviseur_id   INTEGER REFERENCES superviseurs(id),
        equipe_tmc_id    INTEGER REFERENCES equipes_tmc(id),
        statut           TEXT DEFAULT 'ouvert',
        priorite         TEXT DEFAULT 'P2',
        criticite        TEXT DEFAULT 'normale',
        service          TEXT,
        lien_impacte     TEXT,
        description      TEXT NOT NULL,
        cause            TEXT,
        action           TEXT,
        hd               TEXT NOT NULL,
        hf               TEXT,
        zone_impactee    TEXT,
        observation      TEXT,
        mode             TEXT DEFAULT 'services',
        langue           TEXT DEFAULT 'fr',
        preuve_type      TEXT,
        preuve_url       TEXT,
        preuve_note      TEXT,
        ack_tmc          INTEGER DEFAULT 0,
        ack_at           TEXT,
        mttr_minutes     INTEGER,
        created          TEXT DEFAULT (datetime('now')),
        updated          TEXT DEFAULT (datetime('now'))
    )""")

    # ── Timeline événements par ticket ────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS ticket_events (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id    INTEGER NOT NULL REFERENCES tickets(id),
        type_event   TEXT NOT NULL,
        description  TEXT,
        auteur       TEXT,
        ts           TEXT DEFAULT (datetime('now'))
    )""")

    # ── Communications émises ─────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS ticket_comms (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id   INTEGER NOT NULL REFERENCES tickets(id),
        canal       TEXT NOT NULL,
        groupe      TEXT,
        sujet       TEXT,
        corps       TEXT,
        destinataires TEXT,
        statut      TEXT DEFAULT 'envoye',
        ts          TEXT DEFAULT (datetime('now'))
    )""")

    # ── Signatures bilingues par superviseur ──────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS signatures (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        superviseur_id INTEGER REFERENCES superviseurs(id),
        langue         TEXT DEFAULT 'fr',
        nom_affiche    TEXT NOT NULL,
        fonction       TEXT,
        entite         TEXT,
        telephone      TEXT,
        email          TEXT,
        actif          INTEGER DEFAULT 1
    )""")

    # ── Modèles d'e-mail dynamiques ───────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS email_templates (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        code             TEXT UNIQUE NOT NULL,
        langue           TEXT NOT NULL DEFAULT 'fr',
        type_incident_id INTEGER REFERENCES types_incident(id),
        nom              TEXT NOT NULL,
        sujet_template   TEXT NOT NULL,
        corps_template   TEXT NOT NULL,
        actif            INTEGER DEFAULT 1,
        created          TEXT DEFAULT (datetime('now'))
    )""")

    conn.commit()
    conn.close()
    print(f"[DB] incidents.db initialisée — {DB_PATH}")


def _seed_defaults():
    """Insère les données de référence si les tables sont vides."""
    conn = get_conn()
    c = conn.cursor()

    # Types d'incident par défaut
    types = [
        ("SVA_USSD",   "Incident USSD/SVA",          "USSD/SVA Incident",           "SVA",         "fr", "P1"),
        ("B2W",        "Incident Bank to Wallet",     "Bank to Wallet Incident",     "B2W",         "en", "P1"),
        ("ORANGE_MONEY","Incident Orange Money",      "Orange Money Incident",       "Mobile Money","fr", "P1"),
        ("RAN_COUPURE","Coupure Site RAN",            "RAN Site Outage",             "RAN",         "fr", "P1"),
        ("NBN_COUPURE","Coupure Lien NBN",            "NBN Link Outage",             "NBN",         "fr", "P1"),
        ("CORE_NETWORK","Incident Cœur de Réseau",   "Core Network Incident",       "Core",        "fr", "P1"),
        ("VAS_PLATFORM","Incident Plateforme VAS",    "VAS Platform Incident",       "VAS",         "fr", "P2"),
        ("B2B_SERVICE", "Incident Service B2B",       "B2B Service Incident",        "B2B",         "fr", "P2"),
        ("INTERNET",    "Incident Internet",          "Internet Incident",           "Data",        "fr", "P2"),
        ("ROAMING",     "Incident Roaming",           "Roaming Incident",            "Roaming",     "en", "P2"),
    ]
    for t in types:
        c.execute("""INSERT OR IGNORE INTO types_incident
                     (code,libelle_fr,libelle_en,categorie,langue,priorite_defaut)
                     VALUES (?,?,?,?,?,?)""", t)

    # Équipes TMC par défaut
    equipes = [
        ("TMC_RAN",   "TMC RAN & Radio",     "RAN"),
        ("TMC_CORE",  "TMC Cœur de Réseau",  "Core"),
        ("TMC_VAS",   "TMC Plateformes VAS",  "VAS"),
        ("TMC_DATA",  "TMC Data & Internet",  "Data"),
        ("TMC_B2W",   "TMC Bank to Wallet",   "B2W"),
        ("TMC_B2B",   "TMC Services B2B",     "B2B"),
        ("TMC_NBN",   "TMC NBN & Transmission","NBN"),
    ]
    for e in equipes:
        c.execute("""INSERT OR IGNORE INTO equipes_tmc (code,nom,domaine)
                     VALUES (?,?,?)""", e)

    # Superviseur exemple
    c.execute("""INSERT OR IGNORE INTO superviseurs (id,nom,prenom,fonction)
                 VALUES (1,'NOC','Superviseur','Ingénieur Supervision')""")

    conn.commit()
    conn.close()
    print("[DB] Données de référence chargées.")


def migrate_sent_log(log_path):
    """Importe l'historique sent_log.jsonl dans ticket_comms."""
    import json
    from pathlib import Path as P
    p = P(log_path)
    if not p.exists():
        return 0
    conn = get_conn()
    c = conn.cursor()
    count = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
            c.execute("""INSERT OR IGNORE INTO ticket_comms
                         (canal, groupe, sujet, ts)
                         VALUES (?,?,?,?)""",
                      (e.get("method","?"), e.get("mode","?"),
                       e.get("subject",""), e.get("ts","")))
            count += 1
        except Exception:
            continue
    conn.commit()
    conn.close()
    return count
