"""Rendu PDF du bulletin de paie (A4 portrait), calqué sur le PDF de référence.

Ce module **n'effectue aucun calcul de paie** : il met en forme les montants déjà
calculés et figés dans l'enregistrement de paie (résultat, cumuls, paramètres et fiches
copiés au moment du calcul). Les polices standard (Helvetica, encodage WinAnsi) couvrent
tous les caractères accentués du français.
"""

from __future__ import annotations

import calendar
import io
from datetime import datetime

from reportlab.lib.colors import Color, HexColor, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from src.formatting import anciennete, fmt_date, fmt_days, fmt_money, fmt_rate
from src.models.payroll import MOIS_FR, STATUT_CLOTUREE

PAGE_W, PAGE_H = A4
LEFT, RIGHT = 28.5, 567.0
WIDTH = RIGHT - LEFT
HEADER_FILL = HexColor("#E6F2FA")
BRAND = HexColor("#1F3864")
GRID = 0.6
FONT, BOLD, BOLD_ITALIC = "Helvetica", "Helvetica-Bold", "Helvetica-BoldOblique"
ROW_H = 15.5
MIN_FONT = 5.5

# Colonnes du tableau principal (abscisses des séparateurs, d'après le PDF de référence).
COLS = (LEFT, 232.5, 289.0, 340.0, 396.5, 453.5, 510.0, RIGHT)


def bulletin_filename(record) -> str:
    """bulletin_2026-09_0001.pdf ; suffixe _v2, _v3… pour une rectification."""
    matricule = (record.employee_snapshot or {}).get("matricule", str(record.employee_id))
    suffix = f"_v{record.version}" if record.version > 1 else ""
    return f"bulletin_{record.year:04d}-{record.month:02d}_{matricule}{suffix}.pdf"


class _Page:
    """Petites primitives de dessin en coordonnées « depuis le haut »."""

    def __init__(self, canvas: Canvas):
        self.c = canvas

    def y(self, top: float) -> float:
        return PAGE_H - top

    def fit(self, text: str, font: str, size: float, max_width: float) -> tuple[str, float]:
        """Réduit la police puis tronque avec « … » pour ne jamais déborder."""
        text = text or ""
        while size > MIN_FONT and stringWidth(text, font, size) > max_width:
            size -= 0.25
        if stringWidth(text, font, size) > max_width:
            while text and stringWidth(text + "…", font, size) > max_width:
                text = text[:-1]
            text += "…"
        return text, size

    def text(self, x: float, baseline: float, text: str, font: str = FONT, size: float = 8,
             align: str = "left", max_width: float | None = None, color=black) -> None:
        if not text:
            return
        if max_width is not None:
            text, size = self.fit(text, font, size, max_width)
        self.c.setFillColor(color)
        self.c.setFont(font, size)
        if align == "right":
            self.c.drawRightString(x, self.y(baseline), text)
        elif align == "center":
            self.c.drawCentredString(x, self.y(baseline), text)
        else:
            self.c.drawString(x, self.y(baseline), text)
        self.c.setFillColor(black)

    def rect(self, x0: float, top: float, x1: float, bottom: float, fill=None) -> None:
        self.c.setLineWidth(GRID)
        if fill is not None:
            self.c.setFillColor(fill)
        self.c.rect(x0, self.y(bottom), x1 - x0, bottom - top,
                    stroke=1, fill=1 if fill is not None else 0)
        self.c.setFillColor(black)

    def vline(self, x: float, top: float, bottom: float) -> None:
        self.c.setLineWidth(GRID)
        self.c.line(x, self.y(top), x, self.y(bottom))

    def hline(self, x0: float, x1: float, top: float) -> None:
        self.c.setLineWidth(GRID)
        self.c.line(x0, self.y(top), x1, self.y(top))

    def label_value(self, x: float, baseline: float, label: str, value: str, width: float) -> None:
        """« Libellé : valeur » sur une seule ligne, sans débordement."""
        label = f"{label} : "
        lw = stringWidth(label, BOLD, 7.5)
        self.text(x, baseline, label, BOLD, 7.5)
        self.text(x + lw, baseline, value, FONT, 7.5, max_width=max(width - lw, 10))


