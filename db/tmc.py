"""
SmartSup v4 — Module TMC (Technical Management Center)
Gestion de la signalisation back-office :
 - Génération d'e-mails bilingues (FR/EN)
 - Envoi via Outlook COM (avec fallback EML)
 - Règles de routage automatique
 - Gestion des pièces jointes (screenshot, URL, note de parcours)
"""

import html as _html
import os, sys, tempfile, time, threading
from datetime import datetime
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from db.schema import get_conn
from db.api import _render_template, _log_event

# ── Palettes et constantes ──────────────────────────────────────────────────
_FONT       = "'Arial', 'Helvetica', sans-serif"
_ORANGE     = "#FF6D00"
_DARK       = "#1A1A1A"
_LIGHT_GREY = "#F5F5F5"
_BORDER     = "#E0E0E0"
_RED        = "#F44336"
_AMBER      = "#FF9800"
_GREEN      = "#4CAF50"
_BLUE       = "#1565C0"

# Priorité → couleur badge
_PRIO_COLOR = {"P1": _RED, "P2": _AMBER, "P3": _GREEN}

# ── Contenu bilingue ────────────────────────────────────────────────────────
_LABELS = {
    "fr": {
        "title_debut":      "AVIS DE DÉBUT D'INCIDENT",
        "title_fin":        "AVIS DE FIN D'INCIDENT",
        "title_avancement": "POINT D'AVANCEMENT",
        "ticket_number":    "N° Ticket",
        "type_incident":    "Type d'incident",
        "description":      "Description",
        "service":          "Service impacté",
        "heure_debut":      "Heure de début",
        "heure_fin":        "Heure de fin",
        "cause":            "Cause identifiée",
        "action":           "Action corrective",
        "superviseur":      "Superviseur",
        "priorite":         "Priorité",
        "criticite":        "Criticité",
        "preuve":           "Élément de preuve",
        "url_test":         "URL de test",
        "note_parcours":    "Note parcours utilisateur",
        "greeting":         "Équipe,",
        "intro_debut":      "Nous vous informons d'un incident en cours nécessitant votre intervention immédiate.",
        "intro_fin":        "Nous vous informons que l'incident décrit ci-dessous a été résolu.",
        "intro_avanc":      "Voici un point d'avancement sur l'incident en cours.",
        "footer":           "Merci de prendre en charge ce ticket et de confirmer votre prise en charge par retour d'e-mail.",
        "footer_fin":       "Merci de clore le ticket dans votre système.",
        "confidentiel":     "Ce message est à usage interne uniquement — Orange Guinée NOC",
    },
    "en": {
        "title_debut":      "INCIDENT OPENING NOTICE",
        "title_fin":        "INCIDENT CLOSURE NOTICE",
        "title_avancement": "INCIDENT STATUS UPDATE",
        "ticket_number":    "Ticket Number",
        "type_incident":    "Incident Type",
        "description":      "Description",
        "service":          "Impacted Service",
        "heure_debut":      "Start Time",
        "heure_fin":        "End Time",
        "cause":            "Root Cause",
        "action":           "Corrective Action",
        "superviseur":      "Supervisor",
        "priorite":         "Priority",
        "criticite":        "Severity",
        "preuve":           "Evidence",
        "url_test":         "Test URL",
        "note_parcours":    "User Journey Note",
        "greeting":         "Team,",
        "intro_debut":      "We are reporting an ongoing incident that requires your immediate attention.",
        "intro_fin":        "We are informing you that the incident described below has been resolved.",
        "intro_avanc":      "Please find below a status update on the ongoing incident.",
        "footer":           "Please acknowledge this ticket and confirm your assignment by reply email.",
        "footer_fin":       "Please close the ticket in your system.",
        "confidentiel":     "This message is for internal use only — Orange Guinea NOC",
    }
}


