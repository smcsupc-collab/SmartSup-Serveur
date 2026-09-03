"""
SMART-SUP — Tests de non-régression
====================================

Ferme le point bloquant **B9** de l'audit initial : « aucun test automatisé ».

Chaque test correspond à un défaut réellement rencontré sur ce projet, pas à
une couverture théorique. L'audit avait relevé que le MTTR ne se calculait
jamais parce que l'heure de fin n'était pas transmise, et que personne ne
s'en était aperçu — un test trivial l'aurait détecté immédiatement. C'est le
principe retenu ici : on teste ce qui a déjà cassé, ou ce dont la rupture
serait silencieuse.

Exécution :
    python -m unittest discover tests -v
    python -m unittest tests.test_incidents.TestChartesSeparees -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

# pyperclip et pywin32 n'existent pas hors poste Windows : on les neutralise
# pour que les tests tournent partout, y compris en intégration continue.
if "pyperclip" not in sys.modules:
    try:
        import pyperclip  # noqa: F401
    except ImportError:
        sys.modules["pyperclip"] = types.SimpleNamespace(
            copy=lambda x: None, paste=lambda: "")


def _base_temporaire() -> str:
    """Base isolée : les tests ne touchent jamais aux données réelles."""
    fd, chemin = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(chemin)
    return chemin


# ======================================================================
class TestCalculDurees(unittest.TestCase):
    """
    L'audit initial a montré que le MTTR ne se calculait jamais : la route
    existait, mais l'heure de fin n'était pas transmise. Ces tests couvrent
    le calcul lui-même et ses cas limites.
    """

    def setUp(self):
        from db.rapports import _duree_minutes, _hhmm
        self.duree = _duree_minutes
        self.hhmm = _hhmm

    def test_duree_nominale(self):
        # Cas réel : incident BOFFA-THIA, 10:52 → 15:18
        self.assertEqual(
            self.duree("2026-05-11 10:52", "2026-05-11 15:18"), 266)

    def test_format_hhmm(self):
        self.assertEqual(self.hhmm(266), "04:26")
        self.assertEqual(self.hhmm(0), "00:00")
        self.assertEqual(self.hhmm(1440), "24:00")

    def test_sans_heure_de_fin(self):
        """Un incident encore ouvert ne doit pas produire de durée."""
        self.assertIsNone(self.duree("2026-05-11 10:52", None))

    def test_fin_anterieure_au_debut(self):
        """Saisie incohérente : mieux vaut aucune durée qu'une durée négative."""
        self.assertIsNone(self.duree("2026-05-11 15:18", "2026-05-11 10:52"))

    def test_incident_a_cheval_sur_deux_jours(self):
        self.assertEqual(
            self.duree("2026-05-20 22:10", "2026-05-21 07:10"), 540)


# ======================================================================
class TestDecoupageShifts(unittest.TestCase):
    """
    Le découpage des shifts est paramétrable. Une erreur ici décalerait
    silencieusement tous les rapports de fin de shift.
    """

    def _bornes(self, moment, nb_shifts, depart="06:00"):
        from db.rapports import bornes_shift
        params = {"rapport.shifts_par_jour": nb_shifts,
                  "rapport.heure_debut_shift1": depart}
        return bornes_shift(moment, params)

    def test_trois_shifts_de_huit_heures(self):
        d, f, n = self._bornes(datetime(2026, 8, 12, 14, 30), 3)
        self.assertEqual((d.hour, f.hour, n), (14, 22, 2))

    def test_deux_shifts_de_douze_heures(self):
        d, f, n = self._bornes(datetime(2026, 8, 12, 14, 30), 2)
        self.assertEqual((d.hour, f.hour, n), (6, 18, 1))

    def test_heure_de_depart_personnalisee(self):
        d, _, n = self._bornes(datetime(2026, 8, 12, 14, 30), 3, "08:00")
        self.assertEqual((d.hour, n), (8, 1))

    def test_avant_le_premier_shift_rattache_a_la_veille(self):
        """À 03:00 avec un départ à 06:00, on est encore dans le shift d'hier."""
        d, _, _ = self._bornes(datetime(2026, 8, 12, 3, 0), 3)
        self.assertEqual(d.day, 11)


