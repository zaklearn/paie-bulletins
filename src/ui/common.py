"""Briques d'interface partagées par les pages Streamlit.

`st.session_state` ne sert qu'à l'interface (sélections, authentification) : toutes les
données de paie sont lues et écrites en base via les services.
"""

from __future__ import annotations

import base64
import html
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
    """Contrôle d'accès. Renvoie True si l'accès est ouvert.

    - mot de passe configuré : écran de connexion, puis bouton de déconnexion ;
    - aucun mot de passe et `PAIE_ALLOW_NO_AUTH=1` : accès libre (usage local choisi explicitement) ;
    - aucun mot de passe et aucune dérogation : l'application reste bloquée.
    """
    cfg = settings()
    if cfg.access_blocked:
        st.title("Configuration incomplète")
        st.error("Aucun mot de passe d'accès n'est configuré : l'application reste fermée. "
                 "Définissez PAIE_AUTH_PASSWORD_HASH (secrets de l'hébergement ou fichier .env). "
                 "Pour un usage local sans mot de passe, définissez explicitement PAIE_ALLOW_NO_AUTH=1. "
                 "Voir docs/DEPLOIEMENT.md.", icon="⛔")
        return False
    if not cfg.auth_enabled:
        st.sidebar.warning("Accès sans mot de passe (PAIE_ALLOW_NO_AUTH=1, usage local). "
                           "Voir docs/DEPLOIEMENT.md.", icon="⚠️")
        return True
    if st.session_state.get("authenticated"):
        if st.sidebar.button("Se déconnecter", key="logout"):
            st.session_state.clear()
            st.rerun()
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


# --- Téléchargement direct (mobile) -------------------------------------------------------

def direct_download_html(content: bytes, filename: str, label: str,
                         mime: str = "application/pdf") -> str:
    """Lien qui télécharge le fichier sur place (données intégrées, sans nouvel onglet).

    Sur Streamlit Community Cloud, `st.download_button` ouvre le fichier dans un nouvel onglet,
    ouverture que Chrome et Firefox mobiles bloquent sans message (diagnostic du 2026-10-26).
    """
    data = base64.b64encode(content).decode("ascii")
    return (f'<a href="data:{html.escape(mime, quote=True)};base64,{data}" '
            f'download="{html.escape(filename, quote=True)}" target="_self" '
            'style="font-family:sans-serif;font-size:14px;color:#1F3864;">'
            f"{html.escape(label)}</a>")


def mobile_download_link(content: bytes, filename: str) -> None:
    """Affiche le lien dans un cadre (`st.iframe`). Le HTML est entièrement produit ici :
    contenu encodé en base64, nom de fichier et libellé échappés."""
    st.iframe(direct_download_html(content, filename, f"📱 Télécharger sur mobile : {filename}"), height=32)
