You've spotted a real flaw. Here's the problem precisely.

## What's Happening

A hairdresser receives £3,000 in small daily card credits throughout the month. On day 28 they pay a single £36,000 rent and rates bill that covers their annual lease. The debit is 12x larger than any single credit day.

Your velocity calculation is credit-weighted. The denominator is total credits. The numerator is debits following each credit, weighted by that credit's share of total credits. When the single large debit is counted against multiple small credit days, the sum of weighted debits can easily exceed total credits — which you cap at 1.0.

So the customer reads as velocity = 1.0 (maximum pass-through) when actually they're a perfectly normal business that accumulated income slowly and paid a large bill once. The opposite of suspicious.

This is a **scale mismatch problem**. Velocity assumes credits and debits are roughly comparable in size. When one side has a completely different size distribution from the other, the metric breaks.

---

## The Root Cause

Your current numerator accumulates:

```
credit_weight × debits_in_lag_window
```

If debits in the lag window are much larger than the credit that day, that credit day contributes a weighted debit value larger than its own weight. Summed across all credit days touching that large debit event, you get a numerator larger than 1.0, which gets capped.

The cap at 1.0 hides the problem rather than fixing it.

---

## The Solutions

**Option 1 — Cap the per-credit-day contribution**

Don't let any single credit day's weighted debit contribution exceed its own weight. A credit day contributing 5% of total credits can contribute at most 5% to the velocity numerator, regardless of how large the debits were in the following days.

```sql
-- Instead of:
daily_credits * SAFE_DIVIDE(debits_next_1d, daily_credits)

-- Use:
LEAST(
    daily_credits * SAFE_DIVIDE(debits_next_1d, daily_credits),
    daily_credits  -- cap contribution at credit value itself
)
```

This means the velocity score represents "what proportion of credit value had equivalent debit coverage within N days" rather than "how much debit happened after each credit." A credit day of £3,000 can contribute at most £3,000 to the numerator regardless of whether £50,000 was debited the next day.

The problem with this is it makes velocity insensitive to large debit events — which might actually be the signal you want for other typologies. A business that receives many small credits and immediately makes one large debit to an unusual beneficiary is a real pattern.

**Option 2 — Compute velocity on debit side as well**

Rather than measuring "how quickly are credits followed by debits," also measure "how quickly are debits preceded by credits." Average or take the minimum of the two directions. This symmetric approach catches pass-through regardless of which side has the larger transactions.

The debit-side velocity asks: for each debit, how recently did a credit arrive? A large debit preceded by credits within 1 day is fast velocity from the debit perspective.

**Option 3 — Separate large and small transactions**

Split transactions into two tiers before computing velocity. Below a threshold (say the 80th percentile of transaction values for that customer), compute velocity on the small transactions. Above the threshold, compute separately. This prevents one large debit contaminating the velocity signal for the regular flow pattern.

```sql
-- Two velocity measures per customer
-- Regular flow velocity: excludes outlier transactions
-- Large transaction velocity: only the large transactions

-- Regular: transactions below customer's 80th percentile
-- Large: transactions above customer's 80th percentile
```

**Option 4 — Use net daily flow velocity instead**

Rather than tracking credits and measuring how quickly debits follow, compute net daily position (credits minus debits) and measure how quickly the account returns to near-zero after a positive net position. This naturally handles the scale mismatch because you're measuring account balance dynamics rather than individual transaction pairing.

```sql
net_position AS (
    SELECT
        customer_id,
        flow_date,
        daily_credits - daily_debits AS net_flow,
        SUM(daily_credits - daily_debits) OVER (
            PARTITION BY customer_id
            ORDER BY flow_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )                             AS running_balance
    FROM daily_flows
)
```

A pass-through account has a running balance that spikes briefly and returns to near-zero quickly. A normal business has a running balance that grows gradually and depletes in periodic larger steps. The shape of the running balance over time is your velocity signal.

---

## The Recommended Fix For Your Case

The cleanest solution that handles the hairdresser problem without losing the layering signal is a combination of Option 1 and a new complementary feature.

**Fix velocity** using the per-credit-day cap. This makes the velocity score represent genuine pass-through proportion rather than raw debit volume relative to credits.

**Add a separate large debit feature** that captures what you'd lose by capping. Specifically:

