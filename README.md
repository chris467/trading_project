Challenging Your Approach
On clustering first, then adding customer data: Don't do this in two stages. If you cluster on transactions alone, you'll discover transaction-behaviour groups that may already be perfectly explainable by segment or SIC code. You want anomaly to mean "unexpected given who they are" — so the customer metadata needs to be part of how you define peer groups, not added after. The right framing is: peer group definition comes from customer attributes, anomaly detection happens within those peer groups.
On unsupervised being the whole answer: Pure unsupervised models (isolation forests, autoencoders, DBSCAN) will find outliers, but "outlier" and "suspicious" are not the same thing. A company with a single massive annual transaction is an outlier. So is a company that runs payroll like clockwork. You need a hybrid: unsupervised to surface candidates, rule-based or semi-supervised scoring to triage them, and ideally a feedback loop from analyst decisions over time. If your exited customers list is labelled, that's actually a weak supervised signal — use it.
On exited customer comparison: This is your strongest idea and underused in most banks. Your exited-for-FC population is effectively a labelled anomaly set. You can use their behavioural fingerprints as a reference distribution and score active customers on similarity. This is closer to one-class classification than clustering, and it gives you explainability because you can say "this customer's international payment pattern matches 7 of 8 characteristics seen in exited customers in SIC 4511."
On the "why": This is where most anomaly detection projects fail governance. A score means nothing to a financial crime analyst without a decomposed explanation. You need SHAP values or equivalent feature contribution at the individual customer level, not just global feature importance. This is also what satisfies SR 11-7 / your model risk framework — the model must be explainable and its outputs must be interpretable by a non-data-scientist.

Recommended Architecture
Layer 1 — Peer Group Construction
Define peer groups using a combination of: SIC code (at 2-digit level, not 4 — too sparse otherwise), legal structure / number of directors, turnover band, customer segment, and registered address region. This gives you meaningful "who they should behave like" groups rather than letting an algorithm define them in a black box way, which is both riskier for governance and harder to explain to a financial crime analyst.
For thematic review use cases like "car washes" or "Italian-owned construction companies," these peer groups become parameterisable — you filter the peer group definition and re-run. The model doesn't change; only the population does.
Layer 2 — Feature Engineering (this is where the real work is)
Don't feed raw transactions into anything. You need to derive behavioural features at the customer-month or customer-quarter level. The most meaningful ones in your context are:
Transaction velocity and value distribution — mean, coefficient of variation, skewness of transaction values. A company with highly variable transaction sizes is different from one with consistent ones, even at the same average.
Counterparty concentration — how many unique beneficiary IDs does a customer use, and what's the HHI (Herfindahl index) of those payments? High concentration to few beneficiaries can be normal (a franchise paying one supplier) or suspicious. Combine this with whether those beneficiaries are card payment aggregators vs. named entities.
International payment profile — for each customer, build a countries-used vector, a volume/value ratio per country, and flag countries against your internal risk taxonomy. A construction company sending 80% of international payments to a single high-risk jurisdiction with no plausible business rationale is a strong signal.
Temporal patterns — day-of-week and time-of-day distributions of transactions. Some fraud typologies have strong temporal signatures. Also look at whether transaction behaviour is consistent month-on-month (low CV) or erratic.
Device ID features — number of distinct devices, rate of device introduction, shared device IDs across customers (a powerful network signal, especially for mule networks or connected businesses). This one is often neglected but extremely high signal.
Address coherence — mismatches between registered address region, business address region, and correspondence address region. A business registered in one region but with all its transactions going internationally and correspondence to a third country is anomalous for most SIC codes.
Me-to-me flows — you identified this correctly. Build a feature for the proportion of a customer's outflows that return to accounts linked to the same directors, addresses, or device IDs. This requires entity resolution across your customer base.
Layer 3 — Anomaly Scoring
Run two parallel approaches and ensemble them:
Isolation Forest within each peer group on the engineered features. This gives you a peer-relative anomaly score. The advantage is it's fast, handles mixed feature types well, and degrades gracefully with small peer groups.
Autoencoder trained on the full population for reconstruction error. Customers whose behaviour the model struggles to reconstruct are anomalous at a population level. This catches customers who don't even resemble any known type.
Exited customer similarity using your FC-exited population. Train a one-class SVM or use nearest-neighbour distance in feature space to score active customers on how similar they are to exited customers. Flag the percentile rank, not a binary.
Combine these three scores into a composite using a weighted rank aggregation rather than a simple average — this avoids any single model dominating when it has a bad day.
Layer 4 — Explainability and Output
For every customer surfaced, generate a SHAP decomposition of which features drove their anomaly score. Then translate those SHAP values into plain English narratives using a templating system — something like: "This business is anomalous within its peer group (SIC 43xx, 2 directors, turnover £500k–£2m) primarily due to unusually high international payment volume to high-risk jurisdictions (top 3% of peer group) and low counterparty diversity (HHI 0.87 vs peer median 0.31)."
This is not optional — it's what makes the tool usable by analysts and defensible to model risk and the regulator.
Layer 5 — Dashboard Design
Structure the dashboard in three views. A population view showing the full scored universe with filtering by segment, SIC, peer group, score band, and individual score drivers — this replaces thematic review targeting. A customer drilldown view with the score decomposition, time-series of key features, peer group benchmarking charts, and a network view of connected entities via device ID and address. An alert management view where analysts can accept, escalate, or dismiss cases with a mandatory rationale field — these decisions feed back into model performance monitoring.

AI Governance Considerations
This matters from day one, not after you build. You need to document: the model's intended use and limitations, peer group definition methodology and its sensitivity to SIC miscoding (which is common), performance metrics including false positive rate by segment to test for demographic disparity, and the human-in-the-loop requirement — no SAR should be filed or customer exited based on model output alone without analyst review.
Bias testing is non-negotiable. Nationality is in your dataset. It must not be a direct model input. But your peer group definition, if it includes "nationality of directors," could act as a proxy and you need to demonstrate the model doesn't produce systematically higher scores for businesses with directors of particular nationalities beyond what the transaction behaviour genuinely warrants. Run disparate impact analysis before production.
Model risk will want a champion-challenger framework once you're live — keep a rule-based baseline as champion so you can demonstrate the ML model adds lift.

The One Thing Most Teams Get Wrong
They optimise for finding anomalies and forget to optimise for analyst workflow. If your model generates 200 alerts a week and analysts can only review 40, you haven't eliminated thematic reviews — you've just added noise. Build in a calibration mechanism so you can tune the alert volume to analyst capacity, and track what percentage of model-surfaced cases result in meaningful outcomes. That outcome data becomes your most valuable asset for semi-supervised refinement over time.Go in detail what the features should beFeb 19Feature engineering is where this model lives or dies. Let me go through every feature category in depth, including how to construct it, what it signals, and where the gotchas are.

1. Transaction Behaviour Features
These are derived from your transactional data aggregated at customer level, typically over rolling windows (30-day, 90-day, 12-month). Always build features at multiple time horizons and let the model see both.
Volume and Value Distributions
Monthly transaction count and value — straightforward but foundational. Compute mean, median, standard deviation, and coefficient of variation (CV = std/mean) for both count and value separately. CV is more useful than raw std because it's scale-invariant — a company turning over £10m and one turning over £100k can both have high or low CV meaningfully.
Value percentile distribution — don't just use mean and std. Compute the 10th, 25th, 75th, 90th, and 99th percentile of transaction values. A business with a very fat tail (p99 is 50x the median) behaves differently from one with consistent transaction sizes, even at the same average. This catches businesses that occasionally process anomalously large transactions against a backdrop of normal activity.
Transaction size consistency — compute the ratio of transactions above 2x the customer's own historical median. A sudden increase in this ratio signals a step-change in behaviour. This is your within-customer temporal signal, not a peer comparison.
Round number propensity — the proportion of transactions with values ending in 000 or 0000. Structuring and layering often produces round number transactions. Compute at different thresholds (transactions over £5k, over £10k, over £50k) because the signal is stronger at higher values.
Transaction count to value ratio — high transaction count with low total value vs. low count with high value. A construction company processing 400 transactions of £50 each is anomalous. This catches businesses whose operational pattern doesn't match their SIC.
Credit/Debit Asymmetry
Credit-debit ratio — total credits divided by total debits over the period. Most legitimate businesses have a ratio close to 1 over time (money in roughly equals money out). A ratio persistently above 1.2 or below 0.8 warrants explanation. Holding companies and investment vehicles will have naturally different ratios so this needs peer-group context.
Velocity of credits vs. debits — how quickly does money leave after it arrives? Compute the median time lag between a credit and the subsequent debit of equivalent value. Fast pass-through (same day or next day) is a layering signal. This requires you to do some approximate matching of inflows to outflows, which is non-trivial but worth it.
Net position volatility — standard deviation of the account's end-of-day balance divided by average balance. A business that repeatedly goes near-zero before receiving more funds behaves differently from one with a stable working capital buffer.
Transaction Type Features
Transaction type distribution — you have transaction type in your data. Compute the proportion of each type (CHAPS, BACS, Faster Payments, card, etc.) as a share of total count and total value. Encode both because a business might use CHAPS rarely but for large values. The distribution itself is a fingerprint — a cash-intensive business that has no card transactions but high CHAPS volume is anomalous for its SIC.
Cash proxies — depending on what your transaction types include, flag cash-equivalent behaviours: high use of payment types that are harder to trace, frequent just-below-threshold transactions (structuring), or patterns consistent with smurfing across multiple accounts if you can see that.
Transaction type entropy — Shannon entropy of the transaction type distribution. A business using only one transaction type has zero entropy. High entropy means diverse payment behaviour. For most SMEs, moderate entropy is normal; very low entropy (monoculture) is sometimes suspicious.

2. Counterparty Features
Your beneficiary IDs are messy because card payment aggregators pollute them, but they're still highly valuable once cleaned.
Counterparty Diversity
Unique beneficiary count — raw count of distinct beneficiary IDs over the window. Normalise by transaction count to get beneficiaries per transaction. A business making 500 transactions to 3 beneficiaries is structurally different from one making 500 transactions to 400 beneficiaries.
Herfindahl-Hirschman Index (HHI) of beneficiary concentration — this is the sum of squared proportions of payment value going to each beneficiary. A single-beneficiary business has HHI of 1.0. A perfectly distributed business approaches 0. This is better than raw count because it's value-weighted — you care more about where the money goes than how many times it goes there. Compute separately for credits (who sends money to this business) and debits (who this business pays).
Top-N beneficiary concentration — what percentage of total outflow goes to the top 1, top 3, and top 5 beneficiaries? This is more interpretable than HHI for analysts and still very signal-rich.
New beneficiary rate — for each month, what proportion of beneficiaries used that month have never appeared before in the customer's history? A sudden spike in new beneficiaries is a behavioural change signal.
Beneficiary overlap with exited customers — do any of this customer's beneficiaries also appear in the payment history of customers exited for FC reasons? This is a network contamination feature and one of your most powerful. It requires you to have cleaned and preserved the exited customer transaction history.
Beneficiary Classification
Raw beneficiary IDs need enrichment. At minimum, classify each beneficiary into: card payment aggregator (Stripe, Square, Worldpay etc.), known financial institution, government/HMRC, other business in your own book, unknown. Strip aggregators out of your diversity metrics because they inflate counterparty count artificially for legitimate retail-facing businesses. Build a separate feature for the proportion of payments going to aggregators vs. real named counterparties.

3. International Payment Features
This is one of your richest data sources for financial crime because it's where layering and sanctions evasion manifests.
Country-Level Features
Number of distinct countries — over 30, 90, and 365-day windows. Most SMEs have very few international payment destinations. More than 5–10 for a small business is already unusual for many SIC codes.
Country risk score — map each destination country to a risk score using your bank's internal country risk taxonomy (or FATF grey/black lists, Basel AML Index, Transparency International CPI as proxies). Compute the value-weighted average country risk score for all international payments. Also compute the maximum country risk score encountered — a business that sends one payment to a very high-risk jurisdiction is flagged even if its average is low.
High-risk country concentration — percentage of international payment value going to countries above a defined risk threshold. Separate features for volume (number of transactions) and value (total £) because a business that makes many small payments to a high-risk country behaves differently from one making one large payment.
Country distribution entropy — Shannon entropy of the country distribution by value. Low entropy means concentration in one or two countries. High entropy across many risky countries is a different concern from low entropy in one risky country. Both are signals, just different ones.
Jurisdiction mismatch — compare the countries of international payments against the registered SIC code's expected international payment profile. A construction company sending payments to offshore financial centres has a higher mismatch score than an import/export company doing the same. This requires you to build an expected-country-profile per SIC group, which you can derive from the behaviour of the bulk of your low-risk customers in each SIC.
Inbound vs. outbound international asymmetry — do they receive from different countries than they send to? Receiving from Country A and immediately sending to Country C with no plausible trade relationship is a layering indicator.
New country rate — the equivalent of new beneficiary rate but for countries. A business that has paid domestically for two years and suddenly starts sending to three new jurisdictions in one month has a high new country rate.
Structural Features
International as proportion of total payments — what percentage of total outflow value is international? Context-dependent heavily by SIC, but the outlier detection within peer groups handles this.
Average international transaction size vs. domestic — if international transactions are much larger than domestic ones on average, this is a structural signal worth capturing separately from the averages.

4. Temporal and Behavioural Change Features
These are your me-to-peer-over-time features and they're critical for catching customers who were clean and then changed, or who built up slowly.
Within-Customer Trend Features
Rolling slope of transaction value — fit a linear trend to monthly total transaction value over 12 months. A positive slope means growing business (often fine), but a rapidly accelerating slope (exponential growth) is anomalous for many SME types. Compute slope normalised by starting value so it's comparable across customers of different sizes.
Month-on-month change features — for your key metrics (transaction count, value, unique beneficiaries, international volume), compute the percentage change from the prior period and the z-score of that change relative to the customer's own history. A z-score above 3 on any metric in a given month flags a structural break.
Behavioural consistency score — compute the average pairwise correlation of monthly feature vectors across the customer's history. A customer whose monthly behaviour is highly consistent scores near 1. A customer whose behaviour varies wildly scores near 0. Sudden drops in this score (i.e., the recent months look nothing like the historical months) are a change-in-behaviour signal.
Dormancy followed by activity — flag customers who had low or zero activity for 3+ months and then resumed. This is a common account takeover and front company activation pattern. Features: months of dormancy in last 24 months, value in first active month following dormancy.
Seasonality deviation — for customers with enough history (12+ months), fit a seasonal decomposition and compute the residual. Large residuals in recent months indicate the customer is deviating from their own seasonal pattern.
Peer Comparison Over Time
Percentile rank within peer group, rolling — compute each customer's percentile rank on key features (transaction value, international volume, beneficiary concentration) within their peer group each month. The feature is not the raw percentile but the trend of that percentile. A customer who was at the 50th percentile 12 months ago and is now at the 95th percentile has moved significantly within their peer group even if their absolute values don't look extreme.

5. Device ID Features
This data is underused in most financial crime models and it's very high signal.
Number of distinct devices — count of unique device IDs associated with a customer's logins/transactions over the window. Most legitimate SMEs use 1–3 devices (owner's phone, laptop, maybe a second employee). High device counts are anomalous.
Device introduction rate — how often does a new device appear? A business that introduces a new device every week is behaviorally anomalous.
Device sharing across customers — this is the network feature. Count how many other customers in your book share at least one device ID with this customer. Shared devices across nominally unrelated businesses is a very strong signal of connected entities, mule networks, or a single operator running multiple accounts. This feature requires a cross-customer join and can be computationally expensive but is worth it.
Device geographic consistency — if you have device location data, compute whether the device locations are consistent with the registered business address. A business registered in Leeds whose devices all geolocate to London or abroad has an address-device mismatch.
Session behaviour anomalies — if you have session-level data (login times, session durations, actions per session), compute features like typical login time distribution, average session length, and flag deviations. Automated or scripted account activity often has distinctive session signatures.

