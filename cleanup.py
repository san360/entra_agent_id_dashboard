#!/usr/bin/env python3
"""Cleanup script — deletes ALL agent identity blueprints, their service principals,
agent identities, and agent users from the Entra tenant.

Also removes local session artifacts (.foundry_linkages.json).

Hierarchy (each Foundry project gets its own independent blueprint chain):
    Foundry Resource (Microsoft.CognitiveServices/account)
     └── Foundry Project (account/project)  ← blueprint scoped HERE
          └── Project Blueprint (auto-created by Foundry 1P app)
               └── Manager Blueprint (created by Project Blueprint)
                    └── Per-Agent Blueprint(s) (one per published agent)
                         └── Agent Identity/Identities

Usage:
    python cleanup.py               # dry-run (shows what would be deleted)
    python cleanup.py --execute     # actually deletes everything

Prerequisites — Service Principal API Permissions (Application, admin-consented):
    ┌─────────────────────────────────────────────────────────────┐
    │  Microsoft Graph (00000003-0000-0000-c000-000000000000)     │
    ├─────────────────────────────────────────────────────────────┤
    │  Application.ReadWrite.All                                  │
    │  AgentIdentityBlueprint.Read.All                            │
    │  AgentIdentityBlueprint.DeleteRestore.All                   │
    │  AgentIdentityBlueprintPrincipal.Read.All                   │
    │  AgentIdentityBlueprintPrincipal.DeleteRestore.All          │
    │  AgentIdentity.Read.All                                     │
    │  AgentIdentity.DeleteRestore.All                            │
    │  User.ReadWrite.All  (only if agent users exist)            │
    └─────────────────────────────────────────────────────────────┘

    Grant admin consent after adding permissions:
        az ad app permission admin-consent --id <APP_ID>

    Or grant individual roles via:
        az rest --method POST \\
          --uri "https://graph.microsoft.com/v1.0/servicePrincipals/<SP_OBJECT_ID>/appRoleAssignments" \\
          --body '{"principalId":"<SP_OBJECT_ID>","resourceId":"<GRAPH_SP_ID>","appRoleId":"<ROLE_ID>"}'

    Key role IDs:
        AgentIdentityBlueprint.DeleteRestore.All      = 3f80b699-6405-4e36-a4df-4f19950ff91e
        AgentIdentity.DeleteRestore.All               = 5b016f9b-18eb-41d4-869a-66931914d1c8
        AgentIdentityBlueprintPrincipal.DeleteRestore.All = f86a2dd8-9298-4675-bd78-f5a3572da2d7
        AgentIdentityBlueprint.Read.All               = 7547a7d1-36fa-4479-9c31-559a600eaa4f
        AgentIdentity.Read.All                        = b2b8f011-2898-4234-9092-5059f6c1ebfa
        AgentIdentityBlueprintPrincipal.Read.All      = 9361dea9-4524-493d-941d-f1b65aaf6c7c

Environment variables (set in .env or export):
    AZURE_TENANT_ID       — Required
    AZURE_CLIENT_ID       — Required (SP app ID)
    AZURE_CLIENT_SECRET   — Required (SP client secret)
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(__file__))

from config.azure_config import load_azure_config
from services.graph_client import GraphClient, GraphAPIError

LINKAGE_FILE = os.path.join(os.path.dirname(__file__), ".foundry_linkages.json")

# Required Graph API permission role IDs for deletion
REQUIRED_ROLES = {
    "3f80b699-6405-4e36-a4df-4f19950ff91e": "AgentIdentityBlueprint.DeleteRestore.All",
    "5b016f9b-18eb-41d4-869a-66931914d1c8": "AgentIdentity.DeleteRestore.All",
    "f86a2dd8-9298-4675-bd78-f5a3572da2d7": "AgentIdentityBlueprintPrincipal.DeleteRestore.All",
    "7547a7d1-36fa-4479-9c31-559a600eaa4f": "AgentIdentityBlueprint.Read.All",
    "b2b8f011-2898-4234-9092-5059f6c1ebfa": "AgentIdentity.Read.All",
    "1bfefb4e-e0b5-418b-a88f-73c46d2cc8e9": "Application.ReadWrite.All",
}


def _check_permissions(graph: GraphClient) -> bool:
    """Verify the token contains the required roles. Returns True if OK."""
    import base64
    import json as _json

    token = graph._get_access_token()
    # Decode JWT payload (no signature verification — just reading claims)
    payload = token.split(".")[1]
    payload += "=" * (4 - len(payload) % 4)
    claims = _json.loads(base64.b64decode(payload))
    roles = set(claims.get("roles", []))

    required_names = set(REQUIRED_ROLES.values())
    missing = required_names - roles
    if missing:
        print("❌ Missing required API permissions in token:")
        for m in sorted(missing):
            role_id = next((k for k, v in REQUIRED_ROLES.items() if v == m), "?")
            print(f"   • {m}  (role ID: {role_id})")
        print()
        print("   Grant them via:")
        print("     az ad app permission add --id <APP_ID> \\")
        print("       --api 00000003-0000-0000-c000-000000000000 \\")
        print("       --api-permissions <ROLE_ID>=Role")
        print("     az ad app permission admin-consent --id <APP_ID>")
        print()
        print("   Then wait ~1 minute for consent to propagate and retry.")
        return False
    print("✅ All required permissions present in token")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean up Entra Agent Identity resources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Hierarchy (each Foundry project gets its own blueprint chain):
  Foundry Resource (CognitiveServices/account)
   └── Project (account/project)  ← blueprints scoped here
        └── Project Blueprint
             └── Manager Blueprint
                  └── Per-Agent Blueprint(s)
                       └── Agent Identity/Identities

Required permissions:
  AgentIdentityBlueprint.DeleteRestore.All
  AgentIdentityBlueprintPrincipal.DeleteRestore.All
  AgentIdentity.DeleteRestore.All
  Application.ReadWrite.All
  (see script header for full list and role IDs)
""",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete resources. Without this flag, only a dry-run is performed.",
    )
    parser.add_argument(
        "--skip-permission-check",
        action="store_true",
        help="Skip the token permission pre-flight check.",
    )
    args = parser.parse_args()

    dry = not args.execute
    if dry:
        print("=" * 60)
        print("  DRY RUN — pass --execute to actually delete resources")
        print("=" * 60)
    else:
        print("=" * 60)
        print("  ⚠️  EXECUTING DELETES — this cannot be undone!")
        print("=" * 60)

    config = load_azure_config()
    graph = GraphClient(config)

    # ── Pre-flight: verify permissions ─────────────────────────────────
    if not args.skip_permission_check:
        print("\n🔑 Checking API permissions...")
        if not _check_permissions(graph):
            sys.exit(1)
    else:
        print("\n⏩ Skipping permission check (--skip-permission-check)")

    # ── 1. List all blueprints ─────────────────────────────────────────
    print("\n🔍 Listing agent identity blueprints...")
    try:
        blueprints = graph.get_all("/applications/microsoft.graph.agentIdentityBlueprint")
    except GraphAPIError as e:
        print(f"   ❌ Failed to list blueprints: {e}")
        return

    if not blueprints:
        print("   No blueprints found.")
    else:
        print(f"   Found {len(blueprints)} blueprint(s)")

    # ── 2. List all agent identities ───────────────────────────────────
    print("\n🔍 Listing agent identities...")
    try:
        identities = graph.get_all("/servicePrincipals/microsoft.graph.agentIdentity")
    except GraphAPIError as e:
        print(f"   ❌ Failed to list identities: {e}")
        identities = []

    if not identities:
        print("   No agent identities found.")
    else:
        print(f"   Found {len(identities)} agent identity/identities")

    # ── 3. Delete agent users for each identity ────────────────────────
    for identity in identities:
        identity_id = identity.get("id", "")
        identity_name = identity.get("displayName", "unknown")
        print(f"\n   🧹 Identity: {identity_name} ({identity_id})")

        # Find agent users linked to this identity
        try:
            users_resp = graph.get(
                "/users",
                params={"$filter": f"agentIdentityId eq '{identity_id}'", "$select": "id,displayName,userPrincipalName"},
            )
            users = users_resp.get("value", [])
        except GraphAPIError:
            users = []

        for user in users:
            uid = user.get("id", "")
            uname = user.get("displayName", "unknown")
            upn = user.get("userPrincipalName", "")
            if dry:
                print(f"      [DRY] Would delete agent user: {uname} ({upn}) [{uid}]")
            else:
                try:
                    graph.delete(f"/users/{uid}")
                    print(f"      ✅ Deleted agent user: {uname} ({upn})")
                except GraphAPIError as e:
                    print(f"      ❌ Failed to delete user {uname}: {e}")

        # Delete the agent identity via the agent-specific endpoint
        if dry:
            print(f"      [DRY] Would delete identity SP: {identity_name} [{identity_id}]")
        else:
            deleted = False
            for endpoint in [
                f"/servicePrincipals/microsoft.graph.agentIdentity/{identity_id}",
                f"/servicePrincipals/{identity_id}",
            ]:
                try:
                    graph.delete(endpoint)
                    print(f"      ✅ Deleted identity SP: {identity_name}")
                    deleted = True
                    break
                except GraphAPIError:
                    continue
            if not deleted:
                print(f"      ❌ Failed to delete identity SP {identity_name} via all endpoints")

    # ── 4. Delete blueprint principals and blueprint applications ──────
    #
    # Deletion order per blueprint:
    #   1. Delete blueprint principal SP via agentIdentityBlueprintPrincipal endpoint
    #   2. Delete blueprint application via agentIdentityBlueprint endpoint
    #
    # Using the agent-specific endpoints is required — the generic
    # DELETE /servicePrincipals/{id} returns 403 for agent blueprint SPs.
    for bp in blueprints:
        bp_id = bp.get("id", "")
        bp_name = bp.get("displayName", "unknown")
        bp_app_id = bp.get("appId", "")
        print(f"\n   🧹 Blueprint: {bp_name} ({bp_id}), appId={bp_app_id}")

        # Find and delete the blueprint principal
        if bp_app_id:
            try:
                sps = graph.get_all(
                    "/servicePrincipals",
                    params={"$filter": f"appId eq '{bp_app_id}'"},
                )
            except GraphAPIError:
                sps = []

            for sp in sps:
                sp_id = sp.get("id", "")
                sp_name = sp.get("displayName", "unknown")
                if dry:
                    print(f"      [DRY] Would delete blueprint SP: {sp_name} [{sp_id}]")
                else:
                    deleted = False
                    # Try agent-specific endpoint first
                    for endpoint in [
                        f"/servicePrincipals/microsoft.graph.agentIdentityBlueprintPrincipal/{sp_id}",
                        f"/servicePrincipals/{sp_id}",
                    ]:
                        try:
                            graph.delete(endpoint)
                            print(f"      ✅ Deleted blueprint SP: {sp_name}")
                            deleted = True
                            break
                        except GraphAPIError:
                            continue
                    if not deleted:
                        print(f"      ⚠️  Could not delete SP {sp_name} (will be orphaned; "
                              f"deleting the app may cascade-remove it)")

        # Delete the blueprint application
        if dry:
            print(f"      [DRY] Would delete blueprint app: {bp_name} [{bp_id}]")
        else:
            try:
                graph.delete(f"/applications/{bp_id}")
                print(f"      ✅ Deleted blueprint app: {bp_name}")
            except GraphAPIError as e:
                print(f"      ❌ Failed to delete blueprint app {bp_name}: {e}")
            # Brief pause to avoid throttling
            time.sleep(0.5)

    # ── 5. Clean up local files ────────────────────────────────────────
    print("\n🧹 Local cleanup...")
    if os.path.exists(LINKAGE_FILE):
        if dry:
            print(f"   [DRY] Would delete {LINKAGE_FILE}")
        else:
            os.remove(LINKAGE_FILE)
            print(f"   ✅ Deleted {LINKAGE_FILE}")
    else:
        print(f"   No linkage file found at {LINKAGE_FILE}")

    # ── Summary ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    total = len(blueprints) + len(identities)
    if dry:
        print(f"  DRY RUN complete — {total} resources would be deleted.")
        print("  Run with --execute to perform actual deletion.")
    else:
        print(f"  ✅ Cleanup complete — processed {total} resources.")
        print("  Restart the Streamlit app to start with a clean slate.")
    print("=" * 60)


if __name__ == "__main__":
    main()
