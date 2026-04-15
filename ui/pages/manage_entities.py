"""Manage Entities page: create/delete blueprints, identities, Foundry resources/projects, and agents."""

from __future__ import annotations

from typing import Optional

import streamlit as st

from config.azure_config import AzureConfig
from config.theme import (
    NODE_BLUEPRINT, NODE_IDENTITY, NODE_FOUNDRY, NODE_AGENT, NODE_RESOURCE, NODE_DOMAIN,
    COLOR_TEXT_SECONDARY, COLOR_DANGER,
)
from models.blueprint import CredentialType
from services.blueprint_service import BlueprintService
from services.cache import SessionCache
from services.foundry_service import FoundryService
from services.graph_client import GraphClient, GraphAPIError


def render(
    store: dict,
    *,
    graph: GraphClient,
    cache: SessionCache,
    config: AzureConfig,
    arm=None,
    **kwargs,
) -> None:
    st.markdown("## Manage Entities")
    st.caption("Create and manage blueprints, agent identities, Foundry resources/projects, and agents.")

    bp_svc = BlueprintService(graph=graph, cache=cache, config=config)
    foundry_svc = FoundryService(store=store, arm_client=arm)

    tab_bp, tab_id, tab_resource, tab_foundry, tab_agent, tab_delete = st.tabs([
        "📋 Domain Blueprint",
        "🆔 Agent Identity",
        "🏗️ Foundry Resource",
        "📁 Foundry Project",
        "🤖 Publish Agent",
        "🗑️ Delete",
    ])

    with tab_bp:
        _render_create_blueprint(bp_svc, store, config)

    with tab_id:
        _render_create_identity(bp_svc, store)

    with tab_resource:
        _render_create_resource(foundry_svc, store, config)

    with tab_foundry:
        _render_create_foundry(foundry_svc, store)

    with tab_agent:
        _render_publish_agent(bp_svc, foundry_svc, store)

    with tab_delete:
        _render_delete(bp_svc, foundry_svc, store)


# ── Create Blueprint ─────────────────────────────────────────────────────────

# Business domains for blueprint creation presets
BUSINESS_DOMAINS = [
    "HR", "Finance", "Customer Service", "IT Operations",
    "Sales", "Marketing", "Legal", "Engineering", "General",
]

# ── Domain presets for auto-populating blueprint fields ────────────────────────

_DOMAIN_PRESETS = {
    "HR": {
        "name": "HR Agent Platform",
        "desc": "Shared identity blueprint for HR domain agents — recruitment, onboarding, benefits, and employee self-service bots",
        "cred": "Managed Identity (Recommended)",
    },
    "Finance": {
        "name": "Finance Agent Platform",
        "desc": "Shared identity blueprint for Finance domain agents — expense approval, budget forecasting, and invoice processing bots",
        "cred": "Certificate",
    },
    "Customer Service": {
        "name": "Customer Service Agent Platform",
        "desc": "Shared identity blueprint for Customer Service agents — support ticket triage, FAQ bots, and escalation assistants",
        "cred": "Managed Identity (Recommended)",
    },
    "IT Operations": {
        "name": "IT Ops Agent Platform",
        "desc": "Shared identity blueprint for IT Operations agents — incident response, monitoring alerts, and self-healing automation",
        "cred": "Certificate",
    },
    "Sales": {
        "name": "Sales Agent Platform",
        "desc": "Shared identity blueprint for Sales domain agents — lead scoring, CRM assistants, and pipeline analytics bots",
        "cred": "Managed Identity (Recommended)",
    },
    "Marketing": {
        "name": "Marketing Agent Platform",
        "desc": "Shared identity blueprint for Marketing agents — campaign analytics, content generation, and audience segmentation bots",
        "cred": "Managed Identity (Recommended)",
    },
    "Legal": {
        "name": "Legal Agent Platform",
        "desc": "Shared identity blueprint for Legal domain agents — contract review, compliance checks, and policy Q&A bots",
        "cred": "Certificate",
    },
    "Engineering": {
        "name": "Engineering Agent Platform",
        "desc": "Shared identity blueprint for Engineering agents — code review assistants, CI/CD bots, and documentation generators",
        "cred": "Managed Identity (Recommended)",
    },
    "General": {
        "name": "General Agent Platform",
        "desc": "Shared identity blueprint for general-purpose AI agents across the organization",
        "cred": "Managed Identity (Recommended)",
    },
}


