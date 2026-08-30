"""
SmartSup v4 — Couche API métier
Toutes les opérations CRUD sur la base de données.
Importé par app.py via register_blueprints().
"""

import json
import re
import html as _html
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, jsonify, request, Response
from db.schema import get_conn, DB_PATH

api_v4 = Blueprint("api_v4", __name__)

# ════════════════════════════════════════════════════════════════
# UTILS
# ════════════════════════════════════════════════════════════════
def _rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]

def _gen_ticket_number() -> str:
    """TT-YYYYMMDD-NNN — incrémenté par jour."""
    conn = get_conn()
    today = datetime.now().strftime("%Y%m%d")
    row = conn.execute(
        "SELECT COUNT(*) as n FROM tickets WHERE numero LIKE ?",
        (f"TT-{today}-%",)
    ).fetchone()
    n = (row["n"] or 0) + 1
    conn.close()
    return f"TT-{today}-{n:03d}"

def _log_event(conn, ticket_id: int, type_event: str, desc: str, auteur: str = "système"):
    conn.execute(
        "INSERT INTO ticket_events (ticket_id,type_event,description,auteur) VALUES (?,?,?,?)",
        (ticket_id, type_event, desc, auteur)
    )

def _calc_mttr(hd_str: str, hf_str: str) -> int | None:
    """Retourne la durée en minutes entre HD et HF."""
    try:
        fmt = "%Y-%m-%dT%H:%M"
        d1 = datetime.strptime(hd_str[:16], fmt)
        d2 = datetime.strptime(hf_str[:16], fmt)
        return max(0, int((d2 - d1).total_seconds() / 60))
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# RÉFÉRENTIELS — Types d'incident
# ════════════════════════════════════════════════════════════════
@api_v4.get("/api/v4/types-incident")
def get_types_incident():
    conn = get_conn()
    rows = _rows(conn.execute(
        "SELECT * FROM types_incident WHERE actif=1 ORDER BY categorie,libelle_fr"
    ))
    conn.close()
    return jsonify(rows)

@api_v4.post("/api/v4/types-incident")
def create_type_incident():
    d = request.get_json(force=True)
    required = ["code", "libelle_fr", "libelle_en", "categorie"]
    if not all(d.get(k) for k in required):
        return jsonify({"error": f"Champs requis : {required}"}), 400
    conn = get_conn()
    try:
        conn.execute("""INSERT INTO types_incident
            (code,libelle_fr,libelle_en,categorie,langue,priorite_defaut)
            VALUES (?,?,?,?,?,?)""",
            (d["code"].upper(), d["libelle_fr"], d["libelle_en"],
             d["categorie"], d.get("langue","fr"), d.get("priorite_defaut","P2")))
        conn.commit()
        row = dict(conn.execute(
            "SELECT * FROM types_incident WHERE code=?", (d["code"].upper(),)
        ).fetchone())
        conn.close()
        return jsonify(row), 201
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 409

@api_v4.put("/api/v4/types-incident/<int:tid>")
def update_type_incident(tid):
    d = request.get_json(force=True)
    conn = get_conn()
    conn.execute("""UPDATE types_incident SET
        libelle_fr=COALESCE(?,libelle_fr),
        libelle_en=COALESCE(?,libelle_en),
        categorie=COALESCE(?,categorie),
        langue=COALESCE(?,langue),
        priorite_defaut=COALESCE(?,priorite_defaut),
        actif=COALESCE(?,actif)
        WHERE id=?""",
        (d.get("libelle_fr"), d.get("libelle_en"), d.get("categorie"),
         d.get("langue"), d.get("priorite_defaut"), d.get("actif"), tid))
    conn.commit(); conn.close()
    return jsonify({"status": "ok"})

@api_v4.delete("/api/v4/types-incident/<int:tid>")
def delete_type_incident(tid):
    conn = get_conn()
    conn.execute("UPDATE types_incident SET actif=0 WHERE id=?", (tid,))
    conn.commit(); conn.close()
    return jsonify({"status": "ok"})


# ════════════════════════════════════════════════════════════════
# RÉFÉRENTIELS — Équipes TMC
# ════════════════════════════════════════════════════════════════
@api_v4.get("/api/v4/equipes-tmc")
def get_equipes_tmc():
    conn = get_conn()
    rows = _rows(conn.execute(
        "SELECT * FROM equipes_tmc WHERE actif=1 ORDER BY domaine,nom"
    ))
    conn.close()
    return jsonify(rows)

