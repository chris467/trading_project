Got it. Since you've already done the windowed aggregations, I'll write these as point-in-time queries that you can wrap in your existing window logic. Each CTE builds cleanly on the previous one, one feature block at a time.
1. Peer Payment Overlap Score
-- ============================================================
-- PEER PAYMENT OVERLAP SCORE
-- How similar is this customer's beneficiary population
-- to their peer group's typical beneficiary population
-- ============================================================

WITH

-- Step 1: Total payment value per customer
customer_totals AS (
    SELECT
        customer_id,
        SUM(value) AS total_payment_value
    FROM `your_project.your_dataset.transactions`
    WHERE direction = 'debit'
    GROUP BY customer_id
),

-- Step 2: Payment value per customer per beneficiary
customer_bene_values AS (
    SELECT
        t.customer_id,
        t.beneficiary_id,
        SUM(t.value) AS bene_value
    FROM `your_project.your_dataset.transactions` t
    WHERE t.direction = 'debit'
    GROUP BY t.customer_id, t.beneficiary_id
),

-- Step 3: Payment share per customer per beneficiary
customer_bene_shares AS (
    SELECT
        cb.customer_id,
        cb.beneficiary_id,
        cb.bene_value,
        ct.total_payment_value,
        SAFE_DIVIDE(cb.bene_value, ct.total_payment_value) AS payment_share
    FROM customer_bene_values cb
    LEFT JOIN customer_totals ct
        ON cb.customer_id = ct.customer_id
),

-- Step 4: Join peer group assignments
customer_bene_with_peers AS (
    SELECT
        cbs.customer_id,
        cbs.beneficiary_id,
        cbs.payment_share,
        pg.peer_group_id
    FROM customer_bene_shares cbs
    LEFT JOIN `your_project.your_dataset.peer_groups` pg
        ON cbs.customer_id = pg.customer_id
),

-- Step 5: For each peer group, how many distinct customers
-- pay each beneficiary
peer_group_sizes AS (
    SELECT
        peer_group_id,
        COUNT(DISTINCT customer_id) AS peer_group_size
    FROM `your_project.your_dataset.peer_groups`
    GROUP BY peer_group_id
),

peer_bene_counts AS (
    SELECT
        cbp.peer_group_id,
        cbp.beneficiary_id,
        COUNT(DISTINCT cbp.customer_id) AS n_peer_customers_paying
    FROM customer_bene_with_peers cbp
    GROUP BY cbp.peer_group_id, cbp.beneficiary_id
),

-- Step 6: Prevalence of each beneficiary within peer group
peer_bene_prevalence AS (
    SELECT
        pbc.peer_group_id,
        pbc.beneficiary_id,
        pbc.n_peer_customers_paying,
        pgs.peer_group_size,
        SAFE_DIVIDE(
            pbc.n_peer_customers_paying,
            pgs.peer_group_size
        ) AS peer_bene_prevalence
    FROM peer_bene_counts pbc
    LEFT JOIN peer_group_sizes pgs
        ON pbc.peer_group_id = pgs.peer_group_id
),

-- Step 7: For each customer-beneficiary pair, score against
-- peer prevalence
customer_bene_scored AS (
    SELECT
        cbp.customer_id,
        cbp.beneficiary_id,
        cbp.payment_share,
        cbp.peer_group_id,
        COALESCE(pbp.peer_bene_prevalence, 0) AS peer_bene_prevalence,
        cbp.payment_share * COALESCE(pbp.peer_bene_prevalence, 0)
            AS overlap_contribution
    FROM customer_bene_with_peers cbp
    LEFT JOIN peer_bene_prevalence pbp
        ON cbp.peer_group_id = pbp.peer_group_id
        AND cbp.beneficiary_id = pbp.beneficiary_id
),

-- Step 8: Aggregate to single score per customer
-- Invert so high score = more anomalous (less overlap with peers)
peer_overlap_final AS (
    SELECT
        customer_id,
        SUM(overlap_contribution)           AS peer_overlap_raw,
        1 - SUM(overlap_contribution)       AS peer_overlap_score,
        COUNT(DISTINCT beneficiary_id)      AS n_distinct_benes,
        SUM(
            CASE WHEN peer_bene_prevalence = 0
            THEN payment_share ELSE 0 END
        )                                   AS pct_value_to_unseen_benes
    FROM customer_bene_scored
    GROUP BY customer_id
)

