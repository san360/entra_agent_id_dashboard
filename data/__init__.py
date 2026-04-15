"""Initialize session state stores for local-only data (e.g., Foundry project associations)."""


def init_store(session_state) -> None:
    """Initialize session state with empty stores if not already present.

    Blueprints, identities, permissions, etc. are fetched live from
    Microsoft Graph. Only Foundry project associations are stored locally.
    """
    if "store_initialized" in session_state:
        return

    # Foundry project associations (local state — not in Graph)
    session_state.setdefault("foundry_resources", {})
    session_state.setdefault("foundry_projects", {})

    session_state["store_initialized"] = True
