# Metric definitions for the lifecycle analysis (draft for group agreement)

Scope: how each per-repository activity metric is defined in `lifecycle_analysis.ipynb`.
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
  `ai_label_final`, and the full AI-cohort wiring is deferred to the next round.
- `repo_created_at` is needed for every cohort repository. It is currently available for the pilot
  repositories only; the full candidate list is pending from B.
- The `YEAR` switch in section 12 is **declared but not yet wired**: changing it only changes the
  printed label, it does not switch the cohort, created-date range, activity table or coverage list.
  Wiring the two-year switch is a next-round task.

## Round 2 requirements (fixed-cohort 90-day analysis, not yet implemented)

- Fix one AI cohort per year and track that **same** list across all three bands. Do not re-select
  active repositories per band, and do not drop a repository that has no activity after day 60.
- Every cohort repository must keep a row in all three bands. A band with a fully covered window but
  no events is a real **0**, not a missing value.
- Use the per-repository **coverage list** to tell the two apart: data fully processed but no event
  -> 0; data not fetched yet / archive missing / processing failed -> **observation incomplete**,
  not zero.
- Official comparisons use the same set of repositories with a complete 90-day observation as the
  denominator, and report how many were excluded as incomplete.
