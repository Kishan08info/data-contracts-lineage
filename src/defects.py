# Data Contracts & Lineage — synthetic SaaS warehouse
# Project 22
"""Inject a known, counted set of defects into a warehouse copy so the
contract validator can be shown catching them. Every defect count is
exact and asserted in the tests."""

import sqlite3

# (table, column, bad value, how many rows) — all deterministic.
DEFECTS = [
    ("orders", "amount", -49.99, 5),        # min_value violation
    ("orders", "status", "bogus", 1),       # allowed_values violation
    ("customers", "email", None, 4),        # not_null violation (email)
    ("customers", "email", "dup@example.com", 2),  # unique violation
    ("payments", "order_id", "O99999", 3),  # referential violation
]


def inject(db_path):
    """Apply the defects; returns {check: rows_affected} for the report."""
    con = sqlite3.connect(db_path)
    applied = {}
    # 5 negative amounts on the first 5 paid orders
    rows = con.execute(
        "SELECT order_id FROM orders WHERE status='paid' LIMIT 5").fetchall()
    for (oid,) in rows:
        con.execute("UPDATE orders SET amount=-49.99 WHERE order_id=?", (oid,))
    applied["min_value_orders.amount"] = len(rows)
    # 1 bogus status
    oid = con.execute(
        "SELECT order_id FROM orders LIMIT 1").fetchone()[0]
    con.execute("UPDATE orders SET status='bogus' WHERE order_id=?", (oid,))
    applied["allowed_values_orders.status"] = 1
    # 4 NULL emails
    rows = con.execute(
        "SELECT customer_id FROM customers LIMIT 4").fetchall()
    for (cid,) in rows:
        con.execute("UPDATE customers SET email=NULL WHERE customer_id=?", (cid,))
    applied["not_null_customers.email"] = len(rows)
    # 2 duplicate emails (overwrite two distinct customers with the same value)
    rows = con.execute(
        "SELECT customer_id FROM customers WHERE email IS NOT NULL "
        "LIMIT 2").fetchall()
    for (cid,) in rows:
        con.execute("UPDATE customers SET email='dup@example.com' "
                    "WHERE customer_id=?", (cid,))
    applied["unique_customers.email"] = len(rows)
    # 3 orphan payments (point at a never-existing order)
    rows = con.execute(
        "SELECT payment_id FROM payments LIMIT 3").fetchall()
    for (pid,) in rows:
        con.execute("UPDATE payments SET order_id='O99999' WHERE payment_id=?",
                    (pid,))
    applied["referential_payments.order_id"] = len(rows)
    con.commit()
    con.close()
    return applied