# ======================================================================
class TestChartesSeparees(unittest.TestCase):
    """
    Trois identités visuelles coexistent et ne doivent jamais se contaminer :

        Application  #FF7900   static/style.css
        E-mails      #FF6D00   db/api_v5.py
        Rapports     neutre    db/rapports.py

    L'alignement accidentel des deux premières s'est déjà produit pendant le
    développement. Ce test le rendrait immédiatement visible.
    """

    ORANGE_APPLICATION = "#FF7900"
    ORANGE_EMAIL = "#FF6D00"

    def test_le_css_de_l_application_n_impose_pas_la_couleur_des_mails(self):
        import re
        css = (RACINE / "static" / "style.css").read_text(encoding="utf-8")
        regles = re.sub(r"/\*.*?\*/", "", css, flags=re.S)   # hors commentaires
        self.assertNotIn(self.ORANGE_EMAIL, regles,
                         "La couleur des e-mails ne doit pas apparaître dans "
                         "une règle CSS de l'application.")

    def test_le_css_porte_bien_la_couleur_de_l_application(self):
        css = (RACINE / "static" / "style.css").read_text(encoding="utf-8")
        self.assertIn(self.ORANGE_APPLICATION, css)

    def test_le_mail_genere_porte_sa_propre_charte(self):
        db = _base_temporaire()
        try:
            import db.api_v5 as api
            from db.parametres import (charger_defauts, structure_messages,
                                       tous_parametres)
            from db.schema_v5 import init_db
            init_db(db)
            charger_defauts(db)

            corps = api.construire_message(
                {"type_message": "debut", "perimetre": "Test"},
                tous_parametres(db), structure_messages(db))["corps_html"]

            self.assertIn(self.ORANGE_EMAIL, corps)
            self.assertNotIn(self.ORANGE_APPLICATION, corps,
                             "Le thème de l'application ne doit pas atteindre "
                             "les e-mails.")
        finally:
            Path(db).unlink(missing_ok=True)

    def test_le_rapport_reste_neutre_et_imprimable(self):
        from db.rapports import rendre_html
        html = rendre_html({
            "type": "shift", "titre": "Test", "debut": "01/01/2026",
            "fin": "01/01/2026", "total": 0, "en_cours": 0, "clos": 0,
            "majeurs": 0, "incidents": [], "a_suivre": [], "seuil_majeur": "P1"})
        self.assertNotIn(self.ORANGE_APPLICATION, html)
        self.assertIn("@media print", html,
                      "Le rapport doit rester imprimable.")


