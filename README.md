Feature engineering is where this model lives or dies. Let me go through every feature category in depth, including how to construct it, what it signals, and where the gotchas are.

---

## 1. Transaction Behaviour Features

These are derived from your transactional data aggregated at customer level, typically over rolling windows (30-day, 90-day, 12-month). Always build features at multiple time horizons and let the model see both.

### Volume and Value Distributions

**Monthly transaction count and value** — straightforward but foundational. Compute mean, median, standard deviation, and coefficient of variation (CV = std/mean) for both count and value separately. CV is more useful than raw std because it's scale-invariant — a company turning over £10m and one turning over £100k can both have high or low CV meaningfully.

**Value percentile distribution** — don't just use mean and std. Compute the 10th, 25th, 75th, 90th, and 99th percentile of transaction values. A business with a very fat tail (p99 is 50x the median) behaves differently from one with consistent transaction sizes, even at the same average. This catches businesses that occasionally process anomalously large transactions against a backdrop of normal activity.

**Transaction size consistency** — compute the ratio of transactions above 2x the customer's own historical median. A sudden increase in this ratio signals a step-change in behaviour. This is your within-customer temporal signal, not a peer comparison.

**Round number propensity** — the proportion of transactions with values ending in 000 or 0000. Structuring and layering often produces round number transactions. Compute at different thresholds (transactions over £5k, over £10k, over £50k) because the signal is stronger at higher values.

**Transaction count to value ratio** — high transaction count with low total value vs. low count with high value. A construction company processing 400 transactions of £50 each is anomalous. This catches businesses whose operational pattern doesn't match their SIC.

### Credit/Debit Asymmetry

**Credit-debit ratio** — total credits divided by total debits over the period. Most legitimate businesses have a ratio close to 1 over time (money in roughly equals money out). A ratio persistently above 1.2 or below 0.8 warrants explanation. Holding companies and investment vehicles will have naturally different ratios so this needs peer-group context.

**Velocity of credits vs. debits** — how quickly does money leave after it arrives? Compute the median time lag between a credit and the subsequent debit of equivalent value. Fast pass-through (same day or next day) is a layering signal. This requires you to do some approximate matching of inflows to outflows, which is non-trivial but worth it.

**Net position volatility** — standard deviation of the account's end-of-day balance divided by average balance. A business that repeatedly goes near-zero before receiving more funds behaves differently from one with a stable working capital buffer.

### Transaction Type Features

**Transaction type distribution** — you have transaction type in your data. Compute the proportion of each type (CHAPS, BACS, Faster Payments, card, etc.) as a share of total count and total value. Encode both because a business might use CHAPS rarely but for large values. The distribution itself is a fingerprint — a cash-intensive business that has no card transactions but high CHAPS volume is anomalous for its SIC.

**Cash proxies** — depending on what your transaction types include, flag cash-equivalent behaviours: high use of payment types that are harder to trace, frequent just-below-threshold transactions (structuring), or patterns consistent with smurfing across multiple accounts if you can see that.

**Transaction type entropy** — Shannon entropy of the transaction type distribution. A business using only one transaction type has zero entropy. High entropy means diverse payment behaviour. For most SMEs, moderate entropy is normal; very low entropy (monoculture) is sometimes suspicious.

---

## 2. Counterparty Features

Your beneficiary IDs are messy because card payment aggregators pollute them, but they're still highly valuable once cleaned.

### Counterparty Diversity

**Unique beneficiary count** — raw count of distinct beneficiary IDs over the window. Normalise by transaction count to get beneficiaries per transaction. A business making 500 transactions to 3 beneficiaries is structurally different from one making 500 transactions to 400 beneficiaries.

**Herfindahl-Hirschman Index (HHI) of beneficiary concentration** — this is the sum of squared proportions of payment value going to each beneficiary. A single-beneficiary business has HHI of 1.0. A perfectly distributed business approaches 0. This is better than raw count because it's value-weighted — you care more about where the money goes than how many times it goes there. Compute separately for credits (who sends money to this business) and debits (who this business pays).

**Top-N beneficiary concentration** — what percentage of total outflow goes to the top 1, top 3, and top 5 beneficiaries? This is more interpretable than HHI for analysts and still very signal-rich.

**New beneficiary rate** — for each month, what proportion of beneficiaries used that month have never appeared before in the customer's history? A sudden spike in new beneficiaries is a behavioural change signal.

**Beneficiary overlap with exited customers** — do any of this customer's beneficiaries also appear in the payment history of customers exited for FC reasons? This is a network contamination feature and one of your most powerful. It requires you to have cleaned and preserved the exited customer transaction history.

### Beneficiary Classification

Raw beneficiary IDs need enrichment. At minimum, classify each beneficiary into: card payment aggregator (Stripe, Square, Worldpay etc.), known financial institution, government/HMRC, other business in your own book, unknown. Strip aggregators out of your diversity metrics because they inflate counterparty count artificially for legitimate retail-facing businesses. Build a separate feature for the proportion of payments going to aggregators vs. real named counterparties.

