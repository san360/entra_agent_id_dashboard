"""Service for managing Foundry resources, projects, and agent associations.

Hierarchy:
  FoundryResource (AI Services account)  — 1 per subscription/region
    └── FoundryProject                    — N per resource
          └── FoundryAgent                — N per project, each linked to an AgentIdentity

Foundry projects and Agent Identity Blueprints are independent systems.
Blueprints live in Entra ID (Graph API); Foundry projects live in Azure ARM.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional

from models.foundry import FoundryResource, FoundryProject, FoundryAgent

logger = logging.getLogger(__name__)


class FoundryService:
    def __init__(self, store: Optional[dict] = None, arm_client=None):
        self._store = store
        self._arm = arm_client  # Optional ARMClient for real Azure resource discovery

    # ── Foundry Resources ─────────────────────────────────────────────────

    def list_resources(self) -> List[FoundryResource]:
        return list(self._store.get("foundry_resources", {}).values())

    def get_resource(self, resource_id: str) -> Optional[FoundryResource]:
        return self._store.get("foundry_resources", {}).get(resource_id)

    def create_resource(
        self,
        name: str,
        region: str = "eastus",
        resource_group: str = "",
        subscription_id: str = "",
    ) -> FoundryResource:
        rg = resource_group or f"rg-{name}"

        # If ARM client and subscription are available, provision in Azure
        if self._arm and subscription_id:
            try:
                self._arm.ensure_resource_group(subscription_id, rg, region)
                result = self._arm.create_cognitive_account(
                    subscription_id=subscription_id,
                    resource_group=rg,
                    account_name=name,
                    location=region,
                )
                logger.info("Created AI Services account '%s' in Azure", name)
            except Exception as exc:
                logger.error("ARM resource creation failed: %s", exc)
                raise

        resource = FoundryResource(
            name=name,
            region=region,
            resource_group=rg,
            subscription_id=subscription_id,
        )
        self._store.setdefault("foundry_resources", {})[resource.id] = resource
        return resource

    def delete_resource(self, resource_id: str) -> None:
        # Cascade: delete all projects under this resource
        for proj in self.get_projects_for_resource(resource_id):
            self.delete_project(proj.id)
        self._store.get("foundry_resources", {}).pop(resource_id, None)

    def get_projects_for_resource(self, resource_id: str) -> List[FoundryProject]:
        return [
            p for p in self._store.get("foundry_projects", {}).values()
            if p.resource_id == resource_id
        ]

    # ── Foundry Projects ──────────────────────────────────────────────────

    def list_projects(self) -> List[FoundryProject]:
        return list(self._store.get("foundry_projects", {}).values())

    def get_project(self, project_id: str) -> Optional[FoundryProject]:
        return self._store.get("foundry_projects", {}).get(project_id)

    def create_project(
        self,
        name: str,
        resource_id: str = "",
        region: str = "eastus",
        resource_group: str = "",
    ) -> FoundryProject:
        # If linked to an existing Foundry resource, create the project in Azure via ARM
        parent_resource = self.get_resource(resource_id) if resource_id else None
        endpoint = ""

        if self._arm and parent_resource and parent_resource.subscription_id:
            try:
                # Ensure the parent account has allowProjectManagement enabled
                self._arm.create_cognitive_account(
                    subscription_id=parent_resource.subscription_id,
                    resource_group=parent_resource.resource_group,
                    account_name=parent_resource.name,
                    location=parent_resource.region,
                )
                result = self._arm.create_foundry_project(
                    subscription_id=parent_resource.subscription_id,
                    resource_group=parent_resource.resource_group,
                    account_name=parent_resource.name,
                    project_name=name,
                    location=parent_resource.region,
                )
                endpoint = (
                    result.get("properties", {})
                    .get("endpoints", {})
                    .get("AI Foundry API", "")
                )
                logger.info("Created Foundry project '%s' in Azure", name)
            except Exception as exc:
                logger.error("ARM project creation failed: %s", exc)
                raise

        project = FoundryProject(
            name=name,
            resource_id=resource_id,
            region=region,
            resource_group=resource_group or f"rg-{name}",
        )
        if endpoint:
            project.endpoint = endpoint
        if parent_resource and parent_resource.subscription_id:
            project.subscription_id = parent_resource.subscription_id
        self._store.setdefault("foundry_projects", {})[project.id] = project
        return project

    def delete_project(self, project_id: str) -> None:
        self._store.get("foundry_projects", {}).pop(project_id, None)

    # ── Foundry Agents ────────────────────────────────────────────────────

    def add_agent(
        self,
        project_id: str,
        name: str,
        agent_identity_id: str,
        model: str = "gpt-4o",
        description: str = "",
    ) -> Optional[FoundryAgent]:
        project = self.get_project(project_id)
        if not project:
            return None
        agent = FoundryAgent(
            name=name,
            agent_identity_id=agent_identity_id,
            model=model,
            description=description,
        )
        project.agents.append(agent)
        return agent

    def remove_agent(self, project_id: str, agent_id: str) -> None:
        project = self.get_project(project_id)
        if project:
            project.agents = [a for a in project.agents if a.id != agent_id]

    def get_agents_for_identity(self, agent_identity_id: str) -> List[FoundryAgent]:
        """Find all Foundry agents linked to a given agent identity."""
        result = []
        for project in self._store.get("foundry_projects", {}).values():
            for agent in project.agents:
                if agent.agent_identity_id == agent_identity_id:
                    result.append(agent)
        return result

    def get_project_for_agent(self, agent_id: str) -> Optional[FoundryProject]:
        """Find which project a Foundry agent belongs to."""
        for project in self._store.get("foundry_projects", {}).values():
            for agent in project.agents:
                if agent.id == agent_id:
                    return project
        return None

    # ── Azure Resource Discovery ──────────────────────────────────────────

    def discover_azure_resources(self) -> List[FoundryResource]:
        """Discover real Foundry resources (Cognitive Services accounts) from Azure.

        Merges Azure-discovered resources into the local store so they appear
        alongside manually created ones. Returns the full merged list.
        """
        if self._arm is None:
            return self.list_resources()

        try:
            subscriptions = self._arm.list_subscriptions()
        except Exception:
            logger.warning("Failed to list Azure subscriptions for resource discovery")
            return self.list_resources()

        discovered: List[FoundryResource] = []
        for sub in subscriptions:
            sub_id = sub.get("subscriptionId", "")
            if not sub_id:
                continue
            try:
                accounts = self._arm.list_cognitive_accounts(sub_id)
            except Exception:
                continue

            for acct in accounts:
                # Only include AI Services / OpenAI accounts (Foundry-capable)
                kind = acct.get("kind", "")
                if kind not in ("AIServices", "OpenAI", "CognitiveServices"):
                    continue

                name = acct.get("name", "")
                location = acct.get("location", "")
                # Parse RG from the resource ID
                arm_id = acct.get("id", "")
                rg = ""
                parts = arm_id.split("/")
                for i, p in enumerate(parts):
                    if p.lower() == "resourcegroups" and i + 1 < len(parts):
                        rg = parts[i + 1]
                        break

                resource = FoundryResource(
                    name=name,
                    resource_group=rg,
                    region=location,
                    subscription_id=sub_id,
                )

                # Check if already in local store (by name + subscription)
                existing = self._find_local_resource(name, sub_id)
                if existing:
                    resource.id = existing.id
                else:
                    self._store.setdefault("foundry_resources", {})[resource.id] = resource

                discovered.append(resource)

                # Also discover projects under this account
                self._discover_projects_for_account(sub_id, rg, name, resource.id)

        # Deduplicate: remove old entries with "account/project" full names
        # when a short-name entry for the same project+resource already exists
        self._dedup_projects()

        return self.list_resources()

    def _dedup_projects(self) -> None:
        """Remove duplicate project entries that differ only by name format.

        Keeps the short-name entry if available, otherwise the first entry.
        """
        projects = self._store.get("foundry_projects", {})
        # Group by (short_name, resource_id)
        groups: Dict[tuple, List[str]] = {}
        for pid, p in projects.items():
            short = p.name.split("/")[-1] if "/" in p.name else p.name
            key = (short, p.resource_id)
            groups.setdefault(key, []).append(pid)

        remove_ids = []
        for key, pids in groups.items():
            if len(pids) <= 1:
                continue
            # Prefer short name
            keep = None
            for pid in pids:
                if "/" not in projects[pid].name:
                    keep = pid
                    break
            if keep is None:
                keep = pids[0]
            for pid in pids:
                if pid != keep:
                    remove_ids.append(pid)
            # Normalize the kept entry's name to short form
            short_name = key[0]
            projects[keep].name = short_name

        for pid in remove_ids:
            projects.pop(pid, None)

    def _find_local_resource(self, name: str, subscription_id: str) -> Optional[FoundryResource]:
        """Find a local resource matching by name and subscription."""
        for r in self._store.get("foundry_resources", {}).values():
            if r.name == name and r.subscription_id == subscription_id:
                return r
        return None

    def _discover_projects_for_account(
        self, subscription_id: str, resource_group: str, account_name: str, resource_id: str
    ) -> None:
        """Discover projects under a Cognitive Services account and sync with local store."""
        if self._arm is None:
            return
        try:
            projects = self._arm.list_foundry_projects(subscription_id, resource_group, account_name)
        except Exception:
            return

        # Track short project names from Azure for stale detection
        azure_short_names: set = set()

        for proj in projects:
            raw_name = proj.get("name", "")
            location = proj.get("location", "")
            if not raw_name:
                continue

            # ARM returns "account/project" — extract the short name
            short_name = raw_name.split("/")[-1] if "/" in raw_name else raw_name
            azure_short_names.add(short_name)

            # Check if already in local store (match both short and full names)
            existing = self._find_local_project_fuzzy(short_name, raw_name, resource_id)
            if existing:
                # Update the existing entry with Azure metadata if missing
                if not existing.subscription_id or existing.subscription_id.startswith("0000"):
                    existing.subscription_id = subscription_id
                if not existing.resource_group or existing.resource_group.startswith("rg-"):
                    existing.resource_group = resource_group
                if existing.region != location:
                    existing.region = location
                continue

            project = FoundryProject(
                name=short_name,
                resource_id=resource_id,
                resource_group=resource_group,
                region=location,
                subscription_id=subscription_id,
            )
            self._store.setdefault("foundry_projects", {})[project.id] = project

        # Remove local projects that no longer exist in Azure
        stale_ids = []
        for pid, p in self._store.get("foundry_projects", {}).items():
            if p.resource_id != resource_id:
                continue
            p_short = p.name.split("/")[-1] if "/" in p.name else p.name
            if p_short not in azure_short_names:
                stale_ids.append(pid)
        for pid in stale_ids:
            self._store["foundry_projects"].pop(pid, None)

    def _find_local_project_fuzzy(
        self, short_name: str, full_name: str, resource_id: str
    ) -> Optional[FoundryProject]:
        """Find a local project matching by short or full name and parent resource."""
        for p in self._store.get("foundry_projects", {}).values():
            if p.resource_id != resource_id:
                continue
            p_short = p.name.split("/")[-1] if "/" in p.name else p.name
            if p_short == short_name or p.name == full_name:
                # Normalize name to short form
                if "/" in p.name:
                    p.name = p_short
                return p
        return None
