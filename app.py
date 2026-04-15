"""Entra Agent ID Blueprint Dashboard — Streamlit Entry Point."""

import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from config.azure_config import load_azure_config
from config.theme import GLOBAL_CSS, COLOR_PRIMARY, COLOR_TEXT_SECONDARY
from data import init_store
from services.cache import SessionCache
from services.graph_client import GraphClient, ARMClient
from ui.pages import (
    dashboard,
    manage_entities,
    permission_manager,
    reference_docs,
)

# ── Page Config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Entra Agent ID Dashboard",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global Setup ───────────────────────────────────────────────────────────────
st.markdown(f"<style>{GLOBAL_CSS}</style>", unsafe_allow_html=True)
init_store(st.session_state)

# ── Azure Config & Services ───────────────────────────────────────────────────
try:
    if "azure_config" not in st.session_state:
        st.session_state["azure_config"] = load_azure_config()
    config = st.session_state["azure_config"]
except ValueError as e:
    st.error(
        "**Azure configuration required.** "
        "Set `AZURE_TENANT_ID` (and optionally `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET`) "
        "in a `.env` file or as environment variables."
    )
    st.code(
        "# .env file example\n"
        "AZURE_TENANT_ID=your-tenant-id\n"
        "AZURE_CLIENT_ID=your-client-id\n"
        "AZURE_CLIENT_SECRET=your-client-secret\n",
        language="bash",
    )
    st.stop()

cache = SessionCache(st.session_state)
graph = GraphClient(config)
arm = ARMClient(config)

# ── Sidebar Navigation ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f"<h3 style='margin-bottom: 0;'>🔐 Entra Agent ID</h3>"
        f"<p style='color: {COLOR_TEXT_SECONDARY}; font-size: 0.8em; margin-top: 0;'>"
        f"Blueprint Dashboard</p>",
        unsafe_allow_html=True,
    )

    page = st.radio(
        "Navigate",
        [
            "📊 Dashboard",
            "🛠️ Manage Entities",
            "🔒 Permissions",
            " Reference Docs",
        ],
        key="nav_page",
        label_visibility="collapsed",
    )

    st.markdown("---")

    st.markdown(
        "<span class='status-badge status-connected'>✅ Connected</span>",
        unsafe_allow_html=True,
    )
    st.caption(f"Tenant: {config.tenant_id}")
    st.caption("v2.0.0")

# ── Page Routing ───────────────────────────────────────────────────────────────
PAGES = {
    "📊 Dashboard": dashboard,
    "🛠️ Manage Entities": manage_entities,
    "🔒 Permissions": permission_manager,
    " Reference Docs": reference_docs,
}

PAGES[page].render(st.session_state, graph=graph, cache=cache, config=config, arm=arm)
