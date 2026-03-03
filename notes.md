Good instinct. A peer group of 10,000 is too wide — the anomaly detection loses meaning when you're comparing a sole trader hairdresser against a limited company hairdresser with 5 staff. The peer comparison should feel like genuine peers, not just the same SIC code.
The Problem With a Simple Max Cap
Capping at 3,000 by randomly splitting a group of 10,000 is the wrong approach. You'd be creating arbitrary subgroups with no behavioural rationale — the customers in subgroup A aren't meaningfully different from subgroup B, they just happened to sort differently. That undermines the whole point of peer groups.
What you actually want is meaningful subdivision of large groups. The question is what variable creates the most behavioural homogeneity when you split.
What Variables Are Worth Adding
Not all of them are equal. Here's an honest assessment of each.
Customer type / legal structure — this is your strongest candidate. A sole trader and a limited company in the same SIC code with similar turnover genuinely behave differently. Sole traders typically have simpler, lower-volume transaction patterns, less formal payment structures, and different counterparty profiles. Limited companies have payroll, corporation tax payments, director loan activity, more formal supplier relationships. This is a real behavioural difference that the model should know about.
Number of directors — useful as a proxy for business complexity but correlated with legal structure. A sole trader always has one director. A limited company ranges from 1 to many. If you include legal structure, director count adds marginal value except at the extremes — businesses with 6+ directors are structurally different from 2-director businesses even within limited companies.
Business age — a business incorporated last year behaves differently from one incorporated 15 years ago even at the same turnover and SIC. Not because of financial crime risk specifically, but because mature businesses have more stable, predictable patterns. This is useful for anomaly detection because it tightens the peer group baseline. However it's a continuous variable which makes it harder to use as a grouping dimension directly — you'd need to band it.
Geographic region — weaker than you might think for most behavioural features. Transaction patterns are driven more by SIC and size than by where the business is registered. Adds fragmentation without proportionate homogeneity gain. I'd leave this out.
Account tenure — how long they've banked with you. Different from business age. A business that opened its account 6 months ago regardless of how old the company is has less stable baseline behaviour. Worth considering as a grouping dimension specifically for the anomaly model because it affects how reliable the baseline is.
Recommended Approach — Hierarchical Splitting of Large Groups
Rather than imposing a maximum size, split large groups on the most discriminating additional variable, and only split when a group exceeds a threshold. This preserves the logic of your existing peer group design.
def split_large_groups(
    df,
    peer_group_col='peer_group_id',
    max_group_size=3000,
    min_group_size=50,
    split_variables=['legal_structure', 'director_band', 'account_tenure_band'],
    volume_col='log_observed_volume'
):
    """
    For peer groups exceeding max_group_size, attempt to split
    on additional variables in priority order.
    
    Continues splitting until all groups are under max_group_size
    or no further meaningful splits are possible.
    """
    
    df = df.copy()
    df['peer_group_final'] = df[peer_group_col]
    df['peer_group_level_detail'] = 0  # 0 = no additional split needed
    
    iteration = 0
    max_iterations = len(split_variables)
    
    while iteration < max_iterations:
        
        # Find groups still over max size
        group_sizes = df.groupby('peer_group_final').size()
        oversized = group_sizes[group_sizes > max_group_size].index.tolist()
        
        if not oversized:
            break  # all groups within size
        
        split_var = split_variables[iteration]
        
        if split_var not in df.columns:
            print(f"Split variable {split_var} not found, skipping")
            iteration += 1
            continue
        
        print(f"Iteration {iteration+1}: splitting {len(oversized)} oversized "
              f"groups on {split_var}")
        
        for pg in oversized:
            pg_mask = df['peer_group_final'] == pg
            pg_df = df[pg_mask]
            
            # Attempt split on this variable
            split_result = attempt_split(
                pg_df, pg, split_var, min_group_size
            )
            
            if split_result is not None:
                df.loc[pg_mask, 'peer_group_final'] = split_result
                df.loc[pg_mask, 'peer_group_level_detail'] = iteration + 1
            # If split fails min size check, leave group as-is
            # It's oversized but better than creating tiny groups
        
        iteration += 1
    
    # Final check
    final_sizes = df.groupby('peer_group_final').size()
    still_oversized = (final_sizes > max_group_size).sum()
    
    if still_oversized > 0:
        print(f"Warning: {still_oversized} groups still exceed {max_group_size} "
              f"after all split attempts. Consider adding more split variables.")
    
    return df


