"""Interactive relationship graph showing Blueprint → Identity → Foundry connections."""

from __future__ import annotations

from typing import Optional

import graphviz
import streamlit as st

from config.theme import (
    NODE_FOUNDRY, NODE_BLUEPRINT, NODE_PRINCIPAL,
    NODE_IDENTITY, NODE_USER, NODE_AGENT, NODE_PERMISSION,
)
from services.blueprint_service import BlueprintService
from services.foundry_service import FoundryService


def _hex_to_lighter(hex_color: str, factor: float = 0.85) -> str:
    """Make a hex color lighter for fill backgrounds."""
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def build_relationship_graph(
    bp_svc: BlueprintService,
    foundry_svc: FoundryService,
    selected_blueprint_id: Optional[str] = None,
    show_permissions: bool = False,
) -> graphviz.Digraph:
    """Build a graphviz Digraph showing entity relationships."""
    dot = graphviz.Digraph(
        comment="Entra Agent ID Relationships",
        engine="dot",
    )
    dot.attr(
        rankdir="TB",
        bgcolor="transparent",
        fontname="Segoe UI",
        pad="0.5",
        nodesep="0.6",
        ranksep="0.8",
    )
    dot.attr("node", fontname="Segoe UI", fontsize="11", style="filled,rounded", shape="box")
    dot.attr("edge", fontname="Segoe UI", fontsize="9", color="#A19F9D", fontcolor="#605E5C")

    blueprints = bp_svc.list_blueprints()
    if selected_blueprint_id:
        blueprints = [bp for bp in blueprints if bp.id == selected_blueprint_id]

    # Track rendered Foundry project nodes to avoid duplicates
    rendered_foundry: set = set()
    # Track rendered blueprint nodes
    rendered_bp: set = set()
    # Map project names → graph node IDs for unification
    project_name_to_node: dict = {}

    for bp in blueprints:
        # Blueprint node
        rendered_bp.add(bp.id)
        dot.node(
            f"bp_{bp.id}",
            f"📋 {bp.display_name}\n(Blueprint)",
            fillcolor=_hex_to_lighter(NODE_BLUEPRINT),
            color=NODE_BLUEPRINT,
            fontcolor="#1A1A1A",
            penwidth="2",
        )

        # Foundry project from blueprint metadata
        if bp.foundry_project_name and bp.foundry_resource_id not in rendered_foundry:
            rendered_foundry.add(bp.foundry_resource_id)
            node_id = f"fp_{bp.foundry_resource_id}"
            project_name_to_node[bp.foundry_project_name] = node_id
            dot.node(
                node_id,
                f"☁️ {bp.foundry_project_name}\n(Foundry Project)\n"
                f"{bp.foundry_account_name} / {bp.foundry_resource_group}",
                fillcolor=_hex_to_lighter(NODE_FOUNDRY),
                color=NODE_FOUNDRY,
                fontcolor="#1A1A1A",
                penwidth="2",
            )

        # Link blueprint → Foundry project
        if bp.foundry_project_name:
            dot.edge(
                f"fp_{bp.foundry_resource_id}", f"bp_{bp.id}",
                label="provisions",
                style="dashed",
                color=NODE_FOUNDRY,
                fontcolor=NODE_FOUNDRY,
            )

        # Agent Identities under this blueprint
        identities = bp_svc.get_identities_for_blueprint(bp.id)
        for ai in identities:
            dot.node(
                f"ai_{ai.id}",
                f"🆔 {ai.display_name}\n(Agent Identity)",
                fillcolor=_hex_to_lighter(NODE_IDENTITY),
                color=NODE_IDENTITY,
                fontcolor="#1A1A1A",
            )
            dot.edge(
                f"bp_{bp.id}", f"ai_{ai.id}",
                label="creates",
                color=NODE_BLUEPRINT,
                fontcolor=NODE_BLUEPRINT,
            )

    # ── Foundry projects from local store ───
    for fp in foundry_svc.list_projects():
        # Reuse existing project node if the project was already rendered
        # from Entra metadata (same project name)
        existing_node = project_name_to_node.get(fp.name)
        if existing_node:
            fp_node_id = existing_node
        else:
            if fp.id in rendered_foundry:
                continue
            rendered_foundry.add(fp.id)
            fp_node_id = f"fp_{fp.id}"
            project_name_to_node[fp.name] = fp_node_id
            dot.node(
                fp_node_id,
                f"☁️ {fp.name}\n(Foundry Project)\n{fp.region}",
                fillcolor=_hex_to_lighter(NODE_FOUNDRY),
                color=NODE_FOUNDRY,
                fontcolor="#1A1A1A",
                penwidth="2",
            )

        # Show agents under this project
        for agent in fp.agents:
            dot.node(
                f"agent_{agent.id}",
                f"🤖 {agent.name}\n(Agent)\n{agent.model}",
                fillcolor=_hex_to_lighter(NODE_AGENT),
                color=NODE_AGENT,
                fontcolor="#1A1A1A",
            )
            dot.edge(
                fp_node_id, f"agent_{agent.id}",
                label="hosts",
                color=NODE_FOUNDRY,
                fontcolor=NODE_FOUNDRY,
            )

    return dot


def render_graph_legend() -> None:
    """Render color legend for the graph."""
    items = [
        (NODE_FOUNDRY, "Foundry Project"),
        (NODE_BLUEPRINT, "Blueprint / Domain Blueprint"),
        (NODE_IDENTITY, "Agent Identity"),
        (NODE_AGENT, "Agent"),
    ]
    legend_html = " ".join(
        f"<span class='legend-item'>"
        f"<span class='legend-dot' style='background:{color};'></span>"
        f"{label}</span>"
        for color, label in items
    )
    edge_legend = (
        " &nbsp;│&nbsp; "
        "<span style='font-size:0.85em;color:#605E5C;'>"
        "── governs &nbsp; ⤳ provisions &nbsp; → creates"
        "</span>"
    )
    st.markdown(legend_html + edge_legend, unsafe_allow_html=True)


def render_relationship_graph(
    bp_svc: BlueprintService,
    foundry_svc: FoundryService,
    selected_blueprint_id: Optional[str] = None,
    show_permissions: bool = False,
) -> None:
    """Render the full relationship graph with legend."""
    dot = build_relationship_graph(
        bp_svc=bp_svc,
        foundry_svc=foundry_svc,
        selected_blueprint_id=selected_blueprint_id,
        show_permissions=show_permissions,
    )
    render_graph_legend()
    st.graphviz_chart(dot, width='stretch')
