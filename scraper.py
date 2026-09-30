"""
Vitortho / NOW — update-feed met de échte voorraad uit de B2B
============================================================
Vitortho publiceert een eigen feed (service.vitortho.nl/ProductFeed.ashx), maar de
voorraadstatus daarin loopt weken achter. Gemeten op 30-09-2026: van de 11 producten
die de B2B niet kan leveren, stonden er 10 in de feed als "op voorraad". Van de 12 die
de feed "niet op voorraad" noemde, waren er 11 gewoon bestelbaar. Gevolg: klanten
bestelden wat niet kwam (26,9% terugbetaald op NOW/VitOrtho, tegen 2,6% bij de rest),
en leverbare producten stonden op uitverkocht.

Deze feed is Vitortho's eigen feed, byte voor byte. Alleen `VoorraadstatusCode` en
`VoorraadstatusToelichting` worden per product overschreven met wat de B2B
(www.vitorthoshop.nl) nú laat zien. Stock Sync hoeft dus alleen een andere URL te
lezen: de koppeling blijft gelijk.

    B2B toont                                   → code  toelichting
    "Uit voorraad leverbaar" + knop Bestellen   →  2    ruim op voorraad
    "Beperkt in voorraad"    + knop Bestellen   →  1    beperkt op voorraad
    geen knop Bestellen (mail-icoon), "Niet in
    voorraad", "uit assortiment", niet gevonden →  0    niet op voorraad

Producten die Vitortho niet meer voert, blijven in de feed met code 0: niet
bestelbaar, maar niet gearchiveerd. Max beslist later (30-09).

Inloggen gebeurt met VITORTHO_GEBRUIKER en VITORTHO_WACHTWOORD (GitHub-secrets, door
Max ingevuld). Het wachtwoord wordt nergens gelogd of weggeschreven. B2B-prijzen
(inkoop) komen nooit in de feed: de prijzen blijven die van Vitortho's openbare feed.

REM (les van 31-08: een halve feed laat Stock Sync producten archiveren). Er wordt
niets weggeschreven als:
  - de openbare feed < 250 producten heeft of afgebroken is;
  - inloggen mislukt;
  - > 5% van de producten niet te bepalen is (netwerk, sessie weg);
  - > 30% niet bestelbaar zou worden (normaal ~3%: dan klopt er iets niet).
"""
from __future__ import annotations

import csv
import html
import os
import re
import sys
import time

import requests

FEED_URL = "https://service.vitortho.nl/ProductFeed.ashx"
B2B = "https://www.vitorthoshop.nl"
LOGIN_PAD = "/Access/Default"
OUTPUT_FILE = "vitortho_feed.xml"
VERSCHILLEN_FILE = "vitortho_verschillen.csv"

MIN_PRODUCTEN = 250
MAX_ONBEPAALD_PCT = 5
MAX_NIET_BESTELBAAR_PCT = 30
PAUZE_S = 0.4
UA = "Mozilla/5.0 (GoodForYou voorraadfeed; klant van Vitortho)"

TOELICHTING = {2: "ruim op voorraad", 1: "beperkt op voorraad", 0: "niet op voorraad"}

_PRODUCT = re.compile(r"<Product>.*?</Product>", re.S)


# ── de openbare feed ─────────────────────────────────────────────────────────

def haal_feed() -> str:
    r = requests.get(FEED_URL, timeout=120, headers={"User-Agent": UA})
    r.raise_for_status()
    return r.content.decode("utf-8")


def _veld(blok: str, naam: str) -> str:
    m = re.search(rf"<{naam}>([^<]*)</{naam}>", blok)
    return html.unescape(m.group(1).strip()) if m else ""


def producten(xml: str) -> list[dict]:
    return [{"artikel": _veld(b, "Artikelnummer"), "merk": _veld(b, "Merk"), "naam": _veld(b, "Produktnaam"),
             "code": _veld(b, "VoorraadstatusCode")} for b in _PRODUCT.findall(xml)]


def afgekapt(xml: str) -> bool:
    return not xml.rstrip().endswith("</Producten>")


