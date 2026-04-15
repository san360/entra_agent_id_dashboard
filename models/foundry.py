"""Data models for Azure AI Foundry resource, project, and agent associations.

Hierarchy:
  FoundryResource (AI Services account)
    └── FoundryProject (per-project)
          └── FoundryAgent (per published agent, linked to an AgentIdentity)

Foundry projects and Agent Identity Blueprints are independent systems.
Blueprints live in Entra ID (Graph API) while Foundry projects live in
Azure ARM. There is no direct relationship between them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class FoundryAgent:
    """An AI agent deployed within a Foundry project, linked to an Agent Identity."""
    name: str
    agent_identity_id: str  # Links to AgentIdentity.id
    model: str = "gpt-4o"
    status: str = "active"  # active | inactive | provisioning
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FoundryProject:
    """An Azure AI Foundry project that hosts AI agents."""
    name: str
    resource_id: str = ""  # Links to FoundryResource.id
    resource_group: str = ""
    region: str = "eastus"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    subscription_id: str = ""
    endpoint: str = ""
    agents: List[FoundryAgent] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if not self.endpoint:
            self.endpoint = f"https://{self.name}.services.ai.azure.com"
        if not self.resource_group:
            self.resource_group = f"rg-{self.name}"
        if not self.subscription_id:
            self.subscription_id = "00000000-0000-0000-0000-000000000000"

    @property
    def arm_resource_path(self) -> str:
        """Construct the ARM resource path for this project."""
        return (
            f"/subscriptions/{self.subscription_id}"
            f"/resourcegroups/{self.resource_group}"
            f"/providers/Microsoft.CognitiveServices"
            f"/accounts/{self.resource_id or self.name}"
            f"/projects/{self.name}"
        )


@dataclass
class FoundryResource:
    """An Azure AI Services / Cognitive Services account (the parent of Foundry projects).

    One FoundryResource can host MULTIPLE FoundryProjects.
    """
    name: str
    resource_group: str = ""
    region: str = "eastus"
    subscription_id: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if not self.resource_group:
            self.resource_group = f"rg-{self.name}"
        if not self.subscription_id:
            self.subscription_id = "00000000-0000-0000-0000-000000000000"
