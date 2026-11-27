# Curated Final Data & Verification Deliverables (Group 22)

This directory packages the compact, git-friendly final datasets, verification summaries, and execution logs backing the figures and tables in our **CS5488 Final Project Report**. Full raw GH Archive hourly dumps (89.29 GB compressed across 54 UTC days) and full Spark event log tarballs are excluded from Git due to repository size limits and can be reproduced via the scripts in this repository.

## Directory Contents (~3.1 MB Total)

| Directory | Pipeline | Contents | Key Report Links |
| :--- | :---: | :--- | :--- |
| [`pipeline_a_54d_summary/`](pipeline_a_54d_summary/) | **A** | Daily event/byte/repo counts (`day_metrics.csv`), ingest/step/merge timings, orchestration metadata, and run summaries for April 1–27, 2024 & 2026 (1,296 verified hourly `.json.gz` files; 243,525,356 unique events). | Section 2, Table 2, Figure 1 |
| [`pipeline_b_frozen_cohorts/`](pipeline_b_frozen_cohorts/) | **B** | Activity-blind frozen cohorts (`2024/` & `2026/`, 200 repositories each), `cohort_manifest.json`, `repo_ai_labels_analysis.csv`, `repo_metadata.csv`, `selection_log.csv`, `source_selection.json`, and `scope_policy.json` (`assistant_reviewed_user_scope`). | Section 5, Table 7, Figure 7 |
| [`pipeline_c_21d_analysis/`](pipeline_c_21d_analysis/) | **C** | Final 21-day post-creation activity metrics (`combined_cohort_window_summary.csv`, `supplementary_metrics.csv`, `activity_trajectories.csv`, `repo_window_metrics.csv`), `swe_agent_first_week_breakdown.json`, `validation.json`, `timings_and_inputs.json`, joined per-cohort daily activity inputs, execution/replay logs, figures, and `SHA256SUMS.txt`. | Section 6, Table 8, Figures 8–10 |

## Parallel & Distributed Spark Evidence (Already Tracked in `d_parallel_experiments/`)

- **6-Hour Controlled Strong-Scaling Benchmark (`L1`, `L4`, `D4`, 3 formal runs each)**:
  - Summary & stability JSONs: [`../d_parallel_experiments/results/six_hour_20261110_20261111/`](../d_parallel_experiments/results/six_hour_20261110_20261111/)
  - 13-field Python-vs-Spark zero-diff reconciliation: [`../d_parallel_experiments/results/python_spark_6h_20261111/`](../d_parallel_experiments/results/python_spark_6h_20261111/)
- **48-Hour Unified Rolling Batch Acceptance (`L4 24h`, `L4 6h`, `Python 24h`, 19/19 checks passed)**:
  - Validation summaries & stage timings CSV: [`../d_parallel_experiments/docs/two_day_validation_20261114.md`](../d_parallel_experiments/docs/two_day_validation_20261114.md), [`../d_parallel_experiments/docs/two_day_validation_20261114.json`](../d_parallel_experiments/docs/two_day_validation_20261114.json), [`../d_parallel_experiments/docs/two_day_stage_timings_20261114.csv`](../d_parallel_experiments/docs/two_day_stage_timings_20261114.csv)
- **Full Spark Event-Log Tarballs**: Retained offline (`experiment_evidence_20261111.tar.gz`, SHA-256 `72a2c248c5534fc397028496c1f1ff472d4459c417684dd9a99335e3e94910b9`; see [`../d_parallel_experiments/README.md`](../d_parallel_experiments/README.md)).
