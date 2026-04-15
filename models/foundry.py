"""Data models for Azure AI Foundry resource, project, and agent associations.

Hierarchy:
  FoundryResource (AI Services account)
    └── FoundryProject (per-project, linked to a Blueprint)
          └── FoundryAgent (per published agent, linked to an AgentIdentity)

Blueprints operate at the PROJECT level, not the resource level.
One Foundry resource can contain many projects, each with its own set of
blueprints (project blueprint, manager blueprint, per-agent blueprints).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


# ── Business Domains ─────────────────────────────────────────────────────────

BUSINESS_DOMAINS = [
    "HR",
    "Finance",
    "Customer Service",
    "IT Operations",
    "Sales",
    "Marketing",
    "Legal",
    "Engineering",
    "General",
]


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
    """An Azure AI Foundry project that hosts AI agents.

    Each project is linked to ONE blueprint (the project-level blueprint).
    Foundry auto-creates: Project BP → Manager BP → Per-Agent BPs.
    In the "Blueprint per Business Domain" pattern, all projects in the
    same domain share the same domain-level blueprint.
    """
    name: str
    blueprint_id: str  # Links to Blueprint.id (domain blueprint)
    resource_id: str = ""  # Links to FoundryResource.id
    resource_group: str = ""
    region: str = "eastus"
    environment: str = "dev"  # dev | test | prod
    business_domain: str = "General"
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
    Blueprints are scoped at the PROJECT level, not here.
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
