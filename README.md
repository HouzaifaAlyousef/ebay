# Kleinanzeigen Wohnungs-Helfer

Durchsucht täglich eine Kleinanzeigen-Such-URL, filtert nach deinen Kriterien,
bewertet passende Wohnungen per LLM (Gemini/OpenAI/Anthropic) und bereitet ein
persönliches Anschreiben vor (oder sendet es – auf eigenes Risiko).

> ⚠️ **Wichtig:** Automatisiertes Scraping und Nachrichtenversand verstoßen gegen
> die Nutzungsbedingungen von Kleinanzeigen und können zur **Sperrung deines Kontos**
> führen. Nutze das Tool sparsam, mit langen Pausen und vorzugsweise im
> `semi-auto`-Modus. Verwendung auf eigene Verantwortung.

## Installation

```bash
cd kleinanzeigen-helper
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## Konfiguration

```bash
cp config.example.yaml config.yaml     # Kriterien + Profil anpassen
cp .env.example .env                   # API-Key eintragen
```

In `config.yaml` die Such-URL eintragen: Auf kleinanzeigen.de alle Filter setzen,
dann URL aus der Adresszeile kopieren.

## Nutzung

```bash
python -m src.main login     # 1x: manuell einloggen (Session wird gespeichert)
python -m src.main run       # Durchlauf: suchen, bewerten, Nachrichten vorbereiten
```

Vorbereitete Nachrichten landen in **`nachrichten.md`** (zum Kopieren/Senden).

## Täglich automatisch (cron, Linux/Mac)

```bash
crontab -e
# Jeden Tag um 8:17 Uhr:
17 8 * * * cd /pfad/zu/kleinanzeigen-helper && .venv/bin/python -m src.main run >> run.log 2>&1
```

Windows: Aufgabenplanung -> tägliche Aufgabe -> `.venv\Scripts\python.exe -m src.main run`.

## Modi

- `message.mode: semi-auto` (empfohlen) – Nachricht wird nur vorbereitet.
- `message.mode: auto` – **experimentell**, sendet automatisch. Höheres Sperr-Risiko,
  Formular-Selektoren ändern sich oft (siehe `src/messenger.py`).

## Anpassen, wenn etwas nicht klappt

Die CSS-Selektoren von Kleinanzeigen ändern sich. Falls keine/falsche Daten
kommen, prüfe und aktualisiere die Selektoren oben in:
- `src/scraper.py` (Liste, Preis, Beschreibung, Eckdaten)
- `src/messenger.py` (Kontaktformular)
