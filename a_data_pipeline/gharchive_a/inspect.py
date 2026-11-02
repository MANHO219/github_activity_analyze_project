"""Inspect all raw lines before cleaning and retain the observed distributions."""
from collections import Counter

from .common import json_line, select_inputs, stage_directory, write_csv, write_json
from .records import iter_records


def inspect(cfg, data_dir, output, allow_missing=False):
    files, manifest = select_inputs(cfg, data_dir, allow_missing)
    status_counts, types, issues, reasons = Counter(), Counter(), Counter(), Counter()
    repositories, samples, per_file = set(), [], []
    minimum = maximum = None
    with stage_directory(output, "inspect", cfg) as out:
        write_json(out / "input_manifest.json", manifest)
        with (out / "raw_anomalies.jsonl").open("w", encoding="utf-8") as anomalies:
            for path in files:
                counts = Counter()
                file_repos = set()
                for record in iter_records(path):
                    status = record["status"]
                    counts[status] += 1
                    status_counts[status] += 1
                    if status != "blank" and len(samples) < cfg["raw_preview_rows"]:
                        samples.append(record)
                    if status == "valid":
                        types[record["event_type"]] += 1
                        repositories.add(record["repo_id"])
                        file_repos.add(record["repo_id"])
                        issues.update(record["optional_field_issues"])
                        stamp = record["event_time"]
                        minimum = stamp if minimum is None else min(minimum, stamp)
                        maximum = stamp if maximum is None else max(maximum, stamp)
                        if record["time_outside_file_hour"]:
                            counts["time_outside_file_hour"] += 1
                    elif status != "blank":
                        reasons[record["reason"]] += 1
                        json_line(anomalies, record)
                per_file.append({"source_file": path.name, "blank_lines": counts["blank"],
                                 "nonempty_lines": counts["valid"] + counts["invalid"] + counts["parse_error"],
                                 "parse_errors": counts["parse_error"], "invalid_records": counts["invalid"],
                                 "valid_before_dedup": counts["valid"], "unique_valid_repos": len(file_repos),
                                 "time_outside_file_hour": counts["time_outside_file_hour"]})
        summary = {"count_scope": "raw occurrences before deduplication", "line_status_counts": dict(status_counts),
                   "unique_valid_repos": len(repositories), "event_time_min": minimum, "event_time_max": maximum,
                   "event_types": dict(sorted(types.items())), "rejection_reasons": dict(reasons),
                   "optional_field_issues": dict(issues), "coverage": manifest}
        write_json(out / "inspection_summary.json", summary)
        write_json(out / "raw_examples.json", samples)
        write_csv(out / "file_statistics.csv", list(per_file[0]), per_file)
        write_csv(out / "raw_event_types.csv", ["event_type", "occurrences_before_dedup"],
                  ({"event_type": name, "occurrences_before_dedup": number} for name, number in sorted(types.items())))
    return summary
