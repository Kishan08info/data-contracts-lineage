-- mart_churn: ended subscriptions by month and plan.
-- depends_on: stg_subscriptions, stg_customers
SELECT
    strftime('%Y-%m', s.end_date) AS month,
    c.plan AS plan,
    COUNT(*) AS ended_subscriptions
FROM stg_subscriptions s
JOIN stg_customers c ON s.customer_id = c.customer_id
WHERE s.status = 'cancelled'
GROUP BY month, c.plan;
