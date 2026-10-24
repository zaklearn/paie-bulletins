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

from src import __version__  # noqa: E402
from src.ui.common import require_login  # noqa: E402

st.set_page_config(page_title="Paie — bulletins", page_icon="🧾", layout="wide")

if require_login():
    navigation = st.navigation({
        "Pilotage": [
            st.Page("views/dashboard.py", title="Tableau de bord", icon="🏠", default=True),
        ],
        "Référentiels": [
            st.Page("views/entreprise.py", title="Entreprise", icon="🏢"),
            st.Page("views/salaries.py", title="Salariés", icon="👥"),
        ],
        "Paie mensuelle": [
            st.Page("views/saisie.py", title="Saisie mensuelle", icon="✏️"),
            st.Page("views/calcul.py", title="Calcul et validation", icon="🧮"),
            st.Page("views/archives.py", title="Bulletins et archives", icon="🗂️"),
            st.Page("views/exports.py", title="Récapitulatifs et exports", icon="📊"),
        ],
        "Configuration": [
            st.Page("views/parametres.py", title="Paramètres", icon="⚙️"),
            st.Page("views/administration.py", title="Sauvegardes et administration", icon="🛡️"),
        ],
    })
    st.sidebar.caption(f"Version {__version__}")
    navigation.run()
