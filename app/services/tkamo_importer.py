"""
TKAMO-Import: Turnierdaten von tkamo.ch anhand der AIS-Nummer laden.

URL-Format: https://www.tkamo.ch/?lang=de&n0=agenda&n1=&detail=<ais_nummer>

Extrahierte Felder:
  Datum, Ort, Nr. und Sektion, Meldebeginn, Meldeschluss,
  Max. Teilnehmer, Startgeld, Anzahl Indoor/Outdoor-Ringe,
  Läufigkeit, Kategorien und Klassen, Wettbewerbe, Richter,
  Meldestelle (inkl. E-Mail), Prüfungsleiter
"""

import re
import requests
from datetime import datetime, time


TKAMO_BASE = "https://www.tkamo.ch/?lang=de&n0=agenda&n1=&detail={}"


def tkamo_url_for(ais_number: int) -> str:
    return TKAMO_BASE.format(ais_number)


def _parse_ch_date(date_str: str):
    """DD.MM.YYYY → date-Objekt oder None."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def _extract_email(text: str) -> str | None:
    """Findet erste E-Mail-Adresse in einem Text."""
    m = re.search(r'E-Mail:\s*([^\s,;]+)', text, re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip('.')
    m2 = re.search(r'[\w.+-]+@[\w-]+\.[a-z]{2,}', text, re.IGNORECASE)
    return m2.group(0) if m2 else None


def _extract_phone(text: str) -> str | None:
    """Findet erste Schweizer Telefonnummer in einem Text."""
    m = re.search(r'(?:\+41|0041|0)[0-9\s/().-]{7,15}', text)
    if m:
        return re.sub(r'\s+', ' ', m.group()).strip()
    return None


def _extract_name(text: str) -> str:
    """Gibt nur den Namensteil zurück (erstes Komma-Segment, Telefon/E-Mail entfernt)."""
    name = text.split(",")[0].strip()
    name = re.sub(r'[\w.+-]+@[\w-]+\.[a-z]{2,}', '', name)
    name = re.sub(r'(?:\+41|0041|0)[0-9\s/().-]{7,}', '', name)
    return name.strip()


def fetch_tkamo_event(ais_number: int) -> dict:
    """
    Lädt die TKAMO-Eventseite und gibt ein Dict mit den geparsten Feldern zurück.
    Wirft requests.RequestException bei Netzwerkfehlern.
    """
    url = tkamo_url_for(ais_number)
    resp = requests.get(url, timeout=15, headers={"Accept-Language": "de-CH,de;q=0.9"})
    resp.raise_for_status()

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        return _parse_soup(soup, url)
    except ImportError:
        # Fallback ohne BeautifulSoup: reiner Textansatz
        return _parse_text(resp.text, url)


def _parse_soup(soup, url: str) -> dict:
    """BeautifulSoup-basierter Parser: liest Label/Wert aus Tabellenzeilen."""
    rows: dict[str, str] = {}
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) >= 2:
            label = cells[0].get_text(" ", strip=True)
            value = cells[1].get_text(" ", strip=True)
            if label:
                rows[label] = value

    # Auch Definition-Listen abdecken (dl/dt/dd)
    dts = soup.find_all("dt")
    for dt in dts:
        dd = dt.find_next_sibling("dd")
        if dd:
            rows[dt.get_text(strip=True)] = dd.get_text(" ", strip=True)

    return _map_rows(rows, url)


def _parse_text(html: str, url: str) -> dict:
    """Textbasierter Fallback-Parser mittels Regex auf dem HTML-Text."""
    # Tags entfernen
    clean = re.sub(r'<[^>]+>', ' ', html)
    clean = re.sub(r'\s+', ' ', clean)

    rows: dict[str, str] = {}

    LABELS = [
        "Datum", "Ort", "Nr. und Sektion", "Meldebeginn", "Meldeschluss",
        "Max. Teilnehmer", "Startgeld", "Anzahl Indoor-Ringe",
        "Anzahl Outdoor-Ringe", "Läufigkeit", "Kategorien und Klassen",
        "Wettbewerbe", "Richter", "Meldestelle", "Prüfungsleiter",
    ]
    for i, label in enumerate(LABELS):
        next_labels = LABELS[i + 1:i + 3]
        stop = "|".join(re.escape(l) for l in next_labels) if next_labels else r'$'
        pattern = re.escape(label) + r'\s+(.*?)(?=' + stop + r'|$)'
        m = re.search(pattern, clean, re.IGNORECASE)
        if m:
            rows[label] = m.group(1).strip()

    return _map_rows(rows, url)


def _map_rows(rows: dict[str, str], url: str) -> dict:
    """Wandelt Label→Wert Dict in strukturiertes Ergebnis um."""
    result: dict = {"tkamo_url": url}

    # Datum
    if "Datum" in rows:
        result["datum_str"] = rows["Datum"]
        result["datum"] = _parse_ch_date(rows["Datum"])

    # Ort
    if "Ort" in rows:
        result["ort"] = rows["Ort"]

    # Sektion / Klubname
    if "Nr. und Sektion" in rows:
        raw = rows["Nr. und Sektion"]
        result["sektion_raw"] = raw
        m = re.match(r'^\[?\d+\]?\s*(.*)', raw)
        result["club_name"] = m.group(1).strip() if m else raw

    # Meldedaten
    if "Meldebeginn" in rows:
        result["meldebeginn"] = _parse_ch_date(rows["Meldebeginn"])
    if "Meldeschluss" in rows:
        result["meldeschluss"] = _parse_ch_date(rows["Meldeschluss"])

    # Numerische Felder
    if "Max. Teilnehmer" in rows:
        m = re.search(r'\d+', rows["Max. Teilnehmer"])
        if m:
            result["max_participants"] = int(m.group())

    if "Startgeld" in rows:
        m = re.search(r'[\d.,]+', rows["Startgeld"])
        if m:
            try:
                result["entry_fee"] = float(m.group().replace(",", "."))
            except ValueError:
                pass

    if "Anzahl Indoor-Ringe" in rows:
        m = re.search(r'\d+', rows["Anzahl Indoor-Ringe"])
        result["indoor_rings"] = int(m.group()) if m else 0

    if "Anzahl Outdoor-Ringe" in rows:
        m = re.search(r'\d+', rows["Anzahl Outdoor-Ringe"])
        result["outdoor_rings"] = int(m.group()) if m else 0

    # Läufigkeit
    if "Läufigkeit" in rows:
        result["laeufigkeit"] = rows["Läufigkeit"].strip().lower() in (
            "ja", "yes", "oui", "1", "true"
        )

    # Kategorien & Klassen
    if "Kategorien und Klassen" in rows:
        result["kategorien"] = rows["Kategorien und Klassen"]

    # Wettbewerbe / Disziplinen
    if "Wettbewerbe" in rows:
        result["wettbewerbe"] = rows["Wettbewerbe"]

    # Richter
    if "Richter" in rows:
        result["richter"] = rows["Richter"]

    # Meldestelle → E-Mail + Telefon
    if "Meldestelle" in rows:
        result["meldestelle"] = rows["Meldestelle"]
        email = _extract_email(rows["Meldestelle"])
        if email:
            result["contact_email"] = email
        phone = _extract_phone(rows["Meldestelle"])
        if phone:
            result["contact_phone"] = phone

    # Prüfungsleiter → Name, E-Mail, Telefon
    if "Prüfungsleiter" in rows:
        raw_pl = rows["Prüfungsleiter"]
        result["pruefungsleiter_raw"] = raw_pl
        result["pruefungsleiter_name"] = _extract_name(raw_pl)
        # E-Mail aus Prüfungsleiter hat Vorrang (direkter Ansprechpartner)
        email_pl = _extract_email(raw_pl)
        if email_pl:
            result["contact_email"] = email_pl
        phone_pl = _extract_phone(raw_pl)
        if phone_pl:
            result["contact_phone"] = phone_pl

    return result


# ── Auf Event-Objekt anwenden ─────────────────────────────────────────────────

def apply_to_event(event, data: dict) -> list[str]:
    """
    Schreibt die TKAMO-Daten in das Event-Objekt.
    Gibt eine Liste von angewendeten Änderungen zurück.
    """
    changes = []

    if data.get("datum"):
        d = data["datum"]
        event.starts_at = datetime.combine(d, time(8, 0))
        if not event.ends_at:
            event.ends_at = datetime.combine(d, time(18, 0))
        changes.append(f"Datum: {d.strftime('%d.%m.%Y')}")

    if data.get("ort"):
        event.location = data["ort"]
        changes.append(f"Ort: {data['ort']}")

    if data.get("meldebeginn"):
        event.registration_open_at = datetime.combine(data["meldebeginn"], time(0, 0))
        changes.append(f"Meldebeginn: {data['meldebeginn'].strftime('%d.%m.%Y')}")

    if data.get("meldeschluss"):
        event.registration_close_at = datetime.combine(data["meldeschluss"], time(23, 59))
        changes.append(f"Meldeschluss: {data['meldeschluss'].strftime('%d.%m.%Y')}")

    if data.get("max_participants"):
        event.max_participants = data["max_participants"]
        changes.append(f"Max. Teilnehmer: {data['max_participants']}")

    if data.get("entry_fee") is not None:
        event.entry_fee = data["entry_fee"]
        changes.append(f"Startgeld: CHF {data['entry_fee']:.2f}")

    indoor  = data.get("indoor_rings", 0)
    outdoor = data.get("outdoor_rings", 0)
    if indoor or outdoor:
        event.ring_count = max(indoor + outdoor, 1)
        changes.append(f"Ringe: {indoor} Indoor, {outdoor} Outdoor")

    if "laeufigkeit" in data:
        event.allows_bitches_in_season = data["laeufigkeit"]
        changes.append(f"Läufigkeit: {'Ja' if data['laeufigkeit'] else 'Nein'}")

    if data.get("kategorien"):
        event.tkamo_categories = data["kategorien"]
        changes.append(f"Kategorien: {data['kategorien']}")

    if data.get("wettbewerbe"):
        event.tkamo_disciplines = data["wettbewerbe"]
        changes.append(f"Wettbewerbe: {data['wettbewerbe']}")

    if data.get("richter"):
        event.tkamo_judges = data["richter"]
        changes.append(f"Richter: {data['richter']}")

    if data.get("contact_email"):
        event.tkamo_contact_email = data["contact_email"]
        changes.append(f"Kontakt-E-Mail: {data['contact_email']}")

    if data.get("pruefungsleiter_name") and not event.pruefungsleiter:
        event.pruefungsleiter = data["pruefungsleiter_name"]
        changes.append(f"Prüfungsleiter: {data['pruefungsleiter_name']}")

    event.tkamo_imported_at = datetime.utcnow()
    return changes
