"""
SMART-SUP — Schéma de données v5
=================================

Plateforme de DOCUMENTATION, COMMUNICATION, SUIVI et REPORTING des incidents.

Principe fondateur (cf. cahier des charges) :
    Le ticket est créé dans l'outil du groupe.
    Notre système ne fait que documenter, communiquer, suivre et reporter.

Conséquences concrètes sur ce schéma, par rapport au schéma v4 :
  - `reference_externe` est un champ TEXTE LIBRE non contraint : c'est la
    référence du ticket groupe, collée telle quelle. Aucun format n'est
    imposé, aucune logique de l'outil du groupe n'est reproduite.
  - AUCUNE numérotation interne d'incident n'est générée (le `TT-YYYYMMDD-NNN`
    de la v4 est supprimé : il créait un second identifiant concurrent).
  - AUCUN cycle de vie opérationnel (ouvert/en_cours/résolu/clôturé), aucun
    ACK, aucune escalade, aucun SLA. Le seul statut conservé est
    `statut_documentaire` : il décrit l'état de NOTRE documentation,
    pas l'état du ticket dans l'outil du groupe.
  - Le référentiel de services provient du Catalogue de supervision réel
    (19 domaines, 256 services), et non plus d'une liste de 10 types codés
    en dur qui ne correspondait à rien d'existant.

Encodage : UTF-8. Le module ne dépend d'aucune bibliothèque externe.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "smartsup.db"


# ----------------------------------------------------------------------
#  Vocabulaires contrôlés
# ----------------------------------------------------------------------

# Type STRUCTUREL de l'incident : détermine les champs spécifiques attendus
# et le gabarit de communication utilisé. Volontairement ouvert : ajouter un
# type ne demande aucune migration de schéma (cf. décision 0.1 — attributs
# spécifiques en JSON).
TYPES_INCIDENT = ("service", "ran", "nbn", "libre")

# État de NOTRE documentation, pas du ticket groupe.
STATUTS_DOCUMENTAIRES = ("brouillon", "signale", "en_suivi", "cloture", "regularise")

# Les 5 canaux du cahier des charges (§5).
CANAUX = ("email", "notification_arpt", "web", "sms", "whatsapp")

# Types de message. `regularisation` matérialise un cas opérationnel réel
# (avis de fin corrigé et réémis a posteriori), observé dans les mails.
TYPES_MESSAGE = ("debut", "avancement", "fin", "regularisation", "non_avere")

PRIORITES = ("P1", "P2", "P3")
LANGUES = ("fr", "en")

# Distinction À / Cc : dans les mails réels, les partenaires externes qui
# doivent agir sont en « À », les équipes internes en « Cc ». Ce n'est pas
# cosmétique, c'est signifiant.
DESTINATIONS = ("a", "cc")


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

-- ==================================================================
--  RÉFÉRENTIELS
-- ==================================================================

CREATE TABLE IF NOT EXISTS superviseurs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nom             TEXT    NOT NULL,
    email           TEXT    UNIQUE,
    trigramme       TEXT,
    actif           INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS signatures (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    superviseur_id  INTEGER NOT NULL REFERENCES superviseurs(id) ON DELETE CASCADE,
    langue          TEXT    NOT NULL DEFAULT 'fr',
    contenu_html    TEXT    NOT NULL DEFAULT '',
    actif           INTEGER NOT NULL DEFAULT 1,
    UNIQUE (superviseur_id, langue)
);

-- Domaines métier issus du Catalogue de supervision réel.
CREATE TABLE IF NOT EXISTS domaines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nom             TEXT    NOT NULL UNIQUE,
    actif           INTEGER NOT NULL DEFAULT 1
);

-- Catalogue des services supervisés. Sert à trois choses :
--   1. proposer une saisie par sélection plutôt qu'en texte libre ;
--   2. pré-remplir la priorité de l'incident (évite la double saisie) ;
--   3. permettre un reporting fiable par service et par domaine.
CREATE TABLE IF NOT EXISTS services (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    domaine_id          INTEGER NOT NULL REFERENCES domaines(id),
    nom                 TEXT    NOT NULL,
    priorite_defaut     TEXT,                 -- P1/P2/P3, NULL si non définie
    supervise           INTEGER NOT NULL DEFAULT 1,
    outil_supervision   TEXT,
    sim_msisdn_test     TEXT,
    sonde_terminal      TEXT,
    observations        TEXT,
    origine             TEXT,
    actif               INTEGER NOT NULL DEFAULT 1,
    UNIQUE (domaine_id, nom)
);

CREATE INDEX IF NOT EXISTS idx_services_domaine  ON services(domaine_id);
CREATE INDEX IF NOT EXISTS idx_services_priorite ON services(priorite_defaut);

-- Équipes destinataires des notifications.
-- Volontairement nommé « equipes » et non « equipes_tmc » : le terme TMC
-- laissait penser à une prise en charge type ticketing.
CREATE TABLE IF NOT EXISTS equipes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE,
    nom             TEXT    NOT NULL,
    domaine_id      INTEGER REFERENCES domaines(id),
    actif           INTEGER NOT NULL DEFAULT 1
);

-- Listes de diffusion : une adresse, un canal, une destination (À ou Cc).
CREATE TABLE IF NOT EXISTS mailing_lists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    libelle         TEXT    NOT NULL,
    adresse         TEXT    NOT NULL,
    canal           TEXT    NOT NULL DEFAULT 'email',
    destination     TEXT    NOT NULL DEFAULT 'a',      -- 'a' ou 'cc'
    equipe_id       INTEGER REFERENCES equipes(id),
    -- Ciblage : NULL = s'applique à tout. Permet par exemple d'envoyer une
    -- liste uniquement pour les incidents NBN, ou seulement pour les avis
    -- de fin, sans toucher au code.
    type_incident   TEXT,
    type_message    TEXT,
    domaine_id      INTEGER REFERENCES domaines(id),
    groupe          TEXT,                              -- regroupement libre
    ordre           INTEGER NOT NULL DEFAULT 0,
    actif           INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_mailing_canal ON mailing_lists(canal, actif);

-- Gabarits de communication, paramétrés par type/canal/langue.
-- Remplace les ~12 fonctions de génération dupliquées de la v4.
CREATE TABLE IF NOT EXISTS modeles_communication (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE,
    type_incident   TEXT    NOT NULL,
    canal           TEXT    NOT NULL,
    type_message    TEXT    NOT NULL,
    langue          TEXT    NOT NULL DEFAULT 'fr',
    sujet_tpl       TEXT    NOT NULL DEFAULT '',
    corps_tpl       TEXT    NOT NULL DEFAULT '',
    actif           INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_modeles_lookup
    ON modeles_communication(type_incident, canal, type_message, langue);


-- ==================================================================
--  INCIDENTS
-- ==================================================================

CREATE TABLE IF NOT EXISTS incidents (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identifiant externe : collé depuis l'outil du groupe.
    -- Volontairement NON contraint en format et NON unique : les cas réels
    -- montrent des variantes de saisie, et un même ticket groupe peut
    -- légitimement être documenté deux fois (ex. régularisation tardive).
    reference_externe       TEXT    NOT NULL,

    type_incident           TEXT    NOT NULL DEFAULT 'service',
    priorite                TEXT,
    langue                  TEXT    NOT NULL DEFAULT 'fr',

    description             TEXT    NOT NULL DEFAULT '',
    date_debut              TEXT,
    date_fin                TEXT,
    cause                   TEXT,
    action                  TEXT,
    observation             TEXT,

    -- Périmètre non catalogué (sites, liens, texte libre).
    -- Les services catalogués passent par incident_services.
    perimetre_libre         TEXT,

    -- Champs spécifiques au type, en JSON (décision 0.1).
    -- Ajouter un type d'incident ne demande donc aucune migration.
    --   ran  : {"site_id": "...", "sites_rattaches": 58, "nature": "coupure"}
    --   nbn  : {"liens_impactes": ["NBN KIPE-BOKE", ...]}
    --   libre: {"partenaire": "VistaGui", "contact_externe": "..."}
    attributs_specifiques   TEXT    NOT NULL DEFAULT '{}',

    -- État de NOTRE documentation, pas du ticket groupe.
    statut_documentaire     TEXT    NOT NULL DEFAULT 'brouillon',

    superviseur_id          INTEGER REFERENCES superviseurs(id),
    created_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_incidents_ref     ON incidents(reference_externe);
CREATE INDEX IF NOT EXISTS idx_incidents_debut   ON incidents(date_debut);
CREATE INDEX IF NOT EXISTS idx_incidents_statut  ON incidents(statut_documentaire);
CREATE INDEX IF NOT EXISTS idx_incidents_type    ON incidents(type_incident);

-- Un incident peut impacter plusieurs services (cas réel : « VOIX, DATA,
-- SMS, USSD » sur une coupure de site).
CREATE TABLE IF NOT EXISTS incident_services (
    incident_id     INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    service_id      INTEGER NOT NULL REFERENCES services(id),
    PRIMARY KEY (incident_id, service_id)
);


-- ==================================================================
--  PREUVES
-- ==================================================================
-- Comble un manque du système actuel : les captures d'écran ne circulaient
-- que collées dans Outlook, sans trace structurée réutilisable.

CREATE TABLE IF NOT EXISTS incident_evidences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id     INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    type            TEXT    NOT NULL DEFAULT 'capture',  -- capture|lien|note|fichier
    chemin          TEXT,              -- chemin disque (décision 0 : stockage fichier)
    contenu         TEXT,              -- lien ou note technique
    legende         TEXT,
    ordre           INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_evidences_incident ON incident_evidences(incident_id);


-- ==================================================================
--  COMMUNICATIONS
-- ==================================================================
-- Remplace sent_log.jsonl. Conserve un instantané du contenu réellement
-- envoyé (et pas seulement des métadonnées) : utile pour retrouver
-- exactement ce qui a été communiqué, y compris en contexte réglementaire.

CREATE TABLE IF NOT EXISTS incident_communications (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id         INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    canal               TEXT    NOT NULL,
    type_message        TEXT    NOT NULL,
    langue              TEXT    NOT NULL DEFAULT 'fr',
    destinataires_a     TEXT    NOT NULL DEFAULT '',
    destinataires_cc    TEXT    NOT NULL DEFAULT '',
    sujet               TEXT    NOT NULL DEFAULT '',
    corps               TEXT    NOT NULL DEFAULT '',
    envoye_par          INTEGER REFERENCES superviseurs(id),
    envoye_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    statut_envoi        TEXT    NOT NULL DEFAULT 'envoye'  -- envoye|brouillon|echec
);

CREATE INDEX IF NOT EXISTS idx_comms_incident ON incident_communications(incident_id);
CREATE INDEX IF NOT EXISTS idx_comms_date     ON incident_communications(envoye_at);
CREATE INDEX IF NOT EXISTS idx_comms_canal    ON incident_communications(canal);


-- ==================================================================
--  PARAMÉTRAGE
-- ==================================================================
-- Tout ce qui était codé en dur devient éditable ici. Objectif : aucune
-- modification de code pour ajouter un destinataire, une formulation, un
-- type de message, ou pour activer/désactiver une fonctionnalité.

-- Paramètres généraux (clé/valeur typée).
CREATE TABLE IF NOT EXISTS parametres (
    cle             TEXT    PRIMARY KEY,
    valeur          TEXT    NOT NULL DEFAULT '',
    type_valeur     TEXT    NOT NULL DEFAULT 'texte',  -- texte|nombre|booleen|couleur|liste|json
    categorie       TEXT    NOT NULL DEFAULT 'general',
    libelle         TEXT    NOT NULL DEFAULT '',
    aide            TEXT,
    options         TEXT,                -- valeurs autorisées (JSON), si applicable
    ordre           INTEGER NOT NULL DEFAULT 0,
    modifiable      INTEGER NOT NULL DEFAULT 1,
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_parametres_cat ON parametres(categorie, ordre);

-- Types de message : ce qui était STRUCTURE_MESSAGE en dur.
-- Ajouter un type de communication ne demande plus de toucher au code.
CREATE TABLE IF NOT EXISTS types_message (
    code            TEXT    PRIMARY KEY,
    libelle         TEXT    NOT NULL,
    titre_avis      TEXT    NOT NULL DEFAULT '',
    prefixe_sujet   TEXT    NOT NULL DEFAULT '',
    inclut_reference INTEGER NOT NULL DEFAULT 1,
    salutation      TEXT,
    mention_bas     TEXT,
    canal_defaut    TEXT    NOT NULL DEFAULT 'email',
    ordre           INTEGER NOT NULL DEFAULT 0,
    actif           INTEGER NOT NULL DEFAULT 1
);

-- Champs affichés par type de message, dans l'ordre voulu.
CREATE TABLE IF NOT EXISTS champs_message (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    type_message    TEXT    NOT NULL REFERENCES types_message(code) ON DELETE CASCADE,
    champ           TEXT    NOT NULL,
    libelle         TEXT    NOT NULL,
    obligatoire     INTEGER NOT NULL DEFAULT 0,
    ordre           INTEGER NOT NULL DEFAULT 0,
    actif           INTEGER NOT NULL DEFAULT 1,
    UNIQUE (type_message, champ)
);

-- Valeurs proposées à la saisie : causes, actions, observations, zones, TMC…
-- Remplace le dictionnaire SUGGESTIONS codé en dur.
CREATE TABLE IF NOT EXISTS valeurs_suggerees (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    liste           TEXT    NOT NULL,      -- causes|actions|observations|zones|tmc…
    valeur          TEXT    NOT NULL,
    contexte        TEXT,                  -- ex. type de message, NULL = toujours
    ordre           INTEGER NOT NULL DEFAULT 0,
    actif           INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_valeurs_liste ON valeurs_suggerees(liste, contexte, ordre);

-- Règles de description automatique : remplace les `if domaine.includes(...)`
-- qui étaient écrits dans le JavaScript.
CREATE TABLE IF NOT EXISTS regles_description (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    motif_domaine   TEXT    NOT NULL,      -- texte cherché dans le domaine
    modele          TEXT    NOT NULL,      -- {domaine} {service} {reference}
    priorite_regle  INTEGER NOT NULL DEFAULT 0,   -- la plus haute gagne
    actif           INTEGER NOT NULL DEFAULT 1
);


-- ==================================================================
--  VERSIONNAGE DU SCHÉMA
-- ==================================================================
-- Absent de la v4 : rien ne permettait de faire évoluer une base déjà
-- peuplée. Cette table rend les migrations futures possibles.

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applique_at TEXT NOT NULL DEFAULT (datetime('now')),
    note        TEXT
);
"""

SCHEMA_VERSION = 6


def get_conn(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Ouvre une connexion configurée. À utiliser comme context manager."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: Path | str = DB_PATH) -> None:
    """Crée le schéma s'il n'existe pas et enregistre sa version."""
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, note) VALUES (?, ?)",
            (SCHEMA_VERSION, "Socle documentation/communication/reporting"),
        )


# ----------------------------------------------------------------------
#  Helpers attributs spécifiques (décision 0.1 : JSON)
# ----------------------------------------------------------------------

# Schéma de validation applicatif — volontairement souple : les clés
# inconnues sont conservées, seules les clés attendues sont documentées.
ATTRIBUTS_ATTENDUS = {
    "service": ("partenaire",),
    "ran": ("site_id", "sites_rattaches", "nature"),
    "nbn": ("liens_impactes",),
    "libre": ("partenaire", "contact_externe"),
}


def lire_attributs(row_value: str | None) -> dict:
    """Décode la colonne attributs_specifiques, en tolérant les valeurs vides."""
    if not row_value:
        return {}
    try:
        data = json.loads(row_value)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def ecrire_attributs(data: dict | None) -> str:
    """Encode les attributs spécifiques pour stockage."""
    return json.dumps(data or {}, ensure_ascii=False)
