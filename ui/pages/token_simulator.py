"""Token Simulator page: step-by-step token generation flow.

Supports two modes:
- **Simulation mode** (default): Generates realistic synthetic tokens to visualize
  the full T1 → T2 → T3 flow.  Blueprint credentials are managed by the Azure
  platform (Copilot Studio / AI Foundry) and are NOT accessible to external tools,
  so live token exchange is impossible without an explicit dev-test secret.
- **Live mode** (opt-in): When BLUEPRINT_CLIENT_SECRET is set in .env, actual
  token requests are sent to the Entra ID token endpoint.

References:
- Article 2: https://derkvanderwoude.medium.com/from-blueprint-to-token-how-entra-agent-identity-inheritance-really-works-fed114abe281
  Token flow details: T1 aud = agent AppId, T2 includes xms_par_app_azp,
  sign-in logs show TWO entries per exchange, permissions merged at token time.
"""

from __future__ import annotations

import streamlit as st

from config.azure_config import AzureConfig
from config.theme import GREEN_BRIGHT, GREEN_DIM, AMBER_WARN, RED_ALERT
from services.blueprint_service import BlueprintService
from services.cache import SessionCache
from services.graph_client import GraphClient
from services.permission_service import PermissionService
from services.token_service import TokenService
from ui.components.token_flow import (
    render_flow_diagram,
    render_credential_selector,
    render_token_step,
)


def _is_live_mode(config: AzureConfig) -> bool:
    """Return True if a blueprint client secret is available for live token exchange."""
    return bool(config.blueprint_client_secret)