SELECT * FROM peer_overlap_final
2. Beneficiary Uniqueness Score (ICF)
-- ============================================================
-- BENEFICIARY UNIQUENESS SCORE
-- payment_share * ICF summed per customer
-- High = customer pays rare beneficiaries significantly
-- ============================================================

WITH

-- Step 1: Total customers in book
total_customers AS (
    SELECT COUNT(DISTINCT customer_id) AS n AS n_total_customers
    FROM `your_project.your_dataset.transactions`
),

-- Step 2: How many distinct customers pay each beneficiary
bene_customer_counts AS (
    SELECT
        beneficiary_id,
        COUNT(DISTINCT customer_id) AS n_customers_using
    FROM `your_project.your_dataset.transactions`
    WHERE direction = 'debit'
    GROUP BY beneficiary_id
),

-- Step 3: Inverse Customer Frequency
-- Common beneficiaries (HMRC, utilities) → ICF near 0
-- Rare beneficiaries → high ICF
bene_icf AS (
    SELECT
        bcc.beneficiary_id,
        bcc.n_customers_using,
        LN(
            SAFE_DIVIDE(tc.n_total_customers, bcc.n_customers_using)
        )                               AS icf,
        CASE
            WHEN bcc.n_customers_using <= 5    THEN 'unique'
            WHEN bcc.n_customers_using <= 20   THEN 'rare'
            WHEN bcc.n_customers_using <= 100  THEN 'uncommon'
            WHEN bcc.n_customers_using <= 1000 THEN 'common'
            ELSE 'ubiquitous'
        END                             AS rarity_tier
    FROM bene_customer_counts bcc
    CROSS JOIN total_customers tc
),

-- Step 4: Customer total payment value
customer_totals AS (
    SELECT
        customer_id,
        SUM(value) AS total_payment_value
    FROM `your_project.your_dataset.transactions`
    WHERE direction = 'debit'
    GROUP BY customer_id
),

-- Step 5: Customer payment value per beneficiary
customer_bene_values AS (
    SELECT
        customer_id,
        beneficiary_id,
        SUM(value) AS bene_value
    FROM `your_project.your_dataset.transactions`
    WHERE direction = 'debit'
    GROUP BY customer_id, beneficiary_id
),

-- Step 6: Payment share per customer per beneficiary
customer_bene_shares AS (
    SELECT
        cbv.customer_id,
        cbv.beneficiary_id,
        cbv.bene_value,
        SAFE_DIVIDE(cbv.bene_value, ct.total_payment_value)
            AS payment_share
    FROM customer_bene_values cbv
    LEFT JOIN customer_totals ct
        ON cbv.customer_id = ct.customer_id
),

-- Step 7: Join ICF to payment shares
customer_bene_icf AS (
    SELECT
        cbs.customer_id,
        cbs.beneficiary_id,
        cbs.payment_share,
        COALESCE(bi.icf, 0)             AS icf,
        COALESCE(bi.rarity_tier, 'unknown') AS rarity_tier,
        COALESCE(bi.n_customers_using, 0)   AS n_customers_using,
        cbs.payment_share * COALESCE(bi.icf, 0) AS pf_icf
    FROM customer_bene_shares cbs
    LEFT JOIN bene_icf bi
        ON cbs.beneficiary_id = bi.beneficiary_id
),

-- Step 8: Aggregate to single score per customer
bene_uniqueness_final AS (
    SELECT
        customer_id,

        -- Primary uniqueness score: sum of payment_share * ICF
        SUM(pf_icf)                     AS bene_uniqueness_score,

        -- Max single contribution - one very rare large payment
        MAX(pf_icf)                     AS bene_uniqueness_max,

        -- Proportion of value going to rare/unique beneficiaries
        SUM(CASE
            WHEN rarity_tier IN ('unique', 'rare')
            THEN payment_share ELSE 0
        END)                            AS pct_value_to_rare_benes,

        -- Count of unique/rare beneficiaries used
        COUNT(DISTINCT CASE
            WHEN rarity_tier IN ('unique', 'rare')
            THEN beneficiary_id
        END)                            AS n_rare_benes_used,

        -- Proportion going to ubiquitous benes (legitimacy signal)
        SUM(CASE
            WHEN rarity_tier = 'ubiquitous'
            THEN payment_share ELSE 0
        END)                            AS pct_value_to_ubiquitous_benes,

        -- Standard HHI while we're here
        SUM(POWER(payment_share, 2))    AS bene_hhi

    FROM customer_bene_icf
    GROUP BY customer_id
)