def _render_create_blueprint(bp_svc: BlueprintService, store: dict, config: AzureConfig) -> None:
    st.markdown("### Create a Domain Blueprint")
    st.markdown(
        "A **Domain Blueprint** is a shared identity template for all AI agents "
        "in a business domain. Instead of each agent having its own blueprint, "
        "agents across the same domain (e.g., HR, Finance) share one blueprint. "
        "This reduces identity sprawl and simplifies permission governance."
    )

    # Show existing domain blueprint summary
    blueprints = bp_svc.list_blueprints()
    if blueprints:
        st.markdown("#### Existing Blueprints")
        for bp in blueprints:
            ids = bp_svc.get_identities_for_blueprint(bp.id)
            st.markdown(
                f"- 📋 **{bp.display_name}** — {len(ids)} identities "
                f"(`{bp.credential_type.value}`)"
            )
        st.markdown("---")

    # Domain selector outside the form so it drives prepopulation
    domain = st.selectbox(
        "Business Domain *",
        options=BUSINESS_DOMAINS,
        key="bp_domain_select",
        help="Select a domain to auto-populate recommended values below.",
    )

    preset = _DOMAIN_PRESETS.get(domain, _DOMAIN_PRESETS["General"])

    cred_options = {
        "Managed Identity (Recommended)": CredentialType.MANAGED_IDENTITY,
        "Certificate": CredentialType.CERTIFICATE,
        "Client Secret (Dev Only)": CredentialType.CLIENT_SECRET,
    }
    cred_keys = list(cred_options.keys())
    preset_cred_idx = cred_keys.index(preset["cred"]) if preset["cred"] in cred_keys else 0

    with st.form("create_blueprint_form", clear_on_submit=True):
        name = st.text_input(
            "Display Name *",
            value=preset["name"],
            help="Auto-populated from domain. Edit freely.",
        )
        desc = st.text_input(
            "Description",
            value=preset["desc"],
        )
        tenant = st.text_input(
            "Tenant *",
            value=config.tenant_id,
            help="Pre-filled from your .env AZURE_TENANT_ID",
        )

        cred_label = st.selectbox(
            "Credential Type",
            options=cred_keys,
            index=preset_cred_idx,
        )

        st.caption(
            "**Blueprint per Business Domain pattern:** One blueprint per domain "
            "(HR, Finance, etc.). All agents in the domain share this blueprint's "
            "permissions. Each Foundry project linked to this domain uses the same blueprint. "
            "Environment isolation (dev/test/prod) is handled at the Foundry project level."
        )

        submitted = st.form_submit_button("Create Domain Blueprint", type="primary")
        if submitted:
            if not name or not tenant:
                st.error("Display Name and Tenant are required.")
            else:
                try:
                    bp = bp_svc.create_blueprint(
                        display_name=name,
                        description=desc or f"{domain} domain blueprint",
                        credential_type=cred_options[cred_label],
                        tenant_id=tenant,
                    )
                except GraphAPIError as exc:
                    st.error(
                        f"Failed to create blueprint: {exc.message} "
                        f"(code: {exc.error_code}, status: {exc.status_code}). "
                        "Check the required Graph API permissions in README."
                    )
                    st.stop()
                # Check if auto-provisioned principal exists
                try:
                    principals = bp_svc.get_principals_for_blueprint(bp.id)
                except GraphAPIError:
                    principals = []
                if principals:
                    st.success(f"Domain Blueprint **{name}** ({domain}) created with auto-provisioned Service Principal.")
                else:
                    st.warning(
                        f"Domain Blueprint **{name}** ({domain}) created, but Service Principal "
                        "auto-provisioning failed (missing `AgentIdentityBlueprintPrincipal.Create` permission). "
                        "Grant the permission and create the principal from the dashboard."
                    )
                st.rerun()


# ── Create Agent Identity ────────────────────────────────────────────────────

