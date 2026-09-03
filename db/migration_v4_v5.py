"""
SMART-SUP — Migration des données v4 vers le modèle v5
=======================================================

Reprend le contenu de l'ancienne base `data/incidents.db` (modèle « tickets »)
vers `data/smartsup.db` (modèle « incidents »), sans perte.

Ce que la migration conserve :
  · superviseurs et signatures        → tels quels
  · équipes TMC                        → table `equipes`
  · listes de diffusion                → enrichies du champ destination (a/cc)
  · modèles d'e-mail                   → table `modeles_communication`
  · tickets                            → table `incidents`

Ce que la migration abandonne volontairement (cf. cahier des charges : le
ticketing appartient à l'outil du groupe) :
  · ack_tmc / ack_at                   → notion de prise en charge
  · mttr_minutes                       → recalculable en reporting si besoin
  · statuts opérationnels              → convertis en statut documentaire
  · numéro interne TT-AAAAMMJJ-NNN     → voir ci-dessous

Le numéro interne v4 n'est PAS traité comme la référence externe : c'est un
identifiant fabriqué par l'ancien système, pas une référence du groupe. Il est
conservé dans les attributs spécifiques (`numero_interne_v4`) pour ne rien
perdre, et la référence externe est reprise du champ `reference` si présent.
Les incidents sans référence externe sont signalés dans le rapport final : ils
demandent une reprise manuelle, ce qui est plus sûr qu'une correspondance
inventée.

Usage :
    python -m db.migration_v4_v5              (simulation, aucune écriture)
    python -m db.migration_v4_v5 --appliquer  (écriture réelle)
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DB_V4 = RACINE / "data" / "incidents.db"
DB_V5 = RACINE / "data" / "smartsup.db"

# Correspondance des statuts : l'ancien cycle de vie opérationnel devient un
# état documentaire. « résolu » et « clôturé » se rejoignent : pour nous, la
# documentation est close dans les deux cas.
STATUTS = {
    "ouvert": "signale",
    "en_cours": "en_suivi",
    "resolu": "cloture",
    "cloture": "cloture",
}


def _colonnes(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _table_existe(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def migrer(appliquer: bool = False,
           db_v4: Path = DB_V4, db_v5: Path = DB_V5) -> dict:
    """Migre v4 → v5. Sans `appliquer`, ne fait que compter."""

    rapport = {
        "base_v4_presente": db_v4.exists(),
        "superviseurs": 0, "signatures": 0, "equipes": 0,
        "mailing_lists": 0, "modeles": 0, "incidents": 0,
        "preuves": 0, "communications": 0,
        "sans_reference": [], "avertissements": [],
    }

    if not db_v4.exists():
        rapport["avertissements"].append(
            f"Aucune base v4 trouvée ({db_v4.name}) — rien à migrer. "
            "C'est normal si le module v4 n'a jamais été utilisé en production."
        )
        return rapport

    from db.schema_v5 import init_db, ecrire_attributs
    init_db(db_v5)

    src = sqlite3.connect(str(db_v4))
    src.row_factory = sqlite3.Row
    dst = sqlite3.connect(str(db_v5))
    dst.row_factory = sqlite3.Row

    # Correspondance des identifiants d'une base à l'autre
    map_sup: dict[int, int] = {}
    map_equipe: dict[int, int] = {}

    try:
        # ---------------- Superviseurs ----------------
        # La v4 sépare nom et prénom ; la v5 utilise un libellé unique tel
        # qu'il apparaît dans la signature des communications.
        if _table_existe(src, "superviseurs"):
            cols_sup = _colonnes(src, "superviseurs")
            for r in src.execute("SELECT * FROM superviseurs"):
                rapport["superviseurs"] += 1
                if not appliquer:
                    continue
                prenom = (r["prenom"] if "prenom" in cols_sup else "") or ""
                nom_complet = f"{prenom} {r['nom']}".strip()
                cur = dst.execute(
                    """INSERT OR IGNORE INTO superviseurs (nom, email, actif)
                       VALUES (?,?,?)""",
                    (nom_complet,
                     r["email"] if "email" in cols_sup else None,
                     r["actif"] if "actif" in cols_sup else 1),
                )
                nid = cur.lastrowid or dst.execute(
                    "SELECT id FROM superviseurs WHERE nom = ?", (nom_complet,)
                ).fetchone()["id"]
                map_sup[r["id"]] = nid

        # ---------------- Signatures ----------------
        if _table_existe(src, "signatures"):
            cols = _colonnes(src, "signatures")
            for r in src.execute("SELECT * FROM signatures"):
                rapport["signatures"] += 1
                if not appliquer:
                    continue
                sid = map_sup.get(r["superviseur_id"])
                if not sid:
                    continue
                contenu = ""
                for c in ("contenu_html", "contenu", "html"):
                    if c in cols and r[c]:
                        contenu = r[c]
                        break
                dst.execute(
                    """INSERT OR IGNORE INTO signatures
                       (superviseur_id, langue, contenu_html) VALUES (?,?,?)""",
                    (sid, r["langue"] if "langue" in cols else "fr", contenu),
                )

        # ---------------- Équipes ----------------
        for table in ("equipes_tmc", "equipes"):
            if not _table_existe(src, table):
                continue
            cols = _colonnes(src, table)
            for r in src.execute(f"SELECT * FROM {table}"):
                rapport["equipes"] += 1
                if not appliquer:
                    continue
                code = r["code"] if "code" in cols else str(r["nom"])[:40].upper()
                cur = dst.execute(
                    "INSERT OR IGNORE INTO equipes (code, nom) VALUES (?,?)",
                    (code, r["nom"]),
                )
                nid = cur.lastrowid or dst.execute(
                    "SELECT id FROM equipes WHERE code = ?", (code,)
                ).fetchone()["id"]
                map_equipe[r["id"]] = nid
            break

        # ---------------- Listes de diffusion ----------------
        if _table_existe(src, "mailing_lists"):
            cols = _colonnes(src, "mailing_lists")
            for r in src.execute("SELECT * FROM mailing_lists"):
                rapport["mailing_lists"] += 1
                if not appliquer:
                    continue
                # Le champ destination (à/cc) n'existe pas en v4 : tout part
                # en « à » par défaut, à réajuster dans l'administration.
                dst.execute(
                    """INSERT INTO mailing_lists
                       (libelle, adresse, canal, destination, equipe_id, actif)
                       VALUES (?,?,?,?,?,?)""",
                    (r["libelle"] if "libelle" in cols else r["adresse"],
                     r["adresse"],
                     r["canal"] if "canal" in cols else "email",
                     "a",
                     map_equipe.get(r["equipe_tmc_id"]) if "equipe_tmc_id" in cols else None,
                     r["actif"] if "actif" in cols else 1),
                )

        # ---------------- Modèles d'e-mail ----------------
        if _table_existe(src, "email_templates"):
            cols = _colonnes(src, "email_templates")
            for r in src.execute("SELECT * FROM email_templates"):
                rapport["modeles"] += 1
                if not appliquer:
                    continue
                dst.execute(
                    """INSERT OR IGNORE INTO modeles_communication
                       (code, type_incident, canal, type_message, langue,
                        sujet_tpl, corps_tpl)
                       VALUES (?,?,?,?,?,?,?)""",
                    (r["code"] if "code" in cols else f"v4_{r['id']}",
                     "service", "email", "debut",
                     r["langue"] if "langue" in cols else "fr",
                     r["sujet_template"] if "sujet_template" in cols else "",
                     r["corps_template"] if "corps_template" in cols else ""),
                )

        # ---------------- Tickets → Incidents ----------------
        # Point important : la table `tickets` de la v4 ne comporte AUCUNE
        # colonne de référence externe. Le seul identifiant est `numero`
        # (TT-AAAAMMJJ-NNN), fabriqué par l'ancien système — ce n'est pas la
        # référence du ticket groupe.
        #
        # Ces incidents sont donc migrés avec une référence externe VIDE, et
        # le numéro interne est conservé dans les attributs spécifiques. Le
        # rapport final les liste : il faut y coller la vraie référence à la
        # main. Inventer une correspondance serait pire que de la demander.
        if _table_existe(src, "tickets"):
            cols = _colonnes(src, "tickets")

            # Correspondance type d'incident v4 → type structurel v5
            types_v4 = {}
            if _table_existe(src, "types_incident"):
                for t in src.execute("SELECT id, code, categorie FROM types_incident"):
                    code = (t["code"] or "").upper()
                    cat = (t["categorie"] or "").lower()
                    if "RAN" in code or "ran" in cat:
                        types_v4[t["id"]] = "ran"
                    elif "NBN" in code or "nbn" in cat:
                        types_v4[t["id"]] = "nbn"
                    else:
                        types_v4[t["id"]] = "service"

            for r in src.execute("SELECT * FROM tickets"):
                rapport["incidents"] += 1

                numero = r["numero"] if "numero" in cols else None

                # Une vraie référence a pu être saisie dans un champ libre
                # (description ou observation) : on la cherche avant de
                # conclure qu'elle est absente.
                ref = ""
                import re as _re
                for champ in ("description", "observation", "cause"):
                    if champ in cols and r[champ]:
                        trouve = _re.search(r"\d{4}[A-Za-z]\d{5}", str(r[champ]))
                        if trouve:
                            ref = trouve.group(0).upper()
                            break

                if not ref:
                    rapport["sans_reference"].append(numero or f"id={r['id']}")

                if not appliquer:
                    continue

                # Attributs spécifiques : rien de ce que portait la v4 n'est
                # perdu, même ce qui n'a pas de colonne dédiée en v5.
                attrs = {}
                if numero:
                    attrs["numero_interne_v4"] = numero
                for champ, cle in (("lien_impacte", "liens_impactes"),
                                   ("zone_impactee", "zone"),
                                   ("criticite", "criticite"),
                                   ("mode", "mode_v4"),
                                   ("preuve_type", "preuve_type"),
                                   ("preuve_url", "preuve_url"),
                                   ("preuve_note", "preuve_note")):
                    if champ in cols and r[champ]:
                        attrs[cle] = r[champ]

                type_v5 = types_v4.get(
                    r["type_incident_id"] if "type_incident_id" in cols else None,
                    "service")
                # Le mode de saisie v4 est un indice plus fiable que le type
                if "mode" in cols and (r["mode"] or "") == "ran_nbn":
                    type_v5 = "nbn" if attrs.get("liens_impactes") else "ran"

                statut = STATUTS.get(
                    (r["statut"] if "statut" in cols else "") or "", "signale")

                cur = dst.execute(
                    """INSERT INTO incidents
                       (reference_externe, type_incident, priorite, langue,
                        description, date_debut, date_fin, cause, action,
                        observation, perimetre_libre, attributs_specifiques,
                        statut_documentaire, superviseur_id, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (ref,
                     type_v5,
                     r["priorite"] if "priorite" in cols else None,
                     r["langue"] if "langue" in cols else "fr",
                     (r["description"] if "description" in cols else "") or "",
                     r["hd"] if "hd" in cols else None,
                     r["hf"] if "hf" in cols else None,
                     r["cause"] if "cause" in cols else None,
                     r["action"] if "action" in cols else None,
                     r["observation"] if "observation" in cols else None,
                     r["service"] if "service" in cols else None,
                     ecrire_attributs(attrs),
                     statut,
                     map_sup.get(r["superviseur_id"]) if "superviseur_id" in cols else None,
                     r["created"] if "created" in cols else None),
                )
                incident_id = cur.lastrowid

                # Une preuve v4 (URL ou note) devient une vraie preuve v5
                if "preuve_url" in cols and r["preuve_url"]:
                    dst.execute(
                        """INSERT INTO incident_evidences
                           (incident_id, type, contenu, legende) VALUES (?,?,?,?)""",
                        (incident_id, "lien", r["preuve_url"],
                         r["preuve_note"] if "preuve_note" in cols else None))
                    rapport["preuves"] = rapport.get("preuves", 0) + 1
                elif "preuve_note" in cols and r["preuve_note"]:
                    dst.execute(
                        """INSERT INTO incident_evidences
                           (incident_id, type, contenu) VALUES (?,?,?)""",
                        (incident_id, "note", r["preuve_note"]))
                    rapport["preuves"] = rapport.get("preuves", 0) + 1

                # Communications déjà journalisées en v4
                if _table_existe(src, "ticket_comms"):
                    cc = _colonnes(src, "ticket_comms")
                    for m in src.execute(
                        "SELECT * FROM ticket_comms WHERE ticket_id = ?", (r["id"],)
                    ):
                        dst.execute(
                            """INSERT INTO incident_communications
                               (incident_id, canal, type_message, sujet,
                                destinataires_a, envoye_at)
                               VALUES (?,?,?,?,?,?)""",
                            (incident_id,
                             m["canal"] if "canal" in cc else "email",
                             m["type_message"] if "type_message" in cc else "debut",
                             m["sujet"] if "sujet" in cc else "",
                             m["destinataires"] if "destinataires" in cc else "",
                             m["envoye_at"] if "envoye_at" in cc else None))
                        rapport["communications"] = rapport.get("communications", 0) + 1

        # ---------------- Journal d'envois ----------------
        journal = RACINE / "sent_log.jsonl"
        if journal.exists() and appliquer:
            nb = 0
            for ligne in journal.read_text(encoding="utf-8").splitlines():
                if not ligne.strip():
                    continue
                try:
                    e = json.loads(ligne)
                except json.JSONDecodeError:
                    continue
                nb += 1
            rapport["avertissements"].append(
                f"{nb} entrée(s) dans sent_log.jsonl : conservées telles quelles. "
                "Elles ne sont pas rattachables à un incident sans référence "
                "commune fiable — reprise à faire au cas par cas si nécessaire."
            )

        if appliquer:
            dst.commit()

    finally:
        src.close()
        dst.close()

    return rapport