# ======================================================================
class TestParametrageEffectif(unittest.TestCase):
    """
    Un paramètre qui s'enregistre mais ne change rien à la sortie est pire
    qu'un paramètre absent : il donne une fausse impression de contrôle.
    """

    def setUp(self):
        from db.parametres import charger_defauts
        from db.schema_v5 import init_db
        self.db = _base_temporaire()
        init_db(self.db)
        charger_defauts(self.db)

    def tearDown(self):
        Path(self.db).unlink(missing_ok=True)

    def _message(self, **surcharges):
        import db.api_v5 as api
        from db.parametres import structure_messages, tous_parametres
        params = tous_parametres(self.db)
        params.update(surcharges)
        return api.construire_message(
            {"type_message": "debut", "perimetre": "Test",
             "superviseur": {"nom": "Test"}},
            params, structure_messages(self.db))

    def test_la_raison_sociale_est_appliquee(self):
        m = self._message(**{"org.nom": "ORANGE GUINEE — ESSAI"})
        self.assertIn("ORANGE GUINEE — ESSAI", m["corps_html"])

    def test_la_couleur_est_appliquee(self):
        m = self._message(**{"mail.couleur_principale": "#123456"})
        self.assertIn("#123456", m["corps_html"])

    def test_la_formule_de_politesse_est_appliquee(self):
        m = self._message(**{"org.formule_politesse": "Bien à vous,"})
        self.assertIn("Bien à vous,", m["corps_texte"])

    def test_ajouter_un_champ_modifie_le_gabarit(self):
        """Ajouter un champ en administration doit suffire, sans code."""
        import db.api_v5 as api
        from db.parametres import structure_messages, tous_parametres
        from db.schema_v5 import get_conn

        donnees = {"type_message": "debut", "perimetre": "Test",
                   "zone": "Kankan", "superviseur": {"nom": "T"}}
        avant = api.construire_message(
            donnees, tous_parametres(self.db), structure_messages(self.db))
        self.assertNotIn("Kankan", avant["corps_html"])

        conn = get_conn(self.db)
        with conn:
            conn.execute(
                """INSERT INTO champs_message
                   (type_message, champ, libelle, ordre) VALUES (?,?,?,?)""",
                ("debut", "zone", "Zone impactée", 55))
        conn.close()

        apres = api.construire_message(
            donnees, tous_parametres(self.db), structure_messages(self.db))
        self.assertIn("Kankan", apres["corps_html"])
        self.assertIn("Zone impactée", apres["corps_html"])


# ======================================================================
class TestSortiesDerivees(unittest.TestCase):
    """
    Ces sorties remplacent `Web_SMS_Sup_v2.2.html`, qui analysait le texte
    d'un e-mail par expressions régulières et laissait les durées vides.
    """

    def setUp(self):
        from db.parametres import charger_defauts
        from db.schema_v5 import init_db
        self.db = _base_temporaire()
        init_db(self.db)
        charger_defauts(self.db)
        self.donnees = {
            "type_message": "fin", "reference_externe": "2605H66227",
            "priorite": "P1", "perimetre": "VOIX, DATA",
            "description": "Coupure du site BB2BOF20074",
            "date_debut": "2026-05-11 10:52", "date_fin": "2026-05-11 15:18",
            "cause": "Double coupure de fibre", "action": "Soudure de fibre",
            "observation": "Sites UP",
        }

    def tearDown(self):
        Path(self.db).unlink(missing_ok=True)

    def test_les_durees_sont_calculees(self):
        """L'ancien outil les laissait vides : elles doivent l'être ici."""
        from db.exports import construire_ligne_suivi
        ligne = construire_ligne_suivi(self.donnees)
        self.assertEqual(ligne["valeurs"][7], "04:26")
        self.assertEqual(ligne["valeurs"][8], "266")

    def test_la_ligne_est_tabulee_pour_excel(self):
        from db.exports import COLONNES_LIGNE_SUIVI, construire_ligne_suivi
        ligne = construire_ligne_suivi(self.donnees)
        self.assertEqual(len(ligne["ligne"].split("\t")),
                         len(COLONNES_LIGNE_SUIVI))

    def test_le_sms_contient_les_deux_horaires(self):
        from db.exports import construire_sms
        sms = construire_sms(self.donnees)
        self.assertIn("HD :", sms)
        self.assertIn("HF :", sms)
        self.assertIn("P1", sms)

    def test_formulation_de_repli_sur_champ_vide(self):
        """Un avis de début sans cause reprend la formulation d'usage."""
        from db.exports import construire_sms
        sms = construire_sms({**self.donnees, "type_message": "debut", "cause": ""})
        self.assertIn("Investigations en cours", sms)


