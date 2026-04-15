"""Terminal chrome: CRT effects, headers, banners, and terminal box utility."""

import streamlit as st

from config.theme import GLOBAL_CSS, AMBER_WARN, GREEN_BRIGHT, GREEN_DIM, BG_PRIMARY


def inject_global_css() -> None:
    """Inject global CSS for the retro terminal aesthetic."""
    st.markdown(f"<style>{GLOBAL_CSS}</style>", unsafe_allow_html=True)


def render_terminal_header(title: str, subtitle: str = "") -> None:
    """Render a box-drawing terminal header."""
    width = max(len(title), len(subtitle)) + 6
    top = f"\u250c{'─' * width}\u2510"
    mid_title = f"\u2502  {title.upper():<{width - 4}}  \u2502"
    bot = f"\u2514{'─' * width}\u2518"

    lines = [top, mid_title]
    if subtitle:
        mid_sub = f"\u2502  > {subtitle:<{width - 6}}<span class='cursor-blink'>\u2588</span> \u2502"
        lines.append(mid_sub)
    lines.append(bot)

    html = f"""<pre style="font-family: 'Share Tech Mono', monospace;
    color: {GREEN_BRIGHT}; background: {BG_PRIMARY};
    line-height: 1.5; padding: 8px 0; margin: 0 0 16px 0;
    border: none;">{'<br>'.join(lines)}</pre>"""
    st.markdown(html, unsafe_allow_html=True)


def render_simulated_banner() -> None:
    """Render the SIMULATED warning banner."""
    st.markdown(
        '<div class="sim-banner">'
        "\u26a0\ufe0f  EDUCATIONAL SIMULATION \u2014 NO REAL AZURE CREDENTIALS OR CONNECTIONS  "
        "\u26a0\ufe0f<br>"
        "All identities, tokens, and permissions are simulated for learning purposes only."
        "</div>",
        unsafe_allow_html=True,
    )


def terminal_box(title: str, rows: list, width: int = 56) -> str:
    """Build an HTML string for a terminal-style box with key-value rows.

    Args:
        title: Box title (displayed in the top border).
        rows: List of (key, value) tuples.
        width: Total character width of the box.

    Returns:
        HTML string wrapped in <pre> tags.
    """
    inner = width - 2
    title_bar = f"\u250c\u2500 {title.upper()} " + "\u2500" * (inner - len(title) - 3) + "\u2510"
    bottom = f"\u2514{'─' * inner}\u2518"

    lines = [title_bar]
    for key, val in rows:
        val_str = str(val)
        content_width = inner - 2
        key_part = f"<span class='tb-key'>{key}:</span>"
        key_len = len(key) + 1
        padding = content_width - key_len - 1
        val_display = val_str[:padding] if len(val_str) > padding else val_str
        line = f"\u2502 {key_part} <span class='tb-val'>{val_display:<{padding}}</span>\u2502"
        lines.append(line)
    lines.append(bottom)

    return (
        f"<pre class='terminal-box' style=\"font-family: 'Share Tech Mono', monospace; "
        f"color: {GREEN_BRIGHT}; background: {BG_PRIMARY}; padding: 4px 0; "
        f"margin: 4px 0; border: none; line-height: 1.4;\">"
        f"{'<br>'.join(lines)}</pre>"
    )


def render_terminal_box(title: str, rows: list, width: int = 56) -> None:
    """Render a terminal box directly via st.markdown."""
    st.markdown(terminal_box(title, rows, width), unsafe_allow_html=True)


def render_connection_banner(config) -> None:
    """Render a green 'CONNECTED TO AZURE' banner for live mode."""
    st.markdown(
        f"<div style='text-align: center; padding: 8px; "
        f"border: 1px solid {GREEN_BRIGHT}; margin-bottom: 16px; "
        f"background: rgba(0,255,65,0.05); "
        f"font-family: \"Share Tech Mono\", monospace;'>"
        f"<span style='color: {GREEN_BRIGHT}; font-size: 0.85em;'>"
        f"CONNECTED TO AZURE | Tenant: {config.tenant_id} | "
        f"Graph API: {config.graph_base_url}</span></div>",
        unsafe_allow_html=True,
    )


def render_status_line(text: str, status: str = "green") -> None:
    """Render a colored status line."""
    cls = f"status-{status}"
    st.markdown(
        f"<span class='{cls}' style=\"font-family: 'Share Tech Mono', monospace;\">"
        f"{text}</span>",
        unsafe_allow_html=True,
    )
