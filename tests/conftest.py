from __future__ import annotations

import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from governed_mcp.config import Settings
from governed_mcp.gateway import AuditLog, Gateway, GovernedServer, PolicySet
from governed_mcp.gateway.identity import LocalIdentity
from governed_mcp.servers import REGISTRY

ROOT = Path(__file__).resolve().parent.parent
POLICIES = ROOT / "policies"
RUNBOOKS = ROOT / "runbooks"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def policy() -> PolicySet:
    return PolicySet.load_dir(POLICIES)


@pytest.fixture
def settings() -> Settings:
    return Settings(policy_dir=POLICIES, runbook_dir=RUNBOOKS)


@dataclass
class Harness:
    server: GovernedServer
    gateway: Gateway
    sink: io.StringIO

    def audit(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.sink.getvalue().splitlines()]


@pytest.fixture
def make(policy: PolicySet, settings: Settings) -> Callable[..., Harness]:
    def factory(
        server: str, role: str = "reader", principal: str = "alex@example.test", **kw: Any
    ) -> Harness:
        sink = io.StringIO()
        gateway = Gateway(
            policy=policy,
            identity=LocalIdentity(principal=principal, role=role),
            audit=AuditLog(sink),
            **kw,
        )
        return Harness(REGISTRY[server](gateway, settings), gateway, sink)

    return factory