SELECT * FROM bene_uniqueness_final
3. Velocity Layering
-- ============================================================
-- VELOCITY LAYERING AT MULTIPLE TIME LAGS
-- How quickly does money leave after it arrives
-- Computed at 1, 3, 7, 14, 30 day lags
-- ============================================================

WITH

-- Step 1: Daily credit and debit totals per customer
daily_flows AS (
    SELECT
        customer_id,
        DATE(transaction_date)          AS flow_date,
        SUM(CASE WHEN direction = 'credit' THEN value ELSE 0 END)
                                        AS daily_credits,
        SUM(CASE WHEN direction = 'debit'  THEN value ELSE 0 END)
                                        AS daily_debits
    FROM `your_project.your_dataset.transactions`
    GROUP BY customer_id, DATE(transaction_date)
),

-- Step 2: Total credits per customer (denominator)
customer_credit_totals AS (
    SELECT
        customer_id,
        SUM(daily_credits)              AS total_credits
    FROM daily_flows
    GROUP BY customer_id
),

-- Step 3: For each credit day, sum debits within N lag days
-- Self join on same customer within date range
-- Do this for each lag separately then join

lag_1d AS (
    SELECT
        c.customer_id,
        SUM(
            SAFE_DIVIDE(c.daily_credits, ct.total_credits) *
            d.daily_debits
        )                               AS weighted_debits_lag_1d
    FROM daily_flows c
    LEFT JOIN customer_credit_totals ct
        ON c.customer_id = ct.customer_id
    LEFT JOIN daily_flows d
        ON c.customer_id = d.customer_id
        AND d.flow_date > c.flow_date
        AND d.flow_date <= DATE_ADD(c.flow_date, INTERVAL 1 DAY)
    WHERE c.daily_credits > 0
    GROUP BY c.customer_id
),

lag_3d AS (
    SELECT
        c.customer_id,
        SUM(
            SAFE_DIVIDE(c.daily_credits, ct.total_credits) *
            d.daily_debits
        )                               AS weighted_debits_lag_3d
    FROM daily_flows c
    LEFT JOIN customer_credit_totals ct
        ON c.customer_id = ct.customer_id
    LEFT JOIN daily_flows d
        ON c.customer_id = d.customer_id
        AND d.flow_date > c.flow_date
        AND d.flow_date <= DATE_ADD(c.flow_date, INTERVAL 3 DAY)
    WHERE c.daily_credits > 0
    GROUP BY c.customer_id
),

lag_7d AS (
    SELECT
        c.customer_id,
        SUM(
            SAFE_DIVIDE(c.daily_credits, ct.total_credits) *
            d.daily_debits
        )                               AS weighted_debits_lag_7d
    FROM daily_flows c
    LEFT JOIN customer_credit_totals ct
        ON c.customer_id = ct.customer_id
    LEFT JOIN daily_flows d
        ON c.customer_id = d.customer_id
        AND d.flow_date > c.flow_date
        AND d.flow_date <= DATE_ADD(c.flow_date, INTERVAL 7 DAY)
    WHERE c.daily_credits > 0
    GROUP BY c.customer_id
),

lag_14d AS (
    SELECT
        c.customer_id,
        SUM(
            SAFE_DIVIDE(c.daily_credits, ct.total_credits) *
            d.daily_debits
        )                               AS weighted_debits_lag_14d
    FROM daily_flows c
    LEFT JOIN customer_credit_totals ct
        ON c.customer_id = ct.customer_id
    LEFT JOIN daily_flows d
        ON c.customer_id = d.customer_id
        AND d.flow_date > c.flow_date
        AND d.flow_date <= DATE_ADD(c.flow_date, INTERVAL 14 DAY)
    WHERE c.daily_credits > 0
    GROUP BY c.customer_id
),

