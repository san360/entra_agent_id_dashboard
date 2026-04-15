"""Dashboard page: relationship graph overview + entity summary."""

from __future__ import annotations

import streamlit as st

from config.azure_config import AzureConfig
from config.theme import (
    NODE_BLUEPRINT, NODE_IDENTITY, NODE_FOUNDRY, NODE_AGENT, NODE_USER,
    NODE_RESOURCE, NODE_DOMAIN,
)
from services.blueprint_service import BlueprintService
from services.cache import SessionCache
from services.foundry_service import FoundryService
from services.graph_client import GraphClient
from ui.components.relationship_graph import render_relationship_graph


def render(
    store: dict,
    *,
    graph: GraphClient,
    cache: SessionCache,
    config: AzureConfig,
    arm=None,
    **kwargs,
) -> None:
    st.markdown("## Relationship Overview")
    st.caption(
        "Visual map of how Foundry projects, blueprints, identities, and agents connect."
    )

    bp_svc = BlueprintService(graph=graph, cache=cache, config=config)
    foundry_svc = FoundryService(store=store, arm_client=arm)

    # Discover real Azure resources/projects (sync with Azure)
    if arm is not None:
        foundry_svc.discover_azure_resources()

    blueprints = bp_svc.list_blueprints()
    identities = bp_svc.list_identities()
    # Count agent users
    user_count = sum(
        1 for ai in identities
        if ai.has_user_account and bp_svc.get_agent_user(ai.id) is not None
    )
    foundry_projects = foundry_svc.list_projects()
    foundry_agent_count = sum(len(fp.agents) for fp in foundry_projects)
    foundry_resources = foundry_svc.list_resources()

    # Derive unique Foundry projects from blueprint metadata
    foundry_from_entra = {
        bp.foundry_resource_id: bp
        for bp in blueprints if bp.foundry_project_name
    }
    entra_foundry_count = len(foundry_from_entra)

    # ── Summary Metrics ────────────────────────────────────────────────
    # Count unique projects across local store and Entra metadata
    all_project_names: set = {fp.name for fp in foundry_projects}
    for bp in blueprints:
        if bp.foundry_project_name:
            all_project_names.add(bp.foundry_project_name)

    cols = st.columns(7)
    _metric_card(cols[0], "Blueprints", len(blueprints), NODE_BLUEPRINT)
    _metric_card(cols[1], "Identities", len(identities), NODE_IDENTITY)
    _metric_card(cols[2], "Agent Users", user_count, NODE_USER)
    _metric_card(cols[3], "Resources", len(foundry_resources), NODE_RESOURCE)
    _metric_card(cols[4], "Projects", len(all_project_names), NODE_FOUNDRY)
    _metric_card(cols[5], "Agents", foundry_agent_count, NODE_AGENT)
    # Unique domains
    domains = {fp.business_domain for fp in foundry_projects if hasattr(fp, 'business_domain')}
    _metric_card(cols[6], "Domains", len(domains), NODE_DOMAIN)

    st.markdown("---")

    # ── Graph Controls ─────────────────────────────────────────────────
    col_filter, col_opts, col_refresh = st.columns([2, 1, 1])

    with col_filter:
        bp_options = {"All Blueprints": None}
        bp_options.update({bp.display_name: bp.id for bp in blueprints})
        selected_label = st.selectbox(
            "Filter by Blueprint",
            options=list(bp_options.keys()),
            key="dash_bp_filter",
        )
        selected_bp_id = bp_options[selected_label]

    with col_opts:
        show_perms = st.checkbox("Show permissions", key="dash_show_perms", value=False)

    with col_refresh:
        if st.button("🔄 Refresh from Azure", key="dash_refresh"):
            # Clear cached blueprints/identities
            cache.invalidate_all()
            # Re-discover Azure resources (removes stale, adds new)
            if arm is not None:
                foundry_svc.discover_azure_resources()
            st.rerun()

    # ── Relationship Graph ─────────────────────────────────────────────
    if not blueprints:
        st.info("No blueprints found. Create one in **Manage Entities** to see the graph.")
    else:
        render_relationship_graph(
            bp_svc=bp_svc,
            foundry_svc=foundry_svc,
            selected_blueprint_id=selected_bp_id,
            show_permissions=show_perms,
        )

    st.markdown("---")

    # ── Entity Details Table ───────────────────────────────────────────
    st.markdown("### Entity Details")

    tab_bp, tab_foundry, tab_ids = st.tabs(
        ["Blueprints", "Foundry Projects", "Agent Identities"]
    )

    with tab_bp:
        if blueprints:
            for bp in blueprints:
                linked_ids = bp_svc.get_identities_for_blueprint(bp.id)
                with st.expander(f"📋 {bp.display_name}", expanded=False):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"**App ID:** `{bp.app_id}`")
                        st.markdown(f"**Credential:** {bp.credential_type.value}")
                        st.markdown(f"**Tenant:** {bp.tenant_id}")
                        st.markdown(f"**Identifier URI:** `{bp.identifier_uri}`")
                    with c2:
                        st.markdown(f"**Linked Identities:** {len(linked_ids)}")
                        if bp.foundry_project_name:
                            st.markdown(f"**Foundry Project:** {bp.foundry_project_name}")
                            st.markdown(f"**Foundry Account:** {bp.foundry_account_name}")
                            st.markdown(f"**Resource Group:** {bp.foundry_resource_group}")
                            st.markdown(f"**Subscription:** `{bp.foundry_subscription_id}`")
                        else:
                            st.markdown("**Foundry Project:** —")
        else:
            st.info("No blueprints created yet.")

    with tab_foundry:
        # Show Entra-linked projects (from blueprint metadata)
        if foundry_from_entra:
            st.markdown("##### 🔗 Entra-Linked Projects")
            # Group blueprints by Foundry project
            project_groups: dict = {}
            for bp in blueprints:
                if bp.foundry_resource_id:
                    project_groups.setdefault(bp.foundry_resource_id, []).append(bp)

            for resource_id, bps_in_project in project_groups.items():
                ref_bp = bps_in_project[0]
                project_ids = []
                for bp in bps_in_project:
                    project_ids.extend(bp_svc.get_identities_for_blueprint(bp.id))

                with st.expander(
                    f"☁️ {ref_bp.foundry_project_name} — "
                    f"{len(bps_in_project)} blueprints, {len(project_ids)} identities",
                    expanded=True,
                ):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"**Account:** {ref_bp.foundry_account_name}")
                        st.markdown(f"**Resource Group:** {ref_bp.foundry_resource_group}")
                        st.markdown(f"**Subscription:** `{ref_bp.foundry_subscription_id}`")
                        st.markdown(f"**Resource ID:**")
                        st.code(ref_bp.foundry_resource_id, language=None)
                    with c2:
                        st.markdown("**Blueprints in this project:**")
                        for bp in bps_in_project:
                            bp_ids = bp_svc.get_identities_for_blueprint(bp.id)
                            st.markdown(
                                f"  - 📋 **{bp.display_name}** "
                                f"({len(bp_ids)} identities)"
                            )

        # Show local store projects (linked via blueprint_id)
        if foundry_projects:
            # Group by domain
            domain_groups: dict = {}
            for fp in foundry_projects:
                domain = getattr(fp, 'business_domain', 'General')
                domain_groups.setdefault(domain, []).append(fp)

            for domain, projects in sorted(domain_groups.items()):
                st.markdown(f"##### 🏷️ Domain: {domain}")
                for fp in projects:
                    bp = bp_svc.get_blueprint(fp.blueprint_id) if fp.blueprint_id else None
                    bp_name = bp.display_name if bp else "—"
                    env_icon = {"dev": "🟢", "test": "🟡", "prod": "🔴"}.get(
                        getattr(fp, 'environment', ''), "⚪"
                    )
                    env = getattr(fp, 'environment', 'N/A')
                    with st.expander(
                        f"☁️ {fp.name} {env_icon} {env} — linked to {bp_name}",
                        expanded=False,
                    ):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown(f"**Region:** {fp.region}")
                            st.markdown(f"**Environment:** {env}")
                            st.markdown(f"**Domain:** {domain}")
                            st.markdown(f"**Resource Group:** {fp.resource_group}")
                            st.markdown(f"**Endpoint:** `{fp.endpoint}`")
                            st.markdown(f"**Blueprint:** {bp_name}")
                        with c2:
                            st.markdown(f"**Agents:** {len(fp.agents)}")
                            for agent in fp.agents:
                                ai = bp_svc.get_identity(agent.agent_identity_id)
                                ai_name = ai.display_name if ai else "Unknown"
                                status_icon = "🟢" if agent.status == "active" else "🟡"
                                st.markdown(
                                    f"  {status_icon} **{agent.name}** → {ai_name} "
                                    f"(model: {agent.model})"
                                )

        if not foundry_from_entra and not foundry_projects:
            st.info("No Foundry projects linked yet.")

    with tab_ids:
        if identities:
            for ai in identities:
                bp = bp_svc.get_blueprint(ai.blueprint_id)
                bp_name = bp.display_name if bp else "Unknown"
                with st.expander(f"🆔 {ai.display_name} — from {bp_name}", expanded=False):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"**Object ID:** `{ai.id}`")
                        st.markdown(f"**Client ID:** `{ai.client_id}`")
                        st.markdown(f"**Blueprint:** {bp_name}")
                    with c2:
                        if bp and bp.foundry_project_name:
                            st.markdown(f"**Foundry Project:** {bp.foundry_project_name}")
                            st.markdown(f"**Foundry Account:** {bp.foundry_account_name}")
                        else:
                            st.markdown("**Foundry Project:** —")
        else:
            st.info("No identities created yet.")


def _metric_card(col, label: str, value: int, color: str) -> None:
    col.markdown(
        f"<div class='info-card'>"
        f"<h4>{label}</h4>"
        f"<div class='value' style='color: {color};'>{value}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
