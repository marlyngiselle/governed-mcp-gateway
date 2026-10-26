"""cloud-inventory: read-only questions about cloud resources and what they cost."""

from typing import Annotated, Any

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from governed_mcp.adapters.cloud import FakeCloudInventory, ResourceType
from governed_mcp.config import Settings
from governed_mcp.gateway import Gateway, GovernedServer

TagKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,31}$", description="Tag name, e.g. env or team.")]
TagValue = Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]{1,64}$", description="Exact tag value to match.")]
Region = Annotated[str, Field(pattern=r"^[a-z0-9]{3,32}$", description="Region name, e.g. westeurope.")]


def build(
    gateway: Gateway,
    settings: Settings,
    *,
    inventory: FakeCloudInventory | None = None,
    **server_options: Any,
) -> GovernedServer:
    inv = inventory or FakeCloudInventory()
    server = GovernedServer(
        "cloud-inventory",
        gateway=gateway,
        **server_options,
        instructions="Read-only inventory and monthly cost of cloud resources. Costs are in EUR.",
    )

    @server.governed_tool(access="read", title="List resources")
    async def list_resources(
        resource_type: ResourceType | None = None,
        tag_key: TagKey | None = None,
        tag_value: TagValue | None = None,
        region: Region | None = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 25,
    ) -> dict[str, Any]:
        """List cloud resources, optionally filtered by type, region and one tag."""
        if tag_value is not None and tag_key is None:
            raise ToolError("tag_value needs tag_key")
        found = inv.query(resource_type, tag_key, tag_value, region)
        return {
            "total": len(found),
            "returned": min(len(found), limit),
            "resources": [r.model_dump(exclude={"properties"}) for r in found[:limit]],
        }

    @server.governed_tool(access="read", title="Get resource")
    async def get_resource(
        resource_id: Annotated[str, Field(pattern=r"^res-\d{4}$", description="Resource id, e.g. res-0004.")],
    ) -> dict[str, Any]:
        """Get one resource with its properties. Secrets in properties are redacted."""
        resource = inv.get(resource_id)
        if resource is None:
            raise ToolError(f"resource {resource_id} not found")
        return resource.model_dump()

    @server.governed_tool(access="read", title="Monthly cost by tag")
    async def cost_by_tag(tag_key: TagKey) -> dict[str, Any]:
        """Sum last month's cost per value of a tag, for showback. Untagged spend is reported apart."""
        groups, untagged = inv.cost_by_tag(tag_key)
        return {
            "tag_key": tag_key,
            "period": inv.period,
            "currency": inv.currency,
            "groups": [g.model_dump() for g in groups],
            "untagged": untagged.model_dump(),
            "total": round(sum(g.monthly_cost for g in groups) + untagged.monthly_cost, 2),
        }

    return server
