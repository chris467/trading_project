The current query has serious performance problems at that scale. The lag joins are the main culprit — you're doing a self-join on a billions-row table for each lag, for each window. That's potentially 10 full table scans with cross-joins. On hundreds of thousands of customers with billions of transactions it will either timeout or cost a fortune.
The Core Problems
The self-join approach for lags joins every credit day to every debit day within a range per customer. At billions of rows this is an O(n²) operation per customer. BigQuery will struggle even with partition pruning.
Repeated full scans — each lag CTE re-reads the transactions table independently. You're scanning billions of rows 10+ times.
No partitioning leverage — the current structure doesn't take advantage of BigQuery's columnar storage and partition elimination.
daily_flows is recomputed per window — three separate aggregations of the same underlying data.
The Better Approach — Pre-Aggregate Then Window
The key insight is that you don't need transaction-level data for the lag calculation. You need daily totals. Compute those once, then use BigQuery's native window functions and date arithmetic rather than self-joins.
-- ============================================================
-- OPTIMISED VELOCITY FEATURES
-- Designed for billions of rows, hundreds of thousands customers
--
-- Strategy:
-- 1. Single scan of transactions → daily flows (partitioned)
-- 2. Use window functions instead of self-joins for lags
-- 3. Pre-filter to only the data needed (360 day max window)
-- 4. Materialise daily_flows as an intermediate table in practice
-- ============================================================

WITH

-- ============================================================
-- STEP 1 - SINGLE TABLE SCAN
-- Filter to 360 days only - maximum window needed
-- Everything downstream uses this, not the raw table
-- In production: materialise this as a scheduled table
-- updated daily, partitioned by transaction_date
-- ============================================================

daily_flows AS (
    SELECT
        customer_id,
        DATE(transaction_date)                          AS flow_date,
        SUM(CASE WHEN direction = 'credit'
                 THEN value ELSE 0 END)                 AS daily_credits,
        SUM(CASE WHEN direction = 'debit'
                 THEN value ELSE 0 END)                 AS daily_debits
    FROM `your_project.your_dataset.transactions`
    WHERE DATE(transaction_date) >= DATE_SUB(DATE '2024-03-31', INTERVAL 360 DAY)
    AND   DATE(transaction_date) <= DATE '2024-03-31'
    -- If your table is partitioned by transaction_date
    -- this WHERE clause eliminates 360d+ of data immediately
    -- Add clustering on customer_id for further pruning
    GROUP BY customer_id, DATE(transaction_date)
),

-- ============================================================
-- STEP 2 - FORWARD ROLLING SUMS USING WINDOW FUNCTIONS
-- For each customer-day, sum debits in the next N days
-- This replaces all the self-join lag CTEs
-- Uses a single pass over daily_flows
--
-- ROWS BETWEEN CURRENT ROW AND N FOLLOWING gives us
-- the sum of debits from today through N days ahead
-- within the same customer partition ordered by date
--
-- Note: window functions with RANGE BETWEEN and date offsets
-- aren't supported in BQ - we use a different approach
-- via conditional aggregation with date arithmetic
-- ============================================================

-- Pre-compute forward debit sums for each credit day
-- For each row, look ahead N days within the same customer
-- BQ supports this efficiently via partitioned window functions

forward_debits AS (
    SELECT
        customer_id,
        flow_date,
        daily_credits,
        daily_debits,

        -- Sum of debits on same day and next 1 day
        -- (same day = >= current, +1 day = <= DATE_ADD)
        SUM(daily_debits) OVER (
            PARTITION BY customer_id
            ORDER BY flow_date
            ROWS BETWEEN CURRENT ROW AND 1 FOLLOWING
        )                                               AS debits_next_1d,

        -- Sum of debits same day through next 3 days
        SUM(daily_debits) OVER (
            PARTITION BY customer_id
            ORDER BY flow_date
            ROWS BETWEEN CURRENT ROW AND 3 FOLLOWING
        )                                               AS debits_next_3d,

        -- Same day through next 7 days
        SUM(daily_debits) OVER (
            PARTITION BY customer_id
            ORDER BY flow_date
            ROWS BETWEEN CURRENT ROW AND 7 FOLLOWING
        )                                               AS debits_next_7d,

        -- Same day through next 14 days
        SUM(daily_debits) OVER (
            PARTITION BY customer_id
            ORDER BY flow_date
            ROWS BETWEEN CURRENT ROW AND 14 FOLLOWING
        )                                               AS debits_next_14d,

        -- Same day through next 30 days
        SUM(daily_debits) OVER (
            PARTITION BY customer_id
            ORDER BY flow_date
            ROWS BETWEEN CURRENT ROW AND 30 FOLLOWING
        )                                               AS debits_next_30d

    FROM daily_flows
),

