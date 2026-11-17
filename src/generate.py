# Data Contracts & Lineage — synthetic SaaS warehouse
# Project 22 — data contracts as YAML, validated against the warehouse;
# column-level lineage parsed from SQL models; impact analysis;
# breaking-change detection between contract versions.
# SYNTHETIC DATA — portfolio skill demo, not work experience.
"""Seeded synthetic data generator for the contracts/lineage demo warehouse."""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

SEED = 42
START = date(2025, 1, 1)
END = date(2026, 10, 31)

PLANS = ["starter", "growth", "pro", "enterprise"]
PLAN_PRICE = {"starter": 29.0, "growth": 79.0, "pro": 199.0, "enterprise": 499.0}
REGIONS = ["us-west", "us-east", "eu-west", "apac"]
METHODS = ["card", "bank", "paypal"]
FIRST = ["Ava", "Liam", "Maya", "Noah", "Zoe", "Ethan", "Ivy", "Lucas", "Nora",
         "Owen", "Ruby", "Felix", "Tara", "Hugo", "Lena", "Marcus", "Priya",
         "Diego", "Sana", "Kenji"]
LAST = ["Tanaka", "Patel", "Garcia", "Kim", "Novak", "Okafor", "Larsen", "Dubois",
        "Silva", "Chen", "Meyer", "Rossi", "Kaur", "Novak", "Fischer", "Ali",
        "Costa", "Berg", "Sharma", "Wong"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    plan TEXT NOT NULL,
    region TEXT NOT NULL,
    signup_date TEXT NOT NULL,
    is_active INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    plan TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    order_date TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    payment_date TEXT NOT NULL,
    amount REAL NOT NULL,
    method TEXT NOT NULL,
    status TEXT NOT NULL
);
"""


def _rand_date(rng, start=START, end=END):
    return start + timedelta(days=rng.randrange((end - start).days + 1))


def generate(db_path, n_customers=300, seed=SEED):
    """Generate the warehouse from scratch (deterministic for a given seed)."""
    rng = random.Random(seed)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)

    customers = []
    for i in range(1, n_customers + 1):
        cid = f"C{i:04d}"
        plan = rng.choices(PLANS, weights=[0.40, 0.30, 0.20, 0.10])[0]
        signup = _rand_date(rng)
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        email = f"{name.lower().replace(' ', '.')}.{i}@example.com"
        customers.append((cid, name, email, plan, rng.choice(REGIONS),
                          signup.isoformat(), 1))
    con.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?)", customers)

    subs, orders, payments = [], [], []
    order_no = 0
    for cid, _name, _email, plan, _region, signup, _active in customers:
        sid = f"S{cid[1:]}"
        start = date.fromisoformat(signup)
        ended = rng.random() < 0.25
        end = (_rand_date(rng, start, END).isoformat() if ended else None)
        subs.append((sid, cid, plan, start.isoformat(), end,
                     "cancelled" if ended else "active"))
        # 4-9 orders per customer, monthly-ish cadence from signup
        n_orders = rng.randint(4, 9)
        for _ in range(n_orders):
            order_no += 1
            oid = f"O{order_no:05d}"
            odate = _rand_date(rng, start, END)
            price = PLAN_PRICE[plan]
            amount = round(price * rng.uniform(0.9, 1.1), 2)
            status = rng.choices(["paid", "refunded", "failed"],
                                 weights=[0.88, 0.04, 0.08])[0]
            orders.append((oid, cid, odate.isoformat(), amount, "USD", status))
            if status != "failed":
                pid = f"P{order_no:05d}"
                payments.append((pid, oid, odate.isoformat(), amount,
                                 rng.choice(METHODS), status))
    con.executemany("INSERT INTO subscriptions VALUES (?,?,?,?,?,?)", subs)
    con.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?)", orders)
    con.executemany("INSERT INTO payments VALUES (?,?,?,?,?,?)", payments)
    con.commit()
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("customers", "subscriptions", "orders", "payments")}
    con.close()
    return counts


if __name__ == "__main__":
    import sys
    print(generate(sys.argv[1] if len(sys.argv) > 1 else "data/warehouse.db"))