def render_bulletin(record, logo: bytes | None = None, provisional: bool = False) -> bytes:
    """Produit le PDF d'une paie calculée (record : `PayslipRecord`)."""
    if record.result is None or record.cumuls is None or record.parameters is None:
        raise ValueError("La paie doit être calculée avant l'édition du bulletin.")
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=A4, pageCompression=1)
    emp = record.employee_snapshot or {}
    mois = MOIS_FR[record.month - 1]
    canvas.setTitle(f"Bulletin de paie {mois} {record.year} - {emp.get('matricule', '')}")
    canvas.setAuthor((record.company_snapshot or {}).get("raison_sociale", ""))
    canvas.setSubject("Bulletin de paie")
    page = _Page(canvas)

    _draw_company(page, record.company_snapshot or {}, logo)
    _draw_identity(page, record, emp, mois)
    _draw_conges(page, record.result)
    table_bottom = _draw_main_table(page, record)
    cumuls_bottom = _draw_cumuls(page, record, mois, table_bottom + 6)
    _draw_footer(page, record, max(cumuls_bottom + 14, 768.0))
    if provisional:
        _draw_watermark(page)
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


# --- Blocs -----------------------------------------------------------------------------

def _draw_company(page: _Page, company: dict, logo: bytes | None) -> None:
    text_right = RIGHT
    if logo:
        try:
            image = ImageReader(io.BytesIO(logo))
            iw, ih = image.getSize()
            h = 40.0
            w = min(h * iw / ih, 120.0)
            h = w * ih / iw
            page.c.drawImage(image, RIGHT - w, page.y(14 + h), w, h, mask="auto")
            text_right = RIGHT - w - 8
        except Exception:  # logo illisible : le bulletin reste éditable sans logo
            pass
    width = text_right - LEFT
    page.text(LEFT, 26, company.get("raison_sociale", ""), BOLD_ITALIC, 13, max_width=width)
    address = " - ".join(v for v in (company.get("adresse", ""), company.get("ville", "")) if v)
    page.text(LEFT, 36, address, FONT, 7.5, max_width=width)
    ids = []
    for key, label in (("ice", "ICE"), ("cnss_employeur", "N° CNSS employeur"), ("rc", "RC"),
                       ("identifiant_fiscal", "IF")):
        if company.get(key):
            ids.append(f"{label} : {company[key]}")
    page.text(LEFT, 45, "   -   ".join(ids), FONT, 7.5, max_width=width)


def _draw_identity(page: _Page, record, emp: dict, mois: str) -> None:
    top, title_bottom, bottom = 52.0, 75.0, 194.0
    split = 212.5
    page.rect(LEFT, top, RIGHT, bottom)
    page.rect(LEFT, top, split, title_bottom, fill=HEADER_FILL)
    page.rect(split, top, RIGHT, title_bottom, fill=HEADER_FILL)
    page.vline(split, title_bottom, bottom)
    page.text((LEFT + split) / 2, 67, f"BULLETIN DE PAIE : {mois.upper()} {record.year}", BOLD, 11,
              align="center", max_width=split - LEFT - 8)
    nom = f"{emp.get('nom', '').upper()}  {emp.get('prenom', '').upper()}".strip()
    page.text(split + 4, 69, nom, BOLD, 15, max_width=RIGHT - split - 8)

    # Bloc gauche : période et références de la paie.
    last_day = _last_day(record.year, record.month)
    left_lines = [
        ("Période", f"du 01/{record.month:02d}/{record.year} au {last_day:02d}/{record.month:02d}/{record.year}"),
        ("Mode de paiement", emp.get("mode_paiement", "")),
        ("Version", f"{record.version}" + (" (rectificative)" if record.replaces_id else "")),
    ]
    for i, (label, value) in enumerate(left_lines):
        page.label_value(LEFT + 4, 92 + i * 13, label, value, split - LEFT - 8)

    # Bloc droit : identité, trois colonnes comme le modèle.
    x1, x2, x3 = split + 4, 334.0, 452.0
    w1, w2, w3 = x2 - x1 - 4, x3 - x2 - 4, RIGHT - x3 - 4
    rows = [
        [("Adresse", emp.get("adresse", ""), RIGHT - x1 - 4)],
        [("Matricule", emp.get("matricule", ""), w1), ("N° CIN", emp.get("cin", ""), w2),
         ("N° CNSS", emp.get("cnss", ""), w3)],
        [("Situation familiale", emp.get("situation_familiale", ""), w1),
         ("Date de naissance", fmt_date(emp.get("date_naissance")), w2),
         ("Date d'embauche", fmt_date(emp.get("date_embauche")), w3)],
        [("Nombre déductions", str(emp.get("nb_personnes_charge", 0)), w1),
         ("Département", emp.get("departement", ""), w2),
         ("Date de sortie", fmt_date(emp.get("date_sortie")), w3)],
        [("Ancienneté", anciennete(emp.get("date_embauche"), record.year, record.month), w1),
         ("Fonction", emp.get("fonction", ""), w2 + w3 + 4)],
        [("N° CIMR", emp.get("cimr", ""), w1), ("Catégorie", emp.get("categorie", ""), w2 + w3 + 4)],
        [("Banque", emp.get("banque", ""), w1),
         ("N° compte bancaire", emp.get("compte_bancaire", ""), w2 + w3 + 4)],
    ]
    for i, row in enumerate(rows):
        baseline = 87 + i * 15.6
        for x, (label, value, width) in zip((x1, x2, x3), row, strict=False):
            page.label_value(x, baseline, label, value, width)


