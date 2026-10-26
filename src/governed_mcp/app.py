"""Wiring: settings in, a governed server and its transport out."""

from __future__ import annotations

from typing import Literal

from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from governed_mcp.config import Settings
from governed_mcp.gateway import AuditLog, Gateway, GovernedServer, PolicySet
from governed_mcp.gateway.audit import ArgsHasher
from governed_mcp.gateway.auth import JWTVerifier, KeySource, RemoteJWKS, StaticJWKS
from governed_mcp.gateway.identity import BearerIdentity, IdentityResolver, LocalIdentity
from governed_mcp.servers import REGISTRY

Transport = Literal["stdio", "http"]


class ConfigError(RuntimeError):
    pass


def build_gateway(settings: Settings, transport: Transport) -> Gateway:
    policy = PolicySet.load_dir(settings.policy_dir)
    identity: IdentityResolver
    if transport == "stdio":
        if policy.get(settings.local_role) is None:
            raise ConfigError(
                f"GOVERNED_MCP_ROLE={settings.local_role!r} is not a role in {settings.policy_dir}"
            )
        identity = LocalIdentity(principal=settings.local_principal, role=settings.local_role)
    else:
        identity = BearerIdentity(policy=policy, role_claim=settings.role_claim)
    key = settings.audit_hash_key.encode() if settings.audit_hash_key else None
    return Gateway(
        policy=policy, identity=identity, audit=AuditLog(settings.audit_log), hasher=ArgsHasher(key)
    )


def build_server(name: str, settings: Settings, transport: Transport) -> GovernedServer:
    if name not in REGISTRY:
        raise ConfigError(f"unknown server {name!r}; choose one of {sorted(REGISTRY)}")
    return REGISTRY[name](build_gateway(settings, transport), settings)


def build_verifier(settings: Settings) -> JWTVerifier:
    if not settings.issuer or not settings.audience:
        raise ConfigError("HTTP transport needs GOVERNED_MCP_ISSUER and GOVERNED_MCP_AUDIENCE")
    keys: KeySource
    if settings.jwks_file:
        keys = StaticJWKS.from_file(settings.jwks_file)
    elif settings.jwks_url:
        keys = RemoteJWKS(settings.jwks_url)
    else:
        raise ConfigError("HTTP transport needs GOVERNED_MCP_JWKS_URL or GOVERNED_MCP_JWKS_FILE")
    return JWTVerifier(issuer=settings.issuer, audience=settings.audience, keys=keys)


def build_http_app(name: str, settings: Settings) -> Starlette:
    """A Streamable HTTP app that refuses to start without OIDC configured.

    There is deliberately no "auth off" switch: an unauthenticated tool gateway is the
    exact thing this project exists to prevent.
    """
    verifier = build_verifier(settings)
    if name not in REGISTRY:
        raise ConfigError(f"unknown server {name!r}; choose one of {sorted(REGISTRY)}")
    resource_url = settings.resource_url or f"http://{settings.host}:{settings.port}/mcp"
    auth = AuthSettings(
        issuer_url=AnyHttpUrl(settings.issuer or ""),
        resource_server_url=AnyHttpUrl(resource_url),
        # The verifier checks `aud` itself against GOVERNED_MCP_AUDIENCE.
        validate_token_resource=False,
    )
    server = REGISTRY[name](build_gateway(settings, "http"), settings, auth=auth, token_verifier=verifier)

    async def healthz(_: Request) -> Response:
        return JSONResponse({"status": "ok", "server": name})

    server.custom_route("/healthz", methods=["GET"])(healthz)

    return server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(settings.allowed_hosts),
            allowed_origins=[f"http://{h}" for h in settings.allowed_hosts],
        ),
        host=settings.host,
    )