lag_30d AS (
    SELECT
        c.customer_id,
        SUM(
            SAFE_DIVIDE(c.daily_credits, ct.total_credits) *
            d.daily_debits
        )                               AS weighted_debits_lag_30d
    FROM daily_flows c
    LEFT JOIN customer_credit_totals ct
        ON c.customer_id = ct.customer_id
    LEFT JOIN daily_flows d
        ON c.customer_id = d.customer_id
        AND d.flow_date > c.flow_date
        AND d.flow_date <= DATE_ADD(c.flow_date, INTERVAL 30 DAY)
    WHERE c.daily_credits > 0
    GROUP BY c.customer_id
),

-- Step 4: Join all lags and derive shape features
velocity_combined AS (
    SELECT
        ct.customer_id,
        ct.total_credits,

        -- Clamp velocities to 0-1
        LEAST(SAFE_DIVIDE(l1.weighted_debits_lag_1d,  ct.total_credits), 1)
            AS velocity_lag_1d,
        LEAST(SAFE_DIVIDE(l3.weighted_debits_lag_3d,  ct.total_credits), 1)
            AS velocity_lag_3d,
        LEAST(SAFE_DIVIDE(l7.weighted_debits_lag_7d,  ct.total_credits), 1)
            AS velocity_lag_7d,
        LEAST(SAFE_DIVIDE(l14.weighted_debits_lag_14d, ct.total_credits), 1)
            AS velocity_lag_14d,
        LEAST(SAFE_DIVIDE(l30.weighted_debits_lag_30d, ct.total_credits), 1)
            AS velocity_lag_30d

    FROM customer_credit_totals ct
    LEFT JOIN lag_1d  l1  ON ct.customer_id = l1.customer_id
    LEFT JOIN lag_3d  l3  ON ct.customer_id = l3.customer_id
    LEFT JOIN lag_7d  l7  ON ct.customer_id = l7.customer_id
    LEFT JOIN lag_14d l14 ON ct.customer_id = l14.customer_id
    LEFT JOIN lag_30d l30 ON ct.customer_id = l30.customer_id
),

velocity_final AS (
    SELECT
        customer_id,
        velocity_lag_1d,
        velocity_lag_3d,
        velocity_lag_7d,
        velocity_lag_14d,
        velocity_lag_30d,

        -- Steepness: how front-loaded is the velocity curve
        -- High = most money moves out within 1 day
        SAFE_DIVIDE(
            velocity_lag_1d,
            velocity_lag_30d + 0.001
        )                               AS velocity_steepness,

        -- Area under curve: overall pass-through tendency
        (
            velocity_lag_1d +
            velocity_lag_3d +
            velocity_lag_7d +
            velocity_lag_14d +
            velocity_lag_30d
        ) / 5.0                         AS velocity_auc,

        -- Early concentration: proportion of 30d velocity
        -- achieved within first day
        SAFE_DIVIDE(
            velocity_lag_1d,
            NULLIF(velocity_lag_30d, 0)
        )                               AS velocity_early_concentration

    FROM velocity_combined
)

SELECT * FROM velocity_final
4. Burst Detection
-- ============================================================
-- BURST DETECTION
-- Identifies customers with sudden activity spikes
-- relative to their own historical baseline
-- ============================================================

WITH

-- Step 1: Weekly credit volumes per customer
weekly_volumes AS (
    SELECT
        customer_id,
        DATE_TRUNC(DATE(transaction_date), WEEK(MONDAY))
                                        AS week_start,
        SUM(value)                      AS weekly_credit_volume
    FROM `your_project.your_dataset.transactions`
    WHERE direction = 'credit'
    GROUP BY customer_id, DATE_TRUNC(DATE(transaction_date), WEEK(MONDAY))
),

-- Step 2: Rank weeks per customer oldest to newest
weekly_ranked AS (
    SELECT
        customer_id,
        week_start,
        weekly_credit_volume,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY week_start ASC
        )                               AS week_rank_asc,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY week_start DESC
        )                               AS week_rank_desc,
        COUNT(*) OVER (
            PARTITION BY customer_id
        )                               AS total_weeks
    FROM weekly_volumes
),

