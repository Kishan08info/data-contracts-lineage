# Data Contracts & Lineage — synthetic SaaS warehouse
# Project 22
"""End-to-end demo: generate clean warehouse -> validate (0 violations)
-> inject counted defects -> validate (violations caught) -> lineage ->
impact analysis -> breaking-change diff v1 -> v2 -> summary.json.

Run:  python run_demo.py
All numbers in outputs/summary.json come from this run.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.breaking import diff_contracts
from src.contracts import load_contracts, validate
from src.defects import inject
from src.generate import generate
from src.lineage import build_lineage, impact

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "warehouse.db"
OUT = ROOT / "outputs" / "summary.json"


def main():
    counts = generate(DB)
    clean = validate(DB, ROOT / "contracts" / "v1")
    lineage = build_lineage(ROOT / "models", load_contracts(ROOT / "contracts" / "v1"))
    impact_plan = impact(lineage, "customers", "plan")
    impact_amount = impact(lineage, "orders", "amount")

    injected = inject(DB)
    dirty = validate(DB, ROOT / "contracts" / "v1")

    changes = diff_contracts(ROOT / "contracts" / "v1",
                             ROOT / "contracts" / "v2", lineage)
    n_breaking = sum(1 for c in changes if c["severity"] == "breaking")

    # Sanity: the marts actually run against the warehouse.
    import sqlite3
    con = sqlite3.connect(DB)
    # Marts read staging models; materialise staging as temp views once.
    for stg in ("stg_customers", "stg_orders", "stg_subscriptions"):
        stg_sql = (ROOT / "models" / f"{stg}.sql").read_text()
        stg_sql = "\n".join(l for l in stg_sql.splitlines()
                            if not l.strip().startswith("--"))
        con.execute(f"CREATE TEMP VIEW {stg} AS {stg_sql.rstrip(';')}")
    mart_rows = {}
    for name in ("mart_monthly_revenue", "mart_customer_ltv", "mart_churn"):
        sql = (ROOT / "models" / f"{name}.sql").read_text()
        sql = "\n".join(l for l in sql.splitlines()
                        if not l.strip().startswith("--"))
        rows = con.execute(sql.rstrip(";")).fetchall()
        mart_rows[name] = len(rows)
    con.close()

    summary = {
        "rows_generated": counts,
        "clean_validation": {"checks_run": clean["checks_run"],
                             "violations": clean["violations"],
                             "passed": clean["passed"]},
        "defects_injected": injected,
        "dirty_validation": {"checks_run": dirty["checks_run"],
                             "violations": dirty["violations"],
                             "passed": dirty["passed"],
                             "violation_list": dirty["violation_list"]},
        "lineage": {"models": len(lineage["models"]),
                    "table_edges": len(lineage["table_edges"]),
                    "column_edges": len(lineage["column_edges"])},
        "impact": {"customers.plan": impact_plan,
                   "orders.amount": impact_amount},
        "breaking_changes": {"total": len(changes), "breaking": n_breaking,
                             "changes": changes},
        "mart_rows": mart_rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    # Leave the warehouse clean again (the defects were only for the demo).
    generate(DB)
    print("Warehouse regenerated clean — `python cli.py validate` now passes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
