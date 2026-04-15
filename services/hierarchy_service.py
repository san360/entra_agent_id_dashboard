"""Service for building hierarchical trees from the identity store."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from services.blueprint_service import BlueprintService


@dataclass
class HierarchyNode:
    node_type: str  # "blueprint" | "principal" | "identity" | "user"
    entity_id: str
    display_name: str
    icon: str
    children: List[HierarchyNode] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class HierarchyService:
    def __init__(self, bp_svc: BlueprintService):
        self._bp_svc = bp_svc

    def build_tree(self, blueprint_id: str) -> HierarchyNode:
        bp = self._bp_svc.get_blueprint(blueprint_id)
        if bp is None:
            return HierarchyNode(
                node_type="blueprint",
                entity_id=blueprint_id,
                display_name="(unknown)",
                icon="[B]",
            )

        bp_node = HierarchyNode(
            node_type="blueprint",
            entity_id=bp.id,
            display_name=bp.display_name,
            icon="[B]",
            metadata={
                "App ID": bp.app_id,
                "Credential": bp.credential_type.value,
                "Tenant": bp.tenant_id,
                "Identifier URI": bp.identifier_uri,
                "Grant Types": ", ".join(bp.supported_grant_types),
                "Scopes": ", ".join(s.value for s in bp.oauth2_scopes),
                "Sponsors": ", ".join(bp.sponsor_ids[:3]) + ("..." if len(bp.sponsor_ids) > 3 else ""),
                "Graph Endpoint": bp.graph_endpoint,
                "Created": str(bp.created_at)[:19],
            },
        )

        principals = self._bp_svc.get_principals_for_blueprint(blueprint_id)
        for pr in principals:
            pr_node = HierarchyNode(
                node_type="principal",
                entity_id=pr.id,
                display_name=pr.display_name,
                icon="[SP]",
                metadata={
                    "Object ID": pr.id,
                    "App ID": pr.app_id,
                    "Type": pr.service_principal_type,
                    "Tenant": pr.tenant_id,
                    "OAuth2 Grants": ", ".join(pr.oauth2_permission_grants) if pr.oauth2_permission_grants else "None",
                    "Graph Endpoint": pr.graph_endpoint,
                },
            )

            identities = self._bp_svc.get_identities_for_blueprint(blueprint_id)
            for ai in identities:
                if ai.principal_id != pr.id:
                    continue
                ai_node = HierarchyNode(
                    node_type="identity",
                    entity_id=ai.id,
                    display_name=ai.display_name,
                    icon="[AI]",
                    metadata={
                        "Object ID": ai.id,
                        "Client ID": ai.client_id,
                        "Blueprint Link": ai.agent_identity_blueprint_id,
                        "Sponsors": ", ".join(ai.sponsor_ids[:3]) + ("..." if len(ai.sponsor_ids) > 3 else ""),
                        "Has User": str(ai.has_user_account),
                        "Portal Permissions": "None (BY DESIGN — merged at token time)",
                        "Created": str(ai.created_at)[:19],
                    },
                )

                if ai.has_user_account:
                    user = self._bp_svc.get_agent_user(ai.id)
                    if user is not None:
                        au_node = HierarchyNode(
                            node_type="user",
                            entity_id=user.id,
                            display_name=user.display_name,
                            icon="[U]",
                            metadata={
                                "Object ID": user.id,
                                "UPN": user.user_principal_name,
                                "Mail": user.mail,
                                "Created": str(user.created_at)[:19],
                            },
                        )
                        ai_node.children.append(au_node)

                pr_node.children.append(ai_node)
            bp_node.children.append(pr_node)

        return bp_node

    def build_forest(self) -> List[HierarchyNode]:
        blueprints = self._bp_svc.list_blueprints()
        return [self.build_tree(bp.id) for bp in blueprints]

    def flatten_tree(
        self, node: HierarchyNode, depth: int = 0
    ) -> List[Tuple[int, HierarchyNode]]:
        result = [(depth, node)]
        for child in node.children:
            result.extend(self.flatten_tree(child, depth + 1))
        return result
