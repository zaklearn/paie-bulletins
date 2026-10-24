"""Exécution réelle de chaque page Streamlit (banc de test officiel `AppTest`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")
PAGES = ["views/dashboard.py", "views/entreprise.py", "views/salaries.py", "views/saisie.py",
         "views/calcul.py", "views/archives.py", "views/exports.py", "views/parametres.py",
         "views/administration.py"]


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
    app.switch_page("views/saisie.py")
    app.run()
    assert any("clôturée" in w.value for w in app.warning)


def test_entry_page_saves_october_draft(app):
    app.session_state["mois"] = 10
    app.run()
    app.switch_page("views/saisie.py")
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


@pytest.mark.parametrize("page", PAGES)
def test_pages_unreachable_before_login(tmp_path, monkeypatch, page):
    """Sans connexion, aucune page ne doit s'exécuter (pas de menu automatique « pages/ »)."""
    from src.services.auth import hash_password
    from src.ui import common
    monkeypatch.setenv("PAIE_DB_PATH", str(tmp_path / "locked.db"))
    monkeypatch.setenv("PAIE_AUTH_PASSWORD_HASH", hash_password("motdepasse-solide", iterations=1000))
    common._bootstrap.clear()
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    try:
        at.switch_page(page)
        at.run()
    except Exception:
        pass
    assert [t.value for t in at.title] == ["Connexion"]
    common._bootstrap.clear()


def test_no_streamlit_pages_directory():
    assert not (Path(APP).parent / "pages").exists()


def test_version_shown_and_logged(app):
    from src import __version__
    app.run()
    assert any(c.value == f"Version {__version__}" for c in app.sidebar.caption)
    log = (Path(APP).parent / "log.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in log
