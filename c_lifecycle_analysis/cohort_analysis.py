"""Fixed-cohort lifecycle analysis for AI-related GitHub repositories.

The default stays 3 x 30 days for existing notebooks. Pass window_days=7 for
3 x 7 days; denominator fields and out-of-window checks follow that horizon.

Round-2 configurable entry point. It takes a fixed AI repository cohort and
tracks each repository over the three bands after its creation:

    day 1-30   (creation day = day 1)
    day 31-60
    day 61-90

The cohort is fixed once and never re-selected per band: a repository that has
no activity after day 60 stays in the list. A band with a fully covered window
and no events is a real ``0``; a band whose source days were not fully processed
is marked ``incomplete`` and is not silently read as zero activity.

The official cohort comparison uses **one fixed denominator for all three
bands**: the cohort repositories whose whole 90-day window was fully covered
(complete in every band). Repositories that fall short are reported next to it
and never enter the active ratio or the distributions; when that set is empty
the ratio and the totals are not computable (``NaN``), never 0.

All day arithmetic uses UTC calendar days (time-of-day is dropped before the
subtraction), consistent with ``age_band_metrics`` in the round-1 notebook.

Inputs (four files, see ``C_分析修订与双年份准备.md`` for the contract):

* ``repo_metadata.csv``            - one row per repo, incl. ``repo_created_at``
* ``repo_ai_labels_analysis.csv``  - one row per repo, ``ai_label_final``
* ``repo_daily_counts.parquet``    - repo x UTC date x event type x count
* ``coverage.json``                - which hours were fully processed
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

# name, first age day, last age day (creation day counts as day 1)
def bands_for(window_days=30):
    """Three equal windows; creation day is day 1. Default preserves 90-day APIs."""
    if type(window_days) is not int or window_days <= 0:
        raise InputError("window_days must be a positive integer")
    return tuple((f"day_{i * window_days + 1}_{(i + 1) * window_days}",
                  i * window_days + 1, (i + 1) * window_days) for i in range(3))


BANDS = bands_for()

BAND_ORDER = [name for name, _, _ in BANDS]

PUSH_TYPES = frozenset({"PushEvent"})
ISSUE_TYPES = frozenset({"IssuesEvent"})
ISSUE_COMMENT_TYPES = frozenset({"IssueCommentEvent"})
PR_TYPES = frozenset(
    {"PullRequestEvent", "PullRequestReviewEvent", "PullRequestReviewCommentEvent"}
)

DAILY_COLUMNS = ["repo_id", "event_date", "event_type", "event_count"]

# columns of the per-repository, per-band intermediate table
STAGE_COLUMNS = [
    "cohort_year",
    "data_kind",
    "repo_id",
    "repo_created_at",
    "band",
    "band_day_start",
    "band_day_end",
    "required_days",
    "covered_days",
    "band_complete",
    "coverage_status",
    "counts_are_observed_only",
    "total_events",
    "active_days",
    "push_events",
    "issue_events",
    "issue_comment_events",
    "pr_events",
]


class InputError(ValueError):
    """Raised when an input table violates the documented contract."""


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def to_utc_day(value) -> pd.Timestamp:
    """Return the UTC calendar day of a timestamp-like value (naive Timestamp)."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.normalize()


def series_to_utc_day(series: pd.Series) -> pd.Series:
    """Vectorised ``to_utc_day`` for a Series of date strings/timestamps."""
    out = pd.to_datetime(series, utc=True, errors="coerce")
    return out.dt.tz_localize(None).dt.normalize()


def _require_unique(df: pd.DataFrame, column: str, name: str) -> None:
    dup = df[column].duplicated().sum()
    if dup:
        raise InputError(f"{name}: column '{column}' must be unique, found {dup} duplicates")


