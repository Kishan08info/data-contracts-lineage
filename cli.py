# Data Contracts & Lineage — synthetic SaaS warehouse
# Project 22
"""CLI: generate | validate | lineage | impact | breaking-change | demo."""

import argparse
import json
import sqlite3
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
V1 = ROOT / "contracts" / "v1"
V2 = ROOT / "contracts" / "v2"
MODELS = ROOT / "models"


def cmd_generate(args):
    counts = generate(DB)
    print(json.dumps({"warehouse": str(DB), "rows": counts}, indent=2))


def cmd_validate(args):
    result = validate(DB, V1)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


def cmd_lineage(args):
    lineage = build_lineage(MODELS, load_contracts(V1))
    print(json.dumps(lineage, indent=2))


def cmd_impact(args):
    lineage = build_lineage(MODELS, load_contracts(V1))
    table, column = args.column.split(".", 1)
    downstream = impact(lineage, table, column)
    print(json.dumps({"source": args.column, "downstream": downstream},
                     indent=2))


def cmd_breaking(args):
    lineage = build_lineage(MODELS, load_contracts(V1))
    changes = diff_contracts(V1, V2, lineage)
    n_breaking = sum(1 for c in changes if c["severity"] == "breaking")
    print(json.dumps({"changes": changes, "breaking": n_breaking,
                      "non_breaking": len(changes) - n_breaking}, indent=2))
    return 0 if n_breaking == 0 else 1


def main():
    parser = argparse.ArgumentParser(prog="contracts")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate")
    sub.add_parser("validate")
    sub.add_parser("lineage")
    p = sub.add_parser("impact")
    p.add_argument("column", help="table.column, e.g. customers.plan")
    sub.add_parser("breaking-change")
    args = parser.parse_args()
    code = {"generate": cmd_generate, "validate": cmd_validate,
            "lineage": cmd_lineage, "impact": cmd_impact,
            "breaking-change": cmd_breaking}[args.cmd](args)
    return code or 0


if __name__ == "__main__":
    raise SystemExit(main())
