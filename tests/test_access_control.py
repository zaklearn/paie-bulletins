"""Contrôle d'accès : configuration obligatoire, mode local explicite, connexion, déconnexion."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.config import load_settings
from src.services.auth import hash_password

from .test_app_smoke import PAGES

APP = str(Path(__file__).resolve().parent.parent / "app.py")
PASSWORD = "motdepasse-solide"
BLOCKED_TITLE = "Configuration incomplète"


@pytest.fixture
def make_app(tmp_path, monkeypatch):
    """Construit une application avec la configuration d'accès demandée."""
    from src.ui import common
    monkeypatch.setenv("PAIE_DB_PATH", str(tmp_path / "access.db"))
    monkeypatch.setenv("PAIE_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("PAIE_SEED_DEMO", "1")

    def build(password_hash: str = "", allow_no_auth: str | None = None) -> AppTest:
        monkeypatch.setenv("PAIE_AUTH_PASSWORD_HASH", password_hash)
        if allow_no_auth is None:
            monkeypatch.delenv("PAIE_ALLOW_NO_AUTH", raising=False)
        else:
            monkeypatch.setenv("PAIE_ALLOW_NO_AUTH", allow_no_auth)
        common._bootstrap.clear()
        at = AppTest.from_file(APP, default_timeout=60)
        at.run()
        return at

    yield build
    common._bootstrap.clear()


def titles(at: AppTest) -> list[str]:
    return [t.value for t in at.title]


def login(at: AppTest, password: str = PASSWORD, name: str = "Testeur") -> None:
    at.text_input[0].input(name)
    at.text_input[1].input(password)
    at.button[0].click()
    at.run()


# --- Configuration ------------------------------------------------------------------------

def test_settings_default_is_secure(monkeypatch):
    monkeypatch.setenv("PAIE_AUTH_PASSWORD_HASH", "")
    monkeypatch.delenv("PAIE_ALLOW_NO_AUTH", raising=False)
    cfg = load_settings()
    assert cfg.access_blocked and not cfg.allow_no_auth


@pytest.mark.parametrize("value, blocked", [("1", False), ("true", False), ("0", True), ("", True),
                                            ("non", True)])
def test_settings_explicit_local_mode(monkeypatch, value, blocked):
    monkeypatch.setenv("PAIE_AUTH_PASSWORD_HASH", "")
    monkeypatch.setenv("PAIE_ALLOW_NO_AUTH", value)
    assert load_settings().access_blocked is blocked


def test_password_takes_precedence_over_local_mode(monkeypatch):
    monkeypatch.setenv("PAIE_AUTH_PASSWORD_HASH", hash_password(PASSWORD, iterations=1000))
    monkeypatch.setenv("PAIE_ALLOW_NO_AUTH", "1")
    cfg = load_settings()
    assert cfg.auth_enabled and not cfg.access_blocked


# --- Application bloquée sans secret -------------------------------------------------------

def test_missing_secret_blocks_application(make_app):
    at = make_app()
    assert titles(at) == [BLOCKED_TITLE]
    assert any("PAIE_AUTH_PASSWORD_HASH" in e.value for e in at.error)
    assert not at.sidebar.button and not at.text_input        # ni menu, ni formulaire
    assert not at.exception


def test_explicit_zero_still_blocks(make_app):
    assert titles(make_app(allow_no_auth="0")) == [BLOCKED_TITLE]


@pytest.mark.parametrize("page", PAGES)
def test_missing_secret_blocks_every_page(make_app, page):
    at = make_app()
    try:
        at.switch_page(page)
        at.run()
    except Exception:  # page inconnue de la navigation : refus également acceptable
        pass
    assert titles(at) == [BLOCKED_TITLE]


def test_error_message_does_not_expose_configuration_values(make_app, tmp_path):
    at = make_app()
    page_text = " ".join(e.value for e in at.error) + " ".join(t.value for t in at.title)
    assert str(tmp_path) not in page_text


# --- Mode local explicite ------------------------------------------------------------------

def test_explicit_local_mode_opens_with_warning(make_app):
    at = make_app(allow_no_auth="1")
    assert titles(at) == ["Tableau de bord"]
    assert any("PAIE_ALLOW_NO_AUTH" in w.value for w in at.sidebar.warning)
    assert not [b for b in at.sidebar.button if b.label == "Se déconnecter"]


# --- Connexion, nouvelle session, déconnexion ----------------------------------------------

def test_valid_and_invalid_login(make_app):
    at = make_app(hash_password(PASSWORD, iterations=1000))
    assert titles(at) == ["Connexion"]
    login(at, password="mauvais")
    assert titles(at) == ["Connexion"] and at.error
    login(at)
    assert titles(at) == ["Tableau de bord"]
    assert at.session_state["actor"] == "Testeur"


def test_login_requires_a_name(make_app):
    at = make_app(hash_password(PASSWORD, iterations=1000))
    login(at, name="  ")
    assert titles(at) == ["Connexion"]


def test_new_session_requires_login_again(make_app):
    at = make_app(hash_password(PASSWORD, iterations=1000))
    login(at)
    assert titles(at) == ["Tableau de bord"]
    other = AppTest.from_file(APP, default_timeout=60)    # nouvel onglet / relance de session
    other.run()
    assert titles(other) == ["Connexion"]


def test_logout_returns_to_login_and_locks_pages(make_app):
    at = make_app(hash_password(PASSWORD, iterations=1000))
    login(at)
    logout = [b for b in at.sidebar.button if b.label == "Se déconnecter"]
    assert logout
    logout[0].click()
    at.run()
    assert titles(at) == ["Connexion"]
    assert "authenticated" not in at.session_state and "actor" not in at.session_state
    try:
        at.switch_page("views/administration.py")
        at.run()
    except Exception:
        pass
    assert titles(at) == ["Connexion"]


def test_navigation_after_login(make_app):
    at = make_app(hash_password(PASSWORD, iterations=1000))
    login(at)
    at.switch_page("views/parametres.py")
    at.run()
    assert titles(at) == ["Paramètres de paie"] and not at.exception
