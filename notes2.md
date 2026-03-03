## The Reality

With ~1m customers you need a tiered system that's systematic, fast, and produces no singleton groups. The key insight is that **peer comparison should degrade gracefully** — when you can't find tight peers, widen the comparison but flag the reduced confidence. Never compare against the full population.

## The Hierarchy

```
Level 1: SIC 5-digit + customer type + RM tier     → target 100–3000
Level 2: SIC 5-digit + customer type               → target 100–3000  
Level 3: SIC 2-digit + customer type               → target 100–3000
Level 4: SIC 2-digit only                          → minimum 50
Level 5: SIC section (1-digit) + customer type     → minimum 50
Level 6: SIC section only                          → minimum 50
```

Stop at Level 6. Never go to full population. A SIC section like "Manufacturing" or "Professional Services" with 50+ members is a meaningful comparison. Full population is not.

## Handling Genuinely Tiny Groups

Some niche SIC codes will have 3 customers nationally. For these:

**Don't try to give them a peer group they don't have.** Instead, flag them explicitly as `unclassifiable` and handle them differently in the model.

For unclassifiable customers, the isolation forest peer comparison is replaced entirely by the autoencoder and exited customer similarity scores — the components that don't require peer groups. Their composite score is weighted accordingly: autoencoder 50%, exited similarity 50%, peer isolation forest 0%.

Document this in governance as a known limitation — niche businesses cannot be meaningfully peer-compared and their scores reflect population-level anomaly detection only.

## For The Large Groups (12k Hairdressers)

Apply the two-stage approach discussed: hard split on customer type first, then KMeans within each type on log turnover and RM tier. Cap output clusters at 3,000. Label clusters descriptively. This runs fast and produces meaningful groups.

```python
def assign_peer_group(df, min_size=50, max_size=3000):
    
    levels = [
        ['sic_5digit', 'customer_type_clean', 'rm_tier'],
        ['sic_5digit', 'customer_type_clean'],
        ['sic_2digit', 'customer_type_clean'],
        ['sic_2digit'],
        ['sic_section', 'customer_type_clean'],
        ['sic_section'],
    ]
    
    df['peer_group_id'] = None
    df['peer_group_level'] = None
    unassigned = df.index.tolist()
    
    for level_num, cols in enumerate(levels, 1):
        
        if not unassigned:
            break
            
        # Only process customers not yet assigned
        remaining = df.loc[unassigned].copy()
        
        # Create candidate group key
        remaining['candidate_group'] = (
            remaining[cols]
            .astype(str)
            .agg('_'.join, axis=1)
        )
        
        # Check sizes
        group_sizes = remaining['candidate_group'].value_counts()
        valid_groups = group_sizes[
            (group_sizes >= min_size) & 
            (group_sizes <= max_size)
        ].index
        
        # Assign customers in valid groups
        valid_mask = remaining['candidate_group'].isin(valid_groups)
        valid_idx = remaining[valid_mask].index
        
        df.loc[valid_idx, 'peer_group_id'] = (
            remaining.loc[valid_idx, 'candidate_group']
        )
        df.loc[valid_idx, 'peer_group_level'] = level_num
        
        # For oversized groups, apply clustering
        oversized_groups = group_sizes[group_sizes > max_size].index
        for grp in oversized_groups:
            grp_idx = remaining[
                remaining['candidate_group'] == grp
            ].index
            cluster_ids = cluster_large_group(
                df.loc[grp_idx], grp, max_size, min_size
            )
            df.loc[grp_idx, 'peer_group_id'] = cluster_ids
            df.loc[grp_idx, 'peer_group_level'] = level_num
            valid_idx = grp_idx  # mark as assigned
        
        # Update unassigned list
        assigned_so_far = df[df['peer_group_id'].notna()].index
        unassigned = [i for i in df.index if i not in assigned_so_far]
    
    # Remaining truly unclassifiable
    if unassigned:
        df.loc[unassigned, 'peer_group_id'] = 'unclassifiable'
        df.loc[unassigned, 'peer_group_level'] = 99
        print(f"Unclassifiable customers: {len(unassigned)}")
    
    return df
```

## The Balance in Plain Terms

Tight peer groups where data supports it. Gracefully wider groups where it doesn't. Explicit unclassifiable flag as a last resort with adjusted model weighting. No full population comparisons. Every customer gets a peer group level indicator so analysts and the model both know how confident the peer comparison is.

Good catch. It doesn't currently — that's the missing `cluster_large_group()` function. The hierarchy logic assigns peer groups based on categorical combinations only. KMeans is the additional step that fires **after** a valid categorical group is found but is still oversized.

## How It Fits Together

The logic should be:

