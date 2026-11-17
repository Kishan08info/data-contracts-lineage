-- stg_orders: staging model for raw orders.
-- depends_on: orders
SELECT
    order_id,
    customer_id,
    order_date,
    amount,
    currency,
    status
FROM orders;
