from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class AzureConfig:
    """Centralized Azure configuration loaded from environment variables."""

    tenant_id: str
    client_id: str = ""
    client_secret: str = ""
    graph_base_url: str = "https://graph.microsoft.com/beta"
    token_endpoint_template: str = (
        "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    )
    subscription_id: str = ""
    blueprint_client_secret: str = ""
    blueprint_certificate_path: str = ""


def load_azure_config() -> AzureConfig:
    """Load Azure configuration from .env file and environment variables.

    Raises ValueError if AZURE_TENANT_ID is not set.
    """
    load_dotenv()

    tenant_id = os.environ.get("AZURE_TENANT_ID", "")
    if not tenant_id:
        raise ValueError(
            "AZURE_TENANT_ID environment variable is required. "
            "Set it in a .env file or export it before running the dashboard."
        )

    return AzureConfig(
        tenant_id=tenant_id,
        client_id=os.environ.get("AZURE_CLIENT_ID", ""),
        client_secret=os.environ.get("AZURE_CLIENT_SECRET", ""),
        subscription_id=os.environ.get("AZURE_SUBSCRIPTION_ID", ""),
        blueprint_client_secret=os.environ.get("BLUEPRINT_CLIENT_SECRET", ""),
        blueprint_certificate_path=os.environ.get("BLUEPRINT_CERTIFICATE_PATH", ""),
    )
