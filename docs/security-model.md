# Security model

## Assets and trust boundaries

| Asset | Why it matters |
| --- | --- |
| Write access to operational systems | A wrong ticket pages people, a wrong change breaks production |
| Secrets inside resource metadata and documents | Connection strings, keys and tokens leak through tool results |
| Personal data | Reporter and owner emails, payment data in free text |
| The audit trail | The only way to answer "who asked the assistant to do what" |

The assistant is treated as an untrusted intermediary. It acts for an authenticated user, but its next tool call may be shaped by text it read a second ago. Every control below holds even if the assistant is fully steered by an attacker.

## Threats

### 1. Prompt injection leading to tool misuse

Text planted in a runbook, ticket or web page tells the assistant to call a tool the user never asked for. `runbooks/legacy-batch-restart.md` contains such a payload on purpose, and `tests/test_tools.py::test_prompt_injection_in_a_runbook_cannot_turn_into_a_write` proves it cannot become a write.

### 2. Confused deputy

The assistant holds a broad credential and an attacker uses it to reach what they themselves could not. Here the gateway never acts with more than the caller's own role. Over HTTP the role comes from the caller's token, never from the server's configuration, and an unknown role gets nothing.

### 3. Data exfiltration

The assistant is coaxed into reading secrets and writing them somewhere visible, for example in a new ticket's description. Results are redacted before they leave the server, so the secret is never in the assistant's context to begin with.

### 4. Abuse and enumeration

A runaway agent loop or a script hammers tools to enumerate data. Per-client rate limits run before authorisation, so even denied probing is throttled.

### 5. Token forgery and replay against the HTTP transport

Unsigned tokens, tokens signed with HMAC using the public key, tokens for another audience or issuer, expired tokens.

## Controls

| # | Control | Mitigates | Where | Test |
| --- | --- | --- | --- | --- |
| C1 | Deny-by-default role policies, explicit deny wins | 1, 2 | `gateway/policy.py`, `policies/` | `test_policy.py` |
| C2 | Tools hidden from `tools/list` when the role cannot call them | 1 | `GovernedServer.list_tools` | `test_tools_list_is_filtered_by_role` |
| C3 | Write tools need `allow_writes` on the role and `confirm=true` on the call | 1, 2 | `Gateway._precheck` | `test_write_without_confirm_is_refused_then_succeeds_with_it` |
| C4 | Registration refuses write tools without a `confirm: bool = False` parameter, and refuses plain `@tool()` | 1 | `GovernedServer.governed_tool` | `test_registration.py` |
| C5 | Strict pydantic schemas on every argument (patterns, ranges, enums) | 1, 3 | `servers/*.py` | `test_schema_validation_rejects_malformed_input` |
| C6 | Severity ceiling: assistants cannot open sev1 | 1 | `servers/tickets.py` | `test_assistants_cannot_open_sev1` |
| C7 | Output redaction of secrets and PII | 3 | `gateway/redaction.py` | `test_redaction.py`, `test_secrets_and_pii_are_redacted_from_results` |
| C8 | Untrusted content labelled as such in runbook results and server instructions | 1 | `servers/runbooks.py` | `test_runbook_search_and_fetch` |
| C9 | Rate limit per client before authorisation | 4 | `gateway/ratelimit.py` | `test_ratelimit.py`, `test_rate_limit_applies_per_client` |
| C10 | JWT verification: JWKS, `iss`, `aud`, `exp`, `nbf`, `sub`, asymmetric algorithms only | 2, 5 | `gateway/auth.py` | `test_auth.py` |
| C11 | HTTP refuses to start without OIDC configured, no auth-off switch | 2, 5 | `app.build_http_app` | `test_http_refuses_to_start_without_oidc` |
| C12 | DNS rebinding protection on the HTTP endpoint | 5 | `app.build_http_app` | Configured, SDK behaviour |
| C13 | Audit record per call with hashed arguments, never clear text | All | `gateway/audit.py` | `test_audit.py` |
| C14 | Internal errors masked, details only in server logs | 3 | `Gateway.wrap` | `test_unexpected_errors_are_masked_and_audited` |
| C15 | Path traversal impossible in runbook fetch (slug pattern and resolved-path check) | 3 | `adapters/runbooks.py` | `test_schema_validation_rejects_malformed_input` |
| C16 | Container runs as UID 10001, read-only root, no capabilities, hashed dependency lock | All | `Dockerfile`, `docker-compose.yml` | CI `container` job |

## What this does not solve

| Gap | Why, and what to do |
| --- | --- |
| A user who approves a bad write | `confirm=true` proves the assistant asked, not that the human read carefully. Keep write tools narrow and their effects reversible |
| Injection that only changes read behaviour | A steered assistant can still read and summarise misleadingly within its role. Least privilege limits what it can read |
| Redaction of novel secret formats | Pattern matching is a safety net, not a vault. Keep secrets out of the systems the tools read |
| Rate limits across replicas | Buckets are per process. Put a shared store or the ingress in front for a fleet |
| Audit log integrity | Lines are append-only in process. Ship them to write-once storage to make them tamper-evident |
