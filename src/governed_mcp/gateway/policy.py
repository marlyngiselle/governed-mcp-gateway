"""Role policies loaded from YAML.

The rules are deliberately small so a reviewer can hold them in their head:

1. Deny by default. A tool is reachable only if a role pattern allows it.
2. An explicit deny pattern wins over any allow pattern.
3. A write tool also needs ``allow_writes: true`` on the role.
4. An unknown role is denied everything.

Patterns are ``<server>.<tool>`` globs, for example ``tickets.*`` or ``*.get_*``.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

Access = Literal["read", "write"]


class RateLimit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requests_per_minute: int = Field(gt=0, le=10_000)
    burst: int = Field(gt=0, le=1_000)


ToolPattern = Annotated[str, Field(pattern=r"^[a-z0-9*?_.-]{1,80}$")]


class ToolRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allow: tuple[ToolPattern, ...] = Field(default=(), description="Glob patterns over <server>.<tool>.")
    deny: tuple[ToolPattern, ...] = Field(default=(), description="Glob patterns that override allow.")


class RolePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(pattern=r"^[a-z][a-z0-9-]{1,31}$")
    description: str = Field(min_length=1, max_length=300)
    priority: int = Field(ge=0, le=1000, description="Higher wins when a caller holds several roles.")
    allow_writes: bool = False
    tools: ToolRules
    rate_limit: RateLimit


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    reason: str


class PolicySet:
    """All role policies known to a gateway instance."""

    def __init__(self, roles: list[RolePolicy]) -> None:
        names = [r.role for r in roles]
        if len(names) != len(set(names)):
            raise ValueError("duplicate role names in policy set")
        if not roles:
            raise ValueError("a policy set needs at least one role")
        self._roles = {r.role: r for r in roles}

    @classmethod
    def load_dir(cls, path: str | Path) -> PolicySet:
        directory = Path(path)
        files = sorted(directory.glob("*.yaml"))
        if not files:
            raise FileNotFoundError(f"no *.yaml policy files in {directory}")
        roles = [RolePolicy.model_validate(yaml.safe_load(f.read_text(encoding="utf-8"))) for f in files]
        return cls(roles)

    @property
    def roles(self) -> dict[str, RolePolicy]:
        return dict(self._roles)

    def get(self, role: str | None) -> RolePolicy | None:
        return self._roles.get(role) if role else None

    def select_role(self, candidates: list[str]) -> str | None:
        """Pick the highest priority role the policy set knows from a token's role claim."""
        known = [self._roles[c] for c in candidates if c in self._roles]
        if not known:
            return None
        return max(known, key=lambda r: r.priority).role

    def decide(self, role: str | None, tool: str, access: Access) -> Decision:
        policy = self.get(role)
        if policy is None:
            return Decision(False, f"role {role!r} is not defined in the policy set")
        if any(fnmatchcase(tool, p) for p in policy.tools.deny):
            return Decision(False, f"role {policy.role!r} explicitly denies {tool!r}")
        if not any(fnmatchcase(tool, p) for p in policy.tools.allow):
            return Decision(False, f"role {policy.role!r} does not allow {tool!r}")
        if access == "write" and not policy.allow_writes:
            return Decision(False, f"role {policy.role!r} is read-only and {tool!r} is a write tool")
        return Decision(True, f"allowed by role {policy.role!r}")