-- Step 3: Separate baseline weeks from recent weeks
-- Recent = last 12 weeks
-- Baseline = everything before that (up to 52 weeks prior)
baseline_weeks AS (
    SELECT
        customer_id,
        weekly_credit_volume
    FROM weekly_ranked
    WHERE week_rank_desc > 12           -- not in most recent 12 weeks
    AND week_rank_desc <= 64            -- at most 64 weeks back
    AND total_weeks >= 16               -- need enough history
),

recent_weeks AS (
    SELECT
        customer_id,
        weekly_credit_volume
    FROM weekly_ranked
    WHERE week_rank_desc <= 12          -- most recent 12 weeks
    AND total_weeks >= 16
),

-- Step 4: Baseline statistics per customer
-- Using median and MAD for robustness
baseline_stats AS (
    SELECT
        customer_id,
        AVG(weekly_credit_volume)       AS baseline_mean,

        -- Median approximation in BQ using PERCENTILE_CONT
        PERCENTILE_CONT(weekly_credit_volume, 0.5)
            OVER (PARTITION BY customer_id)
                                        AS baseline_median,

        STDDEV(weekly_credit_volume)    AS baseline_std,
        COUNT(*)                        AS n_baseline_weeks

    FROM baseline_weeks
    GROUP BY customer_id
),

-- BQ doesn't support MAD natively so compute via subquery
baseline_mad_prep AS (
    SELECT
        b.customer_id,
        ABS(b.weekly_credit_volume - bs.baseline_median)
            AS abs_deviation
    FROM baseline_weeks b
    LEFT JOIN baseline_stats bs
        ON b.customer_id = bs.customer_id
),

baseline_mad AS (
    SELECT
        customer_id,
        PERCENTILE_CONT(abs_deviation, 0.5)
            OVER (PARTITION BY customer_id)
                                        AS mad
    FROM baseline_mad_prep
    GROUP BY customer_id, abs_deviation
),

baseline_mad_final AS (
    SELECT
        customer_id,
        MAX(mad)                        AS mad
    FROM baseline_mad
    GROUP BY customer_id
),

-- Step 5: Recent week statistics
recent_stats AS (
    SELECT
        customer_id,
        MAX(weekly_credit_volume)       AS recent_max,
        AVG(weekly_credit_volume)       AS recent_mean,
        STDDEV(weekly_credit_volume)    AS recent_std,
        COUNT(*)                        AS n_recent_weeks
    FROM recent_weeks
    GROUP BY customer_id
),

-- Step 6: Compute burst features
burst_final AS (
    SELECT
        rs.customer_id,
        rs.recent_max,
        rs.recent_mean,
        bs.baseline_median,
        bs.baseline_mean,
        bm.mad                          AS baseline_mad,

        -- Burst ratio: how many times baseline median is recent peak
        SAFE_DIVIDE(
            rs.recent_max,
            NULLIF(bs.baseline_median, 0)
        )                               AS burst_ratio,

        -- Burst z-score using robust stats
        SAFE_DIVIDE(
            rs.recent_max - bs.baseline_median,
            1.4826 * NULLIF(bm.mad, 0)
        )                               AS burst_zscore,

        -- Persistence: std of recent weeks relative to mean
        -- Low persistence = spike and drop (more suspicious)
        -- High persistence = sustained change (less suspicious)
        SAFE_DIVIDE(
            rs.recent_std,
            NULLIF(rs.recent_mean, 0)
        )                               AS burst_persistence_cv,

        -- Number of recent weeks above 2x baseline
        (
            SELECT COUNT(*)
            FROM recent_weeks rw
            WHERE rw.customer_id = rs.customer_id
            AND rw.weekly_credit_volume > bs.baseline_median * 2
        )                               AS n_burst_weeks

    FROM recent_stats rs
    LEFT JOIN baseline_stats bs
        ON rs.customer_id = bs.customer_id
    LEFT JOIN baseline_mad_final bm
        ON rs.customer_id = bm.customer_id
)

SELECT * FROM burst_final
5. Structuring Signature
-- ============================================================
-- STRUCTURING SIGNATURE
-- Detects clustering of transactions just below
-- common reporting and monitoring thresholds
-- ============================================================

WITH

