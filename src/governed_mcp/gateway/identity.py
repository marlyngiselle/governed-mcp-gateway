"""Who is calling.

Two sources, one shape:

* ``LocalIdentity`` for stdio, where the server runs as a child process of the MCP client
  and the operating system user who launched it is the principal.
* ``BearerIdentity`` for Streamable HTTP, where the identity comes from a verified OIDC
  access token and the role from one of its claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from mcp.server.auth.middleware.auth_context import get_access_token

from governed_mcp.gateway.policy import PolicySet


@dataclass(frozen=True, slots=True)
class Identity:
    principal: str
    client_id: str
    role: str | None
    source: Literal["local", "oidc"]

    @property
    def rate_key(self) -> str:
        return f"{self.client_id}|{self.principal}"


class IdentityResolver(Protocol):
    def current(self) -> Identity | None: ...


@dataclass(frozen=True, slots=True)
class LocalIdentity:
    """A fixed identity, configured by whoever launches the stdio process."""

    principal: str
    role: str
    client_id: str = "stdio"

    def current(self) -> Identity | None:
        return Identity(self.principal, self.client_id, self.role, "local")


@dataclass(frozen=True, slots=True)
class BearerIdentity:
    """Reads the access token the SDK's bearer middleware verified for this request."""

    policy: PolicySet
    role_claim: str = "roles"

    def current(self) -> Identity | None:
        token = get_access_token()
        if token is None:
            return None
        claims = token.claims or {}
        raw = claims.get(self.role_claim, [])
        candidates = [raw] if isinstance(raw, str) else [str(r) for r in raw if isinstance(r, str)]
        principal = token.subject or token.client_id
        return Identity(principal, token.client_id, self.policy.select_role(candidates), "oidc")
