"""Service for managing Blueprints, Principals, Agent Identities, and Agent Users.

All operations call the Microsoft Graph API (beta) through GraphClient
and cache read results in SessionCache.
"""

from __future__ import annotations

import logging
import re
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

from config.azure_config import AzureConfig
from services.graph_client import GraphClient, GraphAPIError
from services.cache import SessionCache
from models.blueprint import Blueprint, BlueprintPrincipal, CredentialType
from models.identity import AgentIdentity, AgentUser


class BlueprintService:

    _RESOURCE_PATH_RE = re.compile(
        r"/subscriptions/(?P<sub>[^/]+)"
        r"/resourcegroups/(?P<rg>[^/]+)"
        r"/providers/Microsoft\.CognitiveServices"
        r"/accounts/(?P<account>[^/]+)"
        r"/projects/(?P<project>[^/]+)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        graph: GraphClient,
        cache: SessionCache,
        config: AzureConfig,
    ):
        self._graph = graph
        self._cache = cache
        self._config = config

    # ── Blueprints ─────────────────────────────────────────────────────────

    def list_blueprints(self) -> List[Blueprint]:
        cached = self._cache.get("blueprints_list")
        if cached is not None:
            return cached

        data = self._graph.get_all(
            "/applications/microsoft.graph.agentIdentityBlueprint",
        )
        blueprints = [
            Blueprint.from_graph_response(d, self._config.tenant_id) for d in data
        ]
        # Enrich with Foundry project info from owner SPs
        self._resolve_foundry_info(blueprints)
        self._cache.set("blueprints_list", blueprints)
        return blueprints

    def get_blueprint(self, blueprint_id: str) -> Optional[Blueprint]:
        cached = self._cache.get(f"blueprint_{blueprint_id}")
        if cached is not None:
            return cached

        try:
            data = self._graph.get(f"/applications/{blueprint_id}")
        except GraphAPIError:
            return None

        bp = Blueprint.from_graph_response(data, self._config.tenant_id)
        self._cache.set(f"blueprint_{blueprint_id}", bp)
        return bp

    def _resolve_foundry_info(self, blueprints: List[Blueprint]) -> None:
        """Enrich blueprints with Foundry project metadata from owner SPs.

        For each blueprint, check /applications/{id}/owners for a
        servicePrincipal whose alternativeNames contains an ARM resource
        path like:
          /subscriptions/.../providers/Microsoft.CognitiveServices/accounts/.../projects/...

        If found, populate the foundry_* fields on the blueprint.
        If no direct owner match, try to match via serviceManagementReference
        grouping (all blueprints sharing the same SMR belong to the same
        Foundry project context).
        """
        smr_to_foundry: dict = {}  # serviceManagementReference → foundry info

        for bp in blueprints:
            try:
                owners = self._graph.get_all(f"/applications/{bp.id}/owners")
            except GraphAPIError:
                continue

            for owner in owners:
                if owner.get("@odata.type") != "#microsoft.graph.servicePrincipal":
                    continue
                for alt_name in owner.get("alternativeNames", []):
                    m = self._RESOURCE_PATH_RE.search(alt_name)
                    if m:
                        bp.foundry_resource_id = alt_name
                        bp.foundry_subscription_id = m.group("sub")
                        bp.foundry_resource_group = m.group("rg")
                        bp.foundry_account_name = m.group("account")
                        bp.foundry_project_name = m.group("project")
                        # Cache this for SMR-based fallback
                        if bp.service_management_reference:
                            smr_to_foundry[bp.service_management_reference] = {
                                "resource_id": alt_name,
                                "subscription_id": m.group("sub"),
                                "resource_group": m.group("rg"),
                                "account_name": m.group("account"),
                                "project_name": m.group("project"),
                            }
                        break
                if bp.foundry_resource_id:
                    break

        # Fallback: propagate Foundry info to blueprints sharing the same SMR
        for bp in blueprints:
            if bp.foundry_resource_id:
                continue
            if bp.service_management_reference in smr_to_foundry:
                info = smr_to_foundry[bp.service_management_reference]
                bp.foundry_resource_id = info["resource_id"]
                bp.foundry_subscription_id = info["subscription_id"]
                bp.foundry_resource_group = info["resource_group"]
                bp.foundry_account_name = info["account_name"]
                bp.foundry_project_name = info["project_name"]

    def create_blueprint(
        self,
        display_name: str,
        description: str,
        credential_type: CredentialType,
        tenant_id: str,
    ) -> Blueprint:
        # Get a user to act as sponsor (required by the Agent ID API)
        try:
            me = self._graph.get("/me")
            sponsor_url = f"https://graph.microsoft.com/beta/users/{me['id']}"
        except GraphAPIError:
            # App-only token: find a directory user to use as sponsor
            users_data = self._graph.get(
                "/users",
                params={"$top": "1", "$select": "id"},
            )
            user_list = users_data.get("value", [])
            if user_list:
                sponsor_url = f"https://graph.microsoft.com/beta/users/{user_list[0]['id']}"
            else:
                raise

        body = {
            "displayName": display_name,
            "description": description,
            "signInAudience": "AzureADMyOrg",
            "sponsors@odata.bind": [sponsor_url],
        }
        data = self._graph.post(
            "/applications/microsoft.graph.agentIdentityBlueprint", json_body=body
        )
        bp = Blueprint.from_graph_response(data, tenant_id)
        self._cache.set(f"blueprint_{bp.id}", bp)
        self._cache.invalidate("blueprints_list")
        # Auto-create a principal
        self.create_principal(bp.id)
        return bp

    def delete_blueprint(self, blueprint_id: str) -> None:
        # Cascade delete identities first, then the blueprint
        identities = self.get_identities_for_blueprint(blueprint_id)
        for identity in identities:
            self._delete_identity_cascade(identity.id)

        try:
            self._graph.delete(f"/applications/{blueprint_id}")
        except GraphAPIError:
            pass  # Best-effort deletion

        self._cache.invalidate("blueprints_list")
        self._cache.invalidate(f"blueprint_{blueprint_id}")
        self._cache.invalidate(f"principals_{blueprint_id}")
        self._cache.invalidate(f"identities_{blueprint_id}")

    # ── Blueprint Principals ───────────────────────────────────────────────

    def create_principal(
        self, blueprint_id: str, *, _max_retries: int = 5, _base_delay: float = 2.0
    ) -> BlueprintPrincipal:
        bp = self.get_blueprint(blueprint_id)
        if bp is None:
            raise ValueError(f"Blueprint {blueprint_id} not found")
        body = {
            "appId": bp.app_id,
        }

        last_error: Optional[GraphAPIError] = None
        for attempt in range(1, _max_retries + 1):
            try:
                data = self._graph.post(
                    "/servicePrincipals/microsoft.graph.agentIdentityBlueprintPrincipal",
                    json_body=body,
                )
                principal = BlueprintPrincipal.from_graph_response(data, blueprint_id)
                self._cache.invalidate(f"principals_{blueprint_id}")
                return principal
            except GraphAPIError as exc:
                last_error = exc
                # Replication delay: app not yet visible to SP endpoint
                if exc.status_code == 400 and "does not reference a valid application" in str(exc):
                    if attempt < _max_retries:
                        delay = _base_delay * attempt
                        logger.info(
                            "Blueprint SP creation attempt %d/%d failed (replication delay), "
                            "retrying in %.1fs...",
                            attempt, _max_retries, delay,
                        )
                        time.sleep(delay)
                        continue
                # Principal may already exist
                existing = self.get_principals_for_blueprint(blueprint_id)
                if existing:
                    return existing[0]
                raise

        # All retries exhausted
        raise last_error  # type: ignore[misc]

    def get_principals_for_blueprint(
        self, blueprint_id: str
    ) -> List[BlueprintPrincipal]:
        cached = self._cache.get(f"principals_{blueprint_id}")
        if cached is not None:
            return cached

        bp = self.get_blueprint(blueprint_id)
        if bp is None:
            return []

        data = self._graph.get_all(
            "/servicePrincipals",
            params={"$filter": f"appId eq '{bp.app_id}'"},
        )
        principals = [BlueprintPrincipal.from_graph_response(d, blueprint_id) for d in data]
        self._cache.set(f"principals_{blueprint_id}", principals)
        return principals

    # ── Agent Identities ──────────────────────────────────────────────────

    def create_agent_identity(
        self,
        blueprint_id: str,
        display_name: str,
        create_user_account: bool = False,
    ) -> AgentIdentity:
        body = {
            "displayName": display_name,
        }
        data = self._graph.post(
            f"/applications/{blueprint_id}/agentIdentities",
            json_body=body,
        )
        identity = AgentIdentity.from_graph_response(data)
        self._cache.invalidate(f"identities_{blueprint_id}")
        self._cache.invalidate("all_identities")

        if create_user_account:
            bp = self.get_blueprint(blueprint_id)
            safe_name = display_name.lower().replace(" ", "-")
            domain = bp.tenant_id if bp else self._config.tenant_id
            self._create_agent_user(
                agent_identity_id=identity.id,
                display_name=f"{display_name} User",
                upn=f"agent-{safe_name}@{domain}",
            )

        return identity

    def get_identities_for_blueprint(
        self, blueprint_id: str
    ) -> List[AgentIdentity]:
        cached = self._cache.get(f"identities_{blueprint_id}")
        if cached is not None:
            return cached

        all_ids = self.list_identities()
        identities = [
            ai for ai in all_ids if ai.blueprint_id == blueprint_id
        ]
        self._cache.set(f"identities_{blueprint_id}", identities)
        return identities

    def get_identity(self, identity_id: str) -> Optional[AgentIdentity]:
        cached = self._cache.get(f"identity_{identity_id}")
        if cached is not None:
            return cached

        try:
            data = self._graph.get(
                f"/servicePrincipals/microsoft.graph.agentIdentity/{identity_id}"
            )
        except GraphAPIError:
            return None

        identity = AgentIdentity.from_graph_response(data)
        self._cache.set(f"identity_{identity_id}", identity)
        return identity

    def list_identities(self) -> List[AgentIdentity]:
        cached = self._cache.get("all_identities")
        if cached is not None:
            return cached

        try:
            data = self._graph.get_all(
                "/servicePrincipals/microsoft.graph.agentIdentity"
            )
            identities = [AgentIdentity.from_graph_response(d) for d in data]
        except GraphAPIError:
            identities = []

        self._cache.set("all_identities", identities)
        return identities

    # ── Agent Users ────────────────────────────────────────────────────────

    def _create_agent_user(
        self,
        agent_identity_id: str,
        display_name: str,
        upn: str,
    ) -> AgentUser:
        body = {
            "@odata.type": "#microsoft.graph.agentUser",
            "displayName": display_name,
            "userPrincipalName": upn,
            "mailNickname": upn.split("@")[0],
            "accountEnabled": True,
            "agentIdentityId": agent_identity_id,
        }
        data = self._graph.post("/users", json_body=body)
        user = AgentUser.from_graph_response(data)
        self._cache.invalidate(f"agent_user_{agent_identity_id}")
        return user

    def get_agent_user(self, agent_identity_id: str) -> Optional[AgentUser]:
        cached = self._cache.get(f"agent_user_{agent_identity_id}")
        if cached is not None:
            return cached

        try:
            data = self._graph.get_all(
                "/users",
                params={
                    "$filter": f"agentIdentityId eq '{agent_identity_id}'",
                },
            )
        except GraphAPIError:
            return None

        if not data:
            return None

        user = AgentUser.from_graph_response(data[0])
        self._cache.set(f"agent_user_{agent_identity_id}", user)
        return user

    # ── Internal ───────────────────────────────────────────────────────────

    def _delete_identity_cascade(self, identity_id: str) -> None:
        user = self.get_agent_user(identity_id)
        if user is not None:
            try:
                self._graph.delete(f"/users/{user.id}")
            except GraphAPIError:
                pass
            self._cache.invalidate(f"agent_user_{identity_id}")

        try:
            self._graph.delete(f"/servicePrincipals/{identity_id}")
        except GraphAPIError:
            pass

        self._cache.invalidate(f"identity_{identity_id}")
        self._cache.invalidate("all_identities")
