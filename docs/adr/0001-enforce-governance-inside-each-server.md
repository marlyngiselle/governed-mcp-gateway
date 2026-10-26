# ADR 0001: Enforce governance inside each MCP server

Accepted in October 2026.

## Context

Controls could live in a separate proxy that relays MCP traffic to unmodified servers, or in a library every server is built on.

## Decision

A shared library. Each server is a `GovernedServer`, and tools can only be registered through `governed_tool(access=...)`, which wraps them in the gateway pipeline.

## Consequences

- The gateway sees typed, validated arguments and the tool's declared access level, which a protocol proxy would have to infer from JSON.
- There is no network hop and no second process to secure, and stdio servers get the same controls as HTTP ones.
- Third-party servers that are not built on this library are not covered. For those, a proxy remains the right tool, and the same `PolicySet`, `Redactor` and `AuditLog` classes can be reused inside it.
