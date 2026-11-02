"""Portable CSV exports and typed, batched Parquet output."""
from __future__ import annotations

import csv
import gzip
import json
from datetime import date, datetime
from pathlib import Path

from .common import EVENT_COLUMNS, write_csv


def event_schema():
    import pyarrow as pa
    return pa.schema([
        ("event_id", pa.string()), ("event_type", pa.string()), ("event_time", pa.timestamp("us", tz="UTC")),
        ("repo_id", pa.int64()), ("repo_name", pa.string()), ("actor_id", pa.int64()),
        ("actor_login", pa.string()), ("event_date", pa.date32()), ("source_file", pa.string()),
        ("source_line", pa.int64()), ("source_hour", pa.timestamp("us", tz="UTC")),
        ("time_outside_file_hour", pa.bool_()), ("optional_field_issues", pa.list_(pa.string()))])


def csv_event(record):
    row = {key: record.get(key) for key in EVENT_COLUMNS}
    flags = row["optional_field_issues"]
    row["optional_field_issues"] = json.dumps(flags, ensure_ascii=False) if isinstance(flags, list) else flags
    return row


def decoded_event(record):
    row = dict(record)
    row["optional_field_issues"] = json.loads(row["optional_field_issues"]) if isinstance(row["optional_field_issues"], str) else row["optional_field_issues"]
    row["time_outside_file_hour"] = bool(row["time_outside_file_hour"])
    return row


def export_events(rows, output, preview_rows=100, batch_rows=10000, parquet=True):
    out = Path(output)
    writer = None
    if parquet:
        import pyarrow.parquet as pq
        (out / "events_clean.parquet").mkdir()
        writer = pq.ParquetWriter(out / "events_clean.parquet/part-00000.parquet", event_schema(), compression="snappy")
    batch, preview, count = [], [], 0
    try:
        with gzip.open(out / "events_clean.csv.gz", "wt", encoding="utf-8", newline="") as handle:
            csv_writer = csv.DictWriter(handle, fieldnames=EVENT_COLUMNS)
            csv_writer.writeheader()
            for original in rows:
                row = decoded_event(original)
                csv_writer.writerow(csv_event(row))
                if count < preview_rows:
                    preview.append(csv_event(row))
                count += 1
                if writer:
                    typed = {key: row.get(key) for key in EVENT_COLUMNS}
                    for key in ("event_time", "source_hour"):
                        typed[key] = datetime.fromisoformat(typed[key].replace("Z", "+00:00"))
                    typed["event_date"] = date.fromisoformat(typed["event_date"])
                    batch.append(typed)
                    if len(batch) >= batch_rows:
                        _write_batch(writer, batch)
                        batch.clear()
            if writer and batch:
                _write_batch(writer, batch)
    finally:
        if writer:
            writer.close()
    write_csv(out / "events_preview.csv", EVENT_COLUMNS, preview)
    return count


def _write_batch(writer, rows):
    import pyarrow as pa
    writer.write_table(pa.Table.from_pylist(rows, schema=event_schema()))


def export_daily(rows, output, parquet=True):
    out = Path(output)
    columns = ["repo_id", "event_date", "event_type", "event_count"]
    writer = None
    if parquet:
        import pyarrow as pa
        import pyarrow.parquet as pq
        schema = pa.schema([("repo_id", pa.int64()), ("event_date", pa.date32()), ("event_type", pa.string()), ("event_count", pa.int64())])
        (out / "repo_daily_counts.parquet").mkdir()
        writer = pq.ParquetWriter(out / "repo_daily_counts.parquet/part-00000.parquet", schema, compression="snappy")
    total, batch = 0, []
    try:
        with (out / "repo_daily_counts.csv").open("w", encoding="utf-8", newline="") as handle:
            csv_writer = csv.DictWriter(handle, fieldnames=columns)
            csv_writer.writeheader()
            for record in rows:
                row = dict(record)
                csv_writer.writerow(row)
                total += int(row["event_count"])
                if writer:
                    row["event_date"] = date.fromisoformat(row["event_date"])
                    batch.append(row)
                    if len(batch) == 10000:
                        writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                        batch.clear()
            if writer and batch:
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
    finally:
        if writer:
            writer.close()
    return total
