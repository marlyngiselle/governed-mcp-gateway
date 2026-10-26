"""A synthetic cloud inventory.

Stands in for a resource graph or CMDB query API. The data is fictional and fixed so tests
and demos are reproducible. A couple of resources carry secret-looking properties and an
owner email on purpose: they exist to show the redaction layer working.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ResourceType = Literal[
    "virtual_machine", "storage_account", "sql_database", "kubernetes_cluster", "key_vault", "function_app"
]


class Resource(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    type: ResourceType
    region: str
    tags: dict[str, str] = Field(default_factory=dict)
    monthly_cost: float
    properties: dict[str, str] = Field(default_factory=dict)


def _r(i: int, name: str, rtype: ResourceType, region: str, cost: float, **tags: str) -> Resource:
    return Resource(
        id=f"res-{i:04d}",
        name=name,
        type=rtype,
        region=region,
        tags={k.replace("_", "-"): v for k, v in tags.items()},
        monthly_cost=cost,
    )


_SEED: list[Resource] = [
    _r(1, "vm-web-01", "virtual_machine", "westeurope", 182.40, env="prod", team="web", cost_center="cc-100"),
    _r(2, "vm-web-02", "virtual_machine", "westeurope", 182.40, env="prod", team="web", cost_center="cc-100"),
    _r(
        3,
        "vm-batch-01",
        "virtual_machine",
        "northeurope",
        96.10,
        env="dev",
        team="data",
        cost_center="cc-200",
    ),
    _r(
        4,
        "aks-platform-prod",
        "kubernetes_cluster",
        "westeurope",
        1240.00,
        env="prod",
        team="platform",
        cost_center="cc-300",
    ),
    _r(
        5,
        "aks-platform-dev",
        "kubernetes_cluster",
        "westeurope",
        410.75,
        env="dev",
        team="platform",
        cost_center="cc-300",
    ),
    _r(6, "sqldb-orders", "sql_database", "westeurope", 365.00, env="prod", team="web", cost_center="cc-100"),
    _r(
        7,
        "sqldb-analytics",
        "sql_database",
        "northeurope",
        512.30,
        env="prod",
        team="data",
        cost_center="cc-200",
    ),
    _r(
        8,
        "kv-platform-prod",
        "key_vault",
        "westeurope",
        4.20,
        env="prod",
        team="platform",
        cost_center="cc-300",
    ),
    _r(9, "func-ingest", "function_app", "northeurope", 38.90, env="prod", team="data", cost_center="cc-200"),
    _r(10, "func-ingest-dev", "function_app", "northeurope", 6.15, env="dev", team="data"),
    _r(11, "vm-jumpbox", "virtual_machine", "westeurope", 54.00, env="prod", team="platform"),
    _r(12, "sqldb-scratch", "sql_database", "westeurope", 75.00),
]

_SEED[2] = _SEED[2].model_copy(update={"tags": {**_SEED[2].tags, "owner": "dana.ops@example.test"}})
_SEED.append(
    Resource(
        id="res-0013",
        name="stlogsprod01",
        type="storage_account",
        region="westeurope",
        tags={"env": "prod", "team": "platform", "cost-center": "cc-300"},
        monthly_cost=88.60,
        properties={
            "sku": "Standard_GRS",
            "connection_string": "DefaultEndpointsProtocol=https;AccountName=stlogsprod01;"
            "AccountKey=ZmFrZS1rZXktZm9yLWRlbW8tb25seS1ub3QtYS1yZWFsLXNlY3JldA==",
        },
    )
)
_SEED.append(
    Resource(
        id="res-0014",
        name="stexportsdev01",
        type="storage_account",
        region="northeurope",
        tags={"env": "dev", "team": "data", "cost-center": "cc-200"},
        monthly_cost=12.30,
        properties={"sku": "Standard_LRS", "notes": "rotate: Password=Demo-Only-Fake-1234 before go-live"},
    )
)


class CostGroup(BaseModel):
    value: str
    monthly_cost: float
    resources: int


class FakeCloudInventory:
    currency = "EUR"
    period = "2026-09"

    def __init__(self, resources: list[Resource] | None = None) -> None:
        self._resources = list(resources if resources is not None else _SEED)

    def query(
        self,
        resource_type: ResourceType | None = None,
        tag_key: str | None = None,
        tag_value: str | None = None,
        region: str | None = None,
    ) -> list[Resource]:
        out = []
        for r in self._resources:
            if resource_type and r.type != resource_type:
                continue
            if region and r.region != region:
                continue
            if tag_key and (
                tag_key not in r.tags or (tag_value is not None and r.tags[tag_key] != tag_value)
            ):
                continue
            out.append(r)
        return out

    def get(self, resource_id: str) -> Resource | None:
        return next((r for r in self._resources if r.id == resource_id), None)

    def cost_by_tag(self, tag_key: str) -> tuple[list[CostGroup], CostGroup]:
        totals: dict[str, list[float]] = defaultdict(list)
        untagged: list[float] = []
        for r in self._resources:
            (totals[r.tags[tag_key]] if tag_key in r.tags else untagged).append(r.monthly_cost)
        groups = [
            CostGroup(value=k, monthly_cost=round(sum(v), 2), resources=len(v)) for k, v in totals.items()
        ]
        groups.sort(key=lambda g: g.monthly_cost, reverse=True)
        return groups, CostGroup(
            value="(untagged)", monthly_cost=round(sum(untagged), 2), resources=len(untagged)
        )