def pas_toe(xml: str, codes: dict[str, int]) -> str:
    """Vervang per product alleen de twee voorraadvelden; de rest blijft byte voor byte."""
    def een(m: re.Match) -> str:
        blok = m.group(0)
        code = codes.get(_veld(blok, "Artikelnummer"))
        if code is None:
            return blok
        blok = re.sub(r"<VoorraadstatusCode>[^<]*</VoorraadstatusCode>",
                      f"<VoorraadstatusCode>{code}</VoorraadstatusCode>", blok)
        return re.sub(r"<VoorraadstatusToelichting>[^<]*</VoorraadstatusToelichting>",
                      f"<VoorraadstatusToelichting>{TOELICHTING[code]}</VoorraadstatusToelichting>", blok)
    return _PRODUCT.sub(een, xml)


# ── de B2B ───────────────────────────────────────────────────────────────────

def _verborgen_velden(pagina: str) -> dict:
    velden = {}
    for tag in re.findall(r"<input[^>]*type=\"hidden\"[^>]*>", pagina):
        naam = re.search(r'name="([^"]+)"', tag)
        waarde = re.search(r'value="([^"]*)"', tag)
        if naam:
            velden[naam.group(1)] = html.unescape(waarde.group(1)) if waarde else ""
    return velden


def ingelogd(pagina: str) -> bool:
    return "Account/Logout.aspx" in pagina


def login(sessie: requests.Session) -> None:
    gebruiker, wachtwoord = os.environ.get("VITORTHO_GEBRUIKER"), os.environ.get("VITORTHO_WACHTWOORD")
    if not gebruiker or not wachtwoord:
        raise SystemExit("STOP: VITORTHO_GEBRUIKER / VITORTHO_WACHTWOORD ontbreken (GitHub-secrets).")
    pagina = sessie.get(B2B + LOGIN_PAD, timeout=60).text
    velden = _verborgen_velden(pagina)
    velden.update({"ctl00$ContentPlaceHolder1$TextBoxLogin": gebruiker,
                   "ctl00$ContentPlaceHolder1$TextBoxPassword": wachtwoord,
                   "ctl00$ContentPlaceHolder1$ButtonLogin": "Login"})
    antwoord = sessie.post(B2B + LOGIN_PAD, data=velden, timeout=60)
    if not ingelogd(antwoord.text) and not ingelogd(sessie.get(B2B + "/", timeout=60).text):
        raise SystemExit("STOP: inloggen op de B2B mislukt (gebruiker/wachtwoord of loginpagina veranderd). "
                         "Geen feed weggeschreven.")


def lees_productpagina(pagina: str) -> dict:
    label = re.search(r'id="ContentPlaceHolder1_ControlStockStatus_LabelStockVitOrtho"[^>]*>([^<]*)<', pagina)
    knop_tag = re.search(r'<input[^>]*id="ContentPlaceHolder1_ButtonKoopnu"[^>]*>', pagina)
    knop = None
    if knop_tag:
        w = re.search(r'value="([^"]*)"', knop_tag.group(0))
        knop = html.unescape(w.group(1)).strip() if w else ""
    return {"ingelogd": ingelogd(pagina),
            "weg": bool(re.search(r"product is niet gevonden", pagina, re.I)),
            "uit_assortiment": bool(re.search(r"uit assortiment", pagina, re.I)),
            "label": html.unescape(label.group(1)).strip() if label else "",
            "knop": knop}


def status_van(b: dict) -> int | None:
    """None = niet te bepalen (sessie weg): dan blijft Vitortho's eigen code staan."""
    if not b["ingelogd"]:
        return None
    if b["weg"] or b["uit_assortiment"]:
        return 0
    if b["knop"] == "Bestellen":
        return 1 if "beperkt" in b["label"].lower() else 2
    return 0


def reden_van(b: dict) -> str:
    if b["weg"]:
        return "niet gevonden in de B2B"
    if b["uit_assortiment"]:
        return "uit assortiment"
    return b["label"] or ("bestelbaar" if b["knop"] == "Bestellen" else "niet bestelbaar")


