from typing import Any

import pytest

from governed_mcp.gateway.redaction import Redactor

R = Redactor()

# Secret-shaped fixtures are assembled at runtime so no scanner mistakes this file for a leak.
PEM_HEADER = "-----BEGIN " + "PRIVATE KEY-----"
PEM_FOOTER = "-----END " + "PRIVATE KEY-----"
FAKE_AWS_KEY_ID = "AKIA" + "ABCDEFGHIJKLMNOP"


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (f"{PEM_HEADER}\nMIIEvQIBADANBg\n{PEM_FOOTER}", "private_key"),
        ("token eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJhbGV4In0.c2lnbmF0dXJlLXZhbHVl here", "jwt"),
        ("Authorization: Bearer abcdefghijklmnop1234", "bearer_token"),
        (f"key {FAKE_AWS_KEY_ID} in config", "aws_access_key_id"),
        ("ghp_" + "a" * 36, "github_token"),
        ("AccountName=x;AccountKey=c2VjcmV0LXZhbHVl==;EndpointSuffix=y", "connection_string_secret"),
        ("password: hunter2hunter2", "secret_assignment"),
        ("contact dana.ops@example.test today", "email"),
        ("card 4111 1111 1111 1111 on file", "payment_card"),
        ("pay to GB82 WEST 1234 5698 7654 32", "iban"),
    ],
)
def test_each_rule_fires(text: str, kind: str) -> None:
    out, report = R.redact(text)
    assert f"[REDACTED:{kind}]" in out
    assert report.counts[kind] >= 1


def test_keeps_prefix_for_key_value_secrets() -> None:
    out, _ = R.redact("Server=db;Password=s3cr3t-value;Database=app")
    assert out == "Server=db;Password=[REDACTED:connection_string_secret];Database=app"


@pytest.mark.parametrize(
    "text", ["order 4111 1111 1111 1112", "GB82 WEST 1234 5698 7654 33", "build 1234567890123"]
)
def test_checksum_failures_are_left_alone(text: str) -> None:
    out, report = R.redact(text)
    assert out == text
    assert report.total == 0


def test_walks_nested_structures_and_sensitive_keys() -> None:
    value: dict[str, Any] = {
        "name": "stlogsprod01",
        "monthly_cost": 88.6,
        "properties": {"connection_string": "anything at all", "client_secret": "x" * 10, "sku": "LRS"},
        "owners": ["lee.chen@example.test", {"api_key": "abc123abc123"}],
        "ok": True,
    }
    out, report = R.redact(value)
    assert out["properties"]["connection_string"] == "[REDACTED:sensitive_field]"
    assert out["properties"]["client_secret"] == "[REDACTED:sensitive_field]"
    assert out["properties"]["sku"] == "LRS"
    assert out["owners"][0] == "[REDACTED:email]"
    assert out["owners"][1]["api_key"] == "[REDACTED:sensitive_field]"
    assert out["monthly_cost"] == 88.6
    assert out["ok"] is True
    assert report.total == 4
    # The input is not mutated.
    assert value["properties"]["sku"] == "LRS"
    assert value["owners"][0] == "lee.chen@example.test"


def test_plain_operational_text_is_untouched() -> None:
    text = "Disk usage above 90% on vm-batch-01 since 2026-10-10, ticket TCK-1001."
    assert R.redact(text) == (text, R.redact(text)[1])
    assert R.redact(text)[1].total == 0
