"""Blueprint Visualizer page: hierarchical tree + entity creation."""

from __future__ import annotations

import streamlit as st

from config.azure_config import AzureConfig
from models.blueprint import CredentialType
from services.blueprint_service import BlueprintService
from services.cache import SessionCache
from services.graph_client import GraphClient
from services.hierarchy_service import HierarchyService
from ui.components.tree_view import render_tree


def render(
    store: dict,
    *,
    graph: GraphClient,
    cache: SessionCache,
    config: AzureConfig,
) -> None:
    st.markdown("## Blueprint Visualizer")

    bp_svc = BlueprintService(graph=graph, cache=cache, config=config)
    hier_svc = HierarchyService(bp_svc=bp_svc)

    # ── Main Layout ────────────────────────────────────────────────────
    col_tree, col_actions = st.columns([3, 2])

    with col_tree:
        st.markdown("#### Identity Hierarchy")
        forest = hier_svc.build_forest()
        render_tree(forest, key_prefix="viz_tree")

    with col_actions:
        st.markdown(
            "#### Actions"
        )

        # ── Metrics ─────────────────────────────
        m1, m2, m3 = st.columns(3)
        bp_count = len(bp_svc.list_blueprints())
        id_count = len(bp_svc.list_identities())
        m1.metric("Blueprints", bp_count)
        m2.metric("Identities", id_count)
        m3.metric("Users", "—")

        st.markdown("---")

        # ── Create Entity ────────────────────────
        with st.expander("CREATE NEW ENTITY", expanded=False):
            entity_type = st.selectbox(
                "Entity Type",
                ["Blueprint", "Agent Identity"],
                key="viz_entity_type",
            )

            if entity_type == "Blueprint":
                _create_blueprint_form(bp_svc)
            else:
                _create_identity_form(bp_svc)

        # ── Delete Blueprint ─────────────────────
        with st.expander("DELETE BLUEPRINT", expanded=False):
            blueprints = bp_svc.list_blueprints()
            if blueprints:
                bp_names = {bp.display_name: bp.id for bp in blueprints}
                selected = st.selectbox(
                    "Select Blueprint to Delete",
                    options=list(bp_names.keys()),
                    key="viz_del_bp",
                )
                if st.button("DELETE", key="viz_del_btn"):
                    bp_svc.delete_blueprint(bp_names[selected])
                    st.rerun()
            else:
                st.info("No blueprints to delete.")


def _create_blueprint_form(bp_svc: BlueprintService) -> None:
    name = st.text_input("Display Name", key="viz_bp_name", placeholder="My AI Agent Platform")
    desc = st.text_input("Description", key="viz_bp_desc", placeholder="Platform for AI agents")
    tenant = st.text_input(
        "Tenant ID",
        key="viz_bp_tenant",
        placeholder="mytenant.onmicrosoft.com",
        value="contoso.onmicrosoft.com",
    )
    cred = st.selectbox(
        "Credential Type",
        ["Managed Identity (Recommended)", "Certificate", "Client Secret (Dev Only)"],
        key="viz_bp_cred",
    )
    cred_map = {
        "Managed Identity (Recommended)": CredentialType.MANAGED_IDENTITY,
        "Certificate": CredentialType.CERTIFICATE,
        "Client Secret (Dev Only)": CredentialType.CLIENT_SECRET,
    }

    if st.button("CREATE BLUEPRINT", key="viz_bp_create"):
        if name and tenant:
            bp_svc.create_blueprint(
                display_name=name,
                description=desc or "No description",
                credential_type=cred_map[cred],
                tenant_id=tenant,
            )
            st.rerun()
        else:
            st.warning("Display Name and Tenant ID are required.")


def _create_identity_form(bp_svc: BlueprintService) -> None:
    blueprints = bp_svc.list_blueprints()
    if not blueprints:
        st.info("Create a Blueprint first.")
        return

    bp_names = {bp.display_name: bp.id for bp in blueprints}
    selected_bp = st.selectbox(
        "Parent Blueprint",
        options=list(bp_names.keys()),
        key="viz_ai_bp",
    )
    name = st.text_input("Display Name", key="viz_ai_name", placeholder="My Agent")
    create_user = st.checkbox("Create Agent User Account", key="viz_ai_user")

    if st.button("CREATE AGENT IDENTITY", key="viz_ai_create"):
        if name:
            bp_svc.create_agent_identity(
                blueprint_id=bp_names[selected_bp],
                display_name=name,
                create_user_account=create_user,
            )
            st.rerun()
        else:
            st.warning("Display Name is required.")