def _draw_conges(page: _Page, result) -> None:
    top, bottom = 198.0, 222.0
    labels = (("RELIQUAT DE CONGÉS", result.conges_reliquat), ("CONGÉS ACQUIS", result.conges_acquis),
              ("CONGÉS PRIS", result.conges_pris), ("SOLDE CONGÉS", result.conges_solde))
    cell = WIDTH / 4
    for i, (label, value) in enumerate(labels):
        x0 = LEFT + i * cell
        page.rect(x0, top, x0 + cell, bottom)
        page.text(x0 + cell / 2, top + 9.5, label, BOLD, 7.5, align="center")
        page.text(x0 + cell / 2, top + 19.5, f"{fmt_days(value)} jour(s)", FONT, 7.5, align="center")


def _main_rows(record) -> list[dict]:
    """Lignes du tableau principal, dans l'ordre du modèle. Aucune valeur n'est calculée ici."""
    r, p = record.result, record.parameters
    rows: list[dict] = [
        {"label": "Salaire de base (jours)", "base": fmt_money(r.taux_journalier, True),
         "nombre": fmt_days(r.jours_declares), "gain": fmt_money(r.salaire_base)},
    ]
    for label, value in (("Heures supplémentaires", r.heures_sup), ("Prime de panier", r.prime_panier),
                         ("Indemnité de transport - périmètre urbain", r.indemnite_transport),
                         ("Indemnité de représentation", r.indemnite_representation),
                         ("Autre prime", r.autre_prime)):
        if value != 0:   # lignes nulles masquées, comme le PDF de référence (décision D9)
            rows.append({"label": label, "gain": fmt_money(value)})
    rows.append({"label": "Salaire brut", "gain": fmt_money(r.salaire_brut), "total": True})
    rows.append({})
    base, plaf = fmt_money(r.assiette_cotisations), fmt_money(r.assiette_cnss_plafonnee)
    rows += [
        {"label": "Cotisation AMO", "base": base, "nombre": fmt_rate(p.amo_salarial),
         "retenue": fmt_money(r.amo_salarie), "taux_p": fmt_rate(p.amo_patronal),
         "part_p": fmt_money(r.amo_patronal)},
        {"label": "Participation AMO", "base": base, "taux_p": fmt_rate(p.participation_amo),
         "part_p": fmt_money(r.participation_amo)},
        {"label": "Cotisation CNSS", "base": plaf, "nombre": fmt_rate(p.cnss_salarial),
         "retenue": fmt_money(r.cnss_salarie), "taux_p": fmt_rate(p.cnss_patronal),
         "part_p": fmt_money(r.cnss_patronal)},
        {"label": "Cotisation formation professionnelle", "base": base,
         "taux_p": fmt_rate(p.formation_pro), "part_p": fmt_money(r.formation_pro)},
        {"label": "Cotisation allocations familiales", "base": base,
         "taux_p": fmt_rate(p.allocations_familiales), "part_p": fmt_money(r.allocations_familiales)},
        {"label": "Total cotisations", "retenue": fmt_money(r.total_cotisations_salariales),
         "part_p": fmt_money(r.total_cotisations_patronales), "total": True},
        {},
        {"label": "Impôt sur le revenu", "base": fmt_money(r.net_imposable_apres_famille),
         "retenue": fmt_money(r.ir_mensuel, True)},
    ]
    if r.arrondi != 0:
        rows.append({"label": "Arrondi",
                     "gain": fmt_money(r.arrondi) if r.arrondi > 0 else "",
                     "retenue": fmt_money(-r.arrondi) if r.arrondi < 0 else ""})
    rows.append({"label": "Salaire net", "gain": fmt_money(r.net_a_payer), "total": True})
    return rows