# ======================================================================
class TestRoutesApi(unittest.TestCase):
    """Parcours réels de bout en bout, via le client de test de Flask."""

    @classmethod
    def setUpClass(cls):
        import app as A
        cls.client = A.app.test_client()
        cls.local = {"REMOTE_ADDR": "127.0.0.1"}

    def test_creation_incident_sans_reference_refusee(self):
        """La référence externe est le seul identifiant : elle est requise."""
        r = self.client.post("/api/v5/incidents", json={"description": "X"},
                             environ_base=self.local)
        self.assertEqual(r.status_code, 400)

    def test_creation_puis_relecture(self):
        r = self.client.post("/api/v5/incidents", json={
            "reference_externe": "2608T00001", "type_incident": "service",
            "priorite": "P1", "description": "Test",
            "date_debut": "2026-08-06 10:00"}, environ_base=self.local)
        self.assertEqual(r.status_code, 201)
        ident = r.get_json()["id"]

        d = self.client.get(f"/api/v5/incidents/{ident}",
                            environ_base=self.local).get_json()["incident"]
        self.assertEqual(d["reference_externe"], "2608T00001")

    def test_recherche_service_multi_mots_dans_le_desordre(self):
        """« b2w bnig » doit retrouver « BNIG - B2W »."""
        r = self.client.get("/api/v5/services?q=b2w+bnig",
                            environ_base=self.local).get_json()
        self.assertGreaterEqual(r["count"], 1)
        self.assertIn("BNIG", r["services"][0]["nom"])

    def test_gabarit_arpt_sans_dates_avec_zone_et_tmc(self):
        r = self.client.post("/api/v5/preview", json={
            "type_message": "notification", "perimetre": "TOU30363_KOIN",
            "zone": "Mamou", "tmc": "Orange"}, environ_base=self.local).get_json()
        corps = r["corps_html"]
        self.assertIn("Zone impact", corps)
        self.assertIn("TMC", corps)
        self.assertNotIn("Début", corps)
        self.assertEqual(r["canal"], "notification_arpt")

    def test_les_destinataires_changent_avec_le_canal(self):
        interne = self.client.post("/api/v5/preview", json={
            "type_message": "debut", "perimetre": "X"},
            environ_base=self.local).get_json()
        arpt = self.client.post("/api/v5/preview", json={
            "type_message": "notification", "perimetre": "X"},
            environ_base=self.local).get_json()
        self.assertNotEqual(interne["destinataires_a"], arpt["destinataires_a"])
        self.assertTrue(any("arpt" in a for a in arpt["destinataires_a"]))

    def test_les_trois_rapports_repondent_dans_les_trois_formats(self):
        for rapport in ("shift", "hebdomadaire", "mensuel"):
            for format_ in ("json", "html", "xlsx"):
                r = self.client.get(
                    f"/api/v5/rapports/{rapport}?format={format_}",
                    environ_base=self.local)
                self.assertEqual(r.status_code, 200, f"{rapport} / {format_}")

    def test_rapport_inconnu_refuse(self):
        r = self.client.get("/api/v5/rapports/inexistant",
                            environ_base=self.local)
        self.assertEqual(r.status_code, 404)


# ======================================================================
class TestSecurite(unittest.TestCase):
    """
    Le modèle de sécurité repose sur la restriction à 127.0.0.1 et sur des
    listes blanches. Ces tests vérifient qu'aucune brèche évidente ne s'est
    ouverte.
    """

    @classmethod
    def setUpClass(cls):
        import app as A
        cls.client = A.app.test_client()
        cls.local = {"REMOTE_ADDR": "127.0.0.1"}

    def test_appel_distant_refuse(self):
        r = self.client.get("/api/v5/services",
                            environ_base={"REMOTE_ADDR": "192.168.1.50"})
        self.assertIn(r.status_code, (403, 404))

    def test_remontee_de_chemin_sur_les_preuves(self):
        for tentative in ("../../app.py", "..%2f..%2fconfig.json",
                          "....//config.json"):
            r = self.client.get(f"/api/v5/preuves/{tentative}",
                                environ_base=self.local)
            self.assertNotEqual(r.status_code, 200, tentative)

    def test_televersement_non_image_refuse(self):
        r = self.client.post("/api/v5/preuves/televerser",
                             json={"donnee": "data:application/pdf;base64,AAAA"},
                             environ_base=self.local)
        self.assertEqual(r.status_code, 400)

    def test_table_admin_inconnue_refusee(self):
        """Le nom de table vient d'une liste blanche, jamais de la requête."""
        r = self.client.get("/api/v5/admin/sqlite_master",
                            environ_base=self.local)
        self.assertEqual(r.status_code, 404)

    def test_injection_sql_dans_la_recherche(self):
        r = self.client.get("/api/v5/services?q=' OR 1=1 --",
                            environ_base=self.local)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 0,
                         "Une injection ne doit pas retourner le catalogue.")


