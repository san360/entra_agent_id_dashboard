"""Connection status sidebar widget."""
from __future__ import annotations

import streamlit as st

from config.azure_config import AzureConfig


def render_connection_status(config: AzureConfig) -> None:
    """Render connection status in the sidebar."""
    st.markdown(
        "<span class='status-badge status-connected'>✅ Connected</span>",
        unsafe_allow_html=True,
    )
    st.caption(f"Tenant: {config.tenant_id}")
    st.caption(f"API: {config.graph_base_url}")
