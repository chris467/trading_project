```python
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# ============================================================
# CONFIGURATION
# ============================================================

MIN_GROUP_SIZE = 50
MAX_GROUP_SIZE = 3000
N_BANDS = 5  # target number of turnover bands per SIC group

# ============================================================
# STEP 1 - LOAD AND PREPARE CUSTOMER DATA
# ============================================================

customers = pd.read_parquet('customer_data.parquet')

# SIC levels
customers['sic_5digit'] = customers['sic_code'].astype(str).str.zfill(5)
customers['sic_2digit'] = customers['sic_5digit'].str[:2]

sic_section_lookup = {
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
    '69': 'M', '70': 'M', '71': 'M', '72': 'M',
    '73': 'M', '74': 'M', '75': 'M',
    '77': 'N', '78': 'N', '79': 'N', '80': 'N', '81': 'N', '82': 'N',
    '84': 'O',
    '85': 'P',
    '86': 'Q', '87': 'Q', '88': 'Q',
    '90': 'R', '91': 'R', '92': 'R', '93': 'R',
    '94': 'S', '95': 'S', '96': 'S',
    '97': 'T', '98': 'T',
    '99': 'U'
}

customers['sic_section'] = (customers['sic_2digit']
                             .map(sic_section_lookup)
                             .fillna('Z'))

# Log transform credit turnover
customers['log_credit_turnover'] = np.log1p(
    customers['annual_credit_turnover'].fillna(0)
)

print(f"Total customers: {len(customers):,}")

# ============================================================
# STEP 2 - KMEANS TURNOVER BANDS WITHIN EACH SIC GROUP
# ============================================================
# Compute optimal bands separately for each SIC level
# Bands are relative within the SIC group, not global
# ============================================================

def compute_kmeans_bands(sic_customers, sic_id, n_bands, min_size):
    """
    Fit KMeans on log credit turnover for one SIC group.
    Returns DataFrame with customer_id and turnover_band columns.
    Merges small bands until all meet minimum size.
    """

    n = len(sic_customers)

    # Maximum bands possible given minimum size constraint
    max_possible_bands = int(np.floor(n / min_size))
    actual_bands = min(n_bands, max_possible_bands)
    actual_bands = max(actual_bands, 1)

    # If only one band possible, assign all to band 1
    if actual_bands == 1:
        result = sic_customers[['customer_id']].copy()
        result['turnover_band'] = 1
        return result

    # Prepare turnover values
    turnover_values = (sic_customers['log_credit_turnover']
                       .fillna(sic_customers['log_credit_turnover'].median())
                       .values
                       .reshape(-1, 1))

    scaler = StandardScaler()
    turnover_scaled = scaler.fit_transform(turnover_values)

    # Fit KMeans
    kmeans = KMeans(
        n_clusters=actual_bands,
        random_state=42,
        n_init=10
    )
    cluster_labels = kmeans.fit_predict(turnover_scaled)

    # Rank clusters by centre value low to high
    centres = kmeans.cluster_centers_.flatten()
    sort_order = np.argsort(centres)
    rank_map = {old_label: new_rank
                for new_rank, old_label
                in enumerate(sort_order, 1)}

    result = sic_customers[['customer_id']].copy()
    result['turnover_band'] = [rank_map[label] for label in cluster_labels]

    # Merge bands below minimum size into nearest neighbour
    max_merge_iterations = 10
    iteration = 0

    while iteration < max_merge_iterations:

        band_sizes = result['turnover_band'].value_counts()
        small_bands = band_sizes[band_sizes < min_size]

        if len(small_bands) == 0:
            break

        if len(band_sizes) == 1:
            break

        # Find smallest band
        smallest_band = small_bands.index[0]
        all_bands_sorted = sorted(band_sizes.index.tolist())
        position = all_bands_sorted.index(smallest_band)

        # Merge with lower neighbour, or upper if at bottom
        if position > 0:
            merge_target = all_bands_sorted[position - 1]
        else:
            merge_target = all_bands_sorted[position + 1]

        result.loc[
            result['turnover_band'] == smallest_band,
            'turnover_band'
        ] = merge_target

        iteration += 1

    return result


# Compute bands for SIC 5-digit groups
sic5_counts = customers['sic_5digit'].value_counts()
sic5_with_enough = sic5_counts[
    sic5_counts >= MIN_GROUP_SIZE
].index.tolist()

sic5_band_list = []

for sic in sic5_with_enough:

    sic_df = customers[customers['sic_5digit'] == sic].copy()
    banded = compute_kmeans_bands(sic_df, sic, N_BANDS, MIN_GROUP_SIZE)
    banded['sic_5digit'] = sic
    sic5_band_list.append(banded)

sic5_bands = pd.concat(sic5_band_list, ignore_index=True)
sic5_bands = sic5_bands.rename(columns={'turnover_band': 'turnover_band_5digit'})

print(f"SIC 5-digit bands computed for "
      f"{len(sic5_with_enough):,} SIC groups")


# Compute bands for SIC 2-digit groups
sic2_counts = customers['sic_2digit'].value_counts()
sic2_with_enough = sic2_counts[
    sic2_counts >= MIN_GROUP_SIZE
].index.tolist()

sic2_band_list = []

for sic in sic2_with_enough:

    sic_df = customers[customers['sic_2digit'] == sic].copy()
    banded = compute_kmeans_bands(sic_df, sic, N_BANDS, MIN_GROUP_SIZE)
    banded['sic_2digit'] = sic
    sic2_band_list.append(banded)

sic2_bands = pd.concat(sic2_band_list, ignore_index=True)
sic2_bands = sic2_bands.rename(columns={'turnover_band': 'turnover_band_2digit'})

print(f"SIC 2-digit bands computed for "
      f"{len(sic2_with_enough):,} SIC groups")


# Compute bands for SIC section groups
section_counts = customers['sic_section'].value_counts()
section_with_enough = section_counts[
    section_counts >= MIN_GROUP_SIZE
].index.tolist()

section_band_list = []

for section in section_with_enough:

    section_df = customers[customers['sic_section'] == section].copy()
    banded = compute_kmeans_bands(
        section_df, section, N_BANDS, MIN_GROUP_SIZE
    )
    banded['sic_section'] = section
    section_band_list.append(banded)

section_bands = pd.concat(section_band_list, ignore_index=True)
section_bands = section_bands.rename(
    columns={'turnover_band': 'turnover_band_section'}
)

print(f"SIC section bands computed for "
      f"{len(section_with_enough):,} SIC sections")


# Join all band assignments back to customers
customers = customers.merge(
    sic5_bands[['customer_id', 'turnover_band_5digit']],
    on='customer_id',
    how='left'
)

customers = customers.merge(
    sic2_bands[['customer_id', 'turnover_band_2digit']],
    on='customer_id',
    how='left'
)

customers = customers.merge(
    section_bands[['customer_id', 'turnover_band_section']],
    on='customer_id',
    how='left'
)

print("\nBand assignment coverage:")
print(f"  Has 5-digit band: "
      f"{customers['turnover_band_5digit'].notna().sum():,}")
print(f"  Has 2-digit band: "
      f"{customers['turnover_band_2digit'].notna().sum():,}")
print(f"  Has section band: "
      f"{customers['turnover_band_section'].notna().sum():,}")

# ============================================================
# STEP 3 - BUILD CANDIDATE GROUP KEYS AT EACH LEVEL
# ============================================================

# Level 1: SIC 5-digit + turnover band (within SIC 5-digit)
level1_candidates = customers[
    ['customer_id', 'sic_5digit', 'turnover_band_5digit']
].copy()

level1_candidates['candidate_group'] = np.where(
    level1_candidates['turnover_band_5digit'].notna(),
    'sic5_' +
    level1_candidates['sic_5digit'].astype(str) +
    '_vol' +
    level1_candidates['turnover_band_5digit'].astype(str),
    None
)

# Level 2: SIC 5-digit only
level2_candidates = customers[['customer_id', 'sic_5digit']].copy()
level2_candidates['candidate_group'] = (
    'sic5_' + level2_candidates['sic_5digit'].astype(str) + '_all'
)

# Level 3: SIC 2-digit + turnover band (within SIC 2-digit)
level3_candidates = customers[
    ['customer_id', 'sic_2digit', 'turnover_band_2digit']
].copy()

level3_candidates['candidate_group'] = np.where(
    level3_candidates['turnover_band_2digit'].notna(),
    'sic2_' +
    level3_candidates['sic_2digit'].astype(str) +
    '_vol' +
    level3_candidates['turnover_band_2digit'].astype(str),
    None
)

# Level 4: SIC 2-digit only
level4_candidates = customers[['customer_id', 'sic_2digit']].copy()
level4_candidates['candidate_group'] = (
    'sic2_' + level4_candidates['sic_2digit'].astype(str) + '_all'
)

# Level 5: SIC section + turnover band (within section)
level5_candidates = customers[
    ['customer_id', 'sic_section', 'turnover_band_section']
].copy()

level5_candidates['candidate_group'] = np.where(
    level5_candidates['turnover_band_section'].notna(),
    'sec_' +
    level5_candidates['sic_section'].astype(str) +
    '_vol' +
    level5_candidates['turnover_band_section'].astype(str),
    None
)

# Level 6: SIC section only
level6_candidates = customers[['customer_id', 'sic_section']].copy()
level6_candidates['candidate_group'] = (
    'sec_' + level6_candidates['sic_section'].astype(str) + '_all'
)

print("\nCandidate groups built for all 6 levels")

# ============================================================
# STEP 4 - ASSIGNMENT FUNCTION
# ============================================================

def assign_level(remaining_customers,
                 level_candidates,
                 level_num,
                 customers_full,
                 min_size,
                 max_size):
    """
    Takes unassigned customers.
    Assigns those whose candidate group is valid (min to max size).
    Clusters oversized groups on log credit turnover.
    Returns assigned DataFrame.
    """

    # Filter to remaining customers only
    level_remaining = remaining_customers.merge(
        level_candidates,
        on='customer_id',
        how='left'
    )

    # Drop rows where candidate group is null
    # (happens when band wasn't computable)
    level_remaining = level_remaining[
        level_remaining['candidate_group'].notna()
    ]

    if len(level_remaining) == 0:
        print(f"  Level {level_num}: no valid candidates")
        return pd.DataFrame(
            columns=['customer_id', 'peer_group_id', 'peer_group_level']
        )

    # Group sizes
    level_sizes = (level_remaining
                   .groupby('candidate_group')['customer_id']
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

    # Oversized groups - cluster on turnover
    oversized_groups = level_sizes[
        level_sizes['group_size'] > max_size
    ]['candidate_group'].tolist()

    oversized_customers = level_remaining[
        level_remaining['candidate_group'].isin(oversized_groups)
    ][['customer_id', 'candidate_group']].copy()

    oversized_customers = oversized_customers.merge(
        customers_full[['customer_id', 'log_credit_turnover']],
        on='customer_id',
        how='left'
    )

    clustered_list = []

    for group_id in oversized_groups:

        group_df = oversized_customers[
            oversized_customers['candidate_group'] == group_id
        ].copy()

        n = len(group_df)
        n_clusters = min(
            int(np.ceil(n / max_size)),
            int(np.floor(n / min_size)),
            10
        )
        n_clusters = max(n_clusters, 2)

        turnover_values = (group_df['log_credit_turnover']
                           .fillna(group_df['log_credit_turnover'].median())
                           .values
                           .reshape(-1, 1))

        scaler = StandardScaler()
        turnover_scaled = scaler.fit_transform(turnover_values)

        kmeans = KMeans(
            n_clusters=n_clusters,
            random_state=42,
            n_init=10
        )
        cluster_labels = kmeans.fit_predict(turnover_scaled)

        centres = kmeans.cluster_centers_.flatten()
        sort_order = np.argsort(centres)
        rank_map = {old: new
                    for new, old
                    in enumerate(sort_order, 1)}

        clustered = group_df[['customer_id']].copy()
        clustered['peer_group_id'] = (
            group_id + '_split' +
            pd.Series([rank_map[l] for l in cluster_labels])
            .astype(str)
            .values
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

    print(f"  Level {level_num} "
          f"({'|'.join(level_candidates.columns[1:].tolist())}): "
          f"{len(level_assigned):,} assigned")

    return level_assigned

# ============================================================
# STEP 5 - RUN ASSIGNMENT ACROSS ALL LEVELS
# ============================================================

all_assigned_list = []

# Level 1
remaining = customers[['customer_id']].copy()

level1_assigned = assign_level(
    remaining, level1_candidates, 1,
    customers, MIN_GROUP_SIZE, MAX_GROUP_SIZE
)
all_assigned_list.append(level1_assigned)

# Level 2
remaining = customers[
    ~customers['customer_id'].isin(
        level1_assigned['customer_id']
    )
][['customer_id']].copy()

level2_assigned = assign_level(
    remaining, level2_candidates, 2,
    customers, MIN_GROUP_SIZE, MAX_GROUP_SIZE
)
all_assigned_list.append(level2_assigned)

# Level 3
remaining = customers[
    ~customers['customer_id'].isin(
        pd.concat(all_assigned_list)['customer_id']
    )
][['customer_id']].copy()

level3_assigned = assign_level(
    remaining, level3_candidates, 3,
    customers, MIN_GROUP_SIZE, MAX_GROUP_SIZE
)
all_assigned_list.append(level3_assigned)

# Level 4
remaining = customers[
    ~customers['customer_id'].isin(
        pd.concat(all_assigned_list)['customer_id']
    )
][['customer_id']].copy()

level4_assigned = assign_level(
    remaining, level4_candidates, 4,
    customers, MIN_GROUP_SIZE, MAX_GROUP_SIZE
)
all_assigned_list.append(level4_assigned)

# Level 5
remaining = customers[
    ~customers['customer_id'].isin(
        pd.concat(all_assigned_list)['customer_id']
    )
][['customer_id']].copy()

level5_assigned = assign_level(
    remaining, level5_candidates, 5,
    customers, MIN_GROUP_SIZE, MAX_GROUP_SIZE
)
all_assigned_list.append(level5_assigned)

# Level 6
remaining = customers[
    ~customers['customer_id'].isin(
        pd.concat(all_assigned_list)['customer_id']
    )
][['customer_id']].copy()

level6_assigned = assign_level(
    remaining, level6_candidates, 6,
    customers, MIN_GROUP_SIZE, MAX_GROUP_SIZE
)
all_assigned_list.append(level6_assigned)

# ============================================================
# STEP 6 - HANDLE UNCLASSIFIABLE
# ============================================================

all_assigned = pd.concat(all_assigned_list, ignore_index=True)

unclassifiable = customers[
    ~customers['customer_id'].isin(all_assigned['customer_id'])
][['customer_id']].copy()

unclassifiable['peer_group_id'] = 'unclassifiable'
unclassifiable['peer_group_level'] = 99

print(f"\nUnclassifiable: {len(unclassifiable):,}")

# ============================================================
# STEP 7 - COMBINE AND VALIDATE
# ============================================================

peer_groups_final = pd.concat(
    [all_assigned, unclassifiable],
    ignore_index=True
)

group_sizes_final = (peer_groups_final
                     .groupby('peer_group_id')['customer_id']
                     .count()
                     .reset_index()
                     .rename(columns={'customer_id': 'group_size'}))

level_summary = (peer_groups_final
                 .groupby('peer_group_level')['customer_id']
                 .count()
                 .reset_index()
                 .rename(columns={'customer_id': 'n_customers'}))

level_labels = {
    1: 'SIC 5-digit + KMeans turnover band',
    2: 'SIC 5-digit only',
    3: 'SIC 2-digit + KMeans turnover band',
    4: 'SIC 2-digit only',
    5: 'SIC section + KMeans turnover band',
    6: 'SIC section only',
    99: 'Unclassifiable'
}
level_summary['description'] = (level_summary['peer_group_level']
                                 .map(level_labels))

print("\n=== FINAL PEER GROUP SUMMARY ===")
print(f"Total customers:   {len(peer_groups_final):,}")
print(f"Total peer groups: {group_sizes_final['peer_group_id'].nunique():,}")
print(f"Min group size:    {group_sizes_final['group_size'].min()}")
print(f"Max group size:    {group_sizes_final['group_size'].max()}")
print(f"Mean group size:   {group_sizes_final['group_size'].mean():.0f}")
print(f"\nGroups below {MIN_GROUP_SIZE}: "
      f"{(group_sizes_final['group_size'] < MIN_GROUP_SIZE).sum()}")
print(f"Groups above {MAX_GROUP_SIZE}: "
      f"{(group_sizes_final['group_size'] > MAX_GROUP_SIZE).sum()}")
print(f"\nLevel distribution:")
print(level_summary.to_string(index=False))

# ============================================================
# STEP 8 - SAVE
# ============================================================

peer_groups_final.to_parquet('peer_groups.parquet', index=False)
group_sizes_final.to_parquet('peer_group_sizes.parquet', index=False)

print("\nSaved: peer_groups.parquet")
print("Saved: peer_group_sizes.parquet")
```

## What Changed From The Previous Version

**KMeans bands are computed within each SIC group** at all three SIC levels — 5-digit, 2-digit, and section — separately. A hairdresser's band 3 is relative to other hairdressers. A manufacturer's band 3 is relative to other manufacturers. No global skew problem.

**Three separate band columns** on the customers DataFrame — one per SIC level — so each level of the hierarchy uses the band computed at the appropriate SIC granularity.

**Null bands are handled explicitly** — if a SIC group doesn't have enough customers to band, the candidate group is set to None and filtered out, falling through to the next level naturally.

Everything else — the hierarchy logic, the oversized group splitting, the unclassifiable fallback — is unchanged from before but written as clear sequential steps with separate DataFrames throughout.