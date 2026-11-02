"""对 ``repo_metadata.csv`` 应用 AI 规则，产出 ``repo_ai_labels.csv``。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from .common import (
    project_relative,
    read_csv,
    sha256_file,
    update_run_summary,
    utc_now,
    write_csv,
    write_json,
)
from .rules import LABEL_FIELDS, RuleSet, label_rows, load_rules, summary_counts


def run(
    metadata_csv: Path,
    out_dir: Path,
    rules_path: Path,
    *,
    labelled_at: str | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    metadata_rows = read_csv(metadata_csv)
    if not metadata_rows:
        raise ValueError(f"no metadata rows in {metadata_csv}")

    rules = RuleSet(load_rules(rules_path))
    labels = label_rows(metadata_rows, rules, labelled_at=labelled_at)
    write_csv(out_dir / "repo_ai_labels.csv", LABEL_FIELDS, labels)

    counts = summary_counts(labels)
    uncertain = [row for row in labels if row["ai_label"] == "uncertain"]
    summary = {
        "rules_version": rules.version,
        "rules_file": project_relative(rules_path),
        "rules_sha256": sha256_file(rules_path),
        "metadata_csv": project_relative(metadata_csv),
        "metadata_sha256": sha256_file(metadata_csv),
        "labelled_at_utc": labels[0]["labelled_at_utc"] if labels else utc_now(),
        "input_rows": len(metadata_rows),
        "labelled_rows": len(labels),
        "labels_csv": project_relative(out_dir / "repo_ai_labels.csv"),
        "labels_sha256": sha256_file(out_dir / "repo_ai_labels.csv"),
        **counts,
        "uncertain_repo_ids": [row["repo_id"] for row in uncertain],
        "counts_check": {
            "included+excluded+uncertain": sum(counts["by_label"].values()),
            "equals_input_rows": sum(counts["by_label"].values()) == len(metadata_rows),
            "unique_repo_ids": len({row["repo_id"] for row in labels}) == len(labels),
        },
    }
    write_json(out_dir / "label_summary.json", summary)
    update_run_summary(out_dir / "run_summary.json", "labels", summary)
    return summary


def sort_labels(labels: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    order = {"included": 0, "uncertain": 1, "excluded": 2}
    return sorted(labels, key=lambda row: (order.get(row["ai_label"], 9), int(row["repo_id"])))