def _afficher(rapport: dict, appliquer: bool) -> None:
    titre = "MIGRATION APPLIQUÉE" if appliquer else "SIMULATION (aucune écriture)"
    print("=" * 68)
    print(f"  {titre}")
    print("=" * 68)
    if not rapport["base_v4_presente"]:
        for a in rapport["avertissements"]:
            print(f"  {a}")
        return

    for cle, libelle in [
        ("superviseurs", "Superviseurs"), ("signatures", "Signatures"),
        ("equipes", "Équipes"), ("mailing_lists", "Listes de diffusion"),
        ("modeles", "Modèles d'e-mail"), ("incidents", "Tickets → incidents"),
        ("preuves", "Preuves reprises"), ("communications", "Communications reprises"),
    ]:
        print(f"  {libelle:24} {rapport[cle]}")

    if rapport["sans_reference"]:
        print()
        print(f"  ATTENTION — {len(rapport['sans_reference'])} incident(s) sans "
              "référence externe :")
        for n in rapport["sans_reference"][:10]:
            print(f"      · {n}")
        print("    Ces incidents sont migrés avec une référence vide.")
        print("    Il faut y coller la référence du ticket groupe à la main.")

    for a in rapport["avertissements"]:
        print(f"\n  {a}")


if __name__ == "__main__":
    sys.path.insert(0, str(RACINE))
    appliquer = "--appliquer" in sys.argv
    _afficher(migrer(appliquer=appliquer), appliquer)
    if not appliquer:
        print("\n  Relancer avec --appliquer pour écrire réellement.")
