"""Reference Docs page: PowerShell, C#, and best-practice code snippets.

References:
- Article 1: https://medium.com/gitconnected/creating-entra-agent-id-blueprints-and-identities-with-powershell-and-net-fba03825e74c
  PowerShell setup script (setup.ps1) and C# integration patterns (Program.cs)
- Article 2: https://derkvanderwoude.medium.com/from-blueprint-to-token-how-entra-agent-identity-inheritance-really-works-fed114abe281
  Token flow details, inheritance mechanics, sign-in log behavior
"""

from __future__ import annotations

import streamlit as st

from config.theme import GREEN_BRIGHT, GREEN_DIM, AMBER_WARN, RED_ALERT


def render(store: dict, **kwargs) -> None:
    st.markdown("## Reference Documentation")

    st.caption(
        "Official Microsoft Entra Agent ID implementation patterns. "
        "Based on Microsoft Learn docs and community articles by Derk van der Woude."
    )

    tabs = st.tabs([
        "Create Blueprint",
        "Create Identity",
        "Assign Permissions",
        "Acquire Tokens",
        "Inheritance Model",
        "Security Practices",
    ])

    with tabs[0]:
        _tab_create_blueprint()

    with tabs[1]:
        _tab_create_identity()

    with tabs[2]:
        _tab_assign_permissions()

    with tabs[3]:
        _tab_acquire_tokens()

    with tabs[4]:
        _tab_inheritance_model()

    with tabs[5]:
        _tab_security_practices()


def _tab_create_blueprint() -> None:
    st.markdown(
        f"<h4 style='color: {GREEN_BRIGHT};'>Create an Agent Identity Blueprint</h4>"
        f"<p style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        "The blueprint is the template from which agent identities are created. "
        "It holds credentials, inheritable permissions, and the identifier URI "
        "(api://{{appId}}) with the access_agent scope.</p>",
        unsafe_allow_html=True,
    )

    st.markdown(f"**PowerShell — setup.ps1 (from Article 1)**")
    st.code("""# setup.ps1 — Full blueprint setup from Article 1
# Requires: Microsoft.Graph.Beta module
Connect-MgGraph -Scopes "Application.ReadWrite.All"

# 1. Create the blueprint application via Graph beta endpoint
$blueprintBody = @{
    displayName     = "Contoso AI Agent Blueprint"
    signInAudience  = "AzureADMyOrg"
    # Sponsors: accountable human owners (enforced by Entra Agent ID)
    sponsors        = @(
        @{ "@odata.id" = "https://graph.microsoft.com/v1.0/users/{sponsor-user-id}" }
    )
}
$blueprintApp = Invoke-MgGraphRequest -Method POST `
    -Uri "/beta/applications/graph.agentIdentityBlueprint" `
    -Body ($blueprintBody | ConvertTo-Json -Depth 5)

$appId = $blueprintApp.appId
$appObjectId = $blueprintApp.id
Write-Host "Blueprint App ID: $appId"

# 2. Set identifier URI with access_agent scope
$identifierUri = "api://$appId"
Update-MgBetaApplication -ApplicationId $appObjectId `
    -IdentifierUris @($identifierUri) `
    -Api @{
        OAuth2PermissionScopes = @(
            @{
                Id                      = [guid]::NewGuid()
                Value                   = "access_agent"
                AdminConsentDisplayName = "Access agent"
                AdminConsentDescription = "Allow the app to access the agent"
                IsEnabled               = $true
                Type                    = "User"
            }
        )
    }

# 3. Create the blueprint service principal (makes it usable in the tenant)
$principalBody = @{
    appId = $appId
}
$blueprintSP = Invoke-MgGraphRequest -Method POST `
    -Uri "/beta/servicePrincipals/graph.agentIdentityBlueprintPrincipal" `
    -Body ($principalBody | ConvertTo-Json)

Write-Host "Blueprint Principal ID: $($blueprintSP.id)"

# 4. Add federated identity credential (managed identity — recommended)
$ficParams = @{
    name      = "managed-identity-fic"
    issuer    = "https://login.microsoftonline.com/{tenant-id}/v2.0"
    subject   = "{managed-identity-principal-id}"
    audiences = @("api://AzureADTokenExchange")
}
New-MgApplicationFederatedIdentityCredential `
    -ApplicationId $appObjectId `
    -BodyParameter $ficParams""", language="powershell")

    st.markdown(
        f"<p style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        "Key: sponsors field enforces accountable ownership. "
        "The identifier URI (api://{{appId}}) and access_agent scope are required "
        "for the token exchange protocol.</p>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"<p style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        "\u2192 Maps to: Blueprint Visualizer > Create New Entity > Blueprint</p>",
        unsafe_allow_html=True,
    )


