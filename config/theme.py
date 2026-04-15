"""Clean, modern theme configuration — focused on usability over aesthetics."""

# ── Color Palette ──────────────────────────────────────────────────────────────
# Keep existing names for backward compat but map to clean colors
BG_PRIMARY = "#FFFFFF"
BG_SECONDARY = "#F8F9FA"
GREEN_BRIGHT = "#0078D4"    # Primary blue (Azure blue)
GREEN_MID = "#106EBE"       # Darker blue
GREEN_DIM = "#605E5C"       # Gray text
GREEN_FAINT = "#EDEBE9"     # Light gray bg
AMBER_WARN = "#D83B01"      # Warning orange
RED_ALERT = "#A4262C"       # Error red
WHITE_TEXT = "#323130"       # Dark text

# New semantic names
COLOR_PRIMARY = "#0078D4"
COLOR_SUCCESS = "#107C10"
COLOR_WARNING = "#D83B01"
COLOR_DANGER = "#A4262C"
COLOR_INFO = "#0078D4"
COLOR_TEXT = "#323130"
COLOR_TEXT_SECONDARY = "#605E5C"
COLOR_BORDER = "#EDEBE9"
COLOR_BG_CARD = "#FFFFFF"
COLOR_BG_PAGE = "#FAF9F8"

# Node colors for relationship graph
NODE_FOUNDRY = "#6B3FA0"     # Purple for Foundry projects
NODE_RESOURCE = "#4B0082"    # Indigo for Foundry resources (AI Services account)
NODE_DOMAIN = "#B4009E"      # Magenta for business domains
NODE_BLUEPRINT = "#0078D4"   # Blue for Blueprints
NODE_PRINCIPAL = "#038387"   # Teal for Service Principals
NODE_IDENTITY = "#CA5010"    # Orange for Agent Identities
NODE_USER = "#8764B8"        # Violet for Agent Users
NODE_AGENT = "#498205"       # Green for Foundry Agents
NODE_PERMISSION = "#69797E"  # Gray for Permissions

# ── Font ───────────────────────────────────────────────────────────────────────
FONT_FAMILY = "'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif"
FONT_MONO = "'Cascadia Code', 'Consolas', 'Courier New', monospace"

# ── CSS Injection ──────────────────────────────────────────────────────────────
GLOBAL_CSS = f"""
/* ── Clean Modern Reset ──────────────────────────────────────────────────── */
.stApp {{
    background-color: {COLOR_BG_PAGE};
}}

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {{
    background-color: #FFFFFF;
    border-right: 1px solid {COLOR_BORDER};
}}

/* ── Cards ────────────────────────────────────────────────────────────────── */
.info-card {{
    background: white;
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 16px;
    margin: 8px 0;
}}
.info-card h4 {{
    margin: 0 0 8px 0;
    color: {COLOR_TEXT};
    font-size: 0.95em;
}}
.info-card .value {{
    font-size: 1.4em;
    font-weight: 600;
    color: {COLOR_PRIMARY};
}}

/* ── Metric Cards ────────────────────────────────────────────────────────── */
div[data-testid="stMetric"] {{
    background-color: white;
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 16px;
}}

/* ── Status Badge ────────────────────────────────────────────────────────── */
.status-badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.8em;
    font-weight: 500;
}}
.status-connected {{
    background: #DFF6DD;
    color: #0E700E;
    border: 1px solid #9ED89E;
}}

/* ── Entity Tags ─────────────────────────────────────────────────────────── */
.entity-tag {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75em;
    font-weight: 600;
    margin-right: 4px;
}}
.tag-blueprint {{ background: #E5F1FB; color: {NODE_BLUEPRINT}; }}
.tag-principal {{ background: #E3F5F5; color: {NODE_PRINCIPAL}; }}
.tag-identity {{ background: #FFF0E0; color: {NODE_IDENTITY}; }}
.tag-user {{ background: #F0EBF8; color: {NODE_USER}; }}
.tag-foundry {{ background: #F0EBF8; color: {NODE_FOUNDRY}; }}
.tag-agent {{ background: #E8F5E0; color: {NODE_AGENT}; }}

/* ── Relationship lines ──────────────────────────────────────────────────── */
.rel-line {{
    border-left: 2px solid {COLOR_BORDER};
    padding-left: 16px;
    margin-left: 16px;
}}

/* ── Detail Panel ────────────────────────────────────────────────────────── */
.detail-panel {{
    background: white;
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 20px;
    margin: 8px 0;
}}
.detail-panel .detail-row {{
    display: flex;
    padding: 6px 0;
    border-bottom: 1px solid #F3F2F1;
    font-size: 0.9em;
}}
.detail-panel .detail-key {{
    color: {COLOR_TEXT_SECONDARY};
    min-width: 140px;
    font-weight: 500;
}}
.detail-panel .detail-value {{
    color: {COLOR_TEXT};
    word-break: break-all;
}}

/* ── Status Indicators ───────────────────────────────────────────────────── */
.status-green {{ color: {COLOR_SUCCESS}; }}
.status-amber {{ color: {COLOR_WARNING}; }}
.status-red   {{ color: {COLOR_DANGER}; }}

/* ── Graph legend ────────────────────────────────────────────────────────── */
.legend-item {{
    display: inline-flex;
    align-items: center;
    margin-right: 16px;
    font-size: 0.85em;
    color: {COLOR_TEXT_SECONDARY};
}}
.legend-dot {{
    width: 12px;
    height: 12px;
    border-radius: 50%;
    margin-right: 6px;
    display: inline-block;
}}
"""
