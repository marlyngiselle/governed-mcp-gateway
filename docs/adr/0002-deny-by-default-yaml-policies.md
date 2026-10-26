# ADR 0002: Deny-by-default role policies in YAML

Accepted in October 2026.

## Context

Access rules need to be reviewed by people who do not read Python, versioned with the code, and impossible to misread.

## Decision

One YAML file per role in `policies/`, validated by a strict pydantic model (unknown fields are an error). Four rules only: deny by default, explicit deny wins, writes need `allow_writes`, unknown roles get nothing. When a token carries several roles, the one with the highest `priority` applies.

## Consequences

- A policy change is a pull request with a readable diff, and CI rejects a malformed file before it ships.
- Glob patterns keep files short, at the cost of a new tool being reachable by any role whose pattern matches it. The deny list and `tools/list` filtering make that visible in review and in tests.
- No attribute-based conditions (time of day, resource tags). If they become necessary, a policy engine such as OPA can sit behind the same `decide()` interface.
