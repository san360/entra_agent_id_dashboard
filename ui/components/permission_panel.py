"""Permission assignment panel: inheritable + direct + effective."""

from __future__ import annotations

from typing import List

import streamlit as st

from config.theme import GREEN_BRIGHT, GREEN_DIM, GREEN_FAINT, BG_PRIMARY, AMBER_WARN
from models.permission import Permission
from services.permission_service import PermissionService


def render_permission_panel(
    blueprint_id: str,
    agent_identity_id: str,
    perm_service: PermissionService,
    key_prefix: str = "perm",
) -> None:
    """Render the two-column permission assignment panel."""
    catalog = perm_service.get_permission_catalog()
    catalog_names = {p.id: p.name for p in catalog}
    catalog_by_name = {p.name: p for p in catalog}

    col1, col2 = st.columns(2)

    # ── Left Column: Inheritable (Blueprint-level) ─────────────────────
    with col1:
        st.markdown(
            f"<h4 style='color: {GREEN_BRIGHT}; font-family: \"Share Tech Mono\", monospace;'>"
            "BLUEPRINT PERMISSIONS</h4>"
            f"<p style='color: {GREEN_DIM}; font-size: 0.8em;'>"
            "Inherited by ALL agent identities</p>",
            unsafe_allow_html=True,
        )

        current_inherited = perm_service.get_inherited_permissions(blueprint_id)
        current_inherited_names = [p.name for p in current_inherited]

        selected_inherited = st.multiselect(
            "Inheritable Permissions",
            options=sorted(catalog_by_name.keys()),
            default=sorted(current_inherited_names),
            key=f"{key_prefix}_inherited",
        )

        if st.button("APPLY INHERITABLE", key=f"{key_prefix}_apply_inh"):
            # Add new
            for name in selected_inherited:
                if name not in current_inherited_names:
                    p = catalog_by_name[name]
                    perm_service.assign_inheritable(blueprint_id, p.id)
            # Remove deleted
            for name in current_inherited_names:
                if name not in selected_inherited:
                    p = catalog_by_name[name]
                    perm_service.remove_inheritable_by_perm(blueprint_id, p.id)
            st.rerun()

        # Display current
        if current_inherited:
            for p in current_inherited:
                st.markdown(
                    f"<span style='color: {GREEN_BRIGHT};'>"
                    f"\u2588 {p.name}</span> "
                    f"<span style='color: {GREEN_DIM}; font-size: 0.8em;'>"
                    f"({p.description})</span>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                f"<span style='color: {GREEN_DIM};'>No inheritable permissions set</span>",
                unsafe_allow_html=True,
            )

    # ── Right Column: Direct (Agent Identity-level) ────────────────────
    with col2:
        st.markdown(
            f"<h4 style='color: {GREEN_BRIGHT}; font-family: \"Share Tech Mono\", monospace;'>"
            "AGENT-SPECIFIC PERMISSIONS</h4>"
            f"<p style='color: {GREEN_DIM}; font-size: 0.8em;'>"
            "Assigned to this agent only</p>",
            unsafe_allow_html=True,
        )

        current_direct = perm_service.get_direct_permissions(agent_identity_id)
        current_direct_names = [p.name for p in current_direct]

        selected_direct = st.multiselect(
            "Direct Permissions",
            options=sorted(catalog_by_name.keys()),
            default=sorted(current_direct_names),
            key=f"{key_prefix}_direct",
        )

        if st.button("APPLY DIRECT", key=f"{key_prefix}_apply_dir"):
            for name in selected_direct:
                if name not in current_direct_names:
                    p = catalog_by_name[name]
                    perm_service.assign_direct(agent_identity_id, p.id)
            for name in current_direct_names:
                if name not in selected_direct:
                    p = catalog_by_name[name]
                    perm_service.remove_direct_by_perm(agent_identity_id, p.id)
            st.rerun()

        if current_direct:
            for p in current_direct:
                st.markdown(
                    f"<span style='color: {GREEN_BRIGHT};'>"
                    f"\u2588 {p.name}</span> "
                    f"<span style='color: {GREEN_DIM}; font-size: 0.8em;'>"
                    f"({p.description})</span>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                f"<span style='color: {GREEN_DIM};'>No direct permissions set</span>",
                unsafe_allow_html=True,
            )

    # ── Effective Permissions Table ────────────────────────────────────
    st.markdown("---")
    st.markdown(
        f"<h4 style='color: {GREEN_BRIGHT}; font-family: \"Share Tech Mono\", monospace;'>"
        "EFFECTIVE PERMISSIONS</h4>",
        unsafe_allow_html=True,
    )

    effective = perm_service.get_effective(agent_identity_id, blueprint_id)
    inherited_set = {p.id for p in effective.inherited}
    direct_set = {p.id for p in effective.direct}

    if not effective.all_permissions:
        st.markdown(
            f"<span style='color: {GREEN_DIM};'>No permissions assigned</span>",
            unsafe_allow_html=True,
        )
        return

    # Build table rows
    header = (
        f"<pre style=\"font-family: 'Share Tech Mono', monospace; "
        f"color: {GREEN_BRIGHT}; background: {BG_PRIMARY}; "
        f"padding: 8px; border: 1px solid {GREEN_DIM}; line-height: 1.6;\">"
    )
    header += f"{'Permission':<25} {'Source':<12} {'Resource':<20}\n"
    header += f"{'─' * 25} {'─' * 12} {'─' * 20}\n"

    rows = []
    for p in effective.all_permissions:
        source_parts = []
        if p.id in inherited_set:
            source_parts.append("INHERIT")
        if p.id in direct_set:
            source_parts.append("DIRECT")
        source = " + ".join(source_parts)

        if "INHERIT" in source and "DIRECT" in source:
            color = AMBER_WARN
        elif "DIRECT" in source:
            color = "#33FF77"
        else:
            color = GREEN_BRIGHT

        rows.append(
            f"<span style='color: {color};'>"
            f"{p.name:<25} {source:<12} {p.resource_app_display_name:<20}"
            f"</span>"
        )

    table_html = header + "\n".join(rows) + "</pre>"
    st.markdown(table_html, unsafe_allow_html=True)