```
Categorical hierarchy → finds valid group (50–3000) → done
                      → finds oversized group (>3000) → KMeans subdivides it → done
                      → can't find valid group → try next level
```

So KMeans is not part of the level selection — it's a **post-processing step on oversized groups** at whatever level they were assigned.

```python
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import numpy as np

def cluster_large_group(
    df_group,
    group_id,
    max_size=3000,
    min_size=50,
    volume_col='log_credit_turnover'
):
    """
    Takes an oversized peer group and subdivides it using KMeans
    on log credit turnover. Returns a series of new peer group IDs.
    
    Called only when a categorical group exceeds max_size.
    """
    
    n = len(df_group)
    
    # How many clusters do we need minimum to get under max_size
    n_clusters_min = int(np.ceil(n / max_size))
    
    # How many clusters can we have maximum before hitting min_size
    n_clusters_max = int(np.floor(n / min_size))
    
    if n_clusters_max < n_clusters_min:
        # Can't satisfy both constraints simultaneously
        # Prioritise min_size - better to have some large groups
        # than groups too small for reliable anomaly detection
        n_clusters = n_clusters_min
    else:
        # Use minimum clusters needed - keep groups as large as possible
        # while staying under max_size
        n_clusters = n_clusters_min
    
    # Cap at something sensible - no point in 50 clusters
    n_clusters = min(n_clusters, 10)
    
    # Prepare volume feature for clustering
    volume = df_group[[volume_col]].copy()
    
    # Handle nulls - use median for missing volume
    volume[volume_col] = volume[volume_col].fillna(
        volume[volume_col].median()
    )
    
    # Scale
    scaler = StandardScaler()
    volume_scaled = scaler.fit_transform(volume)
    
    # Fit KMeans
    kmeans = KMeans(
        n_clusters=n_clusters,
        random_state=42,
        n_init=10
    )
    cluster_labels = kmeans.fit_predict(volume_scaled)
    
    # Validate cluster sizes
    unique, counts = np.unique(cluster_labels, return_counts=True)
    
    # If any cluster is below min_size, merge it with nearest neighbour
    cluster_labels = merge_small_clusters(
        cluster_labels,
        kmeans.cluster_centers_,
        min_size
    )
    
    # Build descriptive peer group IDs
    # Label by cluster centre value (back-transformed) so IDs are meaningful
    centres = kmeans.cluster_centers_.flatten()
    centre_map = {}
    for i, centre in enumerate(centres):
        # Back transform from log scale for readable label
        actual_value = np.expm1(
            scaler.inverse_transform([[centre]])[0][0]
        )
        centre_map[i] = f"{group_id}_vol{int(actual_value/1000)}k"
    
    new_ids = pd.Series(cluster_labels, index=df_group.index).map(centre_map)
    
    return new_ids


def merge_small_clusters(labels, centres, min_size):
    """
    After KMeans, merge any cluster below min_size into 
    its nearest neighbouring cluster by centre distance.
    """
    
    labels = labels.copy()
    
    max_iterations = 10
    iteration = 0
    
    while iteration < max_iterations:
        
        unique, counts = np.unique(labels, return_counts=True)
        small = unique[counts < min_size]
        
        if len(small) == 0:
            break
        
        # Find smallest cluster
        smallest = unique[counts.argmin()]
        
        if len(unique) == 1:
            break  # can't merge further
        
        # Find nearest cluster by centre distance
        smallest_centre = centres[smallest]
        distances = {
            c: np.linalg.norm(centres[c] - smallest_centre)
            for c in unique if c != smallest
        }
        nearest = min(distances, key=distances.get)
        
        # Merge smallest into nearest
        labels[labels == smallest] = nearest
        
        iteration += 1
    
    return labels
```

## The Full Picture Now

```
assign_peer_group() runs:

For each level (1→6):
    Create categorical group key
    Check size:
        
        50–3000  → assign directly, move on ✓
        
        <50      → too small, try next level
        
        >3000    → call cluster_large_group()
                   which runs KMeans on log credit turnover
                   subdivides into volume-coherent subgroups
                   each subgroup gets a descriptive ID
                   e.g. "47_sole_trader_tier2_vol45k"
                   assigns those, moves on ✓

After level 6:
    Still unassigned → 'unclassifiable', model weighted accordingly
```

## What The IDs Look Like

A hairdresser peer group ID after clustering might be:

```
96020_sole_trader_tier1_vol25k   # small sole trader, ~£25k volume
96020_sole_trader_tier1_vol80k   # mid sole trader, ~£80k volume  
96020_limited_company_tier2_vol200k  # small ltd company
96020_limited_company_tier2_vol650k  # larger ltd company
```

These are human-readable, tell the analyst exactly what the peer group represents, and are directly usable as dashboard filter labels.