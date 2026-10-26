# ADR 0003: Stateless Streamable HTTP as an OAuth resource server

Accepted in October 2026.

## Context

Remote MCP servers need caller identity. The SDK supports acting as a full authorization server or as a resource server that only verifies tokens.

## Decision

Resource server only. Tokens come from the organisation's identity provider and are verified against its JWKS with an allowlist of asymmetric algorithms. The HTTP transport runs stateless with JSON responses and refuses to start without issuer, audience and keys.

## Consequences

- No credentials or client registrations are stored here, and identity lifecycle stays with the identity provider.
- Any replica can serve any request, so the servers scale behind a plain load balancer. The trade-off is no server-initiated streams, which none of these tools need.
- Local development needs a signing key. `governed-mcp dev-keys` creates one in a git-ignored folder, and nothing in the server can tell a dev key from a production one except the JWKS it is given.
