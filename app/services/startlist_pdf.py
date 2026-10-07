"""Erzeugt druckfertige Startlisten-PDFs (ein PDF pro Kategorie/Klasse) und
bündelt sie als ZIP – ein Download statt vieler Browser-Druckdialoge.

Bewusst mit fpdf2 (pure Python, keine System-Abhängigkeiten, berührt den
cryptography-Pin des DB-Treibers nicht) statt eines HTML→PDF-Renderers.
Layout angelehnt an die Startliste der AgilitySoftware.
"""
import io
import re
import zipfile

from flask_babel import gettext as _
from fpdf import FPDF
from fpdf.fonts import FontFace
from PIL import Image

# Logos werden nur klein im PDF-Kopf gezeigt (max. 30mm breit, siehe _HEADER_H
# weiter unten für die Höhe). Ohne Downscale bettet fpdf2 die Originaldatei
# 1:1 ein (hier z.B. 5907x5059px) → >1MB pro PDF allein durchs Logo.
# Ziel-Auflösung grosszügig für Druckqualität bei ~30mm Breite (300dpi ≈
# 350px), danach als PNG neu komprimiert.
_LOGO_MAX_PX = 400


def _shrink_logo(path):
    """(buffer, breite_px, höhe_px) oder None. Pixel-Grösse wird gebraucht, um
    das Logo später seitenrichtig (ohne Verzerrung) ins PDF einzupassen."""
    if not path:
        return None
    try:
        img = Image.open(path)
        img.thumbnail((_LOGO_MAX_PX, _LOGO_MAX_PX), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf, img.width, img.height
    except Exception:
        return None


def _fit_box(px_w, px_h, max_w_mm, max_h_mm):
    """Skaliert (px_w, px_h) proportional so gross wie möglich in die Box
    max_w_mm x max_h_mm hinein, ohne das Seitenverhältnis zu verändern."""
    scale = min(max_w_mm / px_w, max_h_mm / px_h)
    return px_w * scale, px_h * scale


# Höhe des Kopfbereichs (Titel/Untertitel/Meta/Anzahl, siehe _render_block_pdf)
# – Logos dürfen bis zu dieser Höhe gross sein (Breite bleibt separat begrenzt).
_HEADER_H = 27

# Zielgrösse ~30 Datenzeilen auf der ersten Seite (gleiche Grössenordnung wie
# die Rangliste-PDF der AgilitySoftware). eph (272mm) - Kopfbereich (27mm) im
# Verhältnis zur Zeilenzahl (Header-Zeile + 30 Datenzeilen) ergibt die Höhe.
_LINE_HEIGHT = 7.9

# Kerntypografie → ASCII/Latin-1, damit die Core-Fonts (Latin-1) keine
# Unicode-Zeichen aus Namen stolpern lassen (z.B. „Shy’m", Gedankenstriche).
_TYPO = {
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", " ": " ",
}


def _s(text) -> str:
    text = "" if text is None else str(text)
    for bad, good in _TYPO.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", "replace").decode("latin-1")


def _slug(text) -> str:
    text = _s(text)
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text or "Block"


def _block_label(group) -> str:
    cat = group["category_code"] or ""
    cls = group["class_level"]
    return f"{cat} - {_('Klasse')} {cls}" if cls else cat


# Spalten (key, Header, min-Breite mm, Schrumpf-Priorität – 1 schrumpft als
# erstes). "start_no" schrumpft nicht mit (eigene kleine, feste Breite).
def _data_columns():
    return [
        ("handler_name", _("Hundeführer"), 30, 3),
        ("dog_name", _("Hund"), 25, 3),
        ("breed", _("Rasse"), 18, 2),
        ("club_name", _("Verein"), 16, 1),
    ]
_COL_PAD = 4  # mm Puffer je Spalte (Zellenrand + Reserve für Kürzung)


def _text_width(pdf, text, bold=False):
    pdf.set_font("Helvetica", "B" if bold else "", 9)
    return pdf.get_string_width(text)


def _truncate(pdf, text, max_w):
    """Kürzt text mit "..." auf max_w (mm), Font muss bereits gesetzt sein.
    "…" (Unicode-Ellipse) kann der Helvetica-Core-Font nicht (nur Latin-1) –
    deshalb drei ASCII-Punkte, wie auch _TYPO es für Fliesstext macht."""
    if pdf.get_string_width(text) <= max_w:
        return text
    ell = "..."
    while text and pdf.get_string_width(text + ell) > max_w:
        text = text[:-1]
    return (text + ell) if text else ell


def _plan_columns(pdf, rows, has_numbers, available_mm):
    """Berechnet Spaltenbreiten: Start-Nr. klein & fix, die übrigen Spalten
    inhaltsbasiert ('dynamisch'), die Restbreite wird proportional verteilt.
    Reicht der Platz nicht, wird in Prioritätsreihenfolge geschrumpft (Verein
    zuerst) – der Text wird danach pro Zelle auf die finale Breite gekürzt,
    damit keine Zeile umbricht (einheitliche Zeilenhöhe)."""
    cols = []
    if has_numbers:
        nr_header = _s(_("Nr."))
        nr_values = [_s(row["start_no"]) for row in rows]
        nr_w = max([_text_width(pdf, nr_header, bold=True)]
                   + [_text_width(pdf, v) for v in nr_values]) + _COL_PAD
        cols.append({"key": "start_no", "header": nr_header, "width": nr_w,
                     "fixed": True})

    dynamic = []
    for key, header, min_w, prio in _data_columns():
        header = _s(header)
        values = [_s(row[key] or "") for row in rows]
        natural = max([_text_width(pdf, header, bold=True)]
                      + [_text_width(pdf, v) for v in values]) + _COL_PAD
        dynamic.append({"key": key, "header": header,
                         "width": max(natural, min_w + _COL_PAD),
                         "min": min_w + _COL_PAD, "prio": prio, "fixed": False})

    fixed_total = sum(c["width"] for c in cols)
    dyn_total = sum(c["width"] for c in dynamic)
    remaining = available_mm - fixed_total

    if dyn_total > remaining:
        deficit = dyn_total - remaining
        for prio in sorted({c["prio"] for c in dynamic}):
            group = [c for c in dynamic if c["prio"] == prio]
            while deficit > 0.01 and any(c["width"] > c["min"] for c in group):
                shrinkable = [c for c in group if c["width"] > c["min"]]
                share = min(deficit / len(shrinkable), *(c["width"] - c["min"] for c in shrinkable))
                for c in shrinkable:
                    c["width"] -= share
                    deficit -= share
            if deficit <= 0.01:
                break
    elif dyn_total < remaining:
        extra = remaining - dyn_total
        for c in dynamic:
            c["width"] += extra * (c["width"] / dyn_total)

    return cols + dynamic


def _render_block_pdf(event, group, has_numbers, logo_paths) -> bytes:
    event_logo, club_logo = logo_paths
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(10, 10, 10)
    pdf.add_page()

    # ── Kopf mit Logos ───────────────────────────────────────────────
    # Box max. 30mm breit, bis zu _HEADER_H hoch – Seitenverhältnis bleibt
    # erhalten (_fit_box), sonst verzerrt fpdf2 bei fix vorgegebenem w UND h.
    top = pdf.get_y()
    if club_logo:
        buf, px_w, px_h = club_logo
        buf.seek(0)
        w, h = _fit_box(px_w, px_h, 30, _HEADER_H)
        try:
            pdf.image(buf, x=10, y=top, w=w, h=h)
        except Exception:
            pass
    if event_logo:
        buf, px_w, px_h = event_logo
        buf.seek(0)
        w, h = _fit_box(px_w, px_h, 30, _HEADER_H)
        try:
            pdf.image(buf, x=210 - 10 - w, y=top, w=w, h=h)
        except Exception:
            pass
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, _s(event.name), align="C", new_x="LMARGIN", new_y="NEXT")
    sub = _s(f"{_('Startliste') if has_numbers else _('Meldeliste')} {_block_label(group)}")
    pdf.set_font("Helvetica", "BI", 12)
    pdf.cell(0, 7, sub, align="C", new_x="LMARGIN", new_y="NEXT")
    meta = []
    if getattr(event, "starts_at", None):
        meta.append(event.starts_at.strftime("%d.%m.%Y"))
    if getattr(event, "location", None):
        meta.append(_s(event.location))
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, " · ".join(meta), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, _s(f"{_('Anzahl Teams')}: {group['count']}"), align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # ── Tabelle ──────────────────────────────────────────────────────
    # Start-Nr. klein & fix, die übrigen Spalten inhaltsbasiert/dynamisch;
    # Text wird je Zelle auf die finale Breite gekürzt (keine Zeile umbricht
    # mehr → einheitliche Zeilenhöhe über die ganze Tabelle).
    columns = _plan_columns(pdf, group["rows"], has_numbers, pdf.epw)
    widths = [c["width"] for c in columns]

    pdf.set_font("Helvetica", "", 9)
    with pdf.table(col_widths=widths, text_align="LEFT", line_height=_LINE_HEIGHT,
                   first_row_as_headings=True,
                   headings_style=FontFace(emphasis="BOLD")) as table:
        head = table.row()
        for col in columns:
            head.cell(col["header"])
        for row in group["rows"]:
            tr = table.row()
            for col in columns:
                pdf.set_font("Helvetica", "", 9)
                value = _s(row["start_no"]) if col["key"] == "start_no" else _s(row[col["key"]] or "")
                tr.cell(_truncate(pdf, value, col["width"] - _COL_PAD))

    return bytes(pdf.output())


def build_startlist_zip(event, groups, has_numbers, logo_paths):
    """Gibt (zip_bytes, filename) zurück – ein PDF je Block im Archiv."""
    event_logo, club_logo = logo_paths
    shrunk_logos = (_shrink_logo(event_logo), _shrink_logo(club_logo))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, group in enumerate(groups, start=1):
            pdf_bytes = _render_block_pdf(event, group, has_numbers, shrunk_logos)
            name = f"{i:02d}_{_slug(_block_label(group))}.pdf"
            zf.writestr(name, pdf_bytes)
    buf.seek(0)
    kind = _("Startlisten") if has_numbers else _("Meldelisten")
    return buf.getvalue(), f"{_slug(kind)}_{_slug(event.name)}.zip"
