"""把 B 的标签按 ``repo_id`` 接回 A 的事件表，并核对唯一性与覆盖面。

两种数据源：

- 首选 ``events_clean.parquet``（A 的完整事件表，需要 pyarrow）；
- 退路 ``repo_candidates.csv`` 的 ``event_count`` 列（同样由 A 从事件表聚合而来）。

退路只验证“仓库级”可连接性，不验证逐条事件；运行摘要会写明实际使用的数据源。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import (
    project_relative,
    read_csv,
    sha256_file,
    update_run_summary,
    utc_now,
    write_json,
)

JOIN_FIELDS = [
    "repo_id",
    "observed_repo_name",
    "ai_label",
    "event_count",
    "event_share_of_source",
    "event_share_of_pilot_events",
]


def _event_counts_from_parquet(parquet_path: Path) -> tuple[dict[int, int], int, str]:
    import pyarrow.parquet as pq  # 延迟导入：没有 pyarrow 时回退到候选表

    table = pq.read_table(parquet_path, columns=["repo_id"])
    total = table.num_rows
    counts: dict[int, int] = {}
    for value in table.column("repo_id").to_pylist():
        if value is None:
            continue
        key = int(value)
        counts[key] = counts.get(key, 0) + 1
    return counts, total, "events_clean.parquet"


def _event_counts_from_candidates(candidates_csv: Path) -> tuple[dict[int, int], int, str]:
    rows = read_csv(candidates_csv)
    counts = {int(row["repo_id"]): int(row["event_count"]) for row in rows}
    return counts, sum(counts.values()), "repo_candidates.csv:event_count"


def run(
    *,
    metadata_csv: Path,
    labels_csv: Path,
    out_dir: Path,
    events_parquet: Path | None = None,
    candidates_csv: Path | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    metadata = read_csv(metadata_csv)
    labels = read_csv(labels_csv)
    if not metadata or not labels:
        raise ValueError("metadata and labels must be non-empty")

    metadata_ids = [row["repo_id"] for row in metadata]
    label_ids = [row["repo_id"] for row in labels]
    unique_labels = len(set(label_ids)) == len(label_ids)

    counts: dict[int, int] = {}
    total_events = 0
    source = "unavailable"
    if events_parquet and Path(events_parquet).exists():
        try:
            counts, total_events, source = _event_counts_from_parquet(Path(events_parquet))
        except ImportError:
            source = "fallback:pyarrow_missing"
    if source in ("unavailable", "fallback:pyarrow_missing") and candidates_csv and Path(candidates_csv).exists():
        counts, total_events, source = _event_counts_from_candidates(Path(candidates_csv))

    # 先算出每个试点仓库的事件数，才能用“试点事件总数”作分母。
    names = {row["repo_id"]: row.get("observed_repo_name", "") for row in metadata}
    counts_by_repo: dict[str, int] = {}
    missing_from_events: list[str] = []
    for row in labels:
        repo_id = int(row["repo_id"])
        event_count = counts.get(repo_id)
        if event_count is None:
            missing_from_events.append(row["repo_id"])
            event_count = 0
        counts_by_repo[row["repo_id"]] = event_count
    covered_events = sum(counts_by_repo.values())

    per_repo: list[dict[str, Any]] = []
    for row in labels:
        event_count = counts_by_repo[row["repo_id"]]
        per_repo.append(
            {
                "repo_id": row["repo_id"],
                "observed_repo_name": names.get(row["repo_id"], ""),
                "ai_label": row["ai_label"],
                "event_count": event_count,
                # 分母是事件表里全部事件：这个仓库占整个样本事件的比例。
                "event_share_of_source": round(event_count / total_events, 6) if total_events else 0.0,
                # 分母是 50 个试点仓库的事件总数：这个仓库在试点内部的活动占比。
                "event_share_of_pilot_events": round(event_count / covered_events, 6) if covered_events else 0.0,
            }
        )

    by_label_events: dict[str, int] = {}
    for row in per_repo:
        by_label_events[row["ai_label"]] = by_label_events.get(row["ai_label"], 0) + row["event_count"]

    summary = {
        "checked_at_utc": utc_now(),
        "event_source": source,
        "events_total_in_source": total_events,
        "pilot_repos": len(per_repo),
        "pilot_repos_found_in_events": len(per_repo) - len(missing_from_events),
        "missing_from_events": missing_from_events,
        "events_covered_by_pilot": covered_events,
        "events_covered_share_of_source": round(covered_events / total_events, 6) if total_events else 0.0,
        "events_outside_pilot_share": round((total_events - covered_events) / total_events, 6) if total_events else 0.0,
        "event_share_denominators": {
            "event_share_of_source": "事件表全部事件数（events_total_in_source）",
            "event_share_of_pilot_events": "50 个试点仓库的事件总数（events_covered_by_pilot）",
        },
        "events_by_label": dict(sorted(by_label_events.items())),
        "checks": {
            "labels_have_unique_repo_ids": unique_labels,
            "labels_cover_every_metadata_row": sorted(metadata_ids) == sorted(label_ids),
            "every_event_matches_at_most_one_label": unique_labels,
            "all_pilot_repos_present_in_events": not missing_from_events,
            "event_counts_non_negative": all(row["event_count"] >= 0 for row in per_repo),
        },
        "inputs": {
            "metadata_csv": project_relative(metadata_csv),
            "labels_csv": project_relative(labels_csv),
            "events_parquet": project_relative(events_parquet) if events_parquet else None,
            "candidates_csv": project_relative(candidates_csv) if candidates_csv else None,
        },
        "limits": [
            "Only repo_id is used as the join key; repo names in the event table may be historical.",
            "The pilot covers a small sample, so covered/uncovered event shares describe this run only.",
            "event_share_of_source uses all events in the source table; event_share_of_pilot_events uses only the pilot repos' events.",
        ]
        + ([] if source == "events_clean.parquet" else ["Full parquet join not executed; repo-level counts from candidates used."]),
    }
    write_json(out_dir / "join_check.json", summary)

    joined_csv = out_dir / "repo_labels_joined_events.csv"
    from .common import write_csv  # 局部导入避免循环

    write_csv(joined_csv, JOIN_FIELDS, per_repo)
    summary["joined_csv"] = project_relative(joined_csv)
    update_run_summary(out_dir / "run_summary.json", "join", summary)
    return summary