@api_v4.post("/api/v4/equipes-tmc")
def create_equipe_tmc():
    d = request.get_json(force=True)
    if not d.get("code") or not d.get("nom") or not d.get("domaine"):
        return jsonify({"error": "code, nom, domaine requis"}), 400
    conn = get_conn()
    try:
        conn.execute("""INSERT INTO equipes_tmc (code,nom,domaine,email_list,telephone)
            VALUES (?,?,?,?,?)""",
            (d["code"].upper(), d["nom"], d["domaine"],
             d.get("email_list",""), d.get("telephone","")))
        conn.commit()
        row = dict(conn.execute(
            "SELECT * FROM equipes_tmc WHERE code=?", (d["code"].upper(),)
        ).fetchone())
        conn.close()
        return jsonify(row), 201
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 409

@api_v4.put("/api/v4/equipes-tmc/<int:eid>")
def update_equipe_tmc(eid):
    d = request.get_json(force=True)
    conn = get_conn()
    conn.execute("""UPDATE equipes_tmc SET
        nom=COALESCE(?,nom), domaine=COALESCE(?,domaine),
        email_list=COALESCE(?,email_list), telephone=COALESCE(?,telephone),
        actif=COALESCE(?,actif) WHERE id=?""",
        (d.get("nom"), d.get("domaine"), d.get("email_list"),
         d.get("telephone"), d.get("actif"), eid))
    conn.commit(); conn.close()
    return jsonify({"status": "ok"})


# ════════════════════════════════════════════════════════════════
# RÉFÉRENTIELS — Règles de routage
# ════════════════════════════════════════════════════════════════
@api_v4.get("/api/v4/routing-rules")
def get_routing_rules():
    conn = get_conn()
    rows = _rows(conn.execute("""
        SELECT r.*, t.code as type_code, t.libelle_fr, t.langue,
               e.nom as equipe_nom, e.domaine
        FROM routing_rules r
        JOIN types_incident t ON t.id=r.type_incident_id
        JOIN equipes_tmc e ON e.id=r.equipe_tmc_id
        WHERE r.actif=1 ORDER BY t.categorie
    """))
    conn.close()
    return jsonify(rows)

@api_v4.post("/api/v4/routing-rules")
def create_routing_rule():
    d = request.get_json(force=True)
    conn = get_conn()
    conn.execute("""INSERT INTO routing_rules
        (type_incident_id,equipe_tmc_id,niveau_escalade,delai_escalade_min)
        VALUES (?,?,?,?)""",
        (d["type_incident_id"], d["equipe_tmc_id"],
         d.get("niveau_escalade",1), d.get("delai_escalade_min",30)))
    conn.commit(); conn.close()
    return jsonify({"status": "ok"}), 201


# ════════════════════════════════════════════════════════════════
# RÉFÉRENTIELS — Mailing lists
# ════════════════════════════════════════════════════════════════
@api_v4.get("/api/v4/mailing-lists")
def get_mailing_lists():
    conn = get_conn()
    rows = _rows(conn.execute("""
        SELECT m.*, e.nom as equipe_nom, e.domaine
        FROM mailing_lists m
        JOIN equipes_tmc e ON e.id=m.equipe_tmc_id
        ORDER BY e.domaine, m.niveau
    """))
    conn.close()
    return jsonify(rows)

@api_v4.post("/api/v4/mailing-lists")
def create_mailing_list():
    d = request.get_json(force=True)
    if not d.get("equipe_tmc_id") or not d.get("nom") or not d.get("adresses"):
        return jsonify({"error": "equipe_tmc_id, nom, adresses requis"}), 400
    conn = get_conn()
    conn.execute("""INSERT INTO mailing_lists
        (equipe_tmc_id,niveau,nom,adresses,type_canal)
        VALUES (?,?,?,?,?)""",
        (d["equipe_tmc_id"], d.get("niveau",1),
         d["nom"], d["adresses"], d.get("type_canal","email")))
    conn.commit(); conn.close()
    return jsonify({"status": "ok"}), 201

