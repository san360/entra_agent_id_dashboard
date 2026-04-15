"""Data models for Permissions, Inheritable Permissions, and App Role Assignments."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List


class PermissionScope(Enum):
    DELEGATED = "Delegated"
    APPLICATION = "Application"


@dataclass
class Permission:
    name: str
    description: str
    scope: PermissionScope
    resource_app_display_name: str = "Microsoft Graph"
    resource_app_id: str = "00000003-0000-0000-c000-000000000000"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @classmethod
    def from_graph_app_role(
        cls, data: dict, resource_app_id: str, resource_display_name: str
    ) -> Permission:
        """Deserialize a Permission from a Graph API appRoles entry."""
        return cls(
            id=data["id"],
            name=data["value"],
            description=data.get("description", ""),
            scope=PermissionScope.APPLICATION,
            resource_app_id=resource_app_id,
            resource_app_display_name=resource_display_name,
        )

    @classmethod
    def from_graph_oauth2_scope(
        cls, data: dict, resource_app_id: str, resource_display_name: str
    ) -> Permission:
        """Deserialize a Permission from a Graph API oauth2PermissionScopes entry."""
        return cls(
            id=data["id"],
            name=data["value"],
            description=data.get("adminConsentDescription", ""),
            scope=PermissionScope.DELEGATED,
            resource_app_id=resource_app_id,
            resource_app_display_name=resource_display_name,
        )


@dataclass
class InheritablePermission:
    blueprint_id: str
    permission_id: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    admin_consented: bool = True
    assigned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AppRoleAssignment:
    agent_identity_id: str
    permission_id: str
    resource_display_name: str = "Microsoft Graph"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    assigned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EffectivePermissions:
    inherited: List[Permission] = field(default_factory=list)
    direct: List[Permission] = field(default_factory=list)

    @property
    def all_permissions(self) -> List[Permission]:
        seen = set()
        result = []
        for p in self.inherited + self.direct:
            if p.id not in seen:
                seen.add(p.id)
                result.append(p)
        return result
