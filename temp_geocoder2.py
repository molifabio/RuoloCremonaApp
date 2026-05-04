import json
import re
import time
import unicodedata
from pathlib import Path

import requests

ROOT = Path(r"c:/Users/Utente/Desktop/Casa/RUOLO/Cremona")
poi_txt = ROOT / "poi.txt"
out_json = ROOT / "poi_cremona.json"
out_missing = ROOT / "poi_not_found.txt"

headers = {"User-Agent": "cremona-quiz/1.0"}
url = "https://nominatim.openstreetmap.org/search"

category_headers = {
    "ENTI",
    "LUOGHI DI CULTO / CIMITERI",
    "HOTEL / RISTORANTI",
    "PRINCIPALI AZIENDE OPERANTI NEL TERRITORIO",
    "ISTITUTI SCOLASTICI / UNIVERSITA",
    "ISTITUTI SCOLASTICI / UNIVERSITÀ",
    "MUSEI / BIBLIOTECHE",
    "STAZIONI / PARCHEGGI",
    "CINEMA / TEATRI",
    "CENTRI SPORTIVI",
    "PALAZZI / EDIFICI STORICI",
    "PARCHI E GIARDINI",
    "ALTRI PUNTI D'INTERESSE",
}

ALIASES = {
    "Provincia sede principale": ["Provincia di Cremona"],
    "Provincia sede porto": ["Provincia di Cremona"],
    "Comune sede principale": ["Comune di Cremona"],
    "Regione Lombardia sede territoriale": ["Regione Lombardia Cremona"],
    "Poste Ufficio Centrale": ["Poste Italiane Cremona", "ufficio postale centrale Cremona"],
    "Agenzia delle Entrate Ufficio del Registro": ["Agenzia delle Entrate Cremona"],
    "Agenzia del Territorio (Catasto)": ["Catasto Cremona", "Agenzia Entrate Territorio Cremona"],
    "ACI e PRA": ["ACI Cremona", "PRA Cremona"],
    "Motorizzazione Civile": ["Motorizzazione Civile Cremona"],
    "Tribunale": ["Tribunale di Cremona"],
    "Prefettura": ["Prefettura di Cremona"],
    "Questura": ["Questura di Cremona"],
    "Questura ufficio stranieri": ["Questura di Cremona ufficio immigrazione"],
    "Carabinieri Comando Stazione": ["Comando Stazione Carabinieri Cremona"],
    "Polizia Stradale": ["Polizia Stradale Cremona"],
    "Polizia Locale del Comune": ["Polizia Locale Cremona"],
    "ATS Val Padana (ASL)": ["ATS Val Padana Cremona"],
    "Geriatrico Soldi (Cremona Solidale)": ["Cremona Solidale"],
    "Clinica San Camillo": ["San Camillo Cremona"],
    "Clinica Figlie di San Camillo": ["Figlie di San Camillo Cremona"],
    "Clinica Ancelle della Carità": ["Ancelle della Carita Cremona"],
    "ARPA (Agenzia Regionale Protezione Ambiente)": ["ARPA Lombardia Cremona"],
    "Carcere": ["Casa Circondariale Cremona", "carcere Cremona"],
    "Ufficio anagrafe comunale": ["anagrafe Cremona"],
    "Chiesa di San Michele Vetere": ["San Michele Vetere Cremona"],
    "Chiesa di Pietro al Po": ["San Pietro al Po Cremona"],
    "Chiesa di Cristo Re": ["Cristo Re Cremona"],
    "Chiesa di Sant'Imerio": ["Sant Imerio Cremona"],
    "Chiesa di Sant'Omobono": ["Sant Omobono Cremona"],
    "Dellearti Design Hotel": ["Dellearti Design Hotel Cremona"],
    "Ristorante Centrale": ["Ristorante Centrale Cremona"],
    "Osteria del Melograno": ["Osteria del Melograno Cremona"],
    "Ristorante Chiave di Bacco": ["Chiave di Bacco Cremona"],
    "Kandoo": ["Kandoo Cremona"],
    "Pizzeria La Bersagliera": ["La Bersagliera Cremona"],
    "Pizzeria La Pendola": ["La Pendola Cremona"],
    "Centro Commerciale Cremona Po": ["CremonaPo"],
    "Mediaword": ["MediaWorld Cremona"],
    "Concessionaria Renault - Nissan": ["Renault Nissan Cremona"],
    "Istituto d'Istruzione Superiore Ghisleri": ["IIS Ghisleri Cremona"],
    "Istituto d'Istruzione Superiore Stanga": ["IIS Stanga Cremona"],
    "Istituto d'Istruzione Einaudi": ["Einaudi Cremona"],
    "Liceo Sofonisba Anguissola sede via Palestro": ["Liceo Anguissola Cremona"],
    "Liceo Vida": ["Liceo Vida Cremona"],
    "Politecnico di Milano Polo territoriale di Cremona": ["Politecnico di Milano Cremona"],
    "Università degli studi di Brescia sede di Cremona - Infermieristica": ["Universita Brescia infermieristica Cremona"],
    "Scuola media Virgilio": ["Scuola Virgilio Cremona"],
    "Stazione FS": ["Stazione di Cremona"],
    "Parcheggio Autosilo Massarotti": ["Autosilo Massarotti Cremona"],
    "Parcheggio Villa Glori": ["Parcheggio Villa Glori Cremona"],
    "Parcheggio Santa Tecla": ["Parcheggio Santa Tecla Cremona"],
    "Parcheggio Saba Marconi": ["Parcheggio Saba Marconi Cremona"],
    "Teatro Monteverdi": ["Teatro Monteverdi Cremona"],
    "Teatro/Cinema Filodrammatici": ["Cinema Filo Cremona"],
    "Cinema Chaplin": ["Cinema Chaplin Cremona"],
    "Cinema Arena Giardino": ["Arena Giardino Cremona"],
    "Anteo SpazioCinema": ["Anteo Cremona Po"],
    "Canottieri Baldesio": ["Canottieri Baldesio Cremona"],
    "Centro Sportivo Giovanni Arvedi - US Cremonese": ["Centro Sportivo Arvedi Cremona"],
    "Palestra Spettacolo Accademia Boxe": ["Accademia Boxe Cremona"],
    "Palazzetto dello Sport": ["Palazzetto dello Sport Cremona"],
    "Campo di Calcio Soldi": ["Campo Soldi Cremona"],
    "USC Cremonese": ["US Cremonese"],
    "Crossodromo di Cremona - Moto Club": ["crossodromo Cremona"],
    "Golf Il Torrazzo": ["Golf il Torrazzo Cremona"],
    "Palazzo Vescovile": ["Palazzo Vescovile Cremona"],
    "Palazzo Zaccaria Pallavicino": ["Palazzo Zaccaria Pallavicino Cremona"],
    "Palazzo Cattaneo": ["Palazzo Cattaneo Cremona"],
    "Casello autostrada": ["casello Cremona autostrada"],
    "Porto Canale o Porto Interno": ["porto canale Cremona", "porto interno Cremona"],
    "Ponte sul Po": ["ponte sul Po Cremona"],
}

