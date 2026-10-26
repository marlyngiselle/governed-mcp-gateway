# Add a new tool in three steps

The example adds `get_cost_anomalies` to `cloud-inventory`.

## 1. Write the tool with strict arguments

In `src/governed_mcp/servers/cloud_inventory.py`, inside `build()`.

```python
@server.governed_tool(access="read", title="Cost anomalies")
async def get_cost_anomalies(
    threshold_pct: Annotated[
        int, Field(ge=10, le=500, description="Minimum month-over-month increase.")
    ] = 50,
) -> dict[str, Any]:
    """List resources whose cost grew more than threshold_pct since last month."""
    return {"threshold_pct": threshold_pct, "resources": inv.anomalies(threshold_pct)}
```

The gateway enforces three rules at registration, so you cannot forget them.

| Rule | Why |
| --- | --- |
| Use `governed_tool`, not `tool` | `tool()` raises, so nothing bypasses the gateway |
| The function is `async` | One execution model, no blocking calls on the event loop |
| A `write` tool declares `confirm: bool = False` | The gateway refuses the call unless the assistant sends `confirm=true` |

Constrain every argument with `Annotated[..., Field(...)]`. The schema is what the assistant sees, and it is the first line of defence.

## 2. Allow it in the policies

Patterns are `<server>.<tool>` globs. `cloud-inventory.*` already covers the new tool for all three example roles. To keep it from readers, add a deny pattern.

```yaml
# policies/reader.yaml
tools:
  deny:
    - "cloud-inventory.cost_by_tag"
    - "cloud-inventory.get_cost_anomalies"
```

## 3. Test it through a real MCP client session

```python
async def test_reader_cannot_see_anomalies(make: Make) -> None:
    async with Client(make("cloud-inventory", role="reader").server) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        result = await c.call_tool("get_cost_anomalies", {})
    assert "get_cost_anomalies" not in names
    assert result.is_error
```

Then run `pytest`. Redaction and audit apply to the new tool automatically.
