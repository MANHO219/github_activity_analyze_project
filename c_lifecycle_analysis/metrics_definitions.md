# Metric definitions for the lifecycle analysis (draft for group agreement)

Scope: how each per-repository activity metric is defined. The first-pass metrics live in
`lifecycle_analysis.ipynb`; the fixed-cohort 90-day analysis lives in `cohort_analysis.py`.
All metrics are computed per repository, grouped later into fixed-cohort **90-day age bands**
(days 1-30 / 31-60 / 61-90 since creation, counted on **UTC calendar days**).

Two different units are kept separate on purpose:

- **event counts** — how many activities were observed;
- **active days** — on how many distinct days an activity was observed.

A count and a day count are not interchangeable. A repository with 100 events on one day has
`total_events = 100` but `active_days = 1`.

Issue and PR activity are split on purpose. `IssueCommentEvent` is kept separate from
`issue_events` because a comment can land under a pull request as well as under an issue;
counting it with issues would inflate issue activity.

| Metric | Unit | Definition | Fields needed |
|---|---|---|---|
| `total_events` | events | sum of `event_count` for the repository | `repo_id`, `event_count` |
| `push_events` | events | sum of `event_count` where `event_type == "PushEvent"` | `event_type` |
| `issue_events` | events | sum of `IssuesEvent` only (issue open/close actions) | `event_type` |
| `issue_comment_events` | events | sum of `IssueCommentEvent` only | `event_type` |
| `pr_events` | events | sum of `PullRequestEvent` + `PullRequestReviewEvent` + `PullRequestReviewCommentEvent` | `event_type` |
| `active_days` | days | number of distinct `event_date` values with activity | `event_date` |

## Computation

The metrics are produced by `repo_metrics(daily)` on the aggregated table
`repo_id × event_date × event_type × event_count`:

1. pivot the table so each repository is a row and each event type is a column;
2. `total_events` = row sum;
3. `push_events` = the `PushEvent` column;
4. `issue_events` = `IssuesEvent`; `issue_comment_events` = `IssueCommentEvent`;
   `pr_events` = sum of the three PR-related types;
5. `active_days` = distinct `event_date` count per repository.

The aggregate is checked against the raw table: the sum of `total_events` must equal the sum of
`event_count` (verified: 5,528,300 on 2024-01-15).

## Age bands (UTC natural days)

The 90-day lifecycle analysis groups each repository's activity into three bands: **day 1-30**,
**day 31-60** and **day 61-90** since creation.

- Both the creation time (`repo_created_at`) and the activity time are converted to a **UTC
  calendar day** by dropping the time-of-day part (`pd.Timestamp(...).normalize()` for a single
  value, `Series.dt.normalize()` for a column).
- The **creation day counts as day 1**, so `age_day = (activity_utc_date - creation_utc_date).days + 1`.
- Band boundaries use that 1-based day: `1 <= age_day <= 30`, `31 <= age_day <= 60`,
  `61 <= age_day <= 90`.
- Example: a repository created on **4 April** has its day 30 on **3 May**; **1 May** is day 28
  (still band 1) and **4 May** is day 31 (band 2 starts). The earlier code subtracted the raw
  timestamps, so the time-of-day part shifted the boundary and could place a same-day activity
  before creation.
- Activity **before** the creation date is reported as `pre_creation`; activity **after** day 90 is
  reported as `beyond_90`. Neither is silently folded into a band.

## Conventions that the group still needs to confirm

- **Issue vs. comment split (decided for this version)**: `issue_events` counts `IssuesEvent`
  only; `IssueCommentEvent` is reported as `issue_comment_events` because it can also occur under
  pull requests. If the group prefers a different grouping, change the type list in
  `repo_metrics()` and re-run.
- **PR events**: whether to include the two review events, or count only `PullRequestEvent`.
- **Bots**: whether to keep bot actors. The event table keeps all actors; the actor fields
  (`actor_id`, `actor_login`) are available if a bot filter is wanted later.
- **`active_days` window**: which days count as "observed". Days inside a longer window with no
  events must not be read as "the repository was abandoned"; they only mean no public activity was
  observed in the data.

