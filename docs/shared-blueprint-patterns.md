# Shared Blueprint Patterns for Entra Agent Identities

## Deep-Dive: One Blueprint, Many Agents

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [The Four-Object Model Recap](#the-four-object-model-recap)
3. [Why Share a Blueprint?](#why-share-a-blueprint)
4. [How the One-to-Many Relationship Works](#how-the-one-to-many-relationship-works)
5. [What Gets Inherited vs. What Doesn't](#what-gets-inherited-vs-what-doesnt)
6. [The Token Exchange Flow (T1 → T2)](#the-token-exchange-flow-t1--t2)
7. [Shared Blueprint Architecture Patterns](#shared-blueprint-architecture-patterns)
   - [Pattern 1: Single Blueprint per Agent Platform](#pattern-1-single-blueprint-per-agent-platform)
   - [Pattern 2: Blueprint per Business Domain](#pattern-2-blueprint-per-business-domain)
   - [Pattern 3: Blueprint per Environment (Dev/Test/Prod)](#pattern-3-blueprint-per-environment-devtestprod)
   - [Pattern 4: Blueprint per Subscription/Foundry Project](#pattern-4-blueprint-per-subscriptionfoundry-project)
   - [Pattern 5: Blueprint per Tenant (Multi-Tenant)](#pattern-5-blueprint-per-tenant-multi-tenant)
8. [Environment Differentiation Strategies](#environment-differentiation-strategies)
   - [Strategy A: Separate Tenants per Environment](#strategy-a-separate-tenants-per-environment)
   - [Strategy B: Separate Blueprints in Same Tenant](#strategy-b-separate-blueprints-in-same-tenant)
   - [Strategy C: Same Blueprint, Different Agent Identities per Environment](#strategy-c-same-blueprint-different-agent-identities-per-environment)
   - [Strategy D: Foundry Project Scoping](#strategy-d-foundry-project-scoping)
9. [Subscription and Tenant Scoping](#subscription-and-tenant-scoping)
10. [Security Boundaries and Trade-offs](#security-boundaries-and-trade-offs)
11. [Naming Conventions](#naming-conventions)
12. [Implementation Examples](#implementation-examples)
13. [Decision Matrix](#decision-matrix)
14. [How Azure AI Foundry Associates Blueprints with Projects](#how-azure-ai-foundry-associates-blueprints-with-projects)
    - [The Three Blueprint Types Foundry Creates](#the-three-blueprint-types-foundry-creates)
    - [How the Three Layers Relate](#how-the-three-layers-relate)
    - [How to Identify the Blueprint Type](#how-to-identify-the-blueprint-type)
    - [Why Foundry Creates Per-Agent Blueprints](#why-foundry-creates-per-agent-blueprints-not-a-shared-one)
    - [Approaches: Assigning a Shared Blueprint to Foundry Project Agents](#approaches-assigning-a-shared-blueprint-to-foundry-project-agents)
    - [Mapping Foundry Blueprints Across Environments](#mapping-foundry-blueprints-across-environments)
    - [When to Use Shared vs. Foundry-Native Blueprints](#when-to-use-shared-blueprints-vs-foundry-native-per-agent-blueprints)
    - [Tracing the Full Foundry → Blueprint → Agent Chain](#tracing-the-full-foundry--blueprint--agent-chain-in-the-dashboard)
    - [Blueprint Scoping: Foundry Resource vs. Project Level](#blueprint-scoping-foundry-resource-vs-project-level)
    - [Foundry Blueprint Limits](#foundry-blueprint-limits)
15. [References](#references)

---

## Executive Summary

Microsoft Entra Agent ID introduces a **hierarchical identity model** where an **Agent Identity Blueprint** acts as a parent template for **one or more Agent Identities**. This is fundamentally a **one-to-many (1:N) relationship** — a single blueprint can create and govern many agent identities.

The key insight: **you don't need one blueprint per agent**. A shared blueprint centralizes:
- **Credentials** (FIC, certificate, or client secret)
- **Protocol properties** (Identifier URIs, OAuth2 scopes, grant types)
- **Delegated permission inheritance** (via `inheritablePermissions` + `OAuth2PermissionGrant`)
- **Governance** (owner/sponsor accountability, Conditional Access policies)

Each agent identity created from the shared blueprint gets its own:
- **Unique identity** (separate `appId`, separate service principal)
- **Direct permissions** (application permissions, Azure RBAC roles)
- **Audit trail** (distinct sign-in logs and audit entries)

This document explores the patterns for sharing blueprints across agents, subscriptions, tenants, and environments.

---

## The Four-Object Model Recap

```
┌─────────────────────────────────────────────────────────────────┐
│                    ENTRA AGENT ID PLATFORM                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────────────────┐                                      │
│  │  Agent Identity        │  ◄── Application object (template)  │
│  │  Blueprint             │      Holds credentials              │
│  │  (1 per agent type)    │      Defines protocol config        │
│  └──────────┬────────────┘      Sets inheritable permissions    │
│             │                                                   │
│             │ 1:1                                                │
│             ▼                                                   │
│  ┌───────────────────────┐                                      │
│  │  Blueprint Principal   │  ◄── Service Principal of blueprint │
│  │                        │      Makes blueprint visible in     │
│  │                        │      tenant, enables token ops      │
│  └──────────┬────────────┘      Holds OAuth2PermissionGrants   │
│             │                                                   │
│             │ 1:N  (THIS IS THE KEY RELATIONSHIP)               │
│             ▼                                                   │
│  ┌───────────────────────┐                                      │
│  │  Agent Identity        │  ◄── Service Principal (agent type) │
│  │  (per agent instance)  │      Linked via blueprintId         │
│  │                        │      Inherits protocol props        │
│  └──────────┬────────────┘      Can have direct permissions    │
│             │                                                   │
│             │ 1:1 (optional)                                    │
│             ▼                                                   │
│  ┌───────────────────────┐                                      │
│  │  Agent User            │  ◄── User object for human-like     │
│  │  (optional)            │      capabilities (mailbox, Teams)  │
│  └───────────────────────┘                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Key**: The `1:N` relationship between Blueprint Principal and Agent Identities is the foundation of the shared blueprint pattern.

---

## Why Share a Blueprint?

### The Problem: One Blueprint per Agent

If every agent gets its own blueprint, you end up with:

| Issue | Impact |
|-------|--------|
| Credential sprawl | Each blueprint has its own FIC/cert/secret to rotate |
| Permission drift | Each blueprint's `inheritablePermissions` must be maintained separately |
| Policy duplication | Conditional Access policies must target each blueprint individually |
| Governance overhead | Each blueprint needs its own owner, sponsor, and lifecycle management |
| No consistency | Agents doing similar work may end up with different permission sets |

### The Solution: Shared Blueprint

A shared blueprint gives you:

| Benefit | How |
|---------|-----|
| **Single credential to manage** | One FIC/cert/secret for all agent identities under this blueprint |
| **Centralized permission baseline** | `inheritablePermissions` applies to all child identities automatically |
| **Unified Conditional Access** | One policy targeting the blueprint covers all its agent identities |
| **Consistent governance** | One owner, one sponsor, one lifecycle for the "platform" |
| **Individual auditability** | Each agent identity still appears separately in sign-in logs |
| **Per-agent permissions** | Direct permission assignment allows agent-specific access |

---

## How the One-to-Many Relationship Works

### Creation Flow

```
Blueprint (appId: bp-001)
    │
    ├── POST /serviceprincipals/microsoft.graph.agentIdentity
    │   body: { displayName: "HR Agent - US", agentIdentityBlueprintId: "bp-001" }
    │   → Creates Agent Identity (appId: ai-001)
    │
    ├── POST /serviceprincipals/microsoft.graph.agentIdentity
    │   body: { displayName: "HR Agent - UK", agentIdentityBlueprintId: "bp-001" }
    │   → Creates Agent Identity (appId: ai-002)
    │
    └── POST /serviceprincipals/microsoft.graph.agentIdentity
        body: { displayName: "HR Agent - EU", agentIdentityBlueprintId: "bp-001" }
        → Creates Agent Identity (appId: ai-003)
```

All three agent identities share:
- The blueprint's `identifierUri` (e.g., `api://bp-001`)
- The blueprint's `oauth2PermissionScopes` (e.g., `access_agent`)
- The blueprint's `supportedGrantTypes` (e.g., `client_credentials`, `jwt-bearer`, `refresh_token`)
- The blueprint's `inheritablePermissions` (e.g., `User.Read`, `Mail.Read`)

Each agent identity has:
- Its own unique `appId` and service principal `id`
- Its own direct permission assignments
- Its own audit trail
- Its own sponsor

### The `agentIdentityBlueprintId` Link

Every agent identity carries a property `agentIdentityBlueprintId` that points back to the parent blueprint's `appId`. This link is:
- **Set at creation time** and cannot be changed
- **Used at token issuance** to resolve protocol properties and inheritable permissions
- **Visible in audit logs** via the `xms_par_app_azp` claim in issued tokens

---

## What Gets Inherited vs. What Doesn't

### Always Inherited (Protocol Properties)

These flow automatically from blueprint to every agent identity:

| Property | Description | Example |
|----------|-------------|---------|
| **Identifier URI** | Globally unique API surface name | `api://{blueprint-appId}` |
| **OAuth2 Permission Scopes** | Permissions the agent exposes to callers | `access_agent` |
| **Supported Grant Types** | Auth flows the agent supports | `client_credentials`, `jwt-bearer`, `refresh_token` |
| **Credentials** | Auth credentials (FIC, cert, secret) | The blueprint authenticates, then impersonates |

### Conditionally Inherited (Delegated Permissions)

These require **two configurations on the blueprint** to flow down:

1. **`inheritablePermissions`** on the blueprint application object — defines which scopes from which APIs are *eligible* to flow down
2. **`OAuth2PermissionGrant`** on the blueprint service principal — provides admin consent for those scopes

```
Blueprint Application                Blueprint Service Principal
┌───────────────────────┐            ┌────────────────────────────┐
│ inheritablePermissions│            │ OAuth2PermissionGrant       │
│ ├─ resourceAppId:     │            │ ├─ clientId: {bp-sp-id}    │
│ │   00000003-...      │            │ ├─ consentType: AllPrincipals
│ │   (MS Graph)        │            │ ├─ resourceId: {graph-sp}  │
│ └─ inheritableScopes: │            │ └─ scope: "Mail.Read       │
│     - User.Read       │     +      │          Calendars.Read    │
│     - Mail.Read       │            │          User.Read"        │
│     - Calendars.Read  │            │                            │
└───────────────────────┘            └────────────────────────────┘
            │                                     │
            └──────────┬──────────────────────────┘
                       │
                       ▼
              At token issuance time, Entra
              dynamically merges these scopes
              into the issued token for any
              child agent identity
```

> **Important**: The inheritance is **fully automatic** once both are configured. There is no `InheritDelegatedPermissions` toggle on the agent identity itself. The term is used conceptually in documentation but is not a property you can set.

> **Important**: Agent identities do NOT store inherited permissions. They are applied at runtime during token issuance. If you look at an agent identity's permissions in the portal, you'll see nothing — this is by design.

### NOT Inherited (Direct-Only)

| Capability | Description |
|------------|-------------|
| **Application permissions** (`roles`) | Must be assigned directly to each agent identity |
| **Azure RBAC roles** | Must be assigned directly to each agent identity |
| **Microsoft Entra directory roles** | Must be assigned directly to each agent identity |
| **Owner & Sponsor** | Set separately per agent identity |

> **Note**: Agent Identity Blueprints themselves **cannot** be assigned Azure RBAC roles. Only agent identities can.

---

## The Token Exchange Flow (T1 → T2)

Understanding the token flow is essential because it shows how the shared blueprint authenticates on behalf of individual agent identities:

```
  ┌──────────────┐
  │   Blueprint   │ owns credentials (FIC/cert/secret)
  └──────┬───────┘
         │
   Step 1│  POST /oauth2/v2.0/token
         │  client_id    = {blueprint-appId}
         │  client_secret = {blueprint-secret}
         │  scope         = api://AzureADTokenExchange/.default
         │  grant_type    = client_credentials
         │  fmi_path      = {agent-identity-appId}  ◄── which agent to impersonate
         │
         ▼
  ┌──────────────┐
  │  Token T1     │ Exchange token
  │  aud: agent   │ Proves blueprint can speak for this agent
  │  sub: bp-sp   │
  └──────┬───────┘
         │
   Step 2│  POST /oauth2/v2.0/token
         │  client_id              = {agent-identity-appId}
         │  scope                  = https://graph.microsoft.com/.default
         │  grant_type             = client_credentials
         │  client_assertion_type  = urn:ietf:params:oauth:client-assertion-type:jwt-bearer
         │  client_assertion       = {T1}
         │
         ▼
  ┌──────────────┐
  │  Token T2     │ Resource token (e.g., for Microsoft Graph)
  │  aud: graph   │ Contains direct roles + inherited scopes
  │  appid: agent │ Identifies the agent identity as the caller
  │  xms_par_azp  │ Shows the blueprint as the parent
  └──────────────┘
```

**Key insight for shared blueprints**: The `fmi_path` parameter in Step 1 determines which agent identity the blueprint impersonates. The same blueprint credential is used for ALL agent identities — just with different `fmi_path` values.

---

## Shared Blueprint Architecture Patterns

### Pattern 1: Single Blueprint per Agent Platform

**When**: You have a single agent platform (e.g., Copilot Studio, AI Foundry) and all agents share the same baseline capabilities.

```
┌─────────────────────────────────┐
│  "Enterprise AI Platform"       │
│  Blueprint                      │
│  ├─ credentials: FIC (MSI)      │
│  ├─ inheritablePermissions:     │
│  │   User.Read, Mail.Read       │
│  └─ scope: access_agent         │
├─────────────────────────────────┤
│                                 │
│  ├── HR Agent Identity          │
│  │   └─ direct: User.Read.All  │
│  │                              │
│  ├── Finance Agent Identity     │
│  │   └─ direct: Sites.Read.All │
│  │                              │
│  ├── IT Support Agent Identity  │
│  │   └─ direct: Device.Read.All│
│  │                              │
│  └── Sales Agent Identity       │
│      └─ direct: Contacts.Read  │
└─────────────────────────────────┘
```

**Pros**: Simplest to manage, one credential, one policy set.
**Cons**: Blast radius — if the blueprint's credentials are compromised, all agents are affected. Blueprint count is a security boundary decision.

### Pattern 2: Blueprint per Business Domain

**When**: Different business domains have fundamentally different permission baselines.

```
┌────────────────────┐    ┌────────────────────┐    ┌──────────────────────┐
│  "HR Platform"     │    │ "Finance Platform"  │    │ "Customer Service"   │
│  Blueprint         │    │ Blueprint           │    │ Blueprint            │
│  inheritable:      │    │ inheritable:        │    │ inheritable:         │
│  - User.Read       │    │ - Sites.Read.All    │    │ - User.Read          │
│  - Mail.Read       │    │ - Files.Read        │    │ - Mail.Send          │
│  - Calendars.Read  │    │                     │    │ - Calendars.Read     │
├────────────────────┤    ├────────────────────-┤    ├──────────────────────┤
│ ├─ HR Agent US     │    │ ├─ Budget Analyzer  │    │ ├─ Chat Support Bot  │
│ ├─ HR Agent UK     │    │ ├─ Invoice Agent    │    │ ├─ Email Responder   │
│ └─ HR Agent EU     │    │ └─ Expense Agent    │    │ └─ Scheduling Agent  │
└────────────────────┘    └────────────────────-┘    └──────────────────────┘
```

**Pros**: Least-privilege per domain, clear ownership boundaries.
**Cons**: More blueprints to manage (more credentials, more policies).

### Pattern 3: Blueprint per Environment (Dev/Test/Prod)

**When**: You need strict environment isolation within the same tenant.

```
Same Tenant (contoso.onmicrosoft.com)
│
├── "HR Platform - DEV" Blueprint
│   ├─ credential: client_secret (dev-only)
│   ├─ inheritablePermissions: User.Read
│   ├─ Conditional Access: Allow from dev network only
│   └── Agent Identities:
│       ├─ HR Agent Dev 1
│       └─ HR Agent Dev 2
│
├── "HR Platform - TEST" Blueprint
│   ├─ credential: certificate (test)
│   ├─ inheritablePermissions: User.Read, Mail.Read
│   ├─ Conditional Access: Allow from test network
│   └── Agent Identities:
│       ├─ HR Agent Test 1
│       └─ HR Agent Test 2
│
└── "HR Platform - PROD" Blueprint
    ├─ credential: FIC/Managed Identity (most secure)
    ├─ inheritablePermissions: User.Read, Mail.Read, Calendars.Read
    ├─ Conditional Access: Strict MFA + compliant device
    └── Agent Identities:
        ├─ HR Agent Prod US
        ├─ HR Agent Prod UK
        └─ HR Agent Prod EU
```

**Why this works**:
- **Different credential types** per environment (secret for dev is acceptable; prod uses FIC)
- **Different permission scopes** (dev gets minimal; prod gets full)
- **Different Conditional Access** policies per blueprint
- **Independent blast radius** (dev compromise doesn't affect prod)

### Pattern 4: Blueprint per Subscription/Foundry Project

**When**: Each Azure subscription or AI Foundry project represents a distinct workload boundary.

```
Tenant: contoso.onmicrosoft.com
│
├── Subscription A (Dev/Test)
│   └── AI Foundry Project "hr-agents-dev"
│       └── Blueprint: "HR Agents Dev"
│           ├─ serviceManagementReference: links to Foundry project
│           ├─ Owner SP alternativeNames: /subscriptions/sub-A/...
│           └── Agent Identities:
│               ├─ HR Dev Agent 1
│               └─ HR Dev Agent 2
│
├── Subscription B (Production)
│   └── AI Foundry Project "hr-agents-prod"
│       └── Blueprint: "HR Agents Prod"
│           ├─ serviceManagementReference: links to Foundry project
│           ├─ Owner SP alternativeNames: /subscriptions/sub-B/...
│           └── Agent Identities:
│               ├─ HR Prod Agent US
│               ├─ HR Prod Agent UK
│               └─ HR Prod Agent EU
│
└── Subscription C (Sandbox)
    └── AI Foundry Project "experimental"
        └── Blueprint: "Sandbox Agents"
            └── Agent Identities:
                └─ Experimental Agent
```

**How the Foundry link works**: The `serviceManagementReference` property on the blueprint application and the `alternativeNames` on the owner service principal contain ARM resource paths:

```
/subscriptions/{sub-id}/resourcegroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{account}/projects/{project}
```

This creates a traceable link from blueprint → Foundry project → Azure subscription.

### Pattern 5: Blueprint per Tenant (Multi-Tenant)

**When**: Your organization has separate Entra tenants for different business units or environments.

```
┌────────────────────────────┐    ┌────────────────────────────┐
│ Tenant: dev.contoso.com     │    │ Tenant: contoso.com         │
│                             │    │                             │
│ Blueprint: "HR Platform"    │    │ Blueprint: "HR Platform"    │
│ ├─ signInAudience:          │    │ ├─ signInAudience:          │
│ │   AzureADMyOrg            │    │ │   AzureADMyOrg            │
│ ├─ credential: secret       │    │ ├─ credential: FIC          │
│ ├─ inheritablePerms: basic  │    │ ├─ inheritablePerms: full   │
│ └─ Agent Identities:        │    │ └─ Agent Identities:        │
│    ├─ Dev Agent 1            │    │    ├─ Prod Agent US         │
│    └─ Dev Agent 2            │    │    ├─ Prod Agent UK         │
│                             │    │    └─ Prod Agent EU         │
└────────────────────────────┘    └────────────────────────────┘
```

**Important**: Blueprints with `signInAudience: AzureADMyOrg` (the default for agent blueprints) are single-tenant. Each tenant gets its own blueprint. If you need cross-tenant agent access, the calling agent's tenant must create an `OAuth2PermissionGrant` against the target blueprint's service principal.

---

## Environment Differentiation Strategies

### Strategy A: Separate Tenants per Environment

```
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ dev.contoso.com  │   │ test.contoso.com │   │ contoso.com      │
│                  │   │                  │   │ (production)     │
│ Blueprint-Dev    │   │ Blueprint-Test   │   │ Blueprint-Prod   │
│ └─ Agents (dev)  │   │ └─ Agents (test) │   │ └─ Agents (prod) │
└──────────────────┘   └──────────────────┘   └──────────────────┘
```

| Aspect | Detail |
|--------|--------|
| **Isolation** | Complete — no risk of cross-environment bleed |
| **Cost** | Higher — separate Entra tenants, separate licenses |
| **Complexity** | Higher — separate policies, separate admin |
| **When to use** | Regulated industries, financial services, healthcare |
| **Blueprint scoping** | Each tenant has its own independent blueprint |

### Strategy B: Separate Blueprints in Same Tenant

```
contoso.onmicrosoft.com
├── Blueprint: "MyApp-DEV"    → Dev Agent Identities
├── Blueprint: "MyApp-TEST"   → Test Agent Identities
└── Blueprint: "MyApp-PROD"   → Prod Agent Identities
```

| Aspect | Detail |
|--------|--------|
| **Isolation** | Good — different credentials, policies, permissions per environment |
| **Cost** | Lower — single tenant |
| **Complexity** | Moderate — naming conventions and Conditional Access per blueprint |
| **When to use** | Most organizations, standard enterprise setup |
| **Key differentiators** | |
| - Credentials | DEV: secret, TEST: certificate, PROD: FIC/managed identity |
| - Permissions | DEV: minimal, TEST: expanded, PROD: full production scopes |
| - Conditional Access | DEV: lenient, TEST: moderate, PROD: strict |
| - Sponsors | DEV: dev team lead, TEST: QA lead, PROD: business owner |

### Strategy C: Same Blueprint, Different Agent Identities per Environment

```
contoso.onmicrosoft.com
└── Blueprint: "MyApp Platform"
    ├── Agent Identity: "MyApp-DEV-Agent-1"    (dev)
    ├── Agent Identity: "MyApp-DEV-Agent-2"    (dev)
    ├── Agent Identity: "MyApp-TEST-Agent-1"   (test)
    ├── Agent Identity: "MyApp-TEST-Agent-2"   (test)
    ├── Agent Identity: "MyApp-PROD-Agent-US"  (prod)
    ├── Agent Identity: "MyApp-PROD-Agent-UK"  (prod)
    └── Agent Identity: "MyApp-PROD-Agent-EU"  (prod)
```

| Aspect | Detail |
|--------|--------|
| **Isolation** | Weak — all share same credentials and inheritable permissions |
| **Cost** | Lowest — single blueprint |
| **Complexity** | Low — differentiate via naming and direct permissions only |
| **When to use** | Non-sensitive workloads, rapid prototyping |
| **Risk** | Credential compromise affects ALL environments |
| **Differentiation** | Only via direct permission assignments and naming |

> **Not recommended for production** unless all environments genuinely need the same security posture.

### Strategy D: Foundry Project Scoping

```
contoso.onmicrosoft.com
│
├── Foundry Project: "myapp-dev" (Subscription: sub-dev)
│   └── Blueprint: auto-created by Foundry
│       └── Agent Identities for dev
│
├── Foundry Project: "myapp-test" (Subscription: sub-test)
│   └── Blueprint: auto-created by Foundry
│       └── Agent Identities for test
│
└── Foundry Project: "myapp-prod" (Subscription: sub-prod)
    └── Blueprint: auto-created by Foundry
        └── Agent Identities for prod
```

| Aspect | Detail |
|--------|--------|
| **Isolation** | Strong — tied to Azure subscription boundaries |
| **Cost** | Moderate — separate Foundry projects |
| **Complexity** | Low — Foundry manages blueprint lifecycle |
| **When to use** | AI Foundry-based agents, Azure-native workloads |
| **Traceability** | Full ARM resource path → Foundry project → blueprint → agent |

The link is traced via:
- Blueprint's `serviceManagementReference` property
- Owner service principal's `alternativeNames` containing the ARM resource path
- Pattern: `/subscriptions/{sub}/resourcegroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{account}/projects/{project}`

---

## Subscription and Tenant Scoping

### Can a Blueprint Be "Assigned" to a Subscription?

**Not directly.** Blueprints are Entra ID objects (application registrations), not Azure Resource Manager resources. They live in the tenant directory, not in a subscription.

However, the link to subscriptions happens through:

1. **`serviceManagementReference`** — A string field on the application object that can contain a reference to an Azure resource
2. **Owner Service Principal `alternativeNames`** — Contains the full ARM resource path when created by AI Foundry
3. **Conditional Access policies** — Can restrict agent access based on network location (which maps to subscription-level VNets)
4. **Azure RBAC on agent identities** — Each agent identity can be scoped to specific subscriptions/resource groups for RBAC role assignments

### Can a Blueprint Be "Assigned" to a Tenant?

**Implicitly, yes.** Blueprints are created within a tenant and (with `signInAudience: AzureADMyOrg`) are single-tenant by default. The blueprint IS scoped to the tenant where it's created.

For multi-tenant scenarios (`signInAudience: AzureADMultipleOrgs`), the blueprint's *application* lives in the home tenant, but *blueprint principals* can be created in other tenants — though this pattern is unusual for agent blueprints.

### Mapping: Blueprint → Subscription → Environment

```
┌─────────────────────────────────────────────────────────────────┐
│                         ENTRA TENANT                            │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Blueprint: "HR-Platform-DEV"                             │   │
│  │ serviceManagementReference: → sub-dev / foundry-dev      │   │
│  │ └─ Agent Identities (dev)                                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Blueprint: "HR-Platform-PROD"                            │   │
│  │ serviceManagementReference: → sub-prod / foundry-prod    │   │
│  │ └─ Agent Identities (prod)                               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ──────────────────────────────────────────────────────────────  │
│  Azure Subscriptions (ARM layer)                                │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │
│  │ sub-dev         │  │ sub-test       │  │ sub-prod       │    │
│  │ ├─ RG: agents   │  │ ├─ RG: agents  │  │ ├─ RG: agents  │    │
│  │ │ └─ Foundry    │  │ │ └─ Foundry   │  │ │ └─ Foundry   │    │
│  │ │   Project     │  │ │   Project    │  │ │   Project    │    │
│  │ └─ RBAC:        │  │ └─ RBAC:       │  │ └─ RBAC:       │    │
│  │   dev-agents    │  │   test-agents  │  │   prod-agents  │    │
│  └────────────────┘  └────────────────┘  └────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Security Boundaries and Trade-offs

### The Blast Radius Question

> "A compromise of the blueprint's credentials affects all agent identities under it, which is why blueprint count is a security boundary decision."
> — Microsoft Docs: Agent identities, service principals, and applications

| # Blueprints | Blast Radius | Management Overhead | When to Choose |
|-------------|--------------|-------------------|---------------|
| 1 (all agents) | Maximum — all agents compromised | Minimal | Prototyping, small orgs |
| Per domain | Medium — one domain affected | Moderate | Most enterprises |
| Per environment | Low — only one env affected | Higher | Security-conscious orgs |
| Per agent | Minimal — one agent affected | Maximum | Highly regulated, per-agent audit requirements |

### Credential Type Recommendations by Environment

| Environment | Recommended Credential | Rationale |
|-------------|----------------------|-----------|
| **Development** | Client Secret | Easy rotation, acceptable risk for dev data |
| **Testing** | Certificate | Better security, tests cert-based auth flow |
| **Staging** | Certificate or FIC | Mirrors production |
| **Production** | FIC (Managed Identity) | Most secure, no secret to leak, auto-rotated |

### Conditional Access Differentiation

Even with shared blueprints, Conditional Access policies can differentiate environments:

```
Policy: "Restrict Dev Agents"
├─ Target: Blueprint "MyApp-DEV" service principal
├─ Conditions: Any network
├─ Grant: Allow (lenient for dev)
└─ Session: Sign-in frequency = 1 hour

Policy: "Secure Prod Agents"
├─ Target: Blueprint "MyApp-PROD" service principal
├─ Conditions: Named locations only (prod network)
├─ Grant: Require compliant device + MFA
└─ Session: Sign-in frequency = 15 minutes
```

---

## Naming Conventions

Consistent naming helps identify blueprint-to-environment-to-agent relationships:

### Blueprint Names
```
{OrgPrefix}-{Domain}-{Environment}-Blueprint

Examples:
  CONTOSO-HR-DEV-Blueprint
  CONTOSO-HR-PROD-Blueprint
  CONTOSO-Finance-DEV-Blueprint
  CONTOSO-Finance-PROD-Blueprint
```

### Agent Identity Names
```
{OrgPrefix}-{Domain}-{Environment}-{Function}-Agent[-{Region}]

Examples:
  CONTOSO-HR-DEV-Onboarding-Agent
  CONTOSO-HR-PROD-Onboarding-Agent-US
  CONTOSO-HR-PROD-Onboarding-Agent-UK
  CONTOSO-Finance-PROD-Invoice-Agent
```

### Tags and Descriptions
Use the `description` field on both blueprints and agent identities for environment metadata:

```json
{
  "displayName": "CONTOSO-HR-PROD-Blueprint",
  "description": "Production blueprint for HR domain agents. Subscription: sub-prod-001. Foundry Project: hr-agents-prod. Owner: hr-platform-team@contoso.com"
}
```

---

## Implementation Examples

### PowerShell: Create a Shared Blueprint with Multiple Agent Identities

```powershell
# ============================================================
# Step 1: Create the shared blueprint
# ============================================================
Connect-MgGraph -Scopes "AgentIdentityBlueprint.Create","AgentIdentityBlueprintPrincipal.Create","AgentIdentity.Create.All","DelegatedPermissionGrant.ReadWrite.All","Application.ReadWrite.All"

$sponsorUserId = "<sponsor-user-id>"
$ownerUserId   = "<owner-user-id>"

$blueprintBody = @{
    "@odata.type"       = "Microsoft.Graph.AgentIdentityBlueprint"
    "displayName"       = "CONTOSO-HR-PROD-Blueprint"
    "description"       = "Shared production blueprint for all HR agents"
    "sponsors@odata.bind" = @(
        "https://graph.microsoft.com/v1.0/users/$sponsorUserId"
    )
    "owners@odata.bind" = @(
        "https://graph.microsoft.com/v1.0/users/$ownerUserId"
    )
} | ConvertTo-Json -Depth 5

$blueprint = Invoke-MgGraphRequest -Method POST `
    -Uri "https://graph.microsoft.com/beta/applications/graph.agentIdentityBlueprint" `
    -Body $blueprintBody -ContentType "application/json"

$blueprintAppId = $blueprint.appId
Write-Host "Blueprint AppId: $blueprintAppId"

# ============================================================
# Step 2: Create the blueprint principal
# ============================================================
$principalBody = @{ appId = $blueprintAppId } | ConvertTo-Json
Invoke-MgGraphRequest -Method POST `
    -Uri "https://graph.microsoft.com/beta/serviceprincipals/graph.agentIdentityBlueprintPrincipal" `
    -Headers @{ "OData-Version" = "4.0"; "Content-Type" = "application/json" } `
    -Body $principalBody

# ============================================================
# Step 3: Configure inheritable permissions (shared baseline)
# ============================================================
$graphAppId = "00000003-0000-0000-c000-000000000000"

$inheritBody = @{
    "resourceAppId"     = $graphAppId
    "inheritableScopes" = @{
        "@odata.type" = "microsoft.graph.enumeratedScopes"
        "scopes"      = @("User.Read", "Mail.Read", "Calendars.Read")
    }
} | ConvertTo-Json -Depth 5

Invoke-MgGraphRequest -Method POST `
    -Uri "https://graph.microsoft.com/beta/applications/microsoft.graph.agentIdentityBlueprint/$blueprintAppId/inheritablePermissions" `
    -Headers @{ "OData-Version" = "4.0"; "Content-Type" = "application/json" } `
    -Body $inheritBody

# ============================================================
# Step 4: Grant OAuth2 consent on the blueprint principal
# ============================================================
$bpSP = Invoke-MgGraphRequest -Method GET `
    -Uri "https://graph.microsoft.com/beta/servicePrincipals?`$filter=appId eq '$blueprintAppId'" `
    -Headers @{ "OData-Version" = "4.0" } -OutputType PSObject
$bpSPId = $bpSP.value[0].id

$graphSP = Get-MgServicePrincipal -Filter "appId eq '$graphAppId'"

$grantBody = @{
    clientId    = $bpSPId
    consentType = "AllPrincipals"
    resourceId  = $graphSP.Id
    scope       = "Mail.Read Calendars.Read User.Read"
} | ConvertTo-Json

Invoke-MgGraphRequest -Method POST `
    -Uri "https://graph.microsoft.com/v1.0/oauth2PermissionGrants" `
    -Headers @{ "Content-Type" = "application/json" } `
    -Body $grantBody

# ============================================================
# Step 5: Create MULTIPLE agent identities from the SAME blueprint
# ============================================================
$agents = @(
    @{ Name = "CONTOSO-HR-PROD-Onboarding-Agent-US" },
    @{ Name = "CONTOSO-HR-PROD-Onboarding-Agent-UK" },
    @{ Name = "CONTOSO-HR-PROD-Onboarding-Agent-EU" },
    @{ Name = "CONTOSO-HR-PROD-Recruiting-Agent" },
    @{ Name = "CONTOSO-HR-PROD-Benefits-Agent" }
)

foreach ($agent in $agents) {
    $agentBody = @{
        "@odata.type"              = "Microsoft.Graph.AgentIdentity"
        "displayName"              = $agent.Name
        "agentIdentityBlueprintId" = $blueprintAppId
        "sponsors@odata.bind"      = @(
            "https://graph.microsoft.com/v1.0/users/$sponsorUserId"
        )
    } | ConvertTo-Json -Depth 5

    $identity = Invoke-MgGraphRequest -Method POST `
        -Uri "https://graph.microsoft.com/beta/serviceprincipals/Microsoft.Graph.AgentIdentity" `
        -Headers @{ "OData-Version" = "4.0"; "Content-Type" = "application/json" } `
        -Body $agentBody -OutputType PSObject

    Write-Host "Created: $($agent.Name) → SP ID: $($identity.id), AppId: $($identity.appId)"

    # Step 6: Assign agent-specific application permissions if needed
    # (e.g., only the Recruiting Agent needs People.Read)
    if ($agent.Name -like "*Recruiting*") {
        $appRole = $graphSP.AppRoles | Where-Object {
            $_.Value -eq "People.Read.All" -and $_.AllowedMemberTypes -contains "Application"
        }
        if ($appRole) {
            $assignBody = @{
                principalId = $identity.id
                resourceId  = $graphSP.Id
                appRoleId   = $appRole.Id
            } | ConvertTo-Json
            Invoke-MgGraphRequest -Method POST `
                -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$($identity.id)/appRoleAssignments" `
                -Headers @{ "Content-Type" = "application/json" } `
                -Body $assignBody
        }
    }
}
```

### Python (.NET SDK Equivalent): Listing Agents Under a Shared Blueprint

```python
# Using the Graph API (as in this dashboard's blueprint_service.py)
def list_agents_for_shared_blueprint(graph_client, blueprint_app_id):
    """List all agent identities created from a specific shared blueprint."""
    all_agents = graph_client.get_all(
        "/servicePrincipals/microsoft.graph.agentIdentity"
    )
    return [
        agent for agent in all_agents
        if agent.get("agentIdentityBlueprintId") == blueprint_app_id
    ]
```

---

## Decision Matrix

Use this matrix to choose your blueprint architecture:

| Factor | Pattern 1: Single | Pattern 2: Per Domain | Pattern 3: Per Env | Pattern 4: Per Sub | Pattern 5: Per Tenant |
|--------|-------------------|-----------------------|---------------------|---------------------|----------------------|
| **# Blueprints** | 1 | 3-5 | 3 per domain | 1 per subscription | 1 per tenant |
| **Credential management** | Minimal | Moderate | Moderate | Auto (Foundry) | Per tenant |
| **Environment isolation** | None | None | Strong | Strong | Complete |
| **Permission granularity** | Coarse | By domain | By env | By subscription | By tenant |
| **Blast radius** | All agents | One domain | One env | One subscription | One tenant |
| **Conditional Access** | One policy | Per domain | Per env | Per sub | Per tenant |
| **Best for** | Prototyping | Enterprise | Security-first | Azure-native | Regulated |
| **Complexity** | Low | Moderate | Moderate-High | Moderate | High |

### Recommended Approach for Most Organizations

**Combine Patterns 2 + 3**: Blueprint per domain per environment.

```
HR-DEV-Blueprint    ──→ HR dev agents
HR-PROD-Blueprint   ──→ HR prod agents
FIN-DEV-Blueprint   ──→ Finance dev agents
FIN-PROD-Blueprint  ──→ Finance prod agents
```

This gives you:
- Domain-level permission boundaries
- Environment-level credential and policy isolation
- Manageable number of blueprints (~6-12 for a typical enterprise)
- Each blueprint shared across all agents in that domain+environment

---

## How Azure AI Foundry Associates Blueprints with Projects

### The Foundry Blueprint Auto-Creation Model

When you create a project in Azure AI Foundry and deploy agents, Foundry **automatically creates multiple blueprints** in your Entra tenant. This is not a single blueprint — it's a structured hierarchy of blueprints with distinct roles. Understanding this model is essential for planning how your own shared blueprints can coexist with or replace Foundry-managed ones.

### The Three Blueprint Types Foundry Creates

When a Foundry project provisions agents, the following blueprints appear in your tenant:

```
Entra Tenant (contoso.onmicrosoft.com)
│
└── AI Foundry Project: "customer-service-prod"
    │
    ├── 1️⃣ PROJECT BLUEPRINT (Platform-level)
    │   ├─ displayName: "customer-service-prod"
    │   ├─ createdByAppId: {Foundry 1P App ID}
    │   ├─ serviceManagementReference: {ARM resource path}
    │   ├─ credential: FIC (Managed Identity of the Foundry resource)
    │   ├─ permission: AgentIdentity.CreateAsManager (can create agent identities)
    │   ├─ role: "Project Manager" blueprint — manages lifecycle of agent blueprints
    │   └─ Owner SP alternativeNames:
    │       /subscriptions/{sub}/resourcegroups/{rg}/providers/
    │       Microsoft.CognitiveServices/accounts/{account}/projects/{project}
    │
    ├── 2️⃣ PROJECT MANAGER BLUEPRINT (Orchestration-level)
    │   ├─ displayName: "customer-service-prod-manager"
    │   ├─ createdByAppId: {Project Blueprint's appId}
    │   ├─ serviceManagementReference: {same ARM path}
    │   ├─ credential: FIC (same Managed Identity, or project-level MSI)
    │   ├─ permission: AgentIdentity.CreateAsManager
    │   ├─ role: Creates and manages agent identities on behalf of the project
    │   └─ This blueprint is the one that actually calls Graph API to
    │      provision agent identities when you publish agents in Foundry
    │
    └── 3️⃣ PER-AGENT BLUEPRINTS (Agent-level, one per published agent)
        ├── Blueprint: "CS-Chat-Agent"
        │   ├─ createdByAppId: {Project Manager Blueprint's appId}
        │   ├─ serviceManagementReference: {same ARM path}
        │   ├─ credential: Inherits from project (FIC chain)
        │   └─ Agent Identities:
        │       └── Agent Identity: "CS-Chat-Agent-Instance-1"
        │
        ├── Blueprint: "CS-Email-Agent"
        │   ├─ createdByAppId: {Project Manager Blueprint's appId}
        │   ├─ serviceManagementReference: {same ARM path}
        │   └─ Agent Identities:
        │       └── Agent Identity: "CS-Email-Agent-Instance-1"
        │
        └── Blueprint: "CS-Escalation-Agent"
            ├─ createdByAppId: {Project Manager Blueprint's appId}
            ├─ serviceManagementReference: {same ARM path}
            └─ Agent Identities:
                └── Agent Identity: "CS-Escalation-Agent-Instance-1"
```

### How the Three Layers Relate

```
┌──────────────────────────────────────────────────────────────────────────┐
│  FOUNDRY PROJECT ("customer-service-prod")                               │
│                                                                          │
│  ┌─────────────────────────────────────────┐                             │
│  │  1️⃣ Project Blueprint                    │                             │
│  │  • Created by: Foundry 1st-party app    │                             │
│  │  • Purpose: Represents the project      │                             │
│  │    in Entra ID                          │                             │
│  │  • Credential: Project MSI (FIC)        │                             │
│  │  • Can create: Manager blueprints       │                             │
│  └──────────────┬──────────────────────────┘                             │
│                 │ creates & manages                                       │
│                 ▼                                                         │
│  ┌─────────────────────────────────────────┐                             │
│  │  2️⃣ Project Manager Blueprint            │                             │
│  │  • Created by: Project Blueprint        │                             │
│  │  • Purpose: Orchestrates agent          │                             │
│  │    lifecycle (create/delete/update)      │                             │
│  │  • Permission: AgentIdentity            │                             │
│  │    .CreateAsManager                     │                             │
│  │  • Can create: Per-agent blueprints     │                             │
│  │    + agent identities                   │                             │
│  └──────────────┬──────────────────────────┘                             │
│                 │ creates & manages (one per published agent)             │
│                 ▼                                                         │
│  ┌─────────────────────────────────────────┐                             │
│  │  3️⃣ Per-Agent Blueprint(s)               │                             │
│  │  • Created by: Project Manager          │                             │
│  │  • Purpose: Template for each specific  │                             │
│  │    agent type (Chat, Email, etc.)       │                             │
│  │  • Each holds its own:                  │                             │
│  │    - identifierUri + scope              │                             │
│  │    - inheritablePermissions             │                             │
│  │    - OAuth2PermissionGrants             │                             │
│  │  • Creates: Agent Identities (1:N)      │                             │
│  └─────────────────────────────────────────┘                             │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### How to Identify the Blueprint Type

You can distinguish the three types by examining their properties in Graph API:

| Property | Project Blueprint | Manager Blueprint | Per-Agent Blueprint |
|----------|------------------|-------------------|---------------------|
| `createdByAppId` | Foundry 1P app ID | Project Blueprint's `appId` | Manager Blueprint's `appId` |
| `displayName` | Project name | `{project}-manager` or similar | Agent-specific name |
| `serviceManagementReference` | ARM resource path | Same ARM path | Same ARM path |
| `managerApplications` | Foundry 1P app ID | Project Blueprint's `appId` | Manager Blueprint's `appId` |
| Has `AgentIdentity.CreateAsManager` | Yes (can create manager) | Yes (can create agents) | Typically no |
| Creates agent identities directly | No | Yes | Yes (for its specific agent) |

### The `serviceManagementReference` Grouping

All blueprints belonging to the same Foundry project share the **same `serviceManagementReference`** value. This is how your dashboard's `_resolve_foundry_info()` method groups them:

```python
# From blueprint_service.py — grouping blueprints by SMR
smr_to_foundry: dict = {}  # serviceManagementReference → foundry info

for bp in blueprints:
    # Check owner SP's alternativeNames for ARM resource path
    for owner in owners:
        for alt_name in owner.get("alternativeNames", []):
            match = RESOURCE_PATH_RE.search(alt_name)
            if match:
                # All blueprints with same SMR belong to same project
                smr_to_foundry[bp.service_management_reference] = {
                    "subscription_id": match.group("sub"),
                    "resource_group": match.group("rg"),
                    "account_name": match.group("account"),
                    "project_name": match.group("project"),
                }
```

The ARM resource path pattern:
```
/subscriptions/{subscription-id}
  /resourcegroups/{resource-group}
    /providers/Microsoft.CognitiveServices
      /accounts/{ai-services-account}
        /projects/{foundry-project-name}
```

### Why Foundry Creates Per-Agent Blueprints (Not a Shared One)

Foundry deliberately creates **one blueprint per published agent** rather than sharing a single blueprint across all agents. The reasons are:

| Reason | Explanation |
|--------|-------------|
| **Independent lifecycle** | Each agent can be published, unpublished, or deleted independently without affecting siblings |
| **Isolated credentials** | Each agent blueprint gets its own FIC relationship, so credential rotation is per-agent |
| **Granular Conditional Access** | Admins can apply different CA policies to each agent blueprint |
| **Distinct permission sets** | Each agent's `inheritablePermissions` can differ based on what the agent needs |
| **Compliance & audit** | Clearer audit trail — each agent's token shows its own blueprint as `xms_par_app_azp` |
| **Blast radius** | Compromise of one agent's blueprint doesn't affect others in the same project |

### Approaches: Assigning a Shared Blueprint to Foundry Project Agents

If you want to **override** the per-agent blueprint pattern and use a shared blueprint for Foundry agents, there are several approaches:

#### Approach A: Custom Shared Blueprint with Foundry Project Linkage

Create your own shared blueprint and manually link it to the Foundry project via `serviceManagementReference`:

```powershell
# Create a shared blueprint and link it to a Foundry project
$blueprintBody = @{
    "@odata.type"       = "Microsoft.Graph.AgentIdentityBlueprint"
    "displayName"       = "CONTOSO-CustomerService-PROD-SharedBlueprint"
    "description"       = "Shared blueprint for all Customer Service agents"
    "serviceManagementReference" = "/subscriptions/$subId/resourcegroups/$rg/providers/Microsoft.CognitiveServices/accounts/$account/projects/$project"
    "sponsors@odata.bind" = @(
        "https://graph.microsoft.com/v1.0/users/$sponsorUserId"
    )
} | ConvertTo-Json -Depth 5

$blueprint = Invoke-MgGraphRequest -Method POST `
    -Uri "https://graph.microsoft.com/beta/applications/graph.agentIdentityBlueprint" `
    -Body $blueprintBody -ContentType "application/json"

# Now create all agent identities under this single blueprint
$agents = @("Chat-Agent", "Email-Agent", "Escalation-Agent")
foreach ($agentName in $agents) {
    $agentBody = @{
        "@odata.type"              = "Microsoft.Graph.AgentIdentity"
        "displayName"              = "CS-PROD-$agentName"
        "agentIdentityBlueprintId" = $blueprint.appId
        "sponsors@odata.bind"      = @(
            "https://graph.microsoft.com/v1.0/users/$sponsorUserId"
        )
    } | ConvertTo-Json -Depth 5

    Invoke-MgGraphRequest -Method POST `
        -Uri "https://graph.microsoft.com/beta/serviceprincipals/Microsoft.Graph.AgentIdentity" `
        -Headers @{ "OData-Version" = "4.0"; "Content-Type" = "application/json" } `
        -Body $agentBody
}
```

> **Trade-off**: You lose the per-agent lifecycle independence that Foundry's native model provides, but gain simplified credential and permission management.

#### Approach B: Shared Blueprint as the Manager, Foundry-Created Agents

Keep Foundry's native blueprint creation but replace the Project Manager Blueprint with your own shared blueprint that has `AgentIdentity.CreateAsManager`:

```
Foundry Project
│
├── Project Blueprint (Foundry-managed, keep as-is)
│
├── YOUR Shared Blueprint (replaces Manager)
│   ├─ credential: Your FIC / managed identity
│   ├─ permission: AgentIdentity.CreateAsManager
│   ├─ inheritablePermissions: Your baseline scopes
│   └─ Creates all agent identities for this project
│
└── Agent Identities (all under YOUR blueprint)
    ├── Chat Agent Identity
    ├── Email Agent Identity
    └── Escalation Agent Identity
```

> **Important**: This approach requires you to handle agent identity lifecycle management that Foundry would normally automate. You're taking over the "manager" role.

#### Approach C: Blueprint per Environment, Foundry Projects Linked via SMR

This is the **recommended approach** for most organizations. Keep Foundry's native per-agent blueprints but use separate Foundry projects per environment, each with their own SMR:

```
Tenant: contoso.onmicrosoft.com
│
├── Foundry Project: "cs-agents-dev" (Subscription: sub-dev)
│   ├── Project Blueprint (auto)
│   ├── Manager Blueprint (auto)
│   ├── Chat Agent Blueprint → Chat Agent Identity (dev)
│   └── Email Agent Blueprint → Email Agent Identity (dev)
│   SMR: /subscriptions/sub-dev/.../projects/cs-agents-dev
│
├── Foundry Project: "cs-agents-test" (Subscription: sub-test)
│   ├── Project Blueprint (auto)
│   ├── Manager Blueprint (auto)
│   ├── Chat Agent Blueprint → Chat Agent Identity (test)
│   └── Email Agent Blueprint → Email Agent Identity (test)
│   SMR: /subscriptions/sub-test/.../projects/cs-agents-test
│
└── Foundry Project: "cs-agents-prod" (Subscription: sub-prod)
    ├── Project Blueprint (auto)
    ├── Manager Blueprint (auto)
    ├── Chat Agent Blueprint → Chat Agent Identity (prod)
    └── Email Agent Blueprint → Email Agent Identity (prod)
    SMR: /subscriptions/sub-prod/.../projects/cs-agents-prod
```

**Why this is recommended**:
- Foundry manages the blueprint lifecycle automatically
- Environment isolation via separate subscriptions/projects
- Each environment's blueprints have independent credentials
- `serviceManagementReference` groups them cleanly for dashboarding
- Conditional Access can target per-project blueprints

### Mapping Foundry Blueprints Across Environments

Use the `serviceManagementReference` and `createdByAppId` to trace the full hierarchy:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Query: GET /applications/microsoft.graph.agentIdentityBlueprint         │
│ Filter: serviceManagementReference contains 'cs-agents'                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ SMR: .../projects/cs-agents-dev                                         │
│ ├── Blueprint: cs-agents-dev                    (Project)               │
│ ├── Blueprint: cs-agents-dev-manager            (Manager)               │
│ ├── Blueprint: CS-Chat-Agent-Dev                (Per-Agent)             │
│ └── Blueprint: CS-Email-Agent-Dev               (Per-Agent)             │
│                                                                         │
│ SMR: .../projects/cs-agents-prod                                        │
│ ├── Blueprint: cs-agents-prod                   (Project)               │
│ ├── Blueprint: cs-agents-prod-manager           (Manager)               │
│ ├── Blueprint: CS-Chat-Agent-Prod               (Per-Agent)             │
│ └── Blueprint: CS-Email-Agent-Prod              (Per-Agent)             │
│                                                                         │
│ Linkage chain (follow createdByAppId):                                  │
│ Foundry 1P App → Project BP → Manager BP → Per-Agent BP → Agent ID     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### When to Use Shared Blueprints vs. Foundry-Native Per-Agent Blueprints

| Scenario | Recommendation | Rationale |
|----------|---------------|-----------|
| Foundry-only agents, standard deployment | **Use Foundry-native** (per-agent) | Foundry handles lifecycle, credentials, and cleanup |
| Custom agents alongside Foundry agents | **Create your own shared blueprint** | Foundry can't manage custom agent identity lifecycle |
| All agents need same permission baseline | **Shared blueprint + inheritablePermissions** | Avoids duplicating permission config per agent |
| Each agent needs independent CA policies | **Foundry-native per-agent** | Each blueprint = independent CA target |
| Multi-environment (dev/test/prod) | **Separate Foundry projects per env** | Each project creates its own set of blueprints |
| Cross-platform agents (Foundry + Copilot Studio + custom) | **One shared blueprint per platform per env** | Different platforms have different trust boundaries |
| Regulated industry, strict audit | **Per-agent blueprints** | Maximum granularity in audit trail |
| Dev/prototype, minimize overhead | **Single shared blueprint** | Fastest setup, revisit for production |

### Tracing the Full Foundry → Blueprint → Agent Chain in the Dashboard

Your dashboard's `_resolve_foundry_info()` already uses the `serviceManagementReference` and owner SP `alternativeNames` to trace the Foundry linkage. To also trace the **blueprint hierarchy** (Project → Manager → Per-Agent), you can follow the `createdByAppId` chain:

```python
def trace_blueprint_hierarchy(blueprints: List[Blueprint]) -> dict:
    """Build the creation chain: which blueprint created which.
    
    Returns a dict mapping blueprint appId → list of child blueprint appIds.
    """
    # Group by createdByAppId
    children = {}
    for bp in blueprints:
        parent = bp.created_by_app_id
        if parent:
            children.setdefault(parent, []).append(bp.app_id)
    
    # Identify root blueprints (created by Foundry 1P, not another blueprint)
    blueprint_app_ids = {bp.app_id for bp in blueprints}
    roots = [
        bp for bp in blueprints
        if bp.created_by_app_id not in blueprint_app_ids
    ]
    
    return {
        "roots": [r.app_id for r in roots],  # Project Blueprints
        "hierarchy": children,
    }

# Example output:
# {
#   "roots": ["project-bp-appid"],
#   "hierarchy": {
#     "foundry-1p-appid": ["project-bp-appid"],
#     "project-bp-appid": ["manager-bp-appid"],
#     "manager-bp-appid": ["chat-agent-bp-appid", "email-agent-bp-appid"]
#   }
# }
```

### Blueprint Scoping: Foundry Resource vs. Project Level

> **Key Question:** Do blueprints work at the Foundry **resource** level or the **project** level?

**Answer: Blueprints are scoped at the PROJECT level, NOT the resource level.**

The hierarchy is:

```
Azure Subscription
  └── Resource Group
        └── Foundry Resource (AI Services / Cognitive Services account)
              ├── Project A  ← has its OWN set of blueprints
              ├── Project B  ← has its OWN set of blueprints
              └── Project C  ← has its OWN set of blueprints
```

**Why project-level?**

1. **`serviceManagementReference`** — The ARM path that links a blueprint to Foundry includes the **project name**:
   ```
   /subscriptions/{sub}/resourcegroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{account}/projects/{project}
   ```
   This means the blueprint is tied to a specific project, not the parent account.

2. **Each project gets its own blueprint set** — When you publish an agent in Foundry, the platform creates:
   - A **Project Blueprint** for the project itself
   - A **Manager Blueprint** for the project manager
   - A **Per-Agent Blueprint** for each published agent

3. **One resource, many projects, independent blueprints** — Projects under the same Foundry resource do NOT share blueprints. Each project operates independently.

**Implications for the Blueprint per Business Domain pattern:**

| Scenario | Blueprint Sharing |
|----------|-------------------|
| 2 projects in same domain, same resource | Each project links to the **same domain blueprint** |
| 2 projects in different domains, same resource | Each project has a **different domain blueprint** |
| 3 projects in same domain, different resources | All 3 link to the **same domain blueprint** |
| dev + prod projects in same domain | Both link to the **same domain blueprint**, differ by `environment` tag |

The domain blueprint acts as the **shared identity template** across all projects in that domain, regardless of which Foundry resource hosts them.

---

### Foundry Blueprint Limits

| Constraint | Value | Source |
|------------|-------|--------|
| Max agent identities per blueprint principal | 250 | `AgentIdentity.CreateAsManager` permission documentation |
| Max total agent identities | Tenant directory limits apply | Entra directory object limits |
| Blueprint credential types supported | FIC (MSI), Certificate, Client Secret | Blueprint credential documentation |
| `inheritablePermissions` scope model | `enumeratedScopes` (recommended) or `allScopes` | Graph API documentation |

> **250 agent identity limit**: Each blueprint principal is limited to creating 250 agent identities via `AgentIdentity.CreateAsManager`. For Foundry projects with more than 250 agents, multiple Manager Blueprints are needed.

---

## References

### Official Microsoft Documentation
- [Microsoft Entra Agent ID key concepts](https://learn.microsoft.com/en-us/entra/agent-id/key-concepts)
- [Agent identities, service principals, and applications](https://learn.microsoft.com/en-us/entra/agent-id/agent-service-principals)
- [Agent identity blueprints in Microsoft Entra Agent ID](https://learn.microsoft.com/en-us/entra/agent-id/agent-blueprint)
- [Create an agent identity blueprint](https://learn.microsoft.com/en-us/entra/agent-id/create-blueprint)
- [How are agent identities created? (Creation channels)](https://learn.microsoft.com/en-us/entra/agent-id/agent-id-creation-channels)
- [Plan your agent identity architecture](https://learn.microsoft.com/en-us/entra/agent-id/how-to-plan-agent-identity-architecture)
- [Microsoft Entra Agent ID design patterns](https://learn.microsoft.com/en-us/entra/agent-id/concept-agent-id-design-patterns)
- [Microsoft Entra Agent ID APIs overview (Graph beta)](https://learn.microsoft.com/en-us/graph/api/resources/agentid-platform-overview?view=graph-rest-beta)
- [Application resource type (Graph beta)](https://learn.microsoft.com/en-us/graph/api/resources/application?view=graph-rest-beta)
- [agentIdentityBlueprint resource type (Graph beta)](https://learn.microsoft.com/en-us/graph/api/resources/agentidentityblueprint?view=graph-rest-beta)

### Community / Expert References
- [Derk van der Woude — Agent Identity demystified](https://derkvanderwoude.medium.com/agent-identity-security-demystified-2ecb164239bf) (Jan 2026)
- [Derk van der Woude — From Blueprint to Token: How Entra Agent Identity Inheritance Really Works](https://derkvanderwoude.medium.com/from-blueprint-to-token-how-entra-agent-identity-inheritance-really-works-fed114abe281) (Mar 2026)
- [Creating Entra Agent ID Blueprints and Identities with PowerShell and .NET](https://levelup.gitconnected.com/creating-entra-agent-id-blueprints-and-identities-with-powershell-and-net-fba03825e74c)

### Graph API Endpoints
| Operation | Endpoint |
|-----------|----------|
| Create blueprint | `POST /beta/applications/graph.agentIdentityBlueprint` |
| Create blueprint principal | `POST /beta/serviceprincipals/graph.agentIdentityBlueprintPrincipal` |
| List blueprints | `GET /beta/applications/microsoft.graph.agentIdentityBlueprint` |
| Set inheritable permissions | `POST /beta/applications/microsoft.graph.agentIdentityBlueprint/{appId}/inheritablePermissions` |
| Update inheritable permissions | `PATCH /beta/applications/microsoft.graph.agentIdentityBlueprint/{appId}/inheritablePermissions/{resourceAppId}` |
| Create agent identity | `POST /beta/serviceprincipals/Microsoft.Graph.AgentIdentity` |
| List agent identities | `GET /beta/servicePrincipals/microsoft.graph.agentIdentity` |
| Grant OAuth2 consent | `POST /v1.0/oauth2PermissionGrants` |

---

*Document generated: April 2026*
*Status: Entra Agent ID is in Preview — APIs are subject to change*
