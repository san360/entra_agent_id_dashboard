# Entra Agent ID Blueprint Dashboard

A developer-focused dashboard for managing the **Microsoft Entra Agent ID Blueprint** lifecycle. Built with Python and Streamlit, backed by the Microsoft Graph API (beta).

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

# Configure environment (copy and edit)
cp .env.example .env
# Set AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET

# Run the dashboard
streamlit run app.py
```

Navigate to `http://localhost:8501` in your browser.

## Prerequisites

### Required Microsoft Graph API Permissions

The app registration used by this dashboard needs the following **Application** permissions with **admin consent granted**:

| Permission | Type | Purpose |
|------------|------|---------|
| `AgentIdentityBlueprint.Create` | Application | Create new agent identity blueprints |
| `AgentIdentityBlueprint.Read.All` | Application | List and read blueprints |
| `AgentIdentityBlueprint.DeleteRestore.All` | Application | Delete blueprints |
| `AgentIdentityBlueprintPrincipal.Create` | Application | Auto-provision service principals for blueprints |
| `AgentIdentityBlueprintPrincipal.Read.All` | Application | List and read blueprint principals |
| `AgentIdentityBlueprintPrincipal.DeleteRestore.All` | Application | Delete blueprint principals |
| `AgentIdentity.Read.All` | Application | List and read agent identities |
| `AgentIdentity.DeleteRestore.All` | Application | Delete agent identities |
| `Application.ReadWrite.All` | Application | Manage application registrations |
| `AppRoleAssignment.ReadWrite.All` | Application | Manage app role assignments |
| `DelegatedPermissionGrant.ReadWrite.All` | Application | Manage delegated permission grants |
| `ServicePrincipalEndpoint.ReadWrite.All` | Application | Manage service principal endpoints |
| `User.ReadWrite.All` | Application | Read user info for blueprint sponsors |

> **Known Issue (Microsoft):** If your app registration has `Directory.AccessAsUser.All` or `Directory.ReadWrite.All` granted, Agent ID create/update/delete operations will fail with `403 Forbidden`. Remove those permissions if present. See [Microsoft docs](https://learn.microsoft.com/en-us/graph/api/agentidentityblueprint-post).

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_TENANT_ID` | Yes | Your Microsoft Entra tenant ID |
| `AZURE_CLIENT_ID` | Yes | App registration client ID |
| `AZURE_CLIENT_SECRET` | Yes | App registration client secret |
| `AZURE_SUBSCRIPTION_ID` | No | Default Azure subscription ID (pre-fills Foundry resource creation form) |
| `BLUEPRINT_CLIENT_SECRET` | No | Credential for blueprint token simulation |
| `BLUEPRINT_CERTIFICATE_PATH` | No | Certificate path for blueprint token simulation |

### Azure RBAC Permissions (for Foundry Resource Management)

The service principal needs Azure RBAC roles to create and manage Foundry resources (AI Services accounts) and projects via the ARM API:

| Action | Minimum Role | Scope | Purpose |
|--------|-------------|-------|---------|
| Create resource groups | **Contributor** | Subscription | Auto-create resource groups for new Foundry resources |
| Create AI Services accounts | **Cognitive Services Contributor** | Subscription or Resource Group | Provision Azure AI Services (Foundry) accounts |
| Create Foundry projects | **Cognitive Services Contributor** | Resource Group or Account | Create projects under an AI Services account |
| Discover existing resources | **Reader** | Subscription | List subscriptions, accounts, and projects |

**Quick setup (broad):**
```bash
az role assignment create \
  --assignee <APP_CLIENT_ID> \
  --role "Contributor" \
  --scope /subscriptions/<SUBSCRIPTION_ID>
```

**Least-privilege setup:**
```bash
# 1. Create the resource group manually
az group create --name rg-contoso-ai --location swedencentral

# 2. Grant Cognitive Services Contributor on the resource group only
az role assignment create \
  --assignee <APP_CLIENT_ID> \
  --role "Cognitive Services Contributor" \
  --scope /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-contoso-ai
```

> **Note:** If you only need to discover existing resources (no creation), the **Reader** role on the subscription is sufficient.

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

- Store credentials in `.env` (gitignored) — never commit secrets
- Use `DefaultAzureCredential` when `AZURE_CLIENT_ID` is not set (e.g., Managed Identity in production)
- The SDK singleton pattern is used for `CosmosClient` / `GraphClient` to avoid repeated credential creation
- Token simulation JWTs contain `SIMULATED_NOT_REAL` in the signature and are structurally valid but clearly fake
- The credential selector always shows best-practice rankings

## Tech Stack

- **Python 3.10+**
- **Streamlit** — Interactive web framework
- **azure-identity** — Authentication via `DefaultAzureCredential` or `ClientSecretCredential`
- **httpx** — HTTP client for Microsoft Graph API calls

## Aesthetic

Retro-Tech Terminal with:
- Green (#00FF41) on Black (#0D0208) color scheme
- Share Tech Mono monospaced font
- CRT scanline overlay effect
- Box-drawing character UI elements
- Blinking cursor animations
