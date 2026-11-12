"""Generate the round-2 Testing Data for the fixed-cohort 90-day analysis.

Writes, under ``<repo root>/testing_data``:

    testing_data/2024/repo_metadata.csv
    testing_data/2024/repo_ai_labels_analysis.csv
    testing_data/2024/repo_daily_counts.parquet
    testing_data/2024/coverage.json
    testing_data/2024/coverage_missing.json
    testing_data/2026/...            (same five files)

The data is fully synthetic: fictional repository ids, simulated AI labels and
hand-built activity. It exists only to verify the analysis program and must
never be mixed into real statistics. See ``testing_data/README.md`` for the
construction and the expected results.

Run:  python c_lifecycle_analysis/build_testing_data.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO_ROOT / "testing_data"

DAILY_COLUMNS = ["repo_id", "event_date", "event_type", "event_count"]

METADATA_COLUMNS = [
    "repo_id", "observed_repo_name", "api_repo_id", "current_full_name",
    "repo_created_at", "description", "topics_json", "language", "archived",
    "fetch_status", "http_status", "fetched_at_utc",
]

LABEL_COLUMNS = [
    "repo_id", "observed_repo_name", "ai_label_auto", "rule_id", "ai_label_manual",
    "ai_label_final", "label_source", "rule_version", "reason_auto", "reason_human",
    "metadata_fetched_at_utc", "labelled_at_utc", "policy",
]

# --------------------------------------------------------------------------- #
# 2024 test cohort
# --------------------------------------------------------------------------- #
YEAR_2024 = {
    "cohort_year": 2024,
    "created_from": "2024-04-01",
    "created_to": "2024-04-30",
    "repos": [
        # repo_id, name, created_at, ai_label_final, fetch_status, api_repo_id
        (900000000000000001, "test-org/early-decline-2024", "2024-04-01T12:00:00Z", "included", "ok", None),
        (900000000000000002, "test-org/sustained-2024", "2024-04-02T09:30:00Z", "included", "ok", None),
        (900000000000000003, "test-org/growing-2024", "2024-04-03T23:45:00Z", "included", "ok", None),
        (900000000000000004, "test-org/idle-2024", "2024-04-04T00:05:00Z", "included", "ok", None),
        (900000000000000091, "test-org/excluded-2024", "2024-04-05T10:00:00Z", "excluded", "ok", None),
        (900000000000000092, "test-org/uncertain-2024", "2024-04-06T10:00:00Z", "uncertain", "ok", None),
        (900000000000000093, "test-org/no-label-2024", "2024-04-07T10:00:00Z", "", "ok", None),
        (900000000000000094, "test-org/fetch-error-2024", "2024-04-08T10:00:00Z", "included", "error", None),
        (900000000000000096, "test-org/api-mismatch-2024", "2024-04-09T10:00:00Z", "included", "ok", 12345),
        (900000000000000097, "test-org/no-created-at-2024", "", "included", "ok", None),
        (900000000000000095, "test-org/out-of-range-2024", "2024-05-15T10:00:00Z", "included", "ok", None),
    ],
    # repo_id, event_date (UTC), event_type, event_count
    "events": [
        # R1 early then decline: active in the first days of band 1, one event at
        # the band-1 end and the band-2 start, nothing afterwards.
        (900000000000000001, "2024-03-31", "PushEvent", 1),          # before creation
        (900000000000000001, "2024-04-01", "PushEvent", 5),          # day 1
        (900000000000000001, "2024-04-02", "PushEvent", 3),
        (900000000000000001, "2024-04-02", "IssuesEvent", 1),
        (900000000000000001, "2024-04-03", "IssuesEvent", 2),
        (900000000000000001, "2024-04-30", "PushEvent", 1),          # day 30 (band 1 end)
        (900000000000000001, "2024-05-01", "PushEvent", 1),          # day 31 (band 2 start)
        (900000000000000001, "2024-06-30", "PushEvent", 1),          # day 91
        # R2 sustained: a few events in every band.
        (900000000000000002, "2024-04-02", "PushEvent", 2),
        (900000000000000002, "2024-04-16", "PullRequestEvent", 1),
        (900000000000000002, "2024-04-16", "PullRequestReviewEvent", 1),
        (900000000000000002, "2024-05-01", "PushEvent", 1),          # day 30
        (900000000000000002, "2024-05-02", "IssuesEvent", 1),        # day 31
        (900000000000000002, "2024-05-16", "PushEvent", 1),
        (900000000000000002, "2024-05-31", "PullRequestReviewCommentEvent", 1),  # day 60
        (900000000000000002, "2024-06-01", "PushEvent", 1),          # day 61
        (900000000000000002, "2024-06-15", "PushEvent", 1),
        (900000000000000002, "2024-06-30", "PushEvent", 1),          # day 90
        # R3 gradually growing: more events in each later band.
        (900000000000000003, "2024-04-03", "PushEvent", 1),
        (900000000000000003, "2024-04-10", "IssueCommentEvent", 1),
        (900000000000000003, "2024-05-03", "PushEvent", 2),          # day 31
        (900000000000000003, "2024-05-20", "IssuesEvent", 1),
        (900000000000000003, "2024-05-20", "IssueCommentEvent", 1),
        (900000000000000003, "2024-06-01", "PushEvent", 1),          # day 60
        (900000000000000003, "2024-06-02", "PushEvent", 2),          # day 61
        (900000000000000003, "2024-06-15", "PushEvent", 3),
        (900000000000000003, "2024-06-15", "PullRequestEvent", 1),
        (900000000000000003, "2024-07-01", "PushEvent", 4),          # day 90
        (900000000000000003, "2024-07-02", "PushEvent", 2),          # day 91
        # R4 idle: no event rows at all, must stay in the fixed cohort.
        # Control repos: must never enter the AI cohort.
        (900000000000000091, "2024-04-05", "PushEvent", 9),          # excluded
        (900000000000000092, "2024-04-06", "PushEvent", 7),          # uncertain
        (900000000000000093, "2024-04-07", "PushEvent", 5),          # no label
        (900000000000000095, "2024-05-15", "PushEvent", 3),          # out of range
    ],
}

# --------------------------------------------------------------------------- #
# 2026 test cohort (deliberately different counts)
# --------------------------------------------------------------------------- #
YEAR_2026 = {
    "cohort_year": 2026,
    "created_from": "2026-04-01",
    "created_to": "2026-04-30",
    "repos": [
        (910000000000000001, "test-org/early-decline-2026", "2026-04-01T08:00:00Z", "included", "ok", None),
        (910000000000000002, "test-org/sustained-2026", "2026-04-02T18:30:00Z", "included", "ok", None),
        (910000000000000003, "test-org/growing-2026", "2026-04-03T06:15:00Z", "included", "ok", None),
        (910000000000000004, "test-org/idle-2026", "2026-04-04T22:40:00Z", "included", "ok", None),
        (910000000000000091, "test-org/excluded-2026", "2026-04-05T10:00:00Z", "excluded", "ok", None),
        (910000000000000092, "test-org/uncertain-2026", "2026-04-06T10:00:00Z", "uncertain", "ok", None),
        (910000000000000093, "test-org/no-label-2026", "2026-04-07T10:00:00Z", "", "ok", None),
        (910000000000000094, "test-org/fetch-error-2026", "2026-04-08T10:00:00Z", "included", "error", None),
        (910000000000000096, "test-org/api-mismatch-2026", "2026-04-09T10:00:00Z", "included", "ok", 12345),
        (910000000000000097, "test-org/no-created-at-2026", "", "included", "ok", None),
        (910000000000000095, "test-org/out-of-range-2026", "2026-05-15T10:00:00Z", "included", "ok", None),
    ],
    "events": [
        (910000000000000001, "2026-04-01", "PushEvent", 3),
        (910000000000000001, "2026-04-05", "IssuesEvent", 1),
        (910000000000000001, "2026-05-10", "PushEvent", 1),
        (910000000000000002, "2026-04-02", "PushEvent", 4),
        (910000000000000002, "2026-05-02", "PushEvent", 2),
        (910000000000000002, "2026-06-01", "PushEvent", 2),
        (910000000000000003, "2026-04-03", "IssueCommentEvent", 1),
        (910000000000000003, "2026-05-03", "PullRequestEvent", 3),
        (910000000000000003, "2026-06-02", "PushEvent", 7),
        # S4 idle: no event rows.
        (910000000000000091, "2026-04-05", "PushEvent", 6),
        (910000000000000092, "2026-04-06", "PushEvent", 4),
        (910000000000000093, "2026-04-07", "PushEvent", 2),
        (910000000000000095, "2026-05-15", "PushEvent", 1),
    ],
}

# days dropped in the ``coverage_missing`` variant: they lie inside the day-61..90
# window of the late-created cohort repositories, so that band becomes incomplete.
MISSING_WINDOW = ("-07-01", "-07-05")


def build_metadata(spec):
    rows = []
    for repo_id, name, created, _label, fetch_status, api_repo_id in spec["repos"]:
        rows.append(
            {
                "repo_id": repo_id,
                "observed_repo_name": name,
                "api_repo_id": repo_id if api_repo_id is None else api_repo_id,
                "current_full_name": name,
                "repo_created_at": created,
                "description": "synthetic Testing Data repository",
                "topics_json": '["testing-data"]',
                "language": "Python",
                "archived": False,
                "fetch_status": fetch_status,
                "http_status": 200 if fetch_status == "ok" else 500,
                "fetched_at_utc": "2026-11-12T00:00:00Z",
            }
        )
    return pd.DataFrame(rows, columns=METADATA_COLUMNS)


def build_labels(spec):
    rows = []
    for repo_id, name, _created, label, _fetch_status, _api in spec["repos"]:
        rows.append(
            {
                "repo_id": repo_id,
                "observed_repo_name": name,
                "ai_label_auto": label,
                "rule_id": "testing_rule",
                "ai_label_manual": label,
                "ai_label_final": label,
                "label_source": "testing",
                "rule_version": "testing_v1",
                "reason_auto": "synthetic label for Testing Data",
                "reason_human": "",
                "metadata_fetched_at_utc": "2026-11-12T00:00:00Z",
                "labelled_at_utc": "2026-11-12T00:00:00Z",
                "policy": "testing",
            }
        )
    return pd.DataFrame(rows, columns=LABEL_COLUMNS)


def build_daily(spec):
    df = pd.DataFrame(spec["events"], columns=["repo_id", "event_date", "event_type", "event_count"])
    df = df.astype({"repo_id": "int64", "event_date": "string",
                    "event_type": "string", "event_count": "int64"})
    return df[DAILY_COLUMNS]


def build_coverage(spec, drop_days=False):
    year = spec["cohort_year"]
    # a single window that contains every cohort repository's day 1..90
    requested = pd.date_range(f"{year}-04-01", f"{year}-07-28", freq="D")
    requested_days = [d.strftime("%Y-%m-%d") for d in requested]

    missing_hours = []
    if drop_days:
        start, end = MISSING_WINDOW
        dropped = pd.date_range(f"{year}{start}", f"{year}{end}", freq="D")
        for day in dropped:
            for hour in range(24):
                missing_hours.append(f"{day.strftime('%Y-%m-%d')}T{hour:02d}:00:00Z")

    requested_hours = len(requested_days) * 24
    return {
        "requested_days": requested_days,
        "requested_hours": requested_hours,
        "verified_hours": requested_hours - len(missing_hours),
        "missing_source_hours": sorted(missing_hours),
        "event_dates_use_utc_event_time": True,
        "archive_presence_does_not_prove_all_public_activity_was_captured": True,
    }


def write_year(spec):
    year_dir = OUT_ROOT / str(spec["cohort_year"])
    year_dir.mkdir(parents=True, exist_ok=True)

    build_metadata(spec).to_csv(year_dir / "repo_metadata.csv", index=False, encoding="utf-8")
    build_labels(spec).to_csv(year_dir / "repo_ai_labels_analysis.csv", index=False, encoding="utf-8")
    build_daily(spec).to_parquet(year_dir / "repo_daily_counts.parquet", index=False)

    for name, drop in (("coverage.json", False), ("coverage_missing.json", True)):
        payload = build_coverage(spec, drop_days=drop)
        (year_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"{spec['cohort_year']}: wrote 5 files to {year_dir}")


def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    for spec in (YEAR_2024, YEAR_2026):
        write_year(spec)


if __name__ == "__main__":
    main()
