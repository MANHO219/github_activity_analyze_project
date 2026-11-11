"""Local Spark execution: a partition reads one hourly archive, then Spark shuffles.

Parsing/field validation is deliberately shared with the reference pipeline.
Deduplication, conflict handling and aggregation are independently performed with
Spark DataFrames. This is a local filesystem pilot, not a cluster deployment.
"""
from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

from .common import EVENT_COLUMNS, ROOT, select_inputs, stage_directory, write_csv, write_json
from .export import export_daily, export_events
from .records import iter_records


def parse_archive(path):
    for record in iter_records(path):
        if record["status"] == "valid":
            record["raw_line"] = None  # Raw payload is retained in the input archive.
        record["_corrupt_record"] = record.get("raw_line") if record["status"] == "parse_error" else None
        yield record


def configure_java():
    if not os.environ.get("JAVA_HOME"):
        for candidate in (Path(sys.prefix) / "lib/jvm", Path(sys.prefix)):
            if (candidate / "bin/java").is_file():
                os.environ["JAVA_HOME"] = str(candidate)
                break
    os.environ["PYSPARK_PYTHON"] = sys.executable


def parsed_schema():
    from pyspark.sql.types import ArrayType, BooleanType, LongType, StringType, StructField, StructType
    types = {"repo_id": LongType(), "actor_id": LongType(), "source_line": LongType(),
             "time_outside_file_hour": BooleanType(), "optional_field_issues": ArrayType(StringType())}
    columns = EVENT_COLUMNS + ["status", "reason", "canonical_sha256", "raw_line", "raw_hex", "parse_detail", "_corrupt_record"]
    return StructType([StructField(key, types.get(key, StringType()), True) for key in columns])


def rows_as_dict(frame):
    for row in frame.toLocalIterator():
        yield row.asDict(recursive=True)


