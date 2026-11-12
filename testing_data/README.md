# Testing Data for the fixed-cohort 90-day analysis

**This folder is fully synthetic.** Repository ids, AI labels and activity are made up. It exists
only to check that the analysis program produces the expected numbers. It must never be mixed into
real statistics or reported as a result.

Regenerate with:

```text
python c_lifecycle_analysis/build_testing_data.py
```

The analysis entry point is `c_lifecycle_analysis/cohort_analysis.py`; the worked example that reads
these files and compares the computed values against the expectations below is
`c_lifecycle_analysis/cohort_90d_analysis.ipynb`.

## Layout

```text
testing_data/
├── README.md                       # this file
├── 2024/
│   ├── repo_metadata.csv
│   ├── repo_ai_labels_analysis.csv
│   ├── repo_daily_counts.parquet
│   ├── coverage.json               # complete coverage
│   └── coverage_missing.json       # deliberately incomplete
└── 2026/                           # same five files, different repo ids and counts
```

All files follow the "Testing Data input interface" contract: metadata and labels are joined on
`repo_id` (never on name or row order), the daily table key is `repo_id + event_date + event_type`,
and `label_source = testing`, `rule_version = testing_v1`.

## What is constructed

Each year holds **11 metadata rows**: 4 repositories that pass every filter and 7 controls that must
be rejected. The two years use different repository ids and different event counts, so the year
switch provably reads different inputs.

### The 4 included repositories (the fixed cohort)

| repo_id | role | created (UTC, with time of day) |
|---|---|---|
| `...001` | early activity, then decline | 2024-04-01 12:00 / 2026-04-01 08:00 |
| `...002` | sustained activity in every band | 2024-04-02 09:30 / 2026-04-02 18:30 |
| `...003` | gradually growing | 2024-04-03 23:45 / 2026-04-03 06:15 |
| `...004` | completely inactive (no event rows at all) | 2024-04-04 00:05 / 2026-04-04 22:40 |

(`...001` is the 2024 prefix `900000000000000` / 2026 prefix `910000000000000`; `...091` etc. below
follow the same prefixes.) Every included repository is tracked in **all three** bands even when it
has no activity, so `...004` stays in the cohort and drags the active ratio below 100%.

### The 7 control repositories (must be excluded)

| repo_id | what it tests | expected handling |
|---|---|---|
| `...091` | `ai_label_final = excluded` | excluded |
| `...092` | `ai_label_final = uncertain` | uncertain |
| `...093` | empty label | no label |
| `...094` | `fetch_status = error` | invalid metadata |
| `...096` | `api_repo_id` inconsistent with `repo_id` | invalid metadata |
| `...097` | empty `repo_created_at` | invalid metadata |
| `...095` | created 05-15, outside the 04-01..04-30 range | out of range |

Controls `...091`, `...092`, `...093` and `...095` still have activity rows in the daily table, to
confirm the analysis filters by the fixed list rather than by "who has events".

### Boundary days

Creation times carry a time of day on purpose, so the UTC-day arithmetic is exercised. The events sit
on the band edges:

| created | day 1 | day 30 | day 31 | day 60 | day 61 | day 90 | day 91 |
|---|---|---|---|---|---|---|---|
| 2024-04-01 | 04-01 | 04-30 | 05-01 | 05-30 | 05-31 | 06-29 | 06-30 |
| 2024-04-02 | 04-02 | 05-01 | 05-02 | 05-31 | 06-01 | 06-30 | 07-01 |
| 2024-04-03 | 04-03 | 05-02 | 05-03 | 06-01 | 06-02 | 07-01 | 07-02 |
| 2024-04-04 | 04-04 | 05-03 | 05-04 | 06-02 | 06-03 | 07-02 | 07-03 |

`...001` also has one event **before** creation (2024-03-31) and events **after** day 90 (2024-06-30
for `...001`, 2024-07-02 for `...003`). These must be reported separately and never folded into a
band.

### Coverage

`coverage.json` requests **2024-04-01 .. 2024-07-28** (119 days = 2856 hours), all verified. This
single window contains day 1..90 for every cohort repository.

`coverage_missing.json` additionally drops **07-01 .. 07-05** (120 hours). Those days fall inside the
day-61-90 window of `...003` and `...004` only, so only that band becomes incomplete.

## Expected results

The program must **compute** these from the inputs; the notebook asserts computed == expected, and
the expected numbers are never used as the result.

### 2024, complete coverage - per repository x band

Tuple order: `(total_events, active_days, push_events, issue_events, issue_comment_events, pr_events)`.

| repo_id | band | total_events | active_days | push | issue | issue_comment | pr |
|---|---|---|---|---|---|---|---|
| ...001 | day_1_30 | 12 | 4 | 9 | 3 | 0 | 0 |
| ...001 | day_31_60 | 1 | 1 | 1 | 0 | 0 | 0 |
| ...001 | day_61_90 | 0 | 0 | 0 | 0 | 0 | 0 |
| ...002 | day_1_30 | 5 | 3 | 3 | 0 | 0 | 2 |
| ...002 | day_31_60 | 3 | 3 | 1 | 1 | 0 | 1 |
| ...002 | day_61_90 | 3 | 3 | 3 | 0 | 0 | 0 |
| ...003 | day_1_30 | 2 | 2 | 1 | 0 | 1 | 0 |
| ...003 | day_31_60 | 5 | 3 | 3 | 1 | 1 | 0 |
| ...003 | day_61_90 | 10 | 3 | 9 | 0 | 0 | 1 |
| ...004 | day_1_30 | 0 | 0 | 0 | 0 | 0 | 0 |
| ...004 | day_31_60 | 0 | 0 | 0 | 0 | 0 | 0 |
| ...004 | day_61_90 | 0 | 0 | 0 | 0 | 0 | 0 |

