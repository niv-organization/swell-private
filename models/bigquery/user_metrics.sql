-- BigQuery SQL model for user metrics
WITH user_events AS (
    SELECT
        user_id,
        event_date,
        event_name,
        SAFE_CAST(event_params.value AS INT64) AS metric_value
    FROM `project.dataset.events`
    WHERE event_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
),

daily_aggregates AS (
    SELECT
        user_id,
        event_date,
        COUNT(*) AS event_count,
        SUM(metric_value) AS total_value
    FROM user_events
    GROUP BY user_id, event_date
),

user_segments AS (
    SELECT
        user_id,
        ARRAY_AGG(STRUCT(event_date, event_count, total_value)) AS daily_metrics,
        DATE_DIFF(MAX(event_date), MIN(event_date), DAY) AS active_days
    FROM daily_aggregates
    GROUP BY user_id
)

SELECT
    u.user_id,
    u.active_days,
    UNNEST(u.daily_metrics) AS metrics,
    FORMAT_DATE('%Y-%m', CURRENT_DATE()) AS report_month
FROM user_segments u
WHERE u.active_days > 0
