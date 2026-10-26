"""The gateway: one choke point between an MCP tool call and the system behind it.

Every governed tool call runs the same pipeline, in this order:

1. Authenticate. No identity, no call.
2. Rate limit per client, before anything else, so probing is throttled too.
3. Authorise against the caller's role policy (deny by default).
4. Confirm. A write tool runs only with ``confirm=true``.
5. Execute the tool. Arguments were already validated by the SDK against the tool's
   pydantic schema, so the tool body never sees malformed input.
6. Redact secrets and personal data from the result.
7. Audit. One JSON line per call, allowed or denied, with latency.
"""

from __future__ import annotations

import contextvars
import functools
import inspect
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal, ParamSpec, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import Tool as MCPTool
from mcp.types import ToolAnnotations

from governed_mcp.gateway.audit import ArgsHasher, AuditLog, AuditRecord
from governed_mcp.gateway.identity import Identity, IdentityResolver
from governed_mcp.gateway.policy import Decision, PolicySet
from governed_mcp.gateway.ratelimit import RateLimiter
from governed_mcp.gateway.redaction import Redactor

Access = Literal["read", "write"]
CONFIRM_PARAM = "confirm"

P = ParamSpec("P")
R = TypeVar("R")
ToolFn = Callable[P, Awaitable[R]]

log = logging.getLogger(__name__)

_current_identity: contextvars.ContextVar[Identity | None] = contextvars.ContextVar(
    "governed_mcp_identity", default=None
)


def current_identity() -> Identity:
    """The identity of the caller for the tool call in progress.

    Tool bodies use it to stamp who did something (for example the reporter of a ticket),
    never to make access decisions, which belong to the gateway.
    """
    identity = _current_identity.get()
    if identity is None:
        raise RuntimeError("current_identity() called outside a governed tool call")
    return identity


class Gateway:
    def __init__(
        self,
        *,
        policy: PolicySet,
        identity: IdentityResolver,
        audit: AuditLog,
        limiter: RateLimiter | None = None,
        redactor: Redactor | None = None,
        hasher: ArgsHasher | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.policy = policy
        self.identity = identity
        self.audit = audit
        self.limiter = limiter or RateLimiter()
        self.redactor = redactor or Redactor()
        self.hasher = hasher or ArgsHasher()
        self._clock = clock

    def visible(self, server: str, tool: str, access: Access) -> bool:
        identity = self.identity.current()
        if identity is None:
            return False
        return self.policy.decide(identity.role, f"{server}.{tool}", access).allowed

    def _precheck(
        self, identity: Identity | None, qualified: str, access: Access, args: dict[str, Any]
    ) -> Decision:
        if identity is None:
            return Decision(False, "unauthenticated")
        role = self.policy.get(identity.role)
        if role is None:
            return Decision(False, "no recognised role in the caller's identity")
        rate = self.limiter.check(identity.rate_key, role.rate_limit)
        if not rate.allowed:
            return Decision(False, f"rate limit exceeded, retry after {rate.retry_after_s}s")
        decision = self.policy.decide(identity.role, qualified, access)
        if not decision.allowed:
            return decision
        if access == "write" and args.get(CONFIRM_PARAM) is not True:
            return Decision(
                False,
                f"{qualified!r} changes state and needs confirm=true. "
                "Show the user what will be done and ask before retrying.",
            )
        return decision

    def wrap(
        self, server: str, name: str, access: Access, fn: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Any]:
        qualified = f"{server}.{name}"

        @functools.wraps(fn)
        async def governed(**kwargs: Any) -> Any:
            started = self._clock()
            identity = self.identity.current()
            decision = self._precheck(identity, qualified, access, kwargs)
            outcome: Literal["ok", "error", "denied"] = "denied"
            redactions = 0
            try:
                if not decision.allowed:
                    raise ToolError(f"Denied: {decision.reason}")
                token = _current_identity.set(identity)
                try:
                    result = await fn(**kwargs)
                except ToolError:
                    outcome = "error"
                    raise
                except Exception as exc:
                    outcome = "error"
                    log.exception("tool %s failed", qualified)
                    raise ToolError(f"{qualified} failed; see server logs") from exc
                finally:
                    _current_identity.reset(token)
                redacted, report = self.redactor.redact(result)
                redactions = report.total
                outcome = "ok"
                return redacted
            finally:
                self.audit.write(
                    AuditRecord(
                        request_id=str(uuid.uuid4()),
                        server=server,
                        tool=name,
                        access=access,
                        principal=identity.principal if identity else None,
                        client_id=identity.client_id if identity else None,
                        role=identity.role if identity else None,
                        auth=identity.source if identity else "none",
                        args_hash=self.hasher(kwargs),
                        args_hash_alg=self.hasher.algorithm,
                        decision="allow" if decision.allowed else "deny",
                        reason=decision.reason,
                        outcome=outcome,
                        latency_ms=round((self._clock() - started) * 1000, 3),
                        redactions=redactions,
                    )
                )

        return governed


class GovernedServer(MCPServer):
    """An ``MCPServer`` whose tools all run behind a ``Gateway``.

    Tools are registered with ``@server.governed_tool(access=...)``. Plain ``@server.tool()``
    is refused, so nothing can be added that bypasses the gateway by accident.
    """

    def __init__(self, name: str, *, gateway: Gateway, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.gateway = gateway
        self._access: dict[str, Access] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError("use governed_tool(access=...) so the tool runs behind the gateway")

    def governed_tool(
        self, *, access: Access, name: str | None = None, title: str | None = None
    ) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
        def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
            tool_name = name or fn.__name__
            if not inspect.iscoroutinefunction(fn):
                raise TypeError(f"governed tool {tool_name!r} must be async")
            params = inspect.signature(fn).parameters
            if access == "write":
                confirm = params.get(CONFIRM_PARAM)
                if confirm is None or confirm.default is not False:
                    raise TypeError(f"write tool {tool_name!r} must declare `{CONFIRM_PARAM}: bool = False`")
            annotations = ToolAnnotations(
                title=title,
                read_only_hint=access == "read",
                destructive_hint=False,
                idempotent_hint=access == "read",
                open_world_hint=False,
            )
            self.add_tool(
                self.gateway.wrap(self.name, tool_name, access, fn),
                name=tool_name,
                title=title,
                annotations=annotations,
                meta={"governed-mcp/access": access, "governed-mcp/requires-confirmation": access == "write"},
            )
            self._access[tool_name] = access
            return fn

        return decorator

    async def list_tools(self) -> list[MCPTool]:
        """Only list the tools the caller's role can call, so they never enter its context."""
        tools = await super().list_tools()
        return [
            t for t in tools if self.gateway.visible(self.name, t.name, self._access.get(t.name, "write"))
        ]
