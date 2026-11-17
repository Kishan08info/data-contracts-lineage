# Data Contracts & Lineage — synthetic SaaS warehouse
# Project 22
"""Validate a SQLite warehouse against YAML data contracts.

Checks per dataset: schema conformance (columns present, types match),
not-null, uniqueness, allowed values, regex patterns, numeric ranges,
referential integrity, row-count floor, and freshness vs the newest
date in the data (the "as of" reference, so the check is reproducible).
"""

import re
import sqlite3
from datetime import date
from pathlib import Path

import yaml

TYPE_ALIASES = {"DATE": "TEXT"}  # dates are stored as ISO TEXT in SQLite


def load_contracts(contracts_dir):
    """Load every *.yaml in a directory -> {dataset: contract dict}."""
    out = {}
    for path in sorted(Path(contracts_dir).glob("*.yaml")):
        with open(path) as f:
            contract = yaml.safe_load(f)
        out[contract["dataset"]] = contract
    return out


def _table_columns(con, table):
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1]: r[2].upper() for r in rows}  # name -> declared type


def _violations_for_dataset(con, contract, ref_date):
    table = contract["table"]
    violations = []
    checks_run = 0

    def add(check, column, detail, count=1, sample=None):
        violations.append({"dataset": contract["dataset"], "table": table,
                           "check": check, "column": column, "detail": detail,
                           "count": count, "sample": sample})

    if table not in {r[0] for r in
                     con.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        add("table_missing", None, f"table {table} does not exist")
        return violations, 1

    actual = _table_columns(con, table)
    n_rows = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    # --- schema conformance -------------------------------------------------
    for col in contract["columns"]:
        checks_run += 1
        name = col["name"]
        if name not in actual:
            add("column_missing", name, f"column {name} missing from {table}")
            continue
        want = TYPE_ALIASES.get(col["type"].upper(), col["type"].upper())
        if actual[name] != want:
            add("type_mismatch", name,
                f"contract type {want} but table has {actual[name]}")
    for name in actual:
        if name not in {c["name"] for c in contract["columns"]}:
            add("unexpected_column", name,
                f"column {name} in {table} is not in the contract")

    # --- row-count floor ----------------------------------------------------
    checks_run += 1
    floor = contract.get("row_count_min", 0)
    if n_rows < floor:
        add("row_count_below_floor", None,
            f"{n_rows} rows < floor {floor}", count=floor - n_rows)

    # --- freshness ----------------------------------------------------------
    # Reference date = the newest date anywhere in the warehouse
    # (the data-through date). A table whose newest row is older than its
    # SLA has gone stale relative to the rest of the pipeline.
    date_col = contract.get("date_column")
    if date_col and date_col in actual:
        checks_run += 1
        max_date = con.execute(
            f"SELECT MAX({date_col}) FROM {table}").fetchone()[0]
        if max_date:
            lag = (date.fromisoformat(ref_date)
                   - date.fromisoformat(max_date)).days
            sla = contract.get("freshness_sla_days", 30)
            if lag > sla:
                add("freshness_breach", date_col,
                    f"max {date_col} {max_date} is {lag} days behind "
                    f"data-through date {ref_date} (SLA {sla})", count=lag)

    # --- per-column checks --------------------------------------------------
    for col in contract["columns"]:
        name = col["name"]
        if name not in actual:
            continue
        if col.get("nullable") is False:
            checks_run += 1
            n = con.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {name} IS NULL"
            ).fetchone()[0]
            if n:
                sample = con.execute(
                    f"SELECT rowid FROM {table} WHERE {name} IS NULL LIMIT 3"
                ).fetchall()
                add("not_null", name, f"{n} NULL values", count=n,
                    sample=[r[0] for r in sample])
        if col.get("unique"):
            checks_run += 1
            n = con.execute(
                f"SELECT COUNT(*) - COUNT(DISTINCT {name}) FROM {table} "
                f"WHERE {name} IS NOT NULL").fetchone()[0]
            if n:
                dup = con.execute(
                    f"SELECT {name} FROM {table} WHERE {name} IS NOT NULL "
                    f"GROUP BY {name} HAVING COUNT(*) > 1 LIMIT 3").fetchall()
                add("unique", name, f"{n} duplicate values", count=n,
                    sample=[r[0] for r in dup])
        if col.get("allowed_values") is not None:
            checks_run += 1
            allowed = col["allowed_values"]
            placeholders = ",".join("?" for _ in allowed)
            n = con.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {name} IS NOT NULL "
                f"AND {name} NOT IN ({placeholders})", allowed).fetchone()[0]
            if n:
                bad = con.execute(
                    f"SELECT DISTINCT {name} FROM {table} WHERE {name} "
                    f"IS NOT NULL AND {name} NOT IN ({placeholders}) LIMIT 3",
                    allowed).fetchall()
                add("allowed_values", name,
                    f"{n} values outside {allowed}", count=n,
                    sample=[r[0] for r in bad])
        if col.get("pattern"):
            checks_run += 1
            pat = re.compile(col["pattern"])
            bad = [r[0] for r in con.execute(
                f"SELECT {name} FROM {table} WHERE {name} IS NOT NULL").fetchall()
                if not pat.match(str(r[0]))]
            if bad:
                add("pattern", name, f"{len(bad)} values fail pattern "
                    f"{col['pattern']}", count=len(bad), sample=bad[:3])
        if col.get("min_value") is not None:
            checks_run += 1
            n = con.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {name} IS NOT NULL "
                f"AND {name} < ?", (col["min_value"],)).fetchone()[0]
            if n:
                sample = con.execute(
                    f"SELECT {name} FROM {table} WHERE {name} IS NOT NULL "
                    f"AND {name} < ? LIMIT 3", (col["min_value"],)).fetchall()
                add("min_value", name,
                    f"{n} values below {col['min_value']}", count=n,
                    sample=[r[0] for r in sample])
        if col.get("references"):
            checks_run += 1
            ref_table, ref_col = col["references"].split(".")
            n = con.execute(
                f"SELECT COUNT(*) FROM {table} t WHERE t.{name} IS NOT NULL "
                f"AND NOT EXISTS (SELECT 1 FROM {ref_table} r "
                f"WHERE r.{ref_col} = t.{name})").fetchone()[0]
            if n:
                sample = con.execute(
                    f"SELECT t.{name} FROM {table} t WHERE t.{name} IS NOT NULL "
                    f"AND NOT EXISTS (SELECT 1 FROM {ref_table} r "
                    f"WHERE r.{ref_col} = t.{name}) LIMIT 3").fetchall()
                add("referential", name,
                    f"{n} values with no match in {col['references']}",
                    count=n, sample=[r[0] for r in sample])
    return violations, checks_run


def validate(db_path, contracts_dir):
    """Validate the warehouse; returns a summary dict (JSON-serialisable)."""
    contracts = load_contracts(contracts_dir)
    con = sqlite3.connect(db_path)
    # Data-through date: the newest date value anywhere in the warehouse.
    ref_date = "0000-00-00"
    for c in contracts.values():
        dc = c.get("date_column")
        if not dc:
            continue
        try:
            m = con.execute(
                f"SELECT MAX({dc}) FROM {c['table']}").fetchone()[0]
        except sqlite3.Error:
            continue
        if m and m > ref_date:
            ref_date = m
    all_violations, total_checks = [], 0
    per_dataset = {}
    for name in sorted(contracts):
        v, n = _violations_for_dataset(con, contracts[name], ref_date)
        all_violations.extend(v)
        total_checks += n
        per_dataset[name] = {"checks": n, "violations": len(v)}
    con.close()
    return {"datasets": len(contracts), "checks_run": total_checks,
            "violations": len(all_violations),
            "passed": len(all_violations) == 0,
            "per_dataset": per_dataset,
            "violation_list": all_violations}
