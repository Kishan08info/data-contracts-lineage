# Data Contracts & Lineage — synthetic SaaS warehouse
# Project 22
"""Column-level lineage parsed from the SQL models.

The parser is deliberately small and explicit: it reads each model's
`-- depends_on:` header plus its FROM/JOIN clauses for source tables,
splits the SELECT list on top-level commas, and matches the identifiers
in each output expression against the known columns of the source
tables (from the v1 contracts). No CTEs, no subqueries in the models —
the parser refuses anything it cannot parse, rather than guessing.
"""

import re
from pathlib import Path

IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
SQL_KEYWORDS = {
    "select", "from", "where", "group", "by", "order", "having", "join",
    "left", "right", "inner", "outer", "full", "cross", "on", "and", "or",
    "not", "in", "is", "null", "as", "case", "when", "then", "else", "end",
    "distinct", "count", "sum", "avg", "min", "max", "strftime", "cast",
    "coalesce", "limit", "union", "all",
}


def _strip_comments(sql):
    return "\n".join(line for line in sql.splitlines()
                     if not line.strip().startswith("--"))


def _split_top_level_commas(text):
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


def parse_model(path, source_columns):
    """Parse one model file.

    source_columns: {table: {column, ...}} from the contracts.
    Returns {model, sources, columns: [{name, expression, source_columns}]}.
    """
    text = Path(path).read_text()
    model = Path(path).stem
    clean = _strip_comments(text)
    flat = re.sub(r"\s+", " ", clean).strip()

    sources = sorted(set(re.findall(
        r"\b(?:FROM|JOIN)\s+(" + IDENT + r")\b", flat, flags=re.I)))
    # Ignore the model's own name if it ever self-references.
    sources = [s for s in sources if s != model]

    m = re.search(r"\bSELECT\b(.*?)\bFROM\b", flat, flags=re.I | re.S)
    if not m:
        raise ValueError(f"{model}: no SELECT ... FROM found")
    select_list = m.group(1)

    columns = []
    for item in _split_top_level_commas(select_list):
        item = item.strip()
        alias_m = re.search(r"\bAS\s+(" + IDENT + r")\s*$", item, flags=re.I)
        if alias_m:
            alias, expr = alias_m.group(1), item[:alias_m.start()].strip()
        else:
            tokens = item.split()
            if len(tokens) > 1 and re.fullmatch(IDENT, tokens[-1], flags=re.I) \
                    and tokens[-1].lower() not in SQL_KEYWORDS:
                alias, expr = tokens[-1], " ".join(tokens[:-1])
            else:
                expr = item
                alias = item.split(".")[-1].strip()
        # Source columns: identifiers in the expression that are real
        # columns of one of the source tables (qualified or bare).
        found = set()
        for qtable, qcol in re.findall(
                r"\b(" + IDENT + r")\.(" + IDENT + r")\b", expr):
            if qtable in source_columns and qcol in source_columns[qtable]:
                found.add(f"{qtable}.{qcol}")
        for bare in re.findall(r"\b(" + IDENT + r")\b", expr):
            if bare.lower() in SQL_KEYWORDS:
                continue
            for src in sources:
                if bare in source_columns.get(src, set()):
                    found.add(f"{src}.{bare}")
        columns.append({"name": alias, "expression": expr,
                        "source_columns": sorted(found)})
    return {"model": model, "sources": sources, "columns": columns}


def build_lineage(models_dir, contracts):
    """Build the full lineage graph.

    Returns {"models": [...], "table_edges": [[src, dst], ...],
             "column_edges": [[src_table.src_col, dst_model.dst_col], ...]}.
    """
    source_columns = {}
    for name, c in contracts.items():
        source_columns[c["table"]] = {col["name"] for col in c["columns"]}
    # Models can also be sources (staging -> marts): add their outputs
    # in two passes — first parse with raw tables only, then re-parse
    # with model outputs known.
    models = {}
    for path in sorted(Path(models_dir).glob("*.sql")):
        models[path.stem] = parse_model(path, source_columns)
    for m in models.values():
        source_columns[m["model"]] = {c["name"] for c in m["columns"]}
    for path in sorted(Path(models_dir).glob("*.sql")):
        models[path.stem] = parse_model(path, source_columns)

    table_edges, column_edges = set(), set()
    for m in models.values():
        for src in m["sources"]:
            table_edges.add((src, m["model"]))
        for col in m["columns"]:
            for sc in col["source_columns"]:
                column_edges.add((sc, f"{m['model']}.{col['name']}"))
    return {"models": [models[k] for k in sorted(models)],
            "table_edges": sorted(table_edges),
            "column_edges": sorted(column_edges)}


def impact(lineage, table, column):
    """Downstream impact of one source column: every downstream
    (model, column) reached by following column edges, in BFS order."""
    start = f"{table}.{column}"
    downstream = {}  # node -> list of nodes it feeds
    for src, dst in lineage["column_edges"]:
        downstream.setdefault(src, []).append(dst)
    seen, queue, result = set(), [start], []
    while queue:
        node = queue.pop(0)
        for nxt in downstream.get(node, []):
            if nxt not in seen:
                seen.add(nxt)
                result.append(nxt)
                queue.append(nxt)
    return result
