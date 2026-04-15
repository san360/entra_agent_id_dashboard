"""Service for managing permissions: catalog, inheritable, direct, effective.

References:
- Article 2: https://derkvanderwoude.medium.com/from-blueprint-to-token-how-entra-agent-identity-inheritance-really-works-fed114abe281

Three inheritance categories:
1. Protocol Properties (always inherited)
2. Delegated Permissions (conditionally inherited)
3. NOT Inherited (direct assignment only)
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from config.azure_config import AzureConfig
from services.graph_client import GraphClient, GraphAPIError
from services.cache import SessionCache
from models.permission import (
    Permission,
    PermissionScope,
    InheritablePermission,
    AppRoleAssignment,
    EffectivePermissions,
)

_GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"

_CATALOG_TTL = 1800
_SP_TTL = 1800
_DEFAULT_TTL = 300


class PermissionService:
    def __init__(
        self,
        graph: GraphClient,
        cache: SessionCache,
        config: AzureConfig,
    ):
        self._graph = graph
        self._cache = cache
        self._config = config

    # ── Internal helpers ──────────────────────────────────────────────────

    def _get_graph_sp_id(self) -> str:
        cached = self._cache.get("graph_sp_id")
        if cached is not None:
            return cached

        data = self._graph.get(
            "/servicePrincipals",
            params={
                "$filter": f"appId eq '{_GRAPH_APP_ID}'",
                "$select": "id",
            },
        )
        sp_id = data["value"][0]["id"]
        self._cache.set("graph_sp_id", sp_id, ttl=_SP_TTL)
        return sp_id

    def _get_agent_sp_id(self, agent_identity_id: str) -> str:
        cache_key = f"sp_for_{agent_identity_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        data = self._graph.get(
            "/servicePrincipals",
            params={
                "$filter": f"appId eq '{agent_identity_id}'",
                "$select": "id",
            },
        )
        values = data.get("value", [])
        sp_id = values[0]["id"] if values else agent_identity_id

        self._cache.set(cache_key, sp_id, ttl=_SP_TTL)
        return sp_id

    # ── Permission Catalog ────────────────────────────────────────────────

    def get_permission_catalog(self) -> List[Permission]:
        cached = self._cache.get("permission_catalog")
        if cached is not None:
            return cached

        data = self._graph.get(
            "/servicePrincipals",
            params={
                "$filter": f"appId eq '{_GRAPH_APP_ID}'",
                "$select": "appRoles,oauth2PermissionScopes,displayName",
            },
        )
        sp = data["value"][0]
        resource_name = sp.get("displayName", "Microsoft Graph")

        permissions: List[Permission] = []

        for role in sp.get("appRoles", []):
            permissions.append(
                Permission.from_graph_app_role(role, _GRAPH_APP_ID, resource_name)
            )

        for scope in sp.get("oauth2PermissionScopes", []):
            permissions.append(
                Permission.from_graph_oauth2_scope(scope, _GRAPH_APP_ID, resource_name)
            )

        self._cache.set("permission_catalog", permissions, ttl=_CATALOG_TTL)
        return permissions

    def get_permission_by_id(self, permission_id: str) -> Optional[Permission]:
        for p in self.get_permission_catalog():
            if p.id == permission_id:
                return p
        return None

    def get_permission_by_name(self, name: str) -> Optional[Permission]:
        for p in self.get_permission_catalog():
            if p.name == name:
                return p
        return None

    # ── Inheritable Permissions (Blueprint-level) ─────────────────────────

    def assign_inheritable(
        self, blueprint_id: str, permission_id: str, admin_consent: bool = True
    ) -> InheritablePermission:
        app_data = self._graph.get(
            f"/applications/{blueprint_id}",
            params={"$select": "inheritablePermissions"},
        )
        current = app_data.get("inheritablePermissions", [])

        for entry in current:
            if entry.get("permissionId") == permission_id:
                return InheritablePermission(
                    id=entry.get("id", str(uuid.uuid4())),
                    blueprint_id=blueprint_id,
                    permission_id=permission_id,
                    admin_consented=admin_consent,
                )

        new_entry = {
            "permissionId": permission_id,
            "isEnabled": True,
        }
        current.append(new_entry)
        self._graph.patch(
            f"/applications/{blueprint_id}",
            json_body={"inheritablePermissions": current},
        )

        if admin_consent:
            perm = self.get_permission_by_id(permission_id)
            scope_value = perm.name if perm else permission_id
            self._graph.post(
                "/oauth2PermissionGrants",
                json_body={
                    "clientId": blueprint_id,
                    "consentType": "AllPrincipals",
                    "resourceId": self._get_graph_sp_id(),
                    "scope": scope_value,
                },
            )

        self._cache.invalidate(f"inheritable_{blueprint_id}")

        return InheritablePermission(
            id=str(uuid.uuid4()),
            blueprint_id=blueprint_id,
            permission_id=permission_id,
            admin_consented=admin_consent,
        )

    def remove_inheritable_by_perm(
        self, blueprint_id: str, permission_id: str
    ) -> None:
        app_data = self._graph.get(
            f"/applications/{blueprint_id}",
            params={"$select": "inheritablePermissions"},
        )
        current = app_data.get("inheritablePermissions", [])
        updated = [
            entry for entry in current
            if entry.get("permissionId") != permission_id
        ]
        self._graph.patch(
            f"/applications/{blueprint_id}",
            json_body={"inheritablePermissions": updated},
        )
        self._cache.invalidate(f"inheritable_{blueprint_id}")

    def get_inheritable_for_blueprint(
        self, blueprint_id: str
    ) -> List[InheritablePermission]:
        cache_key = f"inheritable_{blueprint_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            app_data = self._graph.get(
                f"/applications/{blueprint_id}",
                params={"$select": "inheritablePermissions"},
            )
        except GraphAPIError:
            return []
        raw_list = app_data.get("inheritablePermissions", [])

        results: List[InheritablePermission] = []
        for entry in raw_list:
            ip = InheritablePermission(
                id=entry.get("id", str(uuid.uuid4())),
                blueprint_id=blueprint_id,
                permission_id=entry["permissionId"],
                admin_consented=entry.get("isEnabled", True),
            )
            results.append(ip)

        self._cache.set(cache_key, results, ttl=_DEFAULT_TTL)
        return results

    def get_inherited_permissions(self, blueprint_id: str) -> List[Permission]:
        ips = self.get_inheritable_for_blueprint(blueprint_id)
        result = []
        for ip in ips:
            if not ip.admin_consented:
                continue
            perm = self.get_permission_by_id(ip.permission_id)
            if perm:
                result.append(perm)
        return result

    # ── Direct Permissions (Agent Identity-level) ─────────────────────────

    def assign_direct(
        self, agent_identity_id: str, permission_id: str
    ) -> AppRoleAssignment:
        sp_id = self._get_agent_sp_id(agent_identity_id)
        resource_id = self._get_graph_sp_id()

        result = self._graph.post(
            f"/servicePrincipals/{sp_id}/appRoleAssignments",
            json_body={
                "principalId": sp_id,
                "resourceId": resource_id,
                "appRoleId": permission_id,
            },
        )

        self._cache.invalidate(f"direct_{agent_identity_id}")

        perm = self.get_permission_by_id(permission_id)
        return AppRoleAssignment(
            id=result.get("id", str(uuid.uuid4())),
            agent_identity_id=agent_identity_id,
            permission_id=permission_id,
            resource_display_name=perm.resource_app_display_name if perm else "Microsoft Graph",
        )

    def remove_direct_by_perm(
        self, agent_identity_id: str, permission_id: str
    ) -> None:
        sp_id = self._get_agent_sp_id(agent_identity_id)
        assignments = self._graph.get_all(
            f"/servicePrincipals/{sp_id}/appRoleAssignments",
        )
        for assignment in assignments:
            if assignment.get("appRoleId") == permission_id:
                self._graph.delete(
                    f"/servicePrincipals/{sp_id}/appRoleAssignments/{assignment['id']}"
                )
                break

        self._cache.invalidate(f"direct_{agent_identity_id}")

    def get_direct_assignments(
        self, agent_identity_id: str
    ) -> List[AppRoleAssignment]:
        cache_key = f"direct_{agent_identity_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        sp_id = self._get_agent_sp_id(agent_identity_id)
        raw = self._graph.get_all(
            f"/servicePrincipals/{sp_id}/appRoleAssignments",
        )

        results: List[AppRoleAssignment] = []
        for entry in raw:
            ar = AppRoleAssignment(
                id=entry["id"],
                agent_identity_id=agent_identity_id,
                permission_id=entry.get("appRoleId", ""),
                resource_display_name=entry.get("resourceDisplayName", "Microsoft Graph"),
            )
            results.append(ar)

        self._cache.set(cache_key, results, ttl=_DEFAULT_TTL)
        return results

    def get_direct_permissions(self, agent_identity_id: str) -> List[Permission]:
        assignments = self.get_direct_assignments(agent_identity_id)
        result = []
        for ar in assignments:
            perm = self.get_permission_by_id(ar.permission_id)
            if perm:
                result.append(perm)
        return result

    # ── Effective Permissions ──────────────────────────────────────────────

    def get_effective(
        self, agent_identity_id: str, blueprint_id: str
    ) -> EffectivePermissions:
        inherited = self.get_inherited_permissions(blueprint_id)
        direct = self.get_direct_permissions(agent_identity_id)
        return EffectivePermissions(inherited=inherited, direct=direct)

    def get_inheritance_summary(self, blueprint_id: str) -> dict:
        try:
            bp_data = self._graph.get(
                f"/applications/{blueprint_id}",
                params={
                    "$select": "identifierUris,web,api,displayName",
                },
            )
            bp = _BlueprintSummary(bp_data)
        except GraphAPIError:
            bp = None

        all_ips = self.get_inheritable_for_blueprint(blueprint_id)
        consented = [ip for ip in all_ips if ip.admin_consented]
        unconsented = [ip for ip in all_ips if not ip.admin_consented]

        protocol_items = [
            f"Identifier URI: {bp.identifier_uri}" if bp else "",
            f"Grant Types: {', '.join(bp.supported_grant_types)}" if bp else "",
            f"OAuth2 Scopes: {', '.join(bp.oauth2_scope_values)}" if bp else "",
        ]

        return {
            "protocol_properties": {
                "description": "Always inherited (OAuth2 config, identifier URIs, grant types)",
                "items": protocol_items,
            },
            "delegated_permissions": {
                "description": "Conditionally inherited (requires inheritablePermissions + OAuth2PermissionGrant)",
                "active_count": len(consented),
                "pending_consent_count": len(unconsented),
                "active": [
                    self.get_permission_by_id(ip.permission_id)
                    for ip in consented
                    if self.get_permission_by_id(ip.permission_id)
                ],
                "pending": [
                    self.get_permission_by_id(ip.permission_id)
                    for ip in unconsented
                    if self.get_permission_by_id(ip.permission_id)
                ],
            },
            "not_inherited": {
                "description": "Direct assignment only (appRoleAssignments, RBAC roles, sponsor designations)",
            },
        }


class _BlueprintSummary:
    """Lightweight adapter for Graph API /applications response."""

    def __init__(self, graph_data: dict) -> None:
        uris = graph_data.get("identifierUris", [])
        self.identifier_uri: str = uris[0] if uris else ""

        api = graph_data.get("api", {})
        scopes = api.get("oauth2PermissionScopes", [])
        self.oauth2_scope_values: List[str] = [
            s.get("value", "") for s in scopes if s.get("isEnabled", True)
        ]

        web = graph_data.get("web", {})
        grant_types = []
        if web.get("redirectUris"):
            grant_types.append("authorization_code")
        if web.get("implicitGrantSettings", {}).get("enableAccessTokenIssuance"):
            grant_types.append("implicit")
        if not grant_types:
            grant_types = ["client_credentials"]
        self.supported_grant_types: List[str] = grant_types
