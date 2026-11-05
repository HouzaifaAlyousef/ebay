"""Scraping von Kleinanzeigen mit Playwright (persistenter Login-Kontext).

HINWEIS: Die CSS-Selektoren können sich jederzeit ändern. Sie sind hier
oben gesammelt, damit du sie bei Bedarf schnell anpassen kannst. Prüfe sie
mit den Dev-Tools (Rechtsklick -> Untersuchen) auf kleinanzeigen.de.
"""
from __future__ import annotations

import re
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

# --- Selektoren (bei Bedarf anpassen) ---
SEL_ITEM = "article.aditem"
SEL_LINK = "a.ellipsis"
SEL_PRICE = ".aditem-main--middle--price-shipping--price"
SEL_LOCATION = ".aditem-main--top--left"
SEL_DESC = "#viewad-description-text"
SEL_ATTR_LIST = ".addetailslist--detail"   # Eckdaten (Zimmer, m², etc.)
SEL_ITEMS = ["article.aditem", "article[data-adid]", "li.ad-listitem article", "[data-adid]"]
CONSENT_LABELS = ["Alle akzeptieren", "Alle akzeptieren und weiter", "Akzeptieren"]
SEL_CONSENT = ["#gdpr-banner-accept", "button[aria-label*='akzeptier' i]"]

BASE = "https://www.kleinanzeigen.de"


def _accept_consent(page) -> bool:
    """Consent-Dialog 'Willkommen bei Kleinanzeigen' / Cookie-Banner wegklicken.
    Sucht per Button-Text (robust) über alle Frames; CSS-IDs als Fallback.
    """
    for fr in [page, *page.frames]:
        for label in CONSENT_LABELS:
            try:
                btn = fr.get_by_role("button", name=label, exact=False)
                if btn.count() > 0:
                    btn.first.click(timeout=3000)
                    page.wait_for_timeout(1500)
                    return True
            except Exception:
                pass
        for sel in SEL_CONSENT:
            try:
                el = fr.query_selector(sel)
                if el:
                    el.click()
                    page.wait_for_timeout(1500)
                    return True
            except Exception:
                pass
    return False


def _find_items(page):
    """Erstes Selektor-Schema, das Treffer liefert (Layout ändert sich)."""
    for sel in SEL_ITEMS:
        els = page.query_selector_all(sel)
        if els:
            return els
    return []


def _dump_debug(page, name: str = "debug_search"):
    """Screenshot + HTML speichern, wenn nichts gefunden wird (zur Diagnose)."""
    from pathlib import Path
    try:
        page.screenshot(path=f"{name}.png", full_page=True)
        Path(f"{name}.html").write_text(page.content(), encoding="utf-8")
        print(f"    [debug] Seite gespeichert: {name}.png  /  {name}.html")
    except Exception as e:  # noqa: BLE001
        print(f"    [debug] Dump fehlgeschlagen: {e}")