6. Customer Attribute Derived Features
These come from your customer data and are partly used for peer group definition and partly as features in their own right.
Director count to turnover ratio — a company with 8 directors and £200k turnover has a high director density relative to size. This is anomalous for most SIC codes and is sometimes associated with nominee director arrangements.
Address coherence features — three binary or categorical features: whether registered address, business address, and correspondence address are in the same region; whether any of the three addresses are in a high-risk postcode (your bank should have a postcode risk list); and whether any address is a known formation agent or virtual office address. The last one requires a lookup table but is extremely high signal.
Nationality diversity of directors — number of distinct director nationalities. This is not a risk feature on its own (and must not be treated as one — see governance note below) but combined with other features like international payment destinations, it can be part of a composite. Be very careful here: the feature should be "director nationalities match international payment destinations" (a coherence check with a plausible business rationale) rather than "directors are of nationality X."
SIC code risk tier — your bank should have a SIC-level inherent risk rating. Include this as a feature but be aware it's a prior, not a signal. It tells you what to expect, not what's happening.
Customer age — days since onboarding. Very new customers with high activity are structurally different from established customers with the same activity level. Also, customers who are several years old but have thin transaction history (low engagement) relative to their declared turnover are anomalous.
Turnover declared vs. transactional turnover — compare the declared annual turnover from onboarding data against the actual transaction volume processed through the account. A company declaring £5m turnover but processing £50m is anomalous. So is one declaring £5m and processing £50k — both represent mismatches with the expected relationship between declared and observed.

7. Network and Linkage Features
These require cross-customer analysis and are more expensive to compute but among the most powerful.
Shared director linkage count — how many other active customers share at least one director with this customer? A network of 10 companies sharing a director pool, especially in the same SIC, is a control structure worth examining.
Address linkage count — how many other customers share the same registered address? Hundreds of companies at the same address is a formation agent flag. Compute separately for registered, business, and correspondence.
Second-degree beneficiary overlap — not just whether this customer pays the same beneficiaries as exited customers, but whether this customer pays businesses that themselves pay the same beneficiaries as exited customers. This is expensive but powerful for detecting networks that have learned to avoid direct connections to flagged entities.
Community detection score — if you build a graph of customers connected by shared directors, addresses, device IDs, and beneficiaries, you can run a community detection algorithm (Louvain, label propagation) and compute the size and risk score of the community this customer belongs to. Customers in large, densely connected communities that include any exited-for-FC members should have elevated scores.

8. Exited Customer Similarity Features
Since you have an FC-exited population, treat it as a reference distribution.
Feature-space distance to exited customer centroid — compute the mean feature vector of your exited-for-FC customers by SIC group. Compute the Mahalanobis distance (not Euclidean — you need to account for feature correlations) from each active customer to that centroid. This is a single continuous similarity score.
Nearest-neighbour distance to exited customers — for each active customer, find the k nearest exited customers in feature space and compute the average distance. Customers very close to exited customers in behaviour space are high-priority regardless of their absolute anomaly score.
Exited customer feature match count — rather than a continuous distance, a more interpretable feature is: across your top 20 most discriminating features between exited and non-exited customers, how many does this active customer match (within a defined threshold)? This gives you a discrete count from 0 to 20 that analysts find intuitive: "this customer matches 14 of 20 behavioural characteristics of customers previously exited for financial crime."

