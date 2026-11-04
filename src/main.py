"""Einstiegspunkt / Orchestrierung.

Befehle:
  python -m src.main run      # Suche durchlaufen, bewerten, Nachrichten vorbereiten/senden
  python -m src.main login    # Einmalig manuell einloggen (Session speichern)
  python -m src.main report   # Report der vorbereiteten Nachrichten neu schreiben
"""
from __future__ import annotations

import random
import sys
import time

from . import scraper, evaluator, messenger
from .config import load_config
from .db import DB


def _sleep(cfg):
    lo, hi = cfg.runtime.delay_between_actions_sec
    time.sleep(random.uniform(lo, hi))


def cmd_run(cfg):
    db = DB()
    channel = getattr(cfg.runtime, "browser_channel", None) or None
    with scraper.browser_context(cfg.runtime.user_data_dir, cfg.runtime.headless,
                                 channel=channel) as ctx:
        print(f"[*] Suche: {cfg.search.url}")
        listings = scraper.fetch_search_listings(ctx, cfg.search.url, cfg.search.max_pages)
        print(f"[*] {len(listings)} Anzeigen gefunden.")

        new_count = 0
        for base in listings:
            if db.seen(base["ad_id"]):
                continue
            new_count += 1
            print(f"\n[+] Neu: {base['title']}  ({base['price']})")

            # Detailseite laden
            detail = scraper.fetch_listing_detail(ctx, base["url"])
            listing = {**base, **detail}
            _sleep(cfg)

            # 1) Harter Filter
            ok, reason = evaluator.hard_filter(listing, cfg.criteria)
            if not ok:
                print(f"    -> aussortiert: {reason}")
                db.save(**_row(base, "filtered_out", reasons=reason))
                continue

            # 2) LLM-Bewertung + Nachricht
            try:
                res = evaluator.evaluate_and_compose(
                    listing, cfg.profile, cfg.criteria, cfg.message, cfg.llm
                )
            except Exception as e:  # noqa: BLE001
                print(f"    -> LLM-Fehler: {e}")
                db.save(**_row(base, "error", reasons=str(e)))
                continue

            print(f"    -> Score {res['score']}: {res['reasons']}")

            if res["match"] and res["score"] >= cfg.message.min_score:
                if cfg.message.mode == "auto":
                    sent = messenger.send_message_auto(
                        ctx, base["url"], res["message"], submit=True
                    )
                    status = "sent" if sent else "error"
                    print(f"    -> {'GESENDET' if sent else 'Senden fehlgeschlagen'}")
                else:
                    status = "ready"
                    print("    -> Nachricht vorbereitet (semi-auto).")
                db.save(**_row(base, status, res["score"], res["reasons"], res["message"]))
            else:
                db.save(**_row(base, "rejected", res["score"], res["reasons"]))

            _sleep(cfg)

        print(f"\n[*] Fertig. {new_count} neue Anzeigen verarbeitet.")

    # Report für vorbereitete Nachrichten
    rows = [dict(r) for r in db.ready_messages()]
    if rows:
        messenger.write_report("nachrichten.md", rows)
        print(f"[*] {len(rows)} vorbereitete Nachricht(en) -> nachrichten.md")
    db.close()


def _row(base, status, score=None, reasons="", message=""):
    return dict(
        ad_id=base["ad_id"], url=base["url"], title=base["title"],
        price=base["price"], location=base["location"],
        status=status, score=score, reasons=reasons, message=message,
    )


def cmd_login(cfg):
    channel = getattr(cfg.runtime, "browser_channel", None) or None
    scraper.interactive_login(cfg.runtime.user_data_dir, channel=channel)
    print("[*] Login-Session gespeichert.")


def cmd_report(cfg):
    db = DB()
    rows = [dict(r) for r in db.ready_messages()]
    messenger.write_report("nachrichten.md", rows)
    print(f"[*] Report geschrieben: {len(rows)} Nachricht(en).")
    db.close()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    cfg = load_config()
    {"run": cmd_run, "login": cmd_login, "report": cmd_report}.get(cmd, cmd_run)(cfg)


if __name__ == "__main__":
    main()
