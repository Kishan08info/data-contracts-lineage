"""Tests for the contract validator: clean data passes, injected defects
are caught with exact counts, and the validator is deterministic."""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.contracts import load_contracts, validate  # noqa: E402
from src.defects import inject  # noqa: E402
from src.generate import generate  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "warehouse.db"
    generate(path)
    return path


def test_clean_warehouse_passes_all_checks(db):
    result = validate(db, ROOT / "contracts" / "v1")
    assert result["passed"] is True, result["violation_list"]
    assert result["violations"] == 0
    assert result["datasets"] == 4
    assert result["checks_run"] > 0


def test_row_counts_are_deterministic(db):
    counts = {t: sqlite3.connect(db).execute(
        f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("customers", "subscriptions", "orders", "payments")}
    assert counts["customers"] == 300
    assert counts["subscriptions"] == 300
    assert counts["orders"] == 1967
    assert counts["payments"] == 1817


def test_injected_defects_caught_with_exact_counts(db):
    inject(db)
    result = validate(db, ROOT / "contracts" / "v1")
    assert result["passed"] is False
    by_check = {}
    for v in result["violation_list"]:
        by_check[(v["check"], v["column"])] = v["count"]
    # 5 negative amounts, 1 bogus status, 4 NULL emails,
    # 2 duplicate emails (1 extra row), 3 orphan payments.
    assert by_check[("min_value", "amount")] == 5
    assert by_check[("allowed_values", "status")] == 1
    assert by_check[("not_null", "email")] == 4
    assert by_check[("unique", "email")] == 1
    assert by_check[("referential", "order_id")] == 3
    assert result["violations"] == 5


def test_validation_is_deterministic(db):
    inject(db)
    first = validate(db, ROOT / "contracts" / "v1")
    second = validate(db, ROOT / "contracts" / "v1")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_contracts_load(db):
    contracts = load_contracts(ROOT / "contracts" / "v1")
    assert set(contracts) == {"customers", "subscriptions", "orders", "payments"}
    assert contracts["orders"]["columns"][3]["name"] == "amount"
