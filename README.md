# Data Contracts & Lineage

**SYNTHETIC DATA — portfolio skill demo, not work experience.**

Data contracts as YAML, validated against a warehouse; column-level lineage
parsed from SQL models; impact analysis; and breaking-change detection
between contract versions. Built from the latest Data Engineer job
descriptions (Nov 17, 2026 pool): Flow Traders asks for "data-quality
practice — tests, contracts, lineage, observability"; dbt/Snowflake-core
roles dominate the DE pool. Nothing in the portfolio covered contracts or
lineage yet — this closes that gap.

## What it demonstrates

- **Data contracts** (`contracts/v1/*.yaml`): per-dataset schema, owners,
  nullability, uniqueness, allowed values, regex, ranges, referential
  integrity, row-count floors, freshness SLAs.
- **Contract validation** (`src/contracts.py`): runs every contract check
  against a SQLite warehouse and reports each violation with counts and
  sample values. Exit code 1 when any check fails.
- **Column-level lineage** (`src/lineage.py`): parses the SQL models in
  `models/` (staging → marts) into table edges and column edges.
- **Impact analysis** (`cli.py impact <table.column>`): every downstream
  model/column a source column feeds, transitively.
- **Breaking-change detection** (`src/breaking.py`): diffs contract v1 → v2
  and flags dropped/renamed columns, type changes, tightened nullability
  and shrunk value sets — with the affected models, via lineage.

## Layout

```
contracts/v1/   YAML contracts for customers, subscriptions, orders, payments
contracts/v2/   changed contracts: customers drops `plan`, adds `segment`;
                orders renames `amount` -> `amount_usd`
models/         3 staging models + 3 marts (monthly revenue, customer LTV, churn)
src/            generate.py, contracts.py, lineage.py, breaking.py, defects.py
cli.py          generate | validate | lineage | impact | breaking-change
run_demo.py     end-to-end demo; writes outputs/summary.json
tests/          pytest suite (12 tests)
```

## Results (real numbers from an actual run — `python run_demo.py`)

Seeded, deterministic synthetic SaaS warehouse, Jan 2025 – Oct 2026:

| | |
|---|---|
| Rows generated | 300 customers, 300 subscriptions, 1,967 orders, 1,817 payments |
| Clean validation | **77 checks, 0 violations** — passes |
| Defects injected | 5 negative amounts, 1 bogus status, 4 NULL emails, 2 duplicate emails, 3 orphan payments |
| Dirty validation | **5 violations caught, exact counts** (min_value 5, allowed_values 1, not_null 4, unique 1, referential 3) |
| Lineage | 6 models, 8 table edges, **28 column edges** |
| Impact `customers.plan` | `stg_customers.plan` → `mart_churn.plan`, `mart_monthly_revenue.plan` |
| Impact `orders.amount` | `stg_orders.amount` → `mart_customer_ltv.total_paid`, `mart_monthly_revenue.revenue` |
| Breaking changes v1 → v2 | **2 of 3 breaking**: `customers.plan` dropped (breaks stg_customers + both marts), `orders.amount` renamed to `amount_usd` (breaks stg_orders + both marts); `customers.segment` added nullable = non-breaking |
| Marts (run against the warehouse) | monthly revenue 84 rows, customer LTV 300 rows, churn 40 rows |

Reproducibility: deleting `data/` and `outputs/` and re-running
`run_demo.py` reproduces `outputs/summary.json` **byte-identically**.
Tests: **12/12 pass** (`python -m pytest tests/ -q`).

## Usage

```bash
pip install -r requirements.txt   # PyYAML; pytest for tests
python cli.py generate            # build the warehouse (data/warehouse.db)
python cli.py validate            # validate v1 contracts (exit 1 on violations)
python cli.py lineage             # full lineage graph as JSON
python cli.py impact customers.plan
python cli.py breaking-change     # v1 -> v2 diff (exit 1 when breaking changes exist)
python run_demo.py                # full demo incl. defect injection; writes outputs/summary.json
```

## Honest labelling

- All data is **synthetic** (seeded generator, `seed=42`).
- SQLite stands in for a cloud warehouse; the YAML contracts and SQL models
  are dbt-style, not a production dbt/Snowflake deployment. No production
  data-contract platform (e.g. Monte Carlo, Soda, Great Expectations)
  experience is claimed.
- The lineage parser is intentionally small: models must be a single
  `SELECT ... FROM` with no CTEs or subqueries, and it does **not** resolve
  table aliases — a bare identifier is linked to every source table that
  carries that column (e.g. `mart_churn.plan` links to both
  `stg_customers.plan` and `stg_subscriptions.plan`). It refuses SQL it
  cannot parse rather than guessing.
- Freshness is measured against the newest date anywhere in the warehouse
  (the data-through date), with a 30-day SLA for this monthly-grained data.

## How to explain it in 60 seconds

> "Producers and consumers kept breaking each other — a column rename would
> silently break downstream dashboards. I wrote data contracts in YAML for
> each dataset and a validator that checks schema, nulls, uniqueness, value
> sets, ranges, foreign keys, row counts and freshness. Then I parse the SQL
> models to build column-level lineage, so `impact customers.plan` lists
> every downstream model before a change ships, and a v1→v2 diff flags
> breaking changes with the affected models. On synthetic data the validator
> catches all 5 injected defect classes with exact counts, and the diff
> correctly flags the dropped `plan` column and the renamed `amount` as
> breaking while the nullable `segment` addition is safe."
