"""Data models for Agent Identity Blueprints and Blueprint Principals.

References:
- https://medium.com/gitconnected/creating-entra-agent-id-blueprints-and-identities-with-powershell-and-net-fba03825e74c
- https://derkvanderwoude.medium.com/from-blueprint-to-token-how-entra-agent-identity-inheritance-really-works-fed114abe281
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class CredentialType(Enum):
    MANAGED_IDENTITY = "managed_identity"
    CERTIFICATE = "certificate"
    CLIENT_SECRET = "client_secret"


@dataclass
class OAuth2Scope:
    """OAuth2 permission scope exposed by the blueprint (e.g., access_agent)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    value: str = "access_agent"
    admin_consent_display_name: str = "Access agent"
    admin_consent_description: str = (
        "Allow the application to access the agent on behalf of the signed-in user."
    )
    is_enabled: bool = True
    scope_type: str = "User"


@dataclass
class Blueprint:
    display_name: str
    description: str
    credential_type: CredentialType
    tenant_id: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    app_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    credential_hint: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Sponsor/owner governance (enforced by Entra Agent ID platform)
    sponsor_ids: List[str] = field(default_factory=list)
    owner_ids: List[str] = field(default_factory=list)
    # Protocol properties (always inherited by child identities)
    identifier_uri: str = ""
    oauth2_scopes: List[OAuth2Scope] = field(default_factory=list)
    supported_grant_types: List[str] = field(default_factory=lambda: [
        "client_credentials", "jwt-bearer", "refresh_token"
    ])
    # Graph API endpoint used for creation
    graph_endpoint: str = "/beta/applications/graph.agentIdentityBlueprint"
    # Foundry / Azure resource linkage (populated from Graph API)
    service_management_reference: str = ""
    created_by_app_id: str = ""
    # Resolved Foundry project info (populated by BlueprintService)
    foundry_resource_id: str = ""     # Full ARM resource path
    foundry_subscription_id: str = ""
    foundry_resource_group: str = ""
    foundry_account_name: str = ""     # AI Services / Cognitive Services account
    foundry_project_name: str = ""

    def __post_init__(self):
        if not self.credential_hint:
            hints = {
                CredentialType.MANAGED_IDENTITY: "System-Assigned Managed Identity",
                CredentialType.CERTIFICATE: "Thumbprint: A1B2C3D4...SIMU (SIMULATED)",
                CredentialType.CLIENT_SECRET: "SIMULATED-SECRET-DO-NOT-USE-0000",
            }
            self.credential_hint = hints.get(self.credential_type, "")
        if not self.identifier_uri:
            self.identifier_uri = f"api://{self.app_id}"
        if not self.oauth2_scopes:
            self.oauth2_scopes = [OAuth2Scope()]
        if not self.sponsor_ids:
            self.sponsor_ids = ["00000000-0000-0000-0000-000000000099"]
        if not self.owner_ids:
            self.owner_ids = ["00000000-0000-0000-0000-000000000099"]

    @classmethod
    def from_graph_response(cls, data: dict, tenant_id: str) -> Blueprint:
        """Deserialize a Blueprint from a Graph API response dict."""
        # Infer credential type from key/password credentials
        if data.get("keyCredentials", []):
            credential_type = CredentialType.CERTIFICATE
        elif data.get("passwordCredentials", []):
            credential_type = CredentialType.CLIENT_SECRET
        else:
            credential_type = CredentialType.MANAGED_IDENTITY

        # Parse OAuth2 permission scopes
        raw_scopes = data.get("api", {}).get("oauth2PermissionScopes", [])
        oauth2_scopes = [
            OAuth2Scope(
                id=s.get("id", str(uuid.uuid4())),
                value=s.get("value", "access_agent"),
                admin_consent_display_name=s.get("adminConsentDisplayName", "Access agent"),
                admin_consent_description=s.get(
                    "adminConsentDescription",
                    "Allow the application to access the agent on behalf of the signed-in user.",
                ),
                is_enabled=s.get("isEnabled", True),
                scope_type=s.get("type", "User"),
            )
            for s in raw_scopes
        ]

        # Extract sponsor and owner IDs
        sponsor_ids = [
            sp["id"] if isinstance(sp, dict) else str(sp)
            for sp in data.get("sponsors", [])
        ]
        owner_ids = [
            ow["id"] if isinstance(ow, dict) else str(ow)
            for ow in data.get("owners", [])
        ]

        # Parse created datetime
        created_raw = data.get("createdDateTime")
        if created_raw:
            try:
                created_at = datetime.fromisoformat(
                    created_raw.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                created_at = datetime.now(timezone.utc)
        else:
            created_at = datetime.now(timezone.utc)

        identifier_uris = data.get("identifierUris", [""])
        identifier_uri = identifier_uris[0] if identifier_uris else ""

        return cls(
            id=data["id"],
            app_id=data["appId"],
            display_name=data["displayName"],
            description=data.get("description", ""),
            credential_type=credential_type,
            tenant_id=tenant_id,
            identifier_uri=identifier_uri,
            oauth2_scopes=oauth2_scopes,
            sponsor_ids=sponsor_ids,
            owner_ids=owner_ids,
            created_at=created_at,
            service_management_reference=data.get("serviceManagementReference", "") or "",
            created_by_app_id=data.get("createdByAppId", "") or "",
        )

    def to_graph_request(self) -> dict:
        """Serialize this Blueprint into a dict suitable for POST/PATCH to Graph API."""
        return {
            "displayName": self.display_name,
            "description": self.description,
            "signInAudience": "AzureADMyOrg",
            "identifierUris": [self.identifier_uri],
            "api": {
                "oauth2PermissionScopes": [
                    {
                        "id": s.id,
                        "value": s.value,
                        "adminConsentDisplayName": s.admin_consent_display_name,
                        "adminConsentDescription": s.admin_consent_description,
                        "isEnabled": s.is_enabled,
                        "type": s.scope_type,
                    }
                    for s in self.oauth2_scopes
                ]
            },
        }


@dataclass
class BlueprintPrincipal:
    blueprint_id: str
    tenant_id: str
    display_name: str
    app_id: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    service_principal_type: str = "Application"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # OAuth2PermissionGrant records (required for delegated permission inheritance)
    oauth2_permission_grants: List[str] = field(default_factory=list)
    # Graph API endpoint used for creation
    graph_endpoint: str = "/beta/serviceprincipals/graph.agentIdentityBlueprintPrincipal"

    @classmethod
    def from_graph_response(cls, data: dict, blueprint_id: str) -> BlueprintPrincipal:
        """Deserialize a BlueprintPrincipal from a Graph API response dict."""
        # Parse OAuth2 permission grants
        raw_grants = data.get("oauth2PermissionGrants", [])
        oauth2_permission_grants = [
            g["id"] if isinstance(g, dict) else str(g)
            for g in raw_grants
        ]

        # Parse created datetime
        created_raw = data.get("createdDateTime")
        if created_raw:
            try:
                created_at = datetime.fromisoformat(
                    created_raw.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                created_at = datetime.now(timezone.utc)
        else:
            created_at = datetime.now(timezone.utc)

        return cls(
            id=data["id"],
            blueprint_id=blueprint_id,
            app_id=data["appId"],
            display_name=data["displayName"],
            tenant_id=data.get("appOwnerOrganizationId", ""),
            service_principal_type=data.get("servicePrincipalType", "Application"),
            oauth2_permission_grants=oauth2_permission_grants,
            created_at=created_at,
        )
