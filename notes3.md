Got it. Clear sequential steps, separate DataFrames at each stage, no index manipulation.

---

## Step 1 — Prepare The Base Customer Data

```python
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# Load your customer dataset
customers = pd.read_parquet('customer_data.parquet')

# Create SIC levels
customers['sic_5digit'] = customers['sic_code'].astype(str).str.zfill(5)
customers['sic_2digit'] = customers['sic_5digit'].str[:2]
customers['sic_section'] = customers['sic_2digit'].map({
    '01': 'A', '02': 'A', '03': 'A',
    '05': 'B', '06': 'B', '07': 'B', '08': 'B', '09': 'B',
    '10': 'C', '11': 'C', '12': 'C', '13': 'C', '14': 'C',
    '15': 'C', '16': 'C', '17': 'C', '18': 'C', '19': 'C',
    '20': 'C', '21': 'C', '22': 'C', '23': 'C', '24': 'C',
    '25': 'C', '26': 'C', '27': 'C', '28': 'C', '29': 'C',
    '30': 'C', '31': 'C', '32': 'C', '33': 'C',
    '35': 'D',
    '36': 'E', '37': 'E', '38': 'E', '39': 'E',
    '41': 'F', '42': 'F', '43': 'F',
    '45': 'G', '46': 'G', '47': 'G',
    '49': 'H', '50': 'H', '51': 'H', '52': 'H', '53': 'H',
    '55': 'I', '56': 'I',
    '58': 'J', '59': 'J', '60': 'J', '61': 'J', '62': 'J', '63': 'J',
    '64': 'K', '65': 'K', '66': 'K',
    '68': 'L',
    '69': 'M', '70': 'M', '71': 'M', '72': 'M', '73': 'M', '74': 'M', '75': 'M',
    '77': 'N', '78': 'N', '79': 'N', '80': 'N', '81': 'N', '82': 'N',
    '84': 'O',
    '85': 'P',
    '86': 'Q', '87': 'Q', '88': 'Q',
    '90': 'R', '91': 'R', '92': 'R', '93': 'R',
    '94': 'S', '95': 'S', '96': 'S',
    '97': 'T', '98': 'T',
    '99': 'U'
})

# Fill any unmapped sections
customers['sic_section'] = customers['sic_section'].fillna('Z')

# Log transform credit turnover
# Using observed credit turnover from transaction data
customers['log_credit_turnover'] = np.log1p(
    customers['annual_credit_turnover'].fillna(0)
)

print(f"Total customers: {len(customers):,}")
print(f"Unique SIC 5-digit: {customers['sic_5digit'].nunique():,}")
print(f"Unique SIC 2-digit: {customers['sic_2digit'].nunique():,}")
print(f"Unique SIC section: {customers['sic_section'].nunique():,}")
```

---

## Step 2 — Create Turnover Bands On Full Population

```python
MIN_GROUP_SIZE = 50
MAX_GROUP_SIZE = 3000
N_BANDS = 5

# Compute quantile breaks on full population log turnover
quantile_points = np.linspace(0, 1, N_BANDS + 1)
turnover_breaks = np.quantile(
    customers['log_credit_turnover'].dropna(),
    quantile_points
)

# Label bands 1 through 5
customers['turnover_band'] = pd.cut(
    customers['log_credit_turnover'],
    bins=turnover_breaks,
    labels=[1, 2, 3, 4, 5],
    include_lowest=True
).astype('Int64')

# Customers with null turnover get band 0 (unknown)
customers['turnover_band'] = customers['turnover_band'].fillna(0)

print("Turnover band distribution:")
print(customers['turnover_band'].value_counts().sort_index())

# Store breaks for documentation
breaks_documentation = pd.DataFrame({
    'band': [1, 2, 3, 4, 5],
    'log_lower': turnover_breaks[:-1],
    'log_upper': turnover_breaks[1:],
    'approx_lower_gbp': np.expm1(turnover_breaks[:-1]).round(-2),
    'approx_upper_gbp': np.expm1(turnover_breaks[1:]).round(-2)
})
print("\nTurnover band boundaries:")
print(breaks_documentation)
```

---

## Step 3 — Build Candidate Groups At Each Level