---

## 3. International Payment Features

This is one of your richest data sources for financial crime because it's where layering and sanctions evasion manifests.

### Country-Level Features

**Number of distinct countries** — over 30, 90, and 365-day windows. Most SMEs have very few international payment destinations. More than 5–10 for a small business is already unusual for many SIC codes.

**Country risk score** — map each destination country to a risk score using your bank's internal country risk taxonomy (or FATF grey/black lists, Basel AML Index, Transparency International CPI as proxies). Compute the value-weighted average country risk score for all international payments. Also compute the maximum country risk score encountered — a business that sends one payment to a very high-risk jurisdiction is flagged even if its average is low.

**High-risk country concentration** — percentage of international payment value going to countries above a defined risk threshold. Separate features for volume (number of transactions) and value (total £) because a business that makes many small payments to a high-risk country behaves differently from one making one large payment.

**Country distribution entropy** — Shannon entropy of the country distribution by value. Low entropy means concentration in one or two countries. High entropy across many risky countries is a different concern from low entropy in one risky country. Both are signals, just different ones.

**Jurisdiction mismatch** — compare the countries of international payments against the registered SIC code's expected international payment profile. A construction company sending payments to offshore financial centres has a higher mismatch score than an import/export company doing the same. This requires you to build an expected-country-profile per SIC group, which you can derive from the behaviour of the bulk of your low-risk customers in each SIC.

**Inbound vs. outbound international asymmetry** — do they receive from different countries than they send to? Receiving from Country A and immediately sending to Country C with no plausible trade relationship is a layering indicator.

**New country rate** — the equivalent of new beneficiary rate but for countries. A business that has paid domestically for two years and suddenly starts sending to three new jurisdictions in one month has a high new country rate.

### Structural Features

**International as proportion of total payments** — what percentage of total outflow value is international? Context-dependent heavily by SIC, but the outlier detection within peer groups handles this.

**Average international transaction size vs. domestic** — if international transactions are much larger than domestic ones on average, this is a structural signal worth capturing separately from the averages.

---

## 4. Temporal and Behavioural Change Features

These are your me-to-peer-over-time features and they're critical for catching customers who were clean and then changed, or who built up slowly.

### Within-Customer Trend Features

**Rolling slope of transaction value** — fit a linear trend to monthly total transaction value over 12 months. A positive slope means growing business (often fine), but a rapidly accelerating slope (exponential growth) is anomalous for many SME types. Compute slope normalised by starting value so it's comparable across customers of different sizes.

**Month-on-month change features** — for your key metrics (transaction count, value, unique beneficiaries, international volume), compute the percentage change from the prior period and the z-score of that change relative to the customer's own history. A z-score above 3 on any metric in a given month flags a structural break.

**Behavioural consistency score** — compute the average pairwise correlation of monthly feature vectors across the customer's history. A customer whose monthly behaviour is highly consistent scores near 1. A customer whose behaviour varies wildly scores near 0. Sudden drops in this score (i.e., the recent months look nothing like the historical months) are a change-in-behaviour signal.

**Dormancy followed by activity** — flag customers who had low or zero activity for 3+ months and then resumed. This is a common account takeover and front company activation pattern. Features: months of dormancy in last 24 months, value in first active month following dormancy.

**Seasonality deviation** — for customers with enough history (12+ months), fit a seasonal decomposition and compute the residual. Large residuals in recent months indicate the customer is deviating from their own seasonal pattern.

### Peer Comparison Over Time

**Percentile rank within peer group, rolling** — compute each customer's percentile rank on key features (transaction value, international volume, beneficiary concentration) within their peer group each month. The feature is not the raw percentile but the trend of that percentile. A customer who was at the 50th percentile 12 months ago and is now at the 95th percentile has moved significantly within their peer group even if their absolute values don't look extreme.

---

## 5. Device ID Features

This data is underused in most financial crime models and it's very high signal.

**Number of distinct devices** — count of unique device IDs associated with a customer's logins/transactions over the window. Most legitimate SMEs use 1–3 devices (owner's phone, laptop, maybe a second employee). High device counts are anomalous.

**Device introduction rate** — how often does a new device appear? A business that introduces a new device every week is behaviorally anomalous.

**Device sharing across customers** — this is the network feature. Count how many other customers in your book share at least one device ID with this customer. Shared devices across nominally unrelated businesses is a very strong signal of connected entities, mule networks, or a single operator running multiple accounts. This feature requires a cross-customer join and can be computationally expensive but is worth it.

**Device geographic consistency** — if you have device location data, compute whether the device locations are consistent with the registered business address. A business registered in Leeds whose devices all geolocate to London or abroad has an address-device mismatch.