def attempt_split(pg_df, pg_id, split_var, min_size):
    """
    Attempt to split a peer group on split_var.
    Returns new peer group IDs if all resulting subgroups
    meet minimum size. Returns None if any subgroup is too small.
    """
    
    split_values = pg_df[split_var].dropna().unique()
    
    if len(split_values) <= 1:
        return None  # no variation to split on
    
    # Check that all resulting subgroups meet minimum size
    subgroup_sizes = pg_df.groupby(split_var).size()
    
    if (subgroup_sizes < min_size).any():
        # Some subgroups too small - try merging small categories
        merged_var = merge_small_categories(
            pg_df[split_var], min_size
        )
        if merged_var is None:
            return None  # can't make it work
        pg_df = pg_df.copy()
        pg_df[split_var] = merged_var
        subgroup_sizes = pg_df.groupby(split_var).size()
        
        if (subgroup_sizes < min_size).any():
            return None
    
    # Build new peer group IDs
    new_ids = pg_df[split_var].map(
        lambda v: f"{pg_id}_{split_var[:4]}_{v}"
    )
    
    return new_ids


def merge_small_categories(series, min_size):
    """
    For a categorical variable, merge small categories into 'other'
    until all categories meet minimum size.
    Returns None if even merged categories can't reach minimum.
    """
    
    counts = series.value_counts()
    small_cats = counts[counts < min_size].index.tolist()
    
    if len(small_cats) == len(counts):
        return None  # everything is small, merging won't help
    
    merged = series.copy()
    merged[series.isin(small_cats)] = 'other'
    
    # Check 'other' category size
    if merged.value_counts().get('other', 0) < min_size:
        return None
    
    return merged
Preparing the Split Variables
Before running this, you need to band your continuous split variables.
def prepare_split_variables(df):
    """
    Create banded versions of continuous variables
    suitable for peer group splitting.
    """
    
    df = df.copy()
    
    # Legal structure - already categorical, use directly
    # Expected values: 'sole_trader', 'limited_company', 
    # 'partnership', 'llp' etc.
    # If you have a numeric code, map it first
    if 'legal_structure' not in df.columns:
        print("Warning: legal_structure not found")
    
    # Director count band
    if 'director_count' in df.columns:
        df['director_band'] = pd.cut(
            df['director_count'],
            bins=[0, 1, 2, 4, np.inf],
            labels=['sole', 'two', 'small_board', 'large_board'],
            include_lowest=True
        )
    
    # Account tenure band (years banking with you)
    if 'account_age_days' in df.columns:
        df['account_tenure_band'] = pd.cut(
            df['account_age_days'] / 365,
            bins=[0, 1, 3, 7, np.inf],
            labels=['new', 'early', 'established', 'long_term'],
            include_lowest=True
        )
    
    # Business age band (years since incorporation)
    if 'company_age_days' in df.columns:
        df['business_age_band'] = pd.cut(
            df['company_age_days'] / 365,
            bins=[0, 2, 5, 10, np.inf],
            labels=['startup', 'young', 'mature', 'established'],
            include_lowest=True
        )
    
    return df

df = prepare_split_variables(df)
The Priority Order for Splitting
When a group exceeds 3,000, try splitting variables in this order:
SPLIT_PRIORITY = [
    'legal_structure',    # strongest behavioural discriminator
    'director_band',      # business complexity proxy
    'account_tenure_band' # baseline reliability proxy
]

df = split_large_groups(
    df,
    peer_group_col='peer_group_id',
    max_group_size=3000,
    min_group_size=50,
    split_variables=SPLIT_PRIORITY
)
Legal structure first because it's the most behaviourally meaningful split. A sole trader hairdresser and a limited company hairdresser at similar turnover genuinely have different transaction patterns. Director band second because it further refines business complexity within legal structure. Account tenure last because it's more about model reliability than genuine behavioural difference — use it to prevent new customers from distorting established customer baselines.
Validating the Result
# Check final distribution
final_sizes = df.groupby('peer_group_final').size().describe()
print(final_sizes)

# How many groups needed additional splitting
split_summary = df.groupby('peer_group_level_detail').agg(
    n_customers=('customer_id', 'count'),
    n_groups=('peer_group_final', 'nunique')
).reset_index()

split_detail_labels = {
    0: 'No split needed (under 3k)',
    1: 'Split on legal structure',
    2: 'Split on director band',
    3: 'Split on account tenure'
}
split_summary['description'] = split_summary[
    'peer_group_level_detail'
].map(split_detail_labels)

print(split_summary)
The Practical Answer to Your Question
Yes, customer type (legal structure) is absolutely worth adding — it's not just a refinement, it's a genuinely important behavioural discriminator that you should have in the peer group definition. A sole trader and a limited company are different types of business, not just differently-sized versions of the same thing.
The max size cap of 3,000 is a reasonable backstop but shouldn't be the primary mechanism. Let the algorithm split on meaningful variables first. The cap catches any group that remains large after all meaningful splits are exhausted — at that point the group is genuinely homogeneous on all available variables and the size just reflects how common that type of business is in your book. A group of 4,000 businesses that are all sole trader hairdressers at similar turnover is actually a tight peer group despite its size. A group of 4,000 that includes sole traders, limited companies, and partnerships of very different sizes is not.