def render(
    store: dict,
    *,
    graph: GraphClient,
    cache: SessionCache,
    config: AzureConfig,
) -> None:
    st.markdown("## Token Simulator")

    live = _is_live_mode(config)
    if live:
        st.caption("**LIVE MODE** — Step-by-step T1 → T2 → T3 token generation flow against your Azure tenant.")
    else:
        st.caption("**SIMULATION MODE** — Visualizing the T1 → T2 → T3 token flow with synthetic tokens.")
        st.markdown(
            f"<div style='border: 1px solid {AMBER_WARN}; padding: 10px 14px; "
            f"margin-bottom: 12px; background: rgba(255,176,0,0.05); "
            f"font-family: \"Share Tech Mono\", monospace; font-size: 0.85em;'>"
            f"<span style='color: {AMBER_WARN};'>ℹ SIMULATION MODE</span><br>"
            f"<span style='color: {GREEN_DIM};'>"
            "Blueprint credentials are managed by the Azure platform (Copilot Studio / AI Foundry) "
            "and are not accessible to external tools. Tokens shown below are synthetic but "
            "accurately represent the structure, claims, and flow of real Entra Agent ID tokens.<br><br>"
            "To enable <b>live token exchange</b>, add a dev-test secret to your blueprint app "
            "registration and set <code>BLUEPRINT_CLIENT_SECRET</code> in your <code>.env</code> file. "
            "See <a href='https://derkvanderwoude.medium.com/from-blueprint-to-token-how-entra-agent-identity-inheritance-really-works-fed114abe281' "
            "style='color: {AMBER_WARN};'>Article 2 § 7</a> for details."
            "</span></div>",
            unsafe_allow_html=True,
        )

    bp_svc = BlueprintService(graph=graph, cache=cache, config=config)
    perm_svc = PermissionService(graph=graph, cache=cache, config=config)
    token_svc = TokenService(graph=graph, cache=cache, config=config)

    # ── Init session state for token sim ───────────────────────────────
    if "tsim_step" not in st.session_state:
        st.session_state.tsim_step = 1
    if "tsim_t1" not in st.session_state:
        st.session_state.tsim_t1 = None
        st.session_state.tsim_t1_claims = None
    if "tsim_t2" not in st.session_state:
        st.session_state.tsim_t2 = None
        st.session_state.tsim_t2_claims = None
    if "tsim_t3" not in st.session_state:
        st.session_state.tsim_t3 = None
        st.session_state.tsim_t3_claims = None

    # ── Blueprint & Identity Selection ─────────────────────────────────
    blueprints = bp_svc.list_blueprints()
    if not blueprints:
        st.info("No blueprints found. Create one in Manage Entities.")
        return

    col_bp, col_ai = st.columns(2)
    with col_bp:
        bp_names = {bp.display_name: bp.id for bp in blueprints}
        selected_bp_name = st.selectbox(
            "SELECT BLUEPRINT",
            options=list(bp_names.keys()),
            key="tsim_bp_select",
        )
    selected_bp_id = bp_names[selected_bp_name]
    blueprint = bp_svc.get_blueprint(selected_bp_id)

    with col_ai:
        identities = bp_svc.get_identities_for_blueprint(selected_bp_id)
        if not identities:
            st.info("No agent identities available.")
            return
        ai_names = {ai.display_name: ai.id for ai in identities}
        selected_ai_name = st.selectbox(
            "SELECT AGENT IDENTITY",
            options=list(ai_names.keys()),
            key="tsim_ai_select",
        )
    selected_ai_id = ai_names[selected_ai_name]
    agent_identity = bp_svc.get_identity(selected_ai_id)
    agent_user = bp_svc.get_agent_user(selected_ai_id) if agent_identity.has_user_account else None

    # Reset button
    if st.button("RESET SIMULATION", key="tsim_reset"):
        st.session_state.tsim_step = 1
        st.session_state.tsim_t1 = None
        st.session_state.tsim_t1_claims = None
        st.session_state.tsim_t2 = None
        st.session_state.tsim_t2_claims = None
        st.session_state.tsim_t3 = None
        st.session_state.tsim_t3_claims = None
        st.rerun()

    st.markdown("---")

    # ── Flow Diagram ──────────────────────────────────────────────────
    render_flow_diagram(st.session_state.tsim_step, agent_identity.has_user_account)

    st.markdown("---")

    # ── Step 1: Credential Configuration ──────────────────────────────
    render_credential_selector(
        credential_type=blueprint.credential_type.value,
        credential_hint=blueprint.credential_hint,
    )

    if st.session_state.tsim_step == 1:
        if st.button("PROCEED TO TOKEN GENERATION", key="tsim_proceed"):
            st.session_state.tsim_step = 2
            st.rerun()
        return

    st.markdown("---")

    # ── Step 2: T1 — Blueprint Token ──────────────────────────────────
    t1_request = token_svc.build_t1_request(blueprint, agent_identity)
    t1_transmitted = render_token_step(
        step_number=2,
        title="BLUEPRINT TOKEN (T1)",
        description=(
            "Blueprint authenticates to Entra ID, targeting the agent identity via fmi_path. "
            "Per Article 2: fmi_path MUST match the agent's AppId, NOT the blueprint's."
        ),
        request=t1_request,
        response=st.session_state.tsim_t1,
        claims=st.session_state.tsim_t1_claims,
        is_active=(st.session_state.tsim_step == 2),
        is_completed=(st.session_state.tsim_step > 2),
        is_locked=False,
        on_transmit_key="tsim_t1_transmit",
        claims_annotations={
            "aud": "api://{agent-client-id} \u2014 proves authorization to impersonate this agent",
            "sub": "Blueprint service principal OID",
            "idtyp": "\"app\" \u2014 application-only token",
            "azp": "Blueprint's App ID (authorized party)",
            "azpacr": "\"2\" = certificate/MI, \"1\" = client secret",
            "appid": "Blueprint's App ID",
            "fmi_path": "\u26a0 Must match agent's AppId, NOT blueprint's. \"If they match, something went wrong.\"",
        },
    )
    if t1_transmitted:
        if live:
            resp, claims = token_svc.generate_t1(blueprint, agent_identity)
        else:
            resp, claims = token_svc.simulate_t1(blueprint, agent_identity)
        st.session_state.tsim_t1 = resp
        st.session_state.tsim_t1_claims = claims
        st.session_state.tsim_step = 3
        st.rerun()

    if st.session_state.tsim_step < 3:
        return

    st.markdown("---")

    # ── Step 3: T2 — Agent Identity Token ─────────────────────────────
    effective = perm_svc.get_effective(selected_ai_id, selected_bp_id)
    t2_request = token_svc.build_t2_request(
        t1_token=st.session_state.tsim_t1.access_token,
        agent_identity=agent_identity,
    )
    t2_transmitted = render_token_step(
        step_number=3,
        title="AGENT IDENTITY TOKEN (T2/TR)",
        description=(
            "Exchange T1 for an access token scoped to the downstream resource. "
            "Per Article 2: roles = direct appRoleAssignments, scp = inherited delegated scopes."
        ),
        request=t2_request,
        response=st.session_state.tsim_t2,
        claims=st.session_state.tsim_t2_claims,
        is_active=(st.session_state.tsim_step == 3),
        is_completed=(st.session_state.tsim_step > 3),
        is_locked=False,
        on_transmit_key="tsim_t2_transmit",
        claims_annotations={
            "appid": "Agent Identity's App ID (not blueprint's)",
            "xms_par_app_azp": "\u2605 KEY CLAIM \u2014 Blueprint's App ID confirming parent-child relationship",
            "roles": "Direct appRoleAssignments (NOT inherited \u2014 per Article 2 Category 3)",
            "scp": "Inherited delegated scopes (dynamically merged from blueprint at token time)",
            "sub": "Agent Identity's Object ID",
            "aud": "Downstream resource (e.g., Microsoft Graph)",
            "azp": "Agent Identity's Client ID (authorized party)",
            "idtyp": "\"app\" \u2014 Application identity token",
        },
    )
    if t2_transmitted:
        if live:
            resp, claims = token_svc.generate_t2(
                blueprint, agent_identity, effective,
                t1_access_token=st.session_state.tsim_t1.access_token,
            )
        else:
            resp, claims = token_svc.simulate_t2(blueprint, agent_identity, effective)
        st.session_state.tsim_t2 = resp
        st.session_state.tsim_t2_claims = claims
        st.session_state.tsim_step = 4
        st.rerun()

    if st.session_state.tsim_step < 4:
        return

    st.markdown("---")

    # ── Step 4: T3 — Agent User Token (Optional) ─────────────────────
    if not agent_identity.has_user_account or not agent_user:
        st.markdown(
            f"<div style='border: 1px solid {GREEN_DIM}; padding: 12px; "
            f"background: transparent; font-family: \"Share Tech Mono\", monospace;'>"
            f"<span style='color: {GREEN_DIM};'>"
            "\u25cb STEP 4: AGENT USER TOKEN (T3) \u2014 SKIPPED<br>"
            "  \u2514 This agent identity does not have an associated user account.<br>"
            "    Agent user tokens are only needed when accessing resources<br>"
            "    that require a user object (e.g., Exchange mailbox, Teams)."
            "</span></div>",
            unsafe_allow_html=True,
        )
        _render_completion(token_svc, blueprint, agent_identity)
        return

    t3_request = token_svc.build_t3_request(
        t1_token=st.session_state.tsim_t1.access_token,
        t2_token=st.session_state.tsim_t2.access_token,
        agent_identity=agent_identity,
        agent_user=agent_user,
    )
    t3_transmitted = render_token_step(
        step_number=4,
        title="AGENT USER TOKEN (T3)",
        description="Exchange tokens for a delegated user token (user_fic grant)",
        request=t3_request,
        response=st.session_state.tsim_t3,
        claims=st.session_state.tsim_t3_claims,
        is_active=(st.session_state.tsim_t3 is None),
        is_completed=(st.session_state.tsim_t3 is not None),
        is_locked=False,
        on_transmit_key="tsim_t3_transmit",
        claims_annotations={
            "idtyp": "\"user_fic\" \u2014 User token via Federated Identity Credential",
            "sub": "Agent User's Object ID (user principal)",
            "upn": "Agent User's UPN (e.g., agent@tenant.onmicrosoft.com)",
            "scp": "Delegated scopes (space-separated, like user tokens)",
            "aud": "Downstream resource the user token targets",
            "xms_par_app_azp": "Blueprint's App ID (maintained through the chain)",
            "appid": "Agent Identity's App ID (issuing identity)",
        },
    )
    if t3_transmitted:
        resp, claims = token_svc.generate_t3(
            blueprint, agent_identity, agent_user,
            t1_access_token=st.session_state.tsim_t1.access_token,
            t2_access_token=st.session_state.tsim_t2.access_token,
        )
        st.session_state.tsim_t3 = resp
        st.session_state.tsim_t3_claims = claims
        st.rerun()

    if st.session_state.tsim_t3 is not None:
        _render_completion(token_svc, blueprint, agent_identity)


