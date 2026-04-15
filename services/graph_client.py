from __future__ import annotations

import time
from typing import Optional

import httpx
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.core.credentials import AccessToken

from config.azure_config import AzureConfig

REQUEST_TIMEOUT = 30


class GraphAPIError(Exception):
    """Exception raised when the Microsoft Graph API returns an error response."""

    def __init__(self, status_code: int, error_code: str, message: str) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            f"GraphAPIError(status_code={self.status_code}, "
            f"error_code='{self.error_code}', "
            f"message='{self.message}')"
        )


class GraphClient:
    """Synchronous wrapper around the Microsoft Graph API using httpx.

    Authenticates via ``azure-identity.DefaultAzureCredential`` and caches
    access tokens until they are within 5 minutes of expiry.
    """

    def __init__(self, config: AzureConfig) -> None:
        self._config = config
        if config.client_id and config.client_secret:
            self._credential = ClientSecretCredential(
                tenant_id=config.tenant_id,
                client_id=config.client_id,
                client_secret=config.client_secret,
            )
        else:
            self._credential = DefaultAzureCredential()
        self._token: Optional[AccessToken] = None

    # ------------------------------------------------------------------
    # Authentication helpers
    # ------------------------------------------------------------------

    def _get_access_token(self) -> str:
        """Return a valid access token, refreshing if expired or near-expiry."""
        now = time.time()
        if self._token is None or self._token.expires_on - now < 300:
            self._token = self._credential.get_token(
                "https://graph.microsoft.com/.default"
            )
        return self._token.token

    def _headers(self) -> dict:
        """Build the default request headers for Graph API calls."""
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Response handling
    # ------------------------------------------------------------------

    def _handle_response(self, response: httpx.Response) -> dict:
        """Parse a Graph API response, raising on errors and handling 429."""
        if response.status_code == 204:
            return {}

        # Handle rate limiting with a single retry.
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                time.sleep(int(retry_after))
                retry_response = httpx.request(
                    method=response.request.method,
                    url=str(response.request.url),
                    headers=dict(response.request.headers),
                    content=response.request.content or None,
                    timeout=REQUEST_TIMEOUT,
                )
                return self._handle_response(retry_response)

        if response.status_code >= 400:
            error_code = "UnknownError"
            message = response.text
            try:
                body = response.json()
                error_obj = body.get("error", {})
                error_code = error_obj.get("code", error_code)
                message = error_obj.get("message", message)
            except Exception:
                pass
            raise GraphAPIError(
                status_code=response.status_code,
                error_code=error_code,
                message=message,
            )

        return response.json()

    # ------------------------------------------------------------------
    # Public HTTP methods
    # ------------------------------------------------------------------

    def get(self, path: str, params: dict = None) -> dict:
        """Send a GET request to the Graph API."""
        response = httpx.get(
            self._config.graph_base_url + path,
            headers=self._headers(),
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        return self._handle_response(response)

    def post(self, path: str, json_body: dict = None) -> dict:
        """Send a POST request to the Graph API."""
        response = httpx.post(
            self._config.graph_base_url + path,
            headers=self._headers(),
            json=json_body,
            timeout=REQUEST_TIMEOUT,
        )
        return self._handle_response(response)

    def patch(self, path: str, json_body: dict = None) -> dict:
        """Send a PATCH request to the Graph API."""
        response = httpx.patch(
            self._config.graph_base_url + path,
            headers=self._headers(),
            json=json_body,
            timeout=REQUEST_TIMEOUT,
        )
        return self._handle_response(response)

    def delete(self, path: str) -> dict:
        """Send a DELETE request to the Graph API."""
        response = httpx.delete(
            self._config.graph_base_url + path,
            headers=self._headers(),
            timeout=REQUEST_TIMEOUT,
        )
        return self._handle_response(response)

    def get_all(self, path: str, params: dict = None) -> list:
        """GET with automatic ``@odata.nextLink`` pagination.

        Returns a flat list of all ``value`` entries across every page.
        """
        results: list = []
        data = self.get(path, params=params)
        results.extend(data.get("value", []))

        while "@odata.nextLink" in data:
            next_url: str = data["@odata.nextLink"]
            response = httpx.get(
                next_url,
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            )
            data = self._handle_response(response)
            results.extend(data.get("value", []))

        return results

    def post_token_endpoint(self, tenant_id: str, form_data: dict) -> dict:
        """POST form-encoded data to the OAuth 2.0 token endpoint.

        This does **not** use a Bearer token or the Graph base URL.
        It targets the Microsoft identity platform token endpoint directly.
        """
        url = self._config.token_endpoint_template.format(tenant_id=tenant_id)
        response = httpx.post(
            url,
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=REQUEST_TIMEOUT,
        )
        return self._handle_response(response)

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def get_me(self) -> dict:
        """Fetch the ``/me`` resource for connection testing."""
        return self.get("/me")


class ARMClient:
    """Synchronous client for Azure Resource Manager API.

    Uses the same credential as GraphClient but targets the ARM endpoint
    to list Azure AI Services accounts (Foundry resources) and projects.
    """

    ARM_BASE = "https://management.azure.com"
    API_VERSION_COGNITIVE = "2024-10-01"
    API_VERSION_PROJECTS = "2025-09-01"

    def __init__(self, config: AzureConfig) -> None:
        self._config = config
        if config.client_id and config.client_secret:
            self._credential = ClientSecretCredential(
                tenant_id=config.tenant_id,
                client_id=config.client_id,
                client_secret=config.client_secret,
            )
        else:
            self._credential = DefaultAzureCredential()
        self._token: Optional[AccessToken] = None

    def _get_access_token(self) -> str:
        now = time.time()
        if self._token is None or self._token.expires_on - now < 300:
            self._token = self._credential.get_token(
                "https://management.azure.com/.default"
            )
        return self._token.token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

    def _get(self, url: str, params: dict = None) -> dict:
        response = httpx.get(
            url, headers=self._headers(), params=params, timeout=REQUEST_TIMEOUT,
        )
        if response.status_code >= 400:
            return {"value": []}
        return response.json()

    def _put(self, url: str, json_body: dict = None, params: dict = None) -> dict:
        last_exc = None
        for attempt in range(3):
            response = httpx.put(
                url, headers=self._headers(), json=json_body, params=params,
                timeout=90,
            )
            if response.status_code < 400:
                return response.json()
            # Retry on transient 500 errors
            if response.status_code in (500, 502, 503, 504) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            error_msg = response.text
            try:
                body = response.json()
                error_msg = body.get("error", {}).get("message", error_msg)
            except Exception:
                pass
            last_exc = Exception(f"ARM PUT failed ({response.status_code}): {error_msg}")
        raise last_exc

    def _delete(self, url: str, params: dict = None) -> dict:
        response = httpx.delete(
            url, headers=self._headers(), params=params, timeout=60,
        )
        if response.status_code == 204:
            return {}
        if response.status_code >= 400:
            error_msg = response.text
            try:
                body = response.json()
                error_msg = body.get("error", {}).get("message", error_msg)
            except Exception:
                pass
            raise Exception(f"ARM DELETE failed ({response.status_code}): {error_msg}")
        try:
            return response.json()
        except Exception:
            return {}

    def list_subscriptions(self) -> list:
        """List all accessible Azure subscriptions."""
        data = self._get(
            f"{self.ARM_BASE}/subscriptions",
            params={"api-version": "2022-01-01"},
        )
        return data.get("value", [])

    def list_cognitive_accounts(self, subscription_id: str) -> list:
        """List all Cognitive Services / AI Services accounts in a subscription."""
        data = self._get(
            f"{self.ARM_BASE}/subscriptions/{subscription_id}"
            f"/providers/Microsoft.CognitiveServices/accounts",
            params={"api-version": self.API_VERSION_COGNITIVE},
        )
        return data.get("value", [])

    def list_foundry_projects(self, subscription_id: str, resource_group: str, account_name: str) -> list:
        """List projects under a Cognitive Services account (Foundry resource)."""
        data = self._get(
            f"{self.ARM_BASE}/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
            f"/projects",
            params={"api-version": self.API_VERSION_PROJECTS},
        )
        return data.get("value", [])

    def create_foundry_project(
        self,
        subscription_id: str,
        resource_group: str,
        account_name: str,
        project_name: str,
        location: str,
        description: str = "",
    ) -> dict:
        """Create a project under a Cognitive Services account via ARM PUT."""
        url = (
            f"{self.ARM_BASE}/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
            f"/projects/{project_name}"
        )
        body: dict = {
            "identity": {"type": "SystemAssigned"},
            "location": location,
            "properties": {},
        }
        if description:
            body["properties"]["description"] = description
        return self._put(url, json_body=body, params={"api-version": self.API_VERSION_PROJECTS})

    def delete_foundry_project(
        self,
        subscription_id: str,
        resource_group: str,
        account_name: str,
        project_name: str,
    ) -> dict:
        """Delete a project under a Cognitive Services account via ARM DELETE."""
        url = (
            f"{self.ARM_BASE}/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
            f"/projects/{project_name}"
        )
        return self._delete(url, params={"api-version": self.API_VERSION_PROJECTS})