**Session behaviour anomalies** — if you have session-level data (login times, session durations, actions per session), compute features like typical login time distribution, average session length, and flag deviations. Automated or scripted account activity often has distinctive session signatures.

---

## 6. Customer Attribute Derived Features

These come from your customer data and are partly used for peer group definition and partly as features in their own right.

**Director count to turnover ratio** — a company with 8 directors and £200k turnover has a high director density relative to size. This is anomalous for most SIC codes and is sometimes associated with nominee director arrangements.

**Address coherence features** — three binary or categorical features: whether registered address, business address, and correspondence address are in the same region; whether any of the three addresses are in a high-risk postcode (your bank should have a postcode risk list); and whether any address is a known formation agent or virtual office address. The last one requires a lookup table but is extremely high signal.

**Nationality diversity of directors** — number of distinct director nationalities. This is not a risk feature on its own (and must not be treated as one — see governance note below) but combined with other features like international payment destinations, it can be part of a composite. Be very careful here: the feature should be "director nationalities match international payment destinations" (a coherence check with a plausible business rationale) rather than "directors are of nationality X."

**SIC code risk tier** — your bank should have a SIC-level inherent risk rating. Include this as a feature but be aware it's a prior, not a signal. It tells you what to expect, not what's happening.

**Customer age** — days since onboarding. Very new customers with high activity are structurally different from established customers with the same activity level. Also, customers who are several years old but have thin transaction history (low engagement) relative to their declared turnover are anomalous.

**Turnover declared vs. transactional turnover** — compare the declared annual turnover from onboarding data against the actual transaction volume processed through the account. A company declaring £5m turnover but processing £50m is anomalous. So is one declaring £5m and processing £50k — both represent mismatches with the expected relationship between declared and observed.

---

## 7. Network and Linkage Features

These require cross-customer analysis and are more expensive to compute but among the most powerful.

**Shared director linkage count** — how many other active customers share at least one director with this customer? A network of 10 companies sharing a director pool, especially in the same SIC, is a control structure worth examining.

**Address linkage count** — how many other customers share the same registered address? Hundreds of companies at the same address is a formation agent flag. Compute separately for registered, business, and correspondence.

**Second-degree beneficiary overlap** — not just whether this customer pays the same beneficiaries as exited customers, but whether this customer pays businesses that themselves pay the same beneficiaries as exited customers. This is expensive but powerful for detecting networks that have learned to avoid direct connections to flagged entities.

**Community detection score** — if you build a graph of customers connected by shared directors, addresses, device IDs, and beneficiaries, you can run a community detection algorithm (Louvain, label propagation) and compute the size and risk score of the community this customer belongs to. Customers in large, densely connected communities that include any exited-for-FC members should have elevated scores.

---

## 8. Exited Customer Similarity Features

Since you have an FC-exited population, treat it as a reference distribution.

**Feature-space distance to exited customer centroid** — compute the mean feature vector of your exited-for-FC customers by SIC group. Compute the Mahalanobis distance (not Euclidean — you need to account for feature correlations) from each active customer to that centroid. This is a single continuous similarity score.

**Nearest-neighbour distance to exited customers** — for each active customer, find the k nearest exited customers in feature space and compute the average distance. Customers very close to exited customers in behaviour space are high-priority regardless of their absolute anomaly score.

**Exited customer feature match count** — rather than a continuous distance, a more interpretable feature is: across your top 20 most discriminating features between exited and non-exited customers, how many does this active customer match (within a defined threshold)? This gives you a discrete count from 0 to 20 that analysts find intuitive: "this customer matches 14 of 20 behavioural characteristics of customers previously exited for financial crime."

---

## Feature Engineering Governance Notes

A few critical points before you build any of this. Nationality must not be a direct model input. Address and director nationality data can be used only for coherence checks (does the business activity match the international footprint) and must be documented as such. Run a feature importance audit to confirm nationality-derived features are not the dominant drivers of anomaly scores.

Missing data strategy must be documented. Many customers will have null values for international payments (they don't send any), device ID (no digital banking), or turnover (not updated since onboarding). Nulls are often themselves informative — a business with no declared turnover update in 3 years is different from one with a current figure. Create explicit missingness indicator features rather than imputing silently.

Feature stability testing — before production, compute the population stability index (PSI) of each feature monthly. Features with high PSI are changing in distribution and may indicate data quality issues or genuine population shifts. Unstable features make model scores unstable and are a model risk concern.

Correlation pruning — many of these features will be correlated (transaction count and value often move together). Run a correlation analysis and for highly correlated pairs (above 0.85), prefer the more interpretable one or create a single composite. This reduces multicollinearity effects in tree-based models and makes SHAP decompositions more stable.

You should aim for somewhere between 60 and 100 final features after pruning, computed across multiple time windows. The richness comes from the combination of cross-sectional peer comparison, within-customer temporal features, and network linkage — none of these three alone is sufficient.