def read_daily_counts(path) -> pd.DataFrame:
    """Read the daily activity table; CSV and Parquet share one code path."""
    path = Path(path)
    if not path.exists():
        raise InputError(f"daily counts file not found: {path}")
    if path.suffix.lower() in {".parquet", ".pq"}:
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    missing = [c for c in DAILY_COLUMNS if c not in df.columns]
    if missing:
        raise InputError(f"daily counts table is missing columns: {missing}")

    df = df[DAILY_COLUMNS].copy()
    df["event_date"] = pd.to_datetime(df["event_date"], utc=True, errors="coerce")
    if df["event_date"].isna().any():
        raise InputError("daily counts table has unparseable event_date values")
    if (df["event_count"] < 0).any() or not pd.api.types.is_integer_dtype(df["event_count"]):
        raise InputError("event_count must be a non-negative integer")
    if df["event_type"].isna().any():
        raise InputError("event_type must not be empty")
    if df.duplicated(["repo_id", "event_date", "event_type"]).any():
        raise InputError("daily counts table has duplicate repo_id+event_date+event_type keys")

    df["event_date"] = df["event_date"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    return df


def read_coverage(path) -> dict:
    path = Path(path)
    if not path.exists():
        raise InputError(f"coverage file not found: {path}")
    coverage = json.loads(path.read_text(encoding="utf-8"))
    for field in ("requested_days", "requested_hours", "verified_hours", "missing_source_hours"):
        if field not in coverage:
            raise InputError(f"coverage is missing required field '{field}'")

    requested_days = sorted({to_utc_day(d) for d in coverage["requested_days"]})
    missing_days = sorted({to_utc_day(h) for h in coverage["missing_source_hours"]})
    missing_set = set(missing_days)

    # parsed, ready-to-use views of the raw JSON fields
    coverage["requested_days_parsed"] = requested_days
    coverage["missing_days"] = missing_days
    coverage["complete_days"] = [d for d in requested_days if d not in missing_set]

    expected_hours = len(requested_days) * 24
    if int(coverage["requested_hours"]) != expected_hours:
        raise InputError(
            "coverage requested_hours must equal len(requested_days) * 24 "
            f"({coverage['requested_hours']} != {expected_hours})"
        )
    verified = int(coverage["verified_hours"])
    if verified != expected_hours - len(coverage["missing_source_hours"]):
        raise InputError("coverage verified_hours must equal requested_hours - missing hours")

    outside = [d for d in missing_days if d not in set(requested_days)]
    if outside:
        raise InputError(f"missing_source_hours outside requested_days: {outside[:3]}")
    return coverage


# --------------------------------------------------------------------------- #
# cohort selection
# --------------------------------------------------------------------------- #
def select_cohort(metadata, labels, cohort_year, created_from, created_to):
    """Fix the cohort: valid metadata + ``ai_label_final == included`` + date range.

    Returns ``(cohort, exclusions)``. ``cohort`` is one row per repository with
    ``repo_id``, ``repo_created_at`` and ``repo_created_day``. Excluded groups are
    counted, never silently dropped.
    """
    _require_unique(metadata, "repo_id", "repo_metadata.csv")
    if labels["repo_id"].duplicated().any():
        raise InputError("repo_ai_labels_analysis.csv must hold at most one row per repo_id")

    meta = metadata.copy()
    meta["repo_created_parsed"] = pd.to_datetime(
        meta["repo_created_at"], utc=True, errors="coerce"
    )

    reasons = {}
    if "fetch_status" in meta.columns:
        bad_status = meta["fetch_status"].astype("string").str.strip().str.lower().isin(["ok", "ok_cached"]).eq(False)
        reasons["fetch_status_not_ok"] = int(bad_status.sum())
    else:
        bad_status = pd.Series(False, index=meta.index)
        reasons["fetch_status_not_ok"] = 0

    if "api_repo_id" in meta.columns:
        api = pd.to_numeric(meta["api_repo_id"], errors="coerce")
        bad_api = api.ne(meta["repo_id"])
        reasons["api_repo_id_mismatch"] = int(bad_api.sum())
    else:
        bad_api = pd.Series(False, index=meta.index)
        reasons["api_repo_id_mismatch"] = 0

    bad_created = meta["repo_created_parsed"].isna()
    reasons["creation_time_unparseable"] = int(bad_created.sum())

    meta_valid = meta[~(bad_status | bad_api | bad_created)].copy()
    reasons["invalid_metadata_rows"] = int(len(meta) - len(meta_valid))
    reasons["invalid_metadata_repo_ids"] = sorted(
        meta.loc[bad_status | bad_api | bad_created, "repo_id"].tolist()
    )

    joined = meta_valid.merge(
        labels[["repo_id", "ai_label_final"]], on="repo_id", how="left"
    )
    joined["ai_label_final"] = joined["ai_label_final"].astype("string").fillna("").str.strip()

    missing_label = joined["ai_label_final"].eq("")
    reasons["no_label"] = int(missing_label.sum())

    uncertain = joined["ai_label_final"].eq("uncertain")
    reasons["uncertain"] = int(uncertain.sum())

    excluded_label = joined["ai_label_final"].eq("excluded")
    reasons["excluded"] = int(excluded_label.sum())

    included = joined[joined["ai_label_final"].eq("included")].copy()
    included["repo_created_day"] = (
        included["repo_created_parsed"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    )

    start = to_utc_day(created_from)
    end = to_utc_day(created_to)
    if end < start:
        raise InputError("created_to must not be earlier than created_from")
    if start.year != int(cohort_year) or end.year != int(cohort_year):
        raise InputError("Creation range must belong to cohort_year")

    in_range = included["repo_created_day"].between(start, end)
    reasons["out_of_range"] = int((~in_range).sum())
    reasons["out_of_range_repo_ids"] = sorted(included.loc[~in_range, "repo_id"].tolist())

    cohort = (
        included.loc[in_range, ["repo_id", "repo_created_parsed", "repo_created_day"]]
        .rename(columns={"repo_created_parsed": "repo_created_at"})
        .sort_values("repo_id")
        .reset_index(drop=True)
    )
    reasons["cohort_size"] = int(len(cohort))
    return cohort, reasons


# --------------------------------------------------------------------------- #
# per-repository, per-band intermediate table
# --------------------------------------------------------------------------- #
def _band_totals(rows: pd.DataFrame) -> dict:
    """Aggregate one repo's events inside one band into the metric columns."""
    if rows.empty:
        return dict(
            total_events=0, active_days=0, push_events=0,
            issue_events=0, issue_comment_events=0, pr_events=0,
        )
    per_type = rows.groupby("event_type")["event_count"].sum()

    def total_of(types):
        return int(sum(int(per_type.get(t, 0)) for t in types))

    per_day = rows.groupby("event_date")["event_count"].sum()
    return dict(
        total_events=int(rows["event_count"].sum()),
        active_days=int((per_day > 0).sum()),
        push_events=total_of(PUSH_TYPES),
        issue_events=total_of(ISSUE_TYPES),
        issue_comment_events=total_of(ISSUE_COMMENT_TYPES),
        pr_events=total_of(PR_TYPES),
    )


def _cohort_events_by_repo(cohort, daily):
    """Group only selected repositories, keeping unrelated input out of memory."""
    selected = daily.loc[daily["repo_id"].isin(cohort["repo_id"])]
    return {rid: rows for rid, rows in selected.groupby("repo_id")}


def per_repo_stage_table(cohort, daily, coverage, cohort_year, data_kind, *, window_days=30):
    """Build the fixed cohort x 3 bands table, incl. coverage status per band.

    Every cohort repository gets exactly three rows, even if it has no event
    rows at all. Counts are computed inside the UTC day window of each band.
    """
    bands = bands_for(window_days)
    band_order = [name for name, _, _ in bands]
    complete_days = set(coverage["complete_days"])
    by_repo = _cohort_events_by_repo(cohort, daily)

    records = []
    for rec in cohort.itertuples(index=False):
        created = pd.Timestamp(rec.repo_created_day).normalize()
        repo_events = by_repo.get(rec.repo_id)
        if repo_events is None:
            repo_events = daily.iloc[0:0]

        for band_name, lo, hi in bands:
            required = [created + pd.Timedelta(days=offset) for offset in range(lo - 1, hi)]
            covered = sum(1 for day in required if day in complete_days)
            complete = covered == len(required)

            in_band = repo_events[repo_events["event_date"].isin(required)]
            totals = _band_totals(in_band)

            records.append(
                dict(
                    cohort_year=cohort_year,
                    data_kind=data_kind,
                    repo_id=rec.repo_id,
                    repo_created_at=rec.repo_created_at,
                    band=band_name,
                    band_day_start=lo,
                    band_day_end=hi,
                    required_days=len(required),
                    covered_days=int(covered),
                    band_complete=bool(complete),
                    coverage_status="complete" if complete else "incomplete",
                    counts_are_observed_only=not complete,
                    **totals,
                )
            )

    table = pd.DataFrame.from_records(records, columns=STAGE_COLUMNS)
    table["band"] = pd.Categorical(table["band"], categories=band_order, ordered=True)
    return table.sort_values(["repo_id", "band"]).reset_index(drop=True)


def out_of_band_events(cohort, daily, *, window_days=30):
    """Events before creation or beyond the configured three-window horizon."""
    horizon = bands_for(window_days)[-1][2]
    beyond_column = f"beyond_{horizon}_events"
    records = []
    by_repo = _cohort_events_by_repo(cohort, daily)
    for rec in cohort.itertuples(index=False):
        created = pd.Timestamp(rec.repo_created_day).normalize()
        repo_events = by_repo.get(rec.repo_id)
        if repo_events is None:
            continue
        age = (repo_events["event_date"] - created).dt.days + 1
        pre = int(repo_events.loc[age < 1, "event_count"].sum())
        beyond = int(repo_events.loc[age > horizon, "event_count"].sum())
        if pre or beyond:
            records.append(
                dict(repo_id=rec.repo_id, pre_creation_events=pre, **{beyond_column: beyond})
            )
    return pd.DataFrame(records, columns=["repo_id", "pre_creation_events", beyond_column])


# --------------------------------------------------------------------------- #
# cohort aggregation
# --------------------------------------------------------------------------- #
def aggregate_cohort(stage_table, cohort_size, *, cohort_year=None, data_kind=None, window_days=None):
    """Aggregate the cohort per band around one fixed official denominator.

    The official comparison tracks the **same** repositories in all three bands,
    so the denominator is the set of cohort repositories whose whole 90-day
    window was fully covered (complete in every band). Repositories that do not
    meet this stay in ``not_complete_90d_repos`` and never enter the ratio or the
    distributions. When that set is empty the ratio, the event total and the
    quantiles are not computable (``NaN``), never 0.
    For a non-empty stage table the year and data kind can still be inferred,
    preserving the original helper interface. An empty cohort needs the explicit
    context supplied by ``analyze_cohort`` and produces three not-computable rows.
    """
    if window_days is None:
        window_days = int(stage_table["band_day_end"].max()) // 3 if not stage_table.empty else 30
    bands = bands_for(window_days)
    horizon = bands[-1][2]
    if cohort_year is None or data_kind is None:
        if stage_table.empty:
            raise InputError("cohort_year and data_kind are required for an empty stage table")
        if cohort_year is None:
            cohort_year = stage_table["cohort_year"].iloc[0]
        if data_kind is None:
            data_kind = stage_table["data_kind"].iloc[0]
    complete_90d = stage_table.groupby("repo_id")["band_complete"].all()
    official_ids = set(complete_90d[complete_90d].index)
    n_official = len(official_ids)

    rows = []
    for band_name, _, _ in bands:
        band = stage_table[stage_table["band"] == band_name]
        official = band[band["repo_id"].isin(official_ids)]

        active = int((official["total_events"] > 0).sum()) if n_official else 0
        events = official["total_events"]
        days = official["active_days"]

        rows.append(
            dict(
                cohort_year=int(cohort_year),
                data_kind=data_kind,
                band=band_name,
                cohort_size=int(cohort_size),
                **{f"complete_{horizon}d_repos": n_official,
                   f"not_complete_{horizon}d_repos": int(cohort_size) - n_official},
                active_repos=active,
                active_ratio=(active / n_official) if n_official else np.nan,
                total_events_sum=int(events.sum()) if n_official else np.nan,
                events_median=float(events.median()) if n_official else np.nan,
                events_q25=float(events.quantile(0.25)) if n_official else np.nan,
                events_q75=float(events.quantile(0.75)) if n_official else np.nan,
                active_days_median=float(days.median()) if n_official else np.nan,
                active_days_q25=float(days.quantile(0.25)) if n_official else np.nan,
                active_days_q75=float(days.quantile(0.75)) if n_official else np.nan,
            )
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def analyze_cohort(
    metadata_path,
    labels_path,
    daily_counts_path,
    coverage_path,
    cohort_year,
    created_from,
    created_to,
    data_kind="Testing Data",
    *,
    window_days=30,
    cohort_path=None,
):
    """Run the fixed-cohort 90-day analysis for one year and one input set.

    Switching ``cohort_year`` plus the four paths switches the cohort, the
    created-date range, the activity table and the coverage list; the
    computation below is identical for every year.
    """
    metadata = pd.read_csv(metadata_path)
    labels = pd.read_csv(labels_path)
    daily = read_daily_counts(daily_counts_path)
    coverage = read_coverage(coverage_path)

    cohort, exclusions = select_cohort(
        metadata, labels, cohort_year, created_from, created_to
    )
    if cohort_path is not None:
        frozen = pd.read_csv(cohort_path)
        _require_unique(frozen, "repo_id", "frozen cohort")
        missing = set(frozen["repo_id"]) - set(cohort["repo_id"])
        if missing:
            raise InputError(f"Frozen cohort has IDs failing metadata/label/date validation: {sorted(missing)[:10]}")
        exclusions["outside_frozen_cohort"] = len(cohort) - len(frozen)
        cohort = cohort[cohort["repo_id"].isin(frozen["repo_id"])].copy()
        exclusions["cohort_size"] = len(cohort)
    stage_table = per_repo_stage_table(cohort, daily, coverage, cohort_year, data_kind, window_days=window_days)
    aggregate = aggregate_cohort(
        stage_table, cohort_size=len(cohort), cohort_year=cohort_year, data_kind=data_kind, window_days=window_days
    )
    out_of_band = out_of_band_events(cohort, daily, window_days=window_days)

    return {
        "window_days": window_days,
        "observation_days": 3 * window_days,
        "cohort_year": int(cohort_year),
        "data_kind": data_kind,
        "cohort": cohort,
        "stage_table": stage_table,
        "aggregate": aggregate,
        "out_of_band": out_of_band,
        "exclusions": exclusions,
        "coverage": coverage,
        "created_from": to_utc_day(created_from),
        "created_to": to_utc_day(created_to),
    }