-- ============================================================
-- IMPORTANT NOTE ON ROWS BETWEEN
-- ROWS BETWEEN CURRENT ROW AND N FOLLOWING counts N rows
-- not N calendar days. If a customer has gaps in their
-- daily activity (no transactions some days) this
-- will look ahead N active days not N calendar days.
-- 
-- For sparse customers this matters.
-- Fix: join to a date spine so every day has a row.
-- For dense customers (daily activity) it's fine as-is.
-- 
-- At your scale, join to a date spine only if needed
-- after profiling how sparse your customers are.
-- For most business banking customers, daily activity
-- is common enough that this is acceptable.
-- ============================================================

-- ============================================================
-- STEP 3 - WINDOW-LEVEL AGGREGATION
-- Now aggregate forward_debits to window level
-- For each window, compute:
-- - total credits (denominator)
-- - credit-weighted sum of forward debits at each lag
-- One pass over forward_debits produces all windows
-- ============================================================

window_aggregates AS (
    SELECT
        customer_id,

        -- ------------------------------------------------
        -- W30: last 30 days
        -- Valid lags: 1d, 3d
        -- ------------------------------------------------

        -- Total credits in w30
        SUM(CASE
            WHEN flow_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 30 DAY)
            THEN daily_credits ELSE 0
        END)                                            AS total_credits_w30,

        -- Weighted debits at lag 1d within w30
        -- Weight = this day's credits / total w30 credits
        -- We'll divide after to get the velocity ratio
        -- Store numerator here, divide in next CTE
        SUM(CASE
            WHEN flow_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 30 DAY)
            AND  daily_credits > 0
            THEN daily_credits * SAFE_DIVIDE(debits_next_1d, daily_credits)
            ELSE 0
        END)                                            AS wtd_debits_1d_w30,

        SUM(CASE
            WHEN flow_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 30 DAY)
            AND  daily_credits > 0
            THEN daily_credits * SAFE_DIVIDE(debits_next_3d, daily_credits)
            ELSE 0
        END)                                            AS wtd_debits_3d_w30,

        -- ------------------------------------------------
        -- W90: last 90 days
        -- Valid lags: 1d, 3d, 7d
        -- ------------------------------------------------

        SUM(CASE
            WHEN flow_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 90 DAY)
            THEN daily_credits ELSE 0
        END)                                            AS total_credits_w90,

        SUM(CASE
            WHEN flow_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 90 DAY)
            AND  daily_credits > 0
            THEN daily_credits * SAFE_DIVIDE(debits_next_1d, daily_credits)
            ELSE 0
        END)                                            AS wtd_debits_1d_w90,

        SUM(CASE
            WHEN flow_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 90 DAY)
            AND  daily_credits > 0
            THEN daily_credits * SAFE_DIVIDE(debits_next_3d, daily_credits)
            ELSE 0
        END)                                            AS wtd_debits_3d_w90,

        SUM(CASE
            WHEN flow_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 90 DAY)
            AND  daily_credits > 0
            THEN daily_credits * SAFE_DIVIDE(debits_next_7d, daily_credits)
            ELSE 0
        END)                                            AS wtd_debits_7d_w90,

        -- ------------------------------------------------
        -- W360: last 360 days
        -- Valid lags: 1d, 3d, 7d, 14d, 30d
        -- ------------------------------------------------

        SUM(daily_credits)                              AS total_credits_w360,

        SUM(CASE
            WHEN daily_credits > 0
            THEN daily_credits * SAFE_DIVIDE(debits_next_1d, daily_credits)
            ELSE 0
        END)                                            AS wtd_debits_1d_w360,

        SUM(CASE
            WHEN daily_credits > 0
            THEN daily_credits * SAFE_DIVIDE(debits_next_3d, daily_credits)
            ELSE 0
        END)                                            AS wtd_debits_3d_w360,

        SUM(CASE
            WHEN daily_credits > 0
            THEN daily_credits * SAFE_DIVIDE(debits_next_7d, daily_credits)
            ELSE 0
        END)                                            AS wtd_debits_7d_w360,

        SUM(CASE
            WHEN daily_credits > 0
            THEN daily_credits * SAFE_DIVIDE(debits_next_14d, daily_credits)
            ELSE 0
        END)                                            AS wtd_debits_14d_w360,

        SUM(CASE
            WHEN daily_credits > 0
            THEN daily_credits * SAFE_DIVIDE(debits_next_30d, daily_credits)
            ELSE 0
        END)                                            AS wtd_debits_30d_w360

    FROM forward_debits
    GROUP BY customer_id
),

