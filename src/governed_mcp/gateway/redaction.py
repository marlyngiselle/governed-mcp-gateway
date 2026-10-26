"""Output redaction for secrets and personal data.

Every tool result passes through ``Redactor.redact`` before it reaches the MCP client.
The assistant on the other side may echo, summarise or forward whatever it receives, so
anything that should not leave the boundary is removed here, not trusted to the prompt.

Two mechanisms:

* Field names. A dictionary key that looks sensitive (``password``, ``connection_string``)
  has its string value replaced whatever it contains.
* Value patterns. Strings are scanned for known secret and PII shapes. Card numbers and
  IBANs are confirmed with their checksums so ordinary numbers are left alone.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"(?i)^(.*[_-])?(password|passwd|secret|client[_-]?secret|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|token|connection[_-]?string|sas)$"
)


def _luhn_ok(candidate: str) -> bool:
    digits = [int(c) for c in candidate if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, digit in enumerate(reversed(digits)):
        doubled = digit * 2 if i % 2 == 1 else digit
        total += doubled - 9 if doubled > 9 else doubled
    return total % 10 == 0


def _iban_ok(candidate: str) -> bool:
    s = candidate.replace(" ", "").upper()
    rearranged = s[4:] + s[:4]
    numeric = "".join(str(int(c, 36)) for c in rearranged)
    return int(numeric) % 97 == 1


@dataclass(frozen=True, slots=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    # Group to replace. 0 replaces the whole match, 2 keeps a "key=" prefix in group 1.
    group: int = 0
    validator: Callable[[str], bool] | None = None


DEFAULT_RULES: tuple[Rule, ...] = (
    Rule(
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"),
    ),
    Rule("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    Rule("bearer_token", re.compile(r"(?i)\b(bearer\s+)(?!\[REDACTED)([A-Za-z0-9._~+/-]{16,}=*)"), group=2),
    Rule("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    Rule("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b")),
    Rule(
        "connection_string_secret",
        re.compile(r"(?i)\b(AccountKey=|SharedAccessKey=|SharedAccessSignature=|Password=|Pwd=)([^;\"'\s]+)"),
        group=2,
    ),
    Rule(
        "secret_assignment",
        re.compile(
            r"(?i)\b((?:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*[\"']?)(?!\[REDACTED)([^\s\"',;]{6,})"
        ),
        group=2,
    ),
    Rule("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    Rule("payment_card", re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), validator=_luhn_ok),
    Rule(
        "iban",
        re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b"),
        validator=_iban_ok,
    ),
)


@dataclass(slots=True)
class RedactionReport:
    counts: Counter[str] = field(default_factory=Counter)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


class Redactor:
    def __init__(self, rules: tuple[Rule, ...] = DEFAULT_RULES) -> None:
        self._rules = rules

    def redact(self, value: Any) -> tuple[Any, RedactionReport]:
        report = RedactionReport()
        return self._walk(value, report), report

    def redact_text(self, text: str, report: RedactionReport | None = None) -> str:
        report = report if report is not None else RedactionReport()
        for rule in self._rules:
            text = self._apply(rule, text, report)
        return text

    def _apply(self, rule: Rule, text: str, report: RedactionReport) -> str:
        marker = f"[REDACTED:{rule.name}]"

        def replace(m: re.Match[str]) -> str:
            target = m.group(rule.group)
            if rule.validator is not None and not rule.validator(target):
                return m.group(0)
            report.counts[rule.name] += 1
            if rule.group == 0:
                return marker
            start, end = m.span(rule.group)
            whole_start = m.start(0)
            whole = m.group(0)
            return whole[: start - whole_start] + marker + whole[end - whole_start :]

        return rule.pattern.sub(replace, text)

    def _walk(self, value: Any, report: RedactionReport) -> Any:
        if isinstance(value, str):
            return self.redact_text(value, report)
        if isinstance(value, dict):
            out: dict[Any, Any] = {}
            for k, v in value.items():
                if isinstance(k, str) and _SENSITIVE_KEY.match(k) and isinstance(v, str) and v:
                    report.counts["sensitive_field"] += 1
                    out[k] = "[REDACTED:sensitive_field]"
                else:
                    out[k] = self._walk(v, report)
            return out
        if isinstance(value, list | tuple):
            return type(value)(self._walk(v, report) for v in value)
        return value
