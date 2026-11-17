-- mart_monthly_revenue: paid revenue by month and plan.
-- depends_on: stg_orders, stg_customers
SELECT
    strftime('%Y-%m', o.order_date) AS month,
    c.plan AS plan,
    SUM(o.amount) AS revenue,
    COUNT(*) AS paid_orders
FROM stg_orders o
JOIN stg_customers c ON o.customer_id = c.customer_id
WHERE o.status = 'paid'
GROUP BY month, c.plan;