def _tab_create_identity() -> None:
    st.markdown(
        f"<h4 style='color: {GREEN_BRIGHT};'>Create an Agent Identity</h4>"
        f"<p style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        "Agent identities are runtime identities created from a blueprint. "
        "Each has its own permissions and audit trail.</p>",
        unsafe_allow_html=True,
    )

    st.markdown(f"**Microsoft Graph API**")
    st.code("""# Create an agent identity via Graph API
POST https://graph.microsoft.com/v1.0/agentIdentityBlueprints/{blueprint-id}/agentIdentities
Authorization: Bearer {token}
Content-Type: application/json

{
    "displayName": "Customer Support Agent",
    "description": "Handles customer support queries"
}

# Response includes:
# - id: Agent identity object ID
# - clientId: Agent identity client ID
# - blueprintId: Parent blueprint ID""", language="http")

    st.markdown(f"**Creating an Agent User Account**")
    st.code("""# Create agent user (requires AgentIdUser.ReadWrite.IdentityParentedBy)
POST https://graph.microsoft.com/beta/users
Content-Type: application/json

{
    "@odata.type": "microsoft.graph.agentUser",
    "displayName": "Support Agent User",
    "userPrincipalName": "agent-support@contoso.onmicrosoft.com",
    "identityParentId": "{agent-identity-id}",
    "mailNickname": "agent-support",
    "accountEnabled": true
}""", language="http")

    st.markdown(
        f"<p style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        "\u2192 Maps to: Blueprint Visualizer > Create New Entity > Agent Identity</p>",
        unsafe_allow_html=True,
    )


def _tab_assign_permissions() -> None:
    st.markdown(
        f"<h4 style='color: {GREEN_BRIGHT};'>Assign Permissions</h4>"
        f"<p style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        "Blueprint-level inheritable permissions are shared by all agent identities. "
        "Direct app role assignments are per-agent. "
        "<b>Important from Article 2:</b> Delegated permission inheritance requires BOTH "
        "inheritablePermissions on the application object AND an OAuth2PermissionGrant "
        "on the service principal (admin consent).</p>",
        unsafe_allow_html=True,
    )

    st.markdown(f"**Inheritable Permissions (Blueprint-level) — Dual Requirement**")
    st.code("""# Step 1: Declare inheritablePermissions on the blueprint APPLICATION object
# This alone is NOT sufficient — the permission won't appear in tokens
$inheritableBody = @{
    inheritablePermissions = @(
        @{
            permissionId = "{graph-user-read-scope-id}"
            resourceAppId = "00000003-0000-0000-c000-000000000000"  # MS Graph
        }
    )
}
Invoke-MgGraphRequest -Method PATCH `
    -Uri "/beta/applications/$appObjectId" `
    -Body ($inheritableBody | ConvertTo-Json -Depth 5)

# Step 2: Create OAuth2PermissionGrant on the blueprint SERVICE PRINCIPAL
# This is the admin consent that activates the inheritance
$grantBody = @{
    clientId    = $blueprintSPId    # Blueprint service principal
    consentType = "AllPrincipals"
    resourceId  = $graphSPId        # Microsoft Graph service principal
    scope       = "User.Read Mail.Read"
}
New-MgOauth2PermissionGrant -BodyParameter $grantBody

# Without BOTH steps, the permission will NOT appear in agent tokens.
# This is the most common gotcha with Entra Agent ID inheritance.""", language="powershell")

    st.markdown(f"**Direct App Role Assignments (Agent-level)**")
    st.code("""# Assign an app role directly to a specific agent identity
# These are NOT inherited — they're per-identity and show in the 'roles' claim
Connect-MgGraph -Scopes "Application.Read.All AppRoleAssignment.ReadWrite.All"

# Get Microsoft Graph service principal
$graphSp = Get-MgServicePrincipal `
    -Filter "appId eq '00000003-0000-0000-c000-000000000000'"

# Find the Mail.Send app role
$mailSendRole = $graphSp.AppRoles | Where-Object {
    $_.Value -eq "Mail.Send" -and
    $_.AllowedMemberTypes -contains "Application"
}

# Assign to the agent identity's service principal
New-MgServicePrincipalAppRoleAssignment `
    -ServicePrincipalId $agentIdentitySpId `
    -PrincipalId $agentIdentitySpId `
    -ResourceId $graphSp.Id `
    -AppRoleId $mailSendRole.Id

# Note: 30-60 second propagation delay after granting new roles
# (permission caching per Article 2)""", language="powershell")

    st.markdown(
        f"<p style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        "\u2192 Maps to: Permission Manager page</p>",
        unsafe_allow_html=True,
    )