@api_v4.put("/api/v4/mailing-lists/<int:mid>")
def update_mailing_list(mid):
    d = request.get_json(force=True)
    conn = get_conn()
    conn.execute("""UPDATE mailing_lists SET
        nom=COALESCE(?,nom), adresses=COALESCE(?,adresses),
        niveau=COALESCE(?,niveau) WHERE id=?""",
        (d.get("nom"), d.get("adresses"), d.get("niveau"), mid))
    conn.commit(); conn.close()
    return jsonify({"status": "ok"})

@api_v4.delete("/api/v4/mailing-lists/<int:mid>")
def delete_mailing_list(mid):
    conn = get_conn()
    conn.execute("DELETE FROM mailing_lists WHERE id=?", (mid,))
    conn.commit(); conn.close()
    return jsonify({"status": "ok"})


# ════════════════════════════════════════════════════════════════
# SUPERVISEURS & SIGNATURES
# ════════════════════════════════════════════════════════════════
@api_v4.get("/api/v4/superviseurs")
def get_superviseurs():
    conn = get_conn()
    rows = _rows(conn.execute(
        "SELECT * FROM superviseurs WHERE actif=1 ORDER BY nom,prenom"
    ))
    conn.close()
    return jsonify(rows)

@api_v4.post("/api/v4/superviseurs")
def create_superviseur():
    d = request.get_json(force=True)
    if not d.get("nom") or not d.get("prenom"):
        return jsonify({"error": "nom et prenom requis"}), 400
    conn = get_conn()
    cur = conn.execute("""INSERT INTO superviseurs (nom,prenom,fonction,telephone,email)
        VALUES (?,?,?,?,?)""",
        (d["nom"], d["prenom"], d.get("fonction",""),
         d.get("telephone",""), d.get("email","")))
    sup_id = cur.lastrowid
    # Créer signatures FR et EN par défaut
    for lang in ("fr", "en"):
        conn.execute("""INSERT INTO signatures
            (superviseur_id,langue,nom_affiche,fonction,entite,telephone,email)
            VALUES (?,?,?,?,?,?,?)""",
            (sup_id, lang,
             f"{d['prenom']} {d['nom']}", d.get("fonction",""),
             "Orange Guinée — NOC",
             d.get("telephone",""), d.get("email","")))
    conn.commit(); conn.close()
    return jsonify({"status": "ok", "id": sup_id}), 201

@api_v4.get("/api/v4/signatures")
def get_signatures():
    conn = get_conn()
    rows = _rows(conn.execute("""
        SELECT s.*, sup.nom as sup_nom, sup.prenom as sup_prenom
        FROM signatures s
        JOIN superviseurs sup ON sup.id=s.superviseur_id
        WHERE s.actif=1 ORDER BY sup.nom
    """))
    conn.close()
    return jsonify(rows)

@api_v4.put("/api/v4/signatures/<int:sid>")
def update_signature(sid):
    d = request.get_json(force=True)
    conn = get_conn()
    conn.execute("""UPDATE signatures SET
        nom_affiche=COALESCE(?,nom_affiche),
        fonction=COALESCE(?,fonction),
        entite=COALESCE(?,entite),
        telephone=COALESCE(?,telephone),
        email=COALESCE(?,email)
        WHERE id=?""",
        (d.get("nom_affiche"), d.get("fonction"),
         d.get("entite"), d.get("telephone"), d.get("email"), sid))
    conn.commit(); conn.close()
    return jsonify({"status": "ok"})


# ════════════════════════════════════════════════════════════════
# MODÈLES D'E-MAIL
# ════════════════════════════════════════════════════════════════
_VAR_RE = re.compile(r"\{\{(\w+)\}\}")

def _render_template(template_str: str, ctx: dict) -> str:
    """Remplace {{variable}} par les valeurs du contexte."""
    return _VAR_RE.sub(lambda m: str(ctx.get(m.group(1), f"[{m.group(1)}]")), template_str)

@api_v4.get("/api/v4/email-templates")
def get_email_templates():
    conn = get_conn()
    rows = _rows(conn.execute(
        "SELECT * FROM email_templates WHERE actif=1 ORDER BY langue,nom"
    ))
    conn.close()
    return jsonify(rows)

