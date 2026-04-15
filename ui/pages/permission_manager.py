"""Permission Manager page: assign inheritable and direct permissions.

References:
- Article 2: https://derkvanderwoude.medium.com/from-blueprint-to-token-how-entra-agent-identity-inheritance-really-works-fed114abe281
  Three inheritance categories: Protocol Properties (always), Delegated Permissions
  (conditionally), Not Inherited (direct only).
"""

from __future__ import annotations

import streamlit as st

from config.azure_config import AzureConfig
from config.theme import GREEN_BRIGHT, GREEN_DIM, AMBER_WARN, RED_ALERT
from services.blueprint_service import BlueprintService
from services.cache import SessionCache
from services.graph_client import GraphClient
from services.permission_service import PermissionService
from ui.components.permission_panel import render_permission_panel


def render(
    store: dict,
    *,
    graph: GraphClient,
    cache: SessionCache,
    config: AzureConfig,
    **kwargs,
) -> None:
    st.markdown("## Permission Manager")
    st.caption("Assign inheritable and direct permissions to blueprints and agent identities.")

    bp_svc = BlueprintService(graph=graph, cache=cache, config=config)
    perm_svc = PermissionService(graph=graph, cache=cache, config=config)

    # ── Blueprint Selection ────────────────────────────────────────────
    blueprints = bp_svc.list_blueprints()
    if not blueprints:
        st.info("No blueprints found. Create one in Manage Entities.")
        return

    bp_names = {bp.display_name: bp.id for bp in blueprints}
    selected_bp_name = st.selectbox(
        "SELECT BLUEPRINT",
        options=list(bp_names.keys()),
        key="perm_bp_select",
    )
    selected_bp_id = bp_names[selected_bp_name]

    # ── Inheritance Summary (Article 2) ───────────────────────────────
    _render_inheritance_summary(perm_svc, selected_bp_id)

    # ── Agent Identity Selection ───────────────────────────────────────
    identities = bp_svc.get_identities_for_blueprint(selected_bp_id)
    if not identities:
        st.info(
            "No agent identities under this blueprint. "
            "Create one in Manage Entities."
        )
        return

    ai_names = {ai.display_name: ai.id for ai in identities}
    selected_ai_name = st.selectbox(
        "SELECT AGENT IDENTITY",
        options=list(ai_names.keys()),
        key="perm_ai_select",
    )
    selected_ai_id = ai_names[selected_ai_name]

    st.markdown("---")

    # ── Permission Panel ───────────────────────────────────────────────
    render_permission_panel(
        blueprint_id=selected_bp_id,
        agent_identity_id=selected_ai_id,
        perm_service=perm_svc,
        key_prefix="perm_mgr",
    )


def _render_inheritance_summary(perm_svc: PermissionService, blueprint_id: str) -> None:
    """Render the three inheritance categories from Article 2."""
    summary = perm_svc.get_inheritance_summary(blueprint_id)

    with st.expander("\u25b8 INHERITANCE MODEL (Article 2 — 3 Categories)", expanded=False):
        col1, col2, col3 = st.columns(3)

        # Category 1: Protocol Properties
        with col1:
            proto = summary["protocol_properties"]
            items_display = "<br>".join(
                f"  \u2022 {item}" for item in proto["items"] if item
            )
            st.markdown(
                f"<div style='border: 1px solid {GREEN_BRIGHT}; padding: 8px; "
                f"font-family: \"Share Tech Mono\", monospace; font-size: 0.8em;'>"
                f"<span style='color: {GREEN_BRIGHT};'>1. PROTOCOL PROPERTIES</span><br>"
                f"<span style='color: {GREEN_DIM};'>(Always inherited)</span><br><br>"
                f"<span style='color: {GREEN_DIM};'>{items_display}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Category 2: Delegated Permissions
        with col2:
            deleg = summary["delegated_permissions"]
            active_names = ", ".join(p.name for p in deleg["active"]) if deleg["active"] else "None"
            pending_names = ", ".join(p.name for p in deleg["pending"]) if deleg["pending"] else "None"
            st.markdown(
                f"<div style='border: 1px solid {AMBER_WARN}; padding: 8px; "
                f"font-family: \"Share Tech Mono\", monospace; font-size: 0.8em;'>"
                f"<span style='color: {AMBER_WARN};'>2. DELEGATED PERMS</span><br>"
                f"<span style='color: {GREEN_DIM};'>(Conditionally inherited)</span><br><br>"
                f"<span style='color: {GREEN_BRIGHT};'>\u2713 Active ({deleg['active_count']}): "
                f"{active_names}</span><br>"
                f"<span style='color: {AMBER_WARN};'>\u25cb Pending ({deleg['pending_consent_count']}): "
                f"{pending_names}</span><br><br>"
                f"<span style='color: {GREEN_DIM}; font-size: 0.85em;'>"
                f"Requires BOTH:<br>"
                f"  1. inheritablePermissions<br>"
                f"  2. OAuth2PermissionGrant</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Category 3: Not Inherited
        with col3:
            not_inh = summary["not_inherited"]
            st.markdown(
                f"<div style='border: 1px solid {RED_ALERT}; padding: 8px; "
                f"font-family: \"Share Tech Mono\", monospace; font-size: 0.8em;'>"
                f"<span style='color: {RED_ALERT};'>3. NOT INHERITED</span><br>"
                f"<span style='color: {GREEN_DIM};'>(Direct assignment only)</span><br><br>"
                f"<span style='color: {GREEN_DIM};'>"
                f"  \u2022 appRoleAssignments<br>"
                f"  \u2022 Azure RBAC roles<br>"
                f"  \u2022 Sponsor designations<br><br>"
                f"<span style='font-size: 0.85em;'>"
                f"Must be assigned per agent identity.</span></span>"
                f"</div>",
                unsafe_allow_html=True,
            )