def _draw_main_table(page: _Page, record) -> float:
    top, mid, head_bottom = 226.0, 243.0, 259.5
    rows = _main_rows(record)
    bottom = max(head_bottom + 6 + len(rows) * ROW_H + 6, 700.0)
    page.rect(LEFT, top, RIGHT, head_bottom, fill=HEADER_FILL)
    page.rect(LEFT, top, RIGHT, bottom)
    for x in COLS[1:-1]:
        page.vline(x, top if x in (COLS[1], COLS[2], COLS[3], COLS[5]) else mid, bottom)
    page.hline(COLS[3], RIGHT, mid)
    c = COLS
    page.text((c[0] + c[1]) / 2, 245.5, "Désignation", BOLD, 8, align="center")
    page.text((c[1] + c[2]) / 2, 245.5, "Base", BOLD, 8, align="center")
    page.text((c[2] + c[3]) / 2, 240, "Nombre", BOLD, 8, align="center")
    page.text((c[2] + c[3]) / 2, 250, "ou taux", BOLD, 8, align="center")
    page.text((c[3] + c[5]) / 2, 237.5, "Part salariale", BOLD, 8, align="center")
    page.text((c[5] + c[7]) / 2, 237.5, "Part patronale", BOLD, 8, align="center")
    for x0, x1, label in ((c[3], c[4], "Gain"), (c[4], c[5], "Retenue"),
                          (c[5], c[6], "Taux"), (c[6], c[7], "Montant")):
        page.text((x0 + x1) / 2, 254, label, BOLD, 8, align="center")

    baseline = head_bottom + 6 + 10
    for row in rows:
        if row:
            total = row.get("total", False)
            font = BOLD if total else FONT
            if total:
                page.text(c[1] - 3, baseline, row["label"], BOLD, 8, align="right",
                          max_width=c[1] - c[0] - 6)
            else:
                page.text(c[0] + 3, baseline, row["label"], FONT, 8, max_width=c[1] - c[0] - 6)
            for key, col in (("base", 1), ("nombre", 2), ("gain", 3), ("retenue", 4),
                             ("taux_p", 5), ("part_p", 6)):
                value = row.get(key, "")
                page.text(c[col + 1] - 3, baseline, value, font, 8, align="right",
                          max_width=c[col + 1] - c[col] - 6)
        baseline += ROW_H
    return bottom


