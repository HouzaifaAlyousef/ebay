"""Harte Filter (Code) + weiche Bewertung & Nachrichten-Erstellung (LLM).

Die LLM-Schicht ist anbieter-unabhängig: gemini | openai | anthropic.
Rückgabe immer als Dict: {"match": bool, "score": int, "reasons": str, "message": str}
"""
from __future__ import annotations

import json
import re

from .config import get_api_key


# ---------------------------------------------------------------------------
# 1) Harte Filter – vor dem (kostenpflichtigen) LLM-Aufruf
# ---------------------------------------------------------------------------
def hard_filter(listing: dict, criteria) -> tuple[bool, str]:
    """True = besteht die harten Kriterien. Zweiter Wert = Begründung bei Ablehnung."""
    text = f"{listing.get('title','')} {listing.get('description','')}".lower()

    price = _num(listing.get("price", ""))
    if price is not None:
        if criteria.max_price and price > criteria.max_price:
            return False, f"Preis {price} > max {criteria.max_price}"
        if criteria.min_price and price < criteria.min_price:
            return False, f"Preis {price} < min {criteria.min_price}"

    rooms = listing.get("rooms")
    if rooms is not None:
        if criteria.min_rooms and rooms < criteria.min_rooms:
            return False, f"Zimmer {rooms} < min {criteria.min_rooms}"
        if criteria.max_rooms and rooms > criteria.max_rooms:
            return False, f"Zimmer {rooms} > max {criteria.max_rooms}"

    size = listing.get("size_sqm")
    if size is not None and criteria.min_size_sqm and size < criteria.min_size_sqm:
        return False, f"Fläche {size} < min {criteria.min_size_sqm}"

    for kw in (criteria.excluded_keywords or []):
        if kw.lower() in text:
            return False, f"Ausschluss-Keyword gefunden: {kw}"

    for kw in (criteria.required_keywords or []):
        if kw.lower() not in text:
            return False, f"Pflicht-Keyword fehlt: {kw}"

    return True, ""


def _num(text: str):
    if not text:
        return None
    m = re.search(r"(\d[\d.]*)", str(text).replace(".", ""))
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# 2) LLM: Bewertung + Nachricht
# ---------------------------------------------------------------------------
def _build_prompt(listing, profile, criteria, message_cfg) -> str:
    return f"""Du bist ein Assistent, der bei der Wohnungssuche auf Kleinanzeigen hilft.

AUFGABE:
1. Bewerte, wie gut die Wohnung zu den Wünschen des Suchenden passt (Score 0-10).
2. Wenn match=true, schreibe ein {message_cfg.tone} Anschreiben an den Vermieter
   in Sprache "{message_cfg.language}". Nutze NUR Infos aus dem Profil, erfinde nichts.
   Halte es kurz (max. ~120 Wörter), persönlich und ohne Floskeln-Überladung.

ANZEIGE:
Titel: {listing.get('title','')}
Preis: {listing.get('price','')}
Ort: {listing.get('location','')}
Zimmer: {listing.get('rooms','?')} | Fläche: {listing.get('size_sqm','?')} m²
Beschreibung:
\"\"\"{(listing.get('description','') or '')[:3000]}\"\"\"

WEICHE WÜNSCHE DES SUCHENDEN:
{criteria.notes}

PROFIL DES SUCHENDEN:
- Name: {profile.name}
- Haushalt: {profile.household}
- Beruf: {profile.job}
- Netto-Einkommen/Monat: {profile.income_net_monthly} EUR
- SCHUFA: {profile.schufa}
- Raucher: {"ja" if profile.smoker else "nein"}
- Haustiere: {profile.pets}
- Einzug: {profile.move_in}
- Sonstiges: {profile.extra}

Antworte AUSSCHLIESSLICH mit gültigem JSON in genau diesem Format:
{{"match": true/false, "score": 0-10, "reasons": "kurze Begründung", "message": "Anschreiben oder leer"}}
"""


def evaluate_and_compose(listing, profile, criteria, message_cfg, llm_cfg) -> dict:
    prompt = _build_prompt(listing, profile, criteria, message_cfg)
    raw = _call_llm(llm_cfg.provider, llm_cfg.model, prompt)
    return _parse_json(raw)


def _call_llm(provider: str, model: str, prompt: str) -> str:
    key = get_api_key(provider)

    if provider == "gemini":
        from google import genai
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(model=model, contents=prompt)
        return resp.text

    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.5,
        )
        return resp.choices[0].message.content

    if provider == "anthropic":
        from anthropic import Anthropic
        client = Anthropic(api_key=key)
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text

    raise ValueError(f"Unbekannter Provider: {provider}")


def _parse_json(raw: str) -> dict:
    """LLM-Antwort robust nach JSON parsen (auch wenn in ```json ... ``` verpackt)."""
    if not raw:
        return {"match": False, "score": 0, "reasons": "Leere LLM-Antwort", "message": ""}
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if m:
        cleaned = m.group(0)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return {"match": False, "score": 0,
                "reasons": f"JSON-Parsing fehlgeschlagen: {raw[:200]}", "message": ""}
    return {
        "match": bool(data.get("match", False)),
        "score": int(data.get("score", 0) or 0),
        "reasons": str(data.get("reasons", "")),
        "message": str(data.get("message", "")),
    }
