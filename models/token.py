"""Data models for Token Requests, Responses, and JWT Claims.

References:
- https://derkvanderwoude.medium.com/from-blueprint-to-token-how-entra-agent-identity-inheritance-really-works-fed114abe281
  Key insight: T2/TR tokens include `xms_par_app_azp` claim confirming parent-child
  relationship, and permissions are dynamically merged at token issuance time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TokenRequest:
    endpoint: str
    grant_type: str
    client_id: str
    scope: str
    client_assertion: str = ""
    client_assertion_type: str = ""
    fmi_path: str = ""
    requested_token_use: str = ""
    user_id: str = ""
    user_federated_identity_credential: str = ""
    credential_display: str = ""
    # For client_secret-based auth (dev only)
    client_secret: str = ""

    def to_form_params(self) -> dict:
        """Return non-empty parameters as a dict for display."""
        params = {
            "grant_type": self.grant_type,
            "client_id": self.client_id,
            "scope": self.scope,
        }
        if self.client_secret:
            params["client_secret"] = self.client_secret
        if self.client_assertion:
            params["client_assertion"] = self.client_assertion
        if self.client_assertion_type:
            params["client_assertion_type"] = self.client_assertion_type
        if self.fmi_path:
            params["fmi_path"] = self.fmi_path
        if self.requested_token_use:
            params["requested_token_use"] = self.requested_token_use
        if self.user_id:
            params["user_id"] = self.user_id
        if self.user_federated_identity_credential:
            params["user_federated_identity_credential"] = (
                self.user_federated_identity_credential
            )
        return params


@dataclass
class TokenResponse:
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    scope: str = ""


@dataclass
class JWTClaims:
    iss: str = ""
    sub: str = ""
    aud: str = ""
    iat: int = 0
    exp: int = 0
    nbf: int = 0
    roles: List[str] = field(default_factory=list)
    scp: str = ""
    idtyp: str = "app"
    azp: str = ""
    azpacr: str = "2"
    tid: str = ""
    oid: str = ""
    app_displayname: str = ""
    upn: Optional[str] = None
    # From Article 2: appid claim (agent identity's AppId in TR tokens)
    appid: Optional[str] = None
    # From Article 2: xms_par_app_azp — blueprint AppId confirming parent-child relationship
    # This is the KEY claim that proves the token was issued via blueprint delegation
    xms_par_app_azp: Optional[str] = None

    def to_dict(self) -> dict:
        """Return claims as a dict, excluding None values."""
        d = {
            "iss": self.iss,
            "sub": self.sub,
            "aud": self.aud,
            "iat": self.iat,
            "exp": self.exp,
            "nbf": self.nbf,
            "idtyp": self.idtyp,
            "azp": self.azp,
            "azpacr": self.azpacr,
            "tid": self.tid,
            "oid": self.oid,
            "app_displayname": self.app_displayname,
        }
        if self.roles:
            d["roles"] = self.roles
        if self.scp:
            d["scp"] = self.scp
        if self.upn is not None:
            d["upn"] = self.upn
        if self.appid is not None:
            d["appid"] = self.appid
        if self.xms_par_app_azp is not None:
            d["xms_par_app_azp"] = self.xms_par_app_azp
        return d