def _draw_cumuls(page: _Page, record, mois: str, top: float) -> float:
    r, cu = record.result, record.cumuls
    net_box_w, gap = 62.0, 5.0
    table_right = RIGHT - net_box_w - gap
    widths = [46.0] + [47.0] * 8
    widths.append(table_right - LEFT - sum(widths))
    xs = [LEFT]
    for w in widths:
        xs.append(xs[-1] + w)
    head_h, row_h = 22.0, 13.0
    bottom = top + head_h + 2 * row_h
    page.rect(LEFT, top, table_right, top + head_h, fill=HEADER_FILL)
    page.rect(LEFT, top, table_right, bottom)
    for x in xs[1:-1]:
        page.vline(x, top, bottom)
    page.hline(LEFT, xs[-2], top + head_h + row_h)
    headers = (("Cumuls",), ("Salaire", "brut"), ("Cotisations", "P.S"), ("Cotisations", "P.P"),
               ("Impôt sur", "le revenu"), ("Net", "imposable"), ("Jours", "déclarés"),
               ("Heures", "supplém."), ("Net", "à payer"), ("Mode de", "paiement"))
    for i, lines in enumerate(headers):
        cx = (xs[i] + xs[i + 1]) / 2
        if len(lines) == 1:
            page.text(cx, top + 14, lines[0], BOLD, 7, align="center")
        else:
            page.text(cx, top + 9.5, lines[0], BOLD, 7, align="center", max_width=widths[i] - 3)
            page.text(cx, top + 18, lines[1], BOLD, 7, align="center", max_width=widths[i] - 3)
    month_values = (r.salaire_brut, r.total_cotisations_salariales, r.total_cotisations_patronales,
                    r.ir_mensuel, r.net_imposable, r.jours_declares, r.heures_sup, r.net_a_payer)
    year_values = (cu.salaire_brut, cu.cotisations_salariales, cu.cotisations_patronales, cu.ir,
                   cu.net_imposable, cu.jours_declares, cu.heures_sup, cu.net_a_payer)
    for row_i, (label, values) in enumerate(((mois.upper(), month_values), (str(record.year), year_values))):
        baseline = top + head_h + row_i * row_h + 9.5
        page.text((xs[0] + xs[1]) / 2, baseline, label, FONT, 7, align="center", max_width=widths[0] - 3)
        for i, value in enumerate(values, start=1):
            page.text(xs[i + 1] - 2.5, baseline, fmt_money(value), FONT, 7, align="right",
                      max_width=widths[i] - 4)
    mode = (record.employee_snapshot or {}).get("mode_paiement", "")
    page.text((xs[-2] + xs[-1]) / 2, top + head_h + row_h + 3, mode, FONT, 7, align="center",
              max_width=widths[-1] - 4)

    x0 = RIGHT - net_box_w
    page.rect(x0, top, RIGHT, top + head_h, fill=HEADER_FILL)
    page.rect(x0, top, RIGHT, bottom)
    page.text(x0 + net_box_w / 2, top + 14, "NET À PAYER", BOLD, 7.5, align="center")
    page.text(x0 + net_box_w / 2, top + head_h + 15, fmt_money(r.net_a_payer), BOLD, 10,
              align="center", max_width=net_box_w - 4)
    page.text(x0 + net_box_w / 2, top + head_h + 23.5, "MAD", FONT, 6.5, align="center")
    return bottom


def _draw_footer(page: _Page, record, baseline: float) -> None:
    page.text(LEFT + 2, baseline,
              "Pour vous aider à faire valoir vos droits, conservez ce bulletin de paie sans limitation de durée.",
              FONT, 8, max_width=WIDTH)
    page.c.setFillColor(BRAND)
    page.c.rect(LEFT, page.y(baseline + 8), WIDTH, 3, stroke=0, fill=1)
    page.c.setFillColor(black)
    if record.status == STATUT_CLOTUREE and record.closed_at:
        status = f"Paie clôturée le {fmt_date(record.closed_at[:10])}"
    else:
        status = "Paie non clôturée"
    info = (f"{status} - version {record.version}"
            + (f" (rectifie la version précédente : {record.rectification_reason})" if record.replaces_id else "")
            + f" - jeu de paramètres n° {record.parameter_set_id}"
            + f" - édité le {datetime.now().strftime('%d/%m/%Y')}")
    page.text(LEFT + 2, baseline + 19, info, FONT, 6.5, max_width=WIDTH, color=HexColor("#555555"))


def _draw_watermark(page: _Page) -> None:
    c = page.c
    c.saveState()
    c.setFillColor(Color(0.8, 0.1, 0.1, alpha=0.18))
    c.setFont(BOLD, 72)
    c.translate(PAGE_W / 2, PAGE_H / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, "PROVISOIRE")
    c.restoreState()
    page.text(PAGE_W / 2, 812, "Aperçu provisoire - paie non clôturée - sans valeur de bulletin",
              BOLD, 8, align="center", color=HexColor("#B00020"))


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]