def _row_html(label: str, value: str, bg: str = "#FFFFFF",
              color: str = "#1A1A1A", bold: bool = False) -> str:
    v_style = f"font-weight:{'bold' if bold else 'normal'};color:{color}"
    return (
        f'<tr>'
        f'<td style="padding:8px 12px;border:1px solid {_BORDER};'
        f'font-family:{_FONT};font-size:12px;font-weight:600;'
        f'background:{_LIGHT_GREY};color:#555;width:35%;white-space:nowrap;">{_html.escape(label)}</td>'
        f'<td style="padding:8px 12px;border:1px solid {_BORDER};'
        f'font-family:{_FONT};font-size:12px;background:{bg};{v_style};">'
        f'{_html.escape(str(value))}</td>'
        f'</tr>'
    )


def _build_html_tmc(ticket: dict, statut_type: str, langue: str,
                    signature: dict | None = None) -> str:
    """Construit le corps HTML de la notification TMC."""
    L = _LABELS.get(langue, _LABELS["fr"])
    t = statut_type  # debut / fin / avancement

    title_key = f"title_{t}" if f"title_{t}" in L else "title_debut"
    intro_key = f"intro_{t[:5]}"  # intro_debut / intro_fin / intro_avan
    footer_key = "footer_fin" if t == "fin" else "footer"

    title     = L.get(title_key, L["title_debut"])
    intro     = L.get(intro_key, L["intro_debut"])
    footer    = L.get(footer_key, L["footer"])

    prio       = ticket.get("priorite", "P2")
    prio_color = _PRIO_COLOR.get(prio, _AMBER)
    service    = ticket.get("service") or ticket.get("lien_impacte") or "—"
    sup_name   = ticket.get("sup_prenom","") + " " + ticket.get("sup_nom","")

    # Pièce jointe / preuve (note dans le corps si pas d'image)
    preuve_html = ""
    if ticket.get("preuve_url"):
        preuve_html = (
            f'<tr><td style="padding:8px 12px;border:1px solid {_BORDER};'
            f'font-family:{_FONT};font-size:12px;font-weight:600;'
            f'background:{_LIGHT_GREY};color:#555;white-space:nowrap;">'
            f'{L["url_test"]}</td>'
            f'<td style="padding:8px 12px;border:1px solid {_BORDER};font-family:{_FONT};font-size:12px;">'
            f'<a href="{_html.escape(ticket["preuve_url"])}">{_html.escape(ticket["preuve_url"])}</a>'
            f'</td></tr>'
        )
    elif ticket.get("preuve_note"):
        preuve_html = _row_html(L["note_parcours"], ticket["preuve_note"])

    # Signature
    if signature:
        sig_html = (
            f'<p style="font-family:{_FONT};font-size:12px;color:#555;margin:0;">'
            f'{_html.escape(signature.get("nom_affiche",""))}<br>'
            f'<span style="color:#888">{_html.escape(signature.get("fonction",""))}</span><br>'
            f'{_html.escape(signature.get("entite","Orange Guinée — NOC"))}<br>'
            f'Tél : {_html.escape(signature.get("telephone",""))}'
            f'</p>'
        )
    else:
        sig_html = f'<p style="font-family:{_FONT};font-size:12px;color:#555;">{_html.escape(sup_name.strip())}<br>Orange Guinée — NOC</p>'

    hf_row = _row_html(L["heure_fin"], ticket.get("hf","—")) if t == "fin" else ""
    cause_row  = _row_html(L["cause"],  ticket.get("cause","—"), bg="#FFF9C4") if ticket.get("cause")  else ""
    action_row = _row_html(L["action"], ticket.get("action","—"), bg="#FFF9C4") if ticket.get("action") else ""

    return f"""<!DOCTYPE html>
<html lang="{langue}">
<head><meta charset="utf-8"><title>{_html.escape(title)}</title></head>
<body style="margin:0;padding:0;background:#F0F0F0;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#F0F0F0;padding:20px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0"
       style="background:#FFFFFF;border-radius:8px;overflow:hidden;
              box-shadow:0 2px 12px rgba(0,0,0,.10);">

  <!-- HEADER -->
  <tr>
    <td style="background:linear-gradient(135deg,{_ORANGE} 0%,#E05A00 100%);
               padding:20px 28px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td>
            <div style="font-family:{_FONT};font-size:22px;font-weight:700;
                        color:#FFFFFF;letter-spacing:.5px;">SmartSup</div>
            <div style="font-family:{_FONT};font-size:11px;color:rgba(255,255,255,.8);
                        margin-top:2px;">Orange Guinée — Network Operations Center</div>
          </td>
          <td align="right">
            <div style="background:rgba(0,0,0,.25);border-radius:6px;
                        padding:6px 14px;display:inline-block;">
              <span style="font-family:monospace;font-size:13px;font-weight:700;
                           color:#FFFFFF;">{_html.escape(ticket.get("numero","—"))}</span>
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- TITLE BAR -->
  <tr>
    <td style="background:{_DARK};padding:12px 28px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td>
            <span style="font-family:{_FONT};font-size:14px;font-weight:700;
                         color:#FFFFFF;letter-spacing:1px;">{_html.escape(title)}</span>
          </td>
          <td align="right">
            <span style="background:{prio_color};color:#FFFFFF;font-family:{_FONT};
                         font-size:11px;font-weight:700;padding:3px 10px;
                         border-radius:12px;">{_html.escape(prio)}</span>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- INTRO -->
  <tr>
    <td style="padding:18px 28px 10px;">
      <p style="font-family:{_FONT};font-size:13px;color:#333;margin:0 0 6px;">
        {_html.escape(L["greeting"])}</p>
      <p style="font-family:{_FONT};font-size:13px;color:#333;margin:0;">
        {_html.escape(intro)}</p>
    </td>
  </tr>

  <!-- TABLE INCIDENT -->
  <tr>
    <td style="padding:10px 28px 18px;">
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border-collapse:collapse;">
        {_row_html(L["ticket_number"], ticket.get("numero","—"), bold=True)}
        {_row_html(L["type_incident"], ticket.get("type_libelle") or ticket.get("libelle_fr","—"))}
        {_row_html(L["description"],   ticket.get("description","—"))}
        {_row_html(L["service"],       service)}
        {_row_html(L["priorite"],      prio, bg=prio_color, color="#FFFFFF", bold=True)}
        {_row_html(L["heure_debut"],   ticket.get("hd","—"))}
        {hf_row}
        {cause_row}
        {action_row}
        {_row_html(L["superviseur"],   sup_name.strip() or "—")}
        {preuve_html}
      </table>
    </td>
  </tr>

  <!-- FOOTER MSG -->
  <tr>
    <td style="padding:0 28px 18px;">
      <p style="font-family:{_FONT};font-size:13px;color:#555;
                border-left:3px solid {_ORANGE};padding-left:10px;margin:0;">
        {_html.escape(footer)}</p>
    </td>
  </tr>

  <!-- SIGNATURE -->
  <tr>
    <td style="padding:16px 28px;border-top:1px solid {_BORDER};">
      {sig_html}
    </td>
  </tr>

  <!-- CONFIDENTIAL FOOTER -->
  <tr>
    <td style="background:#F5F5F5;padding:10px 28px;border-top:1px solid {_BORDER};">
      <p style="font-family:{_FONT};font-size:10px;color:#AAA;margin:0;text-align:center;">
        {_html.escape(L["confidentiel"])}</p>
    </td>
  </tr>

</table>
</td></tr></table>
</body></html>"""