Exclusions reported for 2024: `invalid_metadata_rows = 3`, `no_label = 1`, `uncertain = 1`,
`excluded = 1`, `out_of_range = 1`, `cohort_size = 4`.

Out-of-band events: `...001` pre-creation 1, beyond day 90 = 1; `...003` beyond day 90 = 2.

### 2024, complete coverage - cohort summary per band

| band | cohort_size | complete_90d | not_complete_90d | active | active_ratio | total_events | events_median | events_q25 | events_q75 | active_days_median | active_days_q25 | active_days_q75 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| day_1_30 | 4 | 4 | 0 | 3 | 0.75 | 19 | 3.5 | 1.50 | 6.75 | 2.5 | 1.50 | 3.25 |
| day_31_60 | 4 | 4 | 0 | 3 | 0.75 | 9 | 2.0 | 0.75 | 3.50 | 2.0 | 0.75 | 3.00 |
| day_61_90 | 4 | 4 | 0 | 2 | 0.50 | 13 | 1.5 | 0.00 | 4.75 | 1.5 | 0.00 | 3.00 |

Here all 4 repositories are covered for the whole 90 days, so the official denominator is 4 in every
band. The ratio uses that **fixed set** (not just the repositories with events): in day_61_90 only
`...002` and `...003` are active, so the ratio is 2/4 = 0.50. Zero-activity `...004` still counts in
the denominator.

### 2026, complete coverage

Per repository x band (same tuple order):

| repo_id | band | total_events | active_days | push | issue | issue_comment | pr |
|---|---|---|---|---|---|---|---|
| ...001 | day_1_30 | 4 | 2 | 3 | 1 | 0 | 0 |
| ...001 | day_31_60 | 1 | 1 | 1 | 0 | 0 | 0 |
| ...001 | day_61_90 | 0 | 0 | 0 | 0 | 0 | 0 |
| ...002 | day_1_30 | 4 | 1 | 4 | 0 | 0 | 0 |
| ...002 | day_31_60 | 2 | 1 | 2 | 0 | 0 | 0 |
| ...002 | day_61_90 | 2 | 1 | 2 | 0 | 0 | 0 |
| ...003 | day_1_30 | 1 | 1 | 0 | 0 | 1 | 0 |
| ...003 | day_31_60 | 3 | 1 | 0 | 0 | 0 | 3 |
| ...003 | day_61_90 | 7 | 1 | 7 | 0 | 0 | 0 |
| ...004 | day_1_30 | 0 | 0 | 0 | 0 | 0 | 0 |
| ...004 | day_31_60 | 0 | 0 | 0 | 0 | 0 | 0 |
| ...004 | day_61_90 | 0 | 0 | 0 | 0 | 0 | 0 |

Cohort summary per band:

| band | cohort_size | complete_90d | not_complete_90d | active | active_ratio | total_events | events_median | active_days_median |
|---|---|---|---|---|---|---|---|---|
| day_1_30 | 4 | 4 | 0 | 3 | 0.75 | 9 | 2.5 | 1.0 |
| day_31_60 | 4 | 4 | 0 | 3 | 0.75 | 6 | 1.5 | 1.0 |
| day_61_90 | 4 | 4 | 0 | 2 | 0.50 | 9 | 1.0 | 0.5 |

The 2024 and 2026 cohorts share no repository id, and the counts differ - the year switch really
switches all four input files and the created-date range.

### Incomplete coverage (`coverage_missing.json`)

For both years, band day_61_90 of the missing variant:

| repo_id | required_days | covered_days | coverage_status | counts_are_observed_only |
|---|---|---|---|---|
| ...001 | 30 | 30 | complete | False |
| ...002 | 30 | 30 | complete | False |
| ...003 | 30 | 29 | incomplete | True |
| ...004 | 30 | 28 | incomplete | True |

Cohort summary, 2024 with missing coverage - the official set is now the 2 repositories covered for
the whole 90 days, so `complete_90d_repos = 2` and `not_complete_90d_repos = 2` in **every** band:

| band | complete_90d | not_complete_90d | active | active_ratio | total_events |
|---|---|---|---|---|---|
| day_1_30 | 2 | 2 | 2 | 1.00 | 17 |
| day_31_60 | 2 | 2 | 2 | 1.00 | 4 |
| day_61_90 | 2 | 2 | 1 | 0.50 | 3 |

Repositories are **kept** in the table; the incomplete band is only flagged. `...003` and `...004`
lose their day-61-90 coverage, so they leave the fixed 90-day set - and therefore drop out of the
ratio in *all three* bands, not just day_61_90. The band-1 and band-2 counts for the official set
(`...001`: 12 and 1 events; `...002`: 5 and 3) stay visible in the per-repository table, and an
unobserved band is never treated as zero activity.

### No repository covered for the whole 90 days

If the fixed 90-day set is **empty**, the ratio, the event total and the quantiles must be **not
computable** (`NaN`), never 0%. This is checked by dropping the June days, which breaks the day-61-90
window of all four repositories:

| band | complete_90d | not_complete_90d | active | active_ratio | total_events |
|---|---|---|---|---|---|
| day_1_30 | 0 | 4 | 0 | NaN | NaN |
| day_31_60 | 0 | 4 | 0 | NaN | NaN |
| day_61_90 | 0 | 4 | 0 | NaN | NaN |

## Regenerating and re-checking

1. `python c_lifecycle_analysis/build_testing_data.py` rewrites the five files for each year.
2. Open `c_lifecycle_analysis/cohort_90d_analysis.ipynb` and run it end to end. It reads these files,
   computes the per-repository and cohort tables, and asserts every value above. Any mismatch stops
   the run.
3. The computed tables and figures are written to `c_lifecycle_analysis/testing_results/`.