Feature Engineering Governance Notes
A few critical points before you build any of this. Nationality must not be a direct model input. Address and director nationality data can be used only for coherence checks (does the business activity match the international footprint) and must be documented as such. Run a feature importance audit to confirm nationality-derived features are not the dominant drivers of anomaly scores.
Missing data strategy must be documented. Many customers will have null values for international payments (they don't send any), device ID (no digital banking), or turnover (not updated since onboarding). Nulls are often themselves informative — a business with no declared turnover update in 3 years is different from one with a current figure. Create explicit missingness indicator features rather than imputing silently.
Feature stability testing — before production, compute the population stability index (PSI) of each feature monthly. Features with high PSI are changing in distribution and may indicate data quality issues or genuine population shifts. Unstable features make model scores unstable and are a model risk concern.
Correlation pruning — many of these features will be correlated (transaction count and value often move together). Run a correlation analysis and for highly correlated pairs (above 0.85), prefer the more interpretable one or create a single composite. This reduces multicollinearity effects in tree-based models and makes SHAP decompositions more stable.
You should aim for somewhere between 60 and 100 final features after pruning, computed across multiple time windows. The richness comes from the combination of cross-sectional peer comparison, within-customer temporal features, and network linkage — none of these three alone is sufficient.So just prepare features for  30d, 90d, 180d, 360d, and get data for 2 years to build a view of historical expectations?Feb 20Yes, but with some important nuances on how you structure this.
The Time Window Logic
Your four windows (30, 90, 180, 360 day) are right, but think carefully about what each window is actually measuring. They're not just different granularities of the same thing — they're capturing fundamentally different signals.
The 30-day window captures current behaviour and acute changes — a business that just started doing something unusual will show up here first. It's noisy but sensitive.
The 90-day window captures tactical patterns — enough data to smooth noise for most SMEs while still being responsive to change. For businesses that transact infrequently (maybe 5–10 transactions a month), 30 days isn't enough to be statistically meaningful. 90 days is your workhorse.
The 180-day window captures structural behaviour — this is where you see whether a pattern is sustained or a blip. A business with elevated international payments for 6 months is very different from one that had one unusual month.
The 360-day window captures the baseline identity of the business — what it looks like at full annual cycle, absorbing seasonality. This is your primary peer comparison anchor.
The 2-Year History Point
Two years is a reasonable minimum but you should think of it in two distinct roles.
The first 12 months is your baseline construction period — you use it to build expected behaviour profiles per customer and per peer group. From this you derive each customer's "normal" distribution.
Months 13–24 are your scoring period — you compute features for each rolling window relative to the baseline and look for deviations. The anomaly is defined relative to what was established in the baseline.
The gotcha here is new customers. Someone onboarded 6 months ago has no 360-day window and an unstable 180-day window. You need a maturity flag on every customer's features so the model knows how much history underpins each feature. Don't impute missing windows with zeros — a missing 360-day window for a new customer is fundamentally different from a customer who genuinely had zero transactions in that period. Treat them as separate populations in your model or add a "months of history" feature explicitly.
How to Structure the Feature Table
Don't create one flat table with 400 columns. Build it in layers.
A snapshot table computed monthly — for each customer at each month-end, compute all four windows as they looked at that point in time. This gives you a longitudinal panel, not just a current snapshot. The shape is customer × month with ~80-100 features per window set.
The reason this matters is that it lets you do two things your design requires. First, you can train your anomaly model on historical snapshots so it learns what the population looked like over time, not just today. Second, you can compute trend features as first-class features — the change in a customer's 30-day HHI between month T and month T-3, for example, is itself a feature derived from the panel.
From this panel you then derive your current scoring snapshot — which is just the most recent month's row per customer, plus the trend features computed across recent months.
What 2 Years Actually Gives You
For your exited customer comparison, 2 years of history is particularly valuable because FC-motivated behaviour often has a run-up period before exit. If a customer was exited in month 18, their behaviour in months 1–6 is your "pre-suspicious baseline" and months 12–18 is your "pre-exit signature." Preserving the full longitudinal history of exited customers lets you characterise not just what they looked like at exit but how they evolved — which means you can catch active customers who are in the early stages of that same trajectory, not just the end state.
Practical Advice on Computation
Build the feature pipeline to run monthly, producing a new row per customer in your panel table. Don't try to recompute from raw transactions every time — maintain rolling aggregates where possible. For something like HHI of beneficiary concentration, you can maintain a running beneficiary-value dictionary and update it monthly rather than recomputing from scratch.
Windows should be trailing and inclusive — your 90-day window at month-end October includes August, September, October. Be precise about this in your data dictionary and test it, because off-by-one errors in time windows are one of the most common sources of feature leakage in longitudinal models.
Finally, version your feature table. When you recalibrate the model or add new features, you want to know exactly what feature definition underpinned each model version. This is a model governance requirement and also practically important when an analyst challenges a score 18 months from now.So what's the approach for a monthly snapshot but wanting to do last X days. March Vs Feb will always have an uplift as there are more days - but a monthly snapshot erodes that granuarityFeb 20Exactly right, and this is one of the most common design flaws in transaction monitoring feature pipelines. You've identified the core tension: calendar months are convenient for snapshotting but they're a terrible unit for behavioural windows.
The Problem Precisely Stated
If you snapshot on the last day of each month and compute "last 30 days," March gives you 31 days, February gives you 28. That's an 11% difference in exposure before any behaviour changes. For count-based features this directly inflates March scores. For value-based features it's slightly less mechanical but still introduces calendar noise. The moment you compare a March snapshot to a February snapshot, you're partially measuring the calendar, not the customer.
This gets worse at 90 days across quarter boundaries and 360 days across years with different compositions of long and short months.
The Clean Solution: Anchor to a Fixed Reference Date, Not Month-End
Instead of snapshotting at month-end and looking back variable distances, you compute all windows as exact calendar-day lookbacks from a fixed weekly or bi-weekly computation date.
Run your feature pipeline every Sunday. On that Sunday, every window is computed as exactly the last 30, 90, 180, 360 calendar days from that date. No customer ever gets 28 days when another gets 31. The windows are precise and comparable across all customers and all computation dates.
You lose the convenience of "monthly snapshot" but you gain clean, comparable features. Your panel table now has a row per customer per week rather than per month, which is actually richer.
But Weekly Is Expensive — Here's the Pragmatic Middle Ground
If weekly computation is too heavy for your data infrastructure, the compromise is monthly snapshots but rate-normalised features.
Instead of computing raw counts and values for the window, you compute everything as a daily rate. Transaction count becomes transactions per day. Payment value becomes value per day. International payment volume becomes international transactions per day.
At that point it genuinely doesn't matter whether the window covered 28 or 31 days because you've normalised the exposure out. March and February are directly comparable. The formula is simply: feature value divided by number of calendar days in the window.
This applies cleanly to count and value features. For distributional features like HHI, percentile distributions, or entropy, the calendar length issue is less severe because you're characterising shape rather than volume — though you should still flag windows with very low transaction counts as unreliable regardless of their calendar length.
The Sliding Window Panel Design
If you go the weekly route, your panel table structure becomes:
Each row represents a customer on a specific computation date. You store the computation date, and for each feature you store its value computed over the exact trailing window. The 30-day feature for customer A on 2024-03-17 covers 2024-02-15 to 2024-03-17. The same feature on 2024-03-24 covers 2024-02-22 to 2024-03-24. Both are exactly 30 days. No calendar distortion.
This also means your trend features — the change in a feature between computation dates — are always computed across comparable windows. A delta computed between two weekly snapshots is always a 7-day behavioural shift, not a 28-to-31-day shift.
Handling the Granularity Question for Anomaly Detection
The deeper point your question is getting at is that monthly snapshotting masks intra-month patterns. A business that receives a large payment on the 3rd and disperses it by the 5th will look perfectly normal in a monthly snapshot because the money arrived and left within the same period and the net effect is unremarkable. Weekly or even daily feature computation would catch the velocity.
The practical answer for most banks is a two-tier design. Your anomaly scoring model runs on weekly snapshots using the normalised daily-rate features described above — this is your primary detection layer. Separately, for customers who breach a score threshold, you trigger a transaction-level drilldown that looks at day-by-day behaviour within the flagged window. The model doesn't try to capture intra-week velocity at the feature level; instead, surfacing that detail becomes part of the analyst investigation workflow triggered by the model score.
What to Store in Your Panel Table
On each weekly computation date, for each customer, store the window start date and window end date explicitly alongside every feature. Don't just store the computation date and assume the window is inferrable. When an analyst or model risk reviewer questions a score 14 months later, you need to be able to reproduce exactly what data underpinned every feature value. Storing the window boundaries explicitly makes that reconstruction unambiguous and is a governance requirement in practice even if no policy document explicitly mandates it.I'm happy to run it weekly. So it would be for a given Sunday & I would create 30 day windows for each timeframe historically, as t, t-1 etc. is that right?Feb 20Yes, exactly. Let me make sure the mental model is precise before you build it.
The Structure
For each Sunday (your computation date), you compute four feature vectors per customer — one for each window — where every window ends on that Sunday and looks back exactly 30, 90, 180, 360 days.
So for a given Sunday T:

30-day window: T-30 to T
90-day window: T-60 to T (not T-90 to T-60 — it's always trailing to T)
180-day window: T-150 to T
360-day window: T-300 to T

Wait — I need to correct that. The windows are trailing from T, so:

30-day: T-30 → T
90-day: T-90 → T
180-day: T-180 → T
360-day: T-360 → T

They're nested and overlapping, not sequential. The 90-day window contains the 30-day window within it. That's intentional — the 30-day is always the most recent slice, and each longer window adds historical context around it.
The Panel
Your panel then looks like this conceptually:
customer_idcomputation_datew30_txn_count_dailyw90_txn_count_dailyw180_txn_count_dailyw360_txn_count_daily...A2024-01-070.430.510.480.45...A2024-01-140.610.530.490.46...A2024-01-210.380.520.490.46...
Each row is one customer on one Sunday. Two years of weekly Sundays is roughly 104 rows per customer. Across say 50,000 business customers that's 5.2 million rows in your panel, which is very manageable.
The T, T-1, T-2 Logic
Yes, your T / T-1 / T-2 framing is right but be precise about what T means in context.
T is always "the most recent Sunday" — this is your live scoring snapshot, the one that feeds the dashboard and generates alerts.
T-1 is the prior Sunday — one week ago. The delta between T and T-1 on any feature is a 7-day behavioural shift signal.
T-4 is roughly a month ago — four Sundays back. Delta between T and T-4 gives you a month-on-month comparison that is calendar-clean because both snapshots used identical window definitions.
T-13 is roughly a quarter ago, T-26 is roughly six months ago, T-52 is a year ago.
These deltas become their own features. The rate of change in a customer's w30 international payment value between T and T-4 is more signal-rich than the absolute value at T alone. You're effectively building a feature of features — the derivative of each window metric over time.
One Important Nuance
The windows are nested, which means they're not independent. Your w30 features and w360 features share the last 30 days of underlying data. This means they'll be correlated, and your model needs to handle that. It's not a problem for tree-based models or isolation forests, but it's worth noting in your model documentation and being aware of when interpreting SHAP values — a feature's contribution may be partially absorbed by a correlated window feature.
The reason you still want all four windows despite the overlap is that the ratio between windows is itself informative. If a customer's w30 daily transaction rate is 3x their w360 daily rate, something changed recently. If w30 ≈ w360, behaviour is stable. You can make this explicit by computing a recency ratio feature: w30_value / w360_value. Values far from 1.0 in either direction are a signal. This is one of your cleanest change-detection features and it emerges naturally from the nested window design.Explain the transaction size consistency idea, 2x historical medianFeb 20Good question to dig into because the naive implementation has a flaw that will cause you problems.
The Idea
The intuition is that most legitimate businesses have a characteristic transaction size distribution that reflects their actual commercial activity. A recruitment agency pays salaries in predictable bands. A wholesaler invoices in predictable ranges. When that distribution suddenly shifts — particularly at the upper end — it's worth knowing about.
The "2x historical median" feature is trying to capture: how often is this customer doing something materially larger than their own normal?
The Naive Implementation and Its Flaw
The naive version is: compute the customer's median transaction value over the full historical window, then count the proportion of transactions in the current 30-day window that exceed 2x that median.
The problem is that the historical median is computed on the same data that contains the anomalies you're trying to detect. If a customer had a period of large anomalous transactions 8 months ago, those inflate the median, which makes current large transactions look less unusual. Your baseline is contaminated by the signal you're trying to measure.
This is a form of label leakage through the baseline and it's subtle enough that most implementations miss it.
The Clean Implementation
You need to separate your baseline period from your observation period.
The baseline median should be computed on a fixed historical anchor window — specifically, the earliest stable period of the customer's history where you have sufficient transactions and no known flags. In practice, for a 2-year panel, use months 1–12 as the baseline construction period and months 13–24 as the observation period. The median is fixed from the baseline and doesn't update as you score forward.
So the feature becomes: proportion of transactions in the current 30-day window that exceed 2x the baseline-period median, where baseline median is computed once and stored as a customer-level attribute.
This means the denominator never moves in response to what's happening in the observation period. A customer who was consistently doing £5k transactions in year one has a stable median of £5k. If in month 18 they start doing £15k transactions, that's 3x the baseline median and it registers clearly. The contamination problem disappears.
The Threshold Choice
The 2x multiplier is somewhat arbitrary. The right way to think about it is: what multiple is large enough to exclude normal business variability but small enough to catch meaningful shifts?
For most SMEs, transaction values have moderate natural variance. A coefficient of variation of 0.5–1.0 is common, meaning transactions regularly vary ±50–100% around the mean. A 2x threshold means you're flagging transactions that are in roughly the top 5–15% of the customer's own historical distribution depending on how skewed their distribution is.
Rather than a fixed 2x multiplier, a more principled approach is to use the customer's own historical 90th percentile as the threshold. A transaction exceeding the customer's own 90th percentile is by definition unusual for that customer, and this threshold is empirically derived from their actual distribution rather than an arbitrary multiplier. The feature then becomes: proportion of transactions in the current window exceeding the baseline 90th percentile value.
This handles skewed distributions better. A business whose transactions are naturally high-variance gets a higher threshold. A business with very consistent transaction sizes gets a lower one. The threshold is self-calibrating per customer.
What You're Actually Measuring
Once you have the feature correctly defined, think carefully about what it's detecting and what it isn't.
It detects upward size shifts — transactions getting larger than normal. This is relevant for layering (someone starts processing larger amounts through the account), invoice fraud (inflated invoices), and certain types of disbursement fraud.
It does not detect downward size shifts — transactions getting systematically smaller. You should build a complementary feature for this: proportion of transactions below the baseline 10th percentile. This catches structuring behaviour where a customer who normally transacts in £10k–£50k bands suddenly starts doing lots of £900 transactions, staying just below round number thresholds.
It also does not detect changes in transaction count, only size. A customer whose individual transaction sizes are normal but who is doing 10x their normal number of transactions won't be flagged by this feature. That's why you need the velocity features alongside it.
Combining Into a Composite
In practice, the most useful version of this concept is a three-part distributional shift feature:
The proportion of transactions exceeding the baseline 90th percentile (upper tail shift), the proportion below the baseline 10th percentile (lower tail shift), and the ratio of current median to baseline median (central tendency shift). These three together characterise whether the distribution has shifted up, down, compressed, or expanded. Each is a separate feature going into the model, and together they give SHAP decomposition something meaningful to work with when explaining why a customer scored as anomalous.
New Customer Problem
For customers with less than 6 months of history, the baseline median is unreliable because it's computed on too few transactions. You have two options. Either suppress this feature for customers below a transaction count threshold (say, fewer than 20 transactions in the baseline period) and use a missingness indicator instead, or substitute the peer group median for the individual baseline median for new customers, then transition to the individual baseline once sufficient history exists. The peer group substitution is less precise but better than either suppressing the feature entirely or computing an unstable individual baseline on 8 transactions.
Document whichever approach you choose explicitly — model risk will ask about it.How many peer groups should I look at? I don't want to be too general, but too granular isn't great either.Feb 20This is one of the most consequential design decisions in the whole system because peer groups define what "normal" means. Get them wrong and you're either comparing apples to oranges (too broad) or you have peer groups of 3 customers where one outlier destroys the whole comparison (too granular).
The Core Problem
You're trying to solve two competing constraints simultaneously. Behavioural homogeneity — customers in the same peer group should genuinely behave similarly for non-suspicious reasons. Statistical sufficiency — each peer group needs enough members to produce stable distributional estimates. These pull in opposite directions. Every dimension you add to the peer group definition increases homogeneity but reduces group size.
The minimum viable peer group size for reliable anomaly detection is around 30 customers. Below that, your percentile estimates are unstable, your distributional features are noisy, and a single unusual-but-legitimate customer can distort the whole group's baseline. Aim for a minimum of 50 to give yourself a buffer.
The Dimensions Available to You
You have: SIC code, customer segment, legal structure / number of directors, turnover band, and implicitly customer age and geographic region. Let's think about each one's actual discriminatory power.
SIC code is your most important dimension. It's the primary driver of legitimate behavioural differences — a construction company and a law firm should transact differently and you want the model to know that. However, raw 4-digit SIC gives you over 700 categories, many of which will have very few customers in your book. The question is what level of aggregation to use.
Turnover band matters a lot because a £200k turnover business and a £20m turnover business in the same SIC will have completely different transaction volumes. This is probably your second most important dimension.
Legal structure or director count is a proxy for business complexity and type. A sole director company behaves differently from a 10-director company even in the same SIC and turnover band.
Customer segment — if your bank already segments customers (e.g. micro, SME, mid-market), this may already encode some of the above. Check whether it adds information beyond SIC and turnover before including it as a separate dimension.
Geographic region has weaker discriminatory power for most features and will fragment your groups significantly. I'd exclude it from peer group definition unless you have a specific reason to believe regional behaviour differences are material in your book.
Recommended Approach: Two-Level Hierarchy
Don't use a single flat peer group definition. Use a hierarchy with two levels.
Level 1 is your primary peer group — used for percentile ranking, distributional comparisons, and the core anomaly score. This should be defined on two dimensions only: SIC at division level (the single-letter or two-digit grouping, giving you around 20–25 categories) crossed with turnover band (4–5 bands). That gives you roughly 100–125 potential peer groups before any filtering for minimum size.
Level 2 is your thematic review group — a more granular cut used when an analyst or request specifies a particular population. This is where you bring in 4-digit SIC, director count, and potentially other dimensions. This level is not used for the baseline model scoring — it's used for the dashboard filtering and investigation layer.
The reason to separate these is that your model needs stable peer groups to produce reliable scores, but your analysts need granular filtering to answer questions like "show me Italian-owned construction companies." Those are different use cases and trying to serve both with the same peer group definition will compromise both.
SIC Aggregation in Practice
For your Level 1 groups, the SIC division level works well as a starting point but you should validate it empirically. Pull the distribution of your book across SIC divisions and check group sizes before committing.
Some divisions will be too heterogeneous even at division level. Section G (wholesale and retail trade) contains everything from car dealers to grocery wholesalers — their transaction behaviour is genuinely very different. You may need to split some high-population divisions by the first two digits rather than the single letter.
Some divisions will be too small even at division level and you'll need to merge them. Sections like mining, utilities, and agriculture may have so few customers in a typical bank's SME book that they need to be grouped into an "other" category or treated as their own population with the peer comparison defaulting to the full population.
The right approach is to run your book through a candidate peer group definition and produce a distribution of group sizes. Any group below your minimum threshold (50 customers) needs to either be merged upward or have its peer comparison fall back to the next level up in the hierarchy.
Turnover Bands
Don't use equal-width bands (0–1m, 1–2m, 2–3m etc.) because turnover is log-normally distributed and most customers cluster at the lower end. Use log-scale bands instead:
Under £100k, £100k–£500k, £500k–£2m, £2m–£10m, over £10m.
Five bands is usually sufficient. The boundaries should be calibrated to your actual book distribution so each band has reasonable population. Check the distribution of your customers across these bands and adjust the boundaries so no single band contains more than 40% of your book.
One important gotcha: declared turnover at onboarding is often stale or wrong. A business onboarded 4 years ago with £500k declared turnover may now be turning over £5m or £50k. Consider whether you want to use declared turnover or observed transactional turnover (derived from your transaction data) as the banding variable. Observed transactional turnover is more accurate but only captures what flows through your account, which may be a fraction of total business turnover. Declared turnover is stale but represents total business size. Using both — declared for initial banding, with a flag when observed diverges significantly — is the most defensible approach.
Handling Peer Group Sparsity
Even with a well-designed two-dimensional peer group, you'll have some groups that are too small. Have an explicit fallback hierarchy:
First preference is the defined peer group (SIC division × turnover band) if n ≥ 50. If that group has fewer than 50 members, fall back to SIC division only — drop the turnover band constraint. If that still gives fewer than 50, fall back to SIC section (one level up). If you're still below threshold, fall back to the full population of the same broad customer type (all businesses, for example).
Record which level of the hierarchy was used for each customer's peer comparison. This is a feature in itself — a customer whose peer group is only definable at the full-population level is by definition in a sparse category, which may itself be informative. It also matters for SHAP explainability: telling an analyst "this customer is anomalous compared to all businesses" is much weaker than "anomalous compared to 847 similar construction companies of similar size."
Validating Your Peer Groups
Before you finalise the design, run a validation. For each candidate peer group, compute the within-group variance and between-group variance on your key features (transaction value distribution, international payment rate, beneficiary concentration). You want within-group variance to be substantially lower than between-group variance — this confirms the peer group dimension is actually discriminating behaviour, not just creating arbitrary categories.
If within-group variance is nearly as high as between-group variance for a given feature, the peer group definition isn't doing useful work for that feature. Either your grouping variable isn't predictive of that behaviour, or the feature is genuinely noisy and peer-relative comparisons won't help. This analysis will also tell you which features benefit most from peer comparison and which are better assessed at the population level regardless of peer group.
Practical Number
For a typical bank SME book of 30,000–100,000 business customers, you're likely to end up with somewhere between 40 and 80 stable Level 1 peer groups after applying the minimum size threshold and merging sparse categories. That range gives you genuine behavioural homogeneity within groups while maintaining statistical reliability. Fewer than 30 and you're probably too broad. More than 120 and you'll have too many sparse groups and the complexity of maintaining and validating them all becomes a governance burden in itself.So in simple terms, review the book and identify by sic/turnover peer groups, and as I want it a self service tool without updating for each typology keep it at that level but allow filtering in the dashboards to filter for pertinent customers to investigate anomaliesFeb 20Yes, exactly. You've distilled it well. Let me just sharpen the mental model so it's airtight.
What You're Building
The model and peer groups are fixed and stable. SIC division × turnover band, defined once, validated once, reviewed periodically. Every customer gets a peer group assignment and an anomaly score relative to that group. This runs weekly, automatically, without anyone touching the peer group definitions.
The dashboard is where all the flexibility lives. The score is already computed. The analyst just filters the pre-scored population to find the customers relevant to whatever question they're asking that week.
So when someone comes to you and says "review Italian-owned construction companies," you don't build a new model or redefine peer groups. You open the dashboard, filter by SIC (construction divisions), filter by director nationality (Italian), and the anomaly scores are already there. The model did its job. The analyst is just slicing the scored population.
Why This Architecture Is Right
It means the model is question-agnostic. It doesn't know and doesn't care whether this week's typology is car washes or currency exchanges or nail bars. It scores every customer against their peers every week. The typology question just becomes a filter applied after the fact.
It also means the model is auditable and stable. Model risk can validate it once. You're not rebuilding or retuning every time a new thematic request comes in. If you had to retrain or redefine peer groups for each typology, you'd have an ungovernable model estate within 18 months.
The One Thing to Be Clear About With Stakeholders
The anomaly score tells you who is unusual relative to their peers. It does not tell you who is suspicious in an absolute sense. A car wash that scores highly anomalous is unusual compared to other car washes of similar turnover. Whether that's suspicious requires analyst judgement informed by the score decomposition.
This distinction matters because stakeholders will sometimes expect the tool to directly answer "which car washes are suspicious." What it actually answers is "which car washes behave differently from other car washes, and here is specifically what is different." That's still enormously valuable — it's just important to set the expectation correctly so the tool isn't seen as failing when anomalous customers turn out to have legitimate explanations.
The dashboard filter gets you to the right population. The anomaly score and its decomposition tells you where to look first within that population. The analyst makes the judgement call. That's the correct division of labour and it's also what your AI governance framework will require.So I have started building the transaction aggregation df, with  value, volume, mean, s d., cov, and 5 percentiles for credits and debits for 4 different timeframes seems a massive amount of aggregation. Is this necessary? I still have to do all the transaction types and markers as discussed earlier for each time too. I just want to make sure this is reasonableFeb 20It is a lot, but it's reasonable — the question is whether you need all of it from day one or whether you're over-engineering the first version.
The Honest Answer
You don't need all of it upfront. What you're describing is the full production feature set. But the right approach is to build a lean v1 that proves the concept and gets analyst buy-in, then iterate.
For credits and debits, across four time windows, you're looking at:
Value, volume, mean, SD, CoV, and 5 percentiles = 8 features × 2 directions × 4 windows = 64 features just for basic transaction stats. Before you've touched transaction types, international payments, counterparty concentration, device IDs, or temporal change features. You can see how this reaches 400+ features quickly.
What Actually Does the Heavy Lifting
From everything discussed, the features with the highest signal-to-noise ratio for financial crime in business banking are, in rough order:
CoV is more informative than mean and SD individually — it captures behavioural consistency in a single number. If you're cutting features, keep CoV and drop raw SD.
Percentiles at p10 and p90 are more useful than the full five. P10 catches structuring (unusually small transactions), p90 catches large value anomalies. P25, p50, p75 add nuance but are lower priority for v1.
Volume (count) is as important as value — a business doing 10x normal transaction count at normal values is a different risk to one doing normal count at 10x values.
The ratio between windows — w30 value divided by w360 value — is one of your most powerful change detection features and it's derived from what you already have, not an additional aggregation.
Practical Recommendation
For v1, cut to this per direction (credit/debit) per window:
Total value, total volume, CoV, p10, p90. That's 5 features × 2 × 4 = 40 features just for this block. Still substantial but roughly a third of what you were heading toward.
Then add the cross-window ratio features (w30/w360 for value and volume) which costs you 4 more features but adds significant temporal signal.
Then add the other feature categories — international payments, counterparty concentration, device IDs — but again at a lean level. One or two strong features per category rather than exhaustive coverage.
The Dimensionality Reduction Safety Net
Even if you do build all 400 features, an isolation forest or autoencoder will handle high dimensionality reasonably well. But your explainability layer will suffer — when you have 400 features, SHAP decompositions become cluttered and harder for analysts to interpret. Fewer, well-chosen features actually produce cleaner explanations, which is arguably more important for adoption than marginal model performance gains from the extra features.
A good rule of thumb: if you can't explain in one sentence why a feature belongs, cut it for v1 and add it in v2 if the model misses something important.
What This Means for Your Build
Keep your aggregation framework flexible so adding features later is cheap — you're building the pipeline correctly by doing this in a structured DataFrame. But populate it lean for now. Get to a scoreable dataset, run the model, see what the scores look like, get an analyst to sense-check the top anomalies. If the model is surfacing nonsense, more features won't fix it — the problem will be in peer group definition or data quality. If it's surfacing sensible candidates but missing known cases, that's when you add the next layer of features with a clear hypothesis about what signal they're adding.Just building the report itself has the buy in from stakeholders. I'm happy to build it thoroughly from the outsetFeb 20Then build it properly from the start. That's the right call — retrofitting features into a production pipeline is significantly more painful than building them in once with a clean architecture.
Reframe How You Think About the Volume
400+ features sounds intimidating but you're not writing 400 individual aggregations. You're writing a small number of parameterised aggregation functions that you apply across dimensions. The code structure should reflect that.
Your aggregation logic should look something like:
pythondef compute_window_features(df, window_days, reference_date, direction=None):
    """
    Single function handles any window, any direction.
    Called 8 times (4 windows × 2 directions) to produce all base features.
    """
Then a feature manifest that declares what gets computed:
pythonWINDOWS = [30, 90, 180, 360]
DIRECTIONS = ['credit', 'debit']
PERCENTILES = [0.10, 0.25, 0.50, 0.75, 0.90]
```

You write the logic once. The dimensionality comes from the parameter combinations, not from duplicated code. This also means adding a new feature later — say kurtosis of transaction values — is one line in the function, not 8 separate additions.

## Structuring the Full Feature Build

Think of it in distinct blocks, each its own module or clearly separated section of your pipeline. Each block has its own aggregation function, and all blocks feed into a single customer-week feature table at the end.

**Block 1 — Core transaction stats** (what you're building now)
Value, volume, mean, SD, CoV, 5 percentiles, for credits and debits across 4 windows. Plus the cross-window ratios (w30/w360, w30/w90 etc.) derived after the block runs.

**Block 2 — Transaction type distribution**
For each transaction type in your data, proportion of count and proportion of value, across 4 windows. Plus entropy of the distribution. The feature count here depends on how many transaction types you have — if you have 10 types, that's 10 × 2 × 4 = 80 features, but most will be near-zero for most customers and will drop out in feature selection.

**Block 3 — Counterparty features**
Unique beneficiary count, HHI of beneficiary concentration, top-1/3/5 concentration ratios, new beneficiary rate — all for debits, across 4 windows. Beneficiary classification split (aggregator vs named vs intrabank) as proportions. These require a beneficiary lookup enrichment step before aggregation.

**Block 4 — International payment features**
Distinct country count, value-weighted country risk score, max country risk encountered, proportion of value to high-risk countries, inbound vs outbound country overlap, new country rate. Across 4 windows. Country risk scores need a static lookup table as input.

**Block 5 — Temporal and change features**
These are derived from your panel table, not from raw transactions directly. For each key metric in blocks 1–4, compute the delta between current Sunday and T-4, T-13, T-26, T-52. Also the rolling slope over 12 weeks. Also the recency ratio (w30 metric / w360 metric). These are computed after the window features exist.

**Block 6 — Device ID features**
Distinct device count, device introduction rate, shared device count across customer base, session behaviour features if available. Across 4 windows where applicable — some of these are point-in-time rather than windowed.

**Block 7 — Customer attribute features**
Computed once per customer, not per window. Director count to turnover ratio, address coherence flags, SIC risk tier, customer age, declared vs observed turnover divergence, turnover band assignment. These are static or slow-changing and join to the panel table as customer-level attributes.

**Block 8 — Network and linkage features**
Shared director count, shared address count, device sharing across customers, community detection score. These require cross-customer joins and are the most computationally expensive. Run these separately and join to the panel table.

**Block 9 — Exited customer similarity features**
Mahalanobis distance to exited customer centroid by SIC group, nearest-neighbour distance, exited feature match count. These require the exited customer feature vectors as a reference table and are computed after all other features exist.

## Column Naming Convention

Establish this before you write a single feature. Changing naming conventions mid-build in a 400-column DataFrame is painful. A clean convention is:
```
{block}_{metric}_{direction}_{window}d
```

For example:
- `txn_value_total_credit_30d`
- `txn_cov_debit_90d`
- `txn_p90_credit_180d`
- `intl_country_risk_wtd_360d`
- `cpty_hhi_debit_90d`
- `dev_distinct_count_30d`
- `delta_txn_value_credit_30d_t4` (change features)
- `ratio_txn_value_credit_w30_w360` (cross-window ratios)

Consistent naming means you can programmatically select feature subsets by pattern matching — all 30-day features, all credit features, all international features — which makes model analysis, SHAP grouping, and dashboard development significantly easier.

## Data Quality Flags to Build Alongside Features

For every block, build a parallel set of data quality indicator columns. These serve governance and also become features in their own right.
```
{block}_{window}d_txn_count  # how many transactions underpinned this feature
{block}_{window}d_data_flag  # 0=reliable, 1=sparse, 2=missing
```

A w30 CoV computed on 3 transactions is unreliable. A w360 international payment risk score computed on 1 transaction is unreliable. The model needs to know this. Sparse features should be flagged and either suppressed or down-weighted. Model risk will specifically ask how you handle low-observation windows.

## What Your Final Table Looks Like
```
customer_id | computation_date | peer_group_id | peer_group_level | 
[~320 window features] | [~60 delta/ratio features] | 
[~20 customer attribute features] | [~15 network features] | 
[~10 exited similarity features] |
[data quality flags]
Roughly 400–450 feature columns, plus identifiers and metadata. One row per customer per Sunday. With 2 years of history that's 104 Sundays. Across 50,000 customers that's 5.2 million rows. At 450 columns, mostly float64, that's around 18–20GB uncompressed. Store it as Parquet partitioned by computation_date — query performance and storage will be fine.
Build Order
Do it in this sequence rather than trying to build everything at once.
First get Block 1 complete and validated — you're already here. Sense check the numbers against known customers before moving on. One customer you know well, manually verify their 30-day credit volume matches what you'd expect from the raw data. Do this for edge cases too: a customer with no transactions in a window, a new customer, a dormant customer.
Then Blocks 2 and 3 which use the same transaction data source and similar aggregation logic — they're quick wins once Block 1 is solid.
Then Block 4 which requires joining your international payments data source — a different input so worth treating separately.
Then Block 7 customer attributes — a simple join but validates your customer data quality.
Then Blocks 5 and 6 which depend on earlier blocks being complete.
Then Blocks 8 and 9 last — they're the most complex, require the most data, and aren't needed until the model itself is ready.
Getting Blocks 1–4 and 7 complete gives you enough to run a prototype model and produce a first dashboard. That's your proof of concept. Blocks 5, 6, 8, 9 are what takes it from prototype to production quality.Great, what next?Feb 20You've got your feature table. Here's the full sequence of what comes next, in order.
1. Data Quality and Exploratory Analysis
Before any modelling, spend time understanding what you've actually built. This is not optional and will save you significant pain later.
Distribution analysis on every feature block. Plot distributions for each feature and look for: extreme skew (most financial features will be right-skewed and need log transformation), unexpected spikes at zero (are these genuine zeros or missing data encoded as zero — a critical distinction), and impossible values (negative transaction counts, CoV above 10, percentiles out of order).
Missing data audit. Produce a missingness matrix across your full feature table. You'll likely find certain blocks have systematic missingness for certain customer types — businesses with no international payments, businesses with no digital banking (no device IDs), new customers without full window history. Document every missingness pattern and decide explicitly: is this missing at random, or is the missingness itself informative? For financial crime, it often is. A business with zero international payments for 360 days and then sudden international activity is different from one that consistently uses international payments. The missingness pattern is signal.
Peer group size validation. For every peer group, compute the member count. Apply your minimum threshold (50 customers). Identify which groups fall below it and implement your fallback hierarchy now, before modelling. Trying to fix sparse peer groups after the model is built is significantly harder.
Declared vs observed turnover divergence. Before you use turnover bands for peer group assignment, check how many customers have declared turnover that diverges materially from observed transactional volume. High divergence customers may be in the wrong peer group entirely. Flag them — they're also potentially interesting from a financial crime perspective in their own right.

2. Feature Transformation
Raw features won't go into the model directly. You need to prepare them properly.
Log transformation for all value and volume features. Transaction values, payment volumes, counterparty counts — these are all right-skewed. Log(x+1) is standard (the +1 handles zeros). This prevents high-value customers from dominating distance-based calculations in your anomaly model.
Standardisation within peer groups, not globally. This is the critical step. For each feature, compute the mean and standard deviation within the peer group and standardise to z-scores. A z-score of 2.5 on international payment volume means this customer is 2.5 standard deviations above their peer group mean — that's meaningful regardless of whether the peer group is high-volume or low-volume businesses. Global standardisation would lose this relative context entirely.
Store both the raw feature value and the peer-group-standardised z-score. The raw value is what analysts see in the dashboard. The z-score is what goes into the model.
Handling zeros explicitly. For features like international payment volume, a large proportion of your book may have genuine zeros — they simply don't make international payments. A zero is not the same as a missing value. Consider creating binary indicator features alongside the continuous ones: intl_any_activity_30d (1 if any international payments, 0 if none). This lets the model treat "no international activity" as a distinct state rather than just the low end of a continuous distribution.
Winsorisation. Cap extreme outliers at the 99th percentile before standardisation. A single customer with a genuinely unusual but legitimate transaction pattern shouldn't distort the peer group z-score distribution for everyone else. Winsorise at the peer group level, not globally.

3. Feature Selection
400+ features going into a model creates noise, multicollinearity, and SHAP interpretation problems. You need to reduce to a meaningful subset.
Correlation analysis. Compute a correlation matrix across all features. For any pair above 0.85 correlation, keep the more interpretable one and drop the other. Expect high correlation between adjacent time windows (w30 and w90 features will often be correlated), between raw value and volume features, and within transaction type distributions. Document what you dropped and why.
Variance thresholding. Features with near-zero variance across the population are uninformative. If 95% of customers have the same value for a feature, it can't discriminate anomalies. Drop features below a variance threshold.
Peer group relevance testing. For each feature, compute the ratio of between-group variance to within-group variance (effectively an F-statistic). Features where between-group variance is low relative to within-group variance are poor peer group discriminators — the peer group definition isn't actually explaining variation in that feature. These features are still valid for population-level anomaly detection but shouldn't drive peer-relative scoring.
Domain-driven selection. After the statistical pruning, do a manual review with a financial crime SME (yourself or a colleague). Some features may survive statistical thresholds but have no plausible financial crime interpretation. Others may have low variance in the current book but be theoretically important for catching specific typologies. Human judgement should have final say on the feature list.
Target somewhere between 80 and 150 features after selection. Enough to capture the full behavioural picture, lean enough for interpretable SHAP outputs.

4. Model Build
Now you're ready to model. You're running three parallel approaches as discussed earlier.
Isolation Forest within peer groups. Train a separate isolation forest for each peer group on the standardised feature set. Set contamination parameter low (0.05 or even 0.02) — you want a tight definition of normal because false positives are costly for analyst time. Key hyperparameters to tune: number of estimators (start at 200), max samples (use 'auto' or set to min(256, peer_group_size)), and max features (try 0.7–1.0). Output is a continuous anomaly score per customer, where lower (more negative) means more anomalous.
Autoencoder on full population. Train a single autoencoder on the full standardised feature set regardless of peer group. Architecture for this scale: input layer → 64 nodes → 32 nodes → 16 nodes (bottleneck) → 32 nodes → 64 nodes → output layer. Use ReLU activations, dropout for regularisation, and MSE reconstruction loss. The anomaly score is the reconstruction error — customers whose behaviour the model can't reconstruct well are anomalous at a population level. This catches customers who don't resemble any known type, which the peer-group isolation forest can miss.
Exited customer similarity. Using your exited-for-FC customer feature vectors, compute for each active customer: Mahalanobis distance to the exited customer centroid (by SIC group), and k-nearest-neighbour distance to the exited population in feature space. These produce two additional continuous scores. If your exited population is large enough (50+ customers) you can also train a one-class SVM on the exited population and score active customers against it.
Ensemble scoring. Combine the three model outputs into a single composite score. Don't average raw scores — the scales are different. Instead, convert each model's output to a percentile rank within the population (0–100), then compute a weighted average of the three percentile ranks. Suggested starting weights: isolation forest 50%, autoencoder 30%, exited similarity 20%. These weights should be treated as a hyperparameter and validated against analyst feedback over time.
The composite score is your primary output. Call it something interpretable in the dashboard — "Anomaly Score" or "Behavioural Risk Score" — and express it as a 0–100 scale where higher means more anomalous.

5. Explainability Layer
This is what makes the tool usable. A score without explanation is just a number.
SHAP values for isolation forest. Use the TreeExplainer from the SHAP library — it's computationally efficient for tree-based models and produces feature-level contributions for each customer's score. For each customer, you get a SHAP value per feature telling you how much that feature pushed the score up or down relative to the baseline.
Integrated gradients for autoencoder. SHAP's DeepExplainer works for neural networks but can be slow. For the autoencoder, an alternative is to compute feature-level reconstruction error contribution — for each feature, how much did it contribute to the total reconstruction error? This is less theoretically rigorous than SHAP but faster and interpretable.
SHAP grouping. With 80–150 features, individual SHAP values are too granular for analysts. Group them by feature block: transaction behaviour, counterparty, international payments, temporal change, device, network. Sum the absolute SHAP values within each group to produce a block-level contribution score. The analyst sees: "Score driven 45% by international payment behaviour, 30% by counterparty concentration, 15% by temporal change, 10% by transaction behaviour." They can then drill into the specific features within each block.
Natural language explanation generation. For the top 3 driving feature groups per customer, generate a templated plain-English explanation. Something like: "This business scores in the 94th percentile of its peer group (SIC construction, turnover £500k–£2m). The primary drivers are significantly higher international payment volume to high-risk jurisdictions than peers (w90 international high-risk value z-score: 3.2), rapid increase in new beneficiaries over the last 30 days (new beneficiary rate z-score: 2.8), and transaction size distribution shifting upward relative to historical baseline (p90/baseline p90 ratio: 2.4)." This requires a template engine that maps feature names and z-scores to readable sentences — not trivial to build but enormously valuable for analyst adoption.

6. Validation
Before anything goes near a dashboard or a stakeholder, validate properly.
Sanity check on known cases. Take customers your financial crime team already knows are suspicious or have been exited. Do they score highly? If known bad actors are scoring in the 40th percentile, something is wrong. Take customers you're confident are clean and well-understood. Are they scoring low? This is your basic face validity test.
Peer group score distributions. Plot the score distribution within each peer group. They should roughly follow a right-skewed distribution with most customers scoring low and a small tail scoring high. If any peer group has a bimodal distribution or most customers scoring highly, the peer group definition or feature standardisation may be flawed.
False positive analysis. Take the top 5% of scorers and have a financial crime analyst review a sample. What proportion have a plausible explanation that the model couldn't know about (e.g. a construction company that legitimately works internationally)? This gives you your false positive rate and also tells you what additional context the dashboard needs to surface alongside scores.
Disparate impact testing. This is your governance requirement. Compute average anomaly scores by director nationality group, by geographic region, by business age. Check for systematic score elevation in any group that isn't explained by genuine behavioural differences. If businesses with directors of a particular nationality consistently score higher after controlling for SIC and turnover, your model has a bias problem. Document the results of this analysis regardless of outcome.
Stability testing. Run the model on your last 8 weekly snapshots and check that scores are stable for customers whose behaviour hasn't changed. High week-to-week score volatility for stable customers indicates the model is sensitive to noise. Compute the week-on-week correlation of scores for each customer — it should be high (above 0.8) for customers with stable behaviour.

7. Dashboard Build
Now you build the front end. You have validated scores, SHAP decompositions, and natural language explanations. The dashboard has three views as discussed earlier.
Population view. Scored universe with filtering by peer group, SIC, turnover band, score band, director nationality, date range, and any other customer attribute. Sortable by composite score and by individual score component. This is the thematic review replacement — an analyst filters to their population of interest and ranks by score.
Customer drilldown. For a selected customer: composite score and component breakdown, natural language explanation, peer group benchmarking charts (where does this customer sit on key features relative to their peer group distribution), time series of score and key feature values over the last 52 weeks, and network view showing connected entities via shared directors, addresses, and device IDs.
Alert management. Configurable score threshold above which customers appear as alerts. Analyst workflow to accept (normal — no action), escalate (refer for investigation or SAR consideration), or dismiss with mandatory rationale. All decisions logged with timestamp and analyst ID. This log is your feedback data for model improvement and your audit trail for governance.

8. Model Governance Documentation
Build this in parallel with the model, not after.
You need: model purpose and scope statement, peer group methodology and validation results, feature definitions data dictionary (every feature, how it's computed, what it signals, its missingness handling), training data description, model limitations (what it won't catch, what populations it's less reliable for), performance metrics, disparate impact analysis results, human-in-the-loop requirement statement, and a model monitoring plan.
The monitoring plan specifically needs to cover: weekly PSI on key features to detect distribution shift, monthly score distribution stability check, quarterly false positive rate review with analyst feedback, and an annual full model revalidation. Define the thresholds that trigger a model review or rebuild.

The Sequence in Short
Data quality and EDA → feature transformation → feature selection → model build (three parallel models) → ensemble scoring → explainability layer → validation → dashboard → governance documentation → production deployment → monitoring.
You're currently between steps 1 and 2. The feature table build you're doing now feeds directly into the transformation step. Once you have the full feature table built and validated, the modelling itself is relatively fast — the heavy work is in the data preparation and the explainability layer. Plan for the natural language explanation templating to take longer than you expect. It's the piece that most directly determines whether analysts actually use the tool.How long should a project like this realistically takeFeb 20Honest answer: longer than anyone will want to hear, but here's how to frame it realistically.
The Honest Timeline
End to end, done properly: 9 to 14 months.
That's for a single person with strong data skills working on this as a primary project, with reasonable access to data and stakeholder time. Not a side project. Not competing with BAU. Primary focus.
Here's how that breaks down.

Phase by Phase
Data access, understanding, and quality (6–10 weeks)
This always takes longer than expected and is the most underestimated phase in any financial crime analytics project. You're not just pulling data — you're understanding what the data actually represents, finding out that the SIC codes are 40% blank or miscoded, discovering that device IDs have a gap in 2022 because of a system migration, realising that international payments are in a different schema than you were told, and chasing data owners across multiple teams to get access signed off. Budget 8 weeks and be pleased if it's 6.
Feature engineering and pipeline build (8–12 weeks)
You're already in this phase. Building the transaction aggregation DataFrame properly, adding all the feature blocks discussed, handling edge cases (new customers, dormant customers, sparse windows), building the data quality flags, and validating every feature against known customers. This is largely technical execution once the design is clear but validation loops eat time. Every time you spot an anomaly in a feature distribution you'll need to trace it back to the raw data to determine whether it's a genuine signal or a pipeline bug. That cycle happens many times.
EDA, transformation, and feature selection (3–4 weeks)
Relatively fast if the pipeline is clean. Distribution analysis, correlation pruning, peer group validation, variance thresholding. The main time sink here is the peer group size validation and fallback hierarchy implementation if you find more sparse groups than expected.
Model build (3–5 weeks)
The actual modelling is not the longest phase. Isolation forest and autoencoder are not complex to implement. The time goes on hyperparameter tuning, ensemble weight calibration, and the first round of sanity checking scores against known customers. Expect several iterations where the initial scores look wrong and you trace the problem back to a feature transformation issue rather than the model itself.
Explainability layer (4–6 weeks)
Longer than most people plan for. SHAP computation at scale across 50,000+ customers weekly is not instant and needs optimisation. The natural language template engine is deceptively time-consuming to get right — edge cases, grammatical coherence, handling when the top driver is a missingness flag rather than a real feature. Getting this to a standard where analysts find it genuinely useful rather than confusing requires iteration with actual analysts.
Validation (3–4 weeks)
Face validity with known cases, disparate impact testing, stability testing, false positive rate analysis with analyst review. The analyst review part has external dependencies — you need their time, and financial crime analysts are busy. Schedule this early, don't treat it as a final step that can be compressed.
Dashboard build (4–8 weeks)
Highly variable depending on your technical stack and whether you're building in PowerBI, Tableau, a Python framework like Dash or Streamlit, or something else. A basic functional dashboard is fast. A polished, performant, analyst-friendly tool with drill-downs, network visualisation, time series charts, and alert management workflow takes significantly longer. Don't underestimate the alert management workflow — it's essentially a case management mini-application.
Governance documentation and model risk review (4–8 weeks)
Writing the documentation is 2–3 weeks if you've been documenting as you go. The model risk review process itself is outside your control — it depends on your bank's model risk team capacity and review cycle. In some banks this is 6 weeks. In others it's 6 months. Find out early what the process looks like because this can be the longest phase entirely due to organisational process rather than technical work.

What Will Actually Slow You Down
More than the technical work, these are the real schedule risks.
Data access and governance. Getting sign-off to access transaction data, device data, and exited customer data for this purpose may require data privacy review, legal sign-off, and potentially a legitimate interest assessment depending on your jurisdiction and internal policies. Start this process immediately — it runs in parallel with everything else but if you don't start it now it becomes a blocker later.
Stakeholder availability for validation. You need financial crime analyst time to sense-check scores. Analysts are busy. Getting 4 hours of their time across 3 weeks for a proper validation exercise requires scheduling months in advance in some teams.
Model risk review. As above — find out the process now. In a large bank, deploying any model that influences financial crime decisions will require formal model risk management sign-off. This process has its own timeline that you cannot compress.
IT deployment. If this needs to run on bank infrastructure rather than your laptop or a dev environment, getting compute resources provisioned, security reviewed, and a weekly pipeline scheduled can take months in some organisations. Again, start this conversation early.
Scope creep. Once stakeholders see an early version of the dashboard they will immediately want additions. New features, new filters, new score components, integration with case management systems. This is a sign of success but it's a timeline killer without active scope management.

How to Frame It to Stakeholders
Don't present a 12-month timeline without structure or they'll push back. Present it in three stages with delivery milestones at each.
Stage 1 — Proof of Concept (3 months). Feature pipeline for core transaction and customer blocks, basic isolation forest model on peer groups, simple dashboard showing scores and top driving features for a pilot population. This is enough to demonstrate value and get continued investment. Scope is limited: maybe 5 peer groups, 2 feature blocks, no autoencoder, no exited customer similarity, no network features.
Stage 2 — Production Model (months 4–8). Full feature set, all three model components, ensemble scoring, SHAP explainability, natural language explanations, full peer group coverage, complete dashboard with alert management workflow, governance documentation, model risk submission.
Stage 3 — Operationalisation and Enhancement (months 9–12). Model risk sign-off, IT deployment, analyst training, feedback loop implementation, first quarterly review, and the enhancement features: network graph visualisation, exited customer similarity refinement, additional feature blocks based on what the PoC revealed was missing.
This framing does several things. It gets something in front of analysts within 3 months which maintains momentum and buy-in. It separates the technical build from the organisational process (model risk, IT deployment) so delays in the latter don't make the project look stuck. And it gives you a clear scope boundary at each stage so you can push back on premature scope expansion.

The Number That Will Surprise People
Most financial crime analytics projects of this complexity, when done by a team rather than an individual, involve 3–5 people: a data engineer for the pipeline, a data scientist for the modelling, an analyst for domain validation, a front-end developer for the dashboard, and a project manager. That team working for 9 months is roughly equivalent to one strong person who can do all of it working for the same period — because handoffs, meetings, and coordination overhead consume a significant portion of team time.
If you're largely doing this solo, the timeline above is realistic. If you have team support, the calendar time can compress somewhat but rarely proportionally to headcount.There are other nuances that I'd like to be worked out. Multi-banked customers, shell companies, new customers without much history, and others (please identify and describe) - how should I handle these best?Feb 21These are some of the most important edge cases in the whole system because they're precisely the populations where financial crime risk is elevated but where your model is also most likely to either miss things or misfire. Let me go through each properly.

1. Multi-Banked Customers
The Problem
A business that banks with you and three other banks presents only a partial picture. Their transaction volume through your account may be small and unremarkable, but if you could see their full banking footprint they might be processing enormous volumes elsewhere. The classic financial crime use of multi-banking is to deliberately keep activity below thresholds at each individual bank while the aggregate picture is suspicious. Your model will score them as low anomaly because relative to their peer group they look quiet — but quiet is the disguise.
How to Detect It
The primary signal available to you without cross-bank data is the declared turnover to observed transaction volume ratio. A business declaring £5m annual turnover but processing only £200k through your account has an 96% gap. Some of that is explainable (they use your account for one specific purpose), but the gap itself is a feature worth computing explicitly.
Build: observed_annual_volume / declared_turnover. Values well below 1.0 warrant a flag. The threshold depends on your book — compute the distribution of this ratio across your population and flag customers below the 10th percentile within their peer group.
Secondary signals: accounts used almost exclusively for one transaction type (e.g. only receiving credits, never debiting, or only making international payments with no domestic activity). This partial account usage pattern suggests the customer is routing specific flows through you while doing their main banking elsewhere.
Handling in the Model
Create an explicit account_utilisation_score feature — the ratio of observed volume to declared turnover, log-transformed and peer-group standardised. Also create a transaction_type_breadth feature (entropy of transaction types used) — low entropy for an established business suggests partial account usage.
Flag customers with both low utilisation and low transaction type breadth as potentially multi-banked. Don't suppress their anomaly score — instead, ensure the model weights the utilisation gap feature appropriately and that the dashboard surfaces it prominently for analysts.
In the natural language explanation, if these features are top drivers, the template should explicitly say something like: "This business processes significantly less volume than its declared turnover would suggest, which may indicate banking activity is distributed across multiple institutions."

2. Shell Companies and Nominee Structures
The Problem
Shell companies are specifically designed to look normal on paper while obscuring the true nature of the activity or the beneficial owner. They often have clean, minimal transaction histories by design. A pure anomaly detection model trained on behavioural features may score them low precisely because their carefully managed behaviour is indistinguishable from a quiet legitimate business.
The risk here is the opposite of false positives — it's false negatives on high-risk entities.
Detection Signals
Shell company indicators don't come primarily from transaction behaviour — they come from the customer attribute and network layers.
Formation agent address — registered address matches a known company formation agent or virtual office provider. Maintain a lookup of known formation agent addresses and postcodes. This is a strong indicator and relatively easy to implement.
Director to activity ratio — a company with 6 directors, registered 4 years ago, with minimal transaction history and no declared employees is structurally suspicious for most SIC codes. Build a composite: director count divided by transaction volume divided by company age. Calibrate thresholds within peer groups.
Nominee director indicators — directors who appear across many companies in your book. A person who is a director of 15 different companies all banking with you is a nominee director pattern. This is a cross-customer network feature: compute for each customer the maximum and average number of companies in your book that share any director. High values are a strong shell company signal.
Company age to activity ratio — incorporated 5 years ago but has 3 months of transaction history. Where has the activity been? Either multi-banked, dormant shell now activated, or never genuinely trading. Flag the ratio of account history to company age.
Registered address country vs. operation — UK company with correspondence address abroad and international payments dominating the account. Not definitive but elevates concern in combination with other indicators.
SIC to activity coherence — a construction company with no payments to materials suppliers, no payroll patterns, no equipment-related transactions. The absence of expected transaction types for the SIC code is as informative as the presence of unexpected ones. Build expected transaction type profiles per SIC group and measure each customer's deviation from the expected profile.
Handling in the Model
Shell company indicators are mostly binary flags from the attribute layer rather than continuous behavioural features. Create a shell_indicator_score as a composite of the above flags — weighted sum normalised to 0–1. Feed this into the ensemble as an additional component or use it as a score multiplier: a customer with a high shell indicator score gets their anomaly score uplifted even if their behavioural features look normal.
This is important architecturally — pure behavioural anomaly detection will systematically underScore shells. The shell indicator composite explicitly corrects for this.

3. New Customers Without History
The Problem
You've touched on this but it needs a full treatment. A customer with 6 weeks of history has no meaningful 90-day, 180-day, or 360-day window. Their 30-day window is based on a handful of transactions. CoV computed on 4 transactions is statistically meaningless. Peer group percentile ranks based on sparse data are unreliable. The model genuinely cannot score these customers the same way it scores established customers.
The risk cuts both ways. New customers with genuinely suspicious activity may score low simply because there isn't enough data to detect a pattern. New customers with unusual but legitimate early-stage activity may score high because their sparse data looks volatile.
Handling
Create explicit model maturity tiers based on transaction history length and transaction count, not just account age.
Tier 1 is under 3 months or fewer than 20 transactions — insufficient for behavioural scoring. Don't run the main model on these customers. Instead, apply a dedicated new customer rule set: flag structuring patterns, flag immediate high-value international activity, flag rapid beneficiary accumulation. These are simple threshold rules not anomaly detection, but they're appropriate for the data available.
Tier 2 is 3–6 months or 20–60 transactions — partial scoring. Run the model but only on the features with sufficient data (30-day and 90-day windows where populated). Substitute peer group median for individual baseline where the individual baseline is unreliable. Flag all scores with a data confidence indicator so analysts know to interpret them cautiously.
Tier 3 is 6–12 months — approaching full scoring. Most features are computable but temporal change features are limited. Run the full model with a partial confidence flag.
Tier 4 is 12+ months — full scoring. All features available. Model operates as designed.
In the dashboard, make the maturity tier visible alongside every score. An analyst looking at a Tier 1 customer should immediately see that the score is rule-based, not model-based, and interpret accordingly.
The Onboarding Baseline Opportunity
New customers also represent an opportunity you should exploit. At onboarding, you have declared information: turnover, nature of business, expected transaction volumes, trading countries. Capture these explicitly and structured — not just as free text in a notes field. Then build features that compare actual early behaviour against declared expected behaviour. A business that declared it would process £100k monthly and is processing £2m in month one has a significant deviation from its own declared baseline. This is a powerful early signal that doesn't require historical data.

4. Dormant Accounts Reactivated
The Problem
An account that was dormant for 12–18 months and then suddenly reactivates is a known financial crime pattern — account takeover, front company activation, or a dormant shell being put to use. Your model's baseline was built on the dormant period, so when activity resumes, the model sees everything as anomalous relative to a near-zero baseline. This is correct in one sense — the activity is anomalous relative to history — but the score interpretation is different from a genuinely suspicious active customer.
Handling
Build an explicit dormancy_reactivation_flag — a binary feature that triggers when a customer has had fewer than 2 transactions per month for 6+ months and then exceeds a transaction count threshold in the current window.
When this flag is active, treat the customer as a hybrid new/existing customer. Suppress the historical baseline comparison features (they're meaningless against a dormant baseline) and instead apply the new customer rule set alongside whatever behavioural features the recent activity supports.
In the dashboard, surface the dormancy-reactivation flag prominently. An analyst should immediately see "this account was dormant for 14 months and reactivated 6 weeks ago" rather than just seeing a high anomaly score with confusing driver features.
Also compute: how does the post-reactivation behaviour compare to the pre-dormancy behaviour? If the account was used for domestic payments to a handful of suppliers before dormancy and is now making international payments to new countries, that divergence is a strong signal. Build a pre_post_dormancy_similarity_score using cosine similarity between the pre-dormancy and post-reactivation feature vectors.

5. Seasonal and Cyclical Businesses
The Problem
Businesses with genuine seasonality — tourism, retail around Christmas, agriculture, construction with weather dependencies — will show dramatic transaction volume changes across the year. A seaside hotel that processes 10x its winter volume in summer is not anomalous, it's seasonal. But your rolling window features will flag the summer uplift as anomalous relative to the annual baseline.
Handling
For customers with sufficient history (18+ months), fit a simple seasonal decomposition (STL decomposition works well) on their monthly transaction volume. Extract the seasonal component and use it to create a seasonality-adjusted anomaly — the residual after removing expected seasonal variation.
The adjusted feature for the model is: actual_volume - expected_seasonal_volume, standardised by the historical residual standard deviation. Anomalous behaviour is a large residual, not a large absolute value.
For customers without enough history for seasonal decomposition, use peer group seasonality. Compute the average seasonal pattern across the peer group and apply it to customers without individual seasonal baselines. A hotel that's new to your book gets the hotel-industry seasonal curve applied as its expected pattern.
In practice this means building a peer group seasonal index — for each peer group, compute the average ratio of each month's volume to the annual average. A peer group with a 2.3x July factor and 0.4x January factor has a strong seasonal pattern. Individual customer anomaly assessment adjusts for this expected variation.

6. Holding Companies and Group Structures
The Problem
A holding company whose sole purpose is to receive dividends from subsidiaries and distribute them to shareholders will have a transaction pattern that looks extremely anomalous to a model trained primarily on trading businesses. High value inflows, immediate high value outflows, very few counterparties, no payroll, no supplier payments. This is perfectly legitimate but will score highly on concentration, round number propensity, and pass-through velocity features.
Handling
SIC codes for holding companies (SIC 64202 in the UK) should form their own peer group with appropriate feature interpretation. Within this peer group, the high concentration and pass-through features are normal. The anomaly detection within the peer group then catches holding companies that deviate from the holding company pattern — for example, one that has many diverse counterparties rather than a small number of subsidiaries.
Additionally, build a group structure detection feature. If a customer shares directors with multiple other customers in your book who are all paying into the same account, that's a potentially legitimate group structure — but also a potential layering structure. The network feature captures this without distinguishing the two; the analyst judgement and business context determines which it is.

7. Recently Onboarded High-Risk SIC Codes
The Problem
Certain SIC codes are inherently higher risk — money services businesses, cryptocurrency exchanges, precious metals dealers, cash-intensive retail. When one of these onboards, the first few months of activity establish what will become their baseline. If they start with suspicious activity from day one, that activity becomes the baseline and later anomaly detection is calibrated against an already-suspicious baseline.
Handling
Apply enhanced scrutiny during the baseline establishment period for high-risk SIC codes. For the first 6 months of a high-risk SIC customer's life, apply tighter rule-based thresholds alongside the model, and flag the account for periodic human review regardless of model score. The baseline should only be considered established once a financial crime analyst has reviewed the activity profile and signed it off as acceptable.
Store a baseline_review_status flag per customer — unreviewed, reviewed-clean, reviewed-flagged. Customers in unreviewed status should be surfaced in the dashboard regardless of anomaly score until the baseline has been human-validated.

8. Businesses Undergoing Legitimate Structural Change
The Problem
A business that acquires another company, enters a new market, takes on a major new contract, or changes its primary banking relationship will show dramatic behavioural changes that are entirely legitimate. New counterparties, higher volumes, new countries, different transaction types. Your model will flag them correctly as changed — but changed for legitimate reasons.
Handling
This is fundamentally a false positive management problem rather than a feature engineering problem. You can't build a feature that distinguishes "legitimate business change" from "suspicious behaviour change" without external context — and that external context comes from the analyst review process.
What you can do is build change event markers into the dashboard. When a customer shows a significant director change, a registered address change, or a substantial jump in declared turnover (from a KYC refresh), surface these events on the customer's timeline in the drilldown view. The analyst seeing that a business added 3 new directors and doubled its transaction volume in the same month has very different context than one seeing the volume doubling without any structural change event.
Flag KYC refresh dates, director change dates, and address change dates as timeline events in your customer drilldown. These come from your customer data, not your transaction data, but they're essential interpretive context.

9. Customers With Exited Customer Connections
The Problem
A customer who is otherwise unremarkable but shares a director, address, device ID, or beneficiary with a customer previously exited for financial crime reasons deserves elevated scrutiny regardless of their own behavioural score. The network contamination is itself a risk signal that pure behavioural anomaly detection won't surface.
Handling
Build a network_contamination_score — a composite of: number of direct connections to exited customers (via director, address, device, beneficiary), degree of separation (direct connection scores higher than second-degree), and recency of the exited customer's exit (recent exits are more relevant than historical ones).
This score should function as a floor on the composite anomaly score. A customer with a high network contamination score should never score below a defined threshold regardless of how normal their behaviour looks. In the dashboard, surface the specific connections — "this customer shares a director with [anonymised reference] who was exited in March 2023 for [reason category]."

10. High Cash Proxy Businesses
The Problem
Businesses that are nominally non-cash but exhibit cash-proxy behaviours — nail bars, car washes, convenience stores with unusually high card terminal receipts — are a well-known typology. Your transaction data may not contain actual cash transactions (those happen outside your book) but you can see proxy signals.
Handling
Build a cash_intensity_index — a composite of: proportion of credits coming from card payment aggregators (high for cash-front businesses), consistency of daily credit amounts (genuine card businesses often show more variability than inflated ones), and ratio of credit volume to expected business size for the SIC code. A nail bar processing £50k of card receipts monthly is at the high end for its SIC and peer group. The anomaly within the peer group flags it rather than a general rule.

The Overarching Principle
For each of these edge cases, the handling follows the same logic. Identify whether the edge case causes the model to under-score risk (multi-banked, shells, new customers, network contamination) or over-score legitimate behaviour (seasonal businesses, structural changes, holding companies). Under-scoring cases need supplementary signals or score floors. Over-scoring cases need contextual adjustment or analyst-visible explanatory markers. Neither should result in suppressing the customer from the model entirely — they should result in more nuanced, better-contextualised scores that analysts can interpret correctly.We don't get to see declared turnover as it's only for limited companies and bigger (and the data is for a historical period where they could file 9 months later). What's the approach for Sole traders who multi bank, assuming no declared turnover value... (Unless you know where I can get it)Feb 21Good challenge. This is a real data gap and it affects a significant portion of your book. Let me work through it properly.
The Declared Turnover Problem First
For limited companies you're right that Companies House filing lag makes declared turnover largely useless as a real-time signal — a 2023 filing might reflect 2022 trading, and micro-entity accounts don't even require a profit and loss statement. So even where you have it, treat it as a rough order-of-magnitude anchor rather than a precise figure.
For sole traders there's no filing requirement at all. They're invisible to public data sources. HMRC has their Self Assessment data but you can't access it. Credit reference agencies have some sole trader data but coverage is patchy and it's often derived from the same limited sources you already have.
So practically speaking, treat declared turnover as unavailable for the majority of your book and build your approach without relying on it. The limited company filed accounts become a useful supplementary enrichment where available, not a core feature.
For limited companies specifically, Companies House is your best free source. You can access it via their API or bulk download. Filed turnover, net assets, SIC code, director history, filing dates, and registered address are all available. Build a Companies House enrichment pipeline that joins on company registration number — which you should have at onboarding for limited companies. The filing lag issue means you use it for order-of-magnitude banding rather than precise comparison, and you flag the filing date so you know how stale it is.

The Sole Trader Multi-Banking Problem
Without declared turnover, your primary tool for detecting multi-banking is inferring expected activity from observable proxies and flagging where observed activity falls significantly below that expectation.
The core principle shifts from:
"Observed volume vs declared turnover"
To:
"Observed volume vs inferred expected volume given everything else we can observe"
Here's how to build that inference.
Peer Group Expected Volume
Within your sole trader peer groups (SIC division × whatever banding you can create without turnover), compute the distribution of observed transaction volumes across the population. For a given peer group — say sole trader plumbers — you have a distribution of monthly transaction volumes across all your sole trader plumbers.
A sole trader plumber in the 5th percentile of transaction volume within that peer group is either very small, very part-time, or routing most of their banking elsewhere. You can't distinguish these from transaction data alone, but the percentile rank itself is a feature. Persistently low volume within peer group, combined with other signals, builds a multi-banking picture.
The key is that this is relative to peers with similar characteristics, not against a declared figure. It's imprecise but it's what you have.
Account Behaviour Completeness
For a sole trader running their business through a single account, you'd expect to see a relatively complete picture of a trading business: regular credits from customers or card aggregators, regular debits to suppliers, some evidence of personal drawings or salary equivalent, HMRC payments (VAT, income tax self assessment — these are particularly useful because most trading sole traders pay tax), and utility or overhead payments consistent with operating a business.
Build an account completeness score — how many of these expected transaction categories are present? A sole trader with credits only and no debits, or with no HMRC payments ever despite years of account history, has an incomplete picture of a trading business. This suggests either a very unusual legitimate business model or that the account is being used for a specific subset of their banking while the rest happens elsewhere.
The categories to check for presence or absence:
Credits from multiple sources (not just one payer — a sole trader with all credits from a single source might be an employee misclassified, or might be using this account as a collection account only). Supplier payments (any debits that look like business costs). HMRC or DVLA payments (VAT returns, tax payments — these are identifiable by beneficiary). Personal drawings pattern (regular transfers to what appears to be a personal account — common for sole traders managing cash flow). Business overhead payments (insurance, utilities, rent or lease payments).
Score each category as present or absent, weight them by importance, and sum to a completeness score. Low completeness combined with low peer-relative volume is your multi-banking indicator for sole traders.
Credit-to-Debit Ratio as a Multi-Banking Signal
For a sole trader using one account for everything, credits and debits should roughly balance over time — money comes in from customers, money goes out to suppliers, HMRC, drawings. A credit-to-debit ratio persistently above 1.3 or 1.4 (significantly more money coming in than going out) suggests outflows are happening elsewhere. They're receiving income into your account but spending through another bank.
This is not definitive — some businesses genuinely accumulate surplus — but in combination with low peer-relative volume and low account completeness, it becomes a meaningful composite signal.
Transaction Regularity vs Volume Mismatch
A sole trader doing genuine low volume will typically have both low transaction count and low transaction value — the two move together. A multi-banking sole trader often has a specific pattern: reasonable transaction count (they're actively using the account) but low total value (because the big transactions happen elsewhere). Or conversely, low count but reasonable value (they use this account for specific high-value flows only).
Build a feature for the ratio of transaction count percentile rank to transaction value percentile rank within peer group. A customer who is at the 40th percentile for count but the 8th percentile for value has a mismatch — they're transacting a normal frequency but at unusually low values compared to peers. This mismatch is a multi-banking signal.
Open Banking as a Future Option
This is where the most accurate answer to your problem actually lives. If your bank has open banking capabilities and customers have consented, you can see their accounts at other institutions. This directly solves the multi-banking detection problem — you can observe their full banking footprint rather than inferring it.
For new customer onboarding, some banks are beginning to use open banking data as part of KYC and affordability checks for business customers. If your bank has this capability or is building it, pushing for sole trader open banking data ingestion into your financial crime analytics pipeline is the highest-value data investment you could make for this specific problem. It transforms multi-banking detection from inference to observation.
Even without a formal integration, if your bank already holds open banking data for some customers (perhaps from a lending or onboarding process), that data should flow into your feature engineering pipeline.
Behavioural Consistency as a Proxy for Account Completeness
Legitimate sole traders who use one account for everything tend to show diverse, consistent, operationally coherent transaction patterns — a plumber who pays a parts supplier weekly, receives customer payments via bank transfer and card, makes quarterly VAT payments, and draws a regular personal salary equivalent. The pattern hangs together as a coherent business picture.
A sole trader using your account for only part of their banking shows a partial, sometimes incoherent pattern — perhaps only one type of transaction, or credits with no corresponding operational debits, or operational debits with no corresponding credit income. The incoherence is detectable even without knowing what the full picture should look like.
Build a transaction coherence feature — for each SIC code, characterise the expected mix of transaction types and beneficiary categories that a typical business in that SIC should show. Measure each customer's deviation from that expected mix. Low coherence is a flag for further investigation and is particularly powerful for sole traders where no external turnover reference exists.

Pulling It Together for Sole Traders
Your multi-banking indicator for sole traders becomes a composite of five signals rather than the single declared-vs-observed turnover ratio you'd use for larger entities:
Peer-relative transaction volume percentile (persistently low within peer group), account completeness score (which expected transaction categories are missing), credit-to-debit ratio (significantly above 1 suggests outflows elsewhere), count-to-value percentile mismatch (transacting at normal frequency but low values), and transaction coherence score (does the observable pattern hang together as a complete business picture).
No single signal is definitive. The composite is what builds a picture. A sole trader who is low on all five is a strong multi-banking candidate. A sole trader who is low on one or two probably has a legitimate explanation.
In the dashboard, surface these five components separately rather than just the composite — an analyst investigating a sole trader needs to understand which specific elements of the picture are incomplete, not just that a composite score is elevated. "This customer has no HMRC payments in 3 years of account history and processes 80% less volume than peer group median" is actionable. A composite score of 0.73 is not.I already have all the data. There are 3 analysts doing this, I'm the lead, looking at customer data and transaction data. Analyst 2 is looking at devices, and analyst 3 is looking international payments. I've clearly got the most work but I'm building it and am faster, and able to dedicate more time to it. We're planning to build the feature base dataset in about 4-6 weeks, and spend about 6 weeks doing ml and updating the features, and then deliver a looker core dashboard (analyst 2). My manager wants a team work approach but I think it slows down the process, but good for CV as I can say I've led ai ml teams... Critique timelines, thoughts, and planFeb 23This is a realistic and well-structured plan, but there are some things worth being direct about.
Timeline Critique
4–6 weeks for the feature dataset is tight but achievable with your setup. The critical path is your block — transaction aggregation is the foundation everything else joins to. If your transaction pipeline slips, analysts 2 and 3 are blocked because their features need to join to your customer-transaction base. Make sure you've agreed on the join keys, granularity, and output schema with them before anyone writes a line of code. A week spent aligning on the data contract upfront saves three weeks of rework later.
6 weeks for ML and feature iteration is too compressed. This is where most projects underestimate. The first model run will produce results that look wrong. Tracing whether wrong means bad model, bad features, or bad data takes time. One iteration cycle — run model, review scores, trace anomalies, fix features, rerun — realistically takes 2 weeks per cycle. You'll need at least 2-3 cycles. That's 4-6 weeks minimum just for iteration, before you've touched explainability or validation. I'd push this to 8-10 weeks or explicitly scope the first delivery as a prototype score with known limitations rather than a production model.
Looker dashboard in parallel with ML is the right call but analyst 2 needs a stable feature schema before building dashboards against it. If your features are still changing in week 8, the dashboard built on week 6 schemas breaks. Agree a feature freeze date — probably end of week 6 — after which new features go into v2 not v1. Analyst 2 builds against the frozen schema.
Total timeline: you're looking at 14-16 weeks realistically, not 10-12. That's roughly 4 months to a working v1. Which is actually fast for a project of this complexity, so frame it as an achievement not a failure.

The Team Structure Problem
You're right that it slows things down and you're right to be frustrated, but the reason is probably not what you think.
The slowdown isn't three people instead of one — it's coordination overhead and dependency management. Analyst 2 can't finalise device features until they know the customer ID schema you're using. Analyst 3 can't build the country risk weighted features until they know how you're handling the window logic. These dependencies mean you're effectively the bottleneck for the whole team whether you want to be or not.
The productive framing is to front-load the coordination rather than letting it interrupt the build phase. Spend the first week producing a proper technical specification: agreed schema for the feature table, column naming convention, window definitions, how nulls are handled, what the join keys are, what the output format is. Everyone builds to that spec independently. You review their outputs before they join to the main table. This is faster than ad-hoc coordination throughout.
The honest challenge on teamwork. Three people building three separate feature blocks that need to join cleanly into one table is not really a team ML project — it's parallel feature engineering with a join at the end. The actual ML is one person's work (yours). The Looker dashboard is one person's work. For it to genuinely be a team ML project in a way that's meaningful rather than just title-deep, you'd want analysts 2 and 3 involved in model validation, score interpretation, and feature selection decisions — not just data preparation. That also makes the CV claim more defensible if anyone probes it.

The CV Point — Being Direct
Leading a team that builds an anomaly detection ML system for financial crime is genuinely strong. But the claim is most defensible if you can articulate what each person contributed and how you coordinated the technical decisions. If the honest answer is "I built the model, analyst 2 built the device features, analyst 3 built the international features, and we joined them together" — that's fine, that's real, and it's leadable. The risk is overclaiming coordination complexity that wasn't there, because anyone technical who interviews you will probe the team dynamics and model decisions in detail. Be able to answer: how did you handle disagreements on feature definitions, how did you validate the joined dataset for consistency, how did you ensure analyst 2 and 3's features met the quality bar needed for the model. Those are real leadership questions and if you can answer them honestly you don't need to embellish.

What I'd Actually Do in Your Position
Week 1: Technical specification document. Schema, naming convention, window definitions, join keys, null handling, output format. Get everyone aligned and signed off before any code is written. This document also becomes part of your governance artefact.
Weeks 2-5: Parallel build. You on transaction and customer features. Analyst 2 on device. Analyst 3 on international. Weekly 30-minute sync to flag blockers. You review their feature outputs against the spec at the end of week 4.
Week 6: Integration and data quality. Join all three feature blocks. Run the full data quality audit. Fix issues. Feature freeze for v1 at end of week 6. Analyst 2 starts Looker build against frozen schema.
Weeks 7-14: ML build and iteration. You own this largely solo. First model run week 8. First score review with a financial crime analyst week 9-10. Two more iteration cycles. Explainability layer week 12-13. Validation week 13-14.
Weeks 14-16: Dashboard finalisation, governance documentation, stakeholder review.
That's a 16-week plan with realistic buffers. Present it as 4 months to v1, with v2 enhancements (network features, exited customer similarity, refined explainability) in a subsequent phase. That framing is honest, defensible, and still impressive.So what's best for setting up week 1. Customer number by week as the unique identifier, how to handle everything else?
How can I do the coordination if the other analysts don't proactively engage and discuss - they're like a ticket analyst team in another countryFeb 23This is a very common problem and the offshore/ticket-mentality dynamic makes it significantly harder. Let me deal with both the technical setup and the coordination problem separately.

Week 1 Technical Setup
The Unique Identifier
Customer number by week is the right primary key but be precise about what "week" means before anyone writes a line of code.
Your key should be:
customer_id | computation_date
Where computation_date is always a Sunday, always a specific date (2024-03-17, not "week 11"), and always the end of the observation window — every window trails back from this date. Never use week numbers — they're ambiguous across years and across teams in different countries who may use ISO week numbering differently.
Make this explicit in the spec:
Primary key: (customer_id, computation_date)
computation_date: DATE, always Sunday, format YYYY-MM-DD
Window logic: all windows trail backwards from computation_date inclusive
Example: computation_date = 2024-03-17, w30 covers 2024-02-16 to 2024-03-17
Everyone on the team uses this definition. No exceptions. If analyst 2 builds device features keyed on customer_id and calendar month, the join breaks and you won't always notice immediately.
The Master Spine Table
Before any features are built, create a spine table. This is the scaffolding everything else joins to. It contains nothing but valid combinations of customer IDs and computation dates.
python# Every customer × every Sunday in your 2-year window
# This is the ground truth of what rows should exist

spine = pd.DataFrame({
    'customer_id': [...],  # all active customers
    'computation_date': [...]  # all Sundays in range
})
```

Every analyst builds their feature block and **left joins back to this spine**. The spine never changes. If a customer has no device data for a given week, they still have a row in the spine — analyst 2's join produces nulls for that row, which is correct and handled by your null strategy. If analyst 2 produces a table that has different rows than the spine, something is wrong in their pipeline.

This is the single most important coordination tool you have. The spine is the contract. Everyone builds to it.

### Null Handling — Agree This Now

Establish four explicit null categories and how each is handled:

**True zero** — the customer had activity but the metric was genuinely zero. Encode as 0. Example: zero international payments in a window.

**Structural null** — the customer cannot have this feature by definition. A customer with no digital banking cannot have device features. Encode as NULL with a corresponding `_flag` column set to 2 (missing by structure).

**Sparse null** — the customer has some data but not enough to compute a reliable feature. Fewer than 5 transactions in a 30-day window makes CoV unreliable. Encode the value anyway but set the `_flag` column to 1 (sparse, treat with caution).

**Missing null** — data should exist but doesn't, due to a pipeline or data quality issue. These should be caught in your QA process and resolved, not encoded silently.

Document this in the spec with examples. Analyst 2 and 3 need to apply the same logic to their blocks. If they encode structural nulls as zero, a customer with no device data gets a device count of zero which the model treats as genuinely having zero devices — a very different thing.

### Column Naming Convention

Establish this in week 1 and enforce it. As discussed earlier:
```
{block}_{metric}_{direction}_{window}d
{block}_{metric}_{direction}_{window}d_flag  # data quality flag
```

Block prefixes:
- `txn_` — transaction features (you)
- `cust_` — customer attributes (you)  
- `dev_` — device features (analyst 2)
- `intl_` — international payment features (analyst 3)
- `delta_` — change features derived from panel
- `ratio_` — cross-window ratio features
- `net_` — network features
- `sim_` — exited customer similarity features

Examples:
```
txn_value_total_credit_30d
txn_value_total_credit_30d_flag
dev_distinct_count_30d
dev_distinct_count_30d_flag
intl_country_risk_wtd_90d
intl_country_risk_wtd_90d_flag
```

Tell analysts 2 and 3 explicitly: if your column doesn't follow this convention it won't be accepted into the main table. That sounds harsh but it's the only way to maintain a coherent 400-column dataset built by three people.

### Output Specification for Each Analyst

Each analyst produces **one output table** with a defined schema. Not multiple tables, not a folder of CSVs with different date formats. One table.

**Analyst 2 — Device features output spec:**
```
customer_id: STRING, not null
computation_date: DATE, not null, always Sunday
dev_distinct_count_30d: INTEGER, nullable
dev_distinct_count_30d_flag: INTEGER, not null, values 0/1/2
dev_distinct_count_90d: INTEGER, nullable
dev_distinct_count_90d_flag: INTEGER, not null, values 0/1/2
dev_new_device_rate_30d: FLOAT, nullable
dev_new_device_rate_30d_flag: INTEGER, not null, values 0/1/2
dev_shared_customer_count_30d: INTEGER, nullable
dev_shared_customer_count_30d_flag: INTEGER, not null, values 0/1/2
[... full list of agreed device features]
Primary key: (customer_id, computation_date) — no duplicates
Row count: must match spine exactly
```

**Analyst 3 — International features output spec:**
```
customer_id: STRING, not null
computation_date: DATE, not null, always Sunday
intl_country_count_30d: INTEGER, nullable
intl_country_count_30d_flag: INTEGER, not null, values 0/1/2
intl_value_total_30d: FLOAT, nullable
intl_value_total_30d_flag: INTEGER, not null, values 0/1/2
intl_country_risk_wtd_30d: FLOAT, nullable
intl_country_risk_wtd_30d_flag: INTEGER, not null, values 0/1/2
[... full list of agreed international features]
Primary key: (customer_id, computation_date) — no duplicates
Row count: must match spine exactly
Give them the spine table. Tell them to join their output back to it and verify the row count matches before submitting.
Validation Checks to Define Now
Define what "done" means for each block. Each analyst runs these checks before handing over their table:
python# Check 1: Row count matches spine
assert len(feature_table) == len(spine)

# Check 2: No duplicate primary keys
assert feature_table.duplicated(['customer_id', 'computation_date']).sum() == 0

# Check 3: computation_date is always Sunday
assert (feature_table['computation_date'].dt.dayofweek == 6).all()

# Check 4: Flag columns contain only 0, 1, 2
flag_cols = [c for c in feature_table.columns if c.endswith('_flag')]
for col in flag_cols:
    assert feature_table[col].isin([0, 1, 2]).all()

# Check 5: No column naming violations
expected_prefixes = ['dev_', 'intl_', 'txn_', 'cust_']
for col in feature_table.columns:
    if col not in ['customer_id', 'computation_date']:
        assert any(col.startswith(p) for p in expected_prefixes)

# Check 6: Value ranges are plausible
assert feature_table['dev_distinct_count_30d'].max() < 1000  # sanity cap
```

These checks run automatically. If they fail, the table is not accepted. This removes the subjective element from handover quality and gives you a mechanical basis for rejection that isn't personal.

---

## The Coordination Problem

This is harder than the technical problem and more important to solve in week 1.

The ticket-analyst dynamic you're describing — offshore, reactive, waiting for instructions rather than engaging — means you cannot rely on them to flag problems, ask questions, or surface blockers proactively. In that context, **your coordination approach has to assume zero proactive communication and design around it.**

### Accept the Dynamic, Don't Fight It

Trying to change a ticket-team culture through enthusiasm or expectation-setting rarely works, especially remotely and especially when they report to their own management structure. Don't spend political capital trying to make them engage differently. Instead, design a process where their natural ticket-response behaviour produces what you need.

### Convert Everything to Tickets

If they work best responding to specific, bounded requests, give them specific, bounded requests. Don't send "here's the project overview, let's align on approach." Send "here is the spine table, here is the output schema for device features, here are the 6 validation checks your table must pass, please confirm you can deliver by [date]." That's a ticket. They'll respond to it.

Structure your week 1 output as a package of clear deliverables:

A technical specification document (PDF or Confluence page, not a Word doc in someone's email). The spine table in whatever format they can access (shared database table, S3 path, shared drive CSV). The output schema for their specific block as a template table — literally an empty table with the right columns and dtypes that they populate. The validation script they run before handover. A single point of contact for questions (you) with a defined response SLA.

Send this as a single communication. Not a meeting request. Not a discussion. "Here is everything you need to build your feature block. Deadline is [date]. Run the validation script before handover. Questions to me."

### The Weekly Sync — Make It Asynchronous

A weekly meeting with offshore analysts who don't proactively engage will be a silent, unproductive 30 minutes. Replace it with a **weekly written status update template** that you send to them and they fill in and return.
```
Week [X] Status Update — [Analyst Name]

Features completed this week: [list]
Features in progress: [list]
Blockers: [list or 'none']
Questions: [list or 'none']
On track for [date] deadline: [yes / no / at risk]
Validation checks passing: [yes / no — attach output]
They fill this in and return it to you by a fixed day (Friday). You review it. If there are blockers or questions you respond immediately. If there are none, you have documented evidence of progress. If they stop returning it, you have documented evidence of non-engagement which protects you.
This format works with ticket-mentality teams because it's a ticket — a bounded, specific request with a clear response format.
Front-Load All Decisions Into the Spec
Every decision you leave open is a question they'll either ask at the wrong time or silently get wrong. Go through your feature spec and identify every point where a reasonable person could make a different choice: how to handle customers with no transactions in a window, what to do when a device ID appears for the first time, whether to include or exclude certain transaction types, how to handle customers who appear mid-way through the 2-year history. Decide all of these yourself, document them in the spec, and present them as decisions already made. Don't ask for input — you'll get silence. Make the decision, document it, and tell them to implement it.
Protect Yourself on Dependencies
You are blocked if their feature blocks aren't delivered on time and to spec. That's a project risk you need to manage explicitly.
For the ML phase, you don't actually need their feature blocks — you can build and test the model on your transaction and customer features alone. Device and international features enrich the model but don't gate it. Structure your plan so the ML starts on your features in week 7 regardless of whether analyst 2 and 3 have delivered. Their features integrate in week 9-10 as an enrichment step.
This means a delayed delivery from them delays the enrichment, not the model. Communicate this dependency structure to your manager explicitly — "I can start the model on schedule, device and international features integrate at week 9, any delay in those blocks affects enrichment not core delivery." This protects your timeline and puts the dependency consequence in the right place.
The Manager Wants Teamwork — Give Them the Appearance and the Reality
Your manager wants to see collaboration. Give them visible collaboration: a shared technical spec document, a weekly status update summary you compile from the three analysts' returns and share upward, a joint delivery narrative. These are real — the spec is a real collaboration artefact, the status updates are real progress tracking.
The reality is that you're doing the intellectual heavy lifting and the coordination. That's fine and it's true of most data science lead roles. The important thing is that the team's outputs are coherent, the delivery is on time, and everyone's contribution is documented. Your manager sees teamwork. You deliver a working system. Analysts 2 and 3 have clear tasks with clear deadlines. Everyone gets what they need.
The leadership skill you're actually demonstrating — and this is genuinely CV-worthy — is technical coordination across a distributed team with low proactive engagement. That's a real and common challenge in financial services data science. Being able to design a process that produces coherent outputs from that team structure is more impressive than a team that naturally collaborates well.What about the ml part, how can I have and instil a teamwork with enough work for everyone when I guess I'm doing most of the work myself. I don't want it to be a teaching thing when I'm learning it as I go myselfFeb 23This is the most honest question you've asked and it deserves an honest answer.
The Reality First
The ML phase is largely a solo endeavour by nature. You can't meaningfully parallelise model architecture decisions, hyperparameter tuning, ensemble design, or SHAP implementation across three people — especially when those people are ticket-responders without ML background. Trying to divide the core modelling work will produce inconsistency, integration overhead, and the kind of teaching burden you're explicitly trying to avoid.
So accept that upfront rather than constructing artificial parallelism that everyone can see through. The question becomes: what genuinely useful, non-trivial work can analysts 2 and 3 do during the ML phase that contributes to the project without requiring you to teach ML or pretend their contributions are more central than they are.

What Analysts 2 and 3 Can Actually Do
Analyst 2 — Validation and Ground Truth Building
This is genuinely important work that requires domain knowledge, not ML knowledge, and it directly improves the model.
Known case labelling. Give analyst 2 a sample of 200-300 customers from the scored population — a mix of customers the team has previously reviewed, customers who were exited, customers who were cleared, and a random selection of unknowns. Their job is to assign a label to each: known suspicious, known clean, unknown. This becomes your ground truth dataset for validating whether the model scores correlate with actual financial crime risk. This is real analytical work, it uses their domain expertise, and the output is something you genuinely need.
False positive review. Once you have first model scores, analyst 2 takes the top 10% of scorers and reviews a sample against their case knowledge and the available customer information. They document: does this score make sense, what's the plausible explanation, what information would change the assessment. This feedback directly informs feature iteration and threshold calibration. It's structured, bounded, and produces a deliverable — a reviewed sample with analyst notes.
Peer group sense-checking. Analyst 2 reviews the peer group assignments for a sample of customers. Do the peer group members look like genuine peers? Are there obvious misassignments — a holding company grouped with trading businesses, a dormant account treated as active? This requires business knowledge not ML knowledge, and the output (a list of flagged misassignments with rationale) is a real input to your model.
Analyst 3 — Country Risk and Typology Reference Data
Country risk taxonomy. If your bank doesn't have a formally maintained country risk scoring table, analyst 3 builds one. FATF lists, Basel AML Index, Transparency International CPI, OFAC/HMT sanctions lists — compiling these into a single scored lookup table by country and jurisdiction is real, valuable, non-trivial work. It's a reference dataset the international payment features depend on and it needs maintaining.
Typology mapping. Analyst 3 documents the key financial crime typologies relevant to your book — trade-based money laundering, third-party payment patterns, structuring, smurfing, specific sector risks. For each typology, they map which features in your feature table are theoretically most relevant. This becomes the basis for your SHAP grouping logic and your natural language explanation templates. It's domain work, not ML work, and it produces a real artefact.
Exited customer review. Analyst 3 reviews the exited-for-FC customer population and documents: what were the common patterns, what typologies were present, what features would have flagged them. This directly informs the exited customer similarity component of your model and doesn't require ML knowledge — it requires reading historical case files and extracting patterns.

What You're Doing
Be clear in your own head about the division even if you don't broadcast it.
You're doing: the model architecture, the feature transformation and selection, the isolation forest and autoencoder implementation, the ensemble scoring, the SHAP computation, the natural language template engine, the overall pipeline, and the integration of all feature blocks. That's the project. That's the ML.
Analysts 2 and 3 are doing: domain validation, reference data, ground truth labelling, and false positive review. That's genuinely necessary supporting work and it's the work that makes the ML outputs meaningful rather than technically correct but operationally useless.

How to Frame This to Your Manager
Don't frame it as "I'm doing the ML, they're doing supporting work." Frame it as a genuine division of labour that reflects the team's expertise:
"The ML build is structured so the modelling and engineering is centralised for consistency and governance — you can't have three people making independent decisions on model architecture. The validation and domain expertise work is distributed because that's where analyst knowledge adds most value. Analyst 2 is building the ground truth and running the validation review. Analyst 3 is building the country risk framework and typology mapping. These inputs directly shape the model outputs."
That's accurate, it's not embellished, and it describes a real team structure with a legitimate rationale.

The Learning-As-You-Go Problem
This is worth addressing directly because it's the part that creates the most anxiety.
You're learning ML as you build a production financial crime model. That's actually fine and more common than people admit. The risks are specific and manageable rather than general.
The real risks are: implementing something incorrectly and not knowing it's wrong, making a modelling decision without understanding its implications, and being unable to defend your choices under scrutiny from model risk or a technical interviewer.
The mitigations are specific:
Document every decision with a rationale as you make it. Not to show anyone — for yourself. "I chose contamination=0.05 for the isolation forest because I want a tight definition of normal given false positive cost. Alternative was 0.1 which would flag more customers." Writing the rationale forces you to understand the decision and gives you the answer when someone asks.
For each component — isolation forest, autoencoder, SHAP — spend one focused day reading the actual paper or primary documentation before implementing. Not tutorials, not Medium articles. The scikit-learn isolation forest documentation is thorough. The SHAP documentation and Lundberg's original paper are readable. Understanding the mechanism at first principles means you can explain and defend it. This is maybe 3-4 days of reading across the whole ML phase, not weeks of study.
Test everything on a subset you understand. Before running the isolation forest on 50,000 customers, run it on 50 customers you know well. Look at who scores highest. Does it make sense? If a customer you know is clean scores highest, trace why — which features drove it. This is how you catch implementation errors before they propagate.
Use the validation phase honestly. When analyst 2 reviews the top scorers against their case knowledge, the false positives aren't just model outputs to calibrate — they're your signal about whether the model is working correctly. Take that feedback seriously.
The thing not to do is implement something you don't understand at all and hope no one probes it. That's where people get caught. If you genuinely don't understand why the autoencoder bottleneck layer works the way it does, either spend a day understanding it or use a simpler anomaly detection method you do understand and can defend. A well-implemented and well-understood isolation forest is better than a poorly understood autoencoder. The model risk reviewer will ask you to explain your architecture choices. "I followed a tutorial" is not a defensible answer. "I chose this architecture because the bottleneck forces the model to learn a compressed representation of normal behaviour, and reconstruction error identifies customers whose behaviour can't be compressed into that representation — indicating they don't fit the learned normal pattern" is.

The Honest Summary
The team structure during ML is: you build, they validate and enrich. That's legitimate, it's how many real data science teams work, and the validation work is genuinely valuable. Don't construct fake parallelism in the modelling itself — it'll create more problems than it solves.
On learning as you go: the answer is to learn deliberately rather than accidentally. Understand what you're building well enough to explain and defend every decision. That's a higher bar than following tutorials but a lower bar than being an ML expert before you start. You're clearly capable of reaching it based on the questions you've been asking throughout this conversation — you've been thinking at the right level of depth throughout.How can I algorithmically build peer groups from sic (2 or 6) and credit turnover bandsFeb 24Good question. Rather than manually defining peer groups, let you the data tell you where the natural boundaries are. Here's how to do it properly.

The Core Approach
You're solving two sub-problems simultaneously. First, what level of SIC granularity actually produces behaviourally distinct groups. Second, where the natural turnover band boundaries lie in your actual data rather than imposing arbitrary ones.
The algorithm should answer both empirically rather than by assumption.

Step 1 — Prepare the Input Data
Before any algorithm runs, you need a customer-level summary table with the variables you're grouping on plus the behavioural features you want the groups to be homogeneous on.
pythonimport pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder
from scipy.stats import f_oneway
from sklearn.tree import DecisionTreeClassifier
import matplotlib.pyplot as plt
import seaborn as sns

# Customer summary - one row per customer
# Use your most recent complete 360d window as the behavioural reference
customer_summary = pd.DataFrame({
    'customer_id': [...],
    'sic_2digit': [...],      # first 2 digits of SIC
    'sic_6digit': [...],      # full SIC code
    'observed_annual_volume': [...],  # sum of all transaction value in 360d window
    # Key behavioural features you want homogeneous within groups
    'txn_value_total_360d': [...],
    'txn_cov_credit_360d': [...],
    'intl_pct_value_360d': [...],
    'cpty_hhi_debit_360d': [...],
    'txn_count_total_360d': [...],
})
Note you're using observed_annual_volume rather than declared turnover. This is your proxy for business size and it's derived entirely from what you can see. Log-transform it immediately — the distribution is heavily right-skewed.
pythoncustomer_summary['log_observed_volume'] = np.log1p(
    customer_summary['observed_annual_volume']
)

Step 2 — Determine SIC Granularity Empirically
The question is whether 2-digit SIC explains significantly more behavioural variance than no SIC grouping, and whether 6-digit SIC explains significantly more than 2-digit. Use a variance decomposition approach.
pythondef compute_variance_explained(df, group_col, feature_cols):
    """
    For each feature, compute the ratio of between-group variance 
    to total variance. Higher = group_col explains more of the 
    behavioural variation in that feature.
    """
    results = {}
    
    for feature in feature_cols:
        # Drop nulls for this feature
        valid = df[[group_col, feature]].dropna()
        
        # Total variance
        total_var = valid[feature].var()
        
        if total_var == 0:
            results[feature] = 0
            continue
        
        # Between-group variance
        group_means = valid.groupby(group_col)[feature].mean()
        overall_mean = valid[feature].mean()
        group_sizes = valid.groupby(group_col)[feature].count()
        
        between_var = (
            (group_sizes * (group_means - overall_mean) ** 2).sum() 
            / len(valid)
        )
        
        results[feature] = between_var / total_var
    
    return pd.Series(results)

behavioral_features = [
    'txn_value_total_360d',
    'txn_cov_credit_360d', 
    'intl_pct_value_360d',
    'cpty_hhi_debit_360d',
    'txn_count_total_360d'
]

# Compare variance explained at each SIC level
ve_nosic = compute_variance_explained(
    customer_summary, 'sic_2digit', behavioral_features
) * 0  # baseline - no grouping explains nothing

ve_2digit = compute_variance_explained(
    customer_summary, 'sic_2digit', behavioral_features
)

ve_6digit = compute_variance_explained(
    customer_summary, 'sic_6digit', behavioral_features
)

comparison = pd.DataFrame({
    '2_digit': ve_2digit,
    '6_digit': ve_6digit,
    'marginal_gain_6digit': ve_6digit - ve_2digit
})

print(comparison)
This tells you, for each behavioural feature, how much additional explanatory power 6-digit SIC adds over 2-digit. If the marginal gain is small (below 0.05 on average), 2-digit is sufficient and 6-digit only fragments your groups without adding homogeneity. If certain features show large marginal gains, 6-digit is worth the fragmentation cost for those features.
In practice for most SME books you'll find 2-digit explains a meaningful share of variance in international payment behaviour and transaction type distribution, but 6-digit adds relatively little beyond that except for a handful of high-volume SIC categories like retail, construction, and professional services. Use this output to make a documented, data-driven decision rather than an assumption.

Step 3 — Find Natural Turnover Band Boundaries
Don't impose fixed bands. Use your data to find where the natural breaks in transaction volume distribution occur within each SIC group. The right tool for this is either Jenks natural breaks or a decision tree approach.
Option A — Jenks Natural Breaks
Jenks optimises boundaries to minimise within-group variance while maximising between-group variance. It finds where the data naturally clusters.
pythonimport jenkspy

def find_natural_breaks(series, n_classes=5):
    """
    Find natural break points in a continuous distribution.
    Returns the break values (boundaries between classes).
    """
    clean = series.dropna()
    
    if len(clean) < n_classes * 10:
        # Not enough data for requested classes
        # Fall back to fewer classes
        n_classes = max(2, len(clean) // 10)
    
    breaks = jenkspy.jenks_breaks(clean.tolist(), n_classes=n_classes)
    return breaks

# Find breaks on log-transformed volume
# Do this at the overall population level first
overall_breaks = find_natural_breaks(
    customer_summary['log_observed_volume'], 
    n_classes=5
)

print("Natural volume band boundaries (log scale):")
print(overall_breaks)
print("\nIn original scale (£):")
print([round(np.expm1(b), -3) for b in overall_breaks])
Then check whether these breaks are stable within each major SIC group:
python# Check breaks per SIC group
sic_breaks = {}
for sic in customer_summary['sic_2digit'].unique():
    sic_data = customer_summary[
        customer_summary['sic_2digit'] == sic
    ]['log_observed_volume']
    
    if len(sic_data) >= 50:  # minimum for reliable breaks
        breaks = find_natural_breaks(sic_data, n_classes=5)
        sic_breaks[sic] = breaks
    else:
        sic_breaks[sic] = overall_breaks  # fall back to global breaks

# Compare SIC-specific breaks to global breaks
# If they're similar, global breaks are fine
# If they diverge significantly, consider SIC-specific banding
breaks_df = pd.DataFrame(sic_breaks).T
breaks_df.columns = ['min', 'b1', 'b2', 'b3', 'b4', 'max']
print(breaks_df)
If the SIC-specific breaks cluster close to the global breaks, use global breaks for simplicity — your turnover bands are consistent across all peer groups. If certain SIC groups have radically different break points (which occasionally happens with capital-intensive industries), those SIC groups get their own break points.
Option B — Decision Tree Splits
An alternative that's more interpretable and directly optimises for behavioural separation:
pythonfrom sklearn.tree import DecisionTreeRegressor
from sklearn.tree import export_text

def find_tree_breaks(df, volume_col, target_feature, max_bands=5):
    """
    Use a decision tree to find volume thresholds that best 
    predict a behavioural feature. The split points become 
    your band boundaries.
    """
    valid = df[[volume_col, target_feature]].dropna()
    
    X = valid[[volume_col]]
    y = valid[target_feature]
    
    tree = DecisionTreeRegressor(
        max_leaf_nodes=max_bands,
        min_samples_leaf=50  # enforce minimum group size
    )
    tree.fit(X, y)
    
    # Extract split thresholds
    thresholds = tree.tree_.threshold
    thresholds = sorted(set(
        thresholds[thresholds != -2]  # -2 marks leaf nodes
    ))
    
    return thresholds

# Find breaks that best separate international payment behaviour
# by volume - since that's your most FC-relevant feature
tree_breaks = find_tree_breaks(
    customer_summary,
    'log_observed_volume',
    'intl_pct_value_360d',
    max_bands=5
)

print("Tree-derived volume band boundaries:")
print([round(np.expm1(b), -3) for b in tree_breaks])
Run this for each of your key behavioural features and compare the suggested breaks. Where multiple features agree on similar break points, those are your most robust boundaries — they're naturally separating the population on multiple dimensions simultaneously.

Step 4 — Assign Peer Groups and Validate Size
Now assign every customer to a peer group and check sizes:
pythondef assign_volume_band(log_volume, breaks):
    """Assign a customer to a volume band based on break points."""
    for i, (lower, upper) in enumerate(zip(breaks[:-1], breaks[1:])):
        if lower <= log_volume < upper:
            return i + 1
    return len(breaks) - 1  # top band

# Apply global breaks (or SIC-specific where warranted)
customer_summary['volume_band'] = customer_summary[
    'log_observed_volume'
].apply(lambda x: assign_volume_band(x, overall_breaks))

# Create peer group ID
customer_summary['peer_group_id'] = (
    customer_summary['sic_2digit'].astype(str) + '_' + 
    customer_summary['volume_band'].astype(str)
)

# Check group sizes
group_sizes = customer_summary.groupby('peer_group_id').agg(
    n_customers=('customer_id', 'count'),
    sic=('sic_2digit', 'first'),
    volume_band=('volume_band', 'first'),
    median_volume=('observed_annual_volume', 'median')
).reset_index().sort_values('n_customers')

print(f"Total peer groups: {len(group_sizes)}")
print(f"Groups below minimum size (50): {(group_sizes['n_customers'] < 50).sum()}")
print(f"Smallest groups:")
print(group_sizes.head(20))

Step 5 — Handle Sparse Groups Algorithmically
Rather than manually merging sparse groups, do it programmatically using a hierarchical fallback:
pythonMIN_GROUP_SIZE = 50

def build_fallback_hierarchy(customer_summary, group_sizes, min_size=50):
    """
    For groups below minimum size, assign them to the nearest 
    viable parent group in the hierarchy.
    
    Hierarchy:
    Level 1: sic_2digit + volume_band (target)
    Level 2: sic_2digit only (drop volume band)
    Level 3: sic_1digit + volume_band (broader SIC)
    Level 4: sic_1digit only
    Level 5: full population
    """
    
    # Add SIC 1-digit (section letter)
    # In UK SIC, first letter of the 2-digit numeric maps to sections
    # You'll need a SIC lookup for this - here's the logic
    sic_section_map = build_sic_section_map()  # your lookup table
    customer_summary['sic_1digit'] = customer_summary['sic_2digit'].map(
        sic_section_map
    )
    
    result = customer_summary.copy()
    result['peer_group_level'] = 1  # start assuming Level 1
    result['peer_group_final'] = result['peer_group_id']
    
    sparse_groups = group_sizes[
        group_sizes['n_customers'] < min_size
    ]['peer_group_id'].tolist()
    
    for group_id in sparse_groups:
        members = result[result['peer_group_id'] == group_id].index
        sic_2 = group_id.split('_')[0]
        vol_band = group_id.split('_')[1]
        sic_1 = sic_section_map.get(sic_2, 'Z')
        
        # Try Level 2: SIC 2-digit, no volume band
        l2_id = f"{sic_2}_all"
        l2_size = (result['sic_2digit'] == sic_2).sum()
        
        if l2_size >= min_size:
            result.loc[members, 'peer_group_final'] = l2_id
            result.loc[members, 'peer_group_level'] = 2
            continue
        
        # Try Level 3: SIC 1-digit + volume band
        l3_id = f"{sic_1}_{vol_band}"
        l3_size = (
            (result['sic_1digit'] == sic_1) & 
            (result['volume_band'] == int(vol_band))
        ).sum()
        
        if l3_size >= min_size:
            result.loc[members, 'peer_group_final'] = l3_id
            result.loc[members, 'peer_group_level'] = 3
            continue
        
        # Try Level 4: SIC 1-digit only
        l4_id = f"{sic_1}_all"
        l4_size = (result['sic_1digit'] == sic_1).sum()
        
        if l4_size >= min_size:
            result.loc[members, 'peer_group_final'] = l4_id
            result.loc[members, 'peer_group_level'] = 4
            continue
        
        # Level 5: full population
        result.loc[members, 'peer_group_final'] = 'all_customers'
        result.loc[members, 'peer_group_level'] = 5
    
    return result

customer_summary = build_fallback_hierarchy(
    customer_summary, group_sizes
)

# Check final distribution
final_distribution = customer_summary.groupby(
    ['peer_group_final', 'peer_group_level']
).size().reset_index(name='n_customers')

print(f"Level 1 groups (ideal): {(final_distribution['peer_group_level']==1).sum()}")
print(f"Level 2 groups (SIC only): {(final_distribution['peer_group_level']==2).sum()}")
print(f"Level 3+ groups (sparse): {(final_distribution['peer_group_level']>=3).sum()}")

Step 6 — Validate the Final Peer Groups
Run a final validation to confirm the groups are behaviourally meaningful:
pythondef validate_peer_groups(customer_summary, behavioral_features):
    """
    For each feature, compute within-group vs between-group variance.
    A good peer group definition has low within-group variance
    relative to between-group variance.
    """
    results = []
    
    for feature in behavioral_features:
        valid = customer_summary[
            ['peer_group_final', feature]
        ].dropna()
        
        total_var = valid[feature].var()
        
        # Within-group variance (weighted average)
        within_var = valid.groupby('peer_group_final')[feature].var()
        group_sizes = valid.groupby('peer_group_final')[feature].count()
        weighted_within = (within_var * group_sizes).sum() / group_sizes.sum()
        
        between_var = total_var - weighted_within
        
        results.append({
            'feature': feature,
            'total_variance': total_var,
            'within_group_variance': weighted_within,
            'between_group_variance': between_var,
            'variance_explained_pct': round(between_var / total_var * 100, 1)
        })
    
    return pd.DataFrame(results).sort_values(
        'variance_explained_pct', ascending=False
    )

validation = validate_peer_groups(customer_summary, behavioral_features)
print(validation)
You want variance_explained_pct to be meaningfully above zero for your key features — ideally 15-30%+. If peer groups explain less than 10% of variance in all features, the grouping isn't doing useful work and you need to reconsider your grouping variables. If they explain 40%+ you have strong, well-defined peer groups.

The Output
What you end up with is a customer_summary table with four new columns:
peer_group_final — the actual peer group ID used for scoring. peer_group_level — which fallback level was used (1 = ideal, 5 = population). volume_band — which turnover band the customer falls in. sic_1digit — the section-level SIC for fallback grouping.
This joins to your main feature panel on customer_id and gives every feature standardisation step the peer group context it needs. The level column is a feature in its own right — customers at level 3, 4, or 5 are in sparse categories, which is itself potentially informative and should be surfaced in the dashboard alongside their anomaly score
