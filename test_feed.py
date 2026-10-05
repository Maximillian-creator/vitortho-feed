"""Tests zonder netwerk en zonder inlog: pinnen vast wat een B2B-pagina betekent,
dat de feed verder byte voor byte gelijk blijft, en dat de rem stopt.

    python -m pytest -q test_feed.py
"""
import re

import pytest

import scraper

UIT = '<a href="/Account/Logout.aspx">Uitloggen</a>'
# echte fragmenten van www.vitorthoshop.nl (30-09-2026, product 1086 en 8309)
LEVERBAAR = (UIT + '<span id="ContentPlaceHolder1_ControlStockStatus_LabelStockVitOrtho">Uit voorraad leverbaar</span>'
             '<input type="submit" name="ctl00$ContentPlaceHolder1$ButtonKoopnu" value="Bestellen"  '
             'id="ContentPlaceHolder1_ButtonKoopnu" class="acCatalogDetailKoopButton" />')
NIET = (UIT + '<span id="ContentPlaceHolder1_ControlStockStatus_LabelStockVitOrtho">Niet in voorraad</span>'
        '<input type="submit" name="ctl00$ContentPlaceHolder1$ButtonKoopnu" value=""  '
        'id="ContentPlaceHolder1_ButtonKoopnu" title="Houd mij op de hoogte" class="acCatalogDetailKoopButton"  />')
BEPERKT = LEVERBAAR.replace("Uit voorraad leverbaar", "Beperkt in voorraad")
LEEG_MAIL = NIET.replace("Niet in voorraad", "")                      # 8411/83301: geen label, mail-icoon
UIT_ASS = UIT + "Dit product is uit assortiment, en kunnen wij helaas niet meer leveren." + LEVERBAAR.replace(UIT, "")
WEG = UIT + "Het gevraagde product is niet gevonden."
UITGELOGD = LEVERBAAR.replace(UIT, "")


def test_betekenis_van_een_productpagina():
    s = lambda p: scraper.status_van(scraper.lees_productpagina(p))  # noqa: E731
    assert s(LEVERBAAR) == 2
    assert s(BEPERKT) == 1
    assert s(NIET) == 0
    assert s(LEEG_MAIL) == 0
    assert s(UIT_ASS) == 0            # ook al staat de knop er nog
    assert s(WEG) == 0
    assert s(UITGELOGD) is None       # sessie weg: niet raden, Vitortho's code houden
    # 05-10: de inlogpagina van AsterCart v26.42 heeft óók een uitloglink; het inlogformulier beslist
    loginpagina = UIT + '<input name="ctl00$ContentPlaceHolder1$TextBoxPassword" type="password" />'
    assert s(loginpagina) is None and not scraper.ingelogd(loginpagina)
    # 05-10: AsterCart kan de knop anders noemen of een <button> maken; de "houd mij op de hoogte"-
    # knop (leeg of met die tekst) blijft niet bestelbaar
    assert s(LEVERBAAR.replace('value="Bestellen"', 'value="In winkelwagen"')) == 2
    knop_button = (UIT + '<span id="ContentPlaceHolder1_ControlStockStatus_LabelStockVitOrtho">Uit voorraad leverbaar</span>'
                   '<button type="submit" id="ContentPlaceHolder1_ButtonKoopnu" class="x"><i></i> Bestellen</button>')
    assert s(knop_button) == 2
    assert s(NIET.replace('value=""', 'value="Houd mij op de hoogte"')) == 0
    assert s(NIET.replace('value=""', 'value="Bestellen"')) == 0          # label "Niet in voorraad" wint
    d = scraper.diagnose(LEVERBAAR + '<input type="submit" id="ContentPlaceHolder1_X" value="€ 12,98" />')
    assert d["ingelogd"] and "ButtonKoopnu='Bestellen'" in d["knoppen"]
    x = [k for k in d["knoppen"] if k.startswith("X=")][0]
    assert "€" not in x and not re.search(r"\d", x), x                     # geen prijzen in een openbaar log


FEED = ('<?xml version="1.0" encoding="utf-8"?>\r\n<Producten>\r\n'
        '  <Product>\r\n    <Artikelnummer>1086</Artikelnummer>\r\n    <Merk>VitOrtho</Merk>\r\n'
        '    <Produktnaam>L-Tryptofaan 500 mg</Produktnaam>\r\n    <RetailPrijs>19.9500</RetailPrijs>\r\n'
        '    <CombinedDescriptionHtml>&lt;p&gt;tekst&lt;/p&gt;</CombinedDescriptionHtml>\r\n'
        '    <VoorraadstatusCode>0</VoorraadstatusCode>\r\n'
        '    <VoorraadstatusToelichting>niet op voorraad</VoorraadstatusToelichting>\r\n  </Product>\r\n'
        '  <Product>\r\n    <Artikelnummer>8608</Artikelnummer>\r\n    <Merk>VitOrtho</Merk>\r\n'
        '    <VoorraadstatusCode>2</VoorraadstatusCode>\r\n'
        '    <VoorraadstatusToelichting>ruim op voorraad</VoorraadstatusToelichting>\r\n  </Product>\r\n'
        '</Producten>')


def test_alleen_de_voorraadvelden_veranderen():
    uit = scraper.pas_toe(FEED, {"1086": 2, "8608": 0})
    assert "<VoorraadstatusCode>2</VoorraadstatusCode>\r\n    <VoorraadstatusToelichting>ruim op voorraad" in uit
    assert uit.count("<VoorraadstatusCode>0</VoorraadstatusCode>") == 1
    # alles buiten die twee velden is byte voor byte gelijk
    weg = lambda t: __import__("re").sub(r"<Voorraadstatus\w+>[^<]*</Voorraadstatus\w+>", "", t)  # noqa: E731
    assert weg(uit) == weg(FEED)
    # een product zonder B2B-oordeel houdt Vitortho's eigen code
    assert scraper.pas_toe(FEED, {}) == FEED
    assert [p["artikel"] for p in scraper.producten(FEED)] == ["1086", "8608"]
    assert not scraper.afgekapt(FEED) and scraper.afgekapt(FEED[:-5])


def test_de_rem():
    goed = {str(i): 2 for i in range(300)}
    scraper.keur(300, goed)                                         # gaat door
    with pytest.raises(SystemExit):
        scraper.keur(200, {str(i): 2 for i in range(200)})          # feed te klein
    with pytest.raises(SystemExit):
        scraper.keur(300, {**goed, **{str(i): None for i in range(20)}})   # 20/300 onbepaald > 5%
    with pytest.raises(SystemExit):
        scraper.keur(300, {**goed, **{str(i): 0 for i in range(100)}})     # 100/300 niet leverbaar > 30%
    scraper.keur(300, {**goed, **{str(i): 0 for i in range(12)}})          # 12 niet leverbaar: normaal


def test_inloggen_zonder_secrets_stopt(monkeypatch):
    monkeypatch.delenv("VITORTHO_GEBRUIKER", raising=False)
    monkeypatch.delenv("VITORTHO_WACHTWOORD", raising=False)
    with pytest.raises(SystemExit):
        scraper.login(None)


def test_verborgen_velden_van_asp_net():
    pagina = ('<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="abc&amp;def" />'
              '<input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="xyz" />'
              '<input name="ctl00$ContentPlaceHolder1$TextBoxLogin" type="text" />')
    assert scraper._verborgen_velden(pagina) == {"__VIEWSTATE": "abc&def", "__EVENTVALIDATION": "xyz"}