```python
# Level 1 candidates: SIC 5-digit + turnover band
level1_candidates = customers[['customer_id', 
                                'sic_5digit', 
                                'turnover_band']].copy()

level1_candidates['candidate_group'] = (
    'sic5_' + 
    level1_candidates['sic_5digit'].astype(str) + 
    '_vol' + 
    level1_candidates['turnover_band'].astype(str)
)

# Level 2 candidates: SIC 5-digit only
level2_candidates = customers[['customer_id', 
                                'sic_5digit']].copy()

level2_candidates['candidate_group'] = (
    'sic5_' + 
    level2_candidates['sic_5digit'].astype(str) + 
    '_all'
)

# Level 3 candidates: SIC 2-digit + turnover band
level3_candidates = customers[['customer_id', 
                                'sic_2digit', 
                                'turnover_band']].copy()

level3_candidates['candidate_group'] = (
    'sic2_' + 
    level3_candidates['sic_2digit'].astype(str) + 
    '_vol' + 
    level3_candidates['turnover_band'].astype(str)
)

# Level 4 candidates: SIC 2-digit only
level4_candidates = customers[['customer_id', 
                                'sic_2digit']].copy()

level4_candidates['candidate_group'] = (
    'sic2_' + 
    level4_candidates['sic_2digit'].astype(str) + 
    '_all'
)

# Level 5 candidates: SIC section + turnover band
level5_candidates = customers[['customer_id', 
                                'sic_section', 
                                'turnover_band']].copy()

level5_candidates['candidate_group'] = (
    'sec_' + 
    level5_candidates['sic_section'].astype(str) + 
    '_vol' + 
    level5_candidates['turnover_band'].astype(str)
)

# Level 6 candidates: SIC section only
level6_candidates = customers[['customer_id', 
                                'sic_section']].copy()

level6_candidates['candidate_group'] = (
    'sec_' + 
    level6_candidates['sic_section'].astype(str) + 
    '_all'
)

print("Candidate groups built for all 6 levels")
```

---

## Step 4 — Assign Level 1

```python
# Compute group sizes for level 1
level1_sizes = (level1_candidates
                .groupby('candidate_group')
                ['customer_id']
                .count()
                .reset_index()
                .rename(columns={'customer_id': 'group_size'}))

# Valid groups: between min and max size
level1_valid_groups = level1_sizes[
    (level1_sizes['group_size'] >= MIN_GROUP_SIZE) &
    (level1_sizes['group_size'] <= MAX_GROUP_SIZE)
]['candidate_group'].tolist()

# Assign customers in valid level 1 groups
level1_assigned = level1_candidates[
    level1_candidates['candidate_group'].isin(level1_valid_groups)
][['customer_id', 'candidate_group']].copy()

level1_assigned['peer_group_id'] = level1_assigned['candidate_group']
level1_assigned['peer_group_level'] = 1
level1_assigned = level1_assigned[['customer_id', 
                                    'peer_group_id', 
                                    'peer_group_level']]

print(f"Level 1 assigned: {len(level1_assigned):,} customers")
print(f"Remaining: {len(customers) - len(level1_assigned):,} customers")

# Oversized groups at level 1 - need clustering
level1_oversized_groups = level1_sizes[
    level1_sizes['group_size'] > MAX_GROUP_SIZE
]['candidate_group'].tolist()

level1_oversized_customers = level1_candidates[
    level1_candidates['candidate_group'].isin(level1_oversized_groups)
][['customer_id', 'candidate_group']].copy()

level1_oversized_customers = level1_oversized_customers.merge(
    customers[['customer_id', 'log_credit_turnover']],
    on='customer_id',
    how='left'
)

print(f"Oversized level 1 groups needing clustering: "
      f"{len(level1_oversized_groups)}")
print(f"Customers in oversized groups: "
      f"{len(level1_oversized_customers):,}")
```

---

## Step 5 — Cluster Oversized Level 1 Groups

