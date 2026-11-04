"""Nachrichten versenden.

- semi-auto: Nachricht wird nur gespeichert (DB + Report). Du sendest manuell.
- auto:      EXPERIMENTELL. Versucht, das Kontaktformular der Anzeige auszufüllen
             und abzuschicken. Selektoren ändern sich oft -> ggf. anpassen.
"""
from __future__ import annotations

from pathlib import Path

# --- Selektoren Kontaktformular (bei Bedarf anpassen) ---
SEL_MSG = "#viewad-contact-form textarea, #ContactFormMessage"
SEL_SUBMIT = "#viewad-contact-form button[type=submit], #btn-reply-send"


def write_report(path: str, rows: list[dict]):
    """Markdown-Report mit allen vorbereiteten Nachrichten zum Kopieren."""
    lines = ["# Vorbereitete Nachrichten\n"]
    for r in rows:
        lines += [
            f"## {r['title']}  (Score {r['score']})",
            f"- URL: {r['url']}",
            f"- Preis: {r['price']} | Ort: {r['location']}",
            f"- Bewertung: {r['reasons']}",
            "",
            "```",
            r["message"],
            "```",
            "",
        ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def send_message_auto(ctx, url: str, message: str, submit: bool = False) -> bool:
    """EXPERIMENTELL: Kontaktformular öffnen und ausfüllen.
    submit=False -> nur ausfüllen (du drückst Senden). submit=True -> absenden.
    """
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1500)
        box = page.query_selector(SEL_MSG)
        if not box:
            return False
        box.fill(message)
        page.wait_for_timeout(1000)
        if submit:
            btn = page.query_selector(SEL_SUBMIT)
            if not btn:
                return False
            btn.click()
            page.wait_for_timeout(2500)
        else:
            # Formular offen lassen zum manuellen Prüfen/Senden
            input(">> Formular ausgefüllt. Prüfe es im Browser, dann ENTER...")
        return True
    finally:
        page.close()