@contextmanager
def browser_context(user_data_dir: str, headless: bool = False,
                    channel: str | None = None, user_agent: str | None = None):
    """Persistenter Browser-Kontext mit reduziertem Automatisierungs-Fingerabdruck.

    channel="chrome" nutzt dein installiertes echtes Chrome statt des gebündelten
    Chromium -> deutlich unauffälliger. user_agent nur setzen, wenn nötig
    (sonst nutzt der Browser seinen echten, zur Plattform passenden UA).
    """
    with sync_playwright() as p:
        launch_kwargs = dict(
            user_data_dir=user_data_dir,
            headless=headless,
            locale="de-DE",
            timezone_id="Europe/Berlin",
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        if channel:
            launch_kwargs["channel"] = channel      # z.B. "chrome" | "msedge"
        if user_agent:
            launch_kwargs["user_agent"] = user_agent
        ctx = p.chromium.launch_persistent_context(**launch_kwargs)
        # navigator.webdriver verstecken (häufigstes Bot-Signal)
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        try:
            yield ctx
        finally:
            ctx.close()


def _num(text: str) -> float | None:
    """Erste Zahl aus einem Text ziehen (z.B. '850 € VB' -> 850.0)."""
    if not text:
        return None
    m = re.search(r"(\d[\d.]*)", text.replace(".", ""))
    return float(m.group(1)) if m else None


def fetch_search_listings(ctx, url: str, max_pages: int = 1) -> list[dict]:
    """Liefert eine Liste von {ad_id, url, title, price, location} von den Ergebnisseiten."""
    page = ctx.new_page()
    results: list[dict] = []
    seen_ids = set()

    for page_no in range(1, max_pages + 1):
        page_url = url if page_no == 1 else _paginate(url, page_no)
        page.goto(page_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1500)
        _accept_consent(page)            # Consent-Dialog wegklicken
        try:
            page.wait_for_selector(SEL_ITEM, timeout=10_000)
        except Exception:
            pass
        page.mouse.wheel(0, 4000)        # Lazy-Load anstoßen
        page.wait_for_timeout(1500)

        items = _find_items(page)
        parsed_here = 0

        for it in items:
            ad_id = it.get_attribute("data-adid")
            if not ad_id:
                inner = it.query_selector("[data-adid]")
                ad_id = inner.get_attribute("data-adid") if inner else None

            # Link/URL robust bestimmen (Layout variiert)
            href = it.get_attribute("data-href")
            link = (it.query_selector("a.ellipsis")
                    or it.query_selector("h2 a")
                    or it.query_selector("a[href*='/s-anzeige/']")
                    or it.query_selector("a[href]"))
            if not href and link:
                href = link.get_attribute("href")
            if not href:
                continue
            full_url = href if href.startswith("http") else BASE + href

            if not ad_id:                       # ID aus URL ableiten
                m = re.search(r"/(\d{6,})-", full_url) or re.search(r"(\d{6,})", full_url)
                ad_id = m.group(1) if m else full_url
            if ad_id in seen_ids:
                continue

            # Titel robust
            title = (link.inner_text().strip() if link else "")
            if not title:
                h = it.query_selector("h2")
                title = (h.inner_text().strip() if h else "")

            price_el = it.query_selector(SEL_PRICE)
            loc_el = it.query_selector(SEL_LOCATION)
            results.append({
                "ad_id": ad_id,
                "url": full_url,
                "title": title,
                "price": (price_el.inner_text().strip() if price_el else ""),
                "location": (loc_el.inner_text().strip() if loc_el else ""),
            })
            seen_ids.add(ad_id)
            parsed_here += 1

        if parsed_here == 0:
            _dump_debug(page, "debug_search")
            print(f"    [!] Seite {page_no}: 0 verwertbare Anzeigen "
                  f"({len(items)} Rohelemente gefunden) – siehe debug_search.png / .html")

    page.close()
    return results


def fetch_listing_detail(ctx, url: str) -> dict:
    """Beschreibung + Eckdaten einer einzelnen Anzeige holen."""
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1500)

    desc_el = page.query_selector(SEL_DESC)
    description = desc_el.inner_text().strip() if desc_el else ""

    attrs: dict[str, str] = {}
    for row in page.query_selector_all(SEL_ATTR_LIST):
        txt = row.inner_text().strip()
        # Zeilen sind meist "Zimmer\n3" o.ä.
        parts = [p.strip() for p in txt.split("\n") if p.strip()]
        if len(parts) >= 2:
            attrs[parts[0].lower()] = parts[1]

    page.close()

    rooms = _extract_rooms(attrs, description)
    size = _extract_size(attrs, description)
    return {
        "description": description,
        "attributes": attrs,
        "rooms": rooms,
        "size_sqm": size,
    }


def _extract_rooms(attrs: dict, text: str) -> float | None:
    for k, v in attrs.items():
        if "zimmer" in k:
            return _num(v)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:-?\s*)zimmer", text.lower())
    return float(m.group(1).replace(",", ".")) if m else None


def _extract_size(attrs: dict, text: str) -> float | None:
    for k, v in attrs.items():
        if "wohnfläche" in k or "fläche" in k or "größe" in k:
            return _num(v)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*m²", text.lower())
    return float(m.group(1).replace(",", ".")) if m else None


def _paginate(url: str, page_no: int) -> str:
    """Kleinanzeigen-Pagination: .../seite:2/... – simple Heuristik."""
    if "/seite:" in url:
        return re.sub(r"/seite:\d+", f"/seite:{page_no}", url)
    # vor dem letzten Pfadsegment einfügen
    parts = url.rstrip("/").rsplit("/", 1)
    if len(parts) == 2:
        return f"{parts[0]}/seite:{page_no}/{parts[1]}"
    return url


def interactive_login(user_data_dir: str, channel: str | None = None):
    """Einmalig manuell einloggen; Session wird im user_data_dir gespeichert."""
    with browser_context(user_data_dir, headless=False, channel=channel) as ctx:
        page = ctx.new_page()
        page.goto(BASE + "/m-einloggen.html", wait_until="domcontentloaded")
        print(">> Bitte im Browser einloggen (ggf. Captcha lösen).")
        input(">> Danach hier ENTER drücken, um die Session zu speichern...")