```python
def cluster_oversized_group(group_df, group_id, max_size, min_size):
    """
    Takes customers in one oversized group.
    Splits using KMeans on log credit turnover.
    Returns DataFrame with new cluster-level peer group IDs.
    """
    
    n = len(group_df)
    
    # Minimum clusters needed to get under max_size
    n_clusters = int(np.ceil(n / max_size))
    
    # Maximum clusters before hitting min_size
    max_clusters = int(np.floor(n / min_size))
    
    # Cap sensibly
    n_clusters = min(n_clusters, max_clusters, 10)
    n_clusters = max(n_clusters, 2)
    
    # Prepare turnover for clustering
    turnover_values = group_df['log_credit_turnover'].fillna(
        group_df['log_credit_turnover'].median()
    ).values.reshape(-1, 1)
    
    scaler = StandardScaler()
    turnover_scaled = scaler.fit_transform(turnover_values)
    
    kmeans = KMeans(
        n_clusters=n_clusters,
        random_state=42,
        n_init=10
    )
    cluster_labels = kmeans.fit_predict(turnover_scaled)
    
    # Get cluster centres back in original scale for naming
    centres = kmeans.cluster_centers_.flatten()
    centres_original = np.expm1(
        scaler.inverse_transform(
            centres.reshape(-1, 1)
        ).flatten()
    )
    
    # Sort clusters by turnover (low to high) for readable labels
    sort_order = np.argsort(centres_original)
    rank_map = {old: new for new, old in enumerate(sort_order, 1)}
    cluster_ranks = [rank_map[label] for label in cluster_labels]
    
    # Build output DataFrame
    clustered = group_df[['customer_id']].copy()
    clustered['peer_group_id'] = (
        group_id + '_kmeans' + 
        pd.Series(cluster_ranks).astype(str).values
    )
    clustered['peer_group_level'] = 1
    
    # Validate all clusters meet minimum
    cluster_sizes = clustered['peer_group_id'].value_counts()
    
    if (cluster_sizes < min_size).any():
        # Merge small clusters into nearest neighbour
        small_clusters = cluster_sizes[
            cluster_sizes < min_size
        ].index.tolist()
        
        for small_cluster in small_clusters:
            small_rank = int(small_cluster.split('kmeans')[1])
            
            # Merge with adjacent cluster
            if small_rank > 1:
                merge_target = small_cluster.replace(
                    f'kmeans{small_rank}', 
                    f'kmeans{small_rank - 1}'
                )
            else:
                merge_target = small_cluster.replace(
                    f'kmeans{small_rank}', 
                    f'kmeans{small_rank + 1}'
                )
            
            clustered.loc[
                clustered['peer_group_id'] == small_cluster,
                'peer_group_id'
            ] = merge_target
    
    return clustered


# Apply clustering to each oversized group
clustered_results = []

for group_id in level1_oversized_groups:
    
    group_customers = level1_oversized_customers[
        level1_oversized_customers['candidate_group'] == group_id
    ].copy()
    
    clustered = cluster_oversized_group(
        group_customers,
        group_id,
        MAX_GROUP_SIZE,
        MIN_GROUP_SIZE
    )
    
    clustered_results.append(clustered)

if clustered_results:
    level1_clustered = pd.concat(clustered_results, ignore_index=True)
    print(f"Clustered assignments: {len(level1_clustered):,} customers")
    print(f"New groups created: {level1_clustered['peer_group_id'].nunique()}")
else:
    level1_clustered = pd.DataFrame(
        columns=['customer_id', 'peer_group_id', 'peer_group_level']
    )

# Combine level 1 valid and level 1 clustered
level1_all_assigned = pd.concat(
    [level1_assigned, level1_clustered],
    ignore_index=True
)

print(f"\nTotal assigned after level 1: {len(level1_all_assigned):,}")
```

---

## Step 6 — Identify Remaining Customers And Assign Level 2

