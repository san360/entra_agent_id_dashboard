"""Data models for Agent Identities and Agent Users.

References:
- https://medium.com/gitconnected/creating-entra-agent-id-blueprints-and-identities-with-powershell-and-net-fba03825e74c
- https://derkvanderwoude.medium.com/from-blueprint-to-token-how-entra-agent-identity-inheritance-really-works-fed114abe281
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List


@dataclass
class AgentIdentity:
    display_name: str
    blueprint_id: str
    principal_id: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    client_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    has_user_account: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Sponsorship (enforced by Entra Agent ID — every identity needs an accountable owner)
    sponsor_ids: List[str] = field(default_factory=list)
    # The agentIdentityBlueprintId link — how the Graph API tracks parent-child
    agent_identity_blueprint_id: str = ""
    # Note: agent identity's service principal shows NO permissions in Azure portal.
    # This is BY DESIGN — permissions are dynamically merged at token issuance time
    # from the parent blueprint's inheritablePermissions + OAuth2PermissionGrant.

    def __post_init__(self):
        if not self.agent_identity_blueprint_id:
            self.agent_identity_blueprint_id = self.blueprint_id
        if not self.sponsor_ids:
            self.sponsor_ids = ["00000000-0000-0000-0000-000000000099"]

    @classmethod
    def from_graph_response(cls, data: dict) -> AgentIdentity:
        """Deserialize an AgentIdentity from a Graph API response dict.

        Handles both the /servicePrincipals/microsoft.graph.agentIdentity
        response shape (agentAppId, agentIdentityBlueprintId) and the legacy
        /applications/{id}/agentIdentities shape.
        """
        client_id = (
            data.get("agentAppId")
            or data.get("appId")
            or data.get("clientId")
            or ""
        )
        blueprint_id = data.get("agentIdentityBlueprintId", "")

        sponsor_ids = [
            sp["id"] if isinstance(sp, dict) else str(sp)
            for sp in data.get("sponsors", [])
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
            client_id=client_id,
            display_name=data["displayName"],
            blueprint_id=blueprint_id,
            agent_identity_blueprint_id=blueprint_id,
            # For agentIdentity SPs the id is the SP id itself
            principal_id=data.get("servicePrincipalId") or data["id"],
            has_user_account=data.get("hasUserAccount", False),
            sponsor_ids=sponsor_ids,
            created_at=created_at,
        )


@dataclass
class AgentUser:
    agent_identity_id: str
    user_principal_name: str
    display_name: str
    mail: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_graph_response(cls, data: dict) -> AgentUser:
        """Deserialize an AgentUser from a Graph API response dict."""
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
            agent_identity_id=data.get("identityParentId", ""),
            user_principal_name=data.get("userPrincipalName", ""),
            display_name=data.get("displayName", ""),
            mail=data.get("mail", ""),
            created_at=created_at,
        )