-- Step 1: Tag each transaction with sub-threshold band membership
-- for each threshold of interest
transaction_threshold_tags AS (
    SELECT
        customer_id,
        value,
        transaction_date,

        -- Is this transaction in the 5% band below each threshold?
        CASE WHEN value >= 950    AND value < 1000  THEN 1 ELSE 0 END
            AS sub

5. Structuring Signature
-- ============================================================
-- STRUCTURING SIGNATURE
-- Detects clustering of transactions just below
-- common reporting and monitoring thresholds
-- ============================================================

WITH

-- Step 1: Tag each transaction with sub-threshold band membership
-- for each threshold of interest
transaction_threshold_tags AS (
    SELECT
        customer_id,
        value,
        transaction_date,

        -- Is this transaction in the 5% band below each threshold?
        CASE WHEN value >= 950    AND value < 1000  THEN 1 ELSE 0 END
            AS sub_1000,
        CASE WHEN value >= 2850   AND value < 3000  THEN 1 ELSE 0 END
            AS sub_3000,
        CASE WHEN value >= 4750   AND value < 5000  THEN 1 ELSE 0 END
            AS sub_5000,
        CASE WHEN value >= 9500   AND value < 10000 THEN 1 ELSE 0 END
            AS sub_10000,
        CASE WHEN value >= 14250  AND value < 15000 THEN 1 ELSE 0 END
            AS sub_15000,
        CASE WHEN value >= 47500  AND value < 50000 THEN 1 ELSE 0 END
            AS sub_50000,

        -- Is this transaction above each threshold?
        CASE WHEN value >= 1000  THEN 1 ELSE 0 END AS above_1000,
        CASE WHEN value >= 3000  THEN 1 ELSE 0 END AS above_3000,
        CASE WHEN value >= 5000  THEN 1 ELSE 0 END AS above_5000,
        CASE WHEN value >= 10000 THEN 1 ELSE 0 END AS above_10000,
        CASE WHEN value >= 15000 THEN 1 ELSE 0 END AS above_15000,
        CASE WHEN value >= 50000 THEN 1 ELSE 0 END AS above_50000

    FROM `your_project.your_dataset.transactions`
    WHERE direction = 'credit'
),

-- Step 2: Aggregate per customer
customer_threshold_counts AS (
    SELECT
        customer_id,

        -- Sub-threshold counts
        SUM(sub_1000)                   AS n_sub_1000,
        SUM(sub_3000)                   AS n_sub_3000,
        SUM(sub_5000)                   AS n_sub_5000,
        SUM(sub_10000)                  AS n_sub_10000,
        SUM(sub_15000)                  AS n_sub_15000,
        SUM(sub_50000)                  AS n_sub_50000,

        -- Above threshold counts
        SUM(above_1000)                 AS n_above_1000,
        SUM(above_3000)                 AS n_above_3000,
        SUM(above_5000)                 AS n_above_5000,
        SUM(above_10000)                AS n_above_10000,
        SUM(above_15000)                AS n_above_15000,
        SUM(above_50000)                AS n_above_50000,

        COUNT(*)                        AS total_credit_txns

    FROM transaction_threshold_tags
    GROUP BY customer_id
),

-- Step 3: Compute structuring ratios per threshold
-- Ratio = sub-threshold / (sub-threshold + above threshold)
-- Under random distribution should be ~5%
-- Elevated ratio suggests deliberate sub-threshold placement
structuring_ratios AS (
    SELECT
        customer_id,
        total_credit_txns,

        SAFE_DIVIDE(n_sub_1000,
            n_sub_1000 + n_above_1000)  AS struct_ratio_1000,
        SAFE_DIVIDE(n_sub_3000,
            n_sub_3000 + n_above_3000)  AS struct_ratio_3000,
        SAFE_DIVIDE(n_sub_5000,
            n_sub_5000 + n_above_5000)  AS struct_ratio_5000,
        SAFE_DIVIDE(n_sub_10000,
            n_sub_10000 + n_above_10000) AS struct_ratio_10000,
        SAFE_DIVIDE(n_sub_15000,
            n_sub_15000 + n_above_15000) AS struct_ratio_15000,
        SAFE_DIVIDE(n_sub_50000,
            n_sub_50000 + n_above_50000) AS struct_ratio_50000,

        -- Raw sub-threshold counts for context
        n_sub_1000,
        n_sub_3000,
        n_sub_5000,
        n_sub_10000,
        n_sub_15000,
        n_sub_50000

    FROM customer_threshold_counts
),

-- Step 4: Composite structuring features
structuring_final AS (
    SELECT
        customer_id,

        -- Maximum ratio across all thresholds
        GREATEST(
            COALESCE(struct_ratio_1000,  0),
            COALESCE(struct_ratio_3000,  0),
            COALESCE(struct_ratio_5000,  0),
            COALESCE(struct_ratio_10000, 0),
            COALESCE(struct_ratio_15000, 0),
            COALESCE(struct_ratio_50000, 0)
        )                               AS structuring_max_ratio,

        -- Individual ratios for drilldown
        struct_ratio_1000,
        struct_ratio_3000,
        struct_ratio_5000,
        struct_ratio_10000,
        struct_ratio_15000,
        struct_ratio_50000,

        -- Number of thresholds showing elevated ratio (>15%)
        (
            CASE WHEN struct_ratio_1000  > 0.15 THEN 1 ELSE 0 END +
            CASE WHEN struct_ratio_3000  > 0.15 THEN 1 ELSE 0 END +
            CASE WHEN struct_ratio_5000  > 0.15 THEN 1 ELSE 0 END +
            CASE WHEN struct_ratio_10000 > 0.15 THEN 1 ELSE 0 END +
            CASE WHEN struct_ratio_15000 > 0.15 THEN 1 ELSE 0 END +
            CASE WHEN struct_ratio_50000 > 0.15 THEN 1 ELSE 0 END
        )                               AS structuring_n_thresholds_flagged,

        -- Total sub-threshold transaction count
        n_sub_1000 + n_sub_3000 + n_sub_5000 +
        n_sub_10000 + n_sub_15000 + n_sub_50000
                                        AS structuring_total_sub_threshold_n,

        total_credit_txns

    FROM structuring_ratios
)

SELECT * FROM structuring_final
6. Fan-Out / Fan-In Ratio
-- ============================================================
-- FAN-OUT / FAN-IN RATIO
-- Structural role in payment network
-- ============================================================

WITH

-- Step 1: Fan-out - distinct beneficiaries paid by customer
fan_out AS (
    SELECT
        customer_id,
        COUNT(DISTINCT beneficiary_id)  AS fan_out_count,
        SUM(value)                      AS total_debit_value
    FROM `your_project.your_dataset.transactions`
    WHERE direction = 'debit'
    GROUP BY customer_id
),

-- Step 2: Fan-in - distinct senders paying the customer
-- Using beneficiary_id on credit transactions as sender proxy
-- If you have a sender_id column use that instead
fan_in AS (
    SELECT
        customer_id,
        COUNT(DISTINCT beneficiary_id)  AS fan_in_count,
        SUM(value)                      AS total_credit_value
    FROM `your_project.your_dataset.transactions`
    WHERE direction = 'credit'
    GROUP BY customer_id
),

-- Step 3: Transaction type diversity
-- How many distinct transaction types does customer use
txn_type_diversity AS (
    SELECT
        customer_id,
        COUNT(DISTINCT transaction_type) AS n_distinct_txn_types
    FROM `your_project.your_dataset.transactions`
    GROUP BY customer_id
),

-- Step 4: Combine and derive ratio features
fan_final AS (
    SELECT
        COALESCE(fo.customer_id,
                 fi.customer_id)        AS customer_id,

        COALESCE(fo.fan_out_count, 0)   AS fan_out_count,
        COALESCE(fi.fan_in_count,  0)   AS fan_in_count,
        COALESCE(fo.total_debit_value,  0) AS total_debit_value,
        COALESCE(fi.total_credit_value, 0) AS total_credit_value,

        -- Fan ratio: high = more payers than payees (collection)
        --            low  = more payees than payers (disbursement)
        --            ~1   = balanced trading pattern
        SAFE_DIVIDE(
            COALESCE(fi.fan_in_count,  0) + 1,
            COALESCE(fo.fan_out_count, 0) + 1
        )                               AS fan_ratio,

        -- Hub score: high fan-in AND high fan-out
        -- Legitimate payment processor or layering hub
        LN(1 +
            COALESCE(fi.fan_in_count,  0) *
            COALESCE(fo.fan_out_count, 0)
        )                               AS fan_hub_score_log,

        -- Asymmetry: absolute difference
        -- High = specialised account role
        ABS(
            COALESCE(fi.fan_in_count,  0) -
            COALESCE(fo.fan_out_count, 0)
        )                               AS fan_asymmetry,

        -- Value ratio: are inflows and outflows balanced in value
        SAFE_DIVIDE(
            COALESCE(fi.total_credit_value, 0),
            NULLIF(COALESCE(fo.total_debit_value, 0), 0)
        )                               AS value_fan_ratio,

        -- Concentration: average value per unique counterparty
        SAFE_DIVIDE(
            COALESCE(fo.total_debit_value, 0),
            NULLIF(COALESCE(fo.fan_out_count, 0), 0)
        )                               AS avg_value_per_payee,

        SAFE_DIVIDE(
            COALESCE(fi.total_credit_value, 0),
            NULLIF(COALESCE(fi.fan_in_count, 0), 0)
        )                               AS avg_value_per_payer

    FROM fan_out fo
    FULL OUTER JOIN fan_in fi
        ON fo.customer_id = fi.customer_id
)

SELECT
    f.*,
    COALESCE(ttd.n_distinct_txn_types, 0) AS n_distinct_txn_types
FROM fan_final f
LEFT JOIN txn_type_diversity ttd
    ON f.customer_id = ttd.customer_id
Joining All Five Into One Feature Table
-- ============================================================
-- MASTER FEATURE JOIN
-- One row per customer with all five feature blocks
-- ============================================================

SELECT
    c.customer_id,

    -- Peer overlap
    po.peer_overlap_score,
    po.pct_value_to_unseen_benes,
    po.n_distinct_benes,

    -- Beneficiary uniqueness
    bu.bene_uniqueness_score,
    bu.bene_uniqueness_max,
    bu.pct_value_to_rare_benes,
    bu.n_rare_benes_used,
    bu.pct_value_to_ubiquitous_benes,
    bu.bene_hhi,

    -- Velocity layering
    vl.velocity_lag_1d,
    vl.velocity_lag_3d,
    vl.velocity_lag_7d,
    vl.velocity_lag_14d,
    vl.velocity_lag_30d,
    vl.velocity_steepness,
    vl.velocity_auc,
    vl.velocity_early_concentration,

    -- Burst detection
    bd.burst_ratio,
    bd.burst_zscore,
    bd.burst_persistence_cv,
    bd.n_burst_weeks,
    bd.baseline_median,

    -- Structuring
    st.structuring_max_ratio,
    st.structuring_n_thresholds_flagged,
    st.structuring_total_sub_threshold_n,
    st.struct_ratio_5000,
    st.struct_ratio_10000,

    -- Fan ratio
    fn.fan_out_count,
    fn.fan_in_count,
    fn.fan_ratio,
    fn.fan_hub_score_log,
    fn.fan_asymmetry,
    fn.value_fan_ratio,
    fn.avg_value_per_payee,
    fn.avg_value_per_payer,
    fn.n_distinct_txn_types

FROM `your_project.your_dataset.customers` c
LEFT JOIN peer_overlap_final     po ON c.customer_id = po.customer_id
LEFT JOIN bene_uniqueness_final  bu ON c.customer_id = bu.customer_id
LEFT JOIN velocity_final         vl ON c.customer_id = vl.customer_id
LEFT JOIN burst_final            bd ON c.customer_id = bd.customer_id
LEFT JOIN structuring_final      st ON c.customer_id = st.customer_id
LEFT JOIN fan_final              fn ON c.customer_id = fn.customer_id
A Note On Your Window Logic
Since you've already built 30d, 90d, 180d, 360d windows, wrap each of these queries in a WHERE transaction_date >= DATE_SUB(CURRENT_DATE(), INTERVAL N DAY) filter to get the windowed version. The structuring and burst queries need the full history — don't window those. Burst specifically needs the baseline period to be outside the scoring window, so feed it the full 2-year transaction history and let the internal week-rank logic handle the baseline/recent split.