## Limits of the current data

- One `PushEvent` is not one commit. A push can carry several commits in its payload, which is not
  in the current event table.
- `active_days` is 1 for every repository on the single-day 2024-01-15 table. The current one-week
  package (7 UTC days) is the first window where `active_days` spans more than one day; it is still
  far shorter than the 90 days the lifecycle bands need.
- The 90-day age-band function in section 12 is exercised on a **convenience sample** (a few pilot
  repositories with a valid creation time), selected mainly by creation time. It is a **general
  workflow demonstration**, not an AI-cohort result: the repositories are not filtered by
  `ai_label_final`. The full AI-cohort wiring now lives in `cohort_analysis.py` (see
  "Fixed-cohort 90-day analysis" below).
- `repo_created_at` is needed for every cohort repository. It is currently available for the pilot
  repositories only; the full candidate list is pending from B.
- The `YEAR` switch in section 12 of `lifecycle_analysis.ipynb` is **declared but not wired**:
  changing it only changes the printed label. The working two-year switch is in `cohort_analysis.py`,
  where the year changes the four input files and the created-date range together.

## Fixed-cohort 90-day analysis (round 2)

Implemented in `cohort_analysis.py` and demonstrated in `cohort_90d_analysis.ipynb`; the synthetic
inputs and their expected values are in `testing_data/README.md`.

### The fixed cohort

- One cohort per year. A repository joins the cohort when its metadata is valid
  (`fetch_status = ok`, `api_repo_id` consistent with `repo_id`, `repo_created_at` parseable), its
  `ai_label_final = included`, and its **UTC** creation date falls inside the inclusive
  `created_from .. created_to` range.
- The list is fixed once and then tracked across **all three** bands. Repositories are never
  re-selected per band and never dropped for having no activity later.
- Rejected repositories are reported separately, not silently: invalid metadata, no label,
  `uncertain`, `excluded`, and out of range.

### Bands and out-of-band activity

- The three bands are **day 1-30**, **day 31-60** and **day 61-90** since creation, on **UTC natural
  days** with the creation day counted as day 1 (same rule as "Age bands" above).
- Activity **before** creation and **after** day 90 is reported as `pre_creation` / `beyond_90` and
  is never folded into a band.

### Per-repository stage table

Every cohort repository gets exactly **three** rows (one per band), even when a band has no activity
- this is an aggregation row, not extra raw events. Beyond the six metrics above, each row carries:

| Field | Meaning |
|---|---|
| `band`, `band_day_start`, `band_day_end` | which band, and its 1-based day bounds |
| `required_days` | UTC days the band needs (30, or fewer for a truncated band) |
| `covered_days` | how many of those days the coverage list confirms as fully processed |
| `band_complete` | whether **all** required days are covered |
| `coverage_status` | `complete` / `incomplete` |
| `counts_are_observed_only` | `True` when the band is incomplete, so the counts are only the observed part |

A band whose window is **fully covered** and has no events is a real **0**. A band that is **not
fully covered** is **observation incomplete** and its counts are marked observed-only - it must not
be read as "the repository was inactive".

### Cohort summary and the active ratio

Grouped by year x band, over the fixed cohort:

- `cohort_size`, `complete_90d_repos`, `not_complete_90d_repos`, `active_repos`;
- `active_ratio`, `total_events_sum`, and the median / q25 / q75 of `total_events` and `active_days`.

`active_ratio` = active repositories / `complete_90d_repos`. `complete_90d_repos` is the **fixed
official denominator**: the cohort repositories whose whole 90-day window was fully covered
(complete in *every* band). It is the **same set** for all three bands, so the bands stay comparable
and a repository missing coverage in one band leaves the ratio in all three. Repositories that fall
short are counted in `not_complete_90d_repos` and never enter the ratio or the distributions;
fully-covered zero-activity repositories stay in the denominator and in the distribution. When no
repository is covered for the whole 90 days the set is empty, so `active_ratio`, `total_events_sum`
and the quantiles are **not computable** (`NaN`), never 0%.