def _render_completion(
    token_svc: TokenService,
    blueprint,
    agent_identity,
) -> None:
    st.markdown("---")
    st.markdown(
        f"<div style='border: 1px solid {GREEN_BRIGHT}; padding: 16px; "
        f"text-align: center; background: rgba(0,255,65,0.05); "
        f"font-family: \"Share Tech Mono\", monospace;'>"
        f"<span style='color: {GREEN_BRIGHT}; font-size: 1.2em;'>"
        "\u2713 TOKEN GENERATION COMPLETE</span><br>"
        f"<span style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        "The agent can now access downstream resources using the acquired tokens."
        "</span></div>",
        unsafe_allow_html=True,
    )

    # Sign-in log simulation (Article 2)
    st.markdown(
        f"<h5 style='color: {GREEN_BRIGHT}; margin-top: 16px;'>"
        "\u25b8 Simulated Sign-in Log Entries (Article 2)</h5>"
        f"<p style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        "Per Article 2: Each token exchange produces TWO sign-in log entries. "
        "Use these to audit agent activity.</p>",
        unsafe_allow_html=True,
    )

    log_entries = token_svc.get_sign_in_log_entries(blueprint, agent_identity)
    log_rows = ""
    for entry in log_entries:
        log_rows += (
            f"  {entry['entry']:<18} {entry['principal']:<28} "
            f"{entry['resource']:<35} {entry['status']:<10} {entry['auth_method']}\n"
        )

    log_html = f"""<pre style="font-family: 'Share Tech Mono', monospace;
color: {GREEN_BRIGHT}; background: rgba(0,0,0,0.3);
padding: 12px; line-height: 1.5; font-size: 0.85em;">
  {'Entry':<18} {'Principal':<28} {'Resource':<35} {'Status':<10} Auth Method
  {'─' * 18} {'─' * 28} {'─' * 35} {'─' * 10} {'─' * 20}
{log_rows}</pre>"""
    st.markdown(log_html, unsafe_allow_html=True)