def _render_create_identity(bp_svc: BlueprintService, store: dict) -> None:
    st.markdown("### Create an Agent Identity")
    st.markdown(
        "An **Agent Identity** is a runtime identity created from a blueprint. "
        "It gets its own Client ID but inherits delegated permissions from the parent blueprint. "
        "Direct permissions (appRoleAssignments) must be assigned separately."
    )

    blueprints = bp_svc.list_blueprints()
    if not blueprints:
        st.warning("Create a Blueprint first before creating an Agent Identity.")
        return

    with st.form("create_identity_form", clear_on_submit=True):
        bp_names = {bp.display_name: bp.id for bp in blueprints}
        selected_bp = st.selectbox(
            "Parent Blueprint *",
            options=list(bp_names.keys()),
            help="The blueprint this identity will be created under",
        )
        name = st.text_input(
            "Display Name *",
            placeholder="e.g. Customer Support Agent",
        )
        create_user = st.checkbox(
            "Create Agent User Account",
            help="Creates a companion user account for delegated scenarios (T3 token flow)",
        )

        st.caption(
            "**Important:** The agent identity's service principal shows NO permissions in the Azure Portal. "
            "This is **by design** — permissions are dynamically merged at token issuance time "
            "from the parent blueprint."
        )

        submitted = st.form_submit_button("Create Agent Identity", type="primary")
        if submitted:
            if not name:
                st.error("Display Name is required.")
            else:
                bp_svc.create_agent_identity(
                    blueprint_id=bp_names[selected_bp],
                    display_name=name,
                    create_user_account=create_user,
                )
                st.success(f"Agent Identity **{name}** created under blueprint **{selected_bp}**.")
                st.rerun()


# ── Link Foundry Project ────────────────────────────────────────────────────

def _render_create_resource(foundry_svc: FoundryService, store: dict, config: AzureConfig = None) -> None:
    st.markdown("### Foundry Resources (AI Services Accounts)")
    st.markdown(
        "A **Foundry Resource** is an Azure AI Services (Cognitive Services) account. "
        "It's the **parent** of Foundry projects. One resource can host **multiple projects**, "
        "and blueprints are scoped at the **project level**, not here."
    )

    # Discover real Azure resources
    if foundry_svc._arm is not None:
        with st.spinner("Discovering Azure AI Services accounts..."):
            foundry_svc.discover_azure_resources()

    # Show existing resources
    resources = foundry_svc.list_resources()
    if resources:
        st.markdown("#### Discovered & Local Resources")
        for res in resources:
            projects = foundry_svc.get_projects_for_resource(res.id)
            st.markdown(
                f"- 🏗️ **{res.name}** ({res.region}) — "
                f"{len(projects)} project(s), RG: `{res.resource_group}`, "
                f"Sub: `{res.subscription_id[:8]}...`"
            )
    else:
        st.info("No Foundry Resources found. Create one below or check your Azure credentials.")

    st.markdown("---")
    st.markdown("#### Create a New Foundry Resource")
    st.caption("Creates an Azure AI Services account. Requires a valid Subscription ID and Azure credentials.")

    with st.form("create_resource_form", clear_on_submit=True):
        name = st.text_input(
            "Resource Name *",
            value="contoso-ai-svc360",
            help="Name of the Azure AI Services account",
        )
        regions = [
            "swedencentral", "eastus", "eastus2", "westus2", "westus3", "centralus",
            "westeurope", "northeurope", "uksouth", "francecentral",
            "norwayeast", "germanywestcentral", "switzerlandnorth",
            "southeastasia", "eastasia", "japaneast",
            "australiaeast", "canadacentral", "brazilsouth",
            "koreacentral", "centralindia", "uaenorth",
        ]
        region = st.selectbox("Region", regions)
        rg = st.text_input(
            "Resource Group",
            placeholder="e.g. rg-contoso-ai (auto-generated if blank)",
        )
        default_sub = config.subscription_id if config else ""
        sub_id = st.text_input(
            "Subscription ID *",
            value=default_sub,
            placeholder="00000000-0000-0000-0000-000000000000",
            help="Required to provision the resource in Azure",
        )

        submitted = st.form_submit_button("Create Resource", type="primary")
        if submitted:
            if not name:
                st.error("Resource Name is required.")
            elif not sub_id or sub_id == "00000000-0000-0000-0000-000000000000":
                st.error("A valid Subscription ID is required to create an Azure resource.")
            elif foundry_svc._arm is None:
                st.error("ARM client is not configured. Check your Azure credentials.")
            else:
                try:
                    foundry_svc.create_resource(
                        name=name,
                        region=region,
                        resource_group=rg,
                        subscription_id=sub_id,
                    )
                    st.success(f"Foundry Resource **{name}** created in Azure ({region}).")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to create resource in Azure: {exc}")