```python
# Customers not yet assigned after level 1
remaining_after_level1 = customers[
    ~customers['customer_id'].isin(level1_all_assigned['customer_id'])
][['customer_id']].copy()

print(f"Remaining after level 1: {len(remaining_after_level1):,}")

# Get level 2 candidates for remaining only
level2_remaining = remaining_after_level1.merge(
    level2_candidates,
    on='customer_id',
    how='left'
)

# Compute group sizes
level2_sizes = (level2_remaining
                .groupby('candidate_group')
                ['customer_id']
                .count()
                .reset_index()
                .rename(columns={'customer_id': 'group_size'}))

level2_valid_groups = level2_sizes[
    (level2_sizes['group_size'] >= MIN_GROUP_SIZE) &
    (level2_sizes['group_size'] <= MAX_GROUP_SIZE)
]['candidate_group'].tolist()

level2_assigned = level2_remaining[
    level2_remaining['candidate_group'].isin(level2_valid_groups)
][['customer_id', 'candidate_group']].copy()

level2_assigned['peer_group_id'] = level2_assigned['candidate_group']
level2_assigned['peer_group_level'] = 2
level2_assigned = level2_assigned[['customer_id',
                                    'peer_group_id',
                                    'peer_group_level']]

# Handle oversized level 2 groups
level2_oversized_groups = level2_sizes[
    level2_sizes['group_size'] > MAX_GROUP_SIZE
]['candidate_group'].tolist()

level2_oversized_customers = level2_remaining[
    level2_remaining['candidate_group'].isin(level2_oversized_groups)
][['customer_id', 'candidate_group']].copy()

level2_oversized_customers = level2_oversized_customers.merge(
    customers[['customer_id', 'log_credit_turnover']],
    on='customer_id',
    how='left'
)

# Cluster oversized level 2 groups
level2_clustered_results = []

for group_id in level2_oversized_groups:
    
    group_customers = level2_oversized_customers[
        level2_oversized_customers['candidate_group'] == group_id
    ].copy()
    
    clustered = cluster_oversized_group(
        group_customers,
        group_id,
        MAX_GROUP_SIZE,
        MIN_GROUP_SIZE
    )
    level2_clustered_results.append(clustered)

if level2_clustered_results:
    level2_clustered = pd.concat(
        level2_clustered_results, 
        ignore_index=True
    )
    level2_clustered['peer_group_level'] = 2
else:
    level2_clustered = pd.DataFrame(
        columns=['customer_id', 'peer_group_id', 'peer_group_level']
    )

level2_all_assigned = pd.concat(
    [level2_assigned, level2_clustered],
    ignore_index=True
)

print(f"Level 2 assigned: {len(level2_all_assigned):,} customers")
```

---

## Step 7 — Repeat For Levels 3 Through 6

Rather than repeat identical blocks, here's a clean generic step that handles levels 3–6 identically:

