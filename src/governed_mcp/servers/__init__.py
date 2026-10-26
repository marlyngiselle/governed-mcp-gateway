"""The example MCP servers. Each builder takes a gateway and returns a ``GovernedServer``."""

from __future__ import annotations

from typing import Any, Protocol

from governed_mcp.config import Settings
from governed_mcp.gateway import Gateway, GovernedServer
from governed_mcp.servers.cloud_inventory import build as build_cloud_inventory
from governed_mcp.servers.runbooks import build as build_runbooks
from governed_mcp.servers.tickets import build as build_tickets


class Builder(Protocol):
    def __call__(self, gateway: Gateway, settings: Settings, **server_options: Any) -> GovernedServer: ...


REGISTRY: dict[str, Builder] = {
    "cloud-inventory": build_cloud_inventory,
    "runbooks": build_runbooks,
    "tickets": build_tickets,
}

__all__ = ["REGISTRY", "Builder"]