# ── Create Foundry Project ───────────────────────────────────────────────────

def _render_create_foundry(foundry_svc: FoundryService, store: dict) -> None:
    st.markdown("### Create a Foundry Project")
    st.markdown(
        "A **Foundry Project** hosts your AI agents and lives inside a Foundry Resource. "
        "Projects are independent of Agent Identity Blueprints — blueprints live in "
        "Entra ID while projects live in Azure ARM."
    )

    # Discover real Azure resources if ARM client available
    if foundry_svc._arm is not None:
        foundry_svc.discover_azure_resources()

    resources = foundry_svc.list_resources()

    # ── Resource selector (outside form for dynamic prepopulation) ────
    resource_mode = st.radio(
        "Project Source",
        ["Link to existing Foundry Resource", "Create standalone project"],
        key="foundry_proj_mode",
        horizontal=True,
    )

    selected_resource_id = ""
    prepop_region = "swedencentral"
    prepop_rg = ""
    prepop_sub = ""
    selected_resource_label = ""

    if resource_mode == "Link to existing Foundry Resource":
        if not resources:
            st.warning(
                "No Foundry Resources exist yet. "
                "Create one in the **Foundry Resource** tab first, or choose **Create standalone project**."
            )
            return

        resource_labels = {f"{r.name} ({r.region}) — RG: {r.resource_group}": r for r in resources}
        selected_resource_label = st.selectbox(
            "Select Foundry Resource *",
            options=list(resource_labels.keys()),
            key="foundry_resource_select",
            help="Region and Resource Group will be auto-populated from the selected resource.",
        )
        selected_resource = resource_labels[selected_resource_label]
        selected_resource_id = selected_resource.id
        prepop_region = selected_resource.region
        prepop_rg = selected_resource.resource_group
        prepop_sub = selected_resource.subscription_id

        # Show existing projects under this resource
        existing_projects = foundry_svc.get_projects_for_resource(selected_resource_id)
        if existing_projects:
            st.markdown(f"**Existing projects under {selected_resource.name}:**")
            for ep in existing_projects:
                st.markdown(f"  - ☁️ **{ep.name}** ({ep.region})")

    # ── Region options with preselection ──
    _ALL_REGIONS = [
        "swedencentral", "eastus", "eastus2", "westus2", "westus3", "centralus", "northcentralus", "southcentralus",
        "westeurope", "northeurope", "uksouth", "ukwest", "francecentral",
        "norwayeast", "germanywestcentral", "switzerlandnorth",
        "southeastasia", "eastasia", "japaneast", "japanwest",
        "australiaeast", "australiasoutheast",
        "canadacentral", "canadaeast", "brazilsouth",
        "koreacentral", "centralindia", "southafricanorth", "uaenorth",
    ]

    with st.form("create_foundry_form", clear_on_submit=True):
        proj_name = st.text_input(
            "Project Name *",
            placeholder="e.g. hr-agent-platform-dev",
            help="The Azure AI Foundry project name",
        )

        if resource_mode == "Link to existing Foundry Resource":
            # Region & RG inherited from resource — show as read-only
            st.text_input("Region", value=prepop_region, disabled=True,
                          help="Inherited from the selected Foundry Resource.")
            region = prepop_region
            st.text_input("Resource Group", value=prepop_rg, disabled=True,
                          help="Inherited from the selected Foundry Resource.")
            rg = prepop_rg
            st.caption(
                f"📌 This project will be created under resource **{selected_resource_label}** "
                f"(subscription: `{prepop_sub[:8]}...`)"
            )
        else:
            region_idx = _ALL_REGIONS.index(prepop_region) if prepop_region in _ALL_REGIONS else 0
            region = st.selectbox("Region", options=_ALL_REGIONS, index=region_idx)
            rg = st.text_input(
                "Resource Group",
                placeholder="e.g. rg-contoso-ai (auto-generated if blank)",
            )

        submitted = st.form_submit_button("Create Project", type="primary")
        if submitted:
            if not proj_name:
                st.error("Project Name is required.")
            else:
                try:
                    foundry_svc.create_project(
                        name=proj_name,
                        resource_id=selected_resource_id,
                        region=region,
                        resource_group=rg,
                    )
                    st.success(f"Foundry Project **{proj_name}** created.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to create project: {exc}")


