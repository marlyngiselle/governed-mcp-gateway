"""Runtime configuration, read from environment variables with the GOVERNED_MCP_ prefix."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PREFIX = "GOVERNED_MCP_"
LOCAL_HOSTS: tuple[str, ...] = ("127.0.0.1:*", "localhost:*", "[::1]:*")


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(PREFIX + name)
    return value if value not in (None, "") else default


@dataclass(frozen=True, slots=True)
class Settings:
    policy_dir: Path = Path("policies")
    runbook_dir: Path = Path("runbooks")
    audit_log: str = "-"
    audit_hash_key: str | None = None
    # stdio identity: the OS user who launched the process and the role they chose.
    local_principal: str = "local-user"
    local_role: str = "reader"
    # HTTP / OIDC
    host: str = "127.0.0.1"
    port: int = 8000
    issuer: str | None = None
    audience: str | None = None
    jwks_url: str | None = None
    jwks_file: Path | None = None
    role_claim: str = "roles"
    resource_url: str | None = None
    allowed_hosts: tuple[str, ...] = LOCAL_HOSTS

    @classmethod
    def from_env(cls) -> Settings:
        jwks_file = _env("JWKS_FILE")
        hosts = _env("ALLOWED_HOSTS")
        return cls(
            policy_dir=Path(_env("POLICY_DIR", "policies") or "policies"),
            runbook_dir=Path(_env("RUNBOOK_DIR", "runbooks") or "runbooks"),
            audit_log=_env("AUDIT_LOG", "-") or "-",
            audit_hash_key=_env("AUDIT_HASH_KEY"),
            local_principal=_env("PRINCIPAL", os.environ.get("USER", "local-user")) or "local-user",
            local_role=_env("ROLE", "reader") or "reader",
            host=_env("HOST", "127.0.0.1") or "127.0.0.1",
            port=int(_env("PORT", "8000") or "8000"),
            issuer=_env("ISSUER"),
            audience=_env("AUDIENCE"),
            jwks_url=_env("JWKS_URL"),
            jwks_file=Path(jwks_file) if jwks_file else None,
            role_claim=_env("ROLE_CLAIM", "roles") or "roles",
            resource_url=_env("RESOURCE_URL"),
            allowed_hosts=tuple(h.strip() for h in hosts.split(",")) if hosts else LOCAL_HOSTS,
        )
