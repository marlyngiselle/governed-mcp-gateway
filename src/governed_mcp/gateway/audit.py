"""Structured audit log, one JSON object per line.

Arguments are never written in clear. The log carries a hash of the canonical JSON of the
arguments, which is enough to correlate a call across systems or prove what was sent when
the caller produces the original, without turning the audit trail into a second copy of the
data the tools protect. With ``hash_key`` set, the hash is an HMAC, so low-entropy arguments
such as a ticket number cannot be recovered by brute force.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TextIO

from pydantic import BaseModel, ConfigDict, Field


class AuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="milliseconds"))
    event: Literal["tool_call"] = "tool_call"
    request_id: str
    server: str
    tool: str
    access: Literal["read", "write"]
    principal: str | None
    client_id: str | None
    role: str | None
    auth: Literal["local", "oidc", "none"]
    args_hash: str
    args_hash_alg: Literal["sha256", "hmac-sha256"]
    decision: Literal["allow", "deny"]
    reason: str
    outcome: Literal["ok", "error", "denied"]
    latency_ms: float
    redactions: int = 0


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False).encode()


class ArgsHasher:
    def __init__(self, key: bytes | None = None) -> None:
        self._key = key

    @property
    def algorithm(self) -> Literal["sha256", "hmac-sha256"]:
        return "hmac-sha256" if self._key else "sha256"

    def __call__(self, args: dict[str, Any]) -> str:
        payload = canonical_json(args)
        if self._key:
            return hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        return hashlib.sha256(payload).hexdigest()


class AuditLog:
    """Append-only JSON lines sink. Safe to share between threads."""

    def __init__(self, sink: TextIO | str | Path | None = None) -> None:
        self._lock = threading.Lock()
        self._owned = False
        if sink is None or sink == "-":
            self._stream: TextIO = sys.stderr
        elif isinstance(sink, str | Path):
            path = Path(sink)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = path.open("a", encoding="utf-8")
            self._owned = True
        else:
            self._stream = sink

    def write(self, record: AuditRecord) -> None:
        line = record.model_dump_json()
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()

    def close(self) -> None:
        if self._owned:
            self._stream.close()