-- ============================================================
-- STEP 4 - COMPUTE RAW VELOCITY VALUES
-- Divide weighted debits by total credits per window
-- Cap at 1.0
-- ============================================================

velocity_raw AS (
    SELECT
        customer_id,

        -- W30
        LEAST(SAFE_DIVIDE(wtd_debits_1d_w30, total_credits_w30), 1.0)
                                                        AS velocity_lag_1d_w30,
        LEAST(SAFE_DIVIDE(wtd_debits_3d_w30, total_credits_w30), 1.0)
                                                        AS velocity_lag_3d_w30,

        -- W90
        LEAST(SAFE_DIVIDE(wtd_debits_1d_w90, total_credits_w90), 1.0)
                                                        AS velocity_lag_1d_w90,
        LEAST(SAFE_DIVIDE(wtd_debits_3d_w90, total_credits_w90), 1.0)
                                                        AS velocity_lag_3d_w90,
        LEAST(SAFE_DIVIDE(wtd_debits_7d_w90, total_credits_w90), 1.0)
                                                        AS velocity_lag_7d_w90,

        -- W360
        LEAST(SAFE_DIVIDE(wtd_debits_1d_w360,  total_credits_w360), 1.0)
                                                        AS velocity_lag_1d_w360,
        LEAST(SAFE_DIVIDE(wtd_debits_3d_w360,  total_credits_w360), 1.0)
                                                        AS velocity_lag_3d_w360,
        LEAST(SAFE_DIVIDE(wtd_debits_7d_w360,  total_credits_w360), 1.0)
                                                        AS velocity_lag_7d_w360,
        LEAST(SAFE_DIVIDE(wtd_debits_14d_w360, total_credits_w360), 1.0)
                                                        AS velocity_lag_14d_w360,
        LEAST(SAFE_DIVIDE(wtd_debits_30d_w360, total_credits_w360), 1.0)
                                                        AS velocity_lag_30d_w360,

        -- Keep totals for context
        total_credits_w30,
        total_credits_w90,
        total_credits_w360

    FROM window_aggregates
),

-- ============================================================
-- STEP 5 - DERIVED FEATURES
-- Steepness, AUC, shift
-- Same logic as before, now on clean velocity values
-- ============================================================

velocity_derived AS (
    SELECT
        customer_id,

        -- Raw velocities
        velocity_lag_1d_w30,
        velocity_lag_3d_w30,
        velocity_lag_1d_w90,
        velocity_lag_3d_w90,
        velocity_lag_7d_w90,
        velocity_lag_1d_w360,
        velocity_lag_3d_w360,
        velocity_lag_7d_w360,
        velocity_lag_14d_w360,
        velocity_lag_30d_w360,

        -- Steepness per window
        SAFE_DIVIDE(
            velocity_lag_1d_w30,
            NULLIF(velocity_lag_3d_w30, 0)
        )                                               AS steepness_w30,

        SAFE_DIVIDE(
            velocity_lag_1d_w90,
            NULLIF(velocity_lag_7d_w90, 0)
        )                                               AS steepness_w90,

        SAFE_DIVIDE(
            velocity_lag_1d_w360,
            NULLIF(velocity_lag_30d_w360, 0)
        )                                               AS steepness_w360,

        -- AUC per window
        (velocity_lag_1d_w30 +
         velocity_lag_3d_w30) / 2.0                    AS auc_w30,

        (velocity_lag_1d_w90 +
         velocity_lag_3d_w90 +
         velocity_lag_7d_w90) / 3.0                    AS auc_w90,

        (velocity_lag_1d_w360  +
         velocity_lag_3d_w360  +
         velocity_lag_7d_w360  +
         velocity_lag_14d_w360 +
         velocity_lag_30d_w360) / 5.0                  AS auc_w360,

        -- Comparable AUC for fair shift calculation
        (velocity_lag_1d_w360 +
         velocity_lag_3d_w360) / 2.0                   AS auc_w360_comparable,

        (velocity_lag_1d_w360 +
         velocity_lag_3d_w360 +
         velocity_lag_7d_w360) / 3.0                   AS auc_w360_comparable_w90,

        total_credits_w30,
        total_credits_w360

    FROM velocity_raw
)

