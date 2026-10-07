"""Erzeugt druckfertige Startlisten-PDFs (ein PDF pro Kategorie/Klasse) und
bündelt sie als ZIP – ein Download statt vieler Browser-Druckdialoge.

Bewusst mit fpdf2 (pure Python, keine System-Abhängigkeiten, berührt den
cryptography-Pin des DB-Treibers nicht) statt eines HTML→PDF-Renderers.
Layout angelehnt an die Startliste der AgilitySoftware.
"""
import io
import re
import zipfile

from fpdf import FPDF
from fpdf.fonts import FontFace

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
    return f"{cat} - Klasse {cls}" if cls else cat


def _render_block_pdf(event, group, has_numbers, logo_paths) -> bytes:
    event_logo, club_logo = logo_paths
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(10, 10, 10)
    pdf.add_page()

    # ── Kopf mit Logos ───────────────────────────────────────────────
    top = pdf.get_y()
    if club_logo:
        try:
            pdf.image(club_logo, x=10, y=top, h=16)
        except Exception:
            pass
    if event_logo:
        try:
            pdf.image(event_logo, x=210 - 10 - 30, y=top, h=16, w=30)
        except Exception:
            pass
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, _s(event.name), align="C", new_x="LMARGIN", new_y="NEXT")
    sub = _s(f"{'Startliste' if has_numbers else 'Meldeliste'} {_block_label(group)}")
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
    pdf.cell(0, 5, _s(f"Anzahl Teams: {group['count']}"), align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # ── Tabelle ──────────────────────────────────────────────────────
    if has_numbers:
        headers = ["Start-Nr.", "Hundeführer", "Hund", "Rasse", "Verein"]
        widths = (18, 50, 45, 40, 37)
    else:
        headers = ["Hundeführer", "Hund", "Rasse", "Verein"]
        widths = (55, 50, 45, 40)

    pdf.set_font("Helvetica", "", 9)
    with pdf.table(col_widths=widths, text_align="LEFT", line_height=6,
                   first_row_as_headings=True,
                   headings_style=FontFace(emphasis="BOLD")) as table:
        head = table.row()
        for h in headers:
            head.cell(_s(h))
        for row in group["rows"]:
            tr = table.row()
            if has_numbers:
                tr.cell(_s(row["start_no"]))
            tr.cell(_s(row["handler_name"]))
            tr.cell(_s(row["dog_name"]))
            tr.cell(_s(row["breed"] or ""))
            tr.cell(_s(row["club_name"] or ""))

    return bytes(pdf.output())


def build_startlist_zip(event, groups, has_numbers, logo_paths):
    """Gibt (zip_bytes, filename) zurück – ein PDF je Block im Archiv."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, group in enumerate(groups, start=1):
            pdf_bytes = _render_block_pdf(event, group, has_numbers, logo_paths)
            name = f"{i:02d}_{_slug(_block_label(group))}.pdf"
            zf.writestr(name, pdf_bytes)
    buf.seek(0)
    kind = "Startlisten" if has_numbers else "Meldelisten"
    return buf.getvalue(), f"{kind}_{_slug(event.name)}.zip"