def _tab_acquire_tokens() -> None:
    st.markdown(
        f"<h4 style='color: {GREEN_BRIGHT};'>Acquire Tokens (Autonomous Flow)</h4>"
        f"<p style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        "The token chain: Blueprint \u2192 Agent Identity \u2192 Resource. "
        "Per Article 2: fmi_path MUST match the target agent's AppId, NOT the blueprint's AppId. "
        "\"If they match, something went wrong.\"</p>",
        unsafe_allow_html=True,
    )

    st.markdown(f"**Step 1: T1 \u2014 Exchange Token (Blueprint authenticates)**")
    st.code("""# T1: Blueprint authenticates, targeting agent identity via fmi_path
# Per Article 2: fmi_path = agent identity's client_id, NOT blueprint's
POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

client_id={blueprint-client-id}
&scope=api://AzureADTokenExchange/.default
&grant_type=client_credentials
&client_assertion={managed-identity-assertion}
&client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
&fmi_path={agent-identity-client-id}

# T1 Claims:
# - aud = api://{agent-identity-client-id} (proves authorization to impersonate)
# - sub = blueprint service principal OID
# - idtyp = "app"
# - azpacr = "2" (cert/MI) or "1" (client secret)
#
# Sign-in log entry: blueprint as principal, resource = api://AzureADTokenExchange""", language="http")

    st.markdown(f"**Step 2: T2/TR \u2014 Resource Token (Agent identity accesses resource)**")
    st.code("""# T2: Agent identity exchanges T1 for resource access
POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

client_id={agent-identity-client-id}
&scope=https://graph.microsoft.com/.default
&grant_type=client_credentials
&client_assertion={T1-access-token}
&client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer

# T2/TR Claims (KEY claims from Article 2):
# - appid = agent identity's AppId
# - xms_par_app_azp = blueprint's AppId (confirms parent-child relationship)
# - roles = directly assigned application permissions (appRoleAssignments)
# - scp = inherited delegated scopes (dynamically merged from blueprint)
# - idtyp = "app"
#
# Sign-in log entry: agent identity as principal, resource = graph.microsoft.com
# Agent identity shows NO permissions in Azure portal — this is BY DESIGN""", language="http")

    st.markdown(f"**Step 3: T3 \u2014 Agent User Token (Optional)**")
    st.code("""# T3: Exchange for delegated user token (user_fic grant type)
# Only available when agent identity has an associated agent user account
POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

client_id={agent-identity-client-id}
&scope=https://graph.microsoft.com/.default
&grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
&client_assertion={T1-access-token}
&client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
&requested_token_use=user_fic
&user_id={agent-user-object-id}
&user_federated_identity_credential={T2-exchange-token}""", language="http")

    st.markdown(f"**C# with Microsoft.Identity.Web (from Article 1 — Program.cs)**")
    st.code("""// Program.cs — Agent Identity integration with ASP.NET Core
var builder = WebApplication.CreateBuilder(args);

// Configure authentication with agent identity support
builder.Services.AddMicrosoftIdentityWebApiAuthentication(
    builder.Configuration);
builder.Services.AddAgentIdentities();    // Enables agent identity token exchange
builder.Services.AddInMemoryTokenCaches();

var app = builder.Build();

// Acquire token as agent identity using IDownstreamApi
app.MapGet("/call-graph-as-agent", async (
    IDownstreamApi downstreamApi,
    HttpContext httpContext) =>
{
    // PostForAppAsync — application-level token (T2 flow)
    var result = await downstreamApi.PostForAppAsync<object, GraphResponse>(
        "GraphApi",
        new { query = "users" },
        options => options.WithAgentIdentity("{agent-identity-client-id}")
    );
    return Results.Ok(result);
});

// Alternative: direct authorization header acquisition
app.MapGet("/raw-token", async (HttpContext httpContext) =>
{
    var authProvider = httpContext.RequestServices
        .GetRequiredService<IAuthorizationHeaderProvider>();

    var options = new AuthorizationHeaderProviderOptions()
        .WithAgentIdentity("{agent-identity-client-id}");

    string authHeader = await authProvider
        .CreateAuthorizationHeaderForAppAsync(
            "https://graph.microsoft.com/.default", options);

    return Results.Ok(authHeader);
});

app.Run();""", language="csharp")

    st.markdown(
        f"<p style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        "\u2192 Maps to: Token Simulator page</p>",
        unsafe_allow_html=True,
    )


