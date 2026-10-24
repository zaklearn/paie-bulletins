"""Bulletin PDF : contenu, format A4, accents, absence de débordement, nom de fichier."""

from __future__ import annotations

import io
from dataclasses import replace
from decimal import Decimal as D

import pdfplumber
import pytest

from src.pdf.bulletin import bulletin_filename, render_bulletin
from src.services import master_data, payroll

from .conftest import ACTOR


def _close_september(db, employee_id, ref_input):
    last = None
    for month in (7, 8, 9):
        payslip_id, _ = payroll.save_draft(db, ACTOR, employee_id, 2026, month, ref_input)
        payroll.calculate(db, ACTOR, payslip_id)
        last = payroll.close(db, ACTOR, payslip_id, confirm_warnings=True)
    return last


def _open(pdf_bytes: bytes):
    return pdfplumber.open(io.BytesIO(pdf_bytes))


@pytest.fixture
def september(setup, ref_input):
    db, employee_id = setup
    record = _close_september(db, employee_id, ref_input)
    return db, record, payroll.get_document(db, record.id).content


def test_a4_single_page(september):
    _, _, pdf = september
    with _open(pdf) as doc:
        assert len(doc.pages) == 1
        page = doc.pages[0]
        assert round(page.width, 1) == 595.3 and round(page.height, 1) == 841.9


def test_amounts_and_sections_present(september):
    _, _, pdf = september
    with _open(pdf) as doc:
        text = doc.pages[0].extract_text()
    for expected in ("BULLETIN DE PAIE : SEPTEMBRE 2026", "SOCIÉTÉ EXEMPLE SARL", "EXEMPLE",
                     "RELIQUAT DE CONGÉS", "SOLDE CONGÉS", "1,50 jour(s)",
                     "Salaire de base (jours)", "209,10", "26,00", "5 436,51", "Prime de panier",
                     "930,00", "Indemnité de transport - périmètre urbain", "Indemnité de représentation",
                     "7 366,51", "Cotisation AMO", "Participation AMO", "Cotisation CNSS",
                     "243,56", "122,87", "488,20", "100,58", "86,98", "347,94",
                     "366,43", "1 146,57", "Impôt sur le revenu", "3 167,30", "Arrondi", "0,08",
                     "Salaire net", "7 000,00", "NET À PAYER", "MAD", "Virement",
                     "22 099,53", "1 099,29", "3 439,71", "9 501,90", "78,00", "21 000,00",
                     "conservez ce bulletin de paie sans limitation de durée"):
        assert expected in text, expected


def test_zero_gain_lines_hidden(september):
    _, _, pdf = september
    with _open(pdf) as doc:
        text = doc.pages[0].extract_text()
    assert "Heures supplémentaires\n" not in text and "Autre prime" not in text


def test_all_text_inside_page_and_no_overlap_on_long_values(setup, ref_input):
    db, employee_id = setup
    emp = master_data.get_employee(db, employee_id)
    long = "Département des opérations commerciales et du développement international"
    master_data.update_employee(db, ACTOR, replace(
        emp, nom="NOM-DE-FAMILLE-TRÈS-LONG-POUR-TESTER-LA-MISE-EN-PAGE", prenom="Prénom-Composé-Très-Long",
        departement=long, fonction=long, adresse=long + " " + long, banque=long,
        compte_bancaire="0123456789 0123456789 0123456789 0123456789"))
    company = master_data.get_company(db)
    master_data.save_company(db, ACTOR, replace(company, raison_sociale="RAISON SOCIALE " * 8))
    inputs = replace(ref_input, salaire_base=D("987654.32"), heures_sup=D("123456.78"),
                     autre_prime=D("99999.99"))
    payslip_id, _ = payroll.save_draft(db, ACTOR, employee_id, 2026, 7, inputs)
    payroll.calculate(db, ACTOR, payslip_id)
    pdf = payroll.provisional_pdf(db, payslip_id)
    with _open(pdf) as doc:
        page = doc.pages[0]
        words = page.extract_words()
        assert all(0 <= w["x0"] and w["x1"] <= page.width and 0 <= w["top"] and w["bottom"] <= page.height
                   for w in words)
        text = page.extract_text()
    assert "Aperçu provisoire - paie non clôturée" in text
    assert "1 213 041,09" in text               # salaire brut à 7 chiffres non tronqué


def test_amount_cells_stay_inside_columns(september):
    """Chaque montant du tableau principal reste dans sa colonne."""
    from src.pdf.bulletin import COLS
    _, _, pdf = september
    with _open(pdf) as doc:
        page = doc.pages[0]
        for word in page.extract_words():
            if 260 < word["top"] < 700 and word["x0"] > COLS[1]:
                inside = any(COLS[i] <= word["x0"] and word["x1"] <= COLS[i + 1] for i in range(1, 7))
                assert inside, word


def test_filename_and_versions(september):
    _, record, _ = september
    assert bulletin_filename(record) == "bulletin_2026-09_0001.pdf"
    assert bulletin_filename(replace(record, version=3)) == "bulletin_2026-09_0001_v3.pdf"


def test_render_requires_calculated_payslip(september):
    _, record, _ = september
    with pytest.raises(ValueError):
        render_bulletin(replace(record, result=None))


def test_pdf_uses_snapshot_not_current_data(september):
    db, record, pdf = september
    emp = master_data.get_employee(db, record.employee_id)
    master_data.update_employee(db, ACTOR, replace(emp, nom="CHANGÉ"))
    regenerated = render_bulletin(payroll.get_payslip(db, record.id))
    with _open(regenerated) as doc:
        assert "CHANGÉ" not in doc.pages[0].extract_text()


def test_logo_is_embedded(september):
    from PIL import Image
    db, record, _ = september
    buf = io.BytesIO()
    Image.new("RGB", (200, 80), (31, 56, 100)).save(buf, format="PNG")
    with _open(render_bulletin(record, logo=buf.getvalue())) as doc:
        assert len(doc.pages[0].images) == 1
    with _open(render_bulletin(record, logo=b"pas une image")) as doc:   # logo invalide ignoré
        assert len(doc.pages[0].images) == 0
