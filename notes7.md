```sql
-- ============================================================
-- VELOCITY FEATURES IN BIGQUERY
-- Three customers, three windows (30d, 90d, 360d)
-- Valid lags per window to avoid right-censoring
-- ============================================================

-- Configuration
-- COMPUTATION_DATE = 2024-03-31
-- w30  valid lags: 1d, 3d
-- w90  valid lags: 1d, 3d, 7d  
-- w360 valid lags: 1d, 3d, 7d, 14d, 30d

WITH

-- ============================================================
-- RAW DATA - replace with your actual table reference
-- ============================================================

raw_transactions AS (
    SELECT * FROM UNNEST([

        -- Customer A: stable hairdresser, normal velocity
        STRUCT('A' AS customer_id, DATE '2024-03-01' AS transaction_date, 'credit' AS direction, 3200.0 AS value),
        STRUCT('A', DATE '2024-03-02', 'credit', 2800.0),
        STRUCT('A', DATE '2024-03-08', 'credit', 3100.0),
        STRUCT('A', DATE '2024-03-09', 'credit', 2900.0),
        STRUCT('A', DATE '2024-03-15', 'credit', 3300.0),
        STRUCT('A', DATE '2024-03-16', 'credit', 2700.0),
        STRUCT('A', DATE '2024-03-22', 'credit', 3000.0),
        STRUCT('A', DATE '2024-03-23', 'credit', 2600.0),
        STRUCT('A', DATE '2024-03-05', 'debit',  1200.0),
        STRUCT('A', DATE '2024-03-12', 'debit',  800.0),
        STRUCT('A', DATE '2024-03-19', 'debit',  950.0),
        STRUCT('A', DATE '2024-03-26', 'debit',  1100.0),
        STRUCT('A', DATE '2024-03-28', 'debit',  4200.0),
        -- Anchor period
        STRUCT('A', DATE '2023-03-01', 'credit', 2900.0),
        STRUCT('A', DATE '2023-03-08', 'credit', 2700.0),
        STRUCT('A', DATE '2023-03-15', 'credit', 3100.0),
        STRUCT('A', DATE '2023-03-22', 'credit', 2800.0),
        STRUCT('A', DATE '2023-03-06', 'debit',  1100.0),
        STRUCT('A', DATE '2023-03-13', 'debit',  900.0),
        STRUCT('A', DATE '2023-03-20', 'debit',  850.0),
        STRUCT('A', DATE '2023-03-27', 'debit',  4100.0),

        -- Customer B: recently changed behaviour - suspected layering
        STRUCT('B', DATE '2024-03-01', 'credit', 45000.0),
        STRUCT('B', DATE '2024-03-01', 'debit',  44200.0),
        STRUCT('B', DATE '2024-03-08', 'credit', 38000.0),
        STRUCT('B', DATE '2024-03-08', 'debit',  37500.0),
        STRUCT('B', DATE '2024-03-15', 'credit', 52000.0),
        STRUCT('B', DATE '2024-03-16', 'debit',  51000.0),
        STRUCT('B', DATE '2024-03-22', 'credit', 41000.0),
        STRUCT('B', DATE '2024-03-22', 'debit',  40500.0),
        -- Anchor period - normal pattern
        STRUCT('B', DATE '2023-03-01', 'credit', 8500.0),
        STRUCT('B', DATE '2023-03-08', 'credit', 7200.0),
        STRUCT('B', DATE '2023-03-15', 'credit', 9100.0),
        STRUCT('B', DATE '2023-03-22', 'credit', 8800.0),
        STRUCT('B', DATE '2023-03-07', 'debit',  2100.0),
        STRUCT('B', DATE '2023-03-14', 'debit',  1800.0),
        STRUCT('B', DATE '2023-03-21', 'debit',  2400.0),
        STRUCT('B', DATE '2023-03-28', 'debit',  8900.0),

        -- Customer C: always been a pass-through
        STRUCT('C', DATE '2024-03-01', 'credit', 28000.0),
        STRUCT('C', DATE '2024-03-01', 'debit',  27500.0),
        STRUCT('C', DATE '2024-03-07', 'credit', 19000.0),
        STRUCT('C', DATE '2024-03-07', 'debit',  18800.0),
        STRUCT('C', DATE '2024-03-14', 'credit', 33000.0),
        STRUCT('C', DATE '2024-03-15', 'debit',  32500.0),
        STRUCT('C', DATE '2024-03-21', 'credit', 24000.0),
        STRUCT('C', DATE '2024-03-21', 'debit',  23700.0),
        -- Anchor period - same pattern
        STRUCT('C', DATE '2023-03-01', 'credit', 25000.0),
        STRUCT('C', DATE '2023-03-01', 'debit',  24600.0),
        STRUCT('C', DATE '2023-03-07', 'credit', 18000.0),
        STRUCT('C', DATE '2023-03-07', 'debit',  17800.0),
        STRUCT('C', DATE '2023-03-14', 'credit', 29000.0),
        STRUCT('C', DATE '2023-03-15', 'debit',  28500.0),
        STRUCT('C', DATE '2023-03-21', 'credit', 22000.0),
        STRUCT('C', DATE '2023-03-21', 'debit',  21800.0)

    ])
),

-- ============================================================
-- STEP 1 - DAILY FLOWS PER CUSTOMER
-- Aggregate to day level before any window logic
-- ============================================================

daily_flows AS (
    SELECT
        customer_id,
        transaction_date,
        SUM(CASE WHEN direction = 'credit' THEN value ELSE 0 END) AS daily_credits,
        SUM(CASE WHEN direction = 'debit'  THEN value ELSE 0 END) AS daily_debits
    FROM raw_transactions
    GROUP BY customer_id, transaction_date
),

-- ============================================================
-- STEP 2 - TOTAL CREDITS PER CUSTOMER PER WINDOW
-- Denominator for velocity calculation
-- One CTE per window
-- ============================================================

total_credits_w30 AS (
    SELECT
        customer_id,
        SUM(daily_credits) AS total_credits_w30
    FROM daily_flows
    WHERE transaction_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 30 DAY)
    AND   transaction_date <= DATE '2024-03-31'
    GROUP BY customer_id
),

total_credits_w90 AS (
    SELECT
        customer_id,
        SUM(daily_credits) AS total_credits_w90
    FROM daily_flows
    WHERE transaction_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 90 DAY)
    AND   transaction_date <= DATE '2024-03-31'
    GROUP BY customer_id
),

total_credits_w360 AS (
    SELECT
        customer_id,
        SUM(daily_credits) AS total_credits_w360
    FROM daily_flows
    WHERE transaction_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 360 DAY)
    AND   transaction_date <= DATE '2024-03-31'
    GROUP BY customer_id
),

-- ============================================================
-- STEP 3 - CREDIT DAYS PER WINDOW
-- One row per customer per credit day
-- This is the left side of the lag join
-- ============================================================

credit_days_w30 AS (
    SELECT
        customer_id,
        transaction_date AS credit_date,
        daily_credits
    FROM daily_flows
    WHERE daily_credits > 0
    AND   transaction_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 30 DAY)
    AND   transaction_date <= DATE '2024-03-31'
),

credit_days_w90 AS (
    SELECT
        customer_id,
        transaction_date AS credit_date,
        daily_credits
    FROM daily_flows
    WHERE daily_credits > 0
    AND   transaction_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 90 DAY)
    AND   transaction_date <= DATE '2024-03-31'
),

credit_days_w360 AS (
    SELECT
        customer_id,
        transaction_date AS credit_date,
        daily_credits
    FROM daily_flows
    WHERE daily_credits > 0
    AND   transaction_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 360 DAY)
    AND   transaction_date <= DATE '2024-03-31'
),

-- ============================================================
-- STEP 4 - DEBIT DAYS PER WINDOW
-- One row per customer per debit day
-- This is the right side of the lag join
-- ============================================================

debit_days_w30 AS (
    SELECT
        customer_id,
        transaction_date AS debit_date,
        daily_debits
    FROM daily_flows
    WHERE daily_debits > 0
    AND   transaction_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 30 DAY)
    AND   transaction_date <= DATE '2024-03-31'
),

debit_days_w90 AS (
    SELECT
        customer_id,
        transaction_date AS debit_date,
        daily_debits
    FROM daily_flows
    WHERE daily_debits > 0
    AND   transaction_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 90 DAY)
    AND   transaction_date <= DATE '2024-03-31'
),

debit_days_w360 AS (
    SELECT
        customer_id,
        transaction_date AS debit_date,
        daily_debits
    FROM daily_flows
    WHERE daily_debits > 0
    AND   transaction_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 360 DAY)
    AND   transaction_date <= DATE '2024-03-31'
),

-- ============================================================
-- STEP 5 - LAG JOINS
-- For each credit day, find debits within N days
-- Join credit days to debit days within the lag window
-- Weight each credit day by its share of total window credits
-- One CTE per window per lag
-- ============================================================

-- W30 lags (1d and 3d only - censoring constraint)

lag_w30_1d AS (
    SELECT
        c.customer_id,
        SUM(
            SAFE_DIVIDE(c.daily_credits, t.total_credits_w30) *
            d.daily_debits
        ) AS weighted_debits
    FROM credit_days_w30 c
    LEFT JOIN total_credits_w30 t
        ON c.customer_id = t.customer_id
    LEFT JOIN debit_days_w30 d
        ON  c.customer_id = d.customer_id
        AND d.debit_date  > c.credit_date
        AND d.debit_date <= DATE_ADD(c.credit_date, INTERVAL 1 DAY)
    GROUP BY c.customer_id
),

lag_w30_3d AS (
    SELECT
        c.customer_id,
        SUM(
            SAFE_DIVIDE(c.daily_credits, t.total_credits_w30) *
            d.daily_debits
        ) AS weighted_debits
    FROM credit_days_w30 c
    LEFT JOIN total_credits_w30 t
        ON c.customer_id = t.customer_id
    LEFT JOIN debit_days_w30 d
        ON  c.customer_id = d.customer_id
        AND d.debit_date  > c.credit_date
        AND d.debit_date <= DATE_ADD(c.credit_date, INTERVAL 3 DAY)
    GROUP BY c.customer_id
),

-- W90 lags (1d, 3d, 7d)

lag_w90_1d AS (
    SELECT
        c.customer_id,
        SUM(
            SAFE_DIVIDE(c.daily_credits, t.total_credits_w90) *
            d.daily_debits
        ) AS weighted_debits
    FROM credit_days_w90 c
    LEFT JOIN total_credits_w90 t
        ON c.customer_id = t.customer_id
    LEFT JOIN debit_days_w90 d
        ON  c.customer_id = d.customer_id
        AND d.debit_date  > c.credit_date
        AND d.debit_date <= DATE_ADD(c.credit_date, INTERVAL 1 DAY)
    GROUP BY c.customer_id
),

lag_w90_3d AS (
    SELECT
        c.customer_id,
        SUM(
            SAFE_DIVIDE(c.daily_credits, t.total_credits_w90) *
            d.daily_debits
        ) AS weighted_debits
    FROM credit_days_w90 c
    LEFT JOIN total_credits_w90 t
        ON c.customer_id = t.customer_id
    LEFT JOIN debit_days_w90 d
        ON  c.customer_id = d.customer_id
        AND d.debit_date  > c.credit_date
        AND d.debit_date <= DATE_ADD(c.credit_date, INTERVAL 3 DAY)
    GROUP BY c.customer_id
),

lag_w90_7d AS (
    SELECT
        c.customer_id,
        SUM(
            SAFE_DIVIDE(c.daily_credits, t.total_credits_w90) *
            d.daily_debits
        ) AS weighted_debits
    FROM credit_days_w90 c
    LEFT JOIN total_credits_w90 t
        ON c.customer_id = t.customer_id
    LEFT JOIN debit_days_w90 d
        ON  c.customer_id = d.customer_id
        AND d.debit_date  > c.credit_date
        AND d.debit_date <= DATE_ADD(c.credit_date, INTERVAL 7 DAY)
    GROUP BY c.customer_id
),

-- W360 lags (1d, 3d, 7d, 14d, 30d)

lag_w360_1d AS (
    SELECT
        c.customer_id,
        SUM(
            SAFE_DIVIDE(c.daily_credits, t.total_credits_w360) *
            d.daily_debits
        ) AS weighted_debits
    FROM credit_days_w360 c
    LEFT JOIN total_credits_w360 t
        ON c.customer_id = t.customer_id
    LEFT JOIN debit_days_w360 d
        ON  c.customer_id = d.customer_id
        AND d.debit_date  > c.credit_date
        AND d.debit_date <= DATE_ADD(c.credit_date, INTERVAL 1 DAY)
    GROUP BY c.customer_id
),

lag_w360_3d AS (
    SELECT
        c.customer_id,
        SUM(
            SAFE_DIVIDE(c.daily_credits, t.total_credits_w360) *
            d.daily_debits
        ) AS weighted_debits
    FROM credit_days_w360 c
    LEFT JOIN total_credits_w360 t
        ON c.customer_id = t.customer_id
    LEFT JOIN debit_days_w360 d
        ON  c.customer_id = d.customer_id
        AND d.debit_date  > c.credit_date
        AND d.debit_date <= DATE_ADD(c.credit_date, INTERVAL 3 DAY)
    GROUP BY c.customer_id
),

lag_w360_7d AS (
    SELECT
        c.customer_id,
        SUM(
            SAFE_DIVIDE(c.daily_credits, t.total_credits_w360) *
            d.daily_debits
        ) AS weighted_debits
    FROM credit_days_w360 c
    LEFT JOIN total_credits_w360 t
        ON c.customer_id = t.customer_id
    LEFT JOIN debit_days_w360 d
        ON  c.customer_id = d.customer_id
        AND d.debit_date  > c.credit_date
        AND d.debit_date <= DATE_ADD(c.credit_date, INTERVAL 7 DAY)
    GROUP BY c.customer_id
),

lag_w360_14d AS (
    SELECT
        c.customer_id,
        SUM(
            SAFE_DIVIDE(c.daily_credits, t.total_credits_w360) *
            d.daily_debits
        ) AS weighted_debits
    FROM credit_days_w360 c
    LEFT JOIN total_credits_w360 t
        ON c.customer_id = t.customer_id
    LEFT JOIN debit_days_w360 d
        ON  c.customer_id = d.customer_id
        AND d.debit_date  > c.credit_date
        AND d.debit_date <= DATE_ADD(c.credit_date, INTERVAL 14 DAY)
    GROUP BY c.customer_id
),

lag_w360_30d AS (
    SELECT
        c.customer_id,
        SUM(
            SAFE_DIVIDE(c.daily_credits, t.total_credits_w360) *
            d.daily_debits
        ) AS weighted_debits
    FROM credit_days_w360 c
    LEFT JOIN total_credits_w360 t
        ON c.customer_id = t.customer_id
    LEFT JOIN debit_days_w360 d
        ON  c.customer_id = d.customer_id
        AND d.debit_date  > c.credit_date
        AND d.debit_date <= DATE_ADD(c.credit_date, INTERVAL 30 DAY)
    GROUP BY c.customer_id
),

-- ============================================================
-- STEP 6 - ASSEMBLE RAW VELOCITY VALUES
-- Convert weighted debits to velocity scores (0 to 1)
-- Join all lags to a single customer spine
-- ============================================================

customer_spine AS (
    SELECT DISTINCT customer_id
    FROM raw_transactions
),

velocity_raw AS (
    SELECT
        s.customer_id,

        -- W30 velocities
        LEAST(COALESCE(SAFE_DIVIDE(l30_1.weighted_debits,  t30.total_credits_w30),  0), 1.0) AS velocity_lag_1d_w30,
        LEAST(COALESCE(SAFE_DIVIDE(l30_3.weighted_debits,  t30.total_credits_w30),  0), 1.0) AS velocity_lag_3d_w30,

        -- W90 velocities
        LEAST(COALESCE(SAFE_DIVIDE(l90_1.weighted_debits,  t90.total_credits_w90),  0), 1.0) AS velocity_lag_1d_w90,
        LEAST(COALESCE(SAFE_DIVIDE(l90_3.weighted_debits,  t90.total_credits_w90),  0), 1.0) AS velocity_lag_3d_w90,
        LEAST(COALESCE(SAFE_DIVIDE(l90_7.weighted_debits,  t90.total_credits_w90),  0), 1.0) AS velocity_lag_7d_w90,

        -- W360 velocities
        LEAST(COALESCE(SAFE_DIVIDE(l360_1.weighted_debits,  t360.total_credits_w360), 0), 1.0) AS velocity_lag_1d_w360,
        LEAST(COALESCE(SAFE_DIVIDE(l360_3.weighted_debits,  t360.total_credits_w360), 0), 1.0) AS velocity_lag_3d_w360,
        LEAST(COALESCE(SAFE_DIVIDE(l360_7.weighted_debits,  t360.total_credits_w360), 0), 1.0) AS velocity_lag_7d_w360,
        LEAST(COALESCE(SAFE_DIVIDE(l360_14.weighted_debits, t360.total_credits_w360), 0), 1.0) AS velocity_lag_14d_w360,
        LEAST(COALESCE(SAFE_DIVIDE(l360_30.weighted_debits, t360.total_credits_w360), 0), 1.0) AS velocity_lag_30d_w360,

        -- Total credits per window for context
        COALESCE(t30.total_credits_w30,   0) AS total_credits_w30,
        COALESCE(t90.total_credits_w90,   0) AS total_credits_w90,
        COALESCE(t360.total_credits_w360, 0) AS total_credits_w360

    FROM customer_spine s

    LEFT JOIN total_credits_w30  t30  ON s.customer_id = t30.customer_id
    LEFT JOIN total_credits_w90  t90  ON s.customer_id = t90.customer_id
    LEFT JOIN total_credits_w360 t360 ON s.customer_id = t360.customer_id

    LEFT JOIN lag_w30_1d  l30_1  ON s.customer_id = l30_1.customer_id
    LEFT JOIN lag_w30_3d  l30_3  ON s.customer_id = l30_3.customer_id

    LEFT JOIN lag_w90_1d  l90_1  ON s.customer_id = l90_1.customer_id
    LEFT JOIN lag_w90_3d  l90_3  ON s.customer_id = l90_3.customer_id
    LEFT JOIN lag_w90_7d  l90_7  ON s.customer_id = l90_7.customer_id

    LEFT JOIN lag_w360_1d  l360_1  ON s.customer_id = l360_1.customer_id
    LEFT JOIN lag_w360_3d  l360_3  ON s.customer_id = l360_3.customer_id
    LEFT JOIN lag_w360_7d  l360_7  ON s.customer_id = l360_7.customer_id
    LEFT JOIN lag_w360_14d l360_14 ON s.customer_id = l360_14.customer_id
    LEFT JOIN lag_w360_30d l360_30 ON s.customer_id = l360_30.customer_id
),

-- ============================================================
-- STEP 7 - DERIVED FEATURES
-- Steepness, AUC, and shift features
-- These are the features that go into the model
-- ============================================================

velocity_derived AS (
    SELECT
        customer_id,

        -- Raw velocities (kept for dashboard drilldown)
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
        -- How front-loaded is the velocity curve
        -- High = money moves immediately
        -- Low  = money moves gradually
        SAFE_DIVIDE(
            velocity_lag_1d_w30,
            NULLIF(velocity_lag_3d_w30, 0)
        )                                           AS steepness_w30,

        SAFE_DIVIDE(
            velocity_lag_1d_w90,
            NULLIF(velocity_lag_7d_w90, 0)
        )                                           AS steepness_w90,

        SAFE_DIVIDE(
            velocity_lag_1d_w360,
            NULLIF(velocity_lag_30d_w360, 0)
        )                                           AS steepness_w360,

        -- AUC per window (average of available lags)
        -- Overall pass-through tendency
        (velocity_lag_1d_w30 + velocity_lag_3d_w30)
            / 2.0                                   AS auc_w30,

        (velocity_lag_1d_w90 +
         velocity_lag_3d_w90 +
         velocity_lag_7d_w90)
            / 3.0                                   AS auc_w90,

        (velocity_lag_1d_w360  +
         velocity_lag_3d_w360  +
         velocity_lag_7d_w360  +
         velocity_lag_14d_w360 +
         velocity_lag_30d_w360)
            / 5.0                                   AS auc_w360,

        -- Comparable AUC: use same lags across windows for fair shift
        (velocity_lag_1d_w360 + velocity_lag_3d_w360)
            / 2.0                                   AS auc_w360_comparable_to_w30,

        -- Context
        total_credits_w30,
        total_credits_w90,
        total_credits_w360

    FROM velocity_raw
),

-- ============================================================
-- STEP 8 - SHIFT FEATURES
-- Recent vs baseline
-- Positive = recent more pass-through than baseline
-- Negative = recent less pass-through than baseline
-- These are the primary model inputs
-- ============================================================

velocity_final AS (
    SELECT
        customer_id,

        -- Raw velocities (dashboard use)
        velocity_lag_1d_w30,
        velocity_lag_3d_w30,
        velocity_lag_1d_w360,
        velocity_lag_3d_w360,
        velocity_lag_30d_w360,

        -- Steepness (model input)
        ROUND(steepness_w30,  4)                    AS steepness_w30,
        ROUND(steepness_w90,  4)                    AS steepness_w90,
        ROUND(steepness_w360, 4)                    AS steepness_w360,

        -- AUC (model input)
        ROUND(auc_w30,  4)                          AS auc_w30,
        ROUND(auc_w90,  4)                          AS auc_w90,
        ROUND(auc_w360, 4)                          AS auc_w360,

        -- SHIFT FEATURES - most important for anomaly detection
        -- Change in 1-day velocity: recent vs baseline
        ROUND(velocity_lag_1d_w30 - velocity_lag_1d_w360, 4)
                                                    AS shift_velocity_1d,

        -- Change in 3-day velocity: recent vs baseline
        ROUND(velocity_lag_3d_w30 - velocity_lag_3d_w360, 4)
  