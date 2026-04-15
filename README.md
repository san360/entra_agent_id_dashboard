# Entra Agent ID Blueprint Dashboard

An educational, developer-focused dashboard that visualizes the **Microsoft Entra Agent ID Blueprint** lifecycle. Built with Python and Streamlit.

> **DISCLAIMER**: This is a simulation tool for learning purposes only. No real Azure credentials, connections, or tokens are used. All identities, permissions, and JWTs are simulated.

## What It Teaches

This dashboard demonstrates how Microsoft Entra Agent ID works:

- **Agent Identity Blueprints** — Templates that define agent identity types, hold credentials, and manage inheritable permissions
- **Blueprint Principals** — Service principals created when a blueprint is added to a tenant
- **Agent Identities** — Runtime identities for AI agents, created from blueprints
- **Agent Users** — Optional user accounts paired 1:1 with agent identities

## Features

| Page | What It Does |
|------|-------------|
| **Blueprint Visualizer** | Hierarchical tree view showing Blueprint → Principal → Identity → User inheritance |
| **Permission Manager** | Simulate inheritable (blueprint-level) and direct (agent-level) permission assignment |
| **Token Simulator** | Step-by-step visualization of the T1 → T2 → T3 token generation chain |
| **Reference Docs** | PowerShell, C#, and Graph API code snippets from official Microsoft documentation |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the dashboard
streamlit run app.py
```

Navigate to `http://localhost:8501` in your browser.

## Architecture

```
models/          Pure dataclasses (Blueprint, AgentIdentity, Permission, Token)
services/        Business logic (CRUD, permission resolution, token simulation)
ui/components/   Reusable UI elements (tree view, permission panel, token flow)
ui/pages/        Page-level composition (one module per dashboard page)
config/          Theme and CSS configuration
data/            Sample data initialization
```

**SOLID design**: Models have no dependencies. Services depend on a `dict` store (not Streamlit). UI components receive data and render — they never call services directly. Pages orchestrate by calling services then passing data to components.

## Token Simulation Flow

The dashboard simulates the official Entra Agent ID autonomous authentication flow:

1. **Credential Configuration** — Select between Managed Identity (recommended), Certificate, or Client Secret (dev only)
2. **T1 — Blueprint Token** — `client_credentials` grant with `fmi_path` targeting the agent identity
3. **T2 — Agent Identity Token** — Exchange T1 for a resource-scoped token with effective permissions
4. **T3 — Agent User Token** — (Optional) Exchange for a delegated user token via `user_fic` grant

All simulated JWTs contain `SIMULATED_NOT_REAL` in the signature and are structurally valid but clearly fake.

## Security Notes

- No real secrets or API keys are used anywhere in this application
- All credential values are clearly marked as `SIMULATED-*`
- The credential selector always shows best-practice rankings
- JWT signatures include `SIMULATED_NOT_REAL` to prevent accidental use
- No `st.text_input(type="password")` fields exist in the application

## Tech Stack

- **Python 3.10+**
- **Streamlit** — Interactive web framework
- **No external Azure dependencies** — Everything is simulated

## Aesthetic

Retro-Tech Terminal with:
- Green (#00FF41) on Black (#0D0208) color scheme
- Share Tech Mono monospaced font
- CRT scanline overlay effect
- Box-drawing character UI elements
- Blinking cursor animations