```sql
-- Ratio of largest single debit to total credits in window
-- High for the hairdresser (large annual bill)
-- but combined with LOW velocity = not suspicious
-- High AND combined with HIGH velocity = suspicious

SAFE_DIVIDE(
    MAX(daily_debits),
    NULLIF(SUM(daily_credits), 0)
) AS max_debit_to_total_credit_ratio,

-- Number of debits exceeding total credits for that day
-- i.e. debits that are clearly not funded by same-day credits
COUNT(CASE
    WHEN daily_debits > daily_credits
    THEN 1
END) AS n_days_debit_exceeds_credit
```

This way the model sees both dimensions separately. The hairdresser has low velocity (credits accumulate before debits) but high max_debit_to_credit_ratio (one big payment relative to daily income). The layering account has high velocity AND a high ratio — both features elevated simultaneously is your combined signal.

The isolation forest within peer groups will learn that hairdressers typically have low velocity and occasionally high debit ratios (annual bills are normal). A hairdresser with both high velocity and an unusual debit pattern is anomalous within that peer group. The two features together are more informative than either alone.

---

## The Corrected SQL

```sql
forward_debits_capped AS (
    SELECT
        customer_id,
        flow_date,
        daily_credits,
        daily_debits,

        -- Cap forward debit sums at daily_credits value
        -- Prevents large debits inflating velocity beyond 1
        -- for customers with irregular large outgoings

        LEAST(
            SUM(daily_debits) OVER (
                PARTITION BY customer_id
                ORDER BY flow_date
                ROWS BETWEEN CURRENT ROW AND 1 FOLLOWING
            ),
            daily_credits
        )                                   AS debits_next_1d_capped,

        LEAST(
            SUM(daily_debits) OVER (
                PARTITION BY customer_id
                ORDER BY flow_date
                ROWS BETWEEN CURRENT ROW AND 3 FOLLOWING
            ),
            daily_credits
        )                                   AS debits_next_3d_capped,

        LEAST(
            SUM(daily_debits) OVER (
                PARTITION BY customer_id
                ORDER BY flow_date
                ROWS BETWEEN CURRENT ROW AND 7 FOLLOWING
            ),
            daily_credits
        )                                   AS debits_next_7d_capped,

        LEAST(
            SUM(daily_debits) OVER (
                PARTITION BY customer_id
                ORDER BY flow_date
                ROWS BETWEEN CURRENT ROW AND 14 FOLLOWING
            ),
            daily_credits
        )                                   AS debits_next_14d_capped,

        LEAST(
            SUM(daily_debits) OVER (
                PARTITION BY customer_id
                ORDER BY flow_date
                ROWS BETWEEN CURRENT ROW AND 30 FOLLOWING
            ),
            daily_credits
        )                                   AS debits_next_30d_capped,

        -- Uncapped versions retained for the large debit feature
        SUM(daily_debits) OVER (
            PARTITION BY customer_id
            ORDER BY flow_date
            ROWS BETWEEN CURRENT ROW AND 1 FOLLOWING
        )                                   AS debits_next_1d_raw

    FROM daily_flows
),

-- Large debit supplementary features
-- Computed separately, not part of velocity score
large_debit_features AS (
    SELECT
        customer_id,

        -- Largest single debit day relative to total credits
        -- High = customer makes large irregular payments
        SAFE_DIVIDE(
            MAX(daily_debits),
            NULLIF(SUM(daily_credits), 0)
        )                                   AS max_debit_to_credit_ratio,

        -- Days where debit exceeded that day's credit
        -- Normal for bill-paying businesses
        -- Combined with high velocity = suspicious
        COUNTIF(daily_debits > daily_credits)
                                            AS n_days_debit_exceeds_credit,

        -- Coefficient of variation of daily debits
        -- Low = consistent regular outgoings (normal)
        -- High = erratic debit pattern
        SAFE_DIVIDE(
            STDDEV(daily_debits),
            NULLIF(AVG(daily_debits), 0)
        )                                   AS debit_cv,

        -- Same for credits
        SAFE_DIVIDE(
            STDDEV(daily_credits),
            NULLIF(AVG(daily_credits), 0)
        )                                   AS credit_cv

    FROM daily_flows
    WHERE flow_date >= DATE_SUB(DATE '2024-03-31', INTERVAL 360 DAY)
    GROUP BY customer_id
)
```

Then in `window_aggregates`, replace `debits_next_Nd` with `debits_next_Nd_capped` throughout. The velocity calculation now correctly represents pass-through proportion. The large debit features sit alongside velocity in your feature table as separate inputs to the model.

The model then distinguishes: high velocity alone, large debits alone (normal for bill-paying), or high velocity combined with large debits (the suspicious combination). Three distinct patterns, three distinct anomaly profiles, none of them confused with the others.