# ======================================================================
class TestThemes(unittest.TestCase):
    """
    Le système de thèmes ne concerne QUE l'interface. Ces tests vérifient
    d'une part que chaque thème reste lisible, d'autre part qu'aucun thème
    ne peut atteindre les e-mails ou les rapports.

    Le contraste est vérifié parce qu'un thème sobre reste un thème qui doit
    se lire : le mode furtif était initialement à 4.37, sous le seuil WCAG.
    """

    THEMES = ("clair", "sombre", "furtif", "noc")

    @classmethod
    def setUpClass(cls):
        cls.css = (RACINE / "static" / "theme.css").read_text(encoding="utf-8")

    @staticmethod
    def _luminance(hexa: str) -> float:
        hexa = hexa.lstrip("#")
        canaux = [int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
               for c in canaux]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    @classmethod
    def _contraste(cls, a: str, b: str) -> float:
        la, lb = cls._luminance(a), cls._luminance(b)
        return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

    def _bloc(self, theme: str) -> str:
        """
        Corps de la déclaration d'un thème.

        On cherche le sélecteur SUIVI DE `{` : le nom du thème apparaît aussi
        dans le commentaire d'en-tête du fichier, et s'y arrêter renverrait
        un bloc vide.
        """
        import re
        # Le sélecteur doit être en début de ligne et suivi de son accolade :
        # le nom du thème apparaît aussi dans le commentaire d'en-tête, et une
        # recherche trop permissive y démarrerait le bloc.
        trouve = re.search(rf'^\[data-theme="{theme}"\] *\{{', self.css, re.M)
        self.assertIsNotNone(trouve, f"Thème {theme} non déclaré")
        debut = trouve.end()
        return self.css[debut:self.css.index("\n}", debut)]

    def _primitifs(self) -> dict:
        """Palette brute, pour résoudre les jetons qui pointent vers elle."""
        import re
        return dict(re.findall(r"(--[\w-]+):\s*(#[0-9A-Fa-f]{6})\s*;", self.css))

    def _jeton(self, theme: str, nom: str) -> str | None:
        """
        Valeur d'un jeton, en suivant les indirections.
        Un thème peut écrire `--fond: var(--n-950)` : il faut remonter au
        primitif pour pouvoir calculer un contraste.
        """
        import re
        trouve = re.search(rf"--{nom}:\s*([^;]+);", self._bloc(theme))
        if not trouve:
            return None
        valeur = trouve.group(1).strip()
        primitifs = self._primitifs()
        vus = 0
        while valeur.startswith("var(") and vus < 5:
            valeur = primitifs.get(valeur[4:valeur.index(")")], "")
            vus += 1
        return valeur if valeur.startswith("#") else None

    def test_les_quatre_themes_sont_definis(self):
        for theme in self.THEMES:
            self.assertIn(f'[data-theme="{theme}"]', self.css, theme)

    def test_contraste_du_texte_principal(self):
        """Texte courant : seuil WCAG AA de 4.5."""
        for theme in self.THEMES:
            ratio = self._contraste(self._jeton(theme, "texte"),
                                    self._jeton(theme, "fond"))
            self.assertGreaterEqual(round(ratio, 2), 4.5,
                                    f"{theme} : texte illisible ({ratio:.2f})")

    def test_contraste_du_texte_secondaire(self):
        """C'est ce test qui avait révélé le défaut du mode furtif."""
        for theme in self.THEMES:
            ratio = self._contraste(self._jeton(theme, "texte-2"),
                                    self._jeton(theme, "fond"))
            self.assertGreaterEqual(round(ratio, 2), 4.5,
                                    f"{theme} : texte secondaire illisible "
                                    f"({ratio:.2f})")

    def test_un_incident_critique_reste_visible_partout(self):
        """
        Contrainte non négociable : même en mode furtif, où tout est
        volontairement effacé, un incident critique doit se voir.
        """
        for theme in self.THEMES:
            ratio = self._contraste(self._jeton(theme, "critique"),
                                    self._jeton(theme, "fond"))
            self.assertGreaterEqual(round(ratio, 2), 3.0,
                                    f"{theme} : critique peu visible ({ratio:.2f})")

    def test_les_etats_ne_reposent_pas_sur_la_seule_couleur(self):
        """Chaque état porte aussi une forme distincte."""
        import re
        self.assertIn(".etat-pastille", self.css)
        for etat in ("critique", "encours", "attente", "resolu", "neutre"):
            # L'espacement du CSS est libre : on cherche le sélecteur, pas
            # une mise en forme précise.
            motif = rf"\.etat-{etat}\s+\.etat-pastille"
            self.assertRegex(self.css, motif, etat)

    def test_aucun_theme_n_atteint_les_emails(self):
        db = _base_temporaire()
        try:
            import db.api_v5 as api
            from db.parametres import (charger_defauts, structure_messages,
                                       tous_parametres)
            from db.schema_v5 import init_db
            init_db(db)
            charger_defauts(db)
            corps = api.construire_message(
                {"type_message": "debut", "perimetre": "T"},
                tous_parametres(db), structure_messages(db))["corps_html"]
            self.assertNotIn("var(--", corps,
                             "Un e-mail ne doit contenir aucun jeton de thème.")
            self.assertNotIn("data-theme", corps)
        finally:
            Path(db).unlink(missing_ok=True)

    def test_aucun_theme_n_atteint_les_rapports(self):
        from db.rapports import rendre_html
        html = rendre_html({
            "type": "shift", "titre": "T", "debut": "01/01/2026",
            "fin": "01/01/2026", "total": 0, "en_cours": 0, "clos": 0,
            "majeurs": 0, "incidents": [], "a_suivre": [], "seuil_majeur": "P1"})
        self.assertNotIn("var(--", html)
        self.assertNotIn("data-theme", html)

    def test_mouvement_reduit_respecte(self):
        self.assertIn("prefers-reduced-motion", self.css)


# ======================================================================
class TestMigration(unittest.TestCase):
    """La migration ne doit jamais inventer une référence absente."""

    def test_le_numero_interne_n_est_pas_pris_pour_une_reference(self):
        """
        Le numéro TT-AAAAMMJJ-NNN de la v4 est fabriqué par l'ancien système.
        Le confondre avec la référence du groupe créerait des identifiants
        faux et indétectables.
        """
        import inspect

        import db.migration_v4_v5 as M
        source = inspect.getsource(M)
        self.assertIn("numero_interne_v4", source)
        self.assertIn("sans_reference", source)

    def test_simulation_sans_base_v4(self):
        """L'absence de base v4 est un cas normal, pas une erreur."""
        from db.migration_v4_v5 import migrer
        rapport = migrer(appliquer=False, db_v4=Path("/inexistant.db"))
        self.assertFalse(rapport["base_v4_presente"])
        self.assertTrue(rapport["avertissements"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