def lees_b2b(sessie: requests.Session, artikelen: list[str]) -> dict[str, dict]:
    uit, opnieuw_ingelogd = {}, False
    for i, nr in enumerate(artikelen, 1):
        b = None
        for poging in range(3):
            try:
                r = sessie.get(f"{B2B}/product/{nr}", timeout=60)
                if r.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {r.status_code}")
                b = lees_productpagina(r.text)
                if not b["ingelogd"] and not opnieuw_ingelogd:
                    login(sessie)                 # sessie verlopen: één keer opnieuw
                    opnieuw_ingelogd = True
                    continue
                break
            except requests.RequestException:
                time.sleep(3 * (poging + 1))
        uit[nr] = b or {"ingelogd": False, "weg": False, "uit_assortiment": False, "label": "", "knop": None}
        if i % 50 == 0:
            print(f"  {i}/{len(artikelen)} gelezen")
        time.sleep(PAUZE_S)
    return uit


# ── samen ────────────────────────────────────────────────────────────────────

def keur(n_feed: int, codes: dict[str, int | None]) -> None:
    """De rem. Gooit SystemExit en schrijft dan niets weg."""
    if n_feed < MIN_PRODUCTEN:
        raise SystemExit(f"STOP: Vitortho's feed heeft maar {n_feed} producten (ondergrens {MIN_PRODUCTEN}).")
    onbepaald = sum(1 for c in codes.values() if c is None)
    if onbepaald * 100 > MAX_ONBEPAALD_PCT * n_feed:
        raise SystemExit(f"STOP: {onbepaald} van {n_feed} producten niet te bepalen in de B2B "
                         f"(grens {MAX_ONBEPAALD_PCT}%). Geen feed weggeschreven.")
    niet = sum(1 for c in codes.values() if c == 0)
    if niet * 100 > MAX_NIET_BESTELBAAR_PCT * n_feed:
        raise SystemExit(f"STOP: {niet} van {n_feed} zouden niet bestelbaar worden (grens "
                         f"{MAX_NIET_BESTELBAAR_PCT}%, normaal ~3%). Waarschijnlijk klopt het lezen niet.")


def main() -> None:
    start = time.time()
    print("Vitortho UPDATE-feed (voorraad uit de B2B) gestart\n")
    xml = haal_feed()
    if afgekapt(xml):
        raise SystemExit("STOP: Vitortho's feed is afgebroken (</Producten> ontbreekt).")
    lijst = producten(xml)
    print(f"Openbare feed: {len(lijst)} producten")
    sessie = requests.Session()
    sessie.headers["User-Agent"] = UA
    login(sessie)
    print("Ingelogd op de B2B")
    b2b = lees_b2b(sessie, [p["artikel"] for p in lijst])
    codes = {nr: status_van(b) for nr, b in b2b.items()}
    keur(len(lijst), codes)
    nieuw = pas_toe(xml, {nr: c for nr, c in codes.items() if c is not None})
    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        f.write(nieuw)
    verschil = []
    for p in lijst:
        c = codes.get(p["artikel"])
        oud = int(p["code"]) if p["code"].isdigit() else None
        if c is not None and oud is not None and (c > 0) != (oud > 0):
            verschil.append({"artikelnummer": p["artikel"], "merk": p["merk"], "product": p["naam"],
                             "vitortho_feed": TOELICHTING.get(oud, p["code"]), "b2b": TOELICHTING[c],
                             "b2b_ziet": reden_van(b2b[p["artikel"]])})
    with open(VERSCHILLEN_FILE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["artikelnummer", "merk", "product", "vitortho_feed", "b2b", "b2b_ziet"])
        w.writeheader()
        w.writerows(sorted(verschil, key=lambda r: r["artikelnummer"]))
    telling = {k: sum(1 for c in codes.values() if c == k) for k in (2, 1, 0, None)}
    print(f"\nKlaar in {time.time() - start:.0f}s: {telling[2]} ruim, {telling[1]} beperkt, {telling[0]} niet "
          f"leverbaar, {telling[None]} onbepaald (Vitortho's code gehouden)")
    print(f"Verschil met Vitortho's eigen feed (bestelbaar ja/nee): {len(verschil)} producten → {VERSCHILLEN_FILE}")
    print("\nFeed-URL voor Stock Sync (NOW | Vitortho):")
    print("https://raw.githubusercontent.com/Maximillian-creator/vitortho-feed/main/vitortho_feed.xml")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        print(e, file=sys.stderr)
        raise
