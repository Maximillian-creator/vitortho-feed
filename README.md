# Vitortho / NOW-feed → Stock Sync (met de voorraad uit de B2B)

Vitortho publiceert zelf een feed (`service.vitortho.nl/ProductFeed.ashx`), maar de
voorraadstatus daarin loopt weken achter op hun eigen B2B. Op 30-09-2026 was het
product voor product nagekeken:
- **21 van de 323** producten hadden in de feed een andere status dan in de B2B.
- Van de **11** producten die de B2B niet kon leveren, stonden er **10** in de feed als "op voorraad".
- Van de **12** die de feed "niet op voorraad" noemde, waren er **11** gewoon bestelbaar.

Deze repo maakt een betere feed. Het is Vitortho's eigen feed, **byte voor byte**. Alleen
`VoorraadstatusCode` en `VoorraadstatusToelichting` worden per product vervangen door wat
de B2B nu laat zien. Stock Sync hoeft dus alleen een andere URL te lezen: de koppeling
blijft gelijk.

| B2B toont | code | toelichting |
|---|---|---|
| "Uit voorraad leverbaar" + knop Bestellen | 2 | ruim op voorraad |
| "Beperkt in voorraad" + knop Bestellen | 1 | beperkt op voorraad |
| alleen "Houd mij op de hoogte", "Niet in voorraad", "uit assortiment", niet gevonden | 0 | niet op voorraad |

Producten die Vitortho niet meer voert, blijven in de feed met code 0. Ze zijn dan niet
bestelbaar, maar worden niet gearchiveerd; Max beslist later (30-09).

**Nooit in de feed:** B2B-prijzen (inkoop) en inloggegevens. De prijzen blijven die van
Vitortho's openbare feed.

## Feed-URL (Stock Sync, profiel "NOW | Vitortho")

```
https://raw.githubusercontent.com/Maximillian-creator/vitortho-feed/main/vitortho_feed.xml
```

`vitortho_verschillen.csv` somt na elke run op waar de B2B anders zegt dan Vitortho's
eigen feed.

## Schema

2× per dag, **21:37 en 11:37 NL** (zomertijd); GitHub start tot 6 uur te laat, dus ruim vóór Stock Sync (04:00).


Een ronde leest ~323 productpagina's, rustig achter elkaar, in ~5 minuten.

## De rem (er wordt niets weggeschreven als…)

- Vitortho's feed minder dan 250 producten heeft, of afgebroken is;
- het inloggen op de B2B mislukt;
- meer dan 5% van de producten niet te bepalen is (netwerk, sessie weg);
- meer dan 30% niet bestelbaar zou worden (normaal ~3%: dan klopt het lezen niet).

Dan blijft de vorige feed staan, en Nebula ziet een rode run.

## Eenmalig instellen (Max)

1. Maak op GitHub een lege, **publieke** repo `vitortho-feed` (net als de andere
   feeds, anders kan Stock Sync hem niet lezen).
2. Ga naar Settings → Secrets and variables → Actions → New repository secret en maak
   er twee aan:
   - `VITORTHO_GEBRUIKER`: het e-mailadres waarmee je inlogt op vitorthoshop.nl
   - `VITORTHO_WACHTWOORD`: het wachtwoord daarvan
3. Claude Code pusht de code. Daarna: Actions → "Vitortho Feed Updater" → Run workflow.
4. Is die run groen, en ziet `vitortho_verschillen.csv` er goed uit? Zet dan in Stock
   Sync bij "NOW | Vitortho" de bron-URL op de URL hierboven. Aan de koppeling hoeft
   niets te veranderen.

## Lokaal testen (zonder inlog)

```bash
pip install -r requirements.txt pytest
python -m pytest -q test_feed.py
```
