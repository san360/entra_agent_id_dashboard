"""Token flow visualization: step-by-step token generation with request/response display."""

from __future__ import annotations

from typing import Optional

import streamlit as st

from config.theme import GREEN_BRIGHT, GREEN_DIM, GREEN_FAINT, BG_PRIMARY, BG_SECONDARY, AMBER_WARN, RED_ALERT, WHITE_TEXT
from models.token import TokenRequest, TokenResponse, JWTClaims


def render_flow_diagram(current_step: int, has_user: bool) -> None:
    """Render ASCII flow diagram at the top."""
    def _color(step: int) -> str:
        if step < current_step:
            return GREEN_DIM
        elif step == current_step:
            return GREEN_BRIGHT
        else:
            return GREEN_FAINT

    c1 = _color(1)
    c2 = _color(2)
    c3 = _color(3)
    c4 = _color(4)

    user_line = ""
    if has_user:
        user_line = f"""
<span style="color: {c4};">                                     \u2514\u2500\u2500 T3 \u2500\u2500> [Agent User Context]</span>"""

    diagram = f"""<pre style="font-family: 'Share Tech Mono', monospace;
color: {GREEN_BRIGHT}; background: {BG_PRIMARY};
padding: 12px; border: 1px solid {GREEN_DIM};
line-height: 1.6;">
<span style="color: {c1};">[Credential]</span> <span style="color: {c2};">\u2500\u2500 T1 \u2500\u2500> [Blueprint]</span> <span style="color: {c3};">\u2500\u2500 T2 \u2500\u2500> [Agent Identity] \u2500\u2500> [Resource]</span>{user_line}

Step: <span style="color: {GREEN_BRIGHT};">{'>' * current_step}{'.' * (4 - current_step)}</span> ({current_step}/4)
</pre>"""
    st.markdown(diagram, unsafe_allow_html=True)


