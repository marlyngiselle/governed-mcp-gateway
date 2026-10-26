import io
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from governed_mcp.gateway.audit import ArgsHasher, AuditLog, AuditRecord

FIELDS = {
    "ts",
    "event",
    "request_id",
    "server",
    "tool",
    "access",
    "principal",
    "client_id",
    "role",
    "auth",
    "args_hash",
    "args_hash_alg",
    "decision",
    "reason",
    "outcome",
    "latency_ms",
    "redactions",
}


def record(**kw: object) -> AuditRecord:
    base: dict[str, object] = dict(
        request_id="r1",
        server="tickets",
        tool="get_ticket",
        access="read",
        principal="alex@example.test",
        client_id="stdio",
        role="reader",
        auth="local",
        args_hash="0" * 64,
        args_hash_alg="sha256",
        decision="allow",
        reason="allowed by role 'reader'",
        outcome="ok",
        latency_ms=1.234,
    )
    base.update(kw)
    return AuditRecord.model_validate(base)


def test_one_json_object_per_line_with_fixed_schema() -> None:
    sink = io.StringIO()
    log = AuditLog(sink)
    log.write(record())
    log.write(record(decision="deny", outcome="denied"))
    lines = sink.getvalue().splitlines()
    assert len(lines) == 2
    for line in lines:
        assert set(json.loads(line)) == FIELDS
    assert json.loads(lines[0])["ts"].endswith("+00:00")


def test_schema_rejects_unknown_decisions_and_fields() -> None:
    with pytest.raises(ValidationError):
        record(decision="maybe")
    with pytest.raises(ValidationError):
        record(arguments={"ticket_id": "TCK-1001"})


def test_hash_is_canonical_and_never_contains_the_values() -> None:
    h = ArgsHasher()
    a = h({"ticket_id": "TCK-1001", "limit": 5})
    b = h({"limit": 5, "ticket_id": "TCK-1001"})
    assert a == b
    assert len(a) == 64
    assert "TCK-1001" not in a
    assert h({"ticket_id": "TCK-1002", "limit": 5}) != a


def test_hmac_mode_changes_the_digest_and_reports_it() -> None:
    plain, keyed = ArgsHasher(), ArgsHasher(b"audit-pepper-for-tests")
    args = {"ticket_id": "TCK-1001"}
    assert plain(args) != keyed(args)
    assert keyed.algorithm == "hmac-sha256"
    assert plain.algorithm == "sha256"


def test_file_sink_appends(tmp_path: Path) -> None:
    path = tmp_path / "logs" / "audit.jsonl"
    for _ in range(2):
        log = AuditLog(path)
        log.write(record())
        log.close()
    assert len(path.read_text().splitlines()) == 2
