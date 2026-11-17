-- stg_subscriptions: staging model for raw subscriptions.
-- depends_on: subscriptions
SELECT
    subscription_id,
    customer_id,
    plan,
    start_date,
    end_date,
    status
FROM subscriptions;