def render_credential_selector(credential_type: str, credential_hint: str) -> None:
    """Display credential type with security ranking."""
    creds = [
        ("Managed Identity", "green", "RECOMMENDED",
         "Credential managed by Azure. No secrets stored.",
         credential_type == "managed_identity"),
        ("Certificate", "amber", "GOOD",
         "X.509 certificate with thumbprint authentication.",
         credential_type == "certificate"),
        ("Client Secret", "red", "DEV ONLY",
         "Secret string. NEVER use in production.",
         credential_type == "client_secret"),
    ]

    st.markdown(
        f"<h4 style='color: {GREEN_BRIGHT}; font-family: \"Share Tech Mono\", monospace;'>"
        "STEP 1: CREDENTIAL CONFIGURATION</h4>",
        unsafe_allow_html=True,
    )

    for name, status, badge, desc, is_active in creds:
        colors = {"green": GREEN_BRIGHT, "amber": AMBER_WARN, "red": RED_ALERT}
        bg = GREEN_FAINT if is_active else "transparent"
        border = colors[status] if is_active else GREEN_DIM
        color = colors[status]

        st.markdown(
            f"<div style='border: 1px solid {border}; padding: 8px 12px; "
            f"margin: 4px 0; background: {bg}; font-family: \"Share Tech Mono\", monospace;'>"
            f"<span style='color: {color};'>"
            f"{'[*]' if is_active else '[ ]'} {name} "
            f"</span>"
            f"<span style='color: {color}; border: 1px solid {color}; "
            f"padding: 1px 6px; font-size: 0.75em;'>{badge}</span>"
            f"<br><span style='color: {GREEN_DIM}; font-size: 0.85em;'>{desc}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    if credential_type == "client_secret":
        st.markdown(
            f"<div style='border: 1px solid {RED_ALERT}; padding: 6px 12px; "
            f"background: rgba(255,51,51,0.05); color: {RED_ALERT}; "
            f"font-family: \"Share Tech Mono\", monospace; font-size: 0.85em;'>"
            "\u26a0 Client secrets are for LOCAL DEVELOPMENT ONLY.<br>"
            "Use Managed Identity or Certificates in production.</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        f"<p style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        f"Active credential: <span style='color: {GREEN_BRIGHT};'>{credential_hint}</span></p>",
        unsafe_allow_html=True,
    )


def render_token_step(
    step_number: int,
    title: str,
    description: str,
    request: Optional[TokenRequest],
    response: Optional[TokenResponse],
    claims: Optional[JWTClaims],
    is_active: bool,
    is_completed: bool,
    is_locked: bool,
    on_transmit_key: str,
    claims_annotations: Optional[dict] = None,
) -> bool:
    """Render a single token generation step. Returns True if TRANSMIT was clicked."""
    transmitted = False

    # Status indicator
    if is_completed:
        status_icon = f"<span style='color: {GREEN_BRIGHT};'>\u2713</span>"
    elif is_active:
        status_icon = f"<span style='color: {GREEN_BRIGHT};'>\u25b6</span>"
    elif is_locked:
        status_icon = f"<span style='color: {GREEN_DIM};'>\u25cb</span>"
    else:
        status_icon = f"<span style='color: {GREEN_DIM};'>\u25cb</span>"

    header_html = (
        f"<span style='font-family: \"Share Tech Mono\", monospace; color: "
        f"{GREEN_BRIGHT if (is_active or is_completed) else GREEN_DIM};'>"
        f"{status_icon} STEP {step_number}: {title}</span>"
    )
    st.markdown(header_html, unsafe_allow_html=True)

    if is_locked:
        st.markdown(
            f"<span style='color: {GREEN_DIM}; font-size: 0.85em; "
            f"font-family: \"Share Tech Mono\", monospace;'>"
            f"  \u2514 {description}</span>",
            unsafe_allow_html=True,
        )
        return False

    with st.expander(f"STEP {step_number} DETAILS", expanded=is_active):
        st.markdown(
            f"<p style='color: {GREEN_DIM}; font-size: 0.85em;'>{description}</p>",
            unsafe_allow_html=True,
        )

        if request:
            _render_request(request)

        if is_active and not is_completed:
            transmitted = st.button(
                f"\u25b6 TRANSMIT TOKEN REQUEST",
                key=on_transmit_key,
            )

        if response and claims:
            _render_response(response, claims, claims_annotations)

    return transmitted


def _render_request(request: TokenRequest) -> None:
    """Render the HTTP request."""
    params = request.to_form_params()
    lines = [f"POST {request.endpoint}", "Content-Type: application/x-www-form-urlencoded", ""]
    for k, v in params.items():
        display_v = v
        if len(str(v)) > 60:
            display_v = f"{str(v)[:50]}..."
        lines.append(f"{k}={display_v}")

    st.code("\n".join(lines), language="http")


def _render_response(
    response: TokenResponse,
    claims: JWTClaims,
    annotations: Optional[dict] = None,
) -> None:
    """Render token response and decoded claims."""
    # Token bar - show 3 segments
    parts = response.access_token.split(".")
    if len(parts) == 3:
        st.markdown(
            f"<div style='font-family: \"Share Tech Mono\", monospace; "
            f"font-size: 0.75em; padding: 8px; border: 1px solid {GREEN_DIM}; "
            f"background: {BG_SECONDARY}; overflow-x: auto; word-break: break-all;'>"
            f"<span style='color: #FF6666;'>{parts[0]}</span>."
            f"<span style='color: #66FF66;'>{parts[1][:60]}...</span>."
            f"<span style='color: #6666FF;'>{parts[2]}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # Decoded claims
    st.markdown(
        f"<p style='color: {GREEN_DIM}; font-size: 0.85em; margin-top: 8px;'>"
        "DECODED CLAIMS:</p>",
        unsafe_allow_html=True,
    )
    st.json(claims.to_dict())

    # Annotations
    if annotations:
        st.markdown(
            f"<p style='color: {GREEN_DIM}; font-size: 0.85em; margin-top: 8px;'>"
            "CLAIM ANNOTATIONS:</p>",
            unsafe_allow_html=True,
        )
        for claim_key, explanation in annotations.items():
            st.markdown(
                f"<span style='color: {GREEN_BRIGHT}; font-family: \"Share Tech Mono\", monospace; "
                f"font-size: 0.85em;'>"
                f"  {claim_key}: <span style='color: {GREEN_DIM};'>{explanation}</span>"
                f"</span>",
                unsafe_allow_html=True,
            )