# ── Publish Agent ─────────────────────────────────────────────────────────────

def _render_publish_agent(bp_svc: BlueprintService, foundry_svc: FoundryService, store: dict) -> None:
    st.markdown("### Publish a Foundry Agent")
    st.markdown(
        "A **Foundry Agent** is a deployed AI agent within a Foundry project. "
        "Each agent is linked to an **Agent Identity** from Entra ID."
    )

    projects = foundry_svc.list_projects()
    if not projects:
        st.info("Create a Foundry Project first (in the **Foundry Project** tab).")
        return

    # Get all identities across all blueprints
    all_identities = []
    for bp in bp_svc.list_blueprints():
        all_identities.extend(bp_svc.get_identities_for_blueprint(bp.id))

    with st.form("add_agent_form", clear_on_submit=True):
        proj_options = {f"{fp.name} ({fp.region})": fp.id for fp in projects}
        selected_proj_label = st.selectbox("Foundry Project *", options=list(proj_options.keys()))

        if not all_identities:
            st.warning("No agent identities exist. Create one in the **Agent Identity** tab first.")
        else:
            id_options = {ai.display_name: ai.id for ai in all_identities}
            selected_id = st.selectbox(
                "Agent Identity *",
                options=list(id_options.keys()),
                help="The identity this Foundry agent will authenticate as",
            )
            agent_name = st.text_input(
                "Agent Name *",
                placeholder="e.g. Customer Support Bot",
            )
            model = st.selectbox("Model", ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o3-mini"])
            agent_desc = st.text_input(
                "Description",
                placeholder="e.g. Handles customer queries via Teams",
            )

            submitted = st.form_submit_button("Publish Agent", type="primary")
            if submitted:
                if not agent_name:
                    st.error("Agent Name is required.")
                else:
                    foundry_svc.add_agent(
                        project_id=proj_options[selected_proj_label],
                        name=agent_name,
                        agent_identity_id=id_options[selected_id],
                        model=model,
                        description=agent_desc,
                    )
                    st.success(
                        f"Agent **{agent_name}** published to project **{selected_proj_label}** "
                        f"running as **{selected_id}**."
                    )
                    st.rerun()


# ── Delete ───────────────────────────────────────────────────────────────────

def _render_delete(bp_svc: BlueprintService, foundry_svc: FoundryService, store: dict) -> None:
    st.markdown("### Delete Entities")
    st.caption("Deleting a blueprint cascades to all its child entities (principals, identities, users).")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### Delete Blueprint")
        blueprints = bp_svc.list_blueprints()
        if blueprints:
            bp_names = {bp.display_name: bp.id for bp in blueprints}
            selected = st.selectbox(
                "Select Blueprint",
                options=list(bp_names.keys()),
                key="del_bp_select",
            )
            if st.button("Delete Blueprint", key="del_bp_btn", type="secondary"):
                bp_svc.delete_blueprint(bp_names[selected])
                st.success(f"Blueprint **{selected}** and its entities deleted.")
                st.rerun()
        else:
            st.info("No blueprints to delete.")

    with col2:
        st.markdown("#### Delete Foundry Project")
        projects = foundry_svc.list_projects()
        if projects:
            proj_names = {f"{fp.name} ({fp.region})": fp.id for fp in projects}
            selected_proj = st.selectbox(
                "Select Project",
                options=list(proj_names.keys()),
                key="del_proj_select",
            )
            if st.button("Delete Project", key="del_proj_btn", type="secondary"):
                foundry_svc.delete_project(proj_names[selected_proj])
                st.success(f"Foundry Project **{selected_proj}** deleted.")
                st.rerun()
        else:
            st.info("No Foundry projects to delete.")

    with col3:
        st.markdown("#### Delete Foundry Resource")
        resources = foundry_svc.list_resources()
        if resources:
            res_names = {f"{r.name} ({r.region})": r.id for r in resources}
            selected_res = st.selectbox(
                "Select Resource",
                options=list(res_names.keys()),
                key="del_res_select",
            )
            if st.button("Delete Resource", key="del_res_btn", type="secondary"):
                foundry_svc.delete_resource(res_names[selected_res])
                st.success(f"Foundry Resource **{selected_res}** and its projects deleted.")
                st.rerun()
        else:
            st.info("No Foundry resources to delete.")
