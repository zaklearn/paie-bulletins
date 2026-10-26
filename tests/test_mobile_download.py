"""Lien de téléchargement direct (mobile) : contenu exact du bulletin archivé, nom protégé."""

from __future__ import annotations

import base64
import re
from html.parser import HTMLParser

import pytest

from src.services import payroll
from src.ui.common import direct_download_html

from .test_app_smoke import app  # noqa: F401  (fixture : démonstration, mode local explicite)


class _Link(HTMLParser):
    def __init__(self):
        super().__init__()
        self.attrs: dict = {}
        self.text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.attrs = dict(attrs)

    def handle_data(self, data):
        self.text += data


def parse(html_text: str) -> _Link:
    link = _Link()
    link.feed(html_text)
    return link


def decoded(link: _Link) -> bytes:
    prefix, data = link.attrs["href"].split(",", 1)
    assert prefix == "data:application/pdf;base64"
    return base64.b64decode(data)


def test_link_carries_exact_bytes_and_downloads_in_place():
    content = bytes(range(256)) * 10
    link = parse(direct_download_html(content, "bulletin_2026-09_0001.pdf", "Télécharger"))
    assert decoded(link) == content
    assert link.attrs["download"] == "bulletin_2026-09_0001.pdf"
    assert link.attrs["target"] == "_self"          # pas de nouvel onglet (bloqué sur mobile)
    assert link.text == "Télécharger"


def test_filename_and_label_are_escaped():
    html_text = direct_download_html(b"%PDF", 'x" onclick="alert(1).pdf', "<b>libellé</b>")
    assert "onclick=\"alert" not in html_text and "<b>" not in html_text
    link = parse(html_text)
    assert link.attrs["download"] == 'x" onclick="alert(1).pdf'   # restitué tel quel, sans injection
    assert "onclick" not in link.attrs


def _iframe_links(at) -> list[_Link]:
    return [parse(el.proto.srcdoc) for el in at.get("iframe") if getattr(el.proto, "srcdoc", "")]


@pytest.mark.parametrize("page, month", [("views/archives.py", None), ("views/calcul.py", 9)])
def test_pages_offer_link_with_archived_pdf(app, page, month):  # noqa: F811
    if month:
        app.session_state["mois"] = month
    app.run()
    app.switch_page(page)
    app.run()
    assert not app.exception
    links = _iframe_links(app)
    assert len(links) == 1
    link = links[0]
    match = re.fullmatch(r"bulletin_(\d{4})-(\d{2})_0001\.pdf", link.attrs["download"])
    assert match
    slip = [s for s in payroll.list_payslips(_db(), year=int(match[1]), month=int(match[2]))
            if s.status == "cloturee"][0]
    document = payroll.get_document(_db(), slip.id)
    assert decoded(link) == document.content
    assert link.attrs["download"] == document.filename
    assert link.text == f"📱 Télécharger sur mobile : {document.filename}"


def _db():
    from src.ui.common import get_db
    return get_db()


def test_no_link_for_payslip_not_closed(app):  # noqa: F811
    app.session_state["mois"] = 10            # aucune paie clôturée en octobre (démonstration)
    app.run()
    app.switch_page("views/calcul.py")
    app.run()
    assert not app.exception and not _iframe_links(app)
