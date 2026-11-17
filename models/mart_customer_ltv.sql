-- mart_customer_ltv: lifetime value per customer.
-- depends_on: stg_orders
SELECT
    customer_id,
    SUM(amount) AS total_paid,
    COUNT(*) AS order_count,
    MIN(order_date) AS first_order_date,
    MAX(order_date) AS last_order_date
FROM stg_orders
WHERE status = 'paid'
GROUP BY customer_id;
