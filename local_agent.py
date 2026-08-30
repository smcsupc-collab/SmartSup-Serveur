"""SmartSup local Outlook agent.

This program runs in the logged-in Windows session that owns Outlook.  It only
opens drafts; it never sends mail.  It binds to 127.0.0.1 and is intended to
be exposed privately with Tailscale Serve.
"""

from __future__ import annotations

import hmac
import json
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


HOST = "127.0.0.1"
PORT = int(os.environ.get("SMARTSUP_AGENT_PORT", "8765"))
TOKEN = os.environ.get("SMARTSUP_AGENT_TOKEN", "")
ALLOWED_ORIGIN = os.environ.get(
    "SMARTSUP_ALLOWED_ORIGIN", "https://smartsup-uz6c.onrender.com"
)
MAX_BODY_BYTES = 1_500_000
MAX_RECIPIENTS = 100


def _is_address(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and "\\r" not in value
        and "\\n" not in value
        and len(value) <= 320
    )


def _addresses(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_RECIPIENTS:
        raise ValueError(f"{field} doit être une liste de {MAX_RECIPIENTS} adresses maximum.")
    if not all(_is_address(address) for address in value):
        raise ValueError(f"{field} contient une adresse invalide.")
    return [address.strip() for address in value]


class AgentHandler(BaseHTTPRequestHandler):
    server_version = "SmartSupOutlookAgent/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print("[agent] " + (fmt % args))

    def _cors_allowed(self) -> bool:
        return self.headers.get("Origin") == ALLOWED_ORIGIN

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if self._cors_allowed():
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-SmartSup-Agent-Token")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        supplied = self.headers.get("X-SmartSup-Agent-Token", "")
        return bool(supplied) and hmac.compare_digest(supplied, TOKEN)

    def _read_payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= MAX_BODY_BYTES:
            raise ValueError("Taille de requête invalide.")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("JSON invalide.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Le corps doit être un objet JSON.")
        return payload

    def do_OPTIONS(self) -> None:
        if not self._cors_allowed():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Origine non autorisée."})
            return
        self._send_json(HTTPStatus.NO_CONTENT, {})

    def do_GET(self) -> None:
        if self.path != "/health":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Introuvable."})
            return
        self._send_json(HTTPStatus.OK, {"status": "ok", "service": "SmartSup Outlook agent"})

    def do_POST(self) -> None:
        if self.path != "/v1/outlook/draft":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Introuvable."})
            return
        if not self._cors_allowed():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Origine non autorisée."})
            return
        if not self._authorized():
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Jeton agent invalide."})
            return

        try:
            payload = self._read_payload()
            to = _addresses(payload.get("to"), "to")
            cc = _addresses(payload.get("cc"), "cc")
            subject = payload.get("subject")
            html_body = payload.get("html_body")
            if not to:
                raise ValueError("Au moins un destinataire est requis.")
            if not isinstance(subject, str) or not subject.strip() or len(subject) > 998:
                raise ValueError("Objet invalide.")
            if not isinstance(html_body, str) or not html_body.strip():
                raise ValueError("Corps HTML requis.")

            import win32com.client as win32  # Windows + Outlook uniquement

            outlook = win32.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)
            mail.Subject = subject
            mail.HTMLBody = html_body
            for address in to:
                recipient = mail.Recipients.Add(address)
                recipient.Type = 1  # À
            for address in cc:
                recipient = mail.Recipients.Add(address)
                recipient.Type = 2  # Cc
            mail.Recipients.ResolveAll()
            mail.Display()  # Aucun appel à Send : l'opérateur garde le contrôle.
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except Exception as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"Impossible d'ouvrir Outlook : {exc}"},
            )
            return

        self._send_json(HTTPStatus.OK, {"status": "draft_opened"})

    def do_PUT(self) -> None:
        self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "Méthode non autorisée."})

    do_DELETE = do_PUT


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Cet agent doit être exécuté dans une session Windows avec Outlook.")
    if len(TOKEN) < 32:
        raise SystemExit("Définissez SMARTSUP_AGENT_TOKEN avec au moins 32 caractères.")
    print(f"SmartSup Outlook agent disponible sur http://{HOST}:{PORT}")
    print(f"Origine web autorisée : {ALLOWED_ORIGIN}")
    print("Le programme ouvre des brouillons Outlook, mais ne les envoie jamais.")
    ThreadingHTTPServer((HOST, PORT), AgentHandler).serve_forever()


if __name__ == "__main__":
    main()