def _build_subject_tmc(ticket: dict, statut_type: str, langue: str) -> str:
    """Construit l'objet de l'e-mail TMC."""
    L = _LABELS.get(langue, _LABELS["fr"])
    title_key = f"title_{statut_type}" if f"title_{statut_type}" in L else "title_debut"
    title = L[title_key]
    service = ticket.get("service") or ticket.get("lien_impacte") or ""
    numero  = ticket.get("numero","")
    prio    = ticket.get("priorite","")
    service_part = f" [{service}]" if service else ""
    return f"[{prio}] {title}{service_part} || {numero}"


def _open_cross_platform(path: str):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        import subprocess; subprocess.run(["open", path], check=False)
    else:
        import subprocess; subprocess.run(["xdg-open", path], check=False)


def send_tmc_notification(ticket: dict, statut_type: str = "debut",
                          destinataires_override: list | None = None,
                          preuve_file_path: str | None = None,
                          display_only: bool = True) -> dict:
    """
    Envoie (ou ouvre dans Outlook) la notification TMC pour un ticket.

    Args:
        ticket:                  dict complet du ticket (depuis get_ticket)
        statut_type:             'debut' | 'fin' | 'avancement'
        destinataires_override:  liste d'adresses e-mail si différent du routage auto
        preuve_file_path:        chemin vers screenshot ou fichier à joindre
        display_only:            True = ouvrir dans Outlook, False = envoyer direct
    """
    langue = ticket.get("langue") or ticket.get("type_langue") or "fr"

    # Récupérer signature du superviseur
    sig = None
    if ticket.get("superviseur_id"):
        conn = get_conn()
        sig_row = conn.execute("""
            SELECT * FROM signatures
            WHERE superviseur_id=? AND langue=? AND actif=1
        """, (ticket["superviseur_id"], langue)).fetchone()
        if sig_row:
            sig = dict(sig_row)
        conn.close()

    subject   = _build_subject_tmc(ticket, statut_type, langue)
    html_body = _build_html_tmc(ticket, statut_type, langue, sig)

    # Destinataires : override > routing auto > email_list de l'équipe
    to_list = destinataires_override or []
    if not to_list and ticket.get("email_list"):
        to_list = [a.strip() for a in ticket["email_list"].split(";") if a.strip()]
    if not to_list and ticket.get("equipe_tmc_id"):
        conn = get_conn()
        ml = conn.execute("""
            SELECT adresses FROM mailing_lists
            WHERE equipe_tmc_id=? AND niveau=1 AND type_canal='email'
            ORDER BY niveau LIMIT 1
        """, (ticket["equipe_tmc_id"],)).fetchone()
        if ml:
            to_list = [a.strip() for a in ml["adresses"].split(";") if a.strip()]
        conn.close()

    # Tentative Outlook COM
    try:
        import win32com.client as win32
        outlook = win32.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)
        mail.Subject  = subject
        mail.HTMLBody = html_body
        for addr in to_list:
            mail.Recipients.Add(addr).Type = 1
        mail.Recipients.ResolveAll()

        # Pièce jointe
        if preuve_file_path and Path(preuve_file_path).exists():
            mail.Attachments.Add(str(Path(preuve_file_path).resolve()))

        if display_only:
            mail.Display()
        else:
            mail.Send()

        method = "outlook"
    except Exception as com_err:
        # Fallback EML
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["To"]      = "; ".join(to_list)
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        if preuve_file_path and Path(preuve_file_path).exists():
            with open(preuve_file_path, "rb") as f:
                part = MIMEBase("application","octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition","attachment",
                            filename=Path(preuve_file_path).name)
            msg.attach(part)
        tmp = tempfile.NamedTemporaryFile(mode="wb",suffix=".eml",
                                          prefix="smartsup_tmc_",delete=False)
        tmp.write(msg.as_bytes()); tmp.close()
        _open_cross_platform(tmp.name)
        threading.Thread(target=lambda p:(time.sleep(30), os.unlink(p)),
                         args=(tmp.name,), daemon=True).start()
        method = "eml_fallback"

    # Logger la communication dans ticket_comms
    if ticket.get("id"):
        conn = get_conn()
        conn.execute("""INSERT INTO ticket_comms
            (ticket_id,canal,groupe,sujet,destinataires,statut)
            VALUES (?,?,?,?,?,?)""",
            (ticket["id"], "email_tmc", "TMC",
             subject, "; ".join(to_list),
             "ouvert" if display_only else "envoye"))
        _log_event(conn, ticket["id"], "signalisation_tmc",
                   f"Notification TMC ({langue}) envoyée — {statut_type}", "système")
        conn.commit(); conn.close()

    return {"status": "ok", "method": method, "subject": subject,
            "langue": langue, "destinataires": to_list}
