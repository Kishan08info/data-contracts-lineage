-- stg_customers: staging model for raw customers.
-- depends_on: customers
SELECT
    customer_id,
    email,
    plan,
    region,
    signup_date,
    is_active
FROM customers;
