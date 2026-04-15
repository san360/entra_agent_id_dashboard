"""Service for managing Foundry resources, projects, and agent associations (local state).

Hierarchy:
  FoundryResource (AI Services account)  — 1 per subscription/region
    └── FoundryProject                    — N per resource, each linked to a Blueprint
          └── FoundryAgent                — N per project, each linked to an AgentIdentity

Blueprints are scoped at the PROJECT level.
In the 'Blueprint per Business Domain' pattern, multiple projects in the same
domain share a single domain-level blueprint.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Dict, List, Optional

from models.foundry import FoundryResource, FoundryProject, FoundryAgent

logger = logging.getLogger(__name__)

# File to persist project ↔ blueprint linkages across session restarts
_LINKAGE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".foundry_linkages.json")


class FoundryService:
    def __init__(self, store: Optional[dict] = None, arm_client=None):
        self._store = store
        self._arm = arm_client  # Optional ARMClient for real Azure resource discovery

    # ── Linkage Persistence ───────────────────────────────────────────────

    def _load_linkages(self) -> Dict[str, dict]:
        """Load persisted project → blueprint/domain linkages from disk."""
        try:
            with open(_LINKAGE_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_linkages(self) -> None:
        """Persist current project → blueprint/domain linkages to disk."""
        linkages = {}
        for p in self._store.get("foundry_projects", {}).values():
            if p.blueprint_id:
                linkages[p.name] = {
                    "blueprint_id": p.blueprint_id,
                    "business_domain": p.business_domain,
                    "environment": p.environment,
                }
        try:
            with open(_LINKAGE_FILE, "w") as f:
                json.dump(linkages, f, indent=2)
        except OSError:
            logger.warning("Failed to persist linkage file")

    def _apply_linkages(self) -> None:
        """Restore persisted blueprint linkages to discovered projects."""
        linkages = self._load_linkages()
        if not linkages:
            return
        for p in self._store.get("foundry_projects", {}).values():
            short_name = p.name.split("/")[-1] if "/" in p.name else p.name
            info = linkages.get(short_name)
            if info and not p.blueprint_id:
                p.blueprint_id = info["blueprint_id"]
                if info.get("business_domain"):
                    p.business_domain = info["business_domain"]
                if info.get("environment"):
                    p.environment = info["environment"]

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
        resource = FoundryResource(
            name=name,
            region=region,
            resource_group=resource_group or f"rg-{name}",
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

    def get_projects_for_blueprint(self, blueprint_id: str) -> List[FoundryProject]:
        return [
            p for p in self._store.get("foundry_projects", {}).values()
            if p.blueprint_id == blueprint_id
        ]

    def get_projects_by_domain(self, domain: str) -> List[FoundryProject]:
        return [
            p for p in self._store.get("foundry_projects", {}).values()
            if p.business_domain == domain
        ]

    def get_projects_by_environment(self, environment: str) -> List[FoundryProject]:
        return [
            p for p in self._store.get("foundry_projects", {}).values()
            if p.environment == environment
        ]

    def create_project(
        self,
        name: str,
        blueprint_id: str,
        resource_id: str = "",
        region: str = "eastus",
        resource_group: str = "",
        environment: str = "dev",
        business_domain: str = "General",
    ) -> FoundryProject:
        # If linked to an existing Foundry resource, create the project in Azure via ARM
        parent_resource = self.get_resource(resource_id) if resource_id else None
        arm_created = False
        endpoint = ""

        if self._arm and parent_resource and parent_resource.subscription_id:
            try:
                result = self._arm.create_foundry_project(
                    subscription_id=parent_resource.subscription_id,
                    resource_group=parent_resource.resource_group,
                    account_name=parent_resource.name,
                    project_name=name,
                    location=parent_resource.region,
                    description=f"{business_domain} {environment} project",
                )
                arm_created = True
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
            blueprint_id=blueprint_id,
            resource_id=resource_id,
            region=region,
            resource_group=resource_group or f"rg-{name}",
            environment=environment,
            business_domain=business_domain,
        )
        if endpoint:
            project.endpoint = endpoint
        if parent_resource and parent_resource.subscription_id:
            project.subscription_id = parent_resource.subscription_id
        self._store.setdefault("foundry_projects", {})[project.id] = project
        self._save_linkages()
        return project

    def delete_project(self, project_id: str) -> None:
        self._store.get("foundry_projects", {}).pop(project_id, None)
        self._save_linkages()

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

    # ── Domain Summary ────────────────────────────────────────────────────

    def get_domain_summary(self) -> Dict[str, dict]:
        """Summarize projects, agents, and environments per business domain."""
        summary: Dict[str, dict] = {}
        for project in self._store.get("foundry_projects", {}).values():
            domain = project.business_domain
            if domain not in summary:
                summary[domain] = {
                    "projects": [],
                    "environments": set(),
                    "agent_count": 0,
                    "blueprint_ids": set(),
                }
            summary[domain]["projects"].append(project)
            summary[domain]["environments"].add(project.environment)
            summary[domain]["agent_count"] += len(project.agents)
            summary[domain]["blueprint_ids"].add(project.blueprint_id)
        return summary

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

        # Restore persisted blueprint linkages to discovered projects
        self._apply_linkages()

        return self.list_resources()

    def _dedup_projects(self) -> None:
        """Remove duplicate project entries that differ only by name format.

        Keeps the entry with a blueprint_id (manually linked). If neither has
        one, keeps the short-name entry.
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
            # Keep the one with blueprint_id; otherwise keep first short-name entry
            keep = None
            for pid in pids:
                if projects[pid].blueprint_id:
                    keep = pid
                    break
            if keep is None:
                # Prefer short name
                for pid in pids:
                    if "/" not in projects[pid].name:
                        keep = pid
                        break
            if keep is None:
                keep = pids[0]
            for pid in pids:
                if pid != keep:
                    # Merge blueprint_id if the removed entry had one
                    if projects[pid].blueprint_id and not projects[keep].blueprint_id:
                        projects[keep].blueprint_id = projects[pid].blueprint_id
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
        """Discover projects under a Cognitive Services account and sync with local store.

        Adds new projects from Azure and removes local projects that no longer
        exist in Azure (unless they have a blueprint_id, meaning they were
        manually linked and should be preserved).
        """
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
                blueprint_id="",  # Not linked to a blueprint yet
                resource_id=resource_id,
                resource_group=resource_group,
                region=location,
                subscription_id=subscription_id,
            )
            self._store.setdefault("foundry_projects", {})[project.id] = project

        # Remove local projects that no longer exist in Azure
        # (only if they were auto-discovered, i.e. no blueprint_id set)
        stale_ids = []
        for pid, p in self._store.get("foundry_projects", {}).items():
            if p.resource_id != resource_id:
                continue
            p_short = p.name.split("/")[-1] if "/" in p.name else p.name
            if p_short not in azure_short_names:
                if not p.blueprint_id:
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
