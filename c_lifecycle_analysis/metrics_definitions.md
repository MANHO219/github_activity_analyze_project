# Metric definitions for the lifecycle analysis (draft for group agreement)

Scope: how each per-repository activity metric is defined in `lifecycle_analysis.ipynb`.
All metrics are computed per repository, grouped later by age month (calendar months since creation).

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
- `active_days` is 1 for every repository on the current table because it covers a single day
  (2024-01-15). It only becomes meaningful once the observation window spans several days or months.
- Age month is defined from the repository's own `repo_created_at`, not the calendar month, and only
  repositories whose whole first 12 months fall inside the observation window can be compared over a
  full year. `repo_created_at` is currently available for 50 pilot repositories only.
