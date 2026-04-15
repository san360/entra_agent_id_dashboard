"""Hierarchical tree view component using ASCII art + selectbox."""

from __future__ import annotations

from typing import List

import streamlit as st

from config.theme import GREEN_BRIGHT, GREEN_DIM, BG_PRIMARY, WHITE_TEXT
from services.hierarchy_service import HierarchyNode
from ui.components.terminal_chrome import render_terminal_box


# Icons with color hints
_TYPE_COLORS = {
    "blueprint": "#00FF41",
    "principal": "#00CC33",
    "identity": "#33FF77",
    "user": "#66FFAA",
}

_TYPE_LABELS = {
    "blueprint": "BLUEPRINT",
    "principal": "SERVICE PRINCIPAL",
    "identity": "AGENT IDENTITY",
    "user": "AGENT USER",
}


def _build_tree_text(
    node: HierarchyNode, prefix: str = "", is_last: bool = True, depth: int = 0
) -> List[str]:
    """Recursively build ASCII tree lines."""
    lines = []
    if depth == 0:
        connector = ""
        child_prefix = ""
    else:
        connector = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "
        child_prefix = "    " if is_last else "\u2502   "

    label = f"{node.icon} {node.display_name}"
    lines.append(f"{prefix}{connector}{label}")

    for i, child in enumerate(node.children):
        is_child_last = i == len(node.children) - 1
        lines.extend(
            _build_tree_text(child, prefix + child_prefix, is_child_last, depth + 1)
        )
    return lines


def _collect_nodes(node: HierarchyNode) -> List[HierarchyNode]:
    """Flatten all nodes for the selectbox."""
    result = [node]
    for child in node.children:
        result.extend(_collect_nodes(child))
    return result


def render_tree(forest: List[HierarchyNode], key_prefix: str = "tree") -> None:
    """Render the hierarchy as an ASCII tree with a detail panel."""
    if not forest:
        st.markdown(
            f"<span style='color: {GREEN_DIM};'>No blueprints found. "
            "Create one to get started.</span>",
            unsafe_allow_html=True,
        )
        return

    # Build full ASCII tree
    all_lines = []
    all_nodes = []
    for i, root in enumerate(forest):
        if i > 0:
            all_lines.append("")
        tree_lines = _build_tree_text(root)
        all_lines.extend(tree_lines)
        all_nodes.extend(_collect_nodes(root))

    # Render tree
    tree_text = "\n".join(all_lines)
    import html as _html
    escaped_tree = _html.escape(tree_text)
    st.markdown(
        f"<pre style=\"font-family: 'Share Tech Mono', monospace; "
        f"color: {GREEN_BRIGHT}; background: {BG_PRIMARY}; "
        f"padding: 12px; border: 1px solid {GREEN_DIM}; "
        f"line-height: 1.6; white-space: pre; overflow-x: auto; "
        f"max-height: 500px; overflow-y: auto;\">"
        f"{escaped_tree}</pre>",
        unsafe_allow_html=True,
    )

    # Node selector
    node_labels = [
        f"{n.icon} {n.display_name} ({_TYPE_LABELS.get(n.node_type, n.node_type)})"
        for n in all_nodes
    ]

    selected_idx = st.selectbox(
        "SELECT NODE FOR DETAILS",
        range(len(node_labels)),
        format_func=lambda i: node_labels[i],
        key=f"{key_prefix}_select",
    )

    if selected_idx is not None and selected_idx < len(all_nodes):
        selected_node = all_nodes[selected_idx]
        render_node_detail(selected_node)


def render_node_detail(node: HierarchyNode) -> None:
    """Render the detail panel for a selected node."""
    type_label = _TYPE_LABELS.get(node.node_type, node.node_type.upper())
    rows = list(node.metadata.items())
    render_terminal_box(f"{type_label} DETAILS", rows, width=60)
