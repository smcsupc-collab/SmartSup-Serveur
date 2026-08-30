"""
Validation du schéma v5 sur les incidents réels issus des 8 e-mails analysés.

Objectif : vérifier que le modèle absorbe SANS ADAPTATION les quatre cas
opérationnels observés — un incident service, un incident RAN multi-sites,
un incident NBN multi-liens, et un signalement libre vers un partenaire
externe — ainsi que le cas de la régularisation.

Si un de ces cas ne rentre pas dans le modèle, mieux vaut le découvrir ici
que trois chantiers plus tard.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.schema import get_conn, init_db, ecrire_attributs, lire_attributs  # noqa: E402


def _service_id(conn, domaine: str, service: str) -> int | None:
    row = conn.execute(
        """SELECT s.id FROM services s
           JOIN domaines d ON d.id = s.domaine_id
           WHERE d.nom = ? AND s.nom = ?""",
        (domaine, service),
    ).fetchone()
    return row["id"] if row else None


def _creer_incident(conn, **champs) -> int:
    services = champs.pop("services", [])
    cur = conn.execute(
        """INSERT INTO incidents
           (reference_externe, type_incident, priorite, langue, description,
            date_debut, date_fin, cause, action, observation, perimetre_libre,
            attributs_specifiques, statut_documentaire, superviseur_id)
           VALUES (:reference_externe, :type_incident, :priorite, :langue,
                   :description, :date_debut, :date_fin, :cause, :action,
                   :observation, :perimetre_libre, :attributs_specifiques,
                   :statut_documentaire, :superviseur_id)""",
        {
            "priorite": None, "langue": "fr", "date_debut": None, "date_fin": None,
            "cause": None, "action": None, "observation": None,
            "perimetre_libre": None, "attributs_specifiques": "{}",
            "statut_documentaire": "cloture", "superviseur_id": None,
            **champs,
        },
    )
    incident_id = cur.lastrowid
    for sid in services:
        if sid:
            conn.execute(
                "INSERT OR IGNORE INTO incident_services VALUES (?,?)",
                (incident_id, sid),
            )
    return incident_id


def main() -> None:
    init_db()
    conn = get_conn()

    with conn:
        # Superviseurs observés dans les signatures des mails réels
        for nom, email in [
            ("Mohamed SYLLA", "mohamed.sylla@orange-sonatel.com"),
            ("Abdourahmane BARRY", "abdourahmane.barry@orange-sonatel.com"),
            ("Youssouf SYLLA", "youssouf.sylla@orange-sonatel.com"),
        ]:
            conn.execute(
                "INSERT OR IGNORE INTO superviseurs (nom, email) VALUES (?,?)",
                (nom, email),
            )
        sup = conn.execute("SELECT id FROM superviseurs LIMIT 1").fetchone()["id"]

        # ---- CAS 1 : incident SERVICE (Orange Money B2W / NSIA) ----
        sid = _service_id(conn, "OM Bank to Wallet", "NSIA - B2W")
        i1 = _creer_incident(
            conn,
            reference_externe="2512Q12086",
            type_incident="service",
            priorite="P1",
            description="Orange Money add-on / Bank to Wallet / NSIA",
            date_debut="2025-12-31 08:37",
            date_fin="2025-12-31 12:00",
            cause="Souci de communication avec CBA",
            action="En attente du retour du partenaire",
            observation="Service disponible",
            superviseur_id=sup,
            services=[sid],
        )

        # ---- CAS 2 : incident RAN (coupure site + 58 sites rattachés) ----
        i2 = _creer_incident(
            conn,
            reference_externe="2605H66227",
            type_incident="ran",
            priorite="P1",
            description="Coupure du site BB2BOF20074_BOFFA-THIA + 58 sites rattachés",
            date_debut="2026-05-11 10:52",
            date_fin="2026-05-11 15:18",
            cause="Double coupure de la fibre Labe-Thianguelbore et Kipe-Dubreka côté SOGEB",
            action="Soudure de fibre",
            observation="Sites UP",
            perimetre_libre="VOIX, DATA, SMS, USSD",
            attributs_specifiques=ecrire_attributs({
                "site_id": "BB2BOF20074_BOFFA-THIA",
                "sites_rattaches": 58,
                "nature": "coupure",
            }),
            superviseur_id=sup,
        )

        # ---- CAS 3 : incident NBN (4 liens impactés) ----
        i3 = _creer_incident(
            conn,
            reference_externe="2605H45436",
            type_incident="nbn",
            priorite="P1",
            description="NBN KIPE-BOKE / SONFONIA-FRIA / BOKE-SANGAREDI / BOKE-GOBIRE",
            date_debut="2026-05-11 10:52",
            date_fin="2026-05-11 15:18",
            cause="Coupure de fibre d'un brin sur la liaison Labe-Thianguelbore",
            action="Soudure de fibre",
            observation="Liens UP",
            attributs_specifiques=ecrire_attributs({
                "liens_impactes": [
                    "NBN KIPE-BOKE", "NBN SONFONIA-FRIA",
                    "NBN BOKE-SANGAREDI", "NBN BOKE-GOBIRE",
                ],
                "reference_sujet_divergente": "2605H66227",
            }),
            superviseur_id=sup,
        )

        # ---- CAS 4 : signalement LIBRE en anglais vers partenaire externe ----
        sid_vista = _service_id(conn, "OM Bank to Wallet", "VistaGUI")
        i4 = _creer_incident(
            conn,
            reference_externe="2608N70939",
            type_incident="libre",
            priorite="P1",
            langue="en",
            description="Orange Money add-on / Bank to Wallet / VistaGui",
            date_debut="2026-08-06 10:55",
            statut_documentaire="en_suivi",
            attributs_specifiques=ecrire_attributs({
                "partenaire": "VistaGui",
                "contact_externe": "Vista Bank Group",
            }),
            superviseur_id=sup,
            services=[sid_vista],
        )

        # ---- CAS 5 : régularisation (avis de fin réémis a posteriori) ----
        i5 = _creer_incident(
            conn,
            reference_externe="2605L05006",
            type_incident="nbn",
            priorite="P1",
            description="NBN Kipé to Siatourou",
            date_debut="2026-05-20 22:10",
            date_fin="2026-05-21 07:10",
            cause="Problème d'énergie sur le site de BEY22890_RIO-TINTO-TCC",
            action="En attente du retour du GNOC",
            observation="Lien UP",
            statut_documentaire="regularise",
            attributs_specifiques=ecrire_attributs({
                "liens_impactes": ["NBN Kipé to Siatourou"],
            }),
            superviseur_id=sup,
        )

        # Communications : le cas de régularisation en génère DEUX pour un
        # même incident (l'avis de fin initial, puis sa régularisation).
        conn.execute(
            """INSERT INTO incident_communications
               (incident_id, canal, type_message, destinataires_a, sujet, envoye_at)
               VALUES (?,?,?,?,?,?)""",
            (i5, "email", "fin", "Remontees.reseau.GConakry@orange-sonatel.com",
             "Avis de fin d'incident: NBN Kipé to Siatourou || 2605L05006",
             "2026-05-21 07:20"),
        )
        conn.execute(
            """INSERT INTO incident_communications
               (incident_id, canal, type_message, destinataires_a, sujet, envoye_at)
               VALUES (?,?,?,?,?,?)""",
            (i5, "email", "regularisation", "Remontees.reseau.GConakry@orange-sonatel.com",
             "[Régularisation] Avis de fin d'incident: NBN Kipé to Siatourou || 2605L05006",
             "2026-05-21 14:53"),
        )

        # Preuves : les deux signalements libres portaient des captures.
        conn.execute(
            """INSERT INTO incident_evidences (incident_id, type, chemin, legende)
               VALUES (?,?,?,?)""",
            (i4, "capture", "preuves/2608N70939_01.png",
             "Copie d'écran de l'erreur de transaction"),
        )

    # ------------------------------------------------------------------
    #  Restitution
    # ------------------------------------------------------------------
    print("=" * 76)
    print("VALIDATION DU SCHÉMA SUR LES INCIDENTS RÉELS")
    print("=" * 76)

    for row in conn.execute(
        """SELECT i.*, 
                  (SELECT COUNT(*) FROM incident_services x WHERE x.incident_id = i.id) AS nb_services,
                  (SELECT COUNT(*) FROM incident_evidences e WHERE e.incident_id = i.id) AS nb_preuves,
                  (SELECT COUNT(*) FROM incident_communications c WHERE c.incident_id = i.id) AS nb_comms
           FROM incidents i ORDER BY i.id"""
    ):
        attrs = lire_attributs(row["attributs_specifiques"])
        duree = ""
        if row["date_debut"] and row["date_fin"]:
            from datetime import datetime
            d1 = datetime.fromisoformat(row["date_debut"])
            d2 = datetime.fromisoformat(row["date_fin"])
            mn = int((d2 - d1).total_seconds() // 60)
            duree = f"  ({mn // 60:02d}h{mn % 60:02d})"

        print(f"\n[{row['type_incident'].upper():7}] {row['reference_externe']}"
              f"  {row['priorite'] or '--'}  {row['statut_documentaire']}{duree}")
        print(f"    {row['description'][:66]}")
        if row["perimetre_libre"]:
            print(f"    Périmètre libre : {row['perimetre_libre']}")
        if attrs:
            for cle, val in attrs.items():
                affichage = ", ".join(val) if isinstance(val, list) else val
                print(f"    {cle:28} : {str(affichage)[:52]}")
        print(f"    services liés={row['nb_services']}  preuves={row['nb_preuves']}"
              f"  communications={row['nb_comms']}")

    print("\n" + "=" * 76)
    print("AGRÉGATIONS DE REPORTING (ce qui alimentera les 3 rapports)")
    print("=" * 76)

    print("\n  Par type d'incident :")
    for r in conn.execute(
        "SELECT type_incident, COUNT(*) n FROM incidents GROUP BY 1 ORDER BY 2 DESC"
    ):
        print(f"    {r['type_incident']:10} {r['n']}")

    print("\n  Par domaine de service impacté :")
    for r in conn.execute(
        """SELECT d.nom, COUNT(DISTINCT isv.incident_id) n
           FROM incident_services isv
           JOIN services s ON s.id = isv.service_id
           JOIN domaines d ON d.id = s.domaine_id
           GROUP BY d.nom ORDER BY n DESC"""
    ):
        print(f"    {r['nom']:30} {r['n']}")

    print("\n  Durée moyenne de traitement documenté (min) :")
    r = conn.execute(
        """SELECT ROUND(AVG((julianday(date_fin) - julianday(date_debut)) * 1440)) m
           FROM incidents WHERE date_fin IS NOT NULL"""
    ).fetchone()
    print(f"    {r['m']} minutes sur {conn.execute('SELECT COUNT(*) n FROM incidents WHERE date_fin IS NOT NULL').fetchone()['n']} incidents clos")

    conn.close()


if __name__ == "__main__":
    main()