def clean_spark(cfg, data_dir, output, allow_missing=False, master="local[2]", benchmark=False):
    if not benchmark and not (master == "local" or master.startswith("local[")):
        raise ValueError("This pilot accepts local Spark masters only; raw files live on this machine")
    from pyspark import StorageLevel
    from pyspark.sql import SparkSession, Window, functions as F
    files, manifest = select_inputs(cfg, data_dir, allow_missing)
    configure_java()
    with stage_directory(output, "spark_clean", cfg) as out:
        write_json(out / "input_manifest.json", manifest)
        with zipfile.ZipFile(out / "worker_code.zip", "w") as archive:
            for path in (ROOT / "gharchive_a").glob("*.py"):
                archive.write(path, f"gharchive_a/{path.name}")
        java_path = Path(os.environ.get("JAVA_HOME", "")) / "bin/java"
        java = subprocess.run([str(java_path) if java_path.is_file() else "java", "-version"], capture_output=True, text=True, timeout=10)
        if java.returncode:
            raise RuntimeError(f"Java is unavailable: {java.stderr}")
        write_json(out / "spark_environment.json", {"master": master, "java": java.stderr.strip(),
                   "python": sys.executable, "java_home": os.environ.get("JAVA_HOME"),
                   "timezone": "UTC", "parquet_timestamp_type": "TIMESTAMP_MICROS", "hour_file_partitions": len(files)})
        builder = (SparkSession.builder.master(master).appName("CS5488-" + out.name)
                 .config("spark.sql.session.timeZone", "UTC")
                 .config("spark.sql.parquet.outputTimestampType", "TIMESTAMP_MICROS"))
        if not benchmark:
            builder = (builder.config("spark.sql.shuffle.partitions", max(2, len(files) * 2))
                       .config("spark.driver.host", "127.0.0.1")
                       .config("spark.driver.bindAddress", "127.0.0.1")
                       .config("spark.ui.enabled", "false"))
        spark = builder.getOrCreate()
        write_json(out / "effective_spark_config.json", dict(spark.sparkContext.getConf().getAll()))
        write_json(out / "application.json", {"application_id": spark.sparkContext.applicationId,
                                             "master": spark.sparkContext.master})
        spark.sparkContext.setLogLevel("WARN")
        try:
            spark.sparkContext.addPyFile(str(out / "worker_code.zip"))
            parsed = spark.createDataFrame(spark.sparkContext.parallelize([str(p) for p in files], len(files)).flatMap(parse_archive), parsed_schema())
            parsed = parsed.persist(StorageLevel.DISK_ONLY)
            counts = {row["status"]: row["count"] for row in parsed.groupBy("status").count().collect()}
            valid = parsed.filter(F.col("status") == "valid")
            valid.select(*(EVENT_COLUMNS + ["canonical_sha256"])).write.parquet(str(out / "valid_before_dedup.parquet"))
            rejected = parsed.filter(F.col("status").isin("parse_error", "invalid"))
            rejected.write.json(str(out / "rejected_records.jsonl"))
            parsed.filter((F.size("optional_field_issues") > 0) | F.col("time_outside_file_hour")).select(
                "event_id", "source_file", "source_line", "optional_field_issues", "time_outside_file_hour").write.json(str(out / "flagged_records.jsonl"))
            groups = valid.groupBy("event_id").agg(F.count("*").alias("occurrences"), F.countDistinct("canonical_sha256").alias("variants"))
            conflict = valid.join(groups.filter("variants > 1").select("event_id"), "event_id", "inner")
            safe = valid.join(groups.filter("variants = 1").select("event_id"), "event_id", "inner")
            ranked = safe.withColumn("occurrence_rank", F.row_number().over(Window.partitionBy("event_id").orderBy("source_hour", "source_line")))
            duplicates = ranked.filter("occurrence_rank > 1")
            cleaned = ranked.filter("occurrence_rank = 1").select(*EVENT_COLUMNS).persist(StorageLevel.DISK_ONLY)
            conflict.write.json(str(out / "conflicting_records.jsonl"))
            duplicates.write.json(str(out / "duplicate_records.jsonl"))
            clean_count = export_events(rows_as_dict(cleaned.orderBy("source_hour", "source_line")), out, cfg["clean_preview_rows"], parquet=False)
            cleaned.withColumn("event_time", F.to_timestamp("event_time")).withColumn("source_hour", F.to_timestamp("source_hour")).withColumn(
                "event_date", F.to_date("event_date")).write.parquet(str(out / "events_clean.parquet"))
            daily = cleaned.groupBy("repo_id", "event_date", "event_type").agg(F.count("*").alias("event_count"))
            grouped_total = export_daily(rows_as_dict(daily.orderBy("repo_id", "event_date", "event_type")), out, parquet=False)
            daily.withColumn("event_date", F.to_date("event_date")).write.parquet(str(out / "repo_daily_counts.parquet"))
            names = cleaned.groupBy("repo_id", "repo_name").agg(F.min("event_time").alias("first_observed_at"), F.max("event_time").alias("last_observed_at"), F.count("*").alias("event_count"))
            write_csv(out / "repo_name_history.csv", ["repo_id", "repo_name", "first_observed_at", "last_observed_at", "event_count"], rows_as_dict(names.orderBy("repo_id", "repo_name")))
            name_window = Window.partitionBy("repo_id").orderBy(F.col("event_time").desc(), F.col("source_hour").desc(), F.col("source_line").desc())
            last_name = cleaned.filter(F.col("repo_name").isNotNull()).withColumn("name_rank", F.row_number().over(name_window))
            candidates = cleaned.groupBy("repo_id").agg(F.min("event_time").alias("first_observed_at"), F.max("event_time").alias("last_observed_at"), F.count("*").alias("event_count"), F.countDistinct("repo_name").alias("observed_name_count"))
            candidates = candidates.join(last_name.filter("name_rank = 1").select("repo_id", "repo_name"), "repo_id", "left")
            write_csv(out / "repo_candidates.csv", ["repo_id", "repo_name", "first_observed_at", "last_observed_at", "event_count", "observed_name_count"], rows_as_dict(candidates.orderBy("repo_id")))
            duplicates_count, conflict_count = duplicates.count(), conflict.count()
            checks = {"valid_count_reconciles": counts.get("valid", 0) == clean_count + duplicates_count + conflict_count,
                      "grouped_count_reconciles": grouped_total == clean_count,
                      "clean_ids_unique": cleaned.select("event_id").distinct().count() == clean_count}
            summary = {"rule_version": manifest["rule_version"], "engine": "spark", "master": master,
                       "line_status_counts": counts, "cleaned_events": clean_count, "duplicates_removed": duplicates_count,
                       "nonempty_lines": sum(counts.get(key, 0) for key in ("valid", "invalid", "parse_error")),
                       "time_outside_file_hour_before_dedup": valid.filter("time_outside_file_hour").count(),
                       "time_outside_file_hour_clean": cleaned.filter("time_outside_file_hour").count(),
                       "conflicting_ids": groups.filter("variants > 1").count(), "conflict_occurrences_excluded": conflict_count,
                       "conflict_policy": "exclude all occurrences of a conflicting event ID until reviewed",
                       "rejection_reasons": {r["reason"]: r["count"] for r in rejected.groupBy("reason").count().collect()},
                       "clean_event_types": {r["event_type"]: r["count"] for r in cleaned.groupBy("event_type").count().collect()},
                       "clean_unique_repos": cleaned.select("repo_id").distinct().count(),
                       "grouped_event_count_sum": grouped_total, "checks": checks, "coverage": manifest,
                       "formats": ["csv.gz", "parquet"], "parser": "shared strict Python parser with explicit Spark schema"}
            write_json(out / "quality_summary.json", summary)
            if not all(checks.values()):
                raise RuntimeError("Spark count reconciliation failed")
        finally:
            spark.stop()
    return summary
