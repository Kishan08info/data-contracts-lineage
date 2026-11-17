"""Tests for the lineage parser, impact analysis, and breaking-change diff."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.breaking import diff_contracts  # noqa: E402
from src.contracts import load_contracts  # noqa: E402
from src.lineage import build_lineage, impact  # noqa: E402


@pytest.fixture(scope="module")
def lineage():
    return build_lineage(ROOT / "models", load_contracts(ROOT / "contracts" / "v1"))


def test_all_models_parsed(lineage):
    names = {m["model"] for m in lineage["models"]}
    assert names == {"stg_customers", "stg_orders", "stg_subscriptions",
                     "mart_monthly_revenue", "mart_customer_ltv", "mart_churn"}
    assert len(lineage["table_edges"]) == 8
    assert len(lineage["column_edges"]) == 28


def test_staging_lineage_is_identity(lineage):
    stg = next(m for m in lineage["models"] if m["model"] == "stg_customers")
    by_name = {c["name"]: c["source_columns"] for c in stg["columns"]}
    assert by_name["plan"] == ["customers.plan"]
    assert by_name["email"] == ["customers.email"]


def test_mart_revenue_lineage(lineage):
    mart = next(m for m in lineage["models"]
                if m["model"] == "mart_monthly_revenue")
    by_name = {c["name"]: c["source_columns"] for c in mart["columns"]}
    assert by_name["plan"] == ["stg_customers.plan"]
    assert by_name["revenue"] == ["stg_orders.amount"]
    assert by_name["month"] == ["stg_orders.order_date"]
    assert by_name["paid_orders"] == []


def test_impact_of_customers_plan(lineage):
    downstream = impact(lineage, "customers", "plan")
    assert downstream == [
        "stg_customers.plan",
        "mart_churn.plan",
        "mart_monthly_revenue.plan",
    ]


def test_impact_of_orders_amount(lineage):
    downstream = impact(lineage, "orders", "amount")
    assert downstream == [
        "stg_orders.amount",
        "mart_customer_ltv.total_paid",
        "mart_monthly_revenue.revenue",
    ]


def test_impact_of_unused_column_is_empty(lineage):
    assert impact(lineage, "customers", "region") == ["stg_customers.region"]


def test_breaking_change_diff(lineage):
    changes = diff_contracts(ROOT / "contracts" / "v1",
                             ROOT / "contracts" / "v2", lineage)
    by_change = {(c["dataset"], c["change"]): c for c in changes}
    # customers.plan dropped -> breaks both marts that group by plan
    dropped = by_change[("customers", "column_dropped")]
    assert dropped["severity"] == "breaking"
    assert dropped["affected_models"] == ["mart_churn", "mart_monthly_revenue",
                                          "stg_customers"]
    # orders.amount renamed -> breaks the staging model and both marts
    renamed = by_change[("orders", "column_renamed")]
    assert renamed["severity"] == "breaking"
    assert renamed["affected_models"] == ["mart_customer_ltv",
                                          "mart_monthly_revenue",
                                          "stg_orders"]
    # customers.segment added (nullable) -> non-breaking
    added = by_change[("customers", "column_added")]
    assert added["severity"] == "non-breaking"
    breaking = [c for c in changes if c["severity"] == "breaking"]
    assert len(breaking) == 2
    assert len(changes) == 3
