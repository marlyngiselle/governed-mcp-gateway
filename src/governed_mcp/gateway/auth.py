"""OIDC bearer token verification for the Streamable HTTP transport.

Implements the MCP SDK's ``TokenVerifier`` protocol. The server acts as an OAuth 2.1
resource server only: it never issues tokens, it verifies them against the identity
provider's published keys (JWKS) and rejects anything that is not

* signed with an allowed asymmetric algorithm by a key in the JWKS (``alg: none`` and HMAC
  are refused, which closes the classic key-confusion attacks),
* issued by the configured issuer,
* addressed to this resource (``aud``),
* inside its validity window (``exp``, ``nbf``, ``iat``, with a small clock leeway),
* carrying a subject.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import anyio.to_thread
import jwt
from jwt import PyJWK, PyJWKClient, PyJWKSet
from mcp.server.auth.provider import AccessToken

log = logging.getLogger(__name__)

ALLOWED_ALGORITHMS: tuple[str, ...] = ("RS256", "PS256", "ES256", "EdDSA")


class KeySource(Protocol):
    def signing_key(self, token: str) -> PyJWK: ...


@dataclass(slots=True)
class StaticJWKS:
    """Keys loaded once from a JWKS document. Used in tests and air-gapped setups."""

    jwks: dict[str, Any]
    _keys: PyJWKSet = field(init=False)

    def __post_init__(self) -> None:
        self._keys = PyJWKSet.from_dict(self.jwks)

    @classmethod
    def from_file(cls, path: str | Path) -> StaticJWKS:
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def signing_key(self, token: str) -> PyJWK:
        kid = jwt.get_unverified_header(token).get("kid")
        for key in self._keys.keys:
            if key.key_id == kid:
                return key
        raise jwt.InvalidTokenError(f"no key with kid {kid!r} in JWKS")


@dataclass(slots=True)
class RemoteJWKS:
    """Keys fetched from the identity provider's ``jwks_uri`` and cached."""

    url: str
    lifespan_s: int = 300
    _client: PyJWKClient = field(init=False)

    def __post_init__(self) -> None:
        if not self.url.startswith("https://"):
            raise ValueError("JWKS URL must use https")
        self._client = PyJWKClient(self.url, cache_keys=True, lifespan=self.lifespan_s, timeout=5)

    def signing_key(self, token: str) -> PyJWK:
        return self._client.get_signing_key_from_jwt(token)


@dataclass(slots=True)
class JWTVerifier:
    issuer: str
    audience: str
    keys: KeySource
    algorithms: tuple[str, ...] = ALLOWED_ALGORITHMS
    leeway_s: int = 30

    def __post_init__(self) -> None:
        unsafe = {a for a in self.algorithms if a.lower() == "none" or a.upper().startswith("HS")}
        if unsafe:
            raise ValueError(f"refusing symmetric or empty algorithms: {sorted(unsafe)}")

    def verify(self, token: str) -> AccessToken | None:
        """Synchronous verification. Returns None for any invalid token, never raises."""
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in self.algorithms:
                raise jwt.InvalidAlgorithmError(f"algorithm {header.get('alg')!r} not allowed")
            key = self.keys.signing_key(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=list(self.algorithms),
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.leeway_s,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except (jwt.PyJWTError, ValueError) as exc:
            log.info("bearer token rejected: %s", type(exc).__name__)
            return None
        scope = claims.get("scope", "")
        scopes = scope.split() if isinstance(scope, str) else []
        client_id = str(claims.get("azp") or claims.get("client_id") or "unknown-client")
        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(claims["exp"]),
            resource=self.audience,
            subject=str(claims["sub"]),
            claims=claims,
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        # JWKS refresh may hit the network, so keep it off the event loop.
        return await anyio.to_thread.run_sync(self.verify, token)