```python
def assign_level(
    remaining_customers,
    level_candidates,
    level_num,
    customers_with_turnover,
    min_size,
    max_size
):
    """
    Takes remaining unassigned customers.
    Attempts assignment at this level.
    Returns assigned DataFrame and still-remaining DataFrame.
    """
    
    # Get candidates for remaining customers only
    level_remaining = remaining_customers.merge(
        level_candidates,
        on='customer_id',
        how='left'
    )
    
    # Group sizes
    level_sizes = (level_remaining
                   .groupby('candidate_group')
                   ['customer_id']
                   .count()
                   .reset_index()
                   .rename(columns={'customer_id': 'group_size'}))
    
    # Valid groups
    valid_groups = level_sizes[
        (level_sizes['group_size'] >= min_size) &
        (level_sizes['group_size'] <= max_size)
    ]['candidate_group'].tolist()
    
    assigned = level_remaining[
        level_remaining['candidate_group'].isin(valid_groups)
    ][['customer_id', 'candidate_group']].copy()
    
    assigned['peer_group_id'] = assigned['candidate_group']
    assigned['peer_group_level'] = level_num
    assigned = assigned[['customer_id', 
                          'peer_group_id', 
                          'peer_group_level']]
    
    # Oversized groups
    oversized_groups = level_sizes[
        level_sizes['group_size'] > max_size
    ]['candidate_group'].tolist()
    
    oversized_customers = level_remaining[
        level_remaining['candidate_group'].isin(oversized_groups)
    ][['customer_id', 'candidate_group']].copy()
    
    oversized_customers = oversized_customers.merge(
        customers_with_turnover[['customer_id', 'log_credit_turnover']],
        on='customer_id',
        how='left'
    )
    
    clustered_list = []
    for group_id in oversized_groups:
        group_df = oversized_customers[
            oversized_customers['candidate_group'] == group_id
        ].copy()
        clustered = cluster_oversized_group(
            group_df, group_id, max_size, min_size
        )
        clustered['peer_group_level'] = level_num
        clustered_list.append(clustered)
    
    if clustered_list:
        clustered_all = pd.concat(clustered_list, ignore_index=True)
    else:
        clustered_all = pd.DataFrame(
            columns=['customer_id', 'peer_group_id', 'peer_group_level']
        )
    
    level_assigned = pd.concat(
        [assigned, clustered_all], 
        ignore_index=True
    )
    
    print(f"Level {level_num}: {len(level_assigned):,} assigned")
    
    return level_assigned


# Remaining after levels 1 and 2
remaining_after_level2 = customers[
    ~customers['customer_id'].isin(
        pd.concat([
            level1_all_assigned, 
            level2_all_assigned
        ])['customer_id']
    )
][['customer_id']].copy()

print(f"Remaining after level 2: {len(remaining_after_level2):,}")

# Level 3
level3_assigned = assign_level(
    remaining_after_level2,
    level3_candidates,
    3,
    customers,
    MIN_GROUP_SIZE,
    MAX_GROUP_SIZE
)

remaining_after_level3 = customers[
    ~customers['customer_id'].isin(
        pd.concat([
            level1_all_assigned,
            level2_all_assigned,
            level3_assigned
        ])['customer_id']
    )
][['customer_id']].copy()

# Level 4
level4_assigned = assign_level(
    remaining_after_level3,
    level4_candidates,
    4,
    customers,
    MIN_GROUP_SIZE,
    MAX_GROUP_SIZE
)

remaining_after_level4 = customers[
    ~customers['customer_id'].isin(
        pd.concat([
            level1_all_assigned,
            level2_all_assigned,
            level3_assigned,
            level4_assigned
        ])['customer_id']
    )
][['customer_id']].copy()

# Level 5
level5_assigned = assign_level(
    remaining_after_level4,
    level5_candidates,
    5,
    customers,
    MIN_GROUP_SIZE,
    MAX_GROUP_SIZE
)

remaining_after_level5 = customers[
    ~customers['customer_id'].isin(
        pd.concat([
            level1_all_assigned,
            level2_all_assigned,
            level3_assigned,
            level4_assigned,
            level5_assigned
        ])['customer_id']
    )
][['customer_id']].copy()

# Level 6
level6_assigned = assign_level(
    remaining_after_level5,
    level6_candidates,
    6,
    customers,
    MIN_GROUP_SIZE,
    MAX_GROUP_SIZE
)
```

---

## Step 8 — Handle Unclassifiable Customers

```python
# Anyone still unassigned after all 6 levels
all_assigned = pd.concat([
    level1_all_assigned,
    level2_all_assigned,
    level3_assigned,
    level4_assigned,
    level5_assigned,
    level6_assigned
], ignore_index=True)

unclassifiable = customers[
    ~customers['customer_id'].isin(all_assigned['customer_id'])
][['customer_id']].copy()

unclassifiable['peer_group_id'] = 'unclassifiable'
unclassifiable['peer_group_level'] = 99

print(f"Unclassifiable customers: {len(unclassifiable):,}")
```

---

## Step 9 — Combine And Validate

```python
# Final peer group table
peer_groups_final = pd.concat([
    all_assigned,
    unclassifiable
], ignore_index=True)

# Validation
group_sizes_final = (peer_groups_final
                     .groupby('peer_group_id')
                     ['customer_id']
                     .count()
                     .reset_index()
                     .rename(columns={'customer_id': 'group_size'}))

print("\n=== PEER GROUP VALIDATION ===")
print(f"Total customers: {len(peer_groups_final):,}")
print(f"Total peer groups: {group_sizes_final['peer_group_id'].nunique():,}")
print(f"Min group size: {group_sizes_final['group_size'].min()}")
print(f"Max group size: {group_sizes_final['group_size'].max()}")
print(f"Mean group size: {group_sizes_final['group_size'].mean():.0f}")
print(f"\nGroups below minimum ({MIN_GROUP_SIZE}): "
      f"{(group_sizes_final['group_size'] < MIN_GROUP_SIZE).sum()}")
print(f"Groups above maximum ({MAX_GROUP_SIZE}): "
      f"{(group_sizes_final['group_size'] > MAX_GROUP_SIZE).sum()}")

print("\nAssignment level distribution:")
level_summary = (peer_groups_final
                 .groupby('pee