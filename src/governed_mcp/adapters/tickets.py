"""An in-memory ticket system standing in for an ITSM API."""

from __future__ import annotations

import itertools
import threading
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

Status = Literal["open", "in_progress", "resolved"]
Severity = Literal["sev1", "sev2", "sev3", "sev4"]


class Ticket(BaseModel):
    id: str
    title: str
    description: str
    status: Status
    severity: Severity
    service: str
    reporter: str
    created_at: str


def _seed() -> list[Ticket]:
    rows: list[tuple[str, str, Status, Severity, str, str]] = [
        (
            "Disk usage above 90% on vm-batch-01",
            "Batch logs not rotated since last deploy.",
            "open",
            "sev3",
            "batch",
            "sam.rivera@example.test",
        ),
        (
            "Pods in CrashLoopBackOff in aks-platform-dev",
            "ingress-controller restarts every 40s.",
            "in_progress",
            "sev2",
            "platform",
            "lee.chen@example.test",
        ),
        (
            "Certificate for api.example.test expires in 14 days",
            "Renew before the change freeze.",
            "open",
            "sev3",
            "web",
            "dana.ops@example.test",
        ),
        (
            "Rotate storage keys for stlogsprod01",
            "Quarterly rotation per runbook.",
            "resolved",
            "sev4",
            "platform",
            "lee.chen@example.test",
        ),
        (
            "Slow queries on sqldb-orders",
            "p95 latency doubled after index change.",
            "open",
            "sev2",
            "web",
            "sam.rivera@example.test",
        ),
        (
            "Cost spike on aks-platform-prod",
            "Node pool scaled to 12 overnight.",
            "open",
            "sev3",
            "platform",
            "finops-bot",
        ),
    ]
    return [
        Ticket(
            id=f"TCK-{1001 + i}",
            title=t,
            description=d,
            status=s,
            severity=sev,
            service=svc,
            reporter=rep,
            created_at=f"2026-10-{10 + i:02d}T09:00:00Z",
        )
        for i, (t, d, s, sev, svc, rep) in enumerate(rows)
    ]


class TicketStore:
    def __init__(self, tickets: list[Ticket] | None = None) -> None:
        self._tickets = {t.id: t for t in (tickets if tickets is not None else _seed())}
        start = max((int(t.split("-")[1]) for t in self._tickets), default=1000) + 1
        self._ids = itertools.count(start)
        self._lock = threading.Lock()

    def search(
        self,
        query: str | None = None,
        status: Status | None = None,
        severity: Severity | None = None,
        service: str | None = None,
    ) -> list[Ticket]:
        q = query.lower() if query else None
        out = []
        for t in self._tickets.values():
            if status and t.status != status:
                continue
            if severity and t.severity != severity:
                continue
            if service and t.service != service:
                continue
            if q and q not in t.title.lower() and q not in t.description.lower():
                continue
            out.append(t)
        return out

    def get(self, ticket_id: str) -> Ticket | None:
        return self._tickets.get(ticket_id)

    def create(
        self, *, title: str, description: str, severity: Severity, service: str, reporter: str
    ) -> Ticket:
        with self._lock:
            ticket = Ticket(
                id=f"TCK-{next(self._ids)}",
                title=title,
                description=description,
                status="open",
                severity=severity,
                service=service,
                reporter=reporter,
                created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            self._tickets[ticket.id] = ticket
            return ticket