def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.upper().split())


def parse_poi_lines(text: str) -> list[str]:
    items = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        n = norm(line)
        if n.startswith("PUNTI DINTERESSE") or n.startswith("PUNTI D'INTERESSE"):
            continue
        if n in category_headers:
            continue
        items.append(line)
    return items


def geocode_try(query: str, bounded: bool):
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 1,
        "countrycodes": "it",
    }
    if bounded:
        params["bounded"] = 1
        params["viewbox"] = "9.98,45.17,10.08,45.10"

    resp = requests.get(url, params=params, headers=headers, timeout=12)
    resp.raise_for_status()
    arr = resp.json()
    return arr[0] if arr else None


def geocode_name(name: str):
    candidates = [
        f"{name}, Cremona, Lombardia, Italia",
        f"{name}, Cremona, Italia",
        name,
    ]
    for alias in ALIASES.get(name, []):
        candidates.insert(0, f"{alias}, Cremona, Italia")
        candidates.insert(0, alias)

    seen = set()
    for q in candidates:
        q = " ".join(q.split())
        if q in seen:
            continue
        seen.add(q)
        for bounded in (True, False):
            try:
                best = geocode_try(q, bounded)
                if best:
                    return {
                        "name": name,
                        "lat": float(best["lat"]),
                        "lon": float(best["lon"]),
                    }
            except Exception:
                pass
            time.sleep(0.35)
    return None

poi_names = parse_poi_lines(poi_txt.read_text(encoding="utf-8"))

found = []
missing = []
for i, name in enumerate(poi_names, start=1):
    res = geocode_name(name)
    if res:
        found.append(res)
    else:
        missing.append(name)
    if i % 25 == 0:
        print(f"Progress2: {i}/{len(poi_names)}")
    time.sleep(0.35)

out_json.write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
out_missing.write_text("\n".join(missing), encoding="utf-8")

print(f"TOTAL: {len(poi_names)}")
print(f"FOUND: {len(found)}")
print(f"NOT_FOUND: {len(missing)}")
print("MISSING_LIST_START")
for m in missing:
    print(m)
print("MISSING_LIST_END")