@api_v4.post("/api/v4/email-templates")
def create_email_template():
    d = request.get_json(force=True)
    if not all(d.get(k) for k in ["code","nom","sujet_template","corps_template"]):
        return jsonify({"error": "code, nom, sujet_template, corps_template requis"}), 400
    conn = get_conn()
    try:
        conn.execute("""INSERT INTO email_templates
            (code,langue,type_incident_id,nom,sujet_template,corps_template)
            VALUES (?,?,?,?,?,?)""",
            (d["code"].upper(), d.get("langue","fr"),
             d.get("type_incident_id"), d["nom"],
             d["sujet_template"], d["corps_template"]))
        conn.commit(); conn.close()
        return jsonify({"status": "ok"}), 201
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 409

@api_v4.put("/api/v4/email-templates/<int:tid>")
def update_email_template(tid):
    d = request.get_json(force=True)
    conn = get_conn()
    conn.execute("""UPDATE email_templates SET
        nom=COALESCE(?,nom), langue=COALESCE(?,langue),
        sujet_template=COALESCE(?,sujet_template),
        corps_template=COALESCE(?,corps_template),
        actif=COALESCE(?,actif) WHERE id=?""",
        (d.get("nom"), d.get("langue"), d.get("sujet_template"),
         d.get("corps_template"), d.get("actif"), tid))
    conn.commit(); conn.close()
    return jsonify({"status": "ok"})

@api_v4.post("/api/v4/email-templates/<int:tid>/preview")
def preview_email_template(tid):
    ctx = request.get_json(force=True)
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM email_templates WHERE id=?", (tid,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Template non trouvé"}), 404
    return jsonify({
        "sujet":  _render_template(row["sujet_template"], ctx),
        "corps":  _render_template(row["corps_template"], ctx),
        "langue": row["langue"],
    })


# ════════════════════════════════════════════════════════════════
# TICKETS — CRUD + workflow
# ════════════════════════════════════════════════════════════════
@api_v4.get("/api/v4/tickets")
def get_tickets():
    filters = []
    params  = []
    for col in ("statut","priorite","criticite","mode","superviseur_id","equipe_tmc_id"):
        val = request.args.get(col)
        if val:
            filters.append(f"t.{col}=?"); params.append(val)

    since = request.args.get("depuis")
    if since:
        filters.append("t.created >= ?"); params.append(since)

    where = "WHERE " + " AND ".join(filters) if filters else ""
    limit = min(int(request.args.get("limit", 100)), 500)

    conn = get_conn()
    rows = _rows(conn.execute(f"""
        SELECT t.*,
               ti.libelle_fr as type_libelle, ti.langue as type_langue,
               ti.categorie as type_categorie,
               e.nom as equipe_nom, e.domaine as equipe_domaine,
               s.nom as sup_nom, s.prenom as sup_prenom
        FROM tickets t
        LEFT JOIN types_incident ti ON ti.id=t.type_incident_id
        LEFT JOIN equipes_tmc e    ON e.id=t.equipe_tmc_id
        LEFT JOIN superviseurs s   ON s.id=t.superviseur_id
        {where}
        ORDER BY t.created DESC LIMIT ?
    """, params + [limit]))
    conn.close()
    return jsonify({"tickets": rows, "total": len(rows)})