def _tab_security_practices() -> None:
    st.markdown(
        f"<h4 style='color: {GREEN_BRIGHT};'>Security Best Practices</h4>",
        unsafe_allow_html=True,
    )

    # Credential comparison table
    table_html = f"""<pre style="font-family: 'Share Tech Mono', monospace;
color: {GREEN_BRIGHT}; background: transparent;
padding: 8px; line-height: 1.6;">
{'Credential Type':<25} {'Security':<12} {'Rotation':<15} {'Recommendation':<20}
{'─' * 25} {'─' * 12} {'─' * 15} {'─' * 20}
<span style="color: {GREEN_BRIGHT};">{'Managed Identity':<25} {'HIGH':<12} {'Automatic':<15} {'PRODUCTION':<20}</span>
<span style="color: {AMBER_WARN};">{'Certificate':<25} {'MEDIUM':<12} {'Manual':<15} {'ACCEPTABLE':<20}</span>
<span style="color: {RED_ALERT};">{'Client Secret':<25} {'LOW':<12} {'Manual':<15} {'DEV ONLY':<20}</span>
</pre>"""
    st.markdown(table_html, unsafe_allow_html=True)

    st.markdown(
        f"<h5 style='color: {GREEN_BRIGHT};'>Key Principles</h5>",
        unsafe_allow_html=True,
    )

    principles = [
        ("Use Agent Identity, not Service Principals",
         "Agent identities provide dedicated audit trails, enforced sponsorship, "
         "and platform-level privilege restrictions."),
        ("One Blueprint per Trust Boundary",
         "Agents sharing a runtime, secrets, and network share a trust boundary "
         "and can share a blueprint. Separate boundaries need separate blueprints."),
        ("Inheritable Permissions for Common Baseline",
         "Use blueprint-level permissions when all agents need the same base access. "
         "Use direct assignments for agent-specific differentiation."),
        ("Never Store Secrets in Frontend Code",
         "Use Managed Identities or certificates. Client secrets should only be used "
         "for local development and never committed to source control."),
        ("Enforce Sponsorship",
         "Every agent identity must have an accountable human sponsor. "
         "This is enforced at the platform level by Entra Agent ID."),
        ("Use Ephemeral Identities When Possible",
         "For short-lived tasks, create agent identities at runtime and delete them "
         "when the task completes. Inheritable permissions flow automatically."),
        ("Understand the Portal Gap (Article 2)",
         "Agent identity service principals show NO permissions in the Azure portal. "
         "This is BY DESIGN — permissions exist only in token claims at issuance time. "
         "Use sign-in logs (two entries per exchange) to verify."),
        ("Mind the Propagation Delay (Article 2)",
         "After granting new app role assignments, there is a 30-60 second "
         "permission caching delay before the new roles appear in tokens."),
    ]

    for title, desc in principles:
        st.markdown(
            f"<div style='border-left: 2px solid {GREEN_DIM}; padding: 4px 12px; "
            f"margin: 8px 0; font-family: \"Share Tech Mono\", monospace;'>"
            f"<span style='color: {GREEN_BRIGHT};'>\u25b8 {title}</span><br>"
            f"<span style='color: {GREEN_DIM}; font-size: 0.85em;'>{desc}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )


def _tab_inheritance_model() -> None:
    """Article 2: Three inheritance categories explained."""
    st.markdown(
        f"<h4 style='color: {GREEN_BRIGHT};'>Permission Inheritance Model</h4>"
        f"<p style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        "From Article 2: \"From Blueprint to Token — How Entra Agent Identity "
        "Inheritance Really Works.\" Three distinct categories govern what "
        "agent identities inherit from their parent blueprint.</p>",
        unsafe_allow_html=True,
    )

    # Category 1: Protocol Properties
    st.markdown(
        f"<div style='border: 1px solid {GREEN_BRIGHT}; padding: 12px; margin: 8px 0;'>"
        f"<span style='color: {GREEN_BRIGHT}; font-size: 1.1em;'>"
        "1. PROTOCOL PROPERTIES (Always Inherited)</span><br>"
        f"<span style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        "These are always inherited from the blueprint — no additional configuration needed."
        "</span></div>",
        unsafe_allow_html=True,
    )
    st.code("""# Always inherited from blueprint application object:
# - OAuth2 configuration (scopes, grant types)
# - Identifier URIs (api://{appId})
# - Supported grant types (client_credentials, jwt-bearer, refresh_token)
# - Reply URLs and redirect URIs
#
# These flow automatically to all agent identities created from the blueprint.
# No action required — they're part of the application manifest.""", language="powershell")

    # Category 2: Delegated Permissions
    st.markdown(
        f"<div style='border: 1px solid {AMBER_WARN}; padding: 12px; margin: 8px 0;'>"
        f"<span style='color: {AMBER_WARN}; font-size: 1.1em;'>"
        "2. DELEGATED PERMISSIONS (Conditionally Inherited)</span><br>"
        f"<span style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        "Requires BOTH conditions. Missing either one = permission NOT in token."
        "</span></div>",
        unsafe_allow_html=True,
    )
    st.code("""# CONDITION 1: inheritablePermissions on the blueprint APPLICATION object
# This declares the permission as inheritable but does NOT activate it
Update-MgBetaApplication -ApplicationId $appObjectId -BodyParameter @{
    inheritablePermissions = @(
        @{ permissionId = $scopeId; resourceAppId = $graphAppId }
    )
}

# CONDITION 2: OAuth2PermissionGrant on the blueprint SERVICE PRINCIPAL
# This is the admin consent that actually activates the inheritance
New-MgOauth2PermissionGrant -BodyParameter @{
    clientId    = $blueprintSPId
    consentType = "AllPrincipals"
    resourceId  = $graphSPId
    scope       = "User.Read Mail.Read"
}

# With BOTH conditions met:
# - Permissions are dynamically merged at token issuance time
# - They appear in the 'scp' claim of T2/TR tokens
# - Agent identity shows NO permissions in Azure portal (BY DESIGN)
# - The portal gap is the #1 source of confusion""", language="powershell")

    # Category 3: Not Inherited
    st.markdown(
        f"<div style='border: 1px solid {RED_ALERT}; padding: 12px; margin: 8px 0;'>"
        f"<span style='color: {RED_ALERT}; font-size: 1.1em;'>"
        "3. NOT INHERITED (Direct Assignment Only)</span><br>"
        f"<span style='color: {GREEN_DIM}; font-size: 0.85em;'>"
        "These must be assigned directly to each agent identity's service principal."
        "</span></div>",
        unsafe_allow_html=True,
    )
    st.code("""# These CANNOT be inherited from the blueprint:
# - appRoleAssignments (application permissions like Mail.Send)
# - Azure RBAC role assignments (Contributor, Reader, etc.)
# - Sponsor designations (each identity has its own sponsors)
#
# Each must be granted individually per agent identity.
# They appear in the 'roles' claim of T2/TR tokens.
#
# Design rationale: Application permissions are high-privilege
# and should be explicitly granted per-identity for audit accountability.""", language="powershell")

    # Sign-in log behavior
    st.markdown(
        f"<h5 style='color: {GREEN_BRIGHT};'>Sign-in Log Behavior (Article 2)</h5>",
        unsafe_allow_html=True,
    )
    log_html = f"""<pre style="font-family: 'Share Tech Mono', monospace;
color: {GREEN_BRIGHT}; background: transparent;
padding: 8px; line-height: 1.6;">
{'Entry':<20} {'Principal':<30} {'Resource':<35} {'Auth Method':<20}
{'─' * 20} {'─' * 30} {'─' * 35} {'─' * 20}
{'T1 (Exchange)':<20} {'Blueprint SP':<30} {'api://AzureADTokenExchange':<35} {'Cert/MI/Secret':<20}
{'TR (Resource)':<20} {'Agent Identity SP':<30} {'graph.microsoft.com (etc.)':<35} {'jwt-bearer (via T1)':<20}
</pre>
<p style="color: {GREEN_DIM}; font-size: 0.85em;">
Each token exchange produces TWO sign-in log entries. Use these to audit
agent activity — the T1 entry traces to the blueprint, the TR entry traces
to the specific agent identity accessing the resource.
</p>"""
    st.markdown(log_html, unsafe_allow_html=True)
