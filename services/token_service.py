"""Service for Entra Agent ID token generation via Azure AD token endpoint.

References:
- Article 2: https://derkvanderwoude.medium.com/from-blueprint-to-token-how-entra-agent-identity-inheritance-really-works-fed114abe281
  Token flow: T1 (exchange), T2 (resource), T3 (agent user).
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from typing import Optional, Tuple

import jwt

from config.azure_config import AzureConfig
from models.blueprint import Blueprint, BlueprintPrincipal, CredentialType
from models.identity import AgentIdentity, AgentUser
from models.permission import EffectivePermissions
from models.token import TokenRequest, TokenResponse, JWTClaims
from services.cache import SessionCache
from services.graph_client import GraphClient


class TokenService:
    def __init__(
        self,
        graph: GraphClient,
        cache: SessionCache,
        config: AzureConfig,
    ):
        self._graph = graph
        self._cache = cache
        self._config = config

    # ── Request Builders ───────────────────────────────────────────────────

    def build_t1_request(
        self, blueprint: Blueprint, agent_identity: AgentIdentity
    ) -> TokenRequest:
        cred_display = self._credential_display(blueprint)
        req = TokenRequest(
            endpoint=f"https://login.microsoftonline.com/{blueprint.tenant_id}/oauth2/v2.0/token",
            grant_type="client_credentials",
            client_id=blueprint.app_id,
            scope="api://AzureADTokenExchange/.default",
            fmi_path=agent_identity.client_id,
            credential_display=cred_display,
        )
        if blueprint.credential_type == CredentialType.CLIENT_SECRET:
            req.client_secret = self._config.blueprint_client_secret
        else:
            req.client_assertion = cred_display
            req.client_assertion_type = (
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
            )
        return req

    def build_t2_request(
        self,
        t1_token: str,
        agent_identity: AgentIdentity,
        resource_scope: str = "https://graph.microsoft.com/.default",
    ) -> TokenRequest:
        return TokenRequest(
            endpoint=f"https://login.microsoftonline.com/{self._config.tenant_id}/oauth2/v2.0/token",
            grant_type="client_credentials",
            client_id=agent_identity.client_id,
            scope=resource_scope,
            client_assertion=self._truncate_token(t1_token),
            client_assertion_type="urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        )

    def build_t3_request(
        self,
        t1_token: str,
        t2_token: str,
        agent_identity: AgentIdentity,
        agent_user: AgentUser,
        resource_scope: str = "https://graph.microsoft.com/.default",
    ) -> TokenRequest:
        return TokenRequest(
            endpoint=f"https://login.microsoftonline.com/{self._config.tenant_id}/oauth2/v2.0/token",
            grant_type="urn:ietf:params:oauth:grant-type:jwt-bearer",
            client_id=agent_identity.client_id,
            scope=resource_scope,
            client_assertion=self._truncate_token(t1_token),
            client_assertion_type="urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            requested_token_use="user_fic",
            user_id=agent_user.id,
            user_federated_identity_credential=self._truncate_token(t2_token),
        )

    # ── Token Generators ───────────────────────────────────────────────────

    def generate_t1(
        self,
        blueprint: Blueprint,
        agent_identity: AgentIdentity,
    ) -> Tuple[TokenResponse, JWTClaims]:
        form_data = {
            "grant_type": "client_credentials",
            "client_id": blueprint.app_id,
            "scope": "api://AzureADTokenExchange/.default",
            "fmi_path": agent_identity.client_id,
        }
        if blueprint.credential_type == CredentialType.CLIENT_SECRET:
            secret = self._config.blueprint_client_secret
            if not secret:
                raise ValueError("BLUEPRINT_CLIENT_SECRET not set in .env")
            form_data["client_secret"] = secret
        elif blueprint.credential_type == CredentialType.CERTIFICATE:
            assertion = self._build_cert_assertion(blueprint)
            form_data["client_assertion"] = assertion
            form_data["client_assertion_type"] = (
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
            )

        data = self._graph.post_token_endpoint(self._config.tenant_id, form_data)
        access_token = data["access_token"]
        claims = self._decode_jwt(access_token)

        return (
            TokenResponse(
                access_token=access_token,
                scope=data.get("scope", "api://AzureADTokenExchange/.default"),
                token_type=data.get("token_type", "Bearer"),
                expires_in=data.get("expires_in", 3600),
            ),
            JWTClaims(
                **{k: v for k, v in claims.items() if k in JWTClaims.__dataclass_fields__}
            ),
        )

    def generate_t2(
        self,
        blueprint: Blueprint,
        agent_identity: AgentIdentity,
        effective_permissions: EffectivePermissions,
        resource_scope: str = "https://graph.microsoft.com/.default",
        t1_access_token: Optional[str] = None,
    ) -> Tuple[TokenResponse, JWTClaims]:
        if not t1_access_token:
            raise ValueError("t1_access_token is required for T2 generation")

        form_data = {
            "grant_type": "client_credentials",
            "client_id": agent_identity.client_id,
            "scope": resource_scope,
            "client_assertion": t1_access_token,
            "client_assertion_type": (
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
            ),
        }
        data = self._graph.post_token_endpoint(self._config.tenant_id, form_data)
        access_token = data["access_token"]
        claims = self._decode_jwt(access_token)

        return (
            TokenResponse(
                access_token=access_token,
                scope=data.get("scope", resource_scope),
                token_type=data.get("token_type", "Bearer"),
                expires_in=data.get("expires_in", 3600),
            ),
            JWTClaims(
                **{k: v for k, v in claims.items() if k in JWTClaims.__dataclass_fields__}
            ),
        )

    def generate_t3(
        self,
        blueprint: Blueprint,
        agent_identity: AgentIdentity,
        agent_user: AgentUser,
        resource_scope: str = "https://graph.microsoft.com/.default",
        t1_access_token: Optional[str] = None,
        t2_access_token: Optional[str] = None,
    ) -> Tuple[TokenResponse, JWTClaims]:
        if not t1_access_token:
            raise ValueError("t1_access_token is required for T3 generation")
        if not t2_access_token:
            raise ValueError("t2_access_token is required for T3 generation")

        form_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "client_id": agent_identity.client_id,
            "scope": resource_scope,
            "client_assertion": t1_access_token,
            "client_assertion_type": (
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
            ),
            "requested_token_use": "user_fic",
            "user_id": agent_user.id,
            "user_federated_identity_credential": t2_access_token,
        }
        data = self._graph.post_token_endpoint(self._config.tenant_id, form_data)
        access_token = data["access_token"]
        claims = self._decode_jwt(access_token)

        return (
            TokenResponse(
                access_token=access_token,
                scope=data.get("scope", resource_scope),
                token_type=data.get("token_type", "Bearer"),
                expires_in=data.get("expires_in", 3600),
            ),
            JWTClaims(
                **{k: v for k, v in claims.items() if k in JWTClaims.__dataclass_fields__}
            ),
        )

    # ── Sign-in Log ────────────────────────────────────────────────────────

    def get_sign_in_log_entries(
        self,
        blueprint: Blueprint,
        agent_identity: AgentIdentity,
        resource_scope: str = "https://graph.microsoft.com/.default",
    ) -> list:
        resource = resource_scope.replace("/.default", "")
        from services.blueprint_service import BlueprintService
        bp_svc = BlueprintService(self._graph, self._cache, self._config)
        principals = bp_svc.get_principals_for_blueprint(blueprint.id)
        principal = principals[0] if principals else None

        return [
            {
                "entry": "T1 (Exchange)",
                "principal": blueprint.display_name,
                "principal_id": principal.id if principal else blueprint.app_id,
                "resource": "api://AzureADTokenExchange",
                "status": "Success",
                "auth_method": blueprint.credential_type.value,
            },
            {
                "entry": "TR (Resource)",
                "principal": agent_identity.display_name,
                "principal_id": agent_identity.id,
                "resource": resource,
                "status": "Success",
                "auth_method": "jwt-bearer (via T1)",
            },
        ]

    # ── JWT Decoding ───────────────────────────────────────────────────────

    def decode_jwt(self, token: str) -> Optional[dict]:
        return self._decode_jwt(token)

    def _decode_jwt(self, token: str) -> dict:
        try:
            return jwt.decode(token, options={"verify_signature": False})
        except Exception:
            return {}

    # ── Certificate Assertion ──────────────────────────────────────────────

    def _build_cert_assertion(self, blueprint: Blueprint) -> str:
        cert_path = self._config.blueprint_certificate_path
        if not cert_path:
            raise ValueError("BLUEPRINT_CERTIFICATE_PATH not set in .env")

        import time as _time
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        from cryptography.x509 import load_pem_x509_certificate

        now = int(_time.time())

        with open(cert_path, "rb") as f:
            cert_data = f.read()

        private_key = load_pem_private_key(cert_data, password=None)
        cert = load_pem_x509_certificate(cert_data)
        x5t = (
            base64.urlsafe_b64encode(cert.fingerprint(hashlib.sha1()))
            .rstrip(b"=")
            .decode()
        )

        payload = {
            "aud": f"https://login.microsoftonline.com/{self._config.tenant_id}/oauth2/v2.0/token",
            "iss": blueprint.app_id,
            "sub": blueprint.app_id,
            "jti": str(uuid.uuid4()),
            "nbf": now,
            "exp": now + 600,
        }

        return jwt.encode(
            payload,
            private_key,
            algorithm="RS256",
            headers={"x5t": x5t},
        )

    # ── Internal Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _credential_display(blueprint: Blueprint) -> str:
        if blueprint.credential_type == CredentialType.MANAGED_IDENTITY:
            return "<MANAGED_IDENTITY_ASSERTION>"
        elif blueprint.credential_type == CredentialType.CERTIFICATE:
            return "<CERTIFICATE_SIGNED_ASSERTION>"
        else:
            return "<CLIENT_SECRET>"

    @staticmethod
    def _auth_class_ref(cred_type: CredentialType) -> str:
        if cred_type == CredentialType.CLIENT_SECRET:
            return "1"
        return "2"

    @staticmethod
    def _truncate_token(token: str) -> str:
        if len(token) > 40:
            return f"{token[:20]}...{token[-10:]}"
        return token
