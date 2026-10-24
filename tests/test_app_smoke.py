"""Exécution réelle de chaque page Streamlit (banc de test officiel `AppTest`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")
PAGES = ["pages/dashboard.py", "pages/entreprise.py", "pages/salaries.py", "pages/saisie.py",
         "pages/calcul.py", "pages/archives.py", "pages/exports.py", "pages/parametres.py",
         "pages/administration.py"]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("PAIE_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("PAIE_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("PAIE_SEED_DEMO", "1")
    monkeypatch.setenv("PAIE_AUTH_PASSWORD_HASH", "")
    from src.ui import common
    common._bootstrap.clear()
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["annee"] = 2026
    at.session_state["mois"] = 9
    yield at
    common._bootstrap.clear()


@pytest.mark.parametrize("page", PAGES)
def test_page_runs_without_exception(app, page):
    app.run()
    app.switch_page(page)
    app.run()
    assert not app.exception, [e.value for e in app.exception]


def test_dashboard_shows_demo_company(app):
    app.run()
    assert not app.exception
    assert any("SOCIÉTÉ EXEMPLE SARL" in c.value for c in app.caption)


def test_closed_september_is_read_only_in_entry_page(app):
    app.run()
    app.switch_page("pages/saisie.py")
    app.run()
    assert any("clôturée" in w.value for w in app.warning)


def test_entry_page_saves_october_draft(app):
    app.session_state["mois"] = 10
    app.run()
    app.switch_page("pages/saisie.py")
    app.run()
    assert not app.exception
    save = [b for b in app.button if b.label == "Enregistrer le brouillon"][0]
    save.click()
    app.run()
    assert not app.exception
    assert any("Brouillon enregistré" in s.value for s in app.success)


def test_login_required_when_password_configured(tmp_path, monkeypatch):
    from src.services.auth import hash_password
    from src.ui import common
    monkeypatch.setenv("PAIE_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("PAIE_AUTH_PASSWORD_HASH", hash_password("motdepasse-solide", iterations=1000))
    common._bootstrap.clear()
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert any(t.value == "Connexion" for t in at.title)
    at.text_input[0].input("Testeur")
    at.text_input[1].input("mauvais")
    at.button[0].click()
    at.run()
    assert at.error
    at.text_input[1].input("motdepasse-solide")
    at.button[0].click()
    at.run()
    assert at.session_state["authenticated"] is True
    common._bootstrap.clear()
