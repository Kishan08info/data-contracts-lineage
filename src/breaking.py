# Data Contracts & Lineage — synthetic SaaS warehouse
# Project 22
"""Diff two contract versions and flag breaking changes.

Change classes:
  - column_dropped / column_renamed (renamed_from in v2) — breaking if
    any model consumes the column (checked against the lineage graph).
  - type_narrowed / nullable_tightened / allowed_values_shrunk — breaking.
  - column_added (nullable) — non-breaking.
  - allowed_values_grown / description-only — non-breaking.
"""

from pathlib import Path

from src.contracts import load_contracts
from src.lineage import impact as lineage_impact


def _affected(lineage, table, column):
    """Models affected by a change to table.column, transitively."""
    if not lineage:
        return set()
    return {node.split(".")[0]
            for node in lineage_impact(lineage, table, column)}


def diff_contracts(old_dir, new_dir, lineage=None):
    """Return a list of change dicts, each with severity breaking/non-breaking."""
    old = load_contracts(old_dir)
    new = load_contracts(new_dir)
    changes = []

    def breaking(dataset, change, detail, affected):
        changes.append({"dataset": dataset, "change": change,
                        "detail": detail, "severity": "breaking",
                        "affected_models": sorted(affected)})

    def non_breaking(dataset, change, detail):
        changes.append({"dataset": dataset, "change": change,
                        "detail": detail, "severity": "non-breaking",
                        "affected_models": []})

    # A dataset with no v2 file is unchanged — v2 only carries datasets
    # whose contract actually changed. Only datasets present in BOTH
    # versions are diffed; a dataset only in v2 is an addition.
    for name in sorted(set(new) - set(old)):
        non_breaking(name, "dataset_added", f"new dataset {name} in v2")
    for name in sorted(set(old) & set(new)):
        o_cols = {c["name"]: c for c in old[name]["columns"]}
        n_cols = {c["name"]: c for c in new[name]["columns"]}
        table = old[name]["table"]
        for col in sorted(set(o_cols) - set(n_cols)):
            renamed = [c for c in n_cols.values()
                       if c.get("renamed_from") == col]
            if renamed:
                new_name = renamed[0]["name"]
                breaking(name, "column_renamed",
                         f"{table}.{col} renamed to {new_name}",
                         _affected(lineage, table, col))
            else:
                breaking(name, "column_dropped",
                         f"{table}.{col} dropped in v2",
                         _affected(lineage, table, col))
        for col in sorted(set(n_cols) - set(o_cols)):
            if n_cols[col].get("renamed_from"):
                continue  # handled above as the rename target
            non_breaking(name, "column_added",
                         f"{table}.{col} added (nullable="
                         f"{n_cols[col].get('nullable')})")
        for col in sorted(set(o_cols) & set(n_cols)):
            o, n = o_cols[col], n_cols[col]
            if o.get("type") != n.get("type"):
                breaking(name, "type_changed",
                         f"{table}.{col}: {o.get('type')} -> {n.get('type')}",
                         _affected(lineage, table, col))
            if o.get("nullable") is True and n.get("nullable") is False:
                breaking(name, "nullable_tightened",
                         f"{table}.{col}: nullable -> not null",
                         _affected(lineage, table, col))
            ov, nv = o.get("allowed_values"), n.get("allowed_values")
            if ov and nv and set(nv) < set(ov):
                breaking(name, "allowed_values_shrunk",
                         f"{table}.{col}: {sorted(set(ov) - set(nv))} removed",
                         _affected(lineage, table, col))
            elif ov and nv and set(nv) > set(ov):
                non_breaking(name, "allowed_values_grown",
                             f"{table}.{col}: values added")
    return changes
