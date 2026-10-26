# Client configuration

Most MCP clients read a JSON file with an `mcpServers` map. Field names below follow the common format. Check your client's documentation for the exact file location.

## stdio: the client launches the server

The example assumes the repository is cloned to `/opt/governed-mcp-gateway` with its virtualenv in `.venv`. The role is chosen by whoever configures the client, so give each person the least privileged role that does the job.

```json
{
  "mcpServers": {
    "runbooks": {
      "command": "/opt/governed-mcp-gateway/.venv/bin/governed-mcp",
      "args": ["serve", "runbooks"],
      "env": {
        "GOVERNED_MCP_ROLE": "reader",
        "GOVERNED_MCP_POLICY_DIR": "/opt/governed-mcp-gateway/policies",
        "GOVERNED_MCP_RUNBOOK_DIR": "/opt/governed-mcp-gateway/runbooks",
        "GOVERNED_MCP_AUDIT_LOG": "/opt/governed-mcp-gateway/.dev/audit-runbooks.jsonl"
      }
    },
    "tickets": {
      "command": "/opt/governed-mcp-gateway/.venv/bin/governed-mcp",
      "args": ["serve", "tickets"],
      "env": {
        "GOVERNED_MCP_ROLE": "operator",
        "GOVERNED_MCP_POLICY_DIR": "/opt/governed-mcp-gateway/policies",
        "GOVERNED_MCP_AUDIT_LOG": "/opt/governed-mcp-gateway/.dev/audit-tickets.jsonl"
      }
    }
  }
}
```

Never point the audit log at stdout on stdio, because stdout carries the protocol.

## Streamable HTTP: the client connects to a running server

Start the servers with `docker compose up --build` (ports 8001 to 8003), then mint a token with `governed-mcp dev-token --role operator`. In production the token comes from your identity provider through the client's OAuth flow; the server publishes its protected resource metadata at `/.well-known/oauth-protected-resource/mcp` so clients can discover the issuer.

```json
{
  "mcpServers": {
    "cloud-inventory": {
      "type": "http",
      "url": "http://localhost:8001/mcp",
      "headers": { "Authorization": "Bearer ${GOVERNED_MCP_TOKEN}" }
    },
    "runbooks": {
      "type": "http",
      "url": "http://localhost:8002/mcp",
      "headers": { "Authorization": "Bearer ${GOVERNED_MCP_TOKEN}" }
    },
    "tickets": {
      "type": "http",
      "url": "http://localhost:8003/mcp",
      "headers": { "Authorization": "Bearer ${GOVERNED_MCP_TOKEN}" }
    }
  }
}
```

## Environment variables

| Variable | Default | Used by |
| --- | --- | --- |
| `GOVERNED_MCP_POLICY_DIR` | `policies` | both |
| `GOVERNED_MCP_RUNBOOK_DIR` | `runbooks` | both |
| `GOVERNED_MCP_AUDIT_LOG` | `-` (stderr) | both |
| `GOVERNED_MCP_AUDIT_HASH_KEY` | unset (plain SHA-256) | both, switches argument hashes to HMAC-SHA256 |
| `GOVERNED_MCP_ROLE` | `reader` | stdio |
| `GOVERNED_MCP_PRINCIPAL` | `$USER` | stdio |
| `GOVERNED_MCP_HOST`, `GOVERNED_MCP_PORT` | `127.0.0.1`, `8000` | HTTP |
| `GOVERNED_MCP_ISSUER`, `GOVERNED_MCP_AUDIENCE` | required | HTTP |
| `GOVERNED_MCP_JWKS_URL` or `GOVERNED_MCP_JWKS_FILE` | required, one of them | HTTP |
| `GOVERNED_MCP_ROLE_CLAIM` | `roles` | HTTP |
| `GOVERNED_MCP_RESOURCE_URL` | `http://<host>:<port>/mcp` | HTTP, advertised in resource metadata |
| `GOVERNED_MCP_ALLOWED_HOSTS` | `127.0.0.1:*,localhost:*,[::1]:*` | HTTP, DNS rebinding protection |
