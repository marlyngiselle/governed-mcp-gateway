"""Call one tool on a governed server over Streamable HTTP with an MCP client session.

export GOVERNED_MCP_TOKEN=$(governed-mcp dev-token --role operator)
python examples/call_tool.py http://127.0.0.1:8003/mcp search_tickets '{"limit": 2}'
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def main(url: str, tool: str, arguments: dict[str, object]) -> int:
    token = os.environ["GOVERNED_MCP_TOKEN"]
    http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, trust_env=False, timeout=15)
    async with Client(streamable_http_client(url, http_client=http)) as client:
        tools = await client.list_tools()
        print("tools visible to this token:", ", ".join(t.name for t in tools.tools))
        result = await client.call_tool(tool, arguments)
    if result.is_error:
        print("error:", " ".join(getattr(c, "text", "") for c in result.content))
        return 1
    print(json.dumps(result.structured_content, indent=2))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2], args)))