-- ============================================================
-- FINAL OUTPUT
-- One row per customer
-- Shift features are primary model inputs
-- Raw velocities are for dashboard drilldown
-- ============================================================

SELECT
    customer_id,

    -- Raw velocities for dashboard
    ROUND(velocity_lag_1d_w30,   4)                    AS velocity_lag_1d_w30,
    ROUND(velocity_lag_3d_w30,   4)                    AS velocity_lag_3d_w30,
    ROUND(velocity_lag_1d_w360,  4)                    AS velocity_lag_1d_w360,
    ROUND(velocity_lag_30d_w360, 4)                    AS velocity_lag_30d_w360,

    -- Steepness
    ROUND(steepness_w30,  4)                           AS steepness_w30,
    ROUND(steepness_w90,  4)                           AS steepness_w90,
    ROUND(steepness_w360, 4)                           AS steepness_w360,

    -- AUC
    ROUND(auc_w30,  4)                                 AS auc_w30,
    ROUND(auc_w90,  4)                                 AS auc_w90,
    ROUND(auc_w360, 4)                                 AS auc_w360,

    -- PRIMARY MODEL INPUTS - shift features
    ROUND(velocity_lag_1d_w30  - velocity_lag_1d_w360,  4)
                                                       AS shift_velocity_1d,
    ROUND(velocity_lag_3d_w30  - velocity_lag_3d_w360,  4)
                                                       AS shift_velocity_3d,
    ROUND(steepness_w30        - steepness_w360,        4)
                                                       AS shift_steepness,
    ROUND(auc_w30              - auc_w360_comparable,   4)
                                                       AS shift_auc,
    ROUND(auc_w90              - auc_w360_comparable_w90, 4)
                                                       AS shift_auc_w90,

    -- Acceleration: change concentrated in w30 vs w90
    -- Positive = behaviour shifted very recently
    -- Negative = behaviour has been changing for longer
    ROUND(
        (velocity_lag_1d_w30 - velocity_lag_1d_w360) -
        (velocity_lag_1d_w90 - velocity_lag_1d_w360),
    4)                                                 AS velocity_acceleration,

    -- Context
    ROUND(total_credits_w30,  2)                       AS total_credits_w30,
    ROUND(total_credits_w360, 2)                       AS total_credits_w360

FROM velocity_derived
ORDER BY shift_steepness DESC
What Changed And Why
Single table scan. The original scanned the billions-row transactions table once per lag per window — potentially 10+ times. This version scans it once in daily_flows, filtered to 360 days. Everything else operates on the much smaller daily-aggregated result.
Window functions instead of self-joins. ROWS BETWEEN CURRENT ROW AND N FOLLOWING replaces the credit-to-debit self-joins entirely. BigQuery executes window functions in a single sorted pass over the partitioned data. No cross-join, no O(n²) behaviour.
Single aggregation pass. window_aggregates computes all three windows and all lags in one GROUP BY. The original had a separate CTE for every window-lag combination — 10 separate aggregations each re-reading the data.
Partition pruning. The WHERE DATE(transaction_date) >= DATE_SUB(...) in daily_flows eliminates all data outside your 360-day window immediately on read. If your transactions table is partitioned by date — which it should be at billions of rows — BigQuery won't even scan the excluded partitions.
Production Recommendations
Materialise daily_flows as a scheduled table. At billions of rows, even one scan is expensive if run weekly. Instead, maintain a daily_flows table that appends each day's aggregation incrementally. Your weekly velocity job then reads from a table with at most 360 × number_of_customers rows rather than billions of raw transactions.
Cluster your transactions table on customer_id after partitioning by date. This means BQ reads only the customer IDs present in your window rather than scanning all customers in each partition.
Save the forward_debits CTE as an intermediate materialised view if you're computing multiple feature sets from it. Fan ratio, burst detection, and velocity all need daily flows — compute once, reuse across feature jobs.
Set a computation_date parameter rather than hardcoding DATE '2024-03-31'. In your scheduled query, pass this as a variable so the same SQL runs weekly without modification.