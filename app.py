"""Générateur de bulletins de paie — point d'entrée Streamlit.

Lancement : streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ui.common import require_login  # noqa: E402

st.set_page_config(page_title="Paie — bulletins", page_icon="🧾", layout="wide")

if require_login():
    navigation = st.navigation({
        "Pilotage": [
            st.Page("pages/dashboard.py", title="Tableau de bord", icon="🏠", default=True),
        ],
        "Référentiels": [
            st.Page("pages/entreprise.py", title="Entreprise", icon="🏢"),
            st.Page("pages/salaries.py", title="Salariés", icon="👥"),
        ],
        "Paie mensuelle": [
            st.Page("pages/saisie.py", title="Saisie mensuelle", icon="✏️"),
            st.Page("pages/calcul.py", title="Calcul et validation", icon="🧮"),
            st.Page("pages/archives.py", title="Bulletins et archives", icon="🗂️"),
            st.Page("pages/exports.py", title="Récapitulatifs et exports", icon="📊"),
        ],
        "Configuration": [
            st.Page("pages/parametres.py", title="Paramètres", icon="⚙️"),
            st.Page("pages/administration.py", title="Sauvegardes et administration", icon="🛡️"),
        ],
    })
    navigation.run()
