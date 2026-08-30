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
        if _table_existe(src, "superviseurs"):
            for r in src.execute("SELECT * FROM superviseurs"):
                rapport["superviseurs"] += 1
                if not appliquer:
                    continue
                cur = dst.execute(
                    """INSERT OR IGNORE INTO superviseurs (nom, email, actif)
                       VALUES (?,?,?)""",
                    (r["nom"], r["email"] if "email" in r.keys() else None,
                     r["actif"] if "actif" in r.keys() else 1),
                )
                nid = cur.lastrowid or dst.execute(
                    "SELECT id FROM superviseurs WHERE nom = ?", (r["nom"],)
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
        if _table_existe(src, "tickets"):
            cols = _colonnes(src, "tickets")
            for r in src.execute("SELECT * FROM tickets"):
                rapport["incidents"] += 1

                numero = r["numero"] if "numero" in cols else None
                ref = None
                for c in ("reference", "reference_externe", "ref_externe"):
                    if c in cols and r[c]:
                        ref = str(r[c]).strip()
                        break

                if not ref:
                    rapport["sans_reference"].append(numero or f"id={r['id']}")
                    ref = ""  # laissé vide : reprise manuelle explicite

                if not appliquer:
                    continue

                attrs = {}
                if numero:
                    attrs["numero_interne_v4"] = numero
                for c in ("site", "site_id", "lien_impacte", "zone"):
                    if c in cols and r[c]:
                        attrs[c] = r[c]

                statut = STATUTS.get(
                    (r["statut"] if "statut" in cols else "") or "", "signale"
                )

                dst.execute(
                    """INSERT INTO incidents
                       (reference_externe, type_incident, priorite, description,
                        date_debut, date_fin, cause, action, observation,
                        perimetre_libre, attributs_specifiques,
                        statut_documentaire, superviseur_id, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (ref,
                     "service",
                     r["priorite"] if "priorite" in cols else None,
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