@api_v4.get("/api/v4/tickets/<numero>")
def get_ticket(numero):
    conn = get_conn()
    row = conn.execute("""
        SELECT t.*,
               ti.libelle_fr, ti.libelle_en, ti.langue as type_langue,
               ti.categorie, e.nom as equipe_nom, e.email_list,
               s.nom as sup_nom, s.prenom as sup_prenom
        FROM tickets t
        LEFT JOIN types_incident ti ON ti.id=t.type_incident_id
        LEFT JOIN equipes_tmc e    ON e.id=t.equipe_tmc_id
        LEFT JOIN superviseurs s   ON s.id=t.superviseur_id
        WHERE t.numero=?
    """, (numero,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Ticket non trouvé"}), 404

    events = _rows(conn.execute(
        "SELECT * FROM ticket_events WHERE ticket_id=? ORDER BY ts", (row["id"],)
    ))
    comms = _rows(conn.execute(
        "SELECT id,canal,groupe,sujet,statut,ts FROM ticket_comms WHERE ticket_id=? ORDER BY ts",
        (row["id"],)
    ))
    conn.close()
    return jsonify({"ticket": dict(row), "events": events, "comms": comms})

@api_v4.post("/api/v4/tickets")
def create_ticket():
    d = request.get_json(force=True)
    required = ["description", "hd"]
    if not all(d.get(k) for k in required):
        return jsonify({"error": "description et hd sont requis"}), 400

    # Déterminer la langue selon le type d'incident
    conn = get_conn()
    langue = "fr"
    equipe_id = d.get("equipe_tmc_id")

    if d.get("type_incident_id"):
        ti = conn.execute(
            "SELECT langue,priorite_defaut FROM types_incident WHERE id=?",
            (d["type_incident_id"],)
        ).fetchone()
        if ti:
            langue = ti["langue"]
            if not d.get("priorite"):
                d["priorite"] = ti["priorite_defaut"]

        # Auto-routing : trouver l'équipe TMC via les règles
        if not equipe_id:
            rule = conn.execute("""
                SELECT equipe_tmc_id FROM routing_rules
                WHERE type_incident_id=? AND actif=1
                ORDER BY niveau_escalade LIMIT 1
            """, (d["type_incident_id"],)).fetchone()
            if rule:
                equipe_id = rule["equipe_tmc_id"]

    numero = _gen_ticket_number()
    cur = conn.execute("""
        INSERT INTO tickets (
            numero,type_incident_id,superviseur_id,equipe_tmc_id,
            statut,priorite,criticite,service,lien_impacte,
            description,cause,action,hd,hf,zone_impactee,observation,
            mode,langue,preuve_type,preuve_url,preuve_note
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (numero,
         d.get("type_incident_id"), d.get("superviseur_id", 1),
         equipe_id,
         "ouvert",
         d.get("priorite","P2"), d.get("criticite","normale"),
         d.get("service",""), d.get("lien_impacte",""),
         d["description"],
         d.get("cause",""), d.get("action",""),
         d["hd"], d.get("hf",""),
         d.get("zone_impactee",""), d.get("observation",""),
         d.get("mode","services"), langue,
         d.get("preuve_type",""), d.get("preuve_url",""),
         d.get("preuve_note","")))
    ticket_id = cur.lastrowid
    _log_event(conn, ticket_id, "creation", f"Ticket {numero} créé", "superviseur")
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "numero": numero, "ticket_id": ticket_id,
                    "langue": langue, "equipe_tmc_id": equipe_id}), 201

@api_v4.put("/api/v4/tickets/<numero>/statut")
def update_ticket_statut(numero):
    d    = request.get_json(force=True)
    stat = d.get("statut")
    valid_stats = ("ouvert","en_cours","resolu","cloture")
    if stat not in valid_stats:
        return jsonify({"error": f"Statut invalide. Valeurs : {valid_stats}"}), 400

    conn = get_conn()
    row = conn.execute("SELECT id,hd FROM tickets WHERE numero=?", (numero,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Ticket non trouvé"}), 404

    updates = {"statut": stat, "updated": datetime.now().isoformat(timespec="seconds")}
    if stat == "cloture" and d.get("hf"):
        mttr = _calc_mttr(row["hd"], d["hf"])
        updates["hf"]           = d["hf"]
        updates["mttr_minutes"] = mttr
    if stat == "en_cours" and d.get("ack_tmc"):
        updates["ack_tmc"] = 1
        updates["ack_at"]  = datetime.now().isoformat(timespec="seconds")

    set_clause = ", ".join(f"{k}=?" for k in updates)
    conn.execute(f"UPDATE tickets SET {set_clause} WHERE numero=?",
                 list(updates.values()) + [numero])
    _log_event(conn, row["id"], "statut_change",
               f"Statut → {stat}", d.get("auteur","superviseur"))
    conn.commit(); conn.close()
    return jsonify({"status": "ok"})

@api_v4.put("/api/v4/tickets/<numero>")
def update_ticket(numero):
    d = request.get_json(force=True)
    conn = get_conn()
    row = conn.execute("SELECT id FROM tickets WHERE numero=?", (numero,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Ticket non trouvé"}), 404
    fields = ["cause","action","hf","zone_impactee","observation",
              "priorite","criticite","preuve_type","preuve_url","preuve_note"]
    updates = {f: d[f] for f in fields if f in d}
    updates["updated"] = datetime.now().isoformat(timespec="seconds")
    set_clause = ", ".join(f"{k}=?" for k in updates)
    conn.execute(f"UPDATE tickets SET {set_clause} WHERE numero=?",
                 list(updates.values()) + [numero])
    _log_event(conn, row["id"], "mise_a_jour", "Ticket mis à jour", d.get("auteur","superviseur"))
    conn.commit(); conn.close()
    return jsonify({"status": "ok"})


# ════════════════════════════════════════════════════════════════
# REPORTING & STATISTIQUES v4
# ════════════════════════════════════════════════════════════════
@api_v4.get("/api/v4/stats")
def get_stats_v4():
    conn = get_conn()

    total   = conn.execute("SELECT COUNT(*) as n FROM tickets").fetchone()["n"]
    ouverts = conn.execute("SELECT COUNT(*) as n FROM tickets WHERE statut='ouvert'").fetchone()["n"]
    en_cours= conn.execute("SELECT COUNT(*) as n FROM tickets WHERE statut='en_cours'").fetchone()["n"]
    resolus = conn.execute("SELECT COUNT(*) as n FROM tickets WHERE statut IN ('resolu','cloture')").fetchone()["n"]

    mttr_row= conn.execute("""
        SELECT AVG(mttr_minutes) as avg_mttr
        FROM tickets WHERE mttr_minutes IS NOT NULL AND mttr_minutes > 0
    """).fetchone()
    avg_mttr = round(mttr_row["avg_mttr"] or 0, 1)

    # Par service
    by_service = _rows(conn.execute("""
        SELECT COALESCE(service,lien_impacte,'—') as svc, COUNT(*) as n
        FROM tickets GROUP BY svc ORDER BY n DESC LIMIT 10
    """))

    # Par superviseur
    by_sup = _rows(conn.execute("""
        SELECT COALESCE(s.nom||' '||s.prenom, 'Inconnu') as sup, COUNT(*) as n
        FROM tickets t LEFT JOIN superviseurs s ON s.id=t.superviseur_id
        GROUP BY t.superviseur_id ORDER BY n DESC
    """))

    # Par type d'incident
    by_type = _rows(conn.execute("""
        SELECT COALESCE(ti.libelle_fr,'Inconnu') as type_inc, COUNT(*) as n
        FROM tickets t LEFT JOIN types_incident ti ON ti.id=t.type_incident_id
        GROUP BY t.type_incident_id ORDER BY n DESC LIMIT 10
    """))

    # Par priorité
    by_prio = _rows(conn.execute("""
        SELECT priorite, COUNT(*) as n FROM tickets GROUP BY priorite ORDER BY priorite
    """))

    # Mensuel (12 derniers mois)
    by_month = _rows(conn.execute("""
        SELECT strftime('%Y-%m', created) as mois, COUNT(*) as n
        FROM tickets
        WHERE created >= date('now','-12 months')
        GROUP BY mois ORDER BY mois
    """))

    conn.close()
    return jsonify({
        "total": total, "ouverts": ouverts,
        "en_cours": en_cours, "resolus": resolus,
        "avg_mttr_minutes": avg_mttr,
        "by_service": by_service, "by_superviseur": by_sup,
        "by_type": by_type, "by_priorite": by_prio,
        "by_month": by_month,
    })

@api_v4.get("/api/v4/tickets/export")
def export_tickets():
    fmt = request.args.get("format","csv")
    conn = get_conn()
    rows = _rows(conn.execute("""
        SELECT t.numero, t.statut, t.priorite, t.criticite,
               ti.libelle_fr as type_incident,
               t.service, t.lien_impacte, t.description,
               t.cause, t.action, t.hd, t.hf, t.mttr_minutes,
               t.zone_impactee, t.observation, t.langue,
               s.nom||' '||s.prenom as superviseur,
               e.nom as equipe_tmc, t.ack_tmc, t.created
        FROM tickets t
        LEFT JOIN types_incident ti ON ti.id=t.type_incident_id
        LEFT JOIN equipes_tmc e    ON e.id=t.equipe_tmc_id
        LEFT JOIN superviseurs s   ON s.id=t.superviseur_id
        ORDER BY t.created DESC
    """))
    conn.close()

    if fmt == "csv":
        import io, csv
        buf = io.StringIO()
        if rows:
            writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return Response(buf.getvalue().encode("utf-8-sig"),
                        mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=tickets_export.csv"})
    return jsonify(rows)
