"""Briques d'interface partagées par les pages Streamlit.

`st.session_state` ne sert qu'à l'interface (sélections, authentification) : toutes les
données de paie sont lues et écrites en base via les services.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from src.calculations.money import to_decimal
from src.config import Settings, load_settings
from src.formatting import fmt_money
from src.models.payroll import MOIS_FR
from src.repositories.db import Database
from src.services import auth, demo, master_data
from src.services.errors import PayrollError, ValidationFailed
from src.validation.validators import ERREUR, Issue


@st.cache_resource
def _bootstrap() -> tuple[Settings, Database]:
    settings = load_settings()
    db = Database(settings.db_path)
    db.migrate()
    master_data.ensure_initial_parameters(db)
    if settings.seed_demo:
        demo.seed_demo(db)
    return settings, db


def settings() -> Settings:
    return _bootstrap()[0]


def get_db() -> Database:
    return _bootstrap()[1]


def actor() -> str:
    return st.session_state.get("actor", "utilisateur local")


def require_login() -> bool:
    """Affiche l'écran de connexion si un mot de passe est configuré. Renvoie True si l'accès est ouvert."""
    cfg = settings()
    if not cfg.auth_enabled:
        st.sidebar.warning("Accès sans mot de passe (mode local). Voir docs/DEPLOIEMENT.md.", icon="⚠️")
        return True
    if st.session_state.get("authenticated"):
        return True
    st.title("Connexion")
    with st.form("login"):
        name = st.text_input("Votre nom (pour le journal des opérations)")
        password = st.text_input("Mot de passe", type="password")
        if st.form_submit_button("Se connecter", type="primary"):
            if name.strip() and auth.verify_password(password, cfg.auth_password_hash):
                st.session_state["authenticated"] = True
                st.session_state["actor"] = name.strip()
                st.rerun()
            st.error("Nom manquant ou mot de passe incorrect.")
    return False


# --- Sélecteurs partagés -------------------------------------------------------------------

def period_selector(key_prefix: str = "", show_month: bool = True) -> tuple[int, int]:
    """Année et mois mémorisés d'une page à l'autre."""
    import datetime as dt
    today = dt.date.today()
    st.session_state.setdefault("annee", today.year)
    st.session_state.setdefault("mois", today.month)
    cols = st.columns(2 if show_month else 1)
    years = list(range(2000, 2101))
    year = cols[0].selectbox("Année de paie", years, index=years.index(st.session_state["annee"]),
                             key=f"{key_prefix}annee_sel")
    st.session_state["annee"] = year
    month = st.session_state["mois"]
    if show_month:
        month = cols[1].selectbox("Mois", list(range(1, 13)), index=st.session_state["mois"] - 1,
                                  format_func=lambda m: MOIS_FR[m - 1], key=f"{key_prefix}mois_sel")
        st.session_state["mois"] = month
    return year, month


def employee_selector(db: Database, active_only: bool = True, key: str = "employee_sel"):
    employees = master_data.list_employees(db, active_only=active_only)
    if not employees:
        st.info("Aucun salarié. Créez une fiche dans la page **Salariés**.")
        return None
    ids = [e.id for e in employees]
    current = st.session_state.get("employee_id")
    index = ids.index(current) if current in ids else 0
    chosen = st.selectbox("Salarié", employees, index=index, key=key,
                          format_func=lambda e: f"{e.matricule} — {e.nom_complet}")
    st.session_state["employee_id"] = chosen.id
    return chosen


# --- Saisie et affichage -----------------------------------------------------------------

def decimal_input(label: str, value: Decimal, key: str, help: str | None = None,
                  step: float = 0.01, min_value: float | None = 0.0, disabled: bool = False) -> Decimal:
    """Champ numérique à deux décimales, renvoyé en `Decimal` exact."""
    raw = st.number_input(label, value=float(value), step=step, format="%.2f", key=key,
                          help=help, min_value=min_value, disabled=disabled)
    return to_decimal(f"{raw:.2f}")


def show_issues(issues: list[Issue]) -> None:
    for issue in issues:
        if issue.level == ERREUR:
            st.error(issue.message, icon="⛔")
        else:
            st.warning(issue.message, icon="⚠️")


def run_action(func, *args, success: str | None = None, **kwargs):
    """Exécute un service et affiche proprement les refus métier."""
    try:
        result = func(*args, **kwargs)
    except ValidationFailed as exc:
        show_issues(exc.issues)
        return None
    except PayrollError as exc:
        st.error(str(exc), icon="⛔")
        return None
    if success:
        st.success(success, icon="✅")
    return result


def money_table(rows: list[tuple[str, object]], columns: tuple[str, str] = ("Rubrique", "Montant (MAD)")) -> None:
    df = pd.DataFrame([(label, fmt_money(value) if value is not None else "") for label, value in rows],
                      columns=list(columns))
    st.dataframe(df, hide_index=True)


def page_header(title: str, caption: str | None = None) -> None:
    st.title(title)
    if caption:
        st.caption(